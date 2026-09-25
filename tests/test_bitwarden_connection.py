from __future__ import annotations

import argparse
import io
import json
import os
import sys
from pathlib import Path

import pytest

from gh_vault import bitwarden, cli
from gh_vault.store import BitwardenConnection, StoreError

ORGANIZATION_ID = "11111111-1111-4111-8111-111111111111"
PROJECT_ID = "22222222-2222-4222-8222-22222222abcd"
ACCESS_TOKEN = "synthetic-bws-access-token"


class MemoryStore:
    def __init__(self) -> None:
        self.connections: dict[str, BitwardenConnection] = {}
        self.credentials: dict[str, str] = {}

    def put_bitwarden_connection(self, connection: BitwardenConnection) -> None:
        self.connections[connection.name] = connection

    def bitwarden_connections(self) -> list[BitwardenConnection]:
        return [self.connections[name] for name in sorted(self.connections)]

    def get_bitwarden_connection(self, name: str) -> BitwardenConnection:
        try:
            return self.connections[name]
        except KeyError as exc:
            raise StoreError(f"unknown Bitwarden connection: {name}") from exc

    def put_bitwarden_credential(self, name: str, token: str) -> None:
        self.get_bitwarden_connection(name)
        self.credentials[name] = token

    def get_bitwarden_credential(self, name: str) -> str:
        self.get_bitwarden_connection(name)
        try:
            return self.credentials[name]
        except KeyError as exc:
            raise StoreError(f"Bitwarden credential is not configured for connection '{name}'") from exc

    def remove_bitwarden_credential(self, name: str) -> None:
        self.get_bitwarden_connection(name)
        self.credentials.pop(name, None)


def connection(tmp_path: Path, name: str = "eu-production") -> BitwardenConnection:
    return BitwardenConnection(
        name=name,
        bws_config=str(tmp_path / "bws-config"),
        bws_profile="eu",
        api_url="https://api.bitwarden.eu",
        identity_url="https://identity.bitwarden.eu",
        organization_id=ORGANIZATION_ID,
    )


def write_bws_config(path: Path, body: str) -> Path:
    path.write_text(body, encoding="utf-8")
    return path


def write_adapter(path: Path, body: str) -> Path:
    package = path / "gh_vault_bws"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text(body, encoding="utf-8")
    return path


def test_load_bws_endpoints_resolves_base_and_explicit_overrides(tmp_path: Path) -> None:
    config_path = write_bws_config(
        tmp_path / "config",
        """
[profiles.base]
server_base = "https://vault.example.test/"

[profiles.explicit]
server_base = "https://ignored.example.test"
server_api = "https://api.example.test/"
server_identity = "https://identity.example.test/"
""".strip(),
    )

    assert bitwarden.load_bws_endpoints(config_path, "base") == bitwarden.BitwardenEndpoints(
        "https://vault.example.test/api", "https://vault.example.test/identity"
    )
    assert bitwarden.load_bws_endpoints(config_path, "explicit") == bitwarden.BitwardenEndpoints(
        "https://api.example.test", "https://identity.example.test"
    )


@pytest.mark.parametrize(
    ("body", "profile", "match"),
    [
        ("[profiles.other]\nserver_base='https://example.test'\n", "missing", "does not contain profile"),
        ("[profiles.eu]\nserver_base='http://example.test'\n", "eu", "HTTPS"),
        ("[profiles.eu]\nserver_api='https://api.example.test'\n", "eu", "identity endpoint"),
        ("[profiles.eu]\nserver_base='https://user:password@example.test'\n", "eu", "credentials"),
    ],
)
def test_load_bws_endpoints_rejects_unsafe_or_incomplete_profiles(
    tmp_path: Path, body: str, profile: str, match: str
) -> None:
    config_path = write_bws_config(tmp_path / "config", body)

    with pytest.raises(StoreError, match=match):
        bitwarden.load_bws_endpoints(config_path, profile)


def test_assert_connection_current_refuses_endpoint_drift(tmp_path: Path) -> None:
    config_path = write_bws_config(
        tmp_path / "config",
        "[profiles.eu]\nserver_api='https://api.bitwarden.eu'\nserver_identity='https://identity.bitwarden.eu'\n",
    )
    selected = BitwardenConnection(
        "eu-production",
        str(config_path),
        "eu",
        "https://api.bitwarden.eu",
        "https://identity.bitwarden.eu",
        ORGANIZATION_ID,
    )
    bitwarden.assert_connection_current(selected)

    config_path.write_text(
        "[profiles.eu]\nserver_api='https://api.bitwarden.com'\nserver_identity='https://identity.bitwarden.com'\n",
        encoding="utf-8",
    )
    with pytest.raises(StoreError, match="endpoint configuration changed"):
        bitwarden.assert_connection_current(selected)


def test_canonical_uuid_rejects_noncanonical_and_nil_values() -> None:
    assert bitwarden.canonical_uuid(PROJECT_ID, "project") == PROJECT_ID
    with pytest.raises(argparse.ArgumentTypeError, match="canonical UUID"):
        bitwarden.canonical_uuid(PROJECT_ID.upper(), "project")
    with pytest.raises(argparse.ArgumentTypeError, match="non-nil"):
        bitwarden.canonical_uuid("00000000-0000-0000-0000-000000000000", "project")


def test_load_local_adapter_uses_only_the_selected_path_and_suppresses_output(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    adapter_path = write_adapter(
        tmp_path / "adapter",
        """
print("unexpected import output")
GH_VAULT_ADAPTER_API = 1

def resolve_project(**request):
    print("unexpected call output")
    return {
        "project_id": request["project_id"],
        "organization_id": request["organization_id"],
    }
""".strip(),
    )
    original_path = list(sys.path)

    adapter = bitwarden.load_local_adapter(adapter_path)
    selected = connection(tmp_path)
    result = bitwarden.resolve_project(adapter, selected, ACCESS_TOKEN, PROJECT_ID)

    assert result == bitwarden.BitwardenProject(PROJECT_ID, ORGANIZATION_ID)
    assert sys.path == original_path
    assert "gh_vault_bws" not in sys.modules
    assert capsys.readouterr() == ("", "")


def test_load_local_adapter_rejects_missing_or_incompatible_packages(tmp_path: Path) -> None:
    with pytest.raises(StoreError, match="local adapter path"):
        bitwarden.load_local_adapter(tmp_path / "missing")

    adapter_path = write_adapter(
        tmp_path / "adapter",
        "GH_VAULT_ADAPTER_API = 2\ndef resolve_project(**request): return None\n",
    )
    with pytest.raises(StoreError, match="API version"):
        bitwarden.load_local_adapter(adapter_path)


def test_resolve_project_passes_only_explicit_connection_and_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    selected = connection(tmp_path)
    observed: dict[str, object] = {}

    def adapter(**request):
        observed.update(request)
        return {"project_id": PROJECT_ID, "organization_id": ORGANIZATION_ID}

    monkeypatch.setattr(bitwarden.tempfile, "tempdir", tmp_path)
    before_argv = list(sys.argv)
    result = bitwarden.resolve_project(adapter, selected, ACCESS_TOKEN, PROJECT_ID)

    assert result == bitwarden.BitwardenProject(PROJECT_ID, ORGANIZATION_ID)
    assert observed == {
        "api_url": selected.api_url,
        "identity_url": selected.identity_url,
        "access_token": ACCESS_TOKEN,
        "organization_id": ORGANIZATION_ID,
        "project_id": PROJECT_ID,
        "state_file": observed["state_file"],
    }
    assert isinstance(observed["state_file"], str)
    assert not Path(str(observed["state_file"])).exists()
    assert sys.argv == before_argv


@pytest.mark.parametrize(
    ("result", "match"),
    [
        (None, "not accessible"),
        ({"project_id": PROJECT_ID, "organization_id": "33333333-3333-4333-8333-333333333333"}, "outside the configured organization"),
        ({"project_id": "33333333-3333-4333-8333-333333333333", "organization_id": ORGANIZATION_ID}, "different project"),
        ({"project_id": PROJECT_ID, "organization_id": ORGANIZATION_ID, "name": "metadata"}, "invalid response"),
    ],
)
def test_resolve_project_rejects_inaccessible_or_mismatched_results(
    tmp_path: Path, result: object, match: str
) -> None:
    def adapter(**request):
        return result

    with pytest.raises(StoreError, match=match):
        bitwarden.resolve_project(adapter, connection(tmp_path), ACCESS_TOKEN, PROJECT_ID)


def test_resolve_project_discards_adapter_exception_text(tmp_path: Path) -> None:
    leaked = "synthetic-sensitive-adapter-error"

    def adapter(**request):
        raise RuntimeError(leaked)

    with pytest.raises(StoreError, match="Bitwarden project resolution failed") as caught:
        bitwarden.resolve_project(adapter, connection(tmp_path), ACCESS_TOKEN, PROJECT_ID)

    assert leaked not in str(caught.value)
    assert caught.value.__cause__ is None


def test_project_resolve_uses_explicit_env_credential_without_github_inspection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    store = MemoryStore()
    selected = connection(tmp_path)
    store.put_bitwarden_connection(selected)
    args = cli.build_parser().parse_args(
        [
            "bitwarden",
            "project",
            "resolve",
            "--connection",
            selected.name,
            "--project-id",
            PROJECT_ID,
            "--adapter-path",
            str(tmp_path / "adapter"),
        ]
    )
    observed: dict[str, object] = {}
    sentinel = object()

    def adapter(**request):
        observed.update(request)
        return {"project_id": PROJECT_ID, "organization_id": ORGANIZATION_ID}

    monkeypatch.setenv("BWS_ACCESS_TOKEN", ACCESS_TOKEN)
    monkeypatch.setattr(cli, "project_namespace", lambda directory: ("github.com/owner/repo", "git@github.com:owner/repo.git"))
    monkeypatch.setattr(cli, "assert_connection_current", lambda current: None)
    monkeypatch.setattr(cli, "load_local_adapter", lambda path: adapter)
    monkeypatch.setattr(cli, "inspect_token", lambda token: pytest.fail("GitHub token inspection must not run"))
    before_environment = os.environ.copy()

    assert cli.dispatch(args, store, tmp_path) == 0  # type: ignore[arg-type]

    assert observed["access_token"] == ACCESS_TOKEN
    assert observed["project_id"] == PROJECT_ID
    assert observed.get("unrequested_project", sentinel) is sentinel
    assert os.environ == before_environment
    output = capsys.readouterr().out
    assert output == f"Resolved Bitwarden project {PROJECT_ID} for connection {selected.name}.\n"
    assert ACCESS_TOKEN not in output


def test_project_resolve_uses_only_the_selected_vault_credential(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = MemoryStore()
    selected = connection(tmp_path)
    store.put_bitwarden_connection(selected)
    store.put_bitwarden_credential(selected.name, "vault-selected-token")
    args = cli.build_parser().parse_args(
        [
            "bitwarden",
            "project",
            "resolve",
            "--connection",
            selected.name,
            "--project-id",
            PROJECT_ID,
            "--adapter-path",
            str(tmp_path / "adapter"),
            "--credential-source",
            "vault",
        ]
    )
    observed: dict[str, object] = {}

    def adapter(**request):
        observed.update(request)
        return {"project_id": PROJECT_ID, "organization_id": ORGANIZATION_ID}

    monkeypatch.setenv("BWS_ACCESS_TOKEN", "ambient-token-must-not-win")
    monkeypatch.setattr(cli, "project_namespace", lambda directory: ("github.com/owner/repo", "https://github.com/owner/renamed.git"))
    monkeypatch.setattr(cli, "assert_connection_current", lambda current: None)
    monkeypatch.setattr(cli, "load_local_adapter", lambda path: adapter)

    assert cli.dispatch(args, store, tmp_path) == 0  # type: ignore[arg-type]
    assert observed["access_token"] == "vault-selected-token"


def test_project_resolve_rejects_bws_overrides_before_credential_access(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = MemoryStore()
    selected = connection(tmp_path)
    store.put_bitwarden_connection(selected)
    args = cli.build_parser().parse_args(
        [
            "bitwarden",
            "project",
            "resolve",
            "--connection",
            selected.name,
            "--project-id",
            PROJECT_ID,
            "--adapter-path",
            str(tmp_path / "adapter"),
            "--credential-source",
            "vault",
        ]
    )
    monkeypatch.setenv("BWS_SERVER_URL", "https://conflict.example.test")
    monkeypatch.setattr(cli, "project_namespace", lambda directory: ("github.com/owner/repo", "git@github.com:owner/repo.git"))
    monkeypatch.setattr(cli, "assert_connection_current", lambda current: None)
    monkeypatch.setattr(cli, "load_local_adapter", lambda path: pytest.fail("adapter must not load"))
    monkeypatch.setattr(store, "get_bitwarden_credential", lambda name: pytest.fail("credential must not be read"))

    with pytest.raises(StoreError, match="conflicting bws environment override"):
        cli.dispatch(args, store, tmp_path)  # type: ignore[arg-type]


def test_project_resolve_requires_nonempty_selected_credential(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = MemoryStore()
    selected = connection(tmp_path)
    store.put_bitwarden_connection(selected)
    args = cli.build_parser().parse_args(
        [
            "bitwarden",
            "project",
            "resolve",
            "--connection",
            selected.name,
            "--project-id",
            PROJECT_ID,
            "--adapter-path",
            str(tmp_path / "adapter"),
        ]
    )
    monkeypatch.delenv("BWS_ACCESS_TOKEN", raising=False)
    monkeypatch.setattr(cli, "project_namespace", lambda directory: ("github.com/owner/repo", "git@github.com:owner/repo.git"))
    monkeypatch.setattr(cli, "assert_connection_current", lambda current: None)
    monkeypatch.setattr(cli, "load_local_adapter", lambda path: lambda **request: None)

    with pytest.raises(StoreError, match="BWS_ACCESS_TOKEN"):
        cli.dispatch(args, store, tmp_path)  # type: ignore[arg-type]


def test_connection_and_credential_commands_keep_tokens_out_of_metadata_and_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    store = MemoryStore()
    config_path = tmp_path / "bws-config"
    set_connection = cli.build_parser().parse_args(
        [
            "bitwarden",
            "connection",
            "set",
            "eu-production",
            "--bws-profile",
            "eu",
            "--bws-config",
            str(config_path),
            "--organization-id",
            ORGANIZATION_ID,
        ]
    )
    monkeypatch.setattr(
        cli,
        "load_bws_endpoints",
        lambda path, profile: bitwarden.BitwardenEndpoints(
            "https://api.bitwarden.eu", "https://identity.bitwarden.eu"
        ),
    )

    assert cli.dispatch(set_connection, store, tmp_path) == 0  # type: ignore[arg-type]
    assert store.connections["eu-production"].bws_config == str(config_path.resolve())

    monkeypatch.setattr("sys.stdin", io.StringIO(ACCESS_TOKEN))
    set_credential = cli.build_parser().parse_args(
        ["bitwarden", "credential", "set", "eu-production", "--stdin"]
    )
    assert cli.dispatch(set_credential, store, tmp_path) == 0  # type: ignore[arg-type]

    listed = cli.build_parser().parse_args(["bitwarden", "connection", "list"])
    assert cli.dispatch(listed, store, tmp_path) == 0  # type: ignore[arg-type]
    output = capsys.readouterr().out
    assert "eu-production" in output
    assert ORGANIZATION_ID in output
    assert ACCESS_TOKEN not in output
    assert ACCESS_TOKEN not in json.dumps(
        {name: item.as_dict() for name, item in store.connections.items()}
    )
