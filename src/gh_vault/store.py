from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

STORE_PREFIX = "gh-vault"
ENVIRONMENT_INDEX_VERSION = 1
VARIABLE_PAYLOAD_VERSION = 1
PROFILE_NAME = re.compile(r"^(?:default|[A-Za-z0-9][A-Za-z0-9._-]{0,63})$")
NAMESPACE_PART = re.compile(r"^[A-Za-z0-9._-]+$")



class StoreError(RuntimeError):
    pass


@dataclass(frozen=True)
class Profile:
    name: str
    scopes: tuple[str, ...] = ()
    note: str = ""
    expires_at: str | None = None

    @classmethod
    def from_dict(cls, name: str, value: dict[str, Any]) -> "Profile":
        expires_at = value.get("expires_at")
        return cls(name, tuple(value.get("scopes", ())), value.get("note", ""), expires_at if isinstance(expires_at, str) else None)

    def as_dict(self) -> dict[str, Any]:
        return {"scopes": list(self.scopes), "note": self.note, "expires_at": self.expires_at}


class VaultStore:
    def __init__(self, config_dir: Path | None = None, pass_tool: str | None = None, password_store_dir: Path | None = None) -> None:
        base = config_dir or Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / STORE_PREFIX
        self.config_dir = Path(base)
        self.config_file = self.config_dir / "config.json"
        self.pass_tool = pass_tool or shutil.which("pass") or ""
        self.password_store_dir = Path(password_store_dir or os.environ.get("PASSWORD_STORE_DIR", Path.home() / ".password-store")).expanduser()

    def require_backend(self) -> None:
        if not self.pass_tool:
            raise StoreError("pass is required. Install the 'pass' package and initialize it with 'pass init <gpg-key-id>'.")

    @property
    def backend(self) -> str:
        return self.pass_tool

    def load(self) -> dict[str, Any]:
        try:
            data = json.loads(self.config_file.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {"active": None, "profiles": {}}
        except (OSError, json.JSONDecodeError) as exc:
            raise StoreError(f"cannot read {self.config_file}: {exc}") from exc
        if not isinstance(data.get("profiles"), dict):
            raise StoreError(f"invalid config file: {self.config_file}")
        data.setdefault("active", None)
        return data

    def save(self, data: dict[str, Any]) -> None:
        _write_restrictive_json(self.config_dir, self.config_file, data)

    def profiles(self) -> list[Profile]:
        return [Profile.from_dict(name, value) for name, value in sorted(self.load()["profiles"].items())]

    def active(self) -> str | None:
        return self.load()["active"]

    def put(self, profile: Profile, token: str, *, replace: bool = False) -> None:
        data = self.load()
        if profile.name in data["profiles"] and not replace:
            raise StoreError(f"profile '{profile.name}' already exists")
        if not token or "\n" in token or "\r" in token:
            raise StoreError("token must be a non-empty single line")
        self.put_secret(profile.name, token)
        data["profiles"][profile.name] = profile.as_dict()
        if data["active"] is None:
            data["active"] = profile.name
        self.save(data)

    def get(self, name: str | None = None) -> str:
        selected = name or self.active()
        if not selected:
            raise StoreError("no active profile; set or activate one first")
        if selected not in self.load()["profiles"]:
            raise StoreError(f"unknown profile: {selected}")
        try:
            return self.get_secret(selected)
        except StoreError as exc:
            raise StoreError(str(exc).replace(f"load '{selected}'", f"load profile '{selected}'")) from exc

    def activate(self, name: str) -> None:
        data = self.load()
        if name not in data["profiles"]:
            raise StoreError(f"unknown profile: {name}")
        data["active"] = name
        self.save(data)

    def remove(self, name: str) -> None:
        data = self.load()
        if name not in data["profiles"]:
            raise StoreError(f"unknown profile: {name}")
        self.remove_secret(name)
        del data["profiles"][name]
        if data["active"] == name:
            data["active"] = None
        self.save(data)

    def put_secret(self, name: str, value: str) -> None:
        self._run(["insert", "--force", "--multiline", self._entry(name)], value + "\n", "store")

    def get_secret(self, name: str) -> str:
        return self._run(["show", self._entry(name)], None, f"load '{name}'").rstrip("\n")

    def remove_secret(self, name: str) -> None:
        self._run(["rm", "--force", self._entry(name)], None, f"remove '{name}'")


    def _run(self, args: list[str], input_value: str | None, action: str) -> str:
        self.require_backend()
        result = subprocess.run([self.pass_tool, *args], input=input_value, text=True, capture_output=True, check=False, env=self._backend_environment())
        if result.returncode != 0:
            raise StoreError(f"cannot {action}: {result.stderr.strip() or 'password-store returned no details'}")
        return result.stdout

    @staticmethod
    def _entry(name: str) -> str:
        if name.startswith("/") or ".." in name.split("/"):
            raise StoreError("invalid vault entry name")
        return f"{STORE_PREFIX}/{name}"

    def _backend_environment(self) -> dict[str, str]:
        environment = os.environ.copy()
        environment["PASSWORD_STORE_DIR"] = str(self.password_store_dir)
        return environment


class EnvironmentStore:
    def __init__(self, config_dir: Path | None = None) -> None:
        self.config_dir = Path(config_dir or Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / STORE_PREFIX)
        self.root = self.config_dir / "environments"

    def load_variables(self, namespace: str, profile: str, origin: str) -> dict[str, str]:
        self._require_origin(origin)
        path = self._variables_path(namespace, profile)
        data = self._load_json(path, "environment variable payload")
        if data is None:
            return {}
        values = data.get("values")
        if set(data) != {"version", "origin", "values"} or data.get("version") != VARIABLE_PAYLOAD_VERSION or data.get("origin") != origin:
            raise StoreError("environment variable payload does not match this origin or format")
        if not isinstance(values, dict) or not all(isinstance(key, str) and isinstance(value, str) for key, value in values.items()):
            raise StoreError("environment variable payload has invalid data")
        return values

    def save_variables(self, namespace: str, profile: str, origin: str, values: dict[str, str]) -> None:
        self._require_origin(origin)
        if not all(isinstance(key, str) and isinstance(value, str) for key, value in values.items()):
            raise StoreError("environment variable payload has invalid data")
        path = self._variables_path(namespace, profile)
        _write_restrictive_json(self.config_dir, path, {"version": VARIABLE_PAYLOAD_VERSION, "origin": origin, "values": values})

    def remove_variables(self, namespace: str, profile: str) -> None:
        path = self._variables_path(namespace, profile)
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        except OSError as exc:
            raise StoreError(f"cannot remove {path}: {exc}") from exc

    def load_manifest(self, namespace: str, origin: str) -> dict[str, Any]:
        self._require_origin(origin)
        path = self._namespace_dir(namespace) / "environments.json"
        data = self._load_json(path, "environment index")
        if data is None:
            return {"version": ENVIRONMENT_INDEX_VERSION, "origin": origin, "environments": {}}
        environments = data.get("environments")
        if set(data) != {"version", "origin", "environments"} or data.get("version") != ENVIRONMENT_INDEX_VERSION or data.get("origin") != origin:
            raise StoreError("environment index does not match this origin or format")
        if not isinstance(environments, dict) or not all(self._valid_profile(profile) and self._valid_details(details) for profile, details in environments.items()):
            raise StoreError("environment index has invalid data")
        return data

    def save_manifest(self, namespace: str, origin: str, environments: dict[str, dict[str, bool]]) -> None:
        self._require_origin(origin)
        if not all(self._valid_profile(profile) and self._valid_details(details) for profile, details in environments.items()):
            raise StoreError("environment index has invalid data")
        path = self._namespace_dir(namespace) / "environments.json"
        _write_restrictive_json(self.config_dir, path, {"version": ENVIRONMENT_INDEX_VERSION, "origin": origin, "environments": environments})

    def _variables_path(self, namespace: str, profile: str) -> Path:
        self._require_profile(profile)
        name = "env.variables.json" if profile == "default" else f"env.{profile}.variables.json"
        return self._namespace_dir(namespace) / name

    def _namespace_dir(self, namespace: str) -> Path:
        parts = namespace.split("/")
        if not parts or any(not part or part in {".", ".."} or not NAMESPACE_PART.fullmatch(part) for part in parts):
            raise StoreError("invalid environment namespace")
        return self.root.joinpath(*parts)

    @staticmethod
    def _valid_profile(profile: object) -> bool:
        return isinstance(profile, str) and PROFILE_NAME.fullmatch(profile) is not None

    @classmethod
    def _require_profile(cls, profile: str) -> None:
        if not cls._valid_profile(profile):
            raise StoreError("invalid environment profile")

    @staticmethod
    def _require_origin(origin: str) -> None:
        if not isinstance(origin, str) or not origin:
            raise StoreError("invalid environment origin")

    @staticmethod
    def _valid_details(details: object) -> bool:
        return isinstance(details, dict) and set(details) == {"variables", "secrets", "example"} and all(isinstance(value, bool) for value in details.values())

    @staticmethod
    def _load_json(path: Path, label: str) -> dict[str, Any] | None:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except (OSError, json.JSONDecodeError) as exc:
            raise StoreError(f"cannot read {label} {path}: {exc}") from exc
        if not isinstance(data, dict):
            raise StoreError(f"{label} has invalid data")
        return data


def _write_restrictive_json(config_dir: Path, path: Path, data: dict[str, Any]) -> None:
    config_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(config_dir, 0o700)
    current = config_dir
    for part in path.parent.relative_to(config_dir).parts:
        current /= part
        current.mkdir(exist_ok=True, mode=0o700)
        os.chmod(current, 0o700)
    temporary = path.with_suffix(path.suffix + ".tmp")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            os.fchmod(handle.fileno(), 0o600)
            json.dump(data, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


TokenStore = VaultStore
