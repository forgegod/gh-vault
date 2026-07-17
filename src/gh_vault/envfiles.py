from __future__ import annotations

import base64
import json
import re
import subprocess
from pathlib import Path
from urllib.parse import urlparse

from .store import StoreError, VaultStore

KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
SCP_URL = re.compile(r"^(?:[^@]+@)?(?P<host>[^:]+):(?P<path>.+)$")


def project_namespace(directory: Path) -> tuple[str, str]:
    result = subprocess.run(["git", "config", "--get", "remote.origin.url"], cwd=directory, text=True, capture_output=True, check=False)
    origin = result.stdout.strip()
    if result.returncode or not origin:
        raise StoreError("origin remote is required; run this command in a checkout with remote.origin.url")
    if match := SCP_URL.fullmatch(origin):
        host, path = match["host"], match["path"]
    else:
        parsed = urlparse(origin)
        host, path = parsed.hostname or "", parsed.path.lstrip("/")
    path = path.removesuffix(".git")
    parts = [part for part in path.split("/") if part]
    if not re.fullmatch(r"[A-Za-z0-9.-]+", host or "") or not parts or any(not re.fullmatch(r"[A-Za-z0-9._-]+", part) for part in parts):
        raise StoreError("origin URL cannot be represented as a safe project namespace")
    return f"{host.lower()}/{'/'.join(parts)}", origin


def parse_dotenv(path: Path) -> dict[str, str]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise StoreError(f"cannot read {path}: {exc}") from exc
    values: dict[str, str] = {}
    for number, line in enumerate(lines, 1):
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
    return value.split(" #", 1)[0].rstrip()


def format_dotenv_value(value: str) -> str:
    if "\n" in value:
        return "@base64:" + base64.b64encode(value.encode()).decode()
    if re.fullmatch(r"[A-Za-z0-9_./:@%+=,-]*", value):
        return value
    return json.dumps(value, ensure_ascii=False)


def archive_environment(store: VaultStore, directory: Path, env_file: Path, example_file: Path) -> str:
    namespace, origin = project_namespace(directory)
    values = parse_dotenv(env_file)
    try:
        example = example_file.read_text(encoding="utf-8")
    except OSError as exc:
        raise StoreError(f"cannot read {example_file}: {exc}") from exc
    base = f"projects/{namespace}"
    store.put_secret(f"{base}/env.json", json.dumps({"version": 1, "origin": origin, "values": values}, sort_keys=True))
    store.put_secret(f"{base}/env.example", example)
    return namespace


def restore_environment(store: VaultStore, directory: Path, env_file: Path, example_file: Path, force: bool, restore_example: bool) -> str:
    namespace, origin = project_namespace(directory)
    base = f"projects/{namespace}"
    try:
        data = json.loads(store.get_secret(f"{base}/env.json"))
    except json.JSONDecodeError as exc:
        raise StoreError("archived environment has invalid data") from exc
    if data.get("origin") != origin or not isinstance(data.get("values"), dict):
        raise StoreError("archived environment does not match this origin")
    if env_file.exists() and not force:
        raise StoreError(f"refusing to overwrite {env_file}; use --force")
    archived_example = store.get_secret(f"{base}/env.example")
    if restore_example or not example_file.exists():
        _write_private(example_file, archived_example)
    template = example_file.read_text(encoding="utf-8") if example_file.exists() else archived_example
    rendered = render_template(template, {str(key): str(value) for key, value in data["values"].items()})
    _write_private(env_file, rendered)
    return namespace


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
