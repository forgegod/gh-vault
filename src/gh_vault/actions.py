from __future__ import annotations

import base64
import json
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from .envfiles import _write_private, parse_dotenv, project_namespace, render_template
from .store import StoreError

RESERVED = re.compile(r"^(?:GITHUB_|RUNNER_|CI$|GH_TOKEN$)")
REF = re.compile(r"\b(?P<kind>secrets|vars)\.(?P<name>[A-Z][A-Z0-9_]*)")
DOTENV_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
DOTENV_ASSIGNMENT = re.compile(r"^\s*(?:export\s+)?(?P<key>[A-Za-z_][A-Za-z0-9_]*)\s*=")


@dataclass(frozen=True)
class ActionValue:
    name: str
    kind: str
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
    entries: list[ActionValue] = []
    locations = {
        match["key"]: number
        for number, line in enumerate(env_file.read_text(encoding="utf-8").splitlines(), 1)
        if (match := DOTENV_ASSIGNMENT.match(line))
    }
    for key, value in parse_dotenv(env_file).items():
        if key.startswith("GH_SECRET_"):
            name, kind = key.removeprefix("GH_SECRET_"), "secret"
        elif key.startswith("GH_VAR_"):
            name, kind = key.removeprefix("GH_VAR_"), "var"
        else:
            continue
        if name and value and not RESERVED.fullmatch(name):
            entries.append(ActionValue(name, kind, value, env_file, locations.get(key)))
    return entries


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
    values = parse_dotenv(target)
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
    imported = 0
    for item in remote:
        key = f"GH_VAR_{item['name']}"
        if force or key not in values:
            values[key] = item["value"]
            imported += 1
    _write_private(target, render_template(target.read_text(encoding="utf-8"), values))
    return target, imported


def remote_secret_status(env_file: Path, repo: str) -> RemoteValueStatus:
    values = parse_dotenv(env_file)
    local = {
        key.removeprefix("GH_SECRET_")
        for key in values
        if key.startswith("GH_SECRET_") and key.removeprefix("GH_SECRET_") and not RESERVED.fullmatch(key.removeprefix("GH_SECRET_"))
    }
    local_variables = {
        key.removeprefix("GH_VAR_")
        for key in values
        if key.startswith("GH_VAR_") and key.removeprefix("GH_VAR_") and not RESERVED.fullmatch(key.removeprefix("GH_VAR_"))
    }
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
    grouped = {"secret": [], "var": []}
    for entry in entries:
        value = entry.value
        if "\n" in value:
            value = "@base64:" + base64.b64encode(value.encode()).decode()
        grouped[entry.kind].append(f"{entry.name}={value}")
    for kind, target in (("secret", secrets_path), ("var", vars_path)):
        if grouped[kind]:
            target.write_text("\n".join(grouped[kind]) + "\n", encoding="utf-8")
            target.chmod(0o600)
    return len(grouped["secret"]), len(grouped["var"])


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
        _finding(entry.source or Path(".env"), entry.line or 1, "warning", entry.name, f"GH_{entry.kind.upper()}_{entry.name} is declared locally but not referenced by a workflow")
        for entry in entries
        if entry.name not in refs
    ]
    mismatch = [
        _finding(path, number, "error", name, f"{kind}.{name} is referenced but .env declares GH_{local[name].upper()}_{name}")
        for name, kinds in refs.items()
        if name in local and len(kinds) == 1 and ({"secret": "secrets", "var": "vars"}[local[name]] not in kinds)
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
