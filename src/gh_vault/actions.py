from __future__ import annotations

import base64
import json
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from .envfiles import DotenvAssignment, _parse_assignment, _write_private, example_file_for, format_dotenv_value, parse_typed_dotenv, project_namespace
from .store import StoreError, VaultStore

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


def action_values(env_file: Path, store: VaultStore | None = None) -> list[ActionValue]:
    assignments = parse_typed_dotenv(env_file)
    configured = {profile.name for profile in store.profiles()} if store is not None else set()
    entries: list[ActionValue] = []
    for entry in assignments:
        if entry.kind == "local":
            continue
        if entry.profile is not None:
            if store is None:
                raise StoreError(f"vault profile '{entry.profile}' referenced at {env_file}:{entry.line} requires a vault store")
            if entry.profile not in configured:
                raise StoreError(f"vault profile '{entry.profile}' referenced at {env_file}:{entry.line} is not configured")
            entries.append(ActionValue(entry.key, entry.kind, store.get(entry.profile), env_file, entry.line))
            continue
        if RESERVED.fullmatch(entry.key):
            continue
        if entry.value:
            entries.append(ActionValue(entry.key, entry.kind, entry.value, env_file, entry.line))
    return entries


def runtime_environment(env_file: Path, store: VaultStore) -> dict[str, str]:
    environment: dict[str, str] = {}
    configured = {profile.name for profile in store.profiles()}
    for entry in parse_typed_dotenv(env_file):
        if entry.kind == "local":
            continue
        if entry.profile is not None:
            if entry.profile not in configured:
                raise StoreError(f"vault profile '{entry.profile}' referenced at {env_file}:{entry.line} is not configured")
            environment[entry.key] = store.get(entry.profile)
            continue
        if RESERVED.fullmatch(entry.key):
            continue
        if entry.value:
            environment[entry.key] = entry.value
    return environment


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


def sync(
    entries: list[ActionValue],
    repo: str,
    kind: Literal["secret", "variable"],
    dry_run: bool,
    migrate_types: bool = False,
    prune: bool = False,
) -> SyncResult:
    if migrate_types and prune:
        raise StoreError("--migrate-types and --prune cannot be combined")
    mismatched = [entry for entry in entries if entry.kind != kind]
    if mismatched:
        names = ", ".join(sorted(entry.name for entry in mismatched))
        raise StoreError(f"{kind} sync received entries with other kinds: {names}")
    remote_target = _remote_names(kind, repo) if migrate_types or prune else set()
    remote_opposite = _remote_names("variable" if kind == "secret" else "secret", repo) if migrate_types else set()
    prune_names: list[str] = []
    if prune:
        local_names = {entry.name for entry in entries}
        prune_names = sorted(remote_target - local_names)
        for name in prune_names:
            if not dry_run:
                result = subprocess.run(
                    ["gh", kind, "delete" if kind == "variable" else "remove", name, "--repo", repo],
                    text=True,
                    capture_output=True,
                    check=False,
                )
                if result.returncode:
                    raise StoreError(f"cannot prune stale {kind} '{name}': {result.stderr.strip() or 'gh failed'}")
    for entry in entries:
        if migrate_types and entry.name in remote_opposite and not dry_run:
            opposite = "variable" if kind == "secret" else "secret"
            result = subprocess.run(
                ["gh", opposite, "delete" if opposite == "variable" else "remove", entry.name, "--repo", repo],
                text=True,
                capture_output=True,
                check=False,
            )
            if result.returncode:
                raise StoreError(f"cannot migrate '{entry.name}': failed to remove stale {opposite}: {result.stderr.strip() or 'gh failed'}")
        command = ["gh", kind, "set", entry.name, "--repo", repo]
        if not dry_run:
            result = subprocess.run(command, input=entry.value, text=True, capture_output=True, check=False)
            if result.returncode:
                raise StoreError(
                    f"cannot set {kind} '{entry.name}'; stale counterpart was removed and must be restored manually: {result.stderr.strip() or 'gh failed'}"
                )
    return SyncResult(len(entries), len(prune_names))


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


def run_act(env_file: Path, program: list[str], directory: Path) -> int:
    if not program or program[0] != "--":
        raise StoreError("run-act requires an act command after --")
    if Path(program[1]).name == "act":
        command = program[1:]
    elif len(program) >= 2 and Path(program[1]).name == "gh" and len(program) >= 3 and Path(program[2]).name == "act":
        command = program[1:]
    else:
        raise StoreError("run-act requires an act command after -- (use 'act' or 'gh act')")
    forbidden = ("--secret-file", "--var-file")
    if any(argument == flag or argument.startswith(flag + "=") for argument in command for flag in forbidden):
        raise StoreError("run-act manages --secret-file and --var-file; do not supply them manually")
    entries = action_values(env_file)
    with tempfile.TemporaryDirectory(prefix="gh-vault-act-") as temporary:
        root = Path(temporary)
        os.chmod(root, 0o700)
        secrets_path = root / "secrets.env"
        variables_path = root / "variables.env"
        _write_private(secrets_path, "")
        _write_private(variables_path, "")
        export_act(entries, secrets_path, variables_path)
        try:
            result = subprocess.run(
                [*command, "--secret-file", str(secrets_path), "--var-file", str(variables_path)],
                cwd=directory,
                check=False,
            )
        except OSError as exc:
            raise StoreError(f"cannot run act: {exc}") from exc
        return result.returncode


def migrate_env_source(env_file: Path) -> tuple[int, int]:
    example_file = example_file_for(env_file)
    targets = [(env_file, False), *(([(example_file, True)] if example_file.exists() else []))]
    rendered: list[tuple[Path, str, int]] = []
    for path, include_commented in targets:
        try:
            source = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise StoreError(f"cannot read {path}: {exc}") from exc
        content, count = _render_legacy_declarations(source, path, include_commented)
        rendered.append((path, content, count))

    temporary: list[tuple[Path, Path]] = []
    try:
        for path, content, count in rendered:
            if not count:
                continue
            target = path.with_name(path.name + ".gh-vault.tmp")
            _write_private(target, content)
            parse_typed_dotenv(target, include_commented=path == example_file)
            if target.read_text(encoding="utf-8") != content:
                raise StoreError(f"cannot verify migrated environment file: {path}")
            temporary.append((path, target))
        for path, target in temporary:
            os.replace(target, path)
    finally:
        for _, target in temporary:
            if target.exists():
                target.unlink()
    return rendered[0][2], rendered[1][2] if len(rendered) > 1 else 0


def _render_legacy_declarations(source: str, path: Path, include_commented: bool) -> tuple[str, int]:
    lines = source.splitlines()
    assignments: list[tuple[int, str, bool]] = []
    occupied: set[str] = set()
    pending: tuple[str, int] | None = None
    for number, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith("#") and stripped[1:].lstrip().startswith("gh-vault:"):
            if pending is not None:
                raise StoreError(f"gh-vault directive must be followed immediately by an assignment at {path}:{pending[1]}")
            kind = stripped[1:].lstrip().removeprefix("gh-vault:").strip()
            if kind not in {"secret", "variable"}:
                raise StoreError(f"invalid gh-vault directive at {path}:{number}")
            pending = (kind, number)
            continue
        parsed = _parse_assignment(line, path, number, include_commented=include_commented)
        if pending is not None:
            if parsed is None:
                raise StoreError(f"gh-vault directive must be followed immediately by an assignment at {path}:{pending[1]}")
            if parsed[0].startswith(("GH_VAR_", "GH_SECRET_")):
                raise StoreError(f"legacy declaration conflicts with an existing directive at {path}:{number}")
            pending = None
        if parsed is None:
            continue
        key, _, commented = parsed
        if key.startswith(("GH_VAR_", "GH_SECRET_")):
            assignments.append((number - 1, key, commented))
        else:
            occupied.add(key)
    if pending is not None:
        raise StoreError(f"gh-vault directive must be followed immediately by an assignment at {path}:{pending[1]}")

    migrated: set[str] = set()
    for _, key, _ in assignments:
        target = key.removeprefix("GH_VAR_").removeprefix("GH_SECRET_")
        if target in occupied or target in migrated:
            raise StoreError(f"legacy declaration collides with target key {target} in {path}")
        migrated.add(target)
    for index, key, commented in reversed(assignments):
        kind = "variable" if key.startswith("GH_VAR_") else "secret"
        target = key.removeprefix("GH_VAR_").removeprefix("GH_SECRET_")
        line = lines[index]
        prefix = line[: len(line) - len(line.lstrip())]
        assignment = line.replace(key, target, 1)
        lines[index : index + 1] = [f"{prefix}# gh-vault: {kind}", assignment]
    return "\n".join(lines) + ("\n" if source.endswith("\n") else ""), len(assignments)


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
