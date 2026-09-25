from __future__ import annotations

import argparse
import stat
import sys
from pathlib import Path

import pytest

from gh_vault import bitwarden, cli, envfiles
from gh_vault.envfiles import parse_typed_dotenv
from gh_vault.store import BitwardenConnection, StoreError

ORGANIZATION_ID = "11111111-1111-4111-8111-111111111111"
PROJECT_ID = "22222222-2222-4222-8222-222222222222"
ENTRY_IDS = {
    "REGION": "33333333-3333-4333-8333-333333333331",
    "EMPTY": "33333333-3333-4333-8333-333333333332",
    "MULTILINE": "33333333-3333-4333-8333-333333333333",
    "LITERAL_FILE": "33333333-3333-4333-8333-333333333334",
    "LITERAL_BASE64": "33333333-3333-4333-8333-333333333335",
    "GITHUB_TOKEN": "33333333-3333-4333-8333-333333333336",
}
ACCESS_TOKEN = "synthetic-bws-access-token"


class MemoryStore:
    def __init__(self, selected: BitwardenConnection) -> None:
        self.selected = selected

    def get_bitwarden_connection(self, name: str) -> BitwardenConnection:
        if name != self.selected.name:
            raise StoreError(f"unknown Bitwarden connection: {name}")
        return self.selected

    def get_bitwarden_credential(self, name: str) -> str:
        raise AssertionError("vault credential must not be read")


def connection(tmp_path: Path) -> BitwardenConnection:
    return BitwardenConnection(
        name="eu-production",
        bws_config=str(tmp_path / "bws-config"),
        bws_profile="eu",
        api_url="https://api.bitwarden.eu",
        identity_url="https://identity.bitwarden.eu",
        organization_id=ORGANIZATION_ID,
    )


def response(values: dict[str, str]) -> dict[str, object]:
    return {
        "project_id": PROJECT_ID,
        "organization_id": ORGANIZATION_ID,
        "entries": [
            {
                "id": ENTRY_IDS[key],
                "key": key,
                "value": value,
                "organization_id": ORGANIZATION_ID,
                "project_ids": [PROJECT_ID],
            }
            for key, value in values.items()
        ],
    }


def inspection(*keys: str) -> dict[str, object]:
    return {
        "project_id": PROJECT_ID,
        "organization_id": ORGANIZATION_ID,
        "entries": [
            {
                "id": ENTRY_IDS[key],
                "key": key,
                "organization_id": ORGANIZATION_ID,
                "project_ids": [PROJECT_ID],
            }
            for key in keys
        ],
    }


class FakeAdapter:
    def __init__(self, result: object) -> None:
        self.result = result
        self.requests: list[dict[str, object]] = []
        self.closed = 0

    def read_environment(self, **request: object) -> object:
        self.requests.append(request)
        return self.result

    def close(self) -> None:
        self.closed += 1


class UploadAdapter:
    def __init__(self, inspected: object, written: object | None = None) -> None:
        self.inspected = inspected
        self.written = written
        self.inspect_requests: list[dict[str, object]] = []
        self.write_requests: list[dict[str, object]] = []
        self.closed = 0

    def inspect_environment(self, **request: object) -> object:
        self.inspect_requests.append(request)
        return self.inspected

    def write_environment(self, **request: object) -> object:
        self.write_requests.append(request)
        if isinstance(self.written, Exception):
            print(str(self.written))
            raise self.written
        if self.written is not None:
            return self.written
        entries = request["entries"]
        assert isinstance(entries, tuple)
        return {
            "project_id": request["project_id"],
            "organization_id": request["organization_id"],
            "entries": [
                {
                    "operation": entry["operation"],
                    "id": entry["id"] or ENTRY_IDS[entry["key"]],
                    "key": entry["key"],
                    "value": entry["value"],
                    "organization_id": request["organization_id"],
                    "project_ids": [request["project_id"]],
                }
                for entry in entries
            ],
        }

    def close(self) -> None:
        self.closed += 1


def restore_args(env_file: Path, example_file: Path, *, force: bool = False) -> argparse.Namespace:
    arguments = [
        "bitwarden",
        "env",
        "restore",
        "--connection",
        "eu-production",
        "--project-id",
        PROJECT_ID,
        "--adapter-path",
        "/operator/gh-vault-bws",
        "--env-file",
        str(env_file),
        "--example-file",
        str(example_file),
    ]
    if force:
        arguments.append("--force")
    return cli.build_parser().parse_args(arguments)


def upload_args(
    env_file: Path,
    *,
    apply: bool = False,
    update_existing: bool = False,
) -> argparse.Namespace:
    arguments = [
        "bitwarden",
        "env",
        "upload",
        "--connection",
        "eu-production",
        "--project-id",
        PROJECT_ID,
        "--adapter-path",
        "/operator/gh-vault-bws",
        "--env-file",
        str(env_file),
    ]
    if apply:
        arguments.append("--apply")
    if update_existing:
        arguments.append("--update-existing")
    return cli.build_parser().parse_args(arguments)


def prepare_dispatch(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    adapter: object,
) -> MemoryStore:
    selected = connection(tmp_path)
    store = MemoryStore(selected)
    monkeypatch.setenv("BWS_ACCESS_TOKEN", ACCESS_TOKEN)
    monkeypatch.setattr(
        cli,
        "project_namespace",
        lambda directory: ("github.com/owner/repo", "https://github.com/owner/repo.git"),
    )
    monkeypatch.setattr(cli, "assert_connection_current", lambda current: None)
    monkeypatch.setattr(cli, "load_local_adapter", lambda path, **kwargs: adapter)
    return store


def test_bitwarden_restore_recreates_fresh_environment_from_declared_keys(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    env_file = tmp_path / ".env"
    example_file = tmp_path / ".env.example"
    example_file.write_text(
        "# Deployment 東京\n"
        "# gh-vault: variable\n# REGION=example-is-not-a-default\n"
        "# gh-vault: secret\n# EMPTY=example-is-not-a-default\n"
        "# gh-vault: secret\n# MULTILINE=\n"
        "# gh-vault: secret\n# LITERAL_FILE=\n"
        "# gh-vault: variable\n# LITERAL_BASE64=\n"
        "# gh-vault: secret\n# GITHUB_TOKEN=\n"
        "LOCAL_ONLY=operator-supplied\n",
        encoding="utf-8",
    )
    values = {
        "REGION": "eu west $(literal) 東京",
        "EMPTY": "",
        "MULTILINE": "first\nsecond\n",
        "LITERAL_FILE": "@file:must-remain-literal",
        "LITERAL_BASE64": "@base64:YWJj",
        "GITHUB_TOKEN": "synthetic-reserved-value",
    }
    adapter = FakeAdapter(response(values))
    store = prepare_dispatch(monkeypatch, tmp_path, adapter)

    assert cli.dispatch(restore_args(env_file, example_file), store, tmp_path) == 0  # type: ignore[arg-type]

    assignments = parse_typed_dotenv(env_file)
    assert {entry.key: entry.value for entry in assignments if entry.kind != "local"} == values
    assert env_file.read_text(encoding="utf-8").endswith("# LOCAL_ONLY=operator-supplied\n")
    assert stat.S_IMODE(env_file.stat().st_mode) == 0o600
    assert adapter.closed == 1
    assert len(adapter.requests) == 1
    request = adapter.requests[0]
    assert request["keys"] == tuple(values)
    assert request["access_token"] == ACCESS_TOKEN
    assert request["project_id"] == PROJECT_ID
    assert isinstance(request["state_file"], str)
    assert not Path(str(request["state_file"])).exists()
    output = capsys.readouterr().out
    assert output == f"Restored 6 managed value(s) to {env_file} from Bitwarden project {PROJECT_ID}.\n"
    assert not any(value and value in output for value in values.values())


def test_bitwarden_restore_uses_explicit_named_template_without_cached_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env_file = tmp_path / ".env.production"
    example_file = tmp_path / ".env.example.production"
    example_file.write_text(
        "# gh-vault: variable\n# REGION=\nLOCAL_FILE=@file:missing-source-machine-file\n",
        encoding="utf-8",
    )
    adapter = FakeAdapter(response({"REGION": "eu-central-1"}))
    store = prepare_dispatch(monkeypatch, tmp_path, adapter)

    args = cli.build_parser().parse_args(
        [
            "bitwarden",
            "env",
            "restore",
            "--connection",
            "eu-production",
            "--project-id",
            PROJECT_ID,
            "--adapter-path",
            "/operator/gh-vault-bws",
            "--env-file",
            str(env_file),
        ]
    )
    assert cli.dispatch(args, store, tmp_path) == 0  # type: ignore[arg-type]

    assert env_file.read_text(encoding="utf-8") == (
        "# gh-vault: variable\nREGION=eu-central-1\n# LOCAL_FILE=@file:missing-source-machine-file\n"
    )
    assert adapter.requests[0]["keys"] == ("REGION",)


def test_local_loader_exposes_environment_read_and_cleans_module_state(tmp_path: Path) -> None:
    package = tmp_path / "adapter" / "gh_vault_bws"
    package.mkdir(parents=True)
    package.joinpath("__init__.py").write_text(
        f'''GH_VAULT_ADAPTER_API = 1

def resolve_project(**request):
    return {{"project_id": request["project_id"], "organization_id": request["organization_id"]}}

def read_environment(**request):
    return {{
        "project_id": request["project_id"],
        "organization_id": request["organization_id"],
        "entries": [{{
            "id": "{ENTRY_IDS["REGION"]}",
            "key": request["keys"][0],
            "value": "eu",
            "organization_id": request["organization_id"],
            "project_ids": [request["project_id"]],
        }}],
    }}
''',
        encoding="utf-8",
    )

    adapter = bitwarden.load_local_adapter(tmp_path / "adapter")
    assert bitwarden.read_environment(
        adapter,
        connection(tmp_path),
        ACCESS_TOKEN,
        PROJECT_ID,
        ("REGION",),
    ) == {"REGION": "eu"}
    assert "gh_vault_bws" not in sys.modules


@pytest.mark.parametrize(
    ("entries", "match"),
    [
        ([], "missing declared key"),
        (
            [
                {
                    "id": ENTRY_IDS["REGION"],
                    "key": "REGION",
                    "value": "one",
                    "organization_id": ORGANIZATION_ID,
                    "project_ids": [PROJECT_ID],
                },
                {
                    "id": "33333333-3333-4333-8333-333333333339",
                    "key": "REGION",
                    "value": "two",
                    "organization_id": ORGANIZATION_ID,
                    "project_ids": [PROJECT_ID],
                },
            ],
            "duplicate key",
        ),
        (
            [
                {
                    "id": ENTRY_IDS["REGION"],
                    "key": "REGION",
                    "value": "eu",
                    "organization_id": ORGANIZATION_ID,
                    "project_ids": [PROJECT_ID],
                },
                {
                    "id": "33333333-3333-4333-8333-333333333339",
                    "key": "UNDECLARED",
                    "value": "ignored",
                    "organization_id": ORGANIZATION_ID,
                    "project_ids": [PROJECT_ID],
                },
            ],
            "undeclared key",
        ),
    ],
)
def test_read_environment_rejects_missing_duplicate_or_unsolicited_entries(
    tmp_path: Path, entries: list[dict[str, object]], match: str
) -> None:
    result = {
        "project_id": PROJECT_ID,
        "organization_id": ORGANIZATION_ID,
        "entries": entries,
    }
    adapter = FakeAdapter(result)

    with pytest.raises(StoreError, match=match):
        bitwarden.read_environment(
            adapter,
            connection(tmp_path),
            ACCESS_TOKEN,
            PROJECT_ID,
            ("REGION",),
        )

    assert adapter.closed == 1


@pytest.mark.parametrize(
    ("entry_update", "match"),
    [
        ({"value": "contains\x00nul"}, "NUL"),
        ({"organization_id": "44444444-4444-4444-8444-444444444444"}, "outside the configured organization"),
        ({"project_ids": ["55555555-5555-4555-8555-555555555555"]}, "outside the selected project"),
    ],
)
def test_read_environment_rejects_invalid_value_or_scope(
    tmp_path: Path, entry_update: dict[str, object], match: str
) -> None:
    result = response({"REGION": "eu"})
    entry = result["entries"][0]  # type: ignore[index]
    entry.update(entry_update)  # type: ignore[union-attr]
    adapter = FakeAdapter(result)

    with pytest.raises(StoreError, match=match):
        bitwarden.read_environment(
            adapter,
            connection(tmp_path),
            ACCESS_TOKEN,
            PROJECT_ID,
            ("REGION",),
        )


def test_read_environment_closes_adapter_when_request_validation_fails(tmp_path: Path) -> None:
    adapter = FakeAdapter(response({"REGION": "eu"}))

    with pytest.raises(StoreError, match="single line"):
        bitwarden.read_environment(
            adapter,
            connection(tmp_path),
            "invalid\ntoken",
            PROJECT_ID,
            ("REGION",),
        )

    assert adapter.requests == []
    assert adapter.closed == 1


def test_restore_rejects_profile_reference_before_connection_or_adapter_access(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env_file = tmp_path / ".env"
    example_file = tmp_path / ".env.example"
    example_file.write_text(
        "# gh-vault: secret release\n# GITHUB_TOKEN=\n",
        encoding="utf-8",
    )

    class NoAccessStore:
        def get_bitwarden_connection(self, name: str) -> BitwardenConnection:
            raise AssertionError("connection metadata must not be read")

    monkeypatch.setattr(cli, "load_local_adapter", lambda path: pytest.fail("adapter must not load"))
    monkeypatch.setenv("BWS_ACCESS_TOKEN", ACCESS_TOKEN)

    with pytest.raises(StoreError, match="profile references cannot be restored from Bitwarden"):
        cli.dispatch(restore_args(env_file, example_file), NoAccessStore(), tmp_path)  # type: ignore[arg-type]

    assert not env_file.exists()


def test_restore_refuses_existing_target_before_remote_access(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env_file = tmp_path / ".env"
    example_file = tmp_path / ".env.example"
    original = "LOCAL_ONLY=keep\n"
    env_file.write_text(original, encoding="utf-8")
    example_file.write_text("# gh-vault: variable\n# REGION=\n", encoding="utf-8")

    class NoAccessStore:
        def get_bitwarden_connection(self, name: str) -> BitwardenConnection:
            raise AssertionError("connection metadata must not be read")

    monkeypatch.setattr(cli, "load_local_adapter", lambda path: pytest.fail("adapter must not load"))

    with pytest.raises(StoreError, match="refusing to overwrite"):
        cli.dispatch(restore_args(env_file, example_file), NoAccessStore(), tmp_path)  # type: ignore[arg-type]

    assert env_file.read_text(encoding="utf-8") == original


def test_restore_rechecks_overwrite_before_atomic_replacement(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    example_file = tmp_path / ".env.example"
    example_file.write_text("# gh-vault: variable\n# REGION=\n", encoding="utf-8")
    plan = envfiles.prepare_bitwarden_restore(env_file, example_file, force=False)
    env_file.write_text("LOCAL_ONLY=appeared-during-retrieval\n", encoding="utf-8")

    with pytest.raises(StoreError, match="refusing to overwrite"):
        envfiles.apply_bitwarden_restore(plan, {"REGION": "eu"})

    assert env_file.read_text(encoding="utf-8") == "LOCAL_ONLY=appeared-during-retrieval\n"


def test_restore_keeps_forced_target_when_remote_validation_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env_file = tmp_path / ".env"
    example_file = tmp_path / ".env.example"
    original = "LOCAL_ONLY=keep\n"
    env_file.write_text(original, encoding="utf-8")
    example_file.write_text("# gh-vault: variable\n# REGION=\n", encoding="utf-8")
    adapter = FakeAdapter(response({}))
    store = prepare_dispatch(monkeypatch, tmp_path, adapter)

    with pytest.raises(StoreError, match="missing declared key"):
        cli.dispatch(restore_args(env_file, example_file, force=True), store, tmp_path)  # type: ignore[arg-type]

    assert env_file.read_text(encoding="utf-8") == original


def test_restore_discards_adapter_error_text_and_leaves_target_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env_file = tmp_path / ".env"
    example_file = tmp_path / ".env.example"
    example_file.write_text("# gh-vault: variable\n# REGION=\n", encoding="utf-8")
    leaked = "synthetic-sensitive-service-error"

    class FailingAdapter(FakeAdapter):
        def read_environment(self, **request: object) -> object:
            raise StoreError(leaked)

    adapter = FailingAdapter(None)
    store = prepare_dispatch(monkeypatch, tmp_path, adapter)

    with pytest.raises(StoreError, match="Bitwarden environment retrieval failed") as caught:
        cli.dispatch(restore_args(env_file, example_file), store, tmp_path)  # type: ignore[arg-type]

    assert leaked not in str(caught.value)
    assert caught.value.__cause__ is None
    assert adapter.closed == 1
    assert not env_file.exists()


def test_atomic_restore_keeps_old_target_when_replace_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env_file = tmp_path / ".env"
    example_file = tmp_path / ".env.example"
    original = "LOCAL_ONLY=old\n"
    env_file.write_text(original, encoding="utf-8")
    example_file.write_text("# gh-vault: variable\n# REGION=\n", encoding="utf-8")
    plan = envfiles.prepare_bitwarden_restore(env_file, example_file, force=True)
    monkeypatch.setattr(envfiles.os, "replace", lambda source, target: (_ for _ in ()).throw(OSError("synthetic replace failure")))

    with pytest.raises(StoreError, match="cannot replace"):
        envfiles.apply_bitwarden_restore(plan, {"REGION": "eu"})

    assert env_file.read_text(encoding="utf-8") == original
    assert not any(path.name.startswith("..env.") for path in tmp_path.iterdir())


def test_format_dotenv_value_quotes_literal_transport_markers(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "FILE=" + envfiles.format_dotenv_value("@file:missing") + "\n"
        "ENCODED=" + envfiles.format_dotenv_value("@base64:YWJj") + "\n",
        encoding="utf-8",
    )

    assignments = parse_typed_dotenv(env_file)
    assert {entry.key: entry.value for entry in assignments} == {
        "FILE": "@file:missing",
        "ENCODED": "@base64:YWJj",
    }


def test_bitwarden_upload_preview_names_types_and_operations_without_values(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "# gh-vault: secret\nREGION=synthetic-secret-value\n"
        "# gh-vault: variable\nEMPTY=\n"
        "LOCAL_ONLY=not-uploaded\n",
        encoding="utf-8",
    )
    adapter = UploadAdapter(inspection("REGION"))
    store = prepare_dispatch(monkeypatch, tmp_path, adapter)

    assert cli.dispatch(
        upload_args(env_file, update_existing=True), store, tmp_path  # type: ignore[arg-type]
    ) == 0

    assert adapter.write_requests == []
    assert adapter.closed == 1
    assert adapter.inspect_requests[0]["keys"] == ("REGION", "EMPTY")
    output = capsys.readouterr().out
    assert f"Would update secret REGION in Bitwarden project {PROJECT_ID}." in output
    assert f"Would create variable EMPTY in Bitwarden project {PROJECT_ID}." in output
    assert "1 create(s), 1 update(s), 0 existing value(s) unchanged" in output
    assert "synthetic-secret-value" not in output
    assert "not-uploaded" not in output


def test_bitwarden_upload_applies_resolved_values_and_verifies_readback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = tmp_path / "payload.txt"
    source.write_text("first\nsecond\n", encoding="utf-8")
    env_file = tmp_path / ".env"
    env_file.write_text(
        "# gh-vault: secret\nREGION=@file:payload.txt\n"
        "# gh-vault: variable\nEMPTY=\n"
        "# gh-vault: secret\nLITERAL_FILE=\"@file:must-remain-literal\"\n"
        "# gh-vault: variable\nLITERAL_BASE64='@base64:YWJj'\n"
        "LOCAL_ONLY=excluded\n",
        encoding="utf-8",
    )
    adapter = UploadAdapter(inspection("REGION"))
    store = prepare_dispatch(monkeypatch, tmp_path, adapter)
    before_argv = list(sys.argv)

    assert cli.dispatch(
        upload_args(env_file, apply=True, update_existing=True),
        store,  # type: ignore[arg-type]
        tmp_path,
    ) == 0

    assert len(adapter.inspect_requests) == 1
    assert len(adapter.write_requests) == 1
    assert adapter.closed == 2
    request = adapter.write_requests[0]
    assert request["entries"] == (
        {
            "operation": "update",
            "id": ENTRY_IDS["REGION"],
            "key": "REGION",
            "value": "first\nsecond\n",
        },
        {"operation": "create", "id": None, "key": "EMPTY", "value": ""},
        {
            "operation": "create",
            "id": None,
            "key": "LITERAL_FILE",
            "value": "@file:must-remain-literal",
        },
        {
            "operation": "create",
            "id": None,
            "key": "LITERAL_BASE64",
            "value": "@base64:YWJj",
        },
    )
    assert request["access_token"] == ACCESS_TOKEN
    assert request["project_id"] == PROJECT_ID
    assert isinstance(request["state_file"], str)
    assert not Path(str(request["state_file"])).exists()
    assert sys.argv == before_argv
    output = capsys.readouterr().out
    assert output == (
        f"Uploaded 4 managed value(s) to Bitwarden project {PROJECT_ID}: "
        "3 created, 1 updated; 0 existing value(s) left unchanged.\n"
    )
    assert "first" not in output


def test_bitwarden_upload_rerun_skips_existing_entry_without_creating_duplicate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "# gh-vault: secret\nREGION=current\n"
        "# gh-vault: variable\nEMPTY=\n",
        encoding="utf-8",
    )
    adapter = UploadAdapter(inspection("REGION"))
    store = prepare_dispatch(monkeypatch, tmp_path, adapter)

    assert cli.dispatch(upload_args(env_file, apply=True), store, tmp_path) == 0  # type: ignore[arg-type]

    assert adapter.write_requests[0]["entries"] == (
        {"operation": "create", "id": None, "key": "EMPTY", "value": ""},
    )
    assert capsys.readouterr().out.endswith("1 created, 0 updated; 1 existing value(s) left unchanged.\n")


def test_bitwarden_upload_apply_with_only_existing_entries_performs_no_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("# gh-vault: secret\nREGION=current\n", encoding="utf-8")
    adapter = UploadAdapter(inspection("REGION"))
    store = prepare_dispatch(monkeypatch, tmp_path, adapter)

    assert cli.dispatch(upload_args(env_file, apply=True), store, tmp_path) == 0  # type: ignore[arg-type]

    assert adapter.write_requests == []
    assert adapter.closed == 1
    assert capsys.readouterr().out == (
        f"No Bitwarden writes required for project {PROJECT_ID}; "
        "1 existing value(s) left unchanged.\n"
    )


def test_bitwarden_upload_inspection_failure_never_loads_writer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("# gh-vault: variable\nEMPTY=\n", encoding="utf-8")
    leaked = "synthetic-inspection-error"

    class FailingInspectionAdapter(UploadAdapter):
        def inspect_environment(self, **request: object) -> object:
            print(leaked)
            raise RuntimeError(leaked)

    adapter = FailingInspectionAdapter(inspection())
    store = prepare_dispatch(monkeypatch, tmp_path, adapter)
    loads: list[tuple[str, ...]] = []

    def load(path: Path, **kwargs: object) -> UploadAdapter:
        required = kwargs.get("required_operations")
        assert isinstance(required, tuple)
        loads.append(required)
        if len(loads) > 1:
            pytest.fail("writer adapter must not load after inspection failure")
        return adapter

    monkeypatch.setattr(cli, "load_local_adapter", load)

    with pytest.raises(StoreError, match="environment inspection failed") as caught:
        cli.dispatch(upload_args(env_file, apply=True), store, tmp_path)  # type: ignore[arg-type]

    assert leaked not in str(caught.value)
    assert adapter.write_requests == []
    assert loads == [("inspect_environment", "write_environment")]
    assert capsys.readouterr() == ("", "")


def test_bitwarden_upload_round_trips_into_a_second_synthetic_checkout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_checkout = tmp_path / "source"
    target_checkout = tmp_path / "target"
    source_checkout.mkdir()
    target_checkout.mkdir()
    source_env = source_checkout / ".env"
    source_env.write_text(
        "# gh-vault: secret\nMULTILINE=@base64:Zmlyc3QKc2Vjb25kCg==\n"
        "# gh-vault: variable\nEMPTY=\n"
        "SOURCE_ONLY=excluded\n",
        encoding="utf-8",
    )
    upload_adapter = UploadAdapter(inspection())
    store = prepare_dispatch(monkeypatch, tmp_path, upload_adapter)

    assert cli.dispatch(upload_args(source_env, apply=True), store, source_checkout) == 0  # type: ignore[arg-type]
    written_entries = upload_adapter.write_requests[0]["entries"]
    assert isinstance(written_entries, tuple)
    values = {entry["key"]: entry["value"] for entry in written_entries}

    target_example = target_checkout / ".env.example"
    target_env = target_checkout / ".env"
    target_example.write_text(
        "# gh-vault: secret\n# MULTILINE=\n"
        "# gh-vault: variable\n# EMPTY=\n"
        "TARGET_ONLY=excluded\n",
        encoding="utf-8",
    )
    restore_adapter = FakeAdapter(response(values))
    monkeypatch.setattr(cli, "load_local_adapter", lambda path, **kwargs: restore_adapter)

    assert cli.dispatch(
        restore_args(target_env, target_example), store, target_checkout  # type: ignore[arg-type]
    ) == 0
    restored = parse_typed_dotenv(target_env)
    assert {entry.key: entry.value for entry in restored if entry.kind != "local"} == {
        "MULTILINE": "first\nsecond\n",
        "EMPTY": "",
    }
    assert target_env.read_text(encoding="utf-8").endswith("# TARGET_ONLY=excluded\n")


def test_bitwarden_upload_rejects_duplicate_remote_names_before_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("# gh-vault: secret\nREGION=current\n", encoding="utf-8")
    result = inspection("REGION")
    duplicate = dict(result["entries"][0])  # type: ignore[index]
    duplicate["id"] = "33333333-3333-4333-8333-333333333339"
    result["entries"].append(duplicate)  # type: ignore[union-attr]
    adapter = UploadAdapter(result)
    store = prepare_dispatch(monkeypatch, tmp_path, adapter)

    with pytest.raises(StoreError, match="duplicate key REGION"):
        cli.dispatch(upload_args(env_file, apply=True), store, tmp_path)  # type: ignore[arg-type]

    assert adapter.write_requests == []


def test_bitwarden_inspection_does_not_relay_hostile_response_text(tmp_path: Path) -> None:
    leaked = "synthetic-sensitive-adapter-field"
    result = {
        "project_id": PROJECT_ID,
        "organization_id": ORGANIZATION_ID,
        "entries": [
            {
                "id": ENTRY_IDS["REGION"],
                "key": leaked,
                "organization_id": ORGANIZATION_ID,
                "project_ids": [PROJECT_ID],
            }
        ],
    }
    adapter = UploadAdapter(result)

    with pytest.raises(StoreError, match="undeclared key") as caught:
        bitwarden.inspect_environment(
            adapter,
            connection(tmp_path),
            ACCESS_TOKEN,
            PROJECT_ID,
            ("REGION",),
        )

    assert leaked not in str(caught.value)


@pytest.mark.parametrize(
    ("response_update", "match"),
    [
        ({"project_id": "44444444-4444-4444-8444-444444444444"}, "different project"),
        ({"entries": []}, "incomplete environment write response"),
        (
            {
                "entries": [
                    {
                        "operation": "create",
                        "id": ENTRY_IDS["REGION"],
                        "key": "REGION",
                        "value": "eu",
                        "organization_id": ORGANIZATION_ID,
                        "project_ids": [PROJECT_ID],
                    }
                ]
            },
            "unexpected environment write operation",
        ),
    ],
)
def test_write_environment_rejects_wrong_target_or_incomplete_readback(
    tmp_path: Path,
    response_update: dict[str, object],
    match: str,
) -> None:
    valid = {
        "project_id": PROJECT_ID,
        "organization_id": ORGANIZATION_ID,
        "entries": [
            {
                "operation": "update",
                "id": ENTRY_IDS["REGION"],
                "key": "REGION",
                "value": "eu",
                "organization_id": ORGANIZATION_ID,
                "project_ids": [PROJECT_ID],
            }
        ],
    }
    valid.update(response_update)
    adapter = UploadAdapter(inspection("REGION"), valid)

    with pytest.raises(StoreError, match=match):
        bitwarden.write_environment(
            adapter,
            connection(tmp_path),
            ACCESS_TOKEN,
            PROJECT_ID,
            (bitwarden.BitwardenWrite("REGION", "eu", ENTRY_IDS["REGION"]),),
        )

    assert adapter.closed == 1


def test_write_environment_rejects_changed_readback_value(tmp_path: Path) -> None:
    written = {
        "project_id": PROJECT_ID,
        "organization_id": ORGANIZATION_ID,
        "entries": [
            {
                "operation": "create",
                "id": ENTRY_IDS["EMPTY"],
                "key": "EMPTY",
                "value": "changed",
                "organization_id": ORGANIZATION_ID,
                "project_ids": [PROJECT_ID],
            }
        ],
    }
    adapter = UploadAdapter(inspection(), written)

    with pytest.raises(StoreError, match="write verification failed for EMPTY"):
        bitwarden.write_environment(
            adapter,
            connection(tmp_path),
            ACCESS_TOKEN,
            PROJECT_ID,
            (bitwarden.BitwardenWrite("EMPTY", "", None),),
        )


def test_bitwarden_upload_reports_uncertain_partial_failure_without_adapter_text(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("# gh-vault: variable\nEMPTY=\n", encoding="utf-8")
    leaked = "permission denied for synthetic-secret-value"
    adapter = UploadAdapter(inspection(), RuntimeError(leaked))
    store = prepare_dispatch(monkeypatch, tmp_path, adapter)

    with pytest.raises(StoreError, match="remote state may have changed") as caught:
        cli.dispatch(upload_args(env_file, apply=True), store, tmp_path)  # type: ignore[arg-type]

    assert leaked not in str(caught.value)
    assert caught.value.__cause__ is None
    assert capsys.readouterr() == ("", "")
    assert adapter.closed == 2


def test_upload_rejects_profile_reference_before_connection_or_adapter_access(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "# gh-vault: secret release\nGITHUB_TOKEN=\n",
        encoding="utf-8",
    )

    class NoAccessStore:
        def get_bitwarden_connection(self, name: str) -> BitwardenConnection:
            raise AssertionError("connection metadata must not be read")

    monkeypatch.setattr(cli, "load_local_adapter", lambda path: pytest.fail("adapter must not load"))

    with pytest.raises(StoreError, match="profile references cannot be uploaded to Bitwarden"):
        cli.dispatch(upload_args(env_file), NoAccessStore(), tmp_path)  # type: ignore[arg-type]


def test_prepare_bitwarden_upload_requires_managed_values_and_rejects_nul(
    tmp_path: Path,
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("LOCAL_ONLY=kept-local\n", encoding="utf-8")
    with pytest.raises(StoreError, match="no managed declarations"):
        envfiles.prepare_bitwarden_upload(env_file)

    payload = tmp_path / "payload"
    payload.write_bytes(b"contains\x00nul")
    env_file.write_text("# gh-vault: secret\nREGION=@file:payload\n", encoding="utf-8")
    with pytest.raises(StoreError, match="REGION contains NUL"):
        envfiles.prepare_bitwarden_upload(env_file)


def test_upload_requires_adapter_capabilities_before_credential_access(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("# gh-vault: variable\nEMPTY=\n", encoding="utf-8")
    package = tmp_path / "adapter" / "gh_vault_bws"
    package.mkdir(parents=True)
    package.joinpath("__init__.py").write_text(
        "GH_VAULT_ADAPTER_API = 1\n"
        "def resolve_project(**request): return None\n",
        encoding="utf-8",
    )
    args = upload_args(env_file, apply=True)
    args.adapter_path = tmp_path / "adapter"
    selected = connection(tmp_path)
    store = MemoryStore(selected)
    monkeypatch.delenv("BWS_ACCESS_TOKEN", raising=False)
    monkeypatch.setattr(
        cli,
        "project_namespace",
        lambda directory: ("github.com/owner/repo", "https://github.com/owner/repo.git"),
    )
    monkeypatch.setattr(cli, "assert_connection_current", lambda current: None)
    monkeypatch.setattr(cli, "reject_bws_overrides", lambda: None)

    with pytest.raises(StoreError, match="does not implement inspect_environment") as caught:
        cli.dispatch(args, store, tmp_path)  # type: ignore[arg-type]

    assert "BWS_ACCESS_TOKEN" not in str(caught.value)


def test_upload_closes_preflighted_adapter_when_credential_is_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("# gh-vault: variable\nEMPTY=\n", encoding="utf-8")
    adapter = UploadAdapter(inspection())
    store = prepare_dispatch(monkeypatch, tmp_path, adapter)
    monkeypatch.delenv("BWS_ACCESS_TOKEN")

    with pytest.raises(StoreError, match="BWS_ACCESS_TOKEN is required"):
        cli.dispatch(upload_args(env_file), store, tmp_path)  # type: ignore[arg-type]

    assert adapter.closed == 1
    assert adapter.inspect_requests == []


def test_local_loader_exposes_upload_operations(tmp_path: Path) -> None:
    package = tmp_path / "adapter" / "gh_vault_bws"
    package.mkdir(parents=True)
    package.joinpath("__init__.py").write_text(
        "GH_VAULT_ADAPTER_API = 1\n"
        "def resolve_project(**request): return None\n"
        "def inspect_environment(**request): return None\n"
        "def write_environment(**request): return None\n",
        encoding="utf-8",
    )

    adapter = bitwarden.load_local_adapter(tmp_path / "adapter")
    assert callable(adapter.inspect_environment)
    assert callable(adapter.write_environment)
    adapter.close()
    assert "gh_vault_bws" not in sys.modules
