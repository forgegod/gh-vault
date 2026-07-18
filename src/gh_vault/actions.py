from __future__ import annotations

import base64
import json
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from .envfiles import DotenvAssignment, _write_private, format_dotenv_value, parse_typed_dotenv, project_namespace
from .store import StoreError

RESERVED = re.compile(r"^(?:GITHUB_.*|RUNNER_.*|CI|GH_TOKEN)$")
REF = re.compile(r"\b(?P<kind>secrets|vars)\.(?P<name>[A-Z][A-Z0-9_]*)")
DOTENV_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")



@dataclass(frozen=True)
class ActionValue:
    name: str
    kind: Literal["secret", "variable"]
    value: str
    source: Path | None = field(default=None, compare=False)
    line: int | None = field(default=None, compare=False)


@dataclass(frozen=True)
class RemoteValueStatus:
    missing_secrets: list[str]
    missing_variables: list[str]
    remote_only_secrets: list[str]
    remote_only_variables: list[str]
    secret_to_variable: list[str]
    variable_to_secret: list[str]


@dataclass(frozen=True)
class SyncResult:
    synced: int
    pruned: int


def action_values(env_file: Path) -> list[ActionValue]:
    return [
        ActionValue(entry.key, entry.kind, entry.value, env_file, entry.line)
        for entry in parse_typed_dotenv(env_file)
        if entry.kind != "local" and entry.value and not RESERVED.fullmatch(entry.key)
    ]


def runtime_environment(env_file: Path) -> dict[str, str]:
    return {
        entry.key: entry.value
        for entry in parse_typed_dotenv(env_file)
        if entry.kind != "local" and not RESERVED.fullmatch(entry.key)
    }


def _remote_names(kind: str, repo: str) -> set[str]:
    result = subprocess.run(
        ["gh", kind, "list", "--repo", repo, "--json", "name", "--jq", ".[].name"],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode:
        raise StoreError(f"cannot list GitHub {kind}s: {result.stderr.strip() or 'gh failed'}")
    return {name for name in result.stdout.splitlines() if name}


def import_variables(directory: Path, repo: str, force: bool) -> tuple[Path, int]:
    target = directory / ".env"
    if not target.exists():
        target = directory / ".env.example"
    template = target.name.startswith(".env.example")
    assignments = {entry.key: entry for entry in parse_typed_dotenv(target, include_commented=template)}
    try:
        source = target.read_text(encoding="utf-8")
    except OSError as exc:
        raise StoreError(f"cannot read {target}: {exc}") from exc
    result = subprocess.run(
        ["gh", "variable", "list", "--repo", repo, "--json", "name,value"],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode:
        raise StoreError(f"cannot list GitHub variables: {result.stderr.strip() or 'gh failed'}")
    try:
        remote = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise StoreError("GitHub variable list returned invalid JSON") from exc
    if not isinstance(remote, list) or any(
        not isinstance(item, dict) or not isinstance(item.get("name"), str) or not DOTENV_KEY.fullmatch(item["name"]) or not isinstance(item.get("value"), str)
        for item in remote
    ):
        raise StoreError("GitHub variable list returned invalid data")
    updates: dict[str, str] = {}
    for item in remote:
        if RESERVED.fullmatch(item["name"]):
            continue
        existing = assignments.get(item["name"])
        if existing is not None and not force:
            continue
        if existing is not None and existing.kind != "variable":
            raise StoreError(f"cannot import GitHub variable {item['name']}: local declaration is {existing.kind}")
        updates[item["name"]] = item["value"]
    _write_private(target, _render_imported_variables(source, assignments, updates, template))
    return target, len(updates)


def _render_imported_variables(source: str, assignments: dict[str, DotenvAssignment], updates: dict[str, str], template: bool) -> str:
    lines = source.splitlines()
    existing_names: set[str] = set()
    for name, assignment in assignments.items():
        if name in updates:
            prefix = "# " if assignment.commented else ""
            lines[assignment.line - 1] = f"{prefix}{name}={format_dotenv_value(updates[name])}"
            existing_names.add(name)
    additions = [name for name in updates if name not in existing_names]
    if additions:
        if lines and lines[-1]:
            lines.append("")
        for name in additions:
            lines.extend(("# gh-vault: variable", f"{'# ' if template else ''}{name}={format_dotenv_value(updates[name])}"))
    return "\n".join(lines) + "\n"


def remote_secret_status(env_file: Path, repo: str) -> RemoteValueStatus:
    assignments = parse_typed_dotenv(env_file)
    local = {entry.key for entry in assignments if entry.kind == "secret" and not RESERVED.fullmatch(entry.key)}
    local_variables = {entry.key for entry in assignments if entry.kind == "variable" and not RESERVED.fullmatch(entry.key)}
    remote_secrets = _remote_names("secret", repo)
    remote_variables = _remote_names("variable", repo)
    return RemoteValueStatus(
        sorted(local - remote_secrets - remote_variables),
        sorted(local_variables - remote_variables - remote_secrets),
        sorted(remote_secrets - local - local_variables),
        sorted(remote_variables - local - local_variables),
        sorted(local & remote_variables),
        sorted(local_variables & remote_secrets),
    )


def sync(entries: list[ActionValue], repo: str, dry_run: bool, migrate_types: bool = False, prune: bool = False) -> SyncResult:
    if migrate_types and prune:
        raise StoreError("--migrate-types and --prune cannot be combined")
    remote_secrets = _remote_names("secret", repo) if migrate_types or prune else set()
    remote_variables = _remote_names("variable", repo) if migrate_types or prune else set()
    stale: list[tuple[str, str]] = []
    if prune:
        local_names = {entry.name for entry in entries}
        stale = [("secret", name) for name in sorted(remote_secrets - local_names)] + [("variable", name) for name in sorted(remote_variables - local_names)]
        for kind, name in stale:
            if not dry_run:
                result = subprocess.run(["gh", kind, "delete" if kind == "variable" else "remove", name, "--repo", repo], text=True, capture_output=True, check=False)
                if result.returncode:
                    raise StoreError(f"cannot prune stale {kind} '{name}': {result.stderr.strip() or 'gh failed'}")
    for entry in entries:
        opposite_kind = "variable" if entry.kind == "secret" else "secret"
        opposite_names = remote_variables if entry.kind == "secret" else remote_secrets
        if entry.name in opposite_names:
            if migrate_types and not dry_run:
                result = subprocess.run(["gh", opposite_kind, "delete" if opposite_kind == "variable" else "remove", entry.name, "--repo", repo], text=True, capture_output=True, check=False)
                if result.returncode:
                    raise StoreError(f"cannot migrate '{entry.name}': failed to remove stale {opposite_kind}: {result.stderr.strip() or 'gh failed'}")
        command = ["gh", "secret" if entry.kind == "secret" else "variable", "set", entry.name, "--repo", repo]
        if not dry_run:
            result = subprocess.run(command, input=entry.value, text=True, capture_output=True, check=False)
            if result.returncode:
                raise StoreError(f"cannot set {entry.kind} '{entry.name}'; stale counterpart was removed and must be restored manually: {result.stderr.strip() or 'gh failed'}")
    return SyncResult(len(entries), len(stale))


def export_act(entries: list[ActionValue], secrets_path: Path, vars_path: Path) -> tuple[int, int]:
    grouped = {"secret": [], "variable": []}
    for entry in entries:
        value = entry.value
        if "\n" in value:
            value = "@base64:" + base64.b64encode(value.encode()).decode()
        grouped[entry.kind].append(f"{entry.name}={value}")
    for kind, target in (("secret", secrets_path), ("variable", vars_path)):
        if grouped[kind]:
            target.write_text("\n".join(grouped[kind]) + "\n", encoding="utf-8")
            target.chmod(0o600)
    return len(grouped["secret"]), len(grouped["variable"])


def _finding(path: Path, line: int, severity: str, name: str, message: str) -> dict[str, str | int]:
    return {"file": path.name, "line": line, "severity": severity, "name": name, "message": message}


def check_workflows(directory: Path, entries: list[ActionValue]) -> dict[str, list[dict[str, str | int]]]:
    workflow_dir = directory / ".github" / "workflows"
    if not workflow_dir.is_dir():
        raise StoreError(f"workflow directory not found: {workflow_dir}")
    refs: dict[str, set[str]] = {}
    locations: dict[str, list[tuple[Path, int, str]]] = {}
    defaulted: set[str] = set()
    order: list[dict[str, str | int]] = []
    for path in sorted((*workflow_dir.glob("*.yml"), *workflow_dir.glob("*.yaml"))):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            found: list[tuple[str, str]] = []
            for expression in re.finditer(r"\$\{\{(?P<body>.*?)\}\}", line):
                body = expression["body"]
                for match in REF.finditer(body):
                    found.append((match["name"], match["kind"]))
                    locations.setdefault(match["name"], []).append((path, number, match["kind"]))
                    fallback = body[match.end() :].rsplit("||", 1)
                    if len(fallback) == 2 and not REF.search(fallback[1]):
                        defaulted.add(match["name"])
            for name, kind in found:
                refs.setdefault(name, set()).add(kind)
            kinds = [kind for _, kind in found]
            if "secrets" in kinds and "vars" in kinds and kinds.index("vars") < kinds.index("secrets"):
                order.append(_finding(path, number, "error", found[0][0], "reference secrets before vars in a fallback expression"))
    local = {entry.name: entry.kind for entry in entries}
    unreferenced = [
        _finding(entry.source or Path(".env"), entry.line or 1, "warning", entry.name, f"{entry.name} is declared as gh-vault {entry.kind} but not referenced by a workflow")
        for entry in entries
        if entry.name not in refs
    ]
    mismatch = [
        _finding(path, number, "error", name, f"{kind}.{name} is referenced but .env declares {name} as gh-vault {local[name]}")
        for name, kinds in refs.items()
        if name in local and len(kinds) == 1 and ({"secret": "secrets", "variable": "vars"}[local[name]] not in kinds)
        for path, number, kind in locations[name]
    ]
    orphan = [
        _finding(path, number, "warning", name, f"{kind}.{name} is not declared locally and has no fallback default")
        for name, usages in locations.items()
        if name not in local and name not in defaulted and not RESERVED.match(name)
        for path, number, kind in usages
    ]
    return {"unreferenced": unreferenced, "type_mismatch": mismatch, "order": order, "orphan": orphan}


def suggested_env(entries: list[ActionValue]) -> str:
    return "\n".join(f"  {entry.name}: ${{{{ {'secrets' if entry.kind == 'secret' else 'vars'}.{entry.name} }}}}" for entry in entries)


def default_repo(directory: Path) -> str:
    namespace, _ = project_namespace(directory)
    return namespace


def json_result(result: dict[str, list[dict[str, str | int]]]) -> str:
    return json.dumps(result, indent=2, sort_keys=True)
