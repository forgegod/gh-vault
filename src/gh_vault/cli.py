from __future__ import annotations

import argparse
import getpass
import os
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

from .actions import action_values, check_workflows, default_repo, export_act, json_result, suggested_env, sync
from .envfiles import archive_environment, restore_environment
from .store import Profile, StoreError, VaultStore

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
    add = commands.add_parser("add", help="store a named token")
    add.add_argument("name", type=profile_name); add.add_argument("--scopes", type=parse_scopes, default=()); add.add_argument("--note", default=""); add.add_argument("--stdin", action="store_true"); add.add_argument("--force", action="store_true")
    commands.add_parser("list", help="list token profiles")
    activate = commands.add_parser("activate", help="select the default profile"); activate.add_argument("name", type=profile_name)
    commands.add_parser("status", help="show the active profile")
    remove = commands.add_parser("remove", help="delete a profile"); remove.add_argument("name", type=profile_name)
    run = commands.add_parser("run", help="run a command with a token"); run.add_argument("--name", type=profile_name); run.add_argument("program", nargs=argparse.REMAINDER)
    credential = commands.add_parser("git-credential", help="serve Git credential-helper protocol"); credential.add_argument("operation", choices=("get", "store", "erase"))
    commands.add_parser("migrate", help="copy legacy github-token-safe profiles")
    env = commands.add_parser("env", help="archive or restore project environment files").add_subparsers(dest="env_command", required=True)
    for name in ("archive", "restore"):
        command = env.add_parser(name); command.add_argument("--env-file", type=Path, default=Path(".env")); command.add_argument("--example-file", type=Path, default=Path(".env.example"))
    env.choices["restore"].add_argument("--force", action="store_true"); env.choices["restore"].add_argument("--restore-example", action="store_true")
    secrets = commands.add_parser("secrets", help="sync or export GH_SECRET_/GH_VAR_ entries").add_subparsers(dest="secrets_command", required=True)
    sync_parser = secrets.add_parser("sync"); sync_parser.add_argument("--env-file", type=Path, default=Path(".env")); sync_parser.add_argument("--repo"); sync_parser.add_argument("--dry-run", action="store_true"); sync_parser.add_argument("--migrate-types", action="store_true", help="remove a same-name remote value of the opposite type before sync")
    act = secrets.add_parser("export-act"); act.add_argument("--env-file", type=Path, default=Path(".env")); act.add_argument("--output", type=Path, default=Path(".secrets")); act.add_argument("--var-output", type=Path, default=Path(".vars"))
    workflow = commands.add_parser("workflow", help="validate GitHub Actions secret wiring").add_subparsers(dest="workflow_command", required=True)
    check = workflow.add_parser("check"); check.add_argument("--env-file", type=Path, default=Path(".env")); check.add_argument("--json", action="store_true"); check.add_argument("--fix", action="store_true")
    return parser


def _read_token(use_stdin: bool) -> str:
    if use_stdin:
        return sys.stdin.read().rstrip("\r\n")
    if not sys.stdin.isatty():
        raise StoreError("refusing to prompt without a TTY; use --stdin")
    return getpass.getpass("GitHub token: ")


def _list(store: VaultStore) -> int:
    active = store.active()
    for profile in store.profiles():
        print(f"{'*' if profile.name == active else ' '} {profile.name:<20} scopes={','.join(profile.scopes) or '-'}{f'  {profile.note}' if profile.note else ''}")
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


def _credential_host(fields: dict[str, str]) -> str:
    return fields.get("host", "").split(":", 1)[0].lower() or (urlparse(fields.get("url", "")).hostname or "").lower()


def _git_credential(store: VaultStore, operation: str) -> int:
    fields = dict(line.rstrip("\n").split("=", 1) for line in sys.stdin if "=" in line)
    if operation == "get" and fields.get("protocol", "").lower() == "https" and _credential_host(fields) == "github.com":
        print("username=x-access-token"); print(f"password={store.get()}"); print()
    return 0


def dispatch(args: argparse.Namespace, store: VaultStore, directory: Path = Path.cwd()) -> int:
    if args.command == "add": store.put(Profile(args.name, args.scopes, args.note), _read_token(args.stdin), replace=args.force); print(f"Stored profile: {args.name}"); return 0
    if args.command == "list": return _list(store)
    if args.command == "activate": store.activate(args.name); print(f"Active profile: {args.name}"); return 0
    if args.command == "status": return _status(store)
    if args.command == "remove": store.remove(args.name); print(f"Removed profile: {args.name}"); return 0
    if args.command == "run": return _run(store, args.name, args.program)
    if args.command == "git-credential": return _git_credential(store, args.operation)
    if args.command == "migrate": print(f"Migrated {store.migrate_legacy()} legacy profile(s)."); return 0
    if args.command == "env":
        if args.env_command == "archive": print(f"Archived environment for {archive_environment(store, directory, args.env_file, args.example_file)}.")
        else: print(f"Restored environment for {restore_environment(store, directory, args.env_file, args.example_file, args.force, args.restore_example)}.")
        return 0
    entries = action_values(args.env_file)
    if args.command == "secrets":
        if args.secrets_command == "sync": print(f"{'Would sync' if args.dry_run else 'Synced'} {sync(entries, args.repo or default_repo(directory), args.dry_run, args.migrate_types)} entry(s).")
        else: secret_count, var_count = export_act(entries, args.output, args.var_output); print(f"Wrote {secret_count} secret(s) and {var_count} variable(s).")
        return 0
    result = check_workflows(directory, entries)
    if args.json: print(json_result(result))
    else:
        for category, names in result.items():
            if names: print(f"{category}: {', '.join(names)}")
        if args.fix and result["unreferenced"]: print("Suggested env block:\n" + suggested_env([entry for entry in entries if entry.name in result["unreferenced"]]))
    return 1 if any(result[key] for key in ("unreferenced", "type_mismatch", "order")) else 0


def main() -> int:
    parser = build_parser(); args = parser.parse_args()
    try: return dispatch(args, VaultStore())
    except StoreError as exc: parser.error(str(exc))


if __name__ == "__main__": raise SystemExit(main())
