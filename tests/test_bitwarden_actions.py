from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest

from gh_vault import cli
from gh_vault.store import BitwardenConnection, StoreError

ORGANIZATION_ID = "11111111-1111-4111-8111-111111111111"
PROJECT_ID = "22222222-2222-4222-8222-222222222222"
ENTRY_IDS = {
    "REGION": "33333333-3333-4333-8333-333333333331",
    "API_KEY": "33333333-3333-4333-8333-333333333332",
    "SECOND": "33333333-3333-4333-8333-333333333333",
}
ACCESS_TOKEN = "synthetic-bws-access-token"


class MemoryStore:
    def __init__(self, selected: BitwardenConnection, config_dir: Path) -> None:
        self.selected = selected
        self.config_dir = config_dir

    def get_bitwarden_connection(self, name: str) -> BitwardenConnection:
        if name != self.selected.name:
            raise StoreError(f"unknown Bitwarden connection: {name}")
        return self.selected

    def get_bitwarden_credential(self, name: str) -> str:
        raise AssertionError("vault credential must not be read")


class FakeAdapter:
    def __init__(self, values: dict[str, str]) -> None:
        self.values = values
        self.requests: list[dict[str, object]] = []
        self.closed = 0

    def read_environment(self, **request: object) -> object:
        self.requests.append(request)
        keys = request["keys"]
        assert isinstance(keys, tuple)
        return {
            "project_id": request["project_id"],
            "organization_id": request["organization_id"],
            "entries": [
                {
                    "id": ENTRY_IDS[key],
                    "key": key,
                    "value": self.values[key],
                    "organization_id": request["organization_id"],
                    "project_ids": [request["project_id"]],
                }
                for key in keys
            ],
        }

    def close(self) -> None:
        self.closed += 1


def connection(tmp_path: Path) -> BitwardenConnection:
    return BitwardenConnection(
        name="eu-production",
        bws_config=str(tmp_path / "bws-config"),
        bws_profile="eu",
        api_url="https://api.bitwarden.eu",
        identity_url="https://identity.bitwarden.eu",
        organization_id=ORGANIZATION_ID,
    )


def publish_args(
    env_file: Path,
    repo: str = "owner/repo",
    *,
    example_file: Path | None = None,
    apply: bool = False,
    github_environment: str | None = None,
) -> object:
    arguments = [
        "bitwarden",
        "actions",
        "publish",
        "--connection",
        "eu-production",
        "--project-id",
        PROJECT_ID,
        "--adapter-path",
        "/operator/gh-vault-bws",
        "--env-file",
        str(env_file),
        "--repo",
        repo,
    ]
    if example_file is not None:
        arguments.extend(("--example-file", str(example_file)))
    if github_environment is not None:
        arguments.extend(("--github-environment", github_environment))
    if apply:
        arguments.append("--apply")
    return cli.build_parser().parse_args(arguments)


def prepare_dispatch(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    adapter: FakeAdapter,
) -> MemoryStore:
    store = MemoryStore(connection(tmp_path), tmp_path / "config")
    monkeypatch.setenv("BWS_ACCESS_TOKEN", ACCESS_TOKEN)
    monkeypatch.setenv("GH_TOKEN", "synthetic-github-auth-token")
    monkeypatch.setattr(
        cli,
        "project_namespace",
        lambda directory: (
            "github.com/source/repo",
            "https://github.com/source/repo.git",
        ),
    )
    monkeypatch.setattr(cli, "assert_connection_current", lambda current: None)
    monkeypatch.setattr(cli, "load_local_adapter", lambda path, **kwargs: adapter)
    monkeypatch.setattr(cli, "_publication_time", lambda: "2026-09-25T12:00:00Z")
    return store


def write_template(path: Path, *, include_second: bool = False) -> None:
    contents = (
        "# gh-vault: variable\n# REGION=example-is-not-a-default\n"
        "# gh-vault: secret\n# API_KEY=example-is-not-a-default\n"
        "LOCAL_ONLY=excluded\n"
    )
    if include_second:
        contents += "# gh-vault: secret\n# SECOND=example-is-not-a-default\n"
    path.write_text(contents, encoding="utf-8")


def result(stdout: str = "", *, returncode: int = 0, stderr: str = "") -> object:
    return type(
        "Result",
        (),
        {"returncode": returncode, "stdout": stdout, "stderr": stderr},
    )()


def _assert_clean_child_environment(kwargs: dict[str, object]) -> None:
    child_environment = kwargs.get("env")
    assert isinstance(child_environment, dict)
    assert child_environment.get("GH_TOKEN") == "synthetic-github-auth-token"
    assert "BWS_ACCESS_TOKEN" not in child_environment


def test_bitwarden_actions_publish_requires_explicit_repo_and_exposes_no_destructive_flags() -> None:
    base = [
        "bitwarden",
        "actions",
        "publish",
        "--connection",
        "eu-production",
        "--project-id",
        PROJECT_ID,
        "--adapter-path",
        "/operator/gh-vault-bws",
    ]

    with pytest.raises(SystemExit, match="2"):
        cli.build_parser().parse_args(base)
    for flag in ("--prune", "--migrate-types", "--update-existing"):
        with pytest.raises(SystemExit, match="2"):
            cli.build_parser().parse_args([*base, "--repo", "owner/repo", flag])


def test_bitwarden_actions_publish_previews_exact_bws_values_without_writes_or_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    env_file = tmp_path / ".env"
    example_file = tmp_path / ".env.example"
    write_template(example_file)
    values = {"REGION": "eu-central-1", "API_KEY": "synthetic-secret-value"}
    adapter = FakeAdapter(values)
    store = prepare_dispatch(monkeypatch, tmp_path, adapter)
    calls: list[tuple[list[str], str | None]] = []

    def fake_run(command: list[str], **kwargs: object) -> object:
        _assert_clean_child_environment(kwargs)
        supplied = kwargs.get("input")
        calls.append((command, supplied if isinstance(supplied, str) else None))
        if command[:3] == ["gh", "secret", "list"]:
            return result('[{"name":"API_KEY","updatedAt":"2026-09-24T10:00:00Z"}]')
        if command[:3] == ["gh", "variable", "list"]:
            return result("[]")
        raise AssertionError(f"unexpected command: {command}")

    monkeypatch.setattr("gh_vault.actions.subprocess.run", fake_run)

    assert cli.dispatch(
        publish_args(env_file, example_file=example_file),  # type: ignore[arg-type]
        store,  # type: ignore[arg-type]
        tmp_path,
    ) == 0

    assert adapter.requests[0]["keys"] == ("REGION", "API_KEY")
    assert adapter.requests[0]["access_token"] == ACCESS_TOKEN
    assert adapter.closed == 1
    assert calls == [
        (["gh", "secret", "list", "--repo", "owner/repo", "--json", "name,updatedAt"], None),
        (["gh", "variable", "list", "--repo", "owner/repo", "--json", "name,value,updatedAt"], None),
    ]
    output = capsys.readouterr().out
    assert "Would create variable REGION" in output
    assert "Would update secret API_KEY" in output
    assert "synthetic-secret-value" not in output
    assert "eu-central-1" not in output
    assert not (store.config_dir / "publications").exists()


def test_bitwarden_actions_publish_applies_with_stdin_readback_and_value_free_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    env_file = tmp_path / ".env"
    example_file = tmp_path / ".env.example"
    write_template(example_file)
    values = {"REGION": "eu-central-1", "API_KEY": "synthetic-secret-value"}
    adapter = FakeAdapter(values)
    store = prepare_dispatch(monkeypatch, tmp_path, adapter)
    calls: list[tuple[list[str], str | None]] = []
    secret_lists = 0
    variable_lists = 0

    def fake_run(command: list[str], **kwargs: object) -> object:
        nonlocal secret_lists, variable_lists
        _assert_clean_child_environment(kwargs)
        supplied = kwargs.get("input")
        calls.append((command, supplied if isinstance(supplied, str) else None))
        if command[:3] == ["gh", "secret", "list"]:
            secret_lists += 1
            return result(
                "[]" if secret_lists == 1 else '[{"name":"API_KEY","updatedAt":"2026-09-25T12:01:00Z"}]'
            )
        if command[:3] == ["gh", "variable", "list"]:
            variable_lists += 1
            return result(
                "[]" if variable_lists == 1 else '[{"name":"REGION","value":"eu-central-1","updatedAt":"2026-09-25T12:00:30Z"}]'
            )
        if command[:3] in (["gh", "variable", "set"], ["gh", "secret", "set"]):
            return result()
        raise AssertionError(f"unexpected command: {command}")

    monkeypatch.setattr("gh_vault.actions.subprocess.run", fake_run)

    assert cli.dispatch(
        publish_args(env_file, example_file=example_file, apply=True),  # type: ignore[arg-type]
        store,  # type: ignore[arg-type]
        tmp_path,
    ) == 0
    assert adapter.closed == 1

    assert (["gh", "variable", "set", "REGION", "--repo", "owner/repo"], "eu-central-1") in calls
    assert (["gh", "secret", "set", "API_KEY", "--repo", "owner/repo"], "synthetic-secret-value") in calls
    assert not any(command[1:3] in (["secret", "remove"], ["variable", "delete"]) for command, _ in calls)
    output = capsys.readouterr().out
    assert output == (
        "Published 2 Bitwarden standby value(s) to owner/repo: "
        "2 created; 1 variable verified exactly, 1 secret verified by name/type only.\n"
    )
    assert not any(value in output for value in values.values())

    metadata_path = (
        store.config_dir
        / "publications"
        / "github.com"
        / "source"
        / "repo"
        / "env.standby.json"
    )
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert stat.S_IMODE(metadata_path.stat().st_mode) == 0o600
    assert stat.S_IMODE(metadata_path.parent.stat().st_mode) == 0o700
    assert metadata == {
        "attempted_at": "2026-09-25T12:00:00Z",
        "connection": "eu-production",
        "destination": {"environment": None, "repo": "owner/repo"},
        "entries": [
            {
                "kind": "variable",
                "name": "REGION",
                "operation": "create",
                "remote_revision": "2026-09-25T12:00:30Z",
                "result": "value-verified",
                "source_id": ENTRY_IDS["REGION"],
            },
            {
                "kind": "secret",
                "name": "API_KEY",
                "operation": "create",
                "remote_revision": "2026-09-25T12:01:00Z",
                "result": "name-type-verified",
                "source_id": ENTRY_IDS["API_KEY"],
            },
        ],
        "failed_key": None,
        "origin": "https://github.com/source/repo.git",
        "project_id": PROJECT_ID,
        "source_profile": "default",
        "status": "success",
        "version": 1,
    }
    serialized = json.dumps(metadata)
    assert not any(value in serialized for value in values.values())
    assert "hash" not in serialized.lower()


def test_bitwarden_actions_publish_closes_adapter_after_preview(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env_file = tmp_path / ".env"
    example_file = tmp_path / ".env.example"
    write_template(example_file)
    adapter = FakeAdapter({"REGION": "eu-central-1", "API_KEY": "synthetic"})
    store = prepare_dispatch(monkeypatch, tmp_path, adapter)
    monkeypatch.setattr(
        "gh_vault.actions.subprocess.run",
        lambda *args, **kwargs: result("[]"),
    )

    assert cli.dispatch(
        publish_args(env_file, example_file=example_file),  # type: ignore[arg-type]
        store,  # type: ignore[arg-type]
        tmp_path,
    ) == 0
    assert adapter.closed == 1


def test_bitwarden_actions_publish_keeps_every_github_call_in_selected_environment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env_file = tmp_path / ".env.production"
    example_file = tmp_path / ".env.example.production"
    write_template(example_file)
    adapter = FakeAdapter({"REGION": "eu", "API_KEY": "synthetic"})
    store = prepare_dispatch(monkeypatch, tmp_path, adapter)
    calls: list[list[str]] = []
    secret_lists = 0
    variable_lists = 0

    def fake_run(command: list[str], **kwargs: object) -> object:
        nonlocal secret_lists, variable_lists
        _assert_clean_child_environment(kwargs)
        calls.append(command)
        if command[:2] == ["gh", "api"]:
            return result()
        if command[:3] == ["gh", "secret", "list"]:
            secret_lists += 1
            return result("[]" if secret_lists == 1 else '[{"name":"API_KEY","updatedAt":"secret-revision"}]')
        if command[:3] == ["gh", "variable", "list"]:
            variable_lists += 1
            return result("[]" if variable_lists == 1 else '[{"name":"REGION","value":"eu","updatedAt":"variable-revision"}]')
        return result()

    monkeypatch.setattr("gh_vault.actions.subprocess.run", fake_run)

    assert cli.dispatch(
        publish_args(
            env_file,
            repo="github.example/owner/repo",
            apply=True,
            github_environment="release/2026",
        ),  # type: ignore[arg-type]
        store,  # type: ignore[arg-type]
        tmp_path,
    ) == 0

    assert calls[0] == [
        "gh",
        "api",
        "repos/owner/repo/environments/release%2F2026",
        "--hostname",
        "github.example",
    ]
    for command in calls[1:]:
        assert command[0] == "gh"
        assert "--repo" in command
        assert command[command.index("--repo") + 1] == "github.example/owner/repo"
        assert "--env" in command
        assert command[command.index("--env") + 1] == "release/2026"


def test_bitwarden_actions_publish_rejects_empty_values_before_github_access(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env_file = tmp_path / ".env"
    example_file = tmp_path / ".env.example"
    write_template(example_file)
    adapter = FakeAdapter({"REGION": "", "API_KEY": "synthetic"})
    store = prepare_dispatch(monkeypatch, tmp_path, adapter)
    monkeypatch.setattr(
        "gh_vault.actions.subprocess.run",
        lambda *args, **kwargs: pytest.fail("GitHub must not be accessed"),
    )

    with pytest.raises(StoreError, match="standby value REGION must not be empty"):
        cli.dispatch(
            publish_args(env_file, example_file=example_file, apply=True),  # type: ignore[arg-type]
            store,  # type: ignore[arg-type]
            tmp_path,
        )


def test_bitwarden_actions_publish_rejects_type_drift_before_writes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env_file = tmp_path / ".env"
    example_file = tmp_path / ".env.example"
    write_template(example_file)
    adapter = FakeAdapter({"REGION": "eu", "API_KEY": "synthetic"})
    store = prepare_dispatch(monkeypatch, tmp_path, adapter)
    calls: list[list[str]] = []

    def fake_run(command: list[str], **kwargs: object) -> object:
        _assert_clean_child_environment(kwargs)
        calls.append(command)
        if command[:3] == ["gh", "secret", "list"]:
            return result('[{"name":"REGION","updatedAt":"revision"}]')
        if command[:3] == ["gh", "variable", "list"]:
            return result("[]")
        raise AssertionError("write attempted after type drift")

    monkeypatch.setattr("gh_vault.actions.subprocess.run", fake_run)

    with pytest.raises(StoreError, match="REGION exists as a GitHub secret"):
        cli.dispatch(
            publish_args(env_file, example_file=example_file, apply=True),  # type: ignore[arg-type]
            store,  # type: ignore[arg-type]
            tmp_path,
        )
    assert [command[:3] for command in calls] == [
        ["gh", "secret", "list"],
        ["gh", "variable", "list"],
    ]


def test_bitwarden_actions_publish_records_partial_failure_without_child_diagnostics(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env_file = tmp_path / ".env"
    example_file = tmp_path / ".env.example"
    write_template(example_file)
    adapter = FakeAdapter({"REGION": "eu", "API_KEY": "synthetic-secret-value"})
    store = prepare_dispatch(monkeypatch, tmp_path, adapter)
    secret_lists = 0
    variable_lists = 0
    leaked = "hostile-child-diagnostic-synthetic-secret-value"

    def fake_run(command: list[str], **kwargs: object) -> object:
        nonlocal secret_lists, variable_lists
        _assert_clean_child_environment(kwargs)
        if command[:3] == ["gh", "secret", "list"]:
            secret_lists += 1
            return result("[]")
        if command[:3] == ["gh", "variable", "list"]:
            variable_lists += 1
            return result("[]" if variable_lists == 1 else '[{"name":"REGION","value":"eu","updatedAt":"variable-revision"}]')
        if command[:3] == ["gh", "variable", "set"]:
            return result()
        if command[:3] == ["gh", "secret", "set"]:
            return result(returncode=1, stderr=leaked)
        raise AssertionError(f"unexpected command: {command}")

    monkeypatch.setattr("gh_vault.actions.subprocess.run", fake_run)

    with pytest.raises(StoreError, match="publication failed after 1 of 2 value") as caught:
        cli.dispatch(
            publish_args(env_file, example_file=example_file, apply=True),  # type: ignore[arg-type]
            store,  # type: ignore[arg-type]
            tmp_path,
        )

    assert leaked not in str(caught.value)
    metadata_path = (
        store.config_dir
        / "publications"
        / "github.com"
        / "source"
        / "repo"
        / "env.standby.json"
    )
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert metadata["status"] == "failure"
    assert metadata["failed_key"] == "API_KEY"
    assert metadata["entries"] == [
        {
            "kind": "variable",
            "name": "REGION",
            "operation": "create",
            "remote_revision": "variable-revision",
            "result": "value-verified",
            "source_id": ENTRY_IDS["REGION"],
        },
        {
            "kind": "secret",
            "name": "API_KEY",
            "operation": "create",
            "remote_revision": None,
            "result": "failed",
            "source_id": ENTRY_IDS["API_KEY"],
        },
    ]
    serialized = json.dumps(metadata)
    assert leaked not in serialized
    assert "synthetic-secret-value" not in serialized


def test_bitwarden_actions_publish_rejects_changed_variable_readback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env_file = tmp_path / ".env"
    example_file = tmp_path / ".env.example"
    example_file.write_text("# gh-vault: variable\n# REGION=\n", encoding="utf-8")
    adapter = FakeAdapter({"REGION": "expected"})
    store = prepare_dispatch(monkeypatch, tmp_path, adapter)
    variable_lists = 0

    def fake_run(command: list[str], **kwargs: object) -> object:
        nonlocal variable_lists
        _assert_clean_child_environment(kwargs)
        if command[:3] == ["gh", "secret", "list"]:
            return result("[]")
        if command[:3] == ["gh", "variable", "list"]:
            variable_lists += 1
            return result("[]" if variable_lists == 1 else '[{"name":"REGION","value":"changed","updatedAt":"revision"}]')
        return result()

    monkeypatch.setattr("gh_vault.actions.subprocess.run", fake_run)

    with pytest.raises(StoreError, match="variable REGION read-back did not match"):
        cli.dispatch(
            publish_args(env_file, example_file=example_file, apply=True),  # type: ignore[arg-type]
            store,  # type: ignore[arg-type]
            tmp_path,
        )


def test_bitwarden_actions_publish_rejects_profile_references_before_credentials(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env_file = tmp_path / ".env"
    example_file = tmp_path / ".env.example"
    example_file.write_text(
        "# gh-vault: secret release\n# API_KEY=\n",
        encoding="utf-8",
    )

    class NoAccessStore:
        def get_bitwarden_connection(self, name: str) -> BitwardenConnection:
            raise AssertionError("connection metadata must not be read")

    monkeypatch.setattr(cli, "load_local_adapter", lambda *args, **kwargs: pytest.fail("adapter must not load"))

    with pytest.raises(StoreError, match="profile references cannot be published to GitHub"):
        cli.dispatch(
            publish_args(env_file, example_file=example_file),  # type: ignore[arg-type]
            NoAccessStore(),  # type: ignore[arg-type]
            tmp_path,
        )


def test_bitwarden_actions_publish_does_not_leak_child_diagnostics_through_stderr(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env_file = tmp_path / ".env"
    example_file = tmp_path / ".env.example"
    write_template(example_file)
    adapter = FakeAdapter({"REGION": "eu-central-1", "API_KEY": "synthetic-secret-value"})
    store = prepare_dispatch(monkeypatch, tmp_path, adapter)
    leaked = "gh diagnostic leak: synthetic-secret-value"

    def fake_run(command: list[str], **kwargs: object) -> object:
        _assert_clean_child_environment(kwargs)
        if command[:3] == ["gh", "secret", "list"]:
            return result("[]")
        if command[:3] == ["gh", "variable", "list"]:
            return result("[]")
        if command[:3] in (["gh", "variable", "set"], ["gh", "secret", "set"]):
            return result(returncode=1, stderr=leaked)
        raise AssertionError(f"unexpected command: {command}")

    monkeypatch.setattr("gh_vault.actions.subprocess.run", fake_run)

    with pytest.raises(StoreError) as caught:
        cli.dispatch(
            publish_args(env_file, example_file=example_file, apply=True),  # type: ignore[arg-type]
            store,  # type: ignore[arg-type]
            tmp_path,
        )

    assert leaked not in str(caught.value)
    captured = os.environ.copy()
    assert "BWS_ACCESS_TOKEN" in captured
