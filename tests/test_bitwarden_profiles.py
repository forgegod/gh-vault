from __future__ import annotations

import json
from pathlib import Path

import pytest

from gh_vault import bitwarden, cli
from gh_vault.github import TokenMetadata
from gh_vault.store import BitwardenConnection, BitwardenProfileBinding, Profile, StoreError, VaultStore

ORGANIZATION_ID = "11111111-1111-4111-8111-111111111111"
PROJECT_ID = "22222222-2222-4222-8222-222222222222"
ENTRY_ID = "33333333-3333-4333-8333-333333333333"
TOKEN = "gho_" + "a" * 36


def binding() -> BitwardenProfileBinding:
    return BitwardenProfileBinding(
        connection="eu-production",
        project_id=PROJECT_ID,
        entry_id=ENTRY_ID,
        key="GITHUB_TOKEN",
        credential_source="env",
        adapter_path="/synthetic/gh-vault-bws",
    )


def connection() -> BitwardenConnection:
    return BitwardenConnection(
        name="eu-production",
        bws_config="/synthetic/bws/config",
        bws_profile="eu",
        api_url="https://api.bitwarden.eu",
        identity_url="https://identity.bitwarden.eu",
        organization_id=ORGANIZATION_ID,
    )


class BoundStore:
    def get_bitwarden_connection(self, name: str) -> BitwardenConnection:
        assert name == "eu-production"
        return connection()

    def get_bitwarden_credential(self, name: str) -> str:
        raise AssertionError("environment credential source must not read pass")


class Adapter:
    def __init__(self, entry_id: str = ENTRY_ID, key: str = "GITHUB_TOKEN") -> None:
        self.entry_id = entry_id
        self.key = key
        self.request: dict[str, object] | None = None
        self.closed = False

    def read_environment(self, **request: object) -> object:
        self.request = request
        return {
            "project_id": PROJECT_ID,
            "organization_id": ORGANIZATION_ID,
            "entries": [
                {
                    "id": self.entry_id,
                    "key": self.key,
                    "value": TOKEN,
                    "organization_id": ORGANIZATION_ID,
                    "project_ids": [PROJECT_ID],
                }
            ],
        }

    def close(self) -> None:
        self.closed = True


def test_bitwarden_profile_resolution_reads_and_validates_the_exact_bound_entry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = Adapter()
    monkeypatch.setenv("BWS_ACCESS_TOKEN", "synthetic-bws-access-token")
    monkeypatch.setattr(bitwarden, "assert_connection_current", lambda selected: None)
    monkeypatch.setattr(bitwarden, "load_local_adapter", lambda path, required_operations: adapter)

    assert bitwarden.resolve_bound_profile_token(BoundStore(), binding()) == TOKEN  # type: ignore[arg-type]
    assert adapter.closed is True
    request = adapter.request
    assert request is not None
    assert request == {
        "api_url": "https://api.bitwarden.eu",
        "identity_url": "https://identity.bitwarden.eu",
        "access_token": "synthetic-bws-access-token",
        "organization_id": ORGANIZATION_ID,
        "project_id": PROJECT_ID,
        "keys": ("GITHUB_TOKEN",),
        "state_file": request["state_file"],
    }
    assert isinstance(request["state_file"], str)


def test_bitwarden_profile_resolution_rejects_an_entry_id_change(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = Adapter("44444444-4444-4444-8444-444444444444")
    monkeypatch.setenv("BWS_ACCESS_TOKEN", "synthetic-bws-access-token")
    monkeypatch.setattr(bitwarden, "assert_connection_current", lambda selected: None)
    monkeypatch.setattr(bitwarden, "load_local_adapter", lambda path, required_operations: adapter)

    with pytest.raises(StoreError, match="no longer matches"):
        bitwarden.resolve_bound_profile_token(BoundStore(), binding())  # type: ignore[arg-type]
    assert adapter.closed is True


def test_bitwarden_profile_resolution_rejects_a_key_change(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = Adapter(key="OTHER_TOKEN")
    monkeypatch.setenv("BWS_ACCESS_TOKEN", "synthetic-bws-access-token")
    monkeypatch.setattr(bitwarden, "assert_connection_current", lambda selected: None)
    monkeypatch.setattr(bitwarden, "load_local_adapter", lambda path, required_operations: adapter)

    with pytest.raises(StoreError, match="undeclared key"):
        bitwarden.resolve_bound_profile_token(BoundStore(), binding())  # type: ignore[arg-type]
    assert adapter.closed is True


def test_bitwarden_profile_resolution_requires_the_selected_credential_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = Adapter()
    monkeypatch.delenv("BWS_ACCESS_TOKEN", raising=False)
    monkeypatch.setattr(bitwarden, "assert_connection_current", lambda selected: None)
    monkeypatch.setattr(bitwarden, "load_local_adapter", lambda path, required_operations: adapter)

    with pytest.raises(StoreError, match="BWS_ACCESS_TOKEN"):
        bitwarden.resolve_bound_profile_token(BoundStore(), binding())  # type: ignore[arg-type]
    assert adapter.closed is True


def test_bitwarden_profile_resolution_rejects_endpoint_drift_before_adapter_load(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        bitwarden,
        "assert_connection_current",
        lambda selected: (_ for _ in ()).throw(StoreError("endpoint configuration changed")),
    )
    monkeypatch.setattr(
        bitwarden,
        "load_local_adapter",
        lambda path, required_operations: (_ for _ in ()).throw(AssertionError("adapter must not load")),
    )

    with pytest.raises(StoreError, match="endpoint configuration changed"):
        bitwarden.resolve_bound_profile_token(BoundStore(), binding())  # type: ignore[arg-type]


def test_bitwarden_profile_resolution_rejects_ambient_overrides_before_adapter_load(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(bitwarden, "assert_connection_current", lambda selected: None)
    monkeypatch.setenv("BWS_PROFILE", "ambient")
    monkeypatch.setattr(
        bitwarden,
        "load_local_adapter",
        lambda path, required_operations: (_ for _ in ()).throw(AssertionError("adapter must not load")),
    )

    with pytest.raises(StoreError, match="conflicting bws environment override"):
        bitwarden.resolve_bound_profile_token(BoundStore(), binding())  # type: ignore[arg-type]


def test_bound_profile_metadata_is_value_free_and_removal_does_not_require_pass(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = VaultStore(config_dir=tmp_path / "config", pass_tool="")
    profile = Profile("bws-ghcli", ("repo",), "Bitwarden PAT", bitwarden=binding())
    store.bind_bitwarden(profile)

    config = json.loads(store.config_file.read_text(encoding="utf-8"))
    assert config["profiles"]["bws-ghcli"]["bitwarden"] == binding().as_dict()
    assert TOKEN not in store.config_file.read_text(encoding="utf-8")
    monkeypatch.setattr(bitwarden, "resolve_bound_profile_token", lambda selected_store, selected_binding: TOKEN)
    assert store.get() == TOKEN

    store.remove("bws-ghcli")
    assert store.active() is None
    assert store.profiles() == []


def test_bind_bitwarden_validates_before_persisting_and_emits_no_token(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    class BindingStore:
        def profiles(self) -> list[Profile]:
            return []

        def bind_bitwarden(self, profile: Profile) -> None:
            captured["profile"] = profile

    captured: dict[str, object] = {}
    args = cli.build_parser().parse_args(
        [
            "bind-bitwarden",
            "bws-ghcli",
            "--connection",
            "eu-production",
            "--project-id",
            PROJECT_ID,
            "--entry-id",
            ENTRY_ID,
            "--key",
            "GITHUB_TOKEN",
            "--adapter-path",
            str(tmp_path / "adapter"),
        ]
    )
    monkeypatch.setattr(cli, "resolve_bound_profile_token", lambda store, selected_binding: TOKEN)
    monkeypatch.setattr(cli, "inspect_token", lambda token: TokenMetadata(("repo",), "2026-12-31 23:59:59 UTC"))

    assert cli.dispatch(args, BindingStore()) == 0  # type: ignore[arg-type]
    profile = captured["profile"]
    assert isinstance(profile, Profile)
    assert profile.name == "bws-ghcli"
    assert profile.scopes == ("repo",)
    assert profile.bitwarden is not None
    assert profile.bitwarden.entry_id == ENTRY_ID
    assert profile.bitwarden.adapter_path == str((tmp_path / "adapter").resolve())
    output = capsys.readouterr().out
    assert output.endswith("Bound Bitwarden profile: bws-ghcli\n")
    assert TOKEN not in output
