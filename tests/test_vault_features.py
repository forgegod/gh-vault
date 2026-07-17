from __future__ import annotations

import stat
from pathlib import Path

import pytest

from gh_vault.actions import ActionValue, action_values, check_workflows, export_act, import_variables, remote_secret_status, sync
from gh_vault.envfiles import archive_environment, parse_dotenv, project_namespace, restore_environment
from gh_vault.github import inspect_token
from gh_vault.store import StoreError


class MemoryVault:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def put_secret(self, name: str, value: str) -> None:
        self.values[name] = value

    def get_secret(self, name: str) -> str:
        return self.values[name]


def test_project_namespace_normalizes_ssh_origin(monkeypatch, tmp_path: Path) -> None:
    class Result:
        returncode = 0
        stdout = "git@github.com:owner/repo.git\n"
    monkeypatch.setattr("gh_vault.envfiles.subprocess.run", lambda *args, **kwargs: Result())
    assert project_namespace(tmp_path) == ("github.com/owner/repo", "git@github.com:owner/repo.git")


@pytest.mark.parametrize(
    "origin, expected",
    [
        ("https://github.com/owner/repo.git\n", "github.com/owner/repo"),
        ("ssh://git@github.com/owner/repo.git\n", "github.com/owner/repo"),
    ],
)
def test_project_namespace_normalizes_url_origins(monkeypatch, tmp_path: Path, origin: str, expected: str) -> None:
    class Result:
        returncode = 0
        stdout = origin

    monkeypatch.setattr("gh_vault.envfiles.subprocess.run", lambda *args, **kwargs: Result())

    assert project_namespace(tmp_path) == (expected, origin.strip())


@pytest.mark.parametrize(
    "origin",
    [
        "https://github.com/owner//repo.git\n",
        "https://github.com/owner/repo.git?ref=main\n",
        "git@github.com:owner/../repo.git\n",
    ],
)
def test_project_namespace_rejects_unsafe_origins(monkeypatch, tmp_path: Path, origin: str) -> None:
    class Result:
        returncode = 0
        stdout = origin

    monkeypatch.setattr("gh_vault.envfiles.subprocess.run", lambda *args, **kwargs: Result())

    with pytest.raises(StoreError, match="safe project namespace"):
        project_namespace(tmp_path)


def test_parse_dotenv_decodes_explicit_values_without_sourcing(tmp_path: Path) -> None:
    payload = tmp_path / "payload.txt"
    payload.write_text("from-file\n", encoding="utf-8")
    env = tmp_path / ".env"
    env.write_text(
        "PLAIN=value # comment\nQUOTED=\"two words\"\nFILE=@file:payload.txt\nMULTILINE=@base64:bGluZTEKbGluZTI=\n",
        encoding="utf-8",
    )

    assert parse_dotenv(env) == {
        "PLAIN": "value",
        "QUOTED": "two words",
        "FILE": "from-file\n",
        "MULTILINE": "line1\nline2",
    }


def test_parse_dotenv_rejects_shell_syntax(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("VALUE=$(printf unsafe)\n", encoding="utf-8")

    with pytest.raises(StoreError, match="unsupported dotenv syntax"):
        parse_dotenv(env)


def test_inspect_token_reads_scope_and_expiration_headers(monkeypatch) -> None:
    observed: dict[str, object] = {}

    class Response:
        headers = {
            "X-OAuth-Scopes": "repo, workflow",
            "GitHub-Authentication-Token-Expiration": "2026-12-31 23:59:59 UTC",
        }

        def __enter__(self) -> "Response":
            return self

        def __exit__(self, *args: object) -> None:
            pass

    def fake_urlopen(request, timeout: int) -> Response:
        observed.update(url=request.full_url, authorization=request.get_header("Authorization"), timeout=timeout)
        return Response()

    monkeypatch.setattr("gh_vault.github.urlopen", fake_urlopen)

    metadata = inspect_token("token-value")

    assert metadata.scopes == ("repo", "workflow")
    assert metadata.expires_at == "2026-12-31 23:59:59 UTC"
    assert observed == {"url": "https://api.github.com/user", "authorization": "Bearer token-value", "timeout": 10}


def test_archive_and_restore_uses_template_comments(monkeypatch, tmp_path: Path) -> None:
    class Result:
        returncode = 0
        stdout = "https://github.com/owner/repo.git\n"
    monkeypatch.setattr("gh_vault.envfiles.subprocess.run", lambda *args, **kwargs: Result())
    env = tmp_path / ".env"
    example = tmp_path / ".env.example"
    env.write_text("API_KEY=alpha\nEXTRA=beta\n", encoding="utf-8")
    example.write_text("# API access\nAPI_KEY=\n", encoding="utf-8")
    vault = MemoryVault()
    archive_environment(vault, tmp_path, env, example)  # type: ignore[arg-type]
    env.unlink()
    restore_environment(vault, tmp_path, env, example, False, False)  # type: ignore[arg-type]
    assert env.read_text(encoding="utf-8") == "# API access\nAPI_KEY=alpha\n\n# Local additions\nEXTRA=beta\n"
    assert stat.S_IMODE(env.stat().st_mode) == 0o600


def test_export_act_and_workflow_check(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("GH_SECRET_API_KEY=alpha\nGH_VAR_REGION=eu\n", encoding="utf-8")
    entries = action_values(env)
    secrets, variables = export_act(entries, tmp_path / ".secrets", tmp_path / ".vars")
    assert (secrets, variables) == (1, 1)
    assert (tmp_path / ".secrets").read_text(encoding="utf-8") == "API_KEY=alpha\n"
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "ci.yml").write_text("env:\n  API_KEY: ${{ secrets.API_KEY }}\n  REGION: ${{ vars.REGION }}\n", encoding="utf-8")
    assert check_workflows(tmp_path, entries) == {"unreferenced": [], "type_mismatch": [], "order": [], "orphan": []}


def test_import_variables_preserves_existing_values_without_force(monkeypatch, tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("# Deployment\nGH_VAR_REGION=local\nOTHER=value\n", encoding="utf-8")
    calls: list[list[str]] = []

    class Result:
        returncode = 0
        stderr = ""
        stdout = '[{"name":"REGION","value":"remote"},{"name":"MODE","value":"production"}]'

    def fake_run(command: list[str], **kwargs: object) -> Result:
        calls.append(command)
        return Result()

    monkeypatch.setattr("gh_vault.actions.subprocess.run", fake_run)

    assert import_variables(tmp_path, "owner/repo", False) == (env, 1)
    assert env.read_text(encoding="utf-8") == "# Deployment\nGH_VAR_REGION=local\nOTHER=value\n\n# Local additions\nGH_VAR_MODE=production\n"
    assert stat.S_IMODE(env.stat().st_mode) == 0o600
    assert calls == [["gh", "variable", "list", "--repo", "owner/repo", "--json", "name,value"]]


def test_import_variables_uses_example_and_force_overwrites(monkeypatch, tmp_path: Path) -> None:
    example = tmp_path / ".env.example"
    example.write_text("GH_VAR_REGION=local\n", encoding="utf-8")

    class Result:
        returncode = 0
        stderr = ""
        stdout = '[{"name":"REGION","value":"remote"}]'

    monkeypatch.setattr("gh_vault.actions.subprocess.run", lambda *args, **kwargs: Result())

    assert import_variables(tmp_path, "owner/repo", True) == (example, 1)
    assert example.read_text(encoding="utf-8") == "GH_VAR_REGION=remote\n"


def test_remote_secret_status_identifies_secret_variable_type_drift(monkeypatch, tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("GH_SECRET_CONFIGURED=value\nGH_SECRET_MIGRATED=\nGH_SECRET_MISSING=\nGH_VAR_JMED_SMTP_FROM=sender\n", encoding="utf-8")
    calls: list[list[str]] = []

    class Result:
        returncode = 0
        stderr = ""
        def __init__(self, stdout: str) -> None:
            self.stdout = stdout

    def fake_run(command: list[str], **kwargs: object) -> Result:
        calls.append(command)
        return Result("CONFIGURED\nJMED_SMTP_FROM\nORPHAN\n" if command[1] == "secret" else "MIGRATED\n")

    monkeypatch.setattr("gh_vault.actions.subprocess.run", fake_run)

    assert remote_secret_status(env, "owner/repo") == (["MISSING"], ["MIGRATED"], ["ORPHAN"], ["JMED_SMTP_FROM"])
    assert calls == [
        ["gh", "secret", "list", "--repo", "owner/repo", "--json", "name", "--jq", ".[].name"],
        ["gh", "variable", "list", "--repo", "owner/repo", "--json", "name", "--jq", ".[].name"],
    ]


def test_sync_migrates_a_stale_opposite_type_without_argv_value(monkeypatch) -> None:
    calls: list[tuple[list[str], str | None]] = []

    class Result:
        returncode = 0
        stderr = ""

        def __init__(self, stdout: str = "") -> None:
            self.stdout = stdout

    def fake_run(command: list[str], **kwargs: object) -> Result:
        input_value = kwargs.get("input")
        calls.append((command, input_value if isinstance(input_value, str) else None))
        if command[:3] == ["gh", "variable", "list"]:
            return Result("API_KEY\n")
        return Result()

    monkeypatch.setattr("gh_vault.actions.subprocess.run", fake_run)
    assert sync([ActionValue("API_KEY", "secret", "alpha")], "owner/repo", False, True) == 1
    assert calls == [
        (["gh", "secret", "list", "--repo", "owner/repo", "--json", "name", "--jq", ".[].name"], None),
        (["gh", "variable", "list", "--repo", "owner/repo", "--json", "name", "--jq", ".[].name"], None),
        (["gh", "variable", "delete", "API_KEY", "--repo", "owner/repo"], None),
        (["gh", "secret", "set", "API_KEY", "--repo", "owner/repo"], "alpha"),
    ]
