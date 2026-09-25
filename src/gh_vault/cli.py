from __future__ import annotations

import argparse
import getpass
import os
import re
import sys
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from .actions import action_values, check_workflows, default_repo, export_act, import_variables, json_result, migrate_env_source, remote_secret_status, run_act, runtime_environment, suggested_env, sync
from .bitwarden import assert_connection_current, default_bws_config, load_bws_endpoints, load_local_adapter, organization_uuid, project_uuid, read_environment, reject_bws_overrides, resolve_project
from .envfiles import apply_bitwarden_restore, archive_environment, example_file_for, format_dotenv_value, list_environments, migrate_environment_archive, prepare_bitwarden_restore, project_namespace, restore_environment, show_environment
from .github import TokenMetadata, inspect_token
from .store import BitwardenConnection, EnvironmentStore, Profile, StoreError, VaultStore

NAME_PATTERN = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9._-]{0,63})$")
PROFILE_NAME_ERROR = "must be 1-64 characters; first character must be a letter or digit, the rest may be letters, digits, dot, underscore, or hyphen"

# GitHub token alphabets by class.
#   classic PAT: 36+ chars from [A-Za-z0-9_] beginning with a known prefix.
#   fine-grained: prefix 'github_pat_' followed by 22+ base62-or-underscore chars.
#   OAuth user token (gho_*): 36 chars.
# The masked-output sentinel that `gh auth status` prints without -t looks
# like a prefix followed by a run of '*' characters. Reject it before any
# network call.
_GH_MASKED_SENTINEL = re.compile(r"^(?:gh[pousr]_|github_pat_)\*+$")
_TOKEN_ALPHABET = re.compile(r"^[A-Za-z0-9_]+$")


def profile_name(value: str) -> str:
    if not NAME_PATTERN.fullmatch(value):
        raise argparse.ArgumentTypeError(PROFILE_NAME_ERROR)
    return value


def _validate_token_format(token: str) -> str:
    if not token:
        raise StoreError("token is empty")
    if "\n" in token or "\r" in token:
        raise StoreError("token must be a single line")
    if _GH_MASKED_SENTINEL.fullmatch(token):
        raise StoreError("token is the masked output of 'gh auth status' without -t; rerun with -t or use 'gh auth token'")
    if len(token) < 36 or len(token) > 255:
        raise StoreError(f"token length {len(token)} is outside the supported range 36..255")
    if not _TOKEN_ALPHABET.fullmatch(token):
        raise StoreError("token contains characters outside the GitHub token alphabet")
    return token


def parse_scopes(value: str) -> tuple[str, ...]:
    return tuple(dict.fromkeys(part.strip() for part in value.split(",") if part.strip()))


def github_environment(value: str) -> str:
    if not value:
        raise argparse.ArgumentTypeError("GitHub environment must not be empty")
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="gh-vault", description="Store GitHub credentials and project environment archives safely.")
    commands = parser.add_subparsers(dest="command", required=True)
    set_profile = commands.add_parser("set", help="create or replace a profile", description="Validate a GitHub token and create or replace its named profile in the encrypted vault.")
    set_profile.add_argument("name", type=profile_name, help="profile name"); set_profile.add_argument("--scopes", type=parse_scopes, help="comma-separated scopes; disables automatic classic-PAT detection"); set_profile.add_argument("--note", default="", help="operator note"); set_profile.add_argument("--stdin", action="store_true", help="read the token from standard input"); set_profile.set_defaults(force=True)
    commands.add_parser("list", help="list token profiles", description="Display stored token profiles, their scopes, expiration, and active selection.")
    activate = commands.add_parser("activate", help="select the default profile", description="Select the token profile used when a command does not name one."); activate.add_argument("name", type=profile_name, help="profile name")
    commands.add_parser("status", help="show the active profile", description="Show the profile selected as the default GitHub token.")
    find = commands.add_parser("find", help="find profiles by token", description="Find profiles containing a token read from standard input without printing the token."); find.add_argument("--stdin", action="store_true", help="read the token from standard input")
    output = commands.add_parser("output", help="print a token for piping", description="Print only the selected token to standard output for piping into another command."); output.add_argument("--name", type=profile_name, help="profile name; defaults to the active profile")
    remove = commands.add_parser("remove", help="delete a profile", description="Delete a token profile and its encrypted token from the vault."); remove.add_argument("name", type=profile_name, help="profile name")
    run = commands.add_parser("run", help="run a command with a token", description="Run a child command with the selected token in its environment only."); run.add_argument("--name", type=profile_name, help="profile name; defaults to the active profile"); run.add_argument("program", nargs=argparse.REMAINDER, help="command to run, after --")
    run_act_parser = commands.add_parser("run-act", help="run act with ephemeral typed values", description="Run act with temporary 0600 secret and variable files that are removed when the child exits."); run_act_parser.add_argument("--env-file", type=Path, default=Path(".env"), help="environment file path"); run_act_parser.add_argument("program", nargs=argparse.REMAINDER, help="act command to run, after --")
    credential = commands.add_parser("git-credential", help="serve Git credential-helper protocol", description="Serve Git's credential-helper protocol for HTTPS requests to github.com only."); credential.add_argument("operation", choices=("get", "store", "erase"), help="Git credential-helper operation")

    bitwarden = commands.add_parser("bitwarden", help="manage Bitwarden connections and explicit project access", description="Manage operator-level Bitwarden connection metadata, encrypted access tokens, and explicit project resolution through a local adapter.").add_subparsers(dest="bitwarden_command", required=True)
    bitwarden_connection = bitwarden.add_parser("connection", help="set or list Bitwarden connections", description="Bind named connections to existing bws profiles and expected organizations.").add_subparsers(dest="connection_command", required=True)
    connection_set = bitwarden_connection.add_parser("set", help="create or replace a connection", description="Bind a named bws profile, its resolved HTTPS endpoints, and one expected organization UUID.")
    connection_set.add_argument("name", type=profile_name, help="connection name")
    connection_set.add_argument("--bws-profile", type=profile_name, required=True, help="existing named profile in the selected bws config")
    connection_set.add_argument("--bws-config", type=Path, default=default_bws_config(), help="bws configuration path; defaults to ~/.config/bws/config")
    connection_set.add_argument("--organization-id", type=organization_uuid, required=True, help="expected canonical organization UUID")
    bitwarden_connection.add_parser("list", help="list connections", description="List configured Bitwarden connections without accessing credentials.")
    bitwarden_credential = bitwarden.add_parser("credential", help="store or remove an encrypted Bitwarden credential", description="Manage independently encrypted Bitwarden access tokens without changing GitHub profiles.").add_subparsers(dest="credential_command", required=True)
    credential_set = bitwarden_credential.add_parser("set", help="store a credential", description="Store a Bitwarden access token for one configured connection through pass/GPG.")
    credential_set.add_argument("connection", type=profile_name, help="configured connection name")
    credential_set.add_argument("--stdin", action="store_true", help="read the access token from standard input")
    credential_remove = bitwarden_credential.add_parser("remove", help="remove a credential", description="Remove a Bitwarden access token without removing its connection metadata.")
    credential_remove.add_argument("connection", type=profile_name, help="configured connection name")
    bitwarden_project = bitwarden.add_parser("project", help="resolve an explicit Bitwarden project", description="Resolve one explicit project through an operator-held local adapter.").add_subparsers(dest="project_command", required=True)
    project_resolve = bitwarden_project.add_parser("resolve", help="resolve an explicit project", description="Resolve one explicit Bitwarden project UUID after validating the checkout, connection, and selected credential source.")
    project_resolve.add_argument("--connection", type=profile_name, required=True, help="configured Bitwarden connection")
    project_resolve.add_argument("--project-id", type=project_uuid, required=True, help="canonical project UUID")
    project_resolve.add_argument("--adapter-path", type=Path, required=True, help="local checkout root containing gh_vault_bws")
    project_resolve.add_argument("--credential-source", choices=("env", "vault"), default="env", help="read BWS_ACCESS_TOKEN or the encrypted connection credential; never falls back")
    bitwarden_env = bitwarden.add_parser("env", help="restore declared environments from Bitwarden", description="Restore declared managed values from one explicit Bitwarden project.").add_subparsers(dest="bitwarden_env_command", required=True)
    bitwarden_restore = bitwarden_env.add_parser("restore", help="restore a declared environment", description="Recreate .env from its template and exact-name values in one explicit Bitwarden project.")
    bitwarden_restore.add_argument("--connection", type=profile_name, required=True, help="configured Bitwarden connection")
    bitwarden_restore.add_argument("--project-id", type=project_uuid, required=True, help="canonical project UUID")
    bitwarden_restore.add_argument("--adapter-path", type=Path, required=True, help="local checkout root containing gh_vault_bws")
    bitwarden_restore.add_argument("--credential-source", choices=("env", "vault"), default="env", help="read BWS_ACCESS_TOKEN or the encrypted connection credential; never falls back")
    bitwarden_restore.add_argument("--env-file", type=Path, default=Path(".env"), help=".env or .env.<profile> to restore")
    bitwarden_restore.add_argument("--example-file", type=Path, help="template path; defaults to the matching .env.example variant")
    bitwarden_restore.add_argument("--force", action="store_true", help="atomically replace an existing environment file")

    env = commands.add_parser("env", help="archive, restore, list, or run with project environment values", description="Archive, restore, or list project .env variants and their .env.example templates, or run a command with declared Actions values.").add_subparsers(dest="env_command", required=True)
    archive = env.add_parser("archive", help="archive one or more typed project environments", description="Archive variable declarations in the public XDG store and secret declarations plus eligible templates in the encrypted vault.")
    archive.add_argument("--env-file", type=Path, action="append", help=".env or .env.<profile>; repeat to archive multiple variants")
    archive.add_argument("--example-file", type=Path, help="template path for one selected environment; defaults to the matching .env.example variant")
    restore = env.add_parser("restore", help="restore one typed project environment", description="Restore a project environment from its public variable payload and encrypted secret payload when present. With --key, write only the named key to the target .env with a synthetic directive line.")
    restore.add_argument("--env-file", type=Path, default=Path(".env"), help=".env or .env.<profile> to restore")
    restore.add_argument("--example-file", type=Path, help="template path; defaults to the matching .env.example variant")
    restore.add_argument("--force", action="store_true", help="overwrite an existing environment file"); restore.add_argument("--restore-example", action="store_true", help="restore the archived template too"); restore.add_argument("--key", help="write only the named key to the target .env with a synthetic directive line; refuses --restore-example")
    env.add_parser("list", help="list archived environment variants", description="List archived .env and .env.<profile> variants and whether each has an archived template.")
    show = env.add_parser("show", help="show archived public variables", description="Print only the selected profile's clear-text variable payload without reading the password store."); show.add_argument("--env-file", type=Path, default=Path(".env"), help=".env or .env.<profile> to inspect")
    env_migrate = env.add_parser("migrate", help="migrate one legacy encrypted environment archive", description="Partition one legacy encrypted archive using reviewed local typed declarations, verify the split payloads, then remove the legacy entry."); env_migrate.add_argument("--env-file", type=Path, default=Path(".env"), help="migrated .env or .env.<profile> declaration file")
    env_run = env.add_parser("run", help="run a command with project environment values", description="Run a command with only values marked by adjacent gh-vault secret or variable directives."); env_run.add_argument("--env-file", type=Path, default=Path(".env"), help="environment file path"); env_run.add_argument("program", nargs=argparse.REMAINDER, help="command to run, after --")
    secret = commands.add_parser("secret", help="sync, export, or check declared Actions secrets", description="Synchronize, export, or verify .env secret declarations against GitHub Secrets.").add_subparsers(dest="secret_command", required=True)
    sync_parser = secret.add_parser("sync", help="sync declared Actions secrets to GitHub", description="Set gh-vault secret declarations as GitHub Secrets.")
    sync_parser.add_argument("--env-file", type=Path, default=Path(".env"), help="environment file path")
    sync_parser.add_argument("--repo", help="target repository; defaults to origin"); sync_parser.add_argument("--github-environment", type=github_environment, help="target GitHub Environment; defaults to repository scope")
    sync_parser.add_argument("--dry-run", action="store_true", help="show the count without changing GitHub")
    type_actions = sync_parser.add_mutually_exclusive_group()
    type_actions.add_argument("--migrate-types", action="store_true", help="remove a same-name remote variable before sync")
    type_actions.add_argument("--prune", action="store_true", help="remove remote secrets whose names are absent from .env; never migrate types")
    act = secret.add_parser("export-act", help="export declared Actions values for act", description="Write gh-vault secret declarations to .secrets and variable declarations to .vars for local act runs."); act.add_argument("--env-file", type=Path, default=Path(".env"), help="environment file path"); act.add_argument("--output", type=Path, default=Path(".secrets"), help="output path for secrets"); act.add_argument("--var-output", type=Path, default=Path(".vars"), help="output path for variables")
    secret_check = secret.add_parser("check", help="verify declared Actions secrets on GitHub", description="Compare typed gh-vault secret declarations with GitHub Secrets at repository scope or in one GitHub Environment without changing .env."); secret_check.add_argument("--env-file", type=Path, default=Path(".env"), help="environment file path"); secret_check.add_argument("--repo", help="target repository; defaults to origin"); secret_check.add_argument("--github-environment", type=github_environment, help="target GitHub Environment; defaults to repository scope")
    variable = commands.add_parser("variable", help="sync, import, or check declared Actions variables", description="Synchronize, import, or verify .env variable declarations against GitHub Variables.").add_subparsers(dest="variable_command", required=True)
    variable_sync_parser = variable.add_parser("sync", help="sync declared Actions variables to GitHub", description="Set gh-vault variable declarations as GitHub Variables.")
    variable_sync_parser.add_argument("--env-file", type=Path, default=Path(".env"), help="environment file path")
    variable_sync_parser.add_argument("--repo", help="target repository; defaults to origin"); variable_sync_parser.add_argument("--github-environment", type=github_environment, help="target GitHub Environment; defaults to repository scope")
    variable_sync_parser.add_argument("--dry-run", action="store_true", help="show the count without changing GitHub")
    variable_type_actions = variable_sync_parser.add_mutually_exclusive_group()
    variable_type_actions.add_argument("--migrate-types", action="store_true", help="remove a same-name remote secret before sync")
    variable_type_actions.add_argument("--prune", action="store_true", help="remove remote variables whose names are absent from .env; never migrate types")
    variable_import = variable.add_parser("import", help="import GitHub Variables into .env", description="Import repository Variables with gh-vault variable directives, or Variables from one GitHub Environment, without replacing local values unless forced."); variable_import.add_argument("--env-file", type=Path, default=Path(".env"), help="environment file path"); variable_import.add_argument("--repo", help="source repository; defaults to origin"); variable_import.add_argument("--github-environment", type=github_environment, help="source GitHub Environment; defaults to repository scope"); variable_import.add_argument("--force", action="store_true", help="overwrite existing gh-vault variable settings")
    variable_check = variable.add_parser("check", help="verify declared Actions variables on GitHub", description="Compare typed gh-vault variable declarations with GitHub Variables at repository scope or in one GitHub Environment without changing .env."); variable_check.add_argument("--env-file", type=Path, default=Path(".env"), help="environment file path"); variable_check.add_argument("--repo", help="target repository; defaults to origin"); variable_check.add_argument("--github-environment", type=github_environment, help="target GitHub Environment; defaults to repository scope")
    actions = commands.add_parser("actions", help="migrate legacy Actions declarations", description="Migrate legacy GH_VAR_ and GH_SECRET_ declarations for review before archive migration.").add_subparsers(dest="actions_command", required=True)
    migrate_env = actions.add_parser("migrate-env", help="rewrite legacy Actions declarations", description="Rewrite legacy prefixed declarations in one environment and its matching template to adjacent typed directives."); migrate_env.add_argument("--env-file", type=Path, default=Path(".env"), help=".env or .env.<profile> to migrate")
    workflow = commands.add_parser("workflow", help="validate GitHub Actions secret wiring", description="Check workflow references against locally declared GitHub Actions values.").add_subparsers(dest="workflow_command", required=True)
    check = workflow.add_parser("check", help="check workflow Actions references", description="Report missing, mismatched, and unreferenced GitHub Actions values used by workflows."); check.add_argument("--env-file", type=Path, default=Path(".env"), help="environment file path"); check.add_argument("--json", action="store_true", help="print results as JSON"); check.add_argument("--fix", action="store_true", help="print suggested workflow environment entries")
    return parser


def _read_token(use_stdin: bool, *, enforce_format: bool = True) -> str:
    if use_stdin:
        token = sys.stdin.read().rstrip("\r\n")
    elif not sys.stdin.isatty():
        raise StoreError("refusing to prompt without a TTY; use --stdin")
    else:
        token = getpass.getpass("GitHub token: ")
    if enforce_format:
        return _validate_token_format(token)
    if not token or "\n" in token or "\r" in token:
        raise StoreError("token must be a non-empty single line")
    return token


def _read_bitwarden_token(use_stdin: bool) -> str:
    if use_stdin:
        token = sys.stdin.read().rstrip("\r\n")
    elif not sys.stdin.isatty():
        raise StoreError("refusing to prompt without a TTY; use --stdin")
    else:
        token = getpass.getpass("Bitwarden access token: ")
    if not token or "\n" in token or "\r" in token:
        raise StoreError("Bitwarden access token must be a non-empty single line")
    return token


def _selected_bitwarden_token(args: argparse.Namespace, store: VaultStore) -> str:
    if args.credential_source == "env":
        access_token = os.environ.get("BWS_ACCESS_TOKEN", "")
        if not access_token:
            raise StoreError("BWS_ACCESS_TOKEN is required for --credential-source env")
    else:
        access_token = store.get_bitwarden_credential(args.connection)
    if "\n" in access_token or "\r" in access_token:
        raise StoreError("Bitwarden access token must be a non-empty single line")
    return access_token


def _bitwarden_dispatch(args: argparse.Namespace, store: VaultStore, directory: Path) -> int:
    if args.bitwarden_command == "connection":
        if args.connection_command == "set":
            config_path = args.bws_config.expanduser().resolve()
            endpoints = load_bws_endpoints(config_path, args.bws_profile)
            store.put_bitwarden_connection(
                BitwardenConnection(
                    args.name,
                    str(config_path),
                    args.bws_profile,
                    endpoints.api_url,
                    endpoints.identity_url,
                    args.organization_id,
                )
            )
            print(f"Stored Bitwarden connection: {args.name}")
            return 0
        connections = store.bitwarden_connections()
        for connection in connections:
            print(
                f"{connection.name} profile={connection.bws_profile} "
                f"organization={connection.organization_id} "
                f"api={connection.api_url} identity={connection.identity_url} "
                f"config={connection.bws_config}"
            )
        if not connections:
            print("No Bitwarden connections configured.")
        return 0

    if args.bitwarden_command == "credential":
        if args.credential_command == "set":
            store.put_bitwarden_credential(
                args.connection, _read_bitwarden_token(args.stdin)
            )
            print(f"Stored Bitwarden credential: {args.connection}")
        else:
            store.remove_bitwarden_credential(args.connection)
            print(f"Removed Bitwarden credential: {args.connection}")
        return 0

    if args.bitwarden_command == "env":
        example_file = args.example_file or example_file_for(args.env_file)
        plan = prepare_bitwarden_restore(
            args.env_file,
            example_file,
            force=args.force,
        )
        connection = store.get_bitwarden_connection(args.connection)
        project_namespace(directory)
        assert_connection_current(connection)
        reject_bws_overrides()
        access_token = _selected_bitwarden_token(args, store)
        adapter = load_local_adapter(args.adapter_path)
        values = read_environment(
            adapter,
            connection,
            access_token,
            args.project_id,
            plan.keys,
        )
        apply_bitwarden_restore(plan, values)
        print(
            f"Restored {len(values)} managed value(s) to {args.env_file} "
            f"from Bitwarden project {args.project_id}."
        )
        return 0

    connection = store.get_bitwarden_connection(args.connection)
    project_namespace(directory)
    assert_connection_current(connection)
    reject_bws_overrides()
    access_token = _selected_bitwarden_token(args, store)
    adapter = load_local_adapter(args.adapter_path)
    project = resolve_project(adapter, connection, access_token, args.project_id)
    print(
        f"Resolved Bitwarden project {project.project_id} "
        f"for connection {connection.name}."
    )
    return 0


def _set(store: VaultStore, args: argparse.Namespace) -> int:
    token = _read_token(args.stdin)
    validated = True
    try:
        metadata = inspect_token(token)
    except StoreError:
        if args.scopes is None:
            raise
        validated = False
        metadata = TokenMetadata((), None)
    scopes = metadata.scopes if args.scopes is None else args.scopes
    store.put(Profile(args.name, scopes, args.note, metadata.expires_at), token, replace=args.force)
    if validated:
        print(f"Validated GitHub token: scopes={','.join(metadata.scopes) or '-'}{f' expires={metadata.expires_at}' if metadata.expires_at else ''}")
    print(f"Stored profile: {args.name}")
    return 0


def _list(store: VaultStore) -> int:
    active = store.active()
    for profile in store.profiles():
        print(f"{'*' if profile.name == active else ' '} {profile.name:<20} scopes={','.join(profile.scopes) or '-'}{f' expires={profile.expires_at}' if profile.expires_at else ''}{f'  {profile.note}' if profile.note else ''}")
    if not store.profiles(): print("No token profiles configured.")
    return 0


def _status(store: VaultStore) -> int:
    store.require_backend(); active = store.active()
    if not active:
        print("Active profile: none"); return 1
    store.get(active); print(f"Active profile: {active}"); return 0


def _find(store: VaultStore, use_stdin: bool) -> int:
    if not use_stdin:
        raise StoreError("find requires --stdin")
    token = _read_token(True, enforce_format=False)
    matches = [profile.name for profile in store.profiles() if store.get(profile.name) == token]
    for name in matches:
        print(name)
    return 0 if matches else 1


def _run(store: VaultStore, name: str | None, program: list[str]) -> int:
    if program and program[0] == "--": program = program[1:]
    if not program: raise StoreError("run requires a command after --")
    environment = os.environ.copy(); token = store.get(name); environment["GH_TOKEN"] = token; environment["GITHUB_TOKEN"] = token
    try: os.execvpe(program[0], program, environment)
    except FileNotFoundError as exc: raise StoreError(f"command not found: {program[0]}") from exc
    return 127


def _env_run(store: VaultStore, env_file: Path, program: list[str]) -> int:
    if not program or program[0] != "--": raise StoreError("env run requires a command after --")
    program = program[1:]
    if not program: raise StoreError("env run requires a command after --")
    environment = os.environ.copy()
    environment.update(runtime_environment(env_file, store))
    try: os.execvpe(program[0], program, environment)
    except FileNotFoundError as exc: raise StoreError(f"command not found: {program[0]}") from exc
    return 127


def _credential_host(fields: dict[str, str]) -> str:
    return fields.get("host", "").split(":", 1)[0].lower() or (urlparse(fields.get("url", "")).hostname or "").lower()


def _git_credential(store: VaultStore, operation: str) -> int:
    fields = dict(line.rstrip("\n").split("=", 1) for line in sys.stdin if "=" in line)
    if operation == "get" and fields.get("protocol", "").lower() == "https" and _credential_host(fields) == "github.com":
        print("username=x-access-token"); print(f"password={store.get()}"); print()
    return 0


def _render_secret_check(env_file: Path, repo: str, environment: str | None = None) -> int:
    status = remote_secret_status(env_file, repo, environment=environment) if environment is not None else remote_secret_status(env_file, repo)
    for name in status.secret_to_variable:
        print(f"{name}: GitHub variable -> gh-vault secret")
    for name in status.remote_only_secrets:
        print(f"GitHub secret {name} is not declared in .env")
    if status.missing_secrets:
        print(f"Missing GitHub secrets: {', '.join(status.missing_secrets)}")
    if any((status.missing_secrets, status.remote_only_secrets, status.secret_to_variable)):
        return 1
    print("All local secret values are configured on GitHub.")
    return 0


def _render_variable_check(env_file: Path, repo: str, environment: str | None = None) -> int:
    status = remote_secret_status(env_file, repo, environment=environment) if environment is not None else remote_secret_status(env_file, repo)
    for name in status.variable_to_secret:
        print(f"{name}: GitHub secret -> gh-vault variable")
    for name in status.remote_only_variables:
        print(f"GitHub variable {name} is not declared in .env")
    if status.missing_variables:
        print(f"Missing GitHub variables: {', '.join(status.missing_variables)}")
    if any((status.missing_variables, status.remote_only_variables, status.variable_to_secret)):
        return 1
    print("All local variable values are configured on GitHub.")
    return 0


def _run_sync(store: VaultStore, args: argparse.Namespace, kind: Literal["secret", "variable"], directory: Path) -> int:
    entries = [entry for entry in action_values(args.env_file, store) if entry.kind == kind]
    repo = args.repo or default_repo(directory)
    result = sync(entries, repo, kind, args.dry_run, args.migrate_types, args.prune, environment=args.github_environment) if args.github_environment is not None else sync(entries, repo, kind, args.dry_run, args.migrate_types, args.prune)
    verb = "Would sync" if args.dry_run else "Synced"
    prune_phrase = f"; {'would prune' if args.dry_run else 'pruned'} {result.pruned} {kind}(s)" if args.prune else ""
    target = f" to GitHub environment {args.github_environment!r}" if args.github_environment is not None else ""
    print(f"{verb} {result.synced} {kind}(s){target}{prune_phrase}.")
    return 0


def dispatch(args: argparse.Namespace, store: VaultStore, directory: Path = Path.cwd()) -> int:
    if args.command == "set": return _set(store, args)
    if args.command == "list": return _list(store)
    if args.command == "activate": store.activate(args.name); print(f"Active profile: {args.name}"); return 0
    if args.command == "status": return _status(store)
    if args.command == "find": return _find(store, args.stdin)
    if args.command == "output": print(store.get(args.name)); return 0
    if args.command == "remove": store.remove(args.name); print(f"Removed profile: {args.name}"); return 0
    if args.command == "run": return _run(store, args.name, args.program)
    if args.command == "run-act": return run_act(args.env_file, args.program, directory)
    if args.command == "git-credential": return _git_credential(store, args.operation)
    if args.command == "bitwarden": return _bitwarden_dispatch(args, store, directory)

    if args.command == "actions":
        env_count, example_count = migrate_env_source(args.env_file)
        print(f"Migrated {env_count} declaration(s) in {args.env_file} and {example_count} in {example_file_for(args.env_file)}.")
        return 0

    if args.command == "env":
        environment_store = EnvironmentStore(getattr(store, "config_dir", None))
        if args.env_command == "archive":
            env_files = args.env_file or [Path(".env")]
            if args.example_file and len(env_files) != 1:
                raise StoreError("--example-file can only be used with one --env-file")
            for env_file in env_files:
                example_file = args.example_file or example_file_for(env_file)
                print(f"Archived {env_file} for {archive_environment(store, environment_store, directory, env_file, example_file)}.")
        elif args.env_command == "restore":
            example_file = args.example_file or example_file_for(args.env_file)
            print(f"Restored {args.env_file} for {restore_environment(store, environment_store, directory, args.env_file, example_file, args.force, args.restore_example, args.key)}.")
        elif args.env_command == "list":
            namespace, environments = list_environments(environment_store, directory)
            if not environments:
                print(f"No archived environments for {namespace}.")
            for profile, has_example in environments:
                env_file = ".env" if profile == "default" else f".env.{profile}"
                print(f"{env_file} example={'yes' if has_example else 'no'}")
        elif args.env_command == "show":
            _, values = show_environment(environment_store, directory, args.env_file)
            if not values:
                print("No archived variables")
            else:
                for name, value in sorted(values.items()):
                    print(f"{name}={format_dotenv_value(value)}")
        elif args.env_command == "migrate":
            result = migrate_environment_archive(store, environment_store, directory, args.env_file, example_file_for(args.env_file))
            print(f"Migrated {args.env_file.name} ({result.profile}) for {result.namespace}: {result.variables} variable value(s) moved to clear text, {result.secrets} secret value(s) retained encrypted, {result.local} local-only value(s) removed from gh-vault.")
        else: return _env_run(store, args.env_file, args.program)
        return 0
    if args.command == "secret":
        if args.secret_command == "check":
            return _render_secret_check(args.env_file, args.repo or default_repo(directory), args.github_environment)
        if args.secret_command == "sync":
            return _run_sync(store, args, "secret", directory)
        entries = action_values(args.env_file, store)
        secret_count, var_count = export_act(entries, args.output, args.var_output); print(f"Wrote {secret_count} secret(s) and {var_count} variable(s).")
        return 0
    if args.command == "variable":
        if args.variable_command == "check":
            return _render_variable_check(args.env_file, args.repo or default_repo(directory), args.github_environment)
        if args.variable_command == "sync":
            return _run_sync(store, args, "variable", directory)
        target, count = import_variables(directory, args.repo or default_repo(directory), args.force, args.env_file, args.github_environment)
        print(f"Imported {count} variable(s) into {target}.")
        return 0
    entries = action_values(args.env_file, store)
    result = check_workflows(directory, entries)
    if args.json: print(json_result(result))
    else:
        for findings in result.values():
            for finding in findings:
                print(f"{finding['file']}:{finding['line']}: {finding['severity']}: {finding['message']}")
        if args.fix and result["unreferenced"]:
            unreferenced = {str(finding["name"]) for finding in result["unreferenced"]}
            print("Suggested env block:\n" + suggested_env([entry for entry in entries if entry.name in unreferenced]))
    return 1 if any(result[key] for key in ("unreferenced", "type_mismatch", "order")) else 0


def main() -> int:
    parser = build_parser(); args = parser.parse_args()
    try: return dispatch(args, VaultStore())
    except StoreError as exc: parser.error(str(exc))


if __name__ == "__main__": raise SystemExit(main())
