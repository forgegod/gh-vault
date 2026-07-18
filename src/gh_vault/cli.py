from __future__ import annotations

import argparse
import getpass
import os
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

from .actions import action_values, check_workflows, default_repo, export_act, import_variables, json_result, remote_secret_status, run_act, runtime_environment, suggested_env, sync
from .envfiles import archive_environment, example_file_for, format_dotenv_value, list_environments, restore_environment, show_environment
from .github import TokenMetadata, inspect_token
from .store import EnvironmentStore, Profile, StoreError, VaultStore

NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def profile_name(value: str) -> str:
    if not NAME_PATTERN.fullmatch(value):
        raise argparse.ArgumentTypeError("must be 1-64 characters: letters, digits, dot, underscore, or hyphen")
    return value


def parse_scopes(value: str) -> tuple[str, ...]:
    return tuple(dict.fromkeys(part.strip() for part in value.split(",") if part.strip()))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="gh-vault", description="Store GitHub credentials and project environment archives safely.")
    commands = parser.add_subparsers(dest="command", required=True)
    set_profile = commands.add_parser("set", help="create or replace a profile", description="Validate a GitHub token and create or replace its named profile in the encrypted vault.")
    set_profile.add_argument("name", type=profile_name, help="profile name"); set_profile.add_argument("--scopes", type=parse_scopes, help="comma-separated scopes; disables automatic classic-PAT detection"); set_profile.add_argument("--note", default="", help="operator note"); set_profile.add_argument("--stdin", action="store_true", help="read the token from standard input"); set_profile.set_defaults(force=True)
    commands.add_parser("list", help="list token profiles", description="Display stored token profiles, their scopes, expiration, and active selection.")
    activate = commands.add_parser("activate", help="select the default profile", description="Select the token profile used when a command does not name one."); activate.add_argument("name", type=profile_name, help="profile name")
    commands.add_parser("status", help="show the active profile", description="Show the profile selected as the default GitHub token.")
    remove = commands.add_parser("remove", help="delete a profile", description="Delete a token profile and its encrypted token from the vault."); remove.add_argument("name", type=profile_name, help="profile name")
    run = commands.add_parser("run", help="run a command with a token", description="Run a child command with the selected token in its environment only."); run.add_argument("--name", type=profile_name, help="profile name; defaults to the active profile"); run.add_argument("program", nargs=argparse.REMAINDER, help="command to run, after --")
    run_act_parser = commands.add_parser("run-act", help="run act with ephemeral typed values", description="Run act with temporary 0600 secret and variable files that are removed when the child exits."); run_act_parser.add_argument("--env-file", type=Path, default=Path(".env"), help="environment file path"); run_act_parser.add_argument("program", nargs=argparse.REMAINDER, help="act command to run, after --")
    credential = commands.add_parser("git-credential", help="serve Git credential-helper protocol", description="Serve Git's credential-helper protocol for HTTPS requests to github.com only."); credential.add_argument("operation", choices=("get", "store", "erase"), help="Git credential-helper operation")

    env = commands.add_parser("env", help="archive, restore, list, or run with project environment values", description="Archive, restore, or list project .env variants and their .env.example templates, or run a command with declared Actions values.").add_subparsers(dest="env_command", required=True)
    archive = env.add_parser("archive", help="archive one or more typed project environments", description="Archive variable declarations in the public XDG store and secret declarations plus eligible templates in the encrypted vault.")
    archive.add_argument("--env-file", type=Path, action="append", help=".env or .env.<profile>; repeat to archive multiple variants")
    archive.add_argument("--example-file", type=Path, help="template path for one selected environment; defaults to the matching .env.example variant")
    restore = env.add_parser("restore", help="restore one typed project environment", description="Restore a project environment from its public variable payload and encrypted secret payload when present.")
    restore.add_argument("--env-file", type=Path, default=Path(".env"), help=".env or .env.<profile> to restore")
    restore.add_argument("--example-file", type=Path, help="template path; defaults to the matching .env.example variant")
    restore.add_argument("--force", action="store_true", help="overwrite an existing environment file"); restore.add_argument("--restore-example", action="store_true", help="restore the archived template")
    env.add_parser("list", help="list archived environment variants", description="List archived .env and .env.<profile> variants and whether each has an archived template.")
    show = env.add_parser("show", help="show archived public variables", description="Print only the selected profile's clear-text variable payload without reading the password store."); show.add_argument("--env-file", type=Path, default=Path(".env"), help=".env or .env.<profile> to inspect")
    env_run = env.add_parser("run", help="run a command with project environment values", description="Run a command with only values marked by adjacent gh-vault secret or variable directives."); env_run.add_argument("--env-file", type=Path, default=Path(".env"), help="environment file path"); env_run.add_argument("program", nargs=argparse.REMAINDER, help="command to run, after --")
    secrets = commands.add_parser("secrets", help="sync or export declared Actions values", description="Synchronize, export, or verify .env values marked for GitHub Actions.").add_subparsers(dest="secrets_command", required=True)
    sync_parser = secrets.add_parser("sync", help="sync declared Actions values to GitHub", description="Set gh-vault secret declarations as GitHub Secrets and variable declarations as GitHub Variables."); sync_parser.add_argument("--env-file", type=Path, default=Path(".env"), help="environment file path"); sync_parser.add_argument("--repo", help="target repository; defaults to origin"); sync_parser.add_argument("--dry-run", action="store_true", help="show the count without changing GitHub"); type_actions = sync_parser.add_mutually_exclusive_group(); type_actions.add_argument("--migrate-types", action="store_true", help="remove a same-name remote value of the opposite type before sync"); type_actions.add_argument("--prune", action="store_true", help="remove remote values whose names are absent from .env; never migrate types")
    act = secrets.add_parser("export-act", help="export declared Actions values for act", description="Write gh-vault secret declarations to .secrets and variable declarations to .vars for local act runs."); act.add_argument("--env-file", type=Path, default=Path(".env"), help="environment file path"); act.add_argument("--output", type=Path, default=Path(".secrets"), help="output path for secrets"); act.add_argument("--var-output", type=Path, default=Path(".vars"), help="output path for variables")
    secret_check = secrets.add_parser("check", help="verify declared Actions types on GitHub", description="Compare typed gh-vault declarations with both GitHub Actions stores without changing .env."); secret_check.add_argument("--env-file", type=Path, default=Path(".env"), help="environment file path"); secret_check.add_argument("--repo", help="target repository; defaults to origin")
    variables = commands.add_parser("variables", help="manage repository variables", description="Import GitHub Actions Variables as typed dotenv declarations.").add_subparsers(dest="variables_command", required=True)
    variable_import = variables.add_parser("import", help="import GitHub Variables into .env", description="Import repository Variables with gh-vault variable directives without replacing local values unless forced."); variable_import.add_argument("--repo", help="source repository; defaults to origin"); variable_import.add_argument("--force", action="store_true", help="overwrite existing gh-vault variable settings")
    workflow = commands.add_parser("workflow", help="validate GitHub Actions secret wiring", description="Check workflow references against locally declared GitHub Actions values.").add_subparsers(dest="workflow_command", required=True)
    check = workflow.add_parser("check", help="check workflow Actions references", description="Report missing, mismatched, and unreferenced GitHub Actions values used by workflows."); check.add_argument("--env-file", type=Path, default=Path(".env"), help="environment file path"); check.add_argument("--json", action="store_true", help="print results as JSON"); check.add_argument("--fix", action="store_true", help="print suggested workflow environment entries")
    return parser


def _read_token(use_stdin: bool) -> str:
    if use_stdin:
        return sys.stdin.read().rstrip("\r\n")
    if not sys.stdin.isatty():
        raise StoreError("refusing to prompt without a TTY; use --stdin")
    return getpass.getpass("GitHub token: ")


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


def _run(store: VaultStore, name: str | None, program: list[str]) -> int:
    if program and program[0] == "--": program = program[1:]
    if not program: raise StoreError("run requires a command after --")
    environment = os.environ.copy(); token = store.get(name); environment["GH_TOKEN"] = token; environment["GITHUB_TOKEN"] = token
    try: os.execvpe(program[0], program, environment)
    except FileNotFoundError as exc: raise StoreError(f"command not found: {program[0]}") from exc
    return 127


def _env_run(env_file: Path, program: list[str]) -> int:
    if not program or program[0] != "--": raise StoreError("env run requires a command after --")
    program = program[1:]
    if not program: raise StoreError("env run requires a command after --")
    environment = os.environ.copy()
    environment.update(runtime_environment(env_file))
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


def dispatch(args: argparse.Namespace, store: VaultStore, directory: Path = Path.cwd()) -> int:
    if args.command == "set": return _set(store, args)
    if args.command == "list": return _list(store)
    if args.command == "activate": store.activate(args.name); print(f"Active profile: {args.name}"); return 0
    if args.command == "status": return _status(store)
    if args.command == "remove": store.remove(args.name); print(f"Removed profile: {args.name}"); return 0
    if args.command == "run": return _run(store, args.name, args.program)
    if args.command == "run-act": return run_act(args.env_file, args.program, directory)
    if args.command == "git-credential": return _git_credential(store, args.operation)

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
            print(f"Restored {args.env_file} for {restore_environment(store, environment_store, directory, args.env_file, example_file, args.force, args.restore_example)}.")
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
        else: return _env_run(args.env_file, args.program)
        return 0
    if args.command == "secrets":
        if args.secrets_command == "check":
            status = remote_secret_status(args.env_file, args.repo or default_repo(directory))
            for name in status.secret_to_variable:
                print(f"{name}: GitHub variable -> gh-vault secret")
            for name in status.variable_to_secret:
                print(f"{name}: GitHub secret -> gh-vault variable")
            for name in status.remote_only_secrets:
                print(f"GitHub secret {name} is not declared in .env")
            for name in status.remote_only_variables:
                print(f"GitHub variable {name} is not declared in .env")
            if status.missing_secrets:
                print(f"Missing GitHub secrets: {', '.join(status.missing_secrets)}")
            if status.missing_variables:
                print(f"Missing GitHub variables: {', '.join(status.missing_variables)}")
            if any((status.missing_secrets, status.missing_variables, status.remote_only_secrets, status.remote_only_variables, status.secret_to_variable, status.variable_to_secret)):
                return 1
            print("All local Actions values are configured on GitHub.")
            return 0
        entries = action_values(args.env_file)
        if args.secrets_command == "sync":
            result = sync(entries, args.repo or default_repo(directory), args.dry_run, args.migrate_types, args.prune)
            prune_summary = f"; {'would prune' if args.dry_run else 'pruned'} {result.pruned} remote value(s)" if args.prune else ""
            print(f"{'Would sync' if args.dry_run else 'Synced'} {result.synced} entry(s){prune_summary}.")
        else: secret_count, var_count = export_act(entries, args.output, args.var_output); print(f"Wrote {secret_count} secret(s) and {var_count} variable(s).")
        return 0
    if args.command == "variables":
        target, count = import_variables(directory, args.repo or default_repo(directory), args.force)
        print(f"Imported {count} variable(s) into {target}.")
        return 0
    entries = action_values(args.env_file)
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
