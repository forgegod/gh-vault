from __future__ import annotations

import json
import os
import stat
import subprocess
from pathlib import Path

import pytest

from gh_vault.store import EnvironmentStore, Profile, StoreError, VaultStore


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
    store.put(Profile("repo-read", ("contents:read",), "read only", "2026-12-31 23:59:59 UTC"), "github_pat_read")
    store.put(Profile("release", ("contents:write",)), "github_pat_write")

    assert store.active() == "repo-read"
    assert store.get() == "github_pat_read"
    assert next(profile for profile in store.profiles() if profile.name == "repo-read").expires_at == "2026-12-31 23:59:59 UTC"
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


def test_environment_store_separates_variable_payload_and_manifest(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    store = EnvironmentStore(config_dir)
    namespace = "github.com/owner/repo"
    origin = "git@github.com:owner/repo.git"
    details = {"default": {"variables": True, "secrets": False, "example": False}}

    store.save_variables(namespace, "default", origin, {"REGION": "eu-test-1"})
    store.save_manifest(namespace, origin, details)

    project_dir = config_dir / "environments" / "github.com" / "owner" / "repo"
    payload_path = project_dir / "env.variables.json"
    manifest_path = project_dir / "environments.json"
    assert store.load_variables(namespace, "default", origin) == {"REGION": "eu-test-1"}
    assert store.load_manifest(namespace, origin)["environments"] == details
    assert json.loads(payload_path.read_text(encoding="utf-8")) == {
        "origin": origin,
        "values": {"REGION": "eu-test-1"},
        "version": 1,
    }
    assert "eu-test-1" not in manifest_path.read_text(encoding="utf-8")
    assert stat.S_IMODE(payload_path.stat().st_mode) == 0o600
    assert stat.S_IMODE(manifest_path.stat().st_mode) == 0o600
    for path in (config_dir, config_dir / "environments", config_dir / "environments" / "github.com", config_dir / "environments" / "github.com" / "owner", project_dir):
        assert stat.S_IMODE(path.stat().st_mode) == 0o700


def test_environment_store_validates_payload_origin_and_data(tmp_path: Path) -> None:
    store = EnvironmentStore(tmp_path / "config")
    namespace = "github.com/owner/repo"
    origin = "git@github.com:owner/repo.git"
    store.save_variables(namespace, "production", origin, {"REGION": "eu-test-1"})
    payload_path = store.root / "github.com" / "owner" / "repo" / "env.production.variables.json"

    with pytest.raises(StoreError, match="does not match this origin"):
        store.load_variables(namespace, "production", "git@github.com:other/repo.git")

    payload_path.write_text('{"version":1,"origin":"git@github.com:owner/repo.git","values":{"REGION":42}}', encoding="utf-8")
    with pytest.raises(StoreError, match="invalid data"):
        store.load_variables(namespace, "production", origin)

    payload_path.write_text("not-json", encoding="utf-8")
    with pytest.raises(StoreError, match="cannot read environment variable payload"):
        store.load_variables(namespace, "production", origin)


def test_environment_store_rejects_invalid_paths_and_manifest_details(tmp_path: Path) -> None:
    store = EnvironmentStore(tmp_path / "config")
    origin = "git@github.com:owner/repo.git"

    with pytest.raises(StoreError, match="invalid environment namespace"):
        store.save_variables("github.com/../repo", "default", origin, {})
    with pytest.raises(StoreError, match="invalid environment profile"):
        store.save_variables("github.com/owner/repo", "../production", origin, {})
    with pytest.raises(StoreError, match="invalid environment origin"):
        store.save_variables("github.com/owner/repo", "default", "", {})
    with pytest.raises(StoreError, match="environment index has invalid data"):
        store.save_manifest("github.com/owner/repo", origin, {"default": {"variables": True}})


def test_environment_store_removes_only_the_selected_payload(tmp_path: Path) -> None:
    store = EnvironmentStore(tmp_path / "config")
    namespace = "github.com/owner/repo"
    origin = "git@github.com:owner/repo.git"
    store.save_variables(namespace, "default", origin, {"REGION": "default"})
    store.save_variables(namespace, "production", origin, {"REGION": "production"})

    store.remove_variables(namespace, "default")

    assert store.load_variables(namespace, "default", origin) == {}
    assert store.load_variables(namespace, "production", origin) == {"REGION": "production"}


def test_environment_store_uses_the_xdg_config_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))

    store = EnvironmentStore()

    assert store.root == tmp_path / "xdg" / "gh-vault" / "environments"


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
