from __future__ import annotations

import stat
from pathlib import Path

import pytest

from gh_vault.actions import ActionValue, RemoteValueStatus, SyncResult, action_values, check_workflows, export_act, import_variables, remote_secret_status, runtime_environment, sync
from gh_vault.envfiles import DotenvAssignment, archive_environment, list_environments, parse_dotenv, parse_typed_dotenv, project_namespace, restore_environment
from gh_vault.github import inspect_token
from gh_vault.store import StoreError


class MemoryVault:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def put_secret(self, name: str, value: str) -> None:
        self.values[name] = value

    def get_secret(self, name: str) -> str:
        try:
            return self.values[name]
        except KeyError as exc:
            raise StoreError(f"missing test secret: {name}") from exc

    def remove_secret(self, name: str) -> None:
        self.values.pop(name, None)


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


def test_parse_typed_dotenv_classifies_adjacent_directives(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text(
        "# gh-vault: variable\nREGION=eu\n# gh-vault: secret\nexport API_KEY='synthetic'\nLOCAL_ONLY=local\n",
        encoding="utf-8",
    )

    assert parse_typed_dotenv(env) == (
        DotenvAssignment("REGION", "eu", "variable", 2, False),
        DotenvAssignment("API_KEY", "synthetic", "secret", 4, False),
        DotenvAssignment("LOCAL_ONLY", "local", "local", 5, False),
    )
    assert parse_dotenv(env) == {"REGION": "eu", "API_KEY": "synthetic", "LOCAL_ONLY": "local"}


def test_parse_typed_dotenv_reads_commented_template_assignments(tmp_path: Path) -> None:
    env = tmp_path / ".env.example"
    env.write_text(
        "# Free-form comment.\n# gh-vault: variable\n# REGION=eu\n# gh-vault: secret\n# API_KEY=\n# LOCAL_ONLY=local\n",
        encoding="utf-8",
    )

    assert parse_typed_dotenv(env, include_commented=True) == (
        DotenvAssignment("REGION", "eu", "variable", 3, True),
        DotenvAssignment("API_KEY", "", "secret", 5, True),
        DotenvAssignment("LOCAL_ONLY", "local", "local", 6, True),
    )
    assert parse_dotenv(env) == {}


@pytest.mark.parametrize(
    "contents",
    [
        "# gh-vault: secret\n\nAPI_KEY=value\n",
        "# gh-vault: secret\n# explanation\nAPI_KEY=value\n",
        "# gh-vault: secret\n",
    ],
)
def test_parse_typed_dotenv_requires_strict_directive_adjacency(tmp_path: Path, contents: str) -> None:
    env = tmp_path / ".env"
    env.write_text(contents, encoding="utf-8")

    with pytest.raises(StoreError, match="directive must be followed immediately by an assignment"):
        parse_typed_dotenv(env)


def test_parse_typed_dotenv_rejects_invalid_directive(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("# gh-vault: public\nVALUE=synthetic\n", encoding="utf-8")

    with pytest.raises(StoreError, match="invalid gh-vault directive"):
        parse_typed_dotenv(env)


def test_parse_typed_dotenv_rejects_duplicate_keys(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("VALUE=first\n# gh-vault: secret\nVALUE=second\n", encoding="utf-8")

    with pytest.raises(StoreError, match="duplicate dotenv key VALUE"):
        parse_typed_dotenv(env)


@pytest.mark.parametrize("key", ["GH_VAR_REGION", "GH_SECRET_API_KEY"])
def test_parse_typed_dotenv_rejects_legacy_prefixes(tmp_path: Path, key: str) -> None:
    env = tmp_path / ".env"
    env.write_text(f"{key}=synthetic\n", encoding="utf-8")

    with pytest.raises(StoreError, match="legacy GH_VAR_/GH_SECRET_ declaration"):
        parse_typed_dotenv(env)


def test_runtime_environment_injects_only_declared_actions_values(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text(
        "LOCAL_ONLY=local\n# gh-vault: variable\nREGION=eu\n# gh-vault: secret\nAPI_KEY=synthetic\n# gh-vault: secret\nGITHUB_TOKEN=reserved\n",
        encoding="utf-8",
    )

    assert runtime_environment(env) == {"REGION": "eu", "API_KEY": "synthetic"}


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


def test_archive_lists_and_restores_named_environments(monkeypatch, tmp_path: Path) -> None:
    class Result:
        returncode = 0
        stdout = "https://github.com/owner/repo.git\n"

    monkeypatch.setattr("gh_vault.envfiles.subprocess.run", lambda *args, **kwargs: Result())
    vault = MemoryVault()
    production = tmp_path / ".env.production"
    development = tmp_path / ".env.development"
    production_example = tmp_path / ".env.example.production"
    production.write_text("API_KEY=production\n", encoding="utf-8")
    development.write_text("API_KEY=development\n", encoding="utf-8")
    production_example.write_text("# Production\nAPI_KEY=\n", encoding="utf-8")

    archive_environment(vault, tmp_path, production, production_example)  # type: ignore[arg-type]
    archive_environment(vault, tmp_path, development, tmp_path / ".env.example.development")  # type: ignore[arg-type]
    assert list_environments(vault, tmp_path) == ("github.com/owner/repo", [("development", False), ("production", True)])  # type: ignore[arg-type]

    production.unlink()
    production_example.unlink()
    restore_environment(vault, tmp_path, production, production_example, False, False)  # type: ignore[arg-type]
    assert production.read_text(encoding="utf-8") == "# Production\nAPI_KEY=production\n"


def test_list_and_restore_support_legacy_default_archive(monkeypatch, tmp_path: Path) -> None:
    class Result:
        returncode = 0
        stdout = "https://github.com/owner/repo.git\n"

    monkeypatch.setattr("gh_vault.envfiles.subprocess.run", lambda *args, **kwargs: Result())
    vault = MemoryVault()
    base = "projects/github.com/owner/repo"
    vault.values[f"{base}/env.json"] = '{"origin": "https://github.com/owner/repo.git", "values": {"API_KEY": "legacy"}, "version": 1}'
    vault.values[f"{base}/env.example"] = "API_KEY=\n"

    assert list_environments(vault, tmp_path) == ("github.com/owner/repo", [("default", True)])  # type: ignore[arg-type]
    restore_environment(vault, tmp_path, tmp_path / ".env", tmp_path / ".env.example", False, False)  # type: ignore[arg-type]
    assert (tmp_path / ".env").read_text(encoding="utf-8") == "API_KEY=legacy\n"


def test_export_act_and_workflow_check(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("# gh-vault: secret\nAPI_KEY=alpha\n# gh-vault: variable\nREGION=eu\nLOCAL_ONLY=local\n", encoding="utf-8")
    entries = action_values(env)
    assert entries == [ActionValue("API_KEY", "secret", "alpha"), ActionValue("REGION", "variable", "eu")]
    assert [entry.line for entry in entries] == [2, 4]
    secrets, variables = export_act(entries, tmp_path / ".secrets", tmp_path / ".vars")
    assert (secrets, variables) == (1, 1)
    assert (tmp_path / ".secrets").read_text(encoding="utf-8") == "API_KEY=alpha\n"
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "ci.yml").write_text("env:\n  API_KEY: ${{ secrets.API_KEY }}\n  REGION: ${{ vars.REGION }}\n", encoding="utf-8")
    assert check_workflows(tmp_path, entries) == {"unreferenced": [], "type_mismatch": [], "order": [], "orphan": []}


def test_workflow_check_omits_defaulted_and_github_orphans(tmp_path: Path) -> None:
    workflow_dir = tmp_path / ".github" / "workflows"
    workflow_dir.mkdir(parents=True)
    (workflow_dir / "check.yml").write_text(
        "env:\n"
        "  DEFAULTED: ${{ vars.DEFAULTED || 'fallback' }}\n"
        "  CHAINED: ${{ secrets.CHAINED || vars.CHAINED || 'fallback' }}\n"
        "  GITHUB: ${{ secrets.GITHUB_TOKEN }}\n"
        "  RUNNER: ${{ vars.RUNNER_OS }}\n"
        "  CI: ${{ vars.CI }}\n"
        "  GH: ${{ secrets.GH_TOKEN }}\n"
        "  REQUIRED: ${{ secrets.REQUIRED }}\n",
        encoding="utf-8",
    )

    assert check_workflows(tmp_path, []) == {
        "unreferenced": [],
        "type_mismatch": [],
        "order": [],
        "orphan": [{"file": "check.yml", "line": 8, "severity": "warning", "name": "REQUIRED", "message": "secrets.REQUIRED is not declared locally and has no fallback default"}],
    }


def test_import_variables_preserves_existing_values_without_force(monkeypatch, tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("# Deployment\n# gh-vault: variable\nREGION=local\nOTHER=value\n", encoding="utf-8")
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
    assert env.read_text(encoding="utf-8") == "# Deployment\n# gh-vault: variable\nREGION=local\nOTHER=value\n\n# gh-vault: variable\nMODE=production\n"
    assert stat.S_IMODE(env.stat().st_mode) == 0o600
    assert calls == [["gh", "variable", "list", "--repo", "owner/repo", "--json", "name,value"]]


def test_import_variables_uses_example_and_force_overwrites(monkeypatch, tmp_path: Path) -> None:
    example = tmp_path / ".env.example"
    example.write_text("# gh-vault: variable\n# REGION=local\n", encoding="utf-8")

    class Result:
        returncode = 0
        stderr = ""
        stdout = '[{"name":"REGION","value":"remote"}]'

    monkeypatch.setattr("gh_vault.actions.subprocess.run", lambda *args, **kwargs: Result())

    assert import_variables(tmp_path, "owner/repo", True) == (example, 1)
    assert example.read_text(encoding="utf-8") == "# gh-vault: variable\n# REGION=remote\n"


def test_import_variables_does_not_reclassify_local_values(monkeypatch, tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("REGION=local\n", encoding="utf-8")

    class Result:
        returncode = 0
        stderr = ""
        stdout = '[{"name":"REGION","value":"remote"}]'

    monkeypatch.setattr("gh_vault.actions.subprocess.run", lambda *args, **kwargs: Result())

    with pytest.raises(StoreError, match="local declaration is local"):
        import_variables(tmp_path, "owner/repo", True)
    assert env.read_text(encoding="utf-8") == "REGION=local\n"


def test_import_variables_reports_a_missing_target(tmp_path: Path) -> None:
    with pytest.raises(StoreError, match="cannot read"):
        import_variables(tmp_path, "owner/repo", False)


def test_remote_secret_status_identifies_secret_variable_type_drift(monkeypatch, tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text(
        "# gh-vault: secret\nCONFIGURED=value\n# gh-vault: secret\nSIGNIN_CLIENT_ID=client\n# gh-vault: secret\nMISSING=\n# gh-vault: variable\nJMED_SMTP_FROM=sender\n",
        encoding="utf-8",
    )
    calls: list[list[str]] = []

    class Result:
        returncode = 0
        stderr = ""
        def __init__(self, stdout: str) -> None:
            self.stdout = stdout

    def fake_run(command: list[str], **kwargs: object) -> Result:
        calls.append(command)
        return Result("CONFIGURED\nJMED_SMTP_FROM\nORPHAN\n" if command[1] == "secret" else "SIGNIN_CLIENT_ID\n")

    monkeypatch.setattr("gh_vault.actions.subprocess.run", fake_run)

    assert remote_secret_status(env, "owner/repo") == RemoteValueStatus(["MISSING"], [], ["ORPHAN"], [], ["SIGNIN_CLIENT_ID"], ["JMED_SMTP_FROM"])
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
    assert sync([ActionValue("API_KEY", "secret", "alpha")], "owner/repo", False, True) == SyncResult(1, 0)
    assert calls == [
        (["gh", "secret", "list", "--repo", "owner/repo", "--json", "name", "--jq", ".[].name"], None),
        (["gh", "variable", "list", "--repo", "owner/repo", "--json", "name", "--jq", ".[].name"], None),
        (["gh", "variable", "delete", "API_KEY", "--repo", "owner/repo"], None),
        (["gh", "secret", "set", "API_KEY", "--repo", "owner/repo"], "alpha"),
    ]


def test_sync_prunes_only_remote_names_absent_from_env(monkeypatch) -> None:
    calls: list[tuple[list[str], str | None]] = []

    class Result:
        returncode = 0
        stderr = ""

        def __init__(self, stdout: str = "") -> None:
            self.stdout = stdout

    def fake_run(command: list[str], **kwargs: object) -> Result:
        input_value = kwargs.get("input")
        calls.append((command, input_value if isinstance(input_value, str) else None))
        if command[:3] == ["gh", "secret", "list"]:
            return Result("CONFIGURED\nSTALE_SECRET\n")
        if command[:3] == ["gh", "variable", "list"]:
            return Result("CONFIGURED\nSTALE_VARIABLE\n")
        return Result()

    monkeypatch.setattr("gh_vault.actions.subprocess.run", fake_run)
    assert sync([ActionValue("CONFIGURED", "secret", "alpha")], "owner/repo", False, prune=True) == SyncResult(1, 2)
    assert calls == [
        (["gh", "secret", "list", "--repo", "owner/repo", "--json", "name", "--jq", ".[].name"], None),
        (["gh", "variable", "list", "--repo", "owner/repo", "--json", "name", "--jq", ".[].name"], None),
        (["gh", "secret", "remove", "STALE_SECRET", "--repo", "owner/repo"], None),
        (["gh", "variable", "delete", "STALE_VARIABLE", "--repo", "owner/repo"], None),
        (["gh", "secret", "set", "CONFIGURED", "--repo", "owner/repo"], "alpha"),
    ]
