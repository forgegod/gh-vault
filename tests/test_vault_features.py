from __future__ import annotations

import stat
from pathlib import Path

import pytest

from gh_vault.actions import ActionValue, RemoteValueStatus, SyncResult, action_values, check_workflows, export_act, import_variables, migrate_env_source, remote_secret_status, run_act, runtime_environment, sync
from gh_vault.envfiles import ArchiveMigrationResult, DotenvAssignment, archive_environment, list_environments, migrate_environment_archive, parse_dotenv, parse_typed_dotenv, project_namespace, restore_environment, show_environment
from gh_vault.github import inspect_token
from gh_vault.store import EnvironmentStore, Profile, StoreError


class MemoryVault:
    def __init__(self, profiles: dict[str, str] | None = None) -> None:
        self.values: dict[str, str] = dict(profiles or {})

    def put_secret(self, name: str, value: str) -> None:
        self.values[name] = value

    def get_secret(self, name: str) -> str:
        try:
            return self.values[name]
        except KeyError as exc:
            raise StoreError(f"missing test secret: {name}") from exc

    def remove_secret(self, name: str) -> None:
        self.values.pop(name, None)

    def get(self, name: str) -> str:
        return self.get_secret(name)

    def profiles(self) -> list[Profile]:
        return [Profile(name) for name in sorted(self.values)]


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

    assert runtime_environment(env, MemoryVault()) == {"REGION": "eu", "API_KEY": "synthetic"}


def test_parse_typed_dotenv_records_profile_reference(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text(
        "# gh-vault: secret hermes-agent\nGITHUB_TOKEN=\nLOCAL_ONLY=local\n",
        encoding="utf-8",
    )

    assert parse_typed_dotenv(env) == (
        DotenvAssignment("GITHUB_TOKEN", "", "secret", 2, False, "hermes-agent"),
        DotenvAssignment("LOCAL_ONLY", "local", "local", 3, False, None),
    )


def test_parse_typed_dotenv_rejects_variable_profile_reference(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("# gh-vault: variable hermes-agent\nGITHUB_TOKEN=\n", encoding="utf-8")

    with pytest.raises(StoreError, match="only valid for 'secret' directives"):
        parse_typed_dotenv(env)


def test_parse_typed_dotenv_rejects_invalid_profile_reference(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("# gh-vault: secret -leading-dash\nTOKEN=\n", encoding="utf-8")

    with pytest.raises(StoreError, match="invalid gh-vault profile reference"):
        parse_typed_dotenv(env)


def test_parse_typed_dotenv_rejects_unknown_directive_token(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("# gh-vault: public profile\nVALUE=synthetic\n", encoding="utf-8")

    with pytest.raises(StoreError, match="only valid for 'secret' directives"):
        parse_typed_dotenv(env)


def test_parse_typed_dotenv_rejects_variable_with_profile_token(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("# gh-vault: variable eu-deploy\nREGION=\n", encoding="utf-8")

    with pytest.raises(StoreError, match="only valid for 'secret' directives"):
        parse_typed_dotenv(env)


def test_runtime_environment_resolves_profile_references(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text(
        "# gh-vault: secret hermes-agent\nGITHUB_TOKEN=\nLOCAL_ONLY=local\n# gh-vault: secret release-write\nDEPLOY_TOKEN=\n",
        encoding="utf-8",
    )
    vault = MemoryVault({"hermes-agent": "synthetic-agent-token", "release-write": "synthetic-deploy-token"})

    assert runtime_environment(env, vault) == {  # type: ignore[arg-type]
        "GITHUB_TOKEN": "synthetic-agent-token",
        "DEPLOY_TOKEN": "synthetic-deploy-token",
    }


def test_runtime_environment_rejects_unknown_profile(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("# gh-vault: secret ghost\nTOKEN=\n", encoding="utf-8")
    vault = MemoryVault({"other": "value"})

    with pytest.raises(StoreError, match="is not configured"):
        runtime_environment(env, vault)  # type: ignore[arg-type]


def test_action_values_resolves_profile_references(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text(
        "# gh-vault: secret hermes-agent\nGITHUB_TOKEN=\n# gh-vault: secret\nAPI_KEY=synthetic\n# gh-vault: variable\nREGION=eu\n",
        encoding="utf-8",
    )
    vault = MemoryVault({"hermes-agent": "synthetic-agent-token"})

    entries = action_values(env, vault)  # type: ignore[arg-type]
    by_name = {entry.name: entry for entry in entries}
    assert by_name["GITHUB_TOKEN"].kind == "secret"
    assert by_name["GITHUB_TOKEN"].value == "synthetic-agent-token"
    assert by_name["API_KEY"].value == "synthetic"
    assert by_name["REGION"].value == "eu"
    assert [entry.line for entry in entries] == [2, 4, 6]


def test_secret_sync_resolves_profile_references(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("# gh-vault: secret hermes-agent\nGITHUB_TOKEN=\n", encoding="utf-8")
    vault = MemoryVault({"hermes-agent": "synthetic-agent-token"})
    entries = action_values(env, vault)  # type: ignore[arg-type]

    assert [entry.name for entry in entries] == ["GITHUB_TOKEN"]
    assert [entry.value for entry in entries] == ["synthetic-agent-token"]
    assert all(entry.kind == "secret" for entry in entries)


def test_action_values_without_store_rejects_profile_reference(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("# gh-vault: secret hermes-agent\nGITHUB_TOKEN=\n", encoding="utf-8")

    with pytest.raises(StoreError, match="requires a vault store"):
        action_values(env)


def test_archive_environment_rejects_profile_references(monkeypatch, tmp_path: Path) -> None:
    class Result:
        returncode = 0
        stdout = "https://github.com/owner/repo.git\n"

    monkeypatch.setattr("gh_vault.envfiles.subprocess.run", lambda *args, **kwargs: Result())
    env = tmp_path / ".env"
    env.write_text("# gh-vault: secret hermes-agent\nGITHUB_TOKEN=\n", encoding="utf-8")
    example = tmp_path / ".env.example"
    vault = MemoryVault()
    public = EnvironmentStore(tmp_path / "config")

    with pytest.raises(StoreError, match="references vault profile 'hermes-agent'"):
        archive_environment(vault, public, tmp_path, env, example)  # type: ignore[arg-type]


def test_export_act_resolves_profile_referenced_secrets(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text(
        "# gh-vault: secret hermes-agent\nGITHUB_TOKEN=\n# gh-vault: variable\nREGION=eu\n# gh-vault: secret\nAPI_KEY=synthetic\n",
        encoding="utf-8",
    )
    vault = MemoryVault({"hermes-agent": "synthetic-agent-token"})
    secrets_path = tmp_path / ".secrets"
    variables_path = tmp_path / ".vars"

    entries = action_values(env, vault)  # type: ignore[arg-type]
    secrets, variables = export_act(entries, secrets_path, variables_path)

    assert (secrets, variables) == (2, 1)
    assert secrets_path.read_text(encoding="utf-8") == "GITHUB_TOKEN=synthetic-agent-token\nAPI_KEY=synthetic\n"
    assert variables_path.read_text(encoding="utf-8") == "REGION=eu\n"


def test_restore_environment_preserves_profile_reference_directive(monkeypatch, tmp_path: Path) -> None:
    class Result:
        returncode = 0
        stdout = "https://github.com/owner/repo.git\n"

    monkeypatch.setattr("gh_vault.envfiles.subprocess.run", lambda *args, **kwargs: Result())
    env = tmp_path / ".env"
    example = tmp_path / ".env.example"
    example.write_text("# gh-vault: secret hermes-agent\n# GITHUB_TOKEN=\n# gh-vault: variable\n# REGION=\n", encoding="utf-8")
    vault = MemoryVault({"hermes-agent": "synthetic-agent-token"})
    public = EnvironmentStore(tmp_path / "config")
    public.save_variables("github.com/owner/repo", "default", "https://github.com/owner/repo.git", {"REGION": "eu-test-1"})
    public.save_manifest("github.com/owner/repo", "https://github.com/owner/repo.git", {"default": {"variables": True, "secrets": False, "example": False}})

    restore_environment(vault, public, tmp_path, env, example, False, False)  # type: ignore[arg-type]
    rendered = env.read_text(encoding="utf-8")
    assert "# gh-vault: secret hermes-agent" in rendered
    assert "GITHUB_TOKEN=" in rendered
    assert "synthetic-agent-token" not in rendered
    assert "REGION=eu-test-1" in rendered


def test_parse_dotenv_rejects_shell_syntax(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("VALUE=$(printf unsafe)\n", encoding="utf-8")

    with pytest.raises(StoreError, match="unsupported dotenv syntax"):
        parse_dotenv(env)


def test_migrate_env_source_rewrites_environment_and_commented_template(tmp_path: Path) -> None:
    env = tmp_path / ".env.production"
    example = tmp_path / ".env.example.production"
    env.write_text("# Deployment\nGH_VAR_REGION=eu-west-1\nGH_SECRET_API_KEY=synthetic\nLOCAL_ONLY=keep\n", encoding="utf-8")
    example.write_text("# Template\n  # GH_VAR_REGION=eu-west-1\n# GH_SECRET_API_KEY=\n", encoding="utf-8")

    assert migrate_env_source(env) == (2, 2)
    assert env.read_text(encoding="utf-8") == "# Deployment\n# gh-vault: variable\nREGION=eu-west-1\n# gh-vault: secret\nAPI_KEY=synthetic\nLOCAL_ONLY=keep\n"
    assert example.read_text(encoding="utf-8") == "# Template\n  # gh-vault: variable\n  # REGION=eu-west-1\n# gh-vault: secret\n# API_KEY=\n"
    assert stat.S_IMODE(env.stat().st_mode) == 0o600
    assert stat.S_IMODE(example.stat().st_mode) == 0o600


def test_migrate_env_source_preflights_collisions_before_writing(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    original = "GH_VAR_REGION=remote\nREGION=local\n"
    env.write_text(original, encoding="utf-8")

    with pytest.raises(StoreError, match="collides with target key REGION"):
        migrate_env_source(env)
    assert env.read_text(encoding="utf-8") == original


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
    env.write_text("# gh-vault: secret\nAPI_KEY=alpha\n# gh-vault: variable\nREGION=eu-test-1\nEXTRA=local\n", encoding="utf-8")
    example.write_text("# API access\n# gh-vault: secret\n# API_KEY=\n# gh-vault: variable\n# REGION=\n# EXTRA=\n", encoding="utf-8")
    vault = MemoryVault()
    public = EnvironmentStore(tmp_path / "config")
    archive_environment(vault, public, tmp_path, env, example)  # type: ignore[arg-type]
    public_text = "".join(path.read_text(encoding="utf-8") for path in public.root.rglob("*.json"))
    assert "eu-test-1" in public_text
    assert "alpha" not in public_text
    assert "local" not in public_text
    assert show_environment(public, tmp_path, env)[1] == {"REGION": "eu-test-1"}
    env.unlink()
    restore_environment(vault, public, tmp_path, env, example, False, False)  # type: ignore[arg-type]
    assert env.read_text(encoding="utf-8") == "# API access\n# gh-vault: secret\nAPI_KEY=alpha\n# gh-vault: variable\nREGION=eu-test-1\n# EXTRA=\n"
    assert stat.S_IMODE(env.stat().st_mode) == 0o600


def test_archive_lists_and_restores_named_environments(monkeypatch, tmp_path: Path) -> None:
    class Result:
        returncode = 0
        stdout = "https://github.com/owner/repo.git\n"

    monkeypatch.setattr("gh_vault.envfiles.subprocess.run", lambda *args, **kwargs: Result())
    vault = MemoryVault()
    public = EnvironmentStore(tmp_path / "config")
    production = tmp_path / ".env.production"
    development = tmp_path / ".env.development"
    production_example = tmp_path / ".env.example.production"
    production.write_text("# gh-vault: variable\nREGION=production\n", encoding="utf-8")
    development.write_text("# gh-vault: variable\nREGION=development\n", encoding="utf-8")
    production_example.write_text("# Production\n# gh-vault: variable\n# REGION=\n", encoding="utf-8")

    archive_environment(vault, public, tmp_path, production, production_example)  # type: ignore[arg-type]
    archive_environment(vault, public, tmp_path, development, tmp_path / ".env.example.development")  # type: ignore[arg-type]
    assert list_environments(public, tmp_path) == ("github.com/owner/repo", [("development", False), ("production", False)])

    production.unlink()
    restore_environment(vault, public, tmp_path, production, production_example, False, False)  # type: ignore[arg-type]
    assert production.read_text(encoding="utf-8") == "# Production\n# gh-vault: variable\nREGION=production\n"


def test_list_and_restore_do_not_fallback_to_legacy_default_archive(monkeypatch, tmp_path: Path) -> None:
    class Result:
        returncode = 0
        stdout = "https://github.com/owner/repo.git\n"

    monkeypatch.setattr("gh_vault.envfiles.subprocess.run", lambda *args, **kwargs: Result())
    vault = MemoryVault()
    base = "projects/github.com/owner/repo"
    vault.values[f"{base}/env.json"] = '{"origin": "https://github.com/owner/repo.git", "values": {"API_KEY": "legacy"}, "version": 1}'
    public = EnvironmentStore(tmp_path / "config")

    assert list_environments(public, tmp_path) == ("github.com/owner/repo", [])
    with pytest.raises(StoreError, match="no archived environment"):
        restore_environment(vault, public, tmp_path, tmp_path / ".env", tmp_path / ".env.example", False, False)  # type: ignore[arg-type]


def test_restore_with_key_writes_a_single_directive_tagged_line(monkeypatch, tmp_path: Path) -> None:
    class Result:
        returncode = 0
        stdout = "https://github.com/owner/repo.git\n"

    monkeypatch.setattr("gh_vault.envfiles.subprocess.run", lambda *args, **kwargs: Result())
    env = tmp_path / ".env"
    example = tmp_path / ".env.example"
    env.write_text("# gh-vault: secret\nAPI_KEY=alpha\n# gh-vault: variable\nREGION=eu-test-1\n", encoding="utf-8")
    example.write_text("# gh-vault: secret\n# API_KEY=\n# gh-vault: variable\n# REGION=\n", encoding="utf-8")
    vault = MemoryVault()
    public = EnvironmentStore(tmp_path / "config")
    archive_environment(vault, public, tmp_path, env, example)  # type: ignore[arg-type]

    env.unlink()
    namespace = restore_environment(vault, public, tmp_path, env, example, False, False, "API_KEY")  # type: ignore[arg-type]
    assert namespace == "github.com/owner/repo"
    assert env.read_text(encoding="utf-8") == "# gh-vault: secret\nAPI_KEY=alpha\n"
    assert stat.S_IMODE(env.stat().st_mode) == 0o600

    env.unlink()
    restore_environment(vault, public, tmp_path, env, example, False, False, "REGION")  # type: ignore[arg-type]
    assert env.read_text(encoding="utf-8") == "# gh-vault: variable\nREGION=eu-test-1\n"


def test_restore_with_key_rejects_missing_key(monkeypatch, tmp_path: Path) -> None:
    class Result:
        returncode = 0
        stdout = "https://github.com/owner/repo.git\n"

    monkeypatch.setattr("gh_vault.envfiles.subprocess.run", lambda *args, **kwargs: Result())
    env = tmp_path / ".env"
    example = tmp_path / ".env.example"
    env.write_text("# gh-vault: secret\nAPI_KEY=alpha\n", encoding="utf-8")
    example.write_text("# gh-vault: secret\n# API_KEY=\n", encoding="utf-8")
    vault = MemoryVault()
    public = EnvironmentStore(tmp_path / "config")
    archive_environment(vault, public, tmp_path, env, example)  # type: ignore[arg-type]

    env.unlink()
    with pytest.raises(StoreError, match="not archived"):
        restore_environment(vault, public, tmp_path, env, example, False, False, "MISSING")  # type: ignore[arg-type]


def test_restore_with_key_rejects_combine_with_restore_example(monkeypatch, tmp_path: Path) -> None:
    class Result:
        returncode = 0
        stdout = "https://github.com/owner/repo.git\n"

    monkeypatch.setattr("gh_vault.envfiles.subprocess.run", lambda *args, **kwargs: Result())
    env = tmp_path / ".env"
    example = tmp_path / ".env.example"
    env.write_text("# gh-vault: secret\nAPI_KEY=alpha\n", encoding="utf-8")
    example.write_text("# gh-vault: secret\n# API_KEY=\n", encoding="utf-8")
    vault = MemoryVault()
    public = EnvironmentStore(tmp_path / "config")
    archive_environment(vault, public, tmp_path, env, example)  # type: ignore[arg-type]

    env.unlink()
    with pytest.raises(StoreError, match="--restore-example cannot be combined"):
        restore_environment(vault, public, tmp_path, env, example, False, True, "API_KEY")  # type: ignore[arg-type]


def test_restore_with_key_appends_to_existing_file_without_force(monkeypatch, tmp_path: Path) -> None:
    class Result:
        returncode = 0
        stdout = "https://github.com/owner/repo.git\n"

    monkeypatch.setattr("gh_vault.envfiles.subprocess.run", lambda *args, **kwargs: Result())
    env = tmp_path / ".env"
    example = tmp_path / ".env.example"
    env.write_text("# gh-vault: secret\nAPI_KEY=alpha\n# gh-vault: variable\nREGION=eu-test-1\n", encoding="utf-8")
    example.write_text("# gh-vault: secret\n# API_KEY=\n# gh-vault: variable\n# REGION=\n", encoding="utf-8")
    vault = MemoryVault()
    public = EnvironmentStore(tmp_path / "config")
    archive_environment(vault, public, tmp_path, env, example)  # type: ignore[arg-type]

    env.unlink()
    env.write_text("LOCAL_ONLY=keep\n", encoding="utf-8")
    restore_environment(vault, public, tmp_path, env, example, False, False, "API_KEY")  # type: ignore[arg-type]
    assert env.read_text(encoding="utf-8") == "LOCAL_ONLY=keep\n# gh-vault: secret\nAPI_KEY=alpha\n"
    assert stat.S_IMODE(env.stat().st_mode) == 0o600


def test_restore_with_key_rejects_invalid_key_name(monkeypatch, tmp_path: Path) -> None:
    class Result:
        returncode = 0
        stdout = "https://github.com/owner/repo.git\n"

    monkeypatch.setattr("gh_vault.envfiles.subprocess.run", lambda *args, **kwargs: Result())
    env = tmp_path / ".env"
    example = tmp_path / ".env.example"
    env.write_text("# gh-vault: secret\nAPI_KEY=alpha\n", encoding="utf-8")
    example.write_text("# gh-vault: secret\n# API_KEY=\n", encoding="utf-8")
    vault = MemoryVault()
    public = EnvironmentStore(tmp_path / "config")
    archive_environment(vault, public, tmp_path, env, example)  # type: ignore[arg-type]

    env.unlink()
    with pytest.raises(StoreError, match="invalid key name"):
        restore_environment(vault, public, tmp_path, env, example, False, False, "1-BAD")  # type: ignore[arg-type]


def test_variable_only_archive_and_show_never_use_the_vault(monkeypatch, tmp_path: Path) -> None:
    class Result:
        returncode = 0
        stdout = "https://github.com/owner/repo.git\n"

    class NoVault:
        def __getattr__(self, name):
            raise AssertionError(f"vault access is forbidden: {name}")

    monkeypatch.setattr("gh_vault.envfiles.subprocess.run", lambda *args, **kwargs: Result())
    env = tmp_path / ".env"
    example = tmp_path / ".env.example"
    env.write_text("# gh-vault: variable\nREGION=eu-test-1\nLOCAL_ONLY=private\n", encoding="utf-8")
    example.write_text("# gh-vault: variable\n# REGION=\n# LOCAL_ONLY=\n", encoding="utf-8")
    public = EnvironmentStore(tmp_path / "config")
    vault = NoVault()

    archive_environment(vault, public, tmp_path, env, example)  # type: ignore[arg-type]
    assert show_environment(public, tmp_path, env)[1] == {"REGION": "eu-test-1"}
    env.unlink()
    restore_environment(vault, public, tmp_path, env, example, False, False)  # type: ignore[arg-type]
    assert "REGION=eu-test-1" in env.read_text(encoding="utf-8")
    assert "private" not in "".join(path.read_text(encoding="utf-8") for path in public.root.rglob("*.json"))

    env.unlink()
    example.unlink()
    with pytest.raises(StoreError, match="requires a local template"):
        restore_environment(vault, public, tmp_path, env, example, False, False)  # type: ignore[arg-type]


def test_archive_type_transitions_remove_stale_payloads(monkeypatch, tmp_path: Path) -> None:
    class Result:
        returncode = 0
        stdout = "https://github.com/owner/repo.git\n"

    events: list[str] = []

    class RecordingVault(MemoryVault):
        def put_secret(self, name: str, value: str) -> None:
            events.append(f"put:{name}")
            super().put_secret(name, value)

        def remove_secret(self, name: str) -> None:
            events.append(f"remove:{name}")
            super().remove_secret(name)

    class RecordingEnvironmentStore(EnvironmentStore):
        def save_variables(self, namespace: str, profile: str, origin: str, values: dict[str, str]) -> None:
            events.append("save:variables")
            super().save_variables(namespace, profile, origin, values)

        def remove_variables(self, namespace: str, profile: str) -> None:
            events.append("remove:variables")
            super().remove_variables(namespace, profile)

    monkeypatch.setattr("gh_vault.envfiles.subprocess.run", lambda *args, **kwargs: Result())
    env = tmp_path / ".env"
    example = tmp_path / ".env.example"
    example.write_text("# gh-vault: secret\n# API_KEY=\n", encoding="utf-8")
    vault = RecordingVault()
    public = RecordingEnvironmentStore(tmp_path / "config")
    secret_entry = "projects/github.com/owner/repo/env.secrets.json"
    example_entry = "projects/github.com/owner/repo/env.example"

    env.write_text("# gh-vault: secret\nAPI_KEY=secret-one\n", encoding="utf-8")
    archive_environment(vault, public, tmp_path, env, example)  # type: ignore[arg-type]
    assert secret_entry in vault.values and example_entry in vault.values

    events.clear()
    env.write_text("# gh-vault: variable\nAPI_KEY=public-one\n", encoding="utf-8")
    archive_environment(vault, public, tmp_path, env, example)  # type: ignore[arg-type]
    assert show_environment(public, tmp_path, env)[1] == {"API_KEY": "public-one"}
    assert secret_entry not in vault.values and example_entry not in vault.values
    assert events.index("save:variables") < events.index(f"remove:{secret_entry}")

    events.clear()
    env.write_text("# gh-vault: secret\nAPI_KEY=secret-two\n", encoding="utf-8")
    archive_environment(vault, public, tmp_path, env, example)  # type: ignore[arg-type]
    assert show_environment(public, tmp_path, env)[1] == {}
    assert secret_entry in vault.values and example_entry in vault.values
    assert events.index(f"put:{secret_entry}") < events.index("remove:variables")

    events.clear()
    env.write_text("LOCAL_ONLY=local\n", encoding="utf-8")
    archive_environment(vault, public, tmp_path, env, example)  # type: ignore[arg-type]
    assert list_environments(public, tmp_path)[1] == []
    assert secret_entry not in vault.values and example_entry not in vault.values

    events.clear()
    env.write_text("# gh-vault: variable\nAPI_KEY=public-two\n", encoding="utf-8")
    archive_environment(vault, public, tmp_path, env, example)  # type: ignore[arg-type]
    assert show_environment(public, tmp_path, env)[1] == {"API_KEY": "public-two"}
    assert not any(event.startswith(("put:", "remove:")) for event in events)


def test_migrate_environment_archive_partitions_and_removes_legacy(monkeypatch, tmp_path: Path) -> None:
    class Result:
        returncode = 0
        stdout = "https://github.com/owner/repo.git\n"

    monkeypatch.setattr("gh_vault.envfiles.subprocess.run", lambda *args, **kwargs: Result())
    env = tmp_path / ".env"
    env.write_text("# gh-vault: variable\nREGION=current\n# gh-vault: secret\nAPI_KEY=current\nLOCAL_ONLY=current\n", encoding="utf-8")
    vault = MemoryVault()
    public = EnvironmentStore(tmp_path / "config")
    base = "projects/github.com/owner/repo"
    legacy = f"{base}/env.json"
    vault.values[legacy] = '{"origin":"https://github.com/owner/repo.git","values":{"GH_SECRET_API_KEY":"synthetic-secret","GH_VAR_REGION":"eu-west-1","LOCAL_ONLY":"private-local"},"version":2}'
    vault.values[f"{base}/env.example"] = "# template\n"

    assert migrate_environment_archive(vault, public, tmp_path, env, tmp_path / ".env.example") == ArchiveMigrationResult("github.com/owner/repo", "default", 1, 1, 1)  # type: ignore[arg-type]
    assert public.load_variables("github.com/owner/repo", "default", "https://github.com/owner/repo.git") == {"REGION": "eu-west-1"}
    assert legacy not in vault.values
    assert "synthetic-secret" not in "".join(path.read_text(encoding="utf-8") for path in public.root.rglob("*.json"))

    vault.values[legacy] = '{"origin":"https://github.com/owner/repo.git","values":{"GH_SECRET_API_KEY":"synthetic-secret","GH_VAR_REGION":"eu-west-1","LOCAL_ONLY":"private-local"},"version":2}'
    assert migrate_environment_archive(vault, public, tmp_path, env, tmp_path / ".env.example") == ArchiveMigrationResult("github.com/owner/repo", "default", 1, 1, 1)  # type: ignore[arg-type]
    assert legacy not in vault.values

    vault.values[legacy] = '{"origin":"https://github.com/owner/repo.git","values":{"GH_SECRET_API_KEY":"changed","GH_VAR_REGION":"eu-west-1","LOCAL_ONLY":"private-local"},"version":2}'
    with pytest.raises(StoreError, match="already exists with different data"):
        migrate_environment_archive(vault, public, tmp_path, env, tmp_path / ".env.example")  # type: ignore[arg-type]
    assert legacy in vault.values


def test_migrate_environment_archive_keeps_legacy_when_publication_fails(monkeypatch, tmp_path: Path) -> None:
    class Result:
        returncode = 0
        stdout = "https://github.com/owner/repo.git\n"

    class FailingEnvironmentStore(EnvironmentStore):
        def save_manifest(self, namespace, origin, environments):
            raise StoreError("synthetic publication failure")

    monkeypatch.setattr("gh_vault.envfiles.subprocess.run", lambda *args, **kwargs: Result())
    env = tmp_path / ".env"
    env.write_text("# gh-vault: variable\nREGION=current\n", encoding="utf-8")
    vault = MemoryVault()
    legacy = "projects/github.com/owner/repo/env.json"
    vault.values[legacy] = '{"origin":"https://github.com/owner/repo.git","values":{"GH_VAR_REGION":"eu-west-1"},"version":2}'

    with pytest.raises(StoreError, match="synthetic publication failure"):
        migrate_environment_archive(vault, FailingEnvironmentStore(tmp_path / "config"), tmp_path, env, tmp_path / ".env.example")  # type: ignore[arg-type]
    assert legacy in vault.values


def test_export_act_and_workflow_check(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("# gh-vault: secret\nAPI_KEY=alpha\n# gh-vault: variable\nREGION=eu\nLOCAL_ONLY=local\n", encoding="utf-8")
    entries = action_values(env, MemoryVault())
    assert entries == [ActionValue("API_KEY", "secret", "alpha"), ActionValue("REGION", "variable", "eu")]
    assert [entry.line for entry in entries] == [2, 4]
    secrets, variables = export_act(entries, tmp_path / ".secrets", tmp_path / ".vars")
    assert (secrets, variables) == (1, 1)
    assert (tmp_path / ".secrets").read_text(encoding="utf-8") == "API_KEY=alpha\n"
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "ci.yml").write_text("env:\n  API_KEY: ${{ secrets.API_KEY }}\n  REGION: ${{ vars.REGION }}\n", encoding="utf-8")
    assert check_workflows(tmp_path, entries) == {"unreferenced": [], "type_mismatch": [], "order": [], "orphan": []}


@pytest.mark.parametrize("returncode", [0, 7])
def test_run_act_uses_private_ephemeral_files(monkeypatch, tmp_path: Path, returncode: int) -> None:
    env = tmp_path / ".env"
    env.write_text("LOCAL_ONLY=excluded\n# gh-vault: secret\nAPI_KEY=synthetic\n# gh-vault: variable\nREGION=eu-test-1\n", encoding="utf-8")
    observed: dict[str, Path] = {}

    class Result:
        def __init__(self, code: int) -> None:
            self.returncode = code

    def fake_run(command, *, cwd, check):
        assert command[:2] == ["act", "workflow_dispatch"]
        assert command[-4] == "--secret-file"
        assert command[-2] == "--var-file"
        secrets_path = Path(command[-3])
        variables_path = Path(command[-1])
        observed["root"] = secrets_path.parent
        assert cwd == tmp_path and check is False
        assert stat.S_IMODE(secrets_path.parent.stat().st_mode) == 0o700
        assert stat.S_IMODE(secrets_path.stat().st_mode) == 0o600
        assert stat.S_IMODE(variables_path.stat().st_mode) == 0o600
        assert secrets_path.read_text(encoding="utf-8") == "API_KEY=synthetic\n"
        assert variables_path.read_text(encoding="utf-8") == "REGION=eu-test-1\n"
        return Result(returncode)

    monkeypatch.setattr("gh_vault.actions.subprocess.run", fake_run)

    assert run_act(env, ["--", "act", "workflow_dispatch"], tmp_path) == returncode
    assert not observed["root"].exists()


def test_run_act_creates_empty_files_for_no_typed_values(monkeypatch, tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("LOCAL_ONLY=excluded\n", encoding="utf-8")

    class Result:
        returncode = 0

    def fake_run(command, **kwargs):
        assert Path(command[-3]).read_text(encoding="utf-8") == ""
        assert Path(command[-1]).read_text(encoding="utf-8") == ""
        return Result()

    monkeypatch.setattr("gh_vault.actions.subprocess.run", fake_run)
    assert run_act(env, ["--", "act"], tmp_path) == 0


def test_run_act_cleans_up_when_the_child_cannot_start(monkeypatch, tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("", encoding="utf-8")
    observed: dict[str, Path] = {}

    def fake_run(command, **kwargs):
        observed["root"] = Path(command[-3]).parent
        raise OSError("synthetic launch failure")

    monkeypatch.setattr("gh_vault.actions.subprocess.run", fake_run)

    with pytest.raises(StoreError, match="cannot run act"):
        run_act(env, ["--", "act"], tmp_path)
    assert not observed["root"].exists()


@pytest.mark.parametrize("flag", ["--secret-file", "--secret-file=custom", "--var-file", "--var-file=custom"])
def test_run_act_rejects_managed_file_flags_before_creating_tempfiles(monkeypatch, tmp_path: Path, flag: str) -> None:
    monkeypatch.setattr("gh_vault.actions.tempfile.TemporaryDirectory", lambda **kwargs: pytest.fail("temporary directory created"))

    with pytest.raises(StoreError, match="do not supply them manually"):
        run_act(tmp_path / ".env", ["--", "act", flag], tmp_path)


@pytest.mark.parametrize("returncode", [0, 7])
def test_run_act_accepts_gh_act_invocation(monkeypatch, tmp_path: Path, returncode: int) -> None:
    env = tmp_path / ".env"
    env.write_text("# gh-vault: secret\nAPI_KEY=synthetic\n# gh-vault: variable\nREGION=eu-test-1\n", encoding="utf-8")
    observed: dict[str, Path] = {}

    class Result:
        def __init__(self, code: int) -> None:
            self.returncode = code

    def fake_run(command, *, cwd, check):
        assert command[:3] == ["gh", "act", "workflow_dispatch"]
        assert command[-4] == "--secret-file"
        assert command[-2] == "--var-file"
        secrets_path = Path(command[-3])
        variables_path = Path(command[-1])
        observed["root"] = secrets_path.parent
        assert cwd == tmp_path and check is False
        assert stat.S_IMODE(secrets_path.parent.stat().st_mode) == 0o700
        assert stat.S_IMODE(secrets_path.stat().st_mode) == 0o600
        assert stat.S_IMODE(variables_path.stat().st_mode) == 0o600
        assert secrets_path.read_text(encoding="utf-8") == "API_KEY=synthetic\n"
        assert variables_path.read_text(encoding="utf-8") == "REGION=eu-test-1\n"
        return Result(returncode)

    monkeypatch.setattr("gh_vault.actions.subprocess.run", fake_run)

    assert run_act(env, ["--", "gh", "act", "workflow_dispatch"], tmp_path) == returncode
    assert not observed["root"].exists()


@pytest.mark.parametrize("program", [["--", "gh"], ["--", "gh", "workflow_dispatch"], ["--", "/usr/local/bin/run-tests"]])
def test_run_act_rejects_commands_other_than_act_or_gh_act(monkeypatch, tmp_path: Path, program: list[str]) -> None:
    monkeypatch.setattr("gh_vault.actions.tempfile.TemporaryDirectory", lambda **kwargs: pytest.fail("temporary directory created"))

    with pytest.raises(StoreError, match="use 'act' or 'gh act'"):
        run_act(tmp_path / ".env", program, tmp_path)


@pytest.mark.parametrize("flag", ["--secret-file", "--secret-file=custom", "--var-file", "--var-file=custom"])
def test_run_act_rejects_managed_file_flags_when_invoked_through_gh_act(monkeypatch, tmp_path: Path, flag: str) -> None:
    monkeypatch.setattr("gh_vault.actions.tempfile.TemporaryDirectory", lambda **kwargs: pytest.fail("temporary directory created"))

    with pytest.raises(StoreError, match="do not supply them manually"):
        run_act(tmp_path / ".env", ["--", "gh", "act", flag], tmp_path)


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
    assert sync([ActionValue("API_KEY", "secret", "alpha")], "owner/repo", "secret", False, migrate_types=True) == SyncResult(1, 0)
    assert calls == [
        (["gh", "secret", "list", "--repo", "owner/repo", "--json", "name", "--jq", ".[].name"], None),
        (["gh", "variable", "list", "--repo", "owner/repo", "--json", "name", "--jq", ".[].name"], None),
        (["gh", "variable", "delete", "API_KEY", "--repo", "owner/repo"], None),
        (["gh", "secret", "set", "API_KEY", "--repo", "owner/repo"], "alpha"),
    ]


def test_sync_migrates_a_stale_secret_when_variable_sync_runs(monkeypatch) -> None:
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
            return Result("REGION\n")
        return Result()

    monkeypatch.setattr("gh_vault.actions.subprocess.run", fake_run)
    assert sync([ActionValue("REGION", "variable", "eu")], "owner/repo", "variable", False, migrate_types=True) == SyncResult(1, 0)
    assert calls == [
        (["gh", "variable", "list", "--repo", "owner/repo", "--json", "name", "--jq", ".[].name"], None),
        (["gh", "secret", "list", "--repo", "owner/repo", "--json", "name", "--jq", ".[].name"], None),
        (["gh", "secret", "remove", "REGION", "--repo", "owner/repo"], None),
        (["gh", "variable", "set", "REGION", "--repo", "owner/repo"], "eu"),
    ]


def test_sync_prunes_only_target_store_names_absent_locally(monkeypatch) -> None:
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
            return Result("STALE_VARIABLE\n")
        return Result()

    monkeypatch.setattr("gh_vault.actions.subprocess.run", fake_run)
    assert sync([ActionValue("CONFIGURED", "secret", "alpha")], "owner/repo", "secret", False, prune=True) == SyncResult(1, 1)
    assert calls == [
        (["gh", "secret", "list", "--repo", "owner/repo", "--json", "name", "--jq", ".[].name"], None),
        (["gh", "secret", "remove", "STALE_SECRET", "--repo", "owner/repo"], None),
        (["gh", "secret", "set", "CONFIGURED", "--repo", "owner/repo"], "alpha"),
    ]


def test_sync_variable_prune_only_targets_variables(monkeypatch) -> None:
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
            return Result("CONFIGURED\nSTALE_VARIABLE\n")
        return Result()

    monkeypatch.setattr("gh_vault.actions.subprocess.run", fake_run)
    assert sync([ActionValue("CONFIGURED", "variable", "eu")], "owner/repo", "variable", False, prune=True) == SyncResult(1, 1)
    assert calls == [
        (["gh", "variable", "list", "--repo", "owner/repo", "--json", "name", "--jq", ".[].name"], None),
        (["gh", "variable", "delete", "STALE_VARIABLE", "--repo", "owner/repo"], None),
        (["gh", "variable", "set", "CONFIGURED", "--repo", "owner/repo"], "eu"),
    ]


def test_sync_ordinary_never_lists_or_deletes(monkeypatch) -> None:
    calls: list[tuple[list[str], str | None]] = []

    class Result:
        returncode = 0
        stderr = ""
        stdout = ""

    monkeypatch.setattr("gh_vault.actions.subprocess.run", lambda command, **kwargs: calls.append((command, kwargs.get("input"))) or Result())
    assert sync([ActionValue("API_KEY", "secret", "alpha")], "owner/repo", "secret", False) == SyncResult(1, 0)
    assert calls == [
        (["gh", "secret", "set", "API_KEY", "--repo", "owner/repo"], "alpha"),
    ]


def test_sync_ordinary_variable_sets_only_variables(monkeypatch) -> None:
    calls: list[tuple[list[str], str | None]] = []

    class Result:
        returncode = 0
        stderr = ""
        stdout = ""

    monkeypatch.setattr("gh_vault.actions.subprocess.run", lambda command, **kwargs: calls.append((command, kwargs.get("input"))) or Result())
    assert sync([ActionValue("REGION", "variable", "eu")], "owner/repo", "variable", False) == SyncResult(1, 0)
    assert calls == [
        (["gh", "variable", "set", "REGION", "--repo", "owner/repo"], "eu"),
    ]


def test_sync_dry_run_reports_counts_without_mutation(monkeypatch) -> None:
    calls: list[list[str]] = []

    class Result:
        returncode = 0
        stderr = ""
        stdout = ""

    def fake_run(command: list[str], **kwargs: object) -> Result:
        calls.append(command)
        return Result()

    monkeypatch.setattr("gh_vault.actions.subprocess.run", fake_run)
    assert sync(
        [ActionValue("REGION", "variable", "eu")],
        "owner/repo",
        "variable",
        True,
        migrate_types=True,
    ) == SyncResult(1, 0)
    assert calls == [
        ["gh", "variable", "list", "--repo", "owner/repo", "--json", "name", "--jq", ".[].name"],
        ["gh", "secret", "list", "--repo", "owner/repo", "--json", "name", "--jq", ".[].name"],
    ]


def test_sync_rejects_mismatched_entry_kinds() -> None:
    with pytest.raises(StoreError, match="received entries with other kinds"):
        sync([ActionValue("API_KEY", "secret", "alpha"), ActionValue("REGION", "variable", "eu")], "owner/repo", "secret", False)


def test_sync_failure_after_migration_delete_preserves_manual_restore_hint(monkeypatch) -> None:
    class ListResult:
        returncode = 0
        stderr = ""
        stdout = ""

    class VariableListResult:
        returncode = 0
        stderr = ""
        stdout = "API_KEY\n"

    class OkResult:
        returncode = 0
        stderr = ""

    class FailureResult:
        returncode = 1
        stderr = "synthetic set failure"

    def fake_run(command: list[str], **kwargs: object):
        if command[:3] == ["gh", "secret", "list"]:
            return ListResult()
        if command[:3] == ["gh", "variable", "list"]:
            return VariableListResult()
        if command[:2] == ["gh", "variable"] and command[2] == "delete":
            return OkResult()
        return FailureResult()

    monkeypatch.setattr("gh_vault.actions.subprocess.run", fake_run)
    with pytest.raises(StoreError, match="stale counterpart was removed and must be restored manually"):
        sync([ActionValue("API_KEY", "secret", "alpha")], "owner/repo", "secret", False, migrate_types=True)


def test_sync_combined_prune_and_migrate_types_is_rejected() -> None:
    with pytest.raises(StoreError, match="cannot be combined"):
        sync([ActionValue("API_KEY", "secret", "alpha")], "owner/repo", "secret", False, prune=True, migrate_types=True)
