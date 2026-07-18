from __future__ import annotations

import base64
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from .store import EnvironmentStore, StoreError, VaultStore

KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
SCP_URL = re.compile(r"^(?:[^@]+@)?(?P<host>[^:]+):(?P<path>.+)$")
DotenvKind = Literal["secret", "variable", "local"]


@dataclass(frozen=True)
class DotenvAssignment:
    key: str
    value: str
    kind: DotenvKind
    line: int
    commented: bool


@dataclass(frozen=True)
class ArchiveMigrationResult:
    namespace: str
    profile: str
    variables: int
    secrets: int
    local: int


def project_namespace(directory: Path) -> tuple[str, str]:
    result = subprocess.run(["git", "config", "--get", "remote.origin.url"], cwd=directory, text=True, capture_output=True, check=False)
    origin = result.stdout.strip()
    if result.returncode or not origin:
        raise StoreError("origin remote is required; run this command in a checkout with remote.origin.url")
    if "://" not in origin and (match := SCP_URL.fullmatch(origin)):
        host, path = match["host"], match["path"]
    else:
        parsed = urlparse(origin)
        if parsed.scheme not in {"http", "https", "ssh"} or parsed.query or parsed.fragment or parsed.params:
            raise StoreError("origin URL cannot be represented as a safe project namespace")
        host, path = parsed.hostname or "", parsed.path.lstrip("/")
    path = path.removesuffix(".git")
    parts = path.split("/")
    if not re.fullmatch(r"[A-Za-z0-9.-]+", host or "") or not parts or any(part in {".", ".."} or not re.fullmatch(r"[A-Za-z0-9._-]+", part) for part in parts):
        raise StoreError("origin URL cannot be represented as a safe project namespace")
    return f"{host.lower()}/{'/'.join(parts)}", origin


def parse_dotenv(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for number, line in enumerate(_read_dotenv_lines(path), 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("export "):
            stripped = stripped[7:].lstrip()
        key, separator, raw = stripped.partition("=")
        if not separator or not KEY.fullmatch(key.strip()):
            raise StoreError(f"unsupported dotenv syntax at {path}:{number}")
        values[key.strip()] = _decode(raw.strip(), path.parent, path, number)
    return values


def parse_typed_dotenv(path: Path, *, include_commented: bool = False) -> tuple[DotenvAssignment, ...]:
    assignments: list[DotenvAssignment] = []
    seen: set[str] = set()
    pending: tuple[Literal["secret", "variable"], int] | None = None

    for number, line in enumerate(_read_dotenv_lines(path), 1):
        stripped = line.strip()
        if pending is not None:
            parsed = _parse_assignment(line, path, number, include_commented=include_commented)
            if parsed is None:
                raise StoreError(f"gh-vault directive must be followed immediately by an assignment at {path}:{pending[1]}")
            key, value, commented = parsed
            _append_typed_assignment(assignments, seen, key, value, pending[0], number, commented, path)
            pending = None
            continue

        if not stripped:
            continue
        if stripped.startswith("#"):
            comment = stripped[1:].lstrip()
            if comment.startswith("gh-vault:"):
                kind = comment.removeprefix("gh-vault:").strip()
                if kind == "secret" or kind == "variable":
                    pending = (kind, number)
                else:
                    raise StoreError(f"invalid gh-vault directive at {path}:{number}")
                continue
            if not include_commented:
                continue

        parsed = _parse_assignment(line, path, number, include_commented=include_commented)
        if parsed is None:
            continue
        key, value, commented = parsed
        _append_typed_assignment(assignments, seen, key, value, "local", number, commented, path)

    if pending is not None:
        raise StoreError(f"gh-vault directive must be followed immediately by an assignment at {path}:{pending[1]}")
    return tuple(assignments)


def _read_dotenv_lines(path: Path) -> list[str]:
    try:
        return path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise StoreError(f"cannot read {path}: {exc}") from exc


def _parse_assignment(line: str, path: Path, number: int, *, include_commented: bool) -> tuple[str, str, bool] | None:
    stripped = line.strip()
    if not stripped:
        return None
    commented = stripped.startswith("#")
    if commented:
        if not include_commented:
            return None
        stripped = stripped[1:].lstrip()
        if not stripped or "=" not in stripped:
            return None
    if stripped.startswith("export "):
        stripped = stripped[7:].lstrip()
    key, separator, raw = stripped.partition("=")
    key = key.strip()
    if not separator or not KEY.fullmatch(key):
        if commented:
            return None
        raise StoreError(f"unsupported dotenv syntax at {path}:{number}")
    return key, _decode(raw.strip(), path.parent, path, number), commented


def _append_typed_assignment(
    assignments: list[DotenvAssignment],
    seen: set[str],
    key: str,
    value: str,
    kind: DotenvKind,
    number: int,
    commented: bool,
    path: Path,
) -> None:
    if key.startswith(("GH_VAR_", "GH_SECRET_")):
        raise StoreError(f"legacy GH_VAR_/GH_SECRET_ declaration at {path}:{number}")
    if key in seen:
        raise StoreError(f"duplicate dotenv key {key} at {path}:{number}")
    seen.add(key)
    assignments.append(DotenvAssignment(key, value, kind, number, commented))


def _decode(value: str, parent: Path, path: Path, number: int) -> str:
    if value.startswith("@file:"):
        source = Path(value[6:]).expanduser()
        if not source.is_absolute():
            source = parent / source
        try:
            return source.read_text(encoding="utf-8")
        except OSError as exc:
            raise StoreError(f"cannot read @file at {path}:{number}: {exc}") from exc
    if value.startswith("@base64:"):
        try:
            return base64.b64decode(value[8:], validate=True).decode("utf-8")
        except (ValueError, UnicodeDecodeError) as exc:
            raise StoreError(f"invalid @base64 value at {path}:{number}") from exc
    if value.startswith("'"):
        if len(value) < 2 or not value.endswith("'"):
            raise StoreError(f"unterminated single quote at {path}:{number}")
        return value[1:-1]
    if value.startswith('"'):
        if len(value) < 2 or not value.endswith('"'):
            raise StoreError(f"unterminated double quote at {path}:{number}")
        try:
            return json.loads(value)
        except json.JSONDecodeError as exc:
            raise StoreError(f"invalid double quote escape at {path}:{number}") from exc
    value = value.split(" #", 1)[0].rstrip()
    if "$(" in value or "${" in value or "`" in value:
        raise StoreError(f"unsupported dotenv syntax at {path}:{number}")
    return value


def format_dotenv_value(value: str) -> str:
    if "\n" in value:
        return "@base64:" + base64.b64encode(value.encode()).decode()
    if re.fullmatch(r"[A-Za-z0-9_./:@%+=,-]*", value):
        return value
    return json.dumps(value, ensure_ascii=False)


def archive_environment(store: VaultStore, environment_store: EnvironmentStore, directory: Path, env_file: Path, example_file: Path) -> str:
    namespace, origin = project_namespace(directory)
    assignments = parse_typed_dotenv(env_file)
    variables = {entry.key: entry.value for entry in assignments if entry.kind == "variable"}
    secrets = {entry.key: entry.value for entry in assignments if entry.kind == "secret"}
    base = f"projects/{namespace}"
    profile = environment_profile(env_file)
    manifest = environment_store.load_manifest(namespace, origin)
    environments = dict(manifest["environments"])
    previous = environments.get(profile, {"variables": False, "secrets": False, "example": False})
    example: str | None = None
    if secrets and example_file.exists():
        try:
            example = example_file.read_text(encoding="utf-8")
        except OSError as exc:
            raise StoreError(f"cannot read {example_file}: {exc}") from exc

    if secrets:
        payload = {"version": 3, "origin": origin, "values": secrets}
        store.put_secret(_environment_entry(base, profile, "secrets.json"), json.dumps(payload, sort_keys=True))
        if _load_secret_payload(store, base, profile, origin) != secrets:
            raise StoreError("encrypted environment payload verification failed")
        if example is not None:
            store.put_secret(_environment_entry(base, profile, "example"), example)
            if store.get_secret(_environment_entry(base, profile, "example")) != example:
                raise StoreError("encrypted environment template verification failed")
    if variables:
        environment_store.save_variables(namespace, profile, origin, variables)
        if environment_store.load_variables(namespace, profile, origin) != variables:
            raise StoreError("environment variable payload verification failed")

    if previous["variables"] and not variables:
        environment_store.remove_variables(namespace, profile)
    if previous["secrets"] and not secrets:
        store.remove_secret(_environment_entry(base, profile, "secrets.json"))
    if previous["example"] and example is None:
        store.remove_secret(_environment_entry(base, profile, "example"))

    if variables or secrets:
        environments[profile] = {"variables": bool(variables), "secrets": bool(secrets), "example": example is not None}
    else:
        environments.pop(profile, None)
    if environments:
        environment_store.save_manifest(namespace, origin, environments)
    else:
        environment_store.remove_manifest(namespace)
    return namespace


def migrate_environment_archive(store: VaultStore, environment_store: EnvironmentStore, directory: Path, env_file: Path, example_file: Path) -> ArchiveMigrationResult:
    namespace, origin = project_namespace(directory)
    profile = environment_profile(env_file)
    base = f"projects/{namespace}"
    declaration_file = env_file if env_file.exists() else example_file
    if not declaration_file.exists():
        raise StoreError(f"archive migration requires {env_file} or {example_file}")
    declarations = parse_typed_dotenv(declaration_file, include_commented=declaration_file == example_file)
    kinds = {entry.key: entry.kind for entry in declarations if entry.kind != "local"}
    legacy_entry = _environment_entry(base, profile, "json")
    try:
        legacy = json.loads(store.get_secret(legacy_entry))
    except json.JSONDecodeError as exc:
        raise StoreError(f"legacy archive for {env_file.name} has invalid data") from exc
    if not isinstance(legacy, dict) or set(legacy) != {"version", "origin", "values"} or legacy.get("version") != 2 or legacy.get("origin") != origin:
        raise StoreError(f"legacy archive for {env_file.name} does not match this origin or format")
    values = legacy.get("values")
    if not isinstance(values, dict) or not all(isinstance(key, str) and isinstance(value, str) for key, value in values.items()):
        raise StoreError(f"legacy archive for {env_file.name} has invalid data")

    normalized: dict[str, str] = {}
    for key, value in values.items():
        target = key.removeprefix("GH_VAR_").removeprefix("GH_SECRET_")
        if target in normalized:
            raise StoreError(f"legacy archive for {env_file.name} contains duplicate target key {target}")
        normalized[target] = value
    variables = {key: value for key, value in normalized.items() if kinds.get(key) == "variable"}
    secrets = {key: value for key, value in normalized.items() if kinds.get(key) == "secret"}
    local_count = len(normalized) - len(variables) - len(secrets)

    manifest = environment_store.load_manifest(namespace, origin)
    environments = dict(manifest["environments"])
    existing = environments.get(profile)
    example: str | None = None
    if secrets:
        try:
            example = store.get_secret(_environment_entry(base, profile, "example"))
        except StoreError:
            pass
    expected = {"variables": bool(variables), "secrets": bool(secrets), "example": example is not None}
    if existing is not None:
        current_variables = environment_store.load_variables(namespace, profile, origin) if existing["variables"] else {}
        current_secrets = _load_secret_payload(store, base, profile, origin) if existing["secrets"] else {}
        current_example = store.get_secret(_environment_entry(base, profile, "example")) if existing["example"] else None
        if existing != expected or current_variables != variables or current_secrets != secrets or current_example != example:
            raise StoreError(f"split archive for {env_file.name} already exists with different data")
        store.remove_secret(legacy_entry)
        return ArchiveMigrationResult(namespace, profile, len(variables), len(secrets), local_count)

    destination_variables = environment_store.load_variables(namespace, profile, origin)
    if destination_variables and destination_variables != variables:
        raise StoreError(f"split archive for {env_file.name} already has a different variable payload")
    try:
        store.get_secret(_environment_entry(base, profile, "secrets.json"))
    except StoreError:
        destination_secrets: dict[str, str] | None = None
    else:
        destination_secrets = _load_secret_payload(store, base, profile, origin)
    if destination_secrets is not None and destination_secrets != secrets:
        raise StoreError(f"split archive for {env_file.name} already has a different encrypted payload")

    if secrets:
        payload = {"version": 3, "origin": origin, "values": secrets}
        store.put_secret(_environment_entry(base, profile, "secrets.json"), json.dumps(payload, sort_keys=True))
        if _load_secret_payload(store, base, profile, origin) != secrets:
            raise StoreError("encrypted environment payload verification failed")
    if variables:
        environment_store.save_variables(namespace, profile, origin, variables)
        if environment_store.load_variables(namespace, profile, origin) != variables:
            raise StoreError("environment variable payload verification failed")
    if not secrets:
        try:
            store.remove_secret(_environment_entry(base, profile, "example"))
        except StoreError:
            pass
    if variables or secrets:
        environments[profile] = expected
    else:
        environments.pop(profile, None)
    if environments:
        environment_store.save_manifest(namespace, origin, environments)
        if environment_store.load_manifest(namespace, origin)["environments"] != environments:
            raise StoreError("environment index verification failed")
    else:
        environment_store.remove_manifest(namespace)
    store.remove_secret(legacy_entry)
    return ArchiveMigrationResult(namespace, profile, len(variables), len(secrets), local_count)


def restore_environment(store: VaultStore, environment_store: EnvironmentStore, directory: Path, env_file: Path, example_file: Path, force: bool, restore_example: bool) -> str:
    if env_file.exists() and not force:
        raise StoreError(f"refusing to overwrite {env_file}; use --force")
    namespace, origin = project_namespace(directory)
    base = f"projects/{namespace}"
    profile = environment_profile(env_file)
    manifest = environment_store.load_manifest(namespace, origin)
    details = manifest["environments"].get(profile)
    if details is None:
        raise StoreError(f"no archived environment for {env_file.name}")
    variables = environment_store.load_variables(namespace, profile, origin) if details["variables"] else {}
    secrets = _load_secret_payload(store, base, profile, origin) if details["secrets"] else {}
    if variables.keys() & secrets.keys():
        raise StoreError("environment payloads contain duplicate keys")
    values = {**variables, **secrets}
    archived_example = store.get_secret(_environment_entry(base, profile, "example")) if details["example"] else None
    try:
        local_example = example_file.read_text(encoding="utf-8") if example_file.exists() else None
    except OSError as exc:
        raise StoreError(f"cannot read {example_file}: {exc}") from exc
    if local_example is None and archived_example is None and details["variables"] and not details["secrets"]:
        raise StoreError(f"variable-only restore requires a local template: {example_file}")
    if restore_example and archived_example is None:
        raise StoreError("no archived environment template")
    template = local_example if local_example is not None else archived_example or ""
    _write_private(env_file, render_template(template, values))
    if restore_example:
        assert archived_example is not None
        _write_private(example_file, archived_example)
    return namespace


def environment_profile(env_file: Path) -> str:
    name = env_file.name
    if name == ".env":
        return "default"
    if match := re.fullmatch(r"\.env\.([A-Za-z0-9][A-Za-z0-9._-]{0,63})", name):
        return match[1]
    raise StoreError("environment file must be .env or .env.<profile>")


def example_file_for(env_file: Path) -> Path:
    profile = environment_profile(env_file)
    return env_file.parent / (".env.example" if profile == "default" else f".env.example.{profile}")


def list_environments(environment_store: EnvironmentStore, directory: Path) -> tuple[str, list[tuple[str, bool]]]:
    namespace, origin = project_namespace(directory)
    manifest = environment_store.load_manifest(namespace, origin)
    environments = [(profile, details.get("example") is True) for profile, details in sorted(manifest["environments"].items())]
    return namespace, environments


def show_environment(environment_store: EnvironmentStore, directory: Path, env_file: Path) -> tuple[str, dict[str, str]]:
    namespace, origin = project_namespace(directory)
    profile = environment_profile(env_file)
    manifest = environment_store.load_manifest(namespace, origin)
    details = manifest["environments"].get(profile)
    if details is None or not details["variables"]:
        return namespace, {}
    return namespace, environment_store.load_variables(namespace, profile, origin)


def _environment_entry(base: str, profile: str, suffix: str) -> str:
    return f"{base}/env.{suffix}" if profile == "default" else f"{base}/env.{profile}.{suffix}"


def _load_secret_payload(store: VaultStore, base: str, profile: str, origin: str) -> dict[str, str]:
    try:
        payload = json.loads(store.get_secret(_environment_entry(base, profile, "secrets.json")))
    except json.JSONDecodeError as exc:
        raise StoreError("encrypted environment payload has invalid data") from exc
    if not isinstance(payload, dict) or set(payload) != {"version", "origin", "values"} or payload.get("version") != 3 or payload.get("origin") != origin:
        raise StoreError("encrypted environment payload does not match this origin or format")
    values = payload.get("values")
    if not isinstance(values, dict) or not all(isinstance(key, str) and isinstance(value, str) for key, value in values.items()):
        raise StoreError("encrypted environment payload has invalid data")
    return values


def render_template(template: str, values: dict[str, str]) -> str:
    used: set[str] = set()
    output: list[str] = []
    for line in template.splitlines():
        active = line.lstrip("# ").strip()
        key, separator, _ = active.partition("=")
        if separator and KEY.fullmatch(key) and key in values:
            output.append(f"{key}={format_dotenv_value(values[key])}")
            used.add(key)
        else:
            output.append(line)
    extras = [key for key in values if key not in used]
    if extras:
        output.extend(["", "# Local additions"])
        output.extend(f"{key}={format_dotenv_value(values[key])}" for key in sorted(extras))
    return "\n".join(output) + "\n"


def _write_private(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    path.chmod(0o600)
