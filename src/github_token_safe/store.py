from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

STORE_PREFIX = "github-token-safe"


class StoreError(RuntimeError):
    pass


@dataclass(frozen=True)
class Profile:
    name: str
    scopes: tuple[str, ...] = ()
    note: str = ""

    @classmethod
    def from_dict(cls, name: str, value: dict[str, Any]) -> "Profile":
        return cls(name=name, scopes=tuple(value.get("scopes", ())), note=value.get("note", ""))

    def as_dict(self) -> dict[str, Any]:
        return {"scopes": list(self.scopes), "note": self.note}


class TokenStore:
    def __init__(self, config_dir: Path | None = None, pass_tool: str | None = None) -> None:
        base = config_dir or Path(
            os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")
        ) / STORE_PREFIX
        self.config_dir = Path(base)
        self.config_file = self.config_dir / "config.json"
        self.pass_tool = pass_tool or shutil.which("pass") or ""

    def require_backend(self) -> None:
        if not self.pass_tool:
            raise StoreError(
                "pass is required. Install the 'pass' package and initialize it with "
                "'pass init <gpg-key-id>'."
            )

    @property
    def backend(self) -> str:
        return self.pass_tool

    def load(self) -> dict[str, Any]:
        if not self.config_file.exists():
            return {"active": None, "profiles": {}}
        try:
            data = json.loads(self.config_file.read_text(encoding="utf-8"))
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
        flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
        fd = os.open(temporary, flags, 0o600)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(data, handle, indent=2, sort_keys=True)
                handle.write("\n")
            os.replace(temporary, self.config_file)
            os.chmod(self.config_file, stat.S_IRUSR | stat.S_IWUSR)
        finally:
            if temporary.exists():
                temporary.unlink()

    def profiles(self) -> list[Profile]:
        data = self.load()
        return [Profile.from_dict(name, value) for name, value in sorted(data["profiles"].items())]

    def active(self) -> str | None:
        return self.load()["active"]

    def put(self, profile: Profile, token: str, *, replace: bool = False) -> None:
        self.require_backend()
        data = self.load()
        if profile.name in data["profiles"] and not replace:
            raise StoreError(f"profile '{profile.name}' already exists; use --force to replace it")
        if not token or "\n" in token or "\r" in token:
            raise StoreError("token must be a non-empty single line")
        command = [self.pass_tool, "insert", "--force", "--multiline", self._entry(profile.name)]
        result = subprocess.run(
            command, input=f"{token}\n", text=True, capture_output=True, check=False
        )
        if result.returncode != 0:
            raise StoreError(self._backend_error("store", result))
        data["profiles"][profile.name] = profile.as_dict()
        if data["active"] is None:
            data["active"] = profile.name
        self.save(data)

    def get(self, name: str | None = None) -> str:
        self.require_backend()
        selected = name or self.active()
        if not selected:
            raise StoreError("no active profile; add or activate one first")
        data = self.load()
        if selected not in data["profiles"]:
            raise StoreError(f"unknown profile: {selected}")
        result = subprocess.run(
            [self.pass_tool, "show", self._entry(selected)],
            text=True,
            capture_output=True,
            check=False,
        )
        token = result.stdout.rstrip("\n")
        if result.returncode != 0 or not token:
            raise StoreError(self._backend_error(f"load profile '{selected}'", result))
        return token

    def activate(self, name: str) -> None:
        data = self.load()
        if name not in data["profiles"]:
            raise StoreError(f"unknown profile: {name}")
        data["active"] = name
        self.save(data)

    def remove(self, name: str) -> None:
        self.require_backend()
        data = self.load()
        if name not in data["profiles"]:
            raise StoreError(f"unknown profile: {name}")
        result = subprocess.run(
            [self.pass_tool, "rm", "--force", self._entry(name)],
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            raise StoreError(self._backend_error(f"remove profile '{name}'", result))
        del data["profiles"][name]
        if data["active"] == name:
            data["active"] = next(iter(sorted(data["profiles"])), None)
        self.save(data)

    @staticmethod
    def _backend_error(action: str, result: subprocess.CompletedProcess[str]) -> str:
        detail = result.stderr.strip() or "password-store returned no details"
        return f"cannot {action}: {detail}"

    @staticmethod
    def _entry(name: str) -> str:
        return f"{STORE_PREFIX}/{name}"
