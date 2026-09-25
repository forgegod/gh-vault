from __future__ import annotations

import argparse
import ast
import importlib
import io
import os
import sys
import tempfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID

from .store import BitwardenConnection, StoreError

ADAPTER_API_VERSION = 1
BWS_OVERRIDE_ENV = ("BWS_CONFIG_FILE", "BWS_PROFILE", "BWS_SERVER_URL")


@dataclass(frozen=True)
class BitwardenEndpoints:
    api_url: str
    identity_url: str


@dataclass(frozen=True)
class BitwardenProject:
    project_id: str
    organization_id: str


@dataclass
class LocalBitwardenAdapter:
    resolve: Callable[..., object]
    reader: Callable[..., object] | None
    previous_modules: dict[str, ModuleType]

    def __call__(self, **request: object) -> object:
        return self.resolve(**request)

    def read_environment(self, **request: object) -> object:
        if self.reader is None:
            raise StoreError("Bitwarden local adapter does not implement read_environment")
        return self.reader(**request)

    def close(self) -> None:
        for name in tuple(sys.modules):
            if name == "gh_vault_bws" or name.startswith("gh_vault_bws."):
                del sys.modules[name]
        sys.modules.update(self.previous_modules)


def canonical_uuid(value: str, label: str) -> str:
    try:
        parsed = UUID(value)
    except (AttributeError, TypeError, ValueError) as exc:
        raise argparse.ArgumentTypeError(f"{label} ID must be a canonical UUID") from exc
    canonical = str(parsed)
    if value != canonical:
        raise argparse.ArgumentTypeError(f"{label} ID must be a canonical UUID")
    if parsed.int == 0:
        raise argparse.ArgumentTypeError(f"{label} ID must be non-nil")
    return canonical


def organization_uuid(value: str) -> str:
    return canonical_uuid(value, "organization")


def project_uuid(value: str) -> str:
    return canonical_uuid(value, "project")


def default_bws_config() -> Path:
    return Path.home() / ".config" / "bws" / "config"


def _parse_known_bws_toml(text: str) -> dict[str, object]:
    profiles: dict[str, dict[str, str]] = {}
    current: dict[str, str] | None = None
    for number, raw_line in enumerate(text.splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1]
            if section.startswith("profiles."):
                name = section.removeprefix("profiles.").strip().strip('"').strip("'")
                if not name:
                    raise StoreError("cannot read bws configuration")
                current = profiles.setdefault(name, {})
            else:
                current = None
            continue
        if current is None or "=" not in line:
            continue
        key, raw_value = (part.strip() for part in line.split("=", 1))
        if key not in {"server_base", "server_api", "server_identity"}:
            continue
        raw_value = raw_value.split("#", 1)[0].rstrip()
        try:
            value = ast.literal_eval(raw_value)
        except (SyntaxError, ValueError) as exc:
            raise StoreError(f"cannot read bws configuration near line {number}") from exc
        if not isinstance(value, str):
            raise StoreError(f"cannot read bws configuration near line {number}")
        current[key] = value
    return {"profiles": profiles}


def _read_bws_config(path: Path) -> dict[str, object]:
    try:
        contents = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise StoreError(f"cannot read bws configuration {path}") from None
    try:
        import tomllib
    except ModuleNotFoundError:  # pragma: no cover - exercised by the Python 3.10 CI job
        return _parse_known_bws_toml(contents)
    try:
        data = tomllib.loads(contents)
    except tomllib.TOMLDecodeError:
        raise StoreError(f"cannot read bws configuration {path}") from None
    if not isinstance(data, dict):
        raise StoreError(f"cannot read bws configuration {path}")
    return data


def _https_endpoint(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise StoreError(f"bws profile does not define an {label} endpoint")
    normalized = value.rstrip("/")
    parsed = urlsplit(normalized)
    if parsed.scheme != "https" or not parsed.hostname:
        raise StoreError(f"bws {label} endpoint must use HTTPS")
    if parsed.username is not None or parsed.password is not None:
        raise StoreError(f"bws {label} endpoint must not contain credentials")
    if parsed.query or parsed.fragment:
        raise StoreError(f"bws {label} endpoint must not contain a query or fragment")
    return normalized


def load_bws_endpoints(config_path: Path, profile_name: str) -> BitwardenEndpoints:
    path = Path(config_path).expanduser().resolve()
    data = _read_bws_config(path)
    profiles = data.get("profiles")
    if not isinstance(profiles, dict) or profile_name not in profiles:
        raise StoreError(f"bws configuration does not contain profile '{profile_name}'")
    profile = profiles[profile_name]
    if not isinstance(profile, dict):
        raise StoreError(f"bws profile '{profile_name}' has invalid data")
    base = profile.get("server_base")
    api = profile.get("server_api")
    identity = profile.get("server_identity")
    if api is None and isinstance(base, str):
        api = f"{base.rstrip('/')}/api"
    if identity is None and isinstance(base, str):
        identity = f"{base.rstrip('/')}/identity"
    return BitwardenEndpoints(
        _https_endpoint(api, "API"),
        _https_endpoint(identity, "identity"),
    )


def assert_connection_current(connection: BitwardenConnection) -> None:
    endpoints = load_bws_endpoints(Path(connection.bws_config), connection.bws_profile)
    if endpoints.api_url != connection.api_url or endpoints.identity_url != connection.identity_url:
        raise StoreError(
            f"Bitwarden connection '{connection.name}' endpoint configuration changed; "
            "run 'gh-vault bitwarden connection set' to rebind it"
        )


def reject_bws_overrides(environment: Mapping[str, str] | None = None) -> None:
    selected = os.environ if environment is None else environment
    conflicts = [name for name in BWS_OVERRIDE_ENV if selected.get(name)]
    if conflicts:
        raise StoreError(
            "conflicting bws environment override: " + ", ".join(conflicts)
        )


def _adapter_modules() -> dict[str, ModuleType]:
    return {
        name: module
        for name, module in sys.modules.items()
        if (name == "gh_vault_bws" or name.startswith("gh_vault_bws."))
        and isinstance(module, ModuleType)
    }


def _clear_adapter_modules() -> None:
    for name in tuple(sys.modules):
        if name == "gh_vault_bws" or name.startswith("gh_vault_bws."):
            del sys.modules[name]


def load_local_adapter(path: Path) -> LocalBitwardenAdapter:
    try:
        root = Path(path).expanduser().resolve(strict=True)
    except OSError:
        raise StoreError("Bitwarden local adapter path does not exist") from None
    package = root / "gh_vault_bws"
    if not root.is_dir() or not (package / "__init__.py").is_file():
        raise StoreError("Bitwarden local adapter path must contain gh_vault_bws/__init__.py")

    previous_modules = _adapter_modules()
    original_path = list(sys.path)
    _clear_adapter_modules()
    sys.path.insert(0, str(root))
    try:
        with io.StringIO() as stdout, io.StringIO() as stderr:
            from contextlib import redirect_stderr, redirect_stdout

            with redirect_stdout(stdout), redirect_stderr(stderr):
                module = importlib.import_module("gh_vault_bws")
        module_file = Path(getattr(module, "__file__", "")).resolve()
        if not module_file.is_relative_to(package.resolve()):
            raise StoreError("Bitwarden local adapter was not loaded from the selected path")
        if getattr(module, "GH_VAULT_ADAPTER_API", None) != ADAPTER_API_VERSION:
            raise StoreError(
                f"Bitwarden local adapter must implement API version {ADAPTER_API_VERSION}"
            )
        resolver = getattr(module, "resolve_project", None)
        if not callable(resolver):
            raise StoreError("Bitwarden local adapter does not implement resolve_project")
        reader = getattr(module, "read_environment", None)
        if reader is not None and not callable(reader):
            raise StoreError("Bitwarden local adapter has an invalid read_environment operation")
        return LocalBitwardenAdapter(resolver, reader, previous_modules)
    except StoreError:
        _clear_adapter_modules()
        sys.modules.update(previous_modules)
        raise
    except Exception:
        _clear_adapter_modules()
        sys.modules.update(previous_modules)
        raise StoreError("cannot load Bitwarden local adapter") from None
    finally:
        sys.path[:] = original_path


def _response_uuid(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise StoreError("Bitwarden adapter returned an invalid response")
    try:
        return canonical_uuid(value, label)
    except argparse.ArgumentTypeError:
        raise StoreError("Bitwarden adapter returned an invalid response") from None


def resolve_project(
    adapter: Callable[..., object],
    connection: BitwardenConnection,
    access_token: str,
    project_id: str,
) -> BitwardenProject:
    try:
        if not access_token or "\n" in access_token or "\r" in access_token:
            raise StoreError("Bitwarden access token must be a non-empty single line")
        with tempfile.TemporaryDirectory(prefix="gh-vault-bws-") as state_dir:
            os.chmod(state_dir, 0o700)
            state_file = str(Path(state_dir) / "state")
            try:
                with io.StringIO() as stdout, io.StringIO() as stderr:
                    from contextlib import redirect_stderr, redirect_stdout

                    with redirect_stdout(stdout), redirect_stderr(stderr):
                        response = adapter(
                            api_url=connection.api_url,
                            identity_url=connection.identity_url,
                            access_token=access_token,
                            organization_id=connection.organization_id,
                            project_id=project_id,
                            state_file=state_file,
                        )
            except Exception:
                raise StoreError("Bitwarden project resolution failed") from None
    finally:
        close = getattr(adapter, "close", None)
        if callable(close):
            close()

    if response is None:
        raise StoreError(f"Bitwarden project {project_id} is not accessible through connection '{connection.name}'")
    if not isinstance(response, dict) or set(response) != {"project_id", "organization_id"}:
        raise StoreError("Bitwarden adapter returned an invalid response")
    returned_project = _response_uuid(response["project_id"], "project")
    returned_organization = _response_uuid(response["organization_id"], "organization")
    if returned_organization != connection.organization_id:
        raise StoreError("Bitwarden adapter returned a project outside the configured organization")
    if returned_project != project_id:
        raise StoreError("Bitwarden adapter returned a different project")
    return BitwardenProject(returned_project, returned_organization)


def read_environment(
    adapter: object,
    connection: BitwardenConnection,
    access_token: str,
    project_id: str,
    keys: tuple[str, ...],
) -> dict[str, str]:
    reader = getattr(adapter, "read_environment", None)
    try:
        if not access_token or "\n" in access_token or "\r" in access_token:
            raise StoreError("Bitwarden access token must be a non-empty single line")
        if not keys or len(keys) != len(set(keys)):
            raise StoreError("Bitwarden environment request contains invalid keys")
        if not callable(reader):
            raise StoreError("Bitwarden local adapter does not implement read_environment")
        with tempfile.TemporaryDirectory(prefix="gh-vault-bws-") as state_dir:
            os.chmod(state_dir, 0o700)
            state_file = str(Path(state_dir) / "state")
            try:
                with io.StringIO() as stdout, io.StringIO() as stderr:
                    from contextlib import redirect_stderr, redirect_stdout

                    with redirect_stdout(stdout), redirect_stderr(stderr):
                        response = reader(
                            api_url=connection.api_url,
                            identity_url=connection.identity_url,
                            access_token=access_token,
                            organization_id=connection.organization_id,
                            project_id=project_id,
                            keys=keys,
                            state_file=state_file,
                        )
            except Exception:
                raise StoreError("Bitwarden environment retrieval failed") from None
    finally:
        close = getattr(adapter, "close", None)
        if callable(close):
            close()

    if not isinstance(response, dict) or set(response) != {
        "project_id",
        "organization_id",
        "entries",
    }:
        raise StoreError("Bitwarden adapter returned an invalid environment response")
    returned_project = _response_uuid(response["project_id"], "project")
    returned_organization = _response_uuid(response["organization_id"], "organization")
    if returned_organization != connection.organization_id:
        raise StoreError("Bitwarden adapter returned an environment outside the configured organization")
    if returned_project != project_id:
        raise StoreError("Bitwarden adapter returned an environment for a different project")
    entries = response["entries"]
    if not isinstance(entries, list):
        raise StoreError("Bitwarden adapter returned an invalid environment response")

    requested = set(keys)
    seen_ids: set[str] = set()
    values: dict[str, str] = {}
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {
            "id",
            "key",
            "value",
            "organization_id",
            "project_ids",
        }:
            raise StoreError("Bitwarden adapter returned an invalid environment entry")
        entry_id = _response_uuid(entry["id"], "secret")
        if entry_id in seen_ids:
            raise StoreError("Bitwarden adapter returned a duplicate entry ID")
        seen_ids.add(entry_id)
        key = entry["key"]
        if not isinstance(key, str):
            raise StoreError("Bitwarden adapter returned an invalid environment entry")
        if key in values:
            raise StoreError(f"Bitwarden adapter returned duplicate key {key}")
        if key not in requested:
            raise StoreError(f"Bitwarden adapter returned undeclared key {key}")
        organization_id = _response_uuid(entry["organization_id"], "organization")
        if organization_id != connection.organization_id:
            raise StoreError("Bitwarden adapter returned an entry outside the configured organization")
        project_ids = entry["project_ids"]
        if not isinstance(project_ids, list):
            raise StoreError("Bitwarden adapter returned an invalid environment entry")
        normalized_projects = {
            _response_uuid(value, "project") for value in project_ids
        }
        if project_id not in normalized_projects:
            raise StoreError("Bitwarden adapter returned an entry outside the selected project")
        value = entry["value"]
        if not isinstance(value, str):
            raise StoreError("Bitwarden adapter returned an invalid environment entry")
        if "\0" in value:
            raise StoreError(f"Bitwarden value for {key} contains NUL")
        values[key] = value

    missing = [key for key in keys if key not in values]
    if missing:
        raise StoreError("Bitwarden environment is missing declared key(s): " + ", ".join(missing))
    return {key: values[key] for key in keys}
