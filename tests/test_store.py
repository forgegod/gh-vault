from __future__ import annotations

import json
import os
import stat
import subprocess
from pathlib import Path

import pytest

from gh_vault.store import Profile, StoreError, VaultStore


@pytest.fixture
def backend(tmp_path: Path) -> Path:
    script = tmp_path / "pass"
    script.write_text(
        """#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path

path = Path(os.environ["FAKE_SECRET_DB"])
password_store_dir = Path(os.environ["PASSWORD_STORE_DIR"])
assert path.parent == password_store_dir
data = json.loads(path.read_text()) if path.exists() else {}
command = sys.argv[1]
key = sys.argv[-1]
if command == "insert":
    data[key] = sys.stdin.read().rstrip("\\n")
    path.write_text(json.dumps(data))
elif command == "show":
    if key not in data:
        raise SystemExit(1)
    print(data[key])
elif command == "rm":
    if key not in data:
        raise SystemExit(1)
    del data[key]
    path.write_text(json.dumps(data))
else:
    raise SystemExit(2)
""",
        encoding="utf-8",
    )
    script.chmod(0o755)
    return script


@pytest.fixture
def store(tmp_path: Path, backend: Path, monkeypatch: pytest.MonkeyPatch) -> VaultStore:
    password_store_dir = tmp_path / "password-store"
    password_store_dir.mkdir()
    monkeypatch.setenv("FAKE_SECRET_DB", str(password_store_dir / "secrets.json"))
    return VaultStore(
        config_dir=tmp_path / "config",
        pass_tool=str(backend),
        password_store_dir=password_store_dir,
    )


def test_add_select_get_and_remove(store: VaultStore) -> None:
    store.put(Profile("repo-read", ("contents:read",), "read only"), "github_pat_read")
    store.put(Profile("release", ("contents:write",)), "github_pat_write")

    assert store.active() == "repo-read"
    assert store.get() == "github_pat_read"
    store.activate("release")
    assert store.get() == "github_pat_write"

    store.remove("release")
    assert store.active() is None
    assert [profile.name for profile in store.profiles()] == ["repo-read"]


def test_config_permissions_are_restrictive(store: VaultStore) -> None:
    store.put(Profile("default"), "github_pat_value")

    assert stat.S_IMODE(store.config_dir.stat().st_mode) == 0o700
    assert stat.S_IMODE(store.config_file.stat().st_mode) == 0o600
    config = json.loads(store.config_file.read_text(encoding="utf-8"))
    assert "github_pat_value" not in json.dumps(config)


def test_default_password_store_is_in_the_user_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    monkeypatch.delenv("PASSWORD_STORE_DIR", raising=False)

    store = VaultStore(config_dir=tmp_path / "config", pass_tool="pass")

    assert store.password_store_dir == tmp_path / "home" / ".password-store"


def test_replace_requires_force(store: VaultStore) -> None:
    store.put(Profile("default"), "old")
    with pytest.raises(StoreError, match="already exists"):
        store.put(Profile("default"), "new")

    store.put(Profile("default", note="new profile"), "new", replace=True)
    assert store.get("default") == "new"
    assert store.profiles()[0].note == "new profile"


def test_missing_backend_has_actionable_error(tmp_path: Path) -> None:
    store = VaultStore(config_dir=tmp_path, pass_tool="")
    store.pass_tool = ""
    with pytest.raises(StoreError, match="pass is required"):
        store.require_backend()


def test_rejects_multiline_tokens(store: VaultStore) -> None:
    with pytest.raises(StoreError, match="single line"):
        store.put(Profile("bad"), "first\nsecond")


def test_missing_secret_is_reported(store: VaultStore) -> None:
    store.put(Profile("missing"), "value")
    secret_db = Path(os.environ["FAKE_SECRET_DB"])
    secret_db.write_text("{}", encoding="utf-8")

    with pytest.raises(StoreError, match="load profile"):
        store.get("missing")
