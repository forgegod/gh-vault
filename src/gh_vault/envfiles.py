from __future__ import annotations

import base64
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, TypedDict
from urllib.parse import urlparse

from .store import StoreError, VaultStore

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


class EnvironmentManifest(TypedDict):
    version: int
    origin: str
    environments: dict[str, dict[str, bool]]


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


def archive_environment(store: VaultStore, directory: Path, env_file: Path, example_file: Path) -> str:
    namespace, origin = project_namespace(directory)
    values = parse_dotenv(env_file)
    base = f"projects/{namespace}"
    profile = environment_profile(env_file)
    store.put_secret(_environment_entry(base, profile, "json"), json.dumps({"version": 2, "origin": origin, "values": values}, sort_keys=True))
    has_example = example_file.exists()
    if has_example:
        try:
            store.put_secret(_environment_entry(base, profile, "example"), example_file.read_text(encoding="utf-8"))
        except OSError as exc:
            raise StoreError(f"cannot read {example_file}: {exc}") from exc
    else:
        try:
            store.remove_secret(_environment_entry(base, profile, "example"))
        except StoreError:
            pass
    manifest = _load_environment_manifest(store, base, origin)
    manifest["environments"][profile] = {"example": has_example}
    store.put_secret(f"{base}/environments.json", json.dumps(manifest, sort_keys=True))
    return namespace


def restore_environment(store: VaultStore, directory: Path, env_file: Path, example_file: Path, force: bool, restore_example: bool) -> str:
    namespace, origin = project_namespace(directory)
    base = f"projects/{namespace}"
    profile = environment_profile(env_file)
    try:
        data = json.loads(store.get_secret(_environment_entry(base, profile, "json")))
    except json.JSONDecodeError as exc:
        raise StoreError("archived environment has invalid data") from exc
    if data.get("origin") != origin or not isinstance(data.get("values"), dict):
        raise StoreError("archived environment does not match this origin")
    if env_file.exists() and not force:
        raise StoreError(f"refusing to overwrite {env_file}; use --force")
    manifest = _load_environment_manifest(store, base, origin)
    has_example = manifest["environments"].get(profile, {}).get("example") is True or _has_archived_example(store, base, profile)
    archived_example = store.get_secret(_environment_entry(base, profile, "example")) if has_example else ""
    if has_example and (restore_example or not example_file.exists()):
        _write_private(example_file, archived_example)
    if not example_file.exists():
        raise StoreError(f"cannot reconstruct {env_file}: no local or archived {example_file}")
    template = example_file.read_text(encoding="utf-8")
    rendered = render_template(template, {str(key): str(value) for key, value in data["values"].items()})
    _write_private(env_file, rendered)
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


def list_environments(store: VaultStore, directory: Path) -> tuple[str, list[tuple[str, bool]]]:
    namespace, origin = project_namespace(directory)
    base = f"projects/{namespace}"
    manifest = _load_environment_manifest(store, base, origin)
    environments = [(profile, details.get("example") is True) for profile, details in sorted(manifest["environments"].items())]
    if not environments:
        try:
            data = json.loads(store.get_secret(_environment_entry(base, "default", "json")))
        except (StoreError, json.JSONDecodeError):
            pass
        else:
            if data.get("origin") == origin and isinstance(data.get("values"), dict):
                environments.append(("default", _has_archived_example(store, base, "default")))
    return namespace, environments


def _environment_entry(base: str, profile: str, suffix: str) -> str:
    return f"{base}/env.{suffix}" if profile == "default" else f"{base}/env.{profile}.{suffix}"


def _has_archived_example(store: VaultStore, base: str, profile: str) -> bool:
    try:
        store.get_secret(_environment_entry(base, profile, "example"))
    except StoreError:
        return False
    return True


def _load_environment_manifest(store: VaultStore, base: str, origin: str) -> EnvironmentManifest:
    try:
        manifest = json.loads(store.get_secret(f"{base}/environments.json"))
    except StoreError:
        return {"version": 1, "origin": origin, "environments": {}}
    except json.JSONDecodeError as exc:
        raise StoreError("archived environment index has invalid data") from exc
    if not isinstance(manifest, dict) or manifest.get("origin") != origin or not isinstance(manifest.get("environments"), dict):
        raise StoreError("archived environment index does not match this origin")
    environments = manifest["environments"]
    if not all(isinstance(profile, str) and isinstance(details, dict) and all(isinstance(key, str) and isinstance(value, bool) for key, value in details.items()) for profile, details in environments.items()):
        raise StoreError("archived environment index has invalid data")
    version = manifest.get("version", 1)
    if not isinstance(version, int):
        raise StoreError("archived environment index has invalid data")
    return {"version": version, "origin": origin, "environments": environments}


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
