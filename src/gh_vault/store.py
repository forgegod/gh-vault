from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

STORE_PREFIX = "gh-vault"
LEGACY_STORE_PREFIX = "github-token-safe"


class StoreError(RuntimeError):
    pass


@dataclass(frozen=True)
class Profile:
    name: str
    scopes: tuple[str, ...] = ()
    note: str = ""

    @classmethod
    def from_dict(cls, name: str, value: dict[str, Any]) -> "Profile":
        return cls(name, tuple(value.get("scopes", ())), value.get("note", ""))

    def as_dict(self) -> dict[str, Any]:
        return {"scopes": list(self.scopes), "note": self.note}


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
        self.config_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.config_dir, 0o700)
        temporary = self.config_file.with_suffix(".tmp")
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                os.fchmod(handle.fileno(), 0o600)
                json.dump(data, handle, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.config_file)
        finally:
            if temporary.exists():
                temporary.unlink()

    def profiles(self) -> list[Profile]:
        return [Profile.from_dict(name, value) for name, value in sorted(self.load()["profiles"].items())]

    def active(self) -> str | None:
        return self.load()["active"]

    def put(self, profile: Profile, token: str, *, replace: bool = False) -> None:
        data = self.load()
        if profile.name in data["profiles"] and not replace:
            raise StoreError(f"profile '{profile.name}' already exists; use --force to replace it")
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
            raise StoreError("no active profile; add or activate one first")
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

    def migrate_legacy(self) -> int:
        legacy_config = self.config_dir.parent / LEGACY_STORE_PREFIX / "config.json"
        try:
            legacy = json.loads(legacy_config.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise StoreError(f"legacy metadata not found: {legacy_config}") from exc
        if self.load()["profiles"]:
            raise StoreError("current vault already has profiles; migrate into an empty vault")
        profiles = legacy.get("profiles")
        if not isinstance(profiles, dict):
            raise StoreError(f"invalid legacy config file: {legacy_config}")
        for name, metadata in profiles.items():
            token = self._run(["show", f"{LEGACY_STORE_PREFIX}/{name}"], None, f"load legacy '{name}'").rstrip("\n")
            if not token:
                raise StoreError(f"legacy profile '{name}' has no token")
            self.put_secret(name, token)
        data = {"active": legacy.get("active"), "profiles": profiles}
        self.save(data)
        return len(profiles)

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


TokenStore = VaultStore
