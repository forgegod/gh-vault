from __future__ import annotations

import argparse
import getpass
import os
import re
import sys
from urllib.parse import urlparse

from .store import Profile, StoreError, TokenStore

NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def profile_name(value: str) -> str:
    if not NAME_PATTERN.fullmatch(value):
        raise argparse.ArgumentTypeError(
            "must be 1-64 characters: letters, digits, dot, underscore, or hyphen"
        )
    return value


def parse_scopes(value: str) -> tuple[str, ...]:
    return tuple(dict.fromkeys(part.strip() for part in value.split(",") if part.strip()))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gts",
        description="Store named GitHub tokens and switch between them safely.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    add = subparsers.add_parser("add", help="store a new named token")
    add.add_argument("name", type=profile_name)
    add.add_argument("--scopes", type=parse_scopes, default=(), help="declared scopes, comma separated")
    add.add_argument("--note", default="", help="short description of the token's purpose")
    add.add_argument("--stdin", action="store_true", help="read the token from standard input")
    add.add_argument("--force", action="store_true", help="replace an existing profile")

    subparsers.add_parser("list", help="list profiles without revealing tokens")

    activate = subparsers.add_parser("activate", help="select the default profile")
    activate.add_argument("name", type=profile_name)

    subparsers.add_parser("status", help="show the active profile and backend state")

    remove = subparsers.add_parser("remove", help="delete a profile and its token")
    remove.add_argument("name", type=profile_name)

    run = subparsers.add_parser("run", help="run a command with a named token")
    run.add_argument("--name", type=profile_name, help="profile to use instead of the active profile")
    run.add_argument("program", nargs=argparse.REMAINDER, help="command following --")

    credential = subparsers.add_parser(
        "git-credential", help="serve the Git credential-helper protocol"
    )
    credential.add_argument("operation", choices=("get", "store", "erase"))
    return parser


def _read_token(use_stdin: bool) -> str:
    if use_stdin:
        return sys.stdin.read().rstrip("\r\n")
    if not sys.stdin.isatty():
        raise StoreError("refusing to prompt without a TTY; use --stdin")
    return getpass.getpass("GitHub token: ")


def _list(store: TokenStore) -> int:
    active = store.active()
    profiles = store.profiles()
    if not profiles:
        print("No token profiles configured.")
        return 0
    for profile in profiles:
        marker = "*" if profile.name == active else " "
        scopes = ",".join(profile.scopes) if profile.scopes else "-"
        suffix = f"  {profile.note}" if profile.note else ""
        print(f"{marker} {profile.name:<20} scopes={scopes}{suffix}")
    return 0


def _status(store: TokenStore) -> int:
    store.require_backend()
    active = store.active()
    if not active:
        print("Active profile: none")
        print(f"Secret backend: {store.backend}")
        return 1
    store.get(active)
    print(f"Active profile: {active}")
    print(f"Secret backend: {store.backend} (token available)")
    return 0


def _run(store: TokenStore, name: str | None, program: list[str]) -> int:
    if program and program[0] == "--":
        program = program[1:]
    if not program:
        raise StoreError("run requires a command after --")
    token = store.get(name)
    environment = os.environ.copy()
    environment["GH_TOKEN"] = token
    environment["GITHUB_TOKEN"] = token
    try:
        os.execvpe(program[0], program, environment)
    except FileNotFoundError as exc:
        raise StoreError(f"command not found: {program[0]}") from exc
    return 127


def _credential_host(fields: dict[str, str]) -> str:
    if "host" in fields:
        return fields["host"].split(":", 1)[0].lower()
    if "url" in fields:
        return (urlparse(fields["url"]).hostname or "").lower()
    return ""


def _git_credential(store: TokenStore, operation: str) -> int:
    fields: dict[str, str] = {}
    for line in sys.stdin:
        line = line.rstrip("\n")
        if not line:
            break
        key, separator, value = line.partition("=")
        if separator:
            fields[key] = value
    protocol = fields.get("protocol", "").lower()
    if (
        operation != "get"
        or protocol != "https"
        or _credential_host(fields) != "github.com"
    ):
        return 0
    token = store.get()
    print("username=x-access-token")
    print(f"password={token}")
    print()
    return 0


def dispatch(args: argparse.Namespace, store: TokenStore) -> int:
    if args.command == "add":
        token = _read_token(args.stdin)
        store.put(Profile(args.name, args.scopes, args.note), token, replace=args.force)
        print(f"Stored profile: {args.name}")
        if store.active() == args.name:
            print(f"Active profile: {args.name}")
        return 0
    if args.command == "list":
        return _list(store)
    if args.command == "activate":
        store.activate(args.name)
        print(f"Active profile: {args.name}")
        return 0
    if args.command == "status":
        return _status(store)
    if args.command == "remove":
        store.remove(args.name)
        print(f"Removed profile: {args.name}")
        return 0
    if args.command == "run":
        return _run(store, args.name, args.program)
    if args.command == "git-credential":
        return _git_credential(store, args.operation)
    raise AssertionError(f"unhandled command: {args.command}")


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return dispatch(args, TokenStore())
    except StoreError as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
