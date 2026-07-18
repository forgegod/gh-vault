from __future__ import annotations

import argparse
import io
from pathlib import Path

import pytest

from gh_vault import cli
from gh_vault.actions import ActionValue, RemoteValueStatus, SyncResult
from gh_vault.envfiles import ArchiveMigrationResult
from gh_vault.github import TokenMetadata
from gh_vault.store import Profile, StoreError


class MemoryStore:
    def __init__(self) -> None:
        self.items = {"read": "token-read", "write": "token-write"}
        self.selected = "read"
        self.backend = "/usr/bin/pass"

    def active(self) -> str | None:
        return self.selected

    def profiles(self) -> list[Profile]:
        return [Profile("read", ("contents:read",), "safe reads", "2026-12-31 23:59:59 UTC"), Profile("write")]

    def get(self, name: str | None = None) -> str:
        return self.items[name or self.selected]

    def require_backend(self) -> None:
        pass


def test_profile_name_validation() -> None:
    assert cli.profile_name("release-write.v2") == "release-write.v2"
    with pytest.raises(argparse.ArgumentTypeError):
        cli.profile_name("bad name")


def test_parse_scopes_trims_and_deduplicates() -> None:
    assert cli.parse_scopes("repo, workflow,repo,") == ("repo", "workflow")


def test_parser_uses_public_command_name() -> None:
    assert cli.build_parser().prog == "gh-vault"


def test_add_command_is_removed() -> None:
    with pytest.raises(SystemExit, match="2"):
        cli.build_parser().parse_args(["add", "release"])


@pytest.mark.parametrize(
    ("arguments", "description"),
    [
        (["set", "--help"], "Validate a GitHub token and create or replace its named profile"),
        (["list", "--help"], "Display stored token profiles"),
        (["activate", "--help"], "Select the token profile"),
        (["status", "--help"], "Show the profile selected"),
        (["remove", "--help"], "Delete a token profile"),
        (["run", "--help"], "Run a child command"),
        (["run-act", "--help"], "Run act with temporary 0600 secret and variable files"),
        (["git-credential", "--help"], "Serve Git's credential-helper protocol"),
        (["env", "archive", "--help"], "Archive variable declarations in the public XDG store"),
        (["env", "restore", "--help"], "Restore a project environment"),
        (["env", "list", "--help"], "List archived .env and .env.<profile> variants"),
        (["env", "show", "--help"], "Print only the selected profile's clear-text variable payload"),
        (["env", "migrate", "--help"], "Partition one legacy encrypted archive"),
        (["actions", "migrate-env", "--help"], "Rewrite legacy prefixed declarations"),
        (["secret", "sync", "--help"], "Set gh-vault secret declarations as GitHub Secrets"),
        (["secret", "export-act", "--help"], "Write gh-vault secret declarations to .secrets"),
        (["secret", "check", "--help"], "Compare typed gh-vault secret declarations with GitHub Secrets"),
        (["variable", "sync", "--help"], "Set gh-vault variable declarations as GitHub Variables"),
        (["variable", "import", "--help"], "Import repository Variables with gh-vault variable directives"),
        (["variable", "check", "--help"], "Compare typed gh-vault variable declarations with GitHub Variables"),
        (["workflow", "check", "--help"], "Report missing, mismatched, and unreferenced"),
    ],
)
def test_subtool_help_explains_its_operation(arguments: list[str], description: str, capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit, match="0"):
        cli.build_parser().parse_args(arguments)

    assert description in capsys.readouterr().out


@pytest.mark.parametrize("command", ["secrets", "variables"])
def test_parser_rejects_removed_plural_command_groups(command: str) -> None:
    with pytest.raises(SystemExit, match="2"):
        cli.build_parser().parse_args([command, "--help"])


@pytest.mark.parametrize(
    "arguments",
    [
        ["secret", "sync"],
        ["secret", "sync", "--dry-run"],
        ["secret", "sync", "--prune"],
        ["secret", "sync", "--migrate-types"],
        ["secret", "sync", "--repo", "owner/repo"],
        ["secret", "export-act"],
        ["secret", "check", "--repo", "owner/repo"],
        ["variable", "import", "--force"],
        ["variable", "check", "--repo", "owner/repo"],
    ],
)
def test_parser_accepts_singular_action_command_groups(arguments: list[str]) -> None:
    args = cli.build_parser().parse_args(arguments)
    assert args.command in {"secret", "variable"}


@pytest.mark.parametrize("command", ["secret", "variable"])
def test_sync_parser_accepts_matching_options(command: str) -> None:
    args = cli.build_parser().parse_args([command, "sync", "--env-file", ".env.test", "--repo", "owner/repo", "--dry-run"])
    assert getattr(args, f"{command}_command") == "sync"
    assert args.env_file == Path(".env.test")
    assert args.repo == "owner/repo"
    assert args.dry_run is True
    assert args.prune is False
    assert args.migrate_types is False


@pytest.mark.parametrize("command", ["secret", "variable"])
def test_sync_parser_accepts_prune_and_migrate_types_separately(command: str) -> None:
    prune_args = cli.build_parser().parse_args([command, "sync", "--prune"])
    assert prune_args.prune is True
    assert prune_args.migrate_types is False
    migrate_args = cli.build_parser().parse_args([command, "sync", "--migrate-types"])
    assert migrate_args.prune is False
    assert migrate_args.migrate_types is True


def test_variable_sync_parser_accepts_matching_options() -> None:
    args = cli.build_parser().parse_args(["variable", "sync", "--env-file", ".env.production", "--repo", "owner/repo"])
    assert args.variable_command == "sync"
    assert args.env_file == Path(".env.production")
    assert args.repo == "owner/repo"
    assert args.dry_run is False
    assert args.prune is False
    assert args.migrate_types is False


def test_set_discovers_scopes_and_expiration(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    args = cli.build_parser().parse_args(["set", "release", "--stdin"])
    store = MemoryStore()
    captured: dict[str, object] = {}

    monkeypatch.setattr(cli, "_read_token", lambda use_stdin: "token-value")
    monkeypatch.setattr(cli, "inspect_token", lambda token: TokenMetadata(("repo", "workflow"), "2026-12-31 23:59:59 UTC"))
    monkeypatch.setattr(store, "put", lambda profile, token, replace: captured.update(profile=profile, token=token, replace=replace), raising=False)

    assert cli.dispatch(args, store) == 0  # type: ignore[arg-type]
    assert captured == {
        "profile": Profile("release", ("repo", "workflow"), "", "2026-12-31 23:59:59 UTC"),
        "token": "token-value",
        "replace": True,
    }
    assert capsys.readouterr().out == "Validated GitHub token: scopes=repo,workflow expires=2026-12-31 23:59:59 UTC\nStored profile: release\n"


def test_set_preserves_expiration_with_manual_scopes(monkeypatch: pytest.MonkeyPatch) -> None:
    args = cli.build_parser().parse_args(["set", "release", "--stdin", "--scopes", "read:org"])
    store = MemoryStore()
    captured: dict[str, Profile] = {}

    monkeypatch.setattr(cli, "_read_token", lambda use_stdin: "token-value")
    monkeypatch.setattr(cli, "inspect_token", lambda token: TokenMetadata(("repo",), "2026-12-31 23:59:59 UTC"))
    monkeypatch.setattr(store, "put", lambda profile, token, replace: captured.update(profile=profile), raising=False)

    assert cli.dispatch(args, store) == 0  # type: ignore[arg-type]
    assert captured["profile"] == Profile("release", ("read:org",), "", "2026-12-31 23:59:59 UTC")


def test_set_with_manual_scopes_allows_unavailable_inspection(monkeypatch: pytest.MonkeyPatch) -> None:
    args = cli.build_parser().parse_args(["set", "release", "--stdin", "--scopes", "read:org"])
    store = MemoryStore()
    captured: dict[str, Profile] = {}

    def unavailable(token: str) -> TokenMetadata:
        raise StoreError("GitHub API is unavailable")

    monkeypatch.setattr(cli, "_read_token", lambda use_stdin: "token-value")
    monkeypatch.setattr(cli, "inspect_token", unavailable)
    monkeypatch.setattr(store, "put", lambda profile, token, replace: captured.update(profile=profile), raising=False)

    assert cli.dispatch(args, store) == 0  # type: ignore[arg-type]
    assert captured["profile"] == Profile("release", ("read:org",))


def test_env_run_injects_declared_actions_values(monkeypatch: pytest.MonkeyPatch) -> None:
    args = cli.build_parser().parse_args(["env", "run", "--", "program", "argument"])
    captured: dict[str, object] = {}

    monkeypatch.setattr(cli, "runtime_environment", lambda path: {"REGION": "eu", "TOKEN": "secret-token"})
    monkeypatch.setattr(cli.os, "execvpe", lambda program, arguments, environment: captured.update(program=program, arguments=arguments, environment=environment))

    assert cli.dispatch(args, MemoryStore()) == 127  # type: ignore[arg-type]
    assert captured["program"] == "program"
    assert captured["arguments"] == ["program", "argument"]
    assert captured["environment"]["REGION"] == "eu"  # type: ignore[index]
    assert captured["environment"]["TOKEN"] == "secret-token"  # type: ignore[index]


def test_run_act_dispatches_the_explicit_act_command(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    args = cli.build_parser().parse_args(["run-act", "--env-file", ".env.test", "--", "act", "workflow_dispatch"])
    captured: dict[str, object] = {}

    def fake_run_act(env_file: Path, program: list[str], directory: Path) -> int:
        captured.update(env_file=env_file, program=program, directory=directory)
        return 7

    monkeypatch.setattr(cli, "run_act", fake_run_act)

    assert cli.dispatch(args, MemoryStore(), tmp_path) == 7  # type: ignore[arg-type]
    assert captured == {"env_file": Path(".env.test"), "program": ["--", "act", "workflow_dispatch"], "directory": tmp_path}


def test_env_archive_accepts_repeated_profile_files_and_list_reports_templates(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    args = cli.build_parser().parse_args(["env", "archive", "--env-file", ".env.development", "--env-file", ".env.production"])
    archived: list[tuple[Path, Path]] = []
    monkeypatch.setattr(cli, "archive_environment", lambda store, environment_store, directory, env_file, example_file: archived.append((env_file, example_file)) or "github.com/owner/repo")

    assert cli.dispatch(args, MemoryStore()) == 0  # type: ignore[arg-type]
    assert archived == [(Path(".env.development"), Path(".env.example.development")), (Path(".env.production"), Path(".env.example.production"))]
    assert capsys.readouterr().out.splitlines() == ["Archived .env.development for github.com/owner/repo.", "Archived .env.production for github.com/owner/repo."]

    args = cli.build_parser().parse_args(["env", "list"])
    monkeypatch.setattr(cli, "list_environments", lambda store, directory: ("github.com/owner/repo", [("development", False), ("production", True)]))
    assert cli.dispatch(args, MemoryStore()) == 0  # type: ignore[arg-type]
    assert capsys.readouterr().out.splitlines() == [".env.development example=no", ".env.production example=yes"]


def test_env_run_requires_an_explicit_command_separator() -> None:
    args = cli.build_parser().parse_args(["env", "run", "program"])
    with pytest.raises(StoreError, match="after --"):
        cli.dispatch(args, MemoryStore())  # type: ignore[arg-type]


def test_parser_rejects_removed_legacy_migration_command() -> None:
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args(["migrate"])


def test_explicit_migration_commands_dispatch_without_values(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    source = cli.build_parser().parse_args(["actions", "migrate-env", "--env-file", ".env.production"])
    monkeypatch.setattr(cli, "migrate_env_source", lambda path: (2, 1))
    assert cli.dispatch(source, MemoryStore()) == 0  # type: ignore[arg-type]
    assert capsys.readouterr().out == "Migrated 2 declaration(s) in .env.production and 1 in .env.example.production.\n"

    archive = cli.build_parser().parse_args(["env", "migrate", "--env-file", ".env.production"])
    monkeypatch.setattr(cli, "migrate_environment_archive", lambda *args: ArchiveMigrationResult("github.com/owner/repo", "production", 2, 1, 3))
    assert cli.dispatch(archive, MemoryStore()) == 0  # type: ignore[arg-type]
    assert capsys.readouterr().out == "Migrated .env.production (production) for github.com/owner/repo: 2 variable value(s) moved to clear text, 1 secret value(s) retained encrypted, 3 local-only value(s) removed from gh-vault.\n"


def test_parser_accepts_variable_import_and_secret_check_commands() -> None:
    args = cli.build_parser().parse_args(["variable", "import", "--force"])
    assert args.variable_command == "import"
    assert args.force is True
    assert cli.build_parser().parse_args(["secret", "check"]).secret_command == "check"
    assert cli.build_parser().parse_args(["variable", "check"]).variable_command == "check"


def test_sync_rejects_prune_with_type_migration() -> None:
    with pytest.raises(SystemExit, match="2"):
        cli.build_parser().parse_args(["secret", "sync", "--prune", "--migrate-types"])


def test_variable_sync_rejects_prune_with_type_migration() -> None:
    with pytest.raises(SystemExit, match="2"):
        cli.build_parser().parse_args(["variable", "sync", "--prune", "--migrate-types"])


def test_secret_sync_dispatches_only_secret_entries(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    args = cli.build_parser().parse_args(["secret", "sync", "--dry-run", "--prune"])
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        cli,
        "action_values",
        lambda path: [
            ActionValue("API_KEY", "secret", "alpha"),
            ActionValue("REGION", "variable", "eu"),
        ],
    )

    def fake_sync(entries, repo, kind, dry_run, migrate_types=False, prune=False):
        captured["entries"] = [(entry.name, entry.kind) for entry in entries]
        captured["repo"] = repo
        captured["kind"] = kind
        captured["dry_run"] = dry_run
        captured["prune"] = prune
        captured["migrate_types"] = migrate_types
        return SyncResult(1, 3)

    monkeypatch.setattr(cli, "sync", fake_sync)

    assert cli.dispatch(args, MemoryStore()) == 0  # type: ignore[arg-type]
    assert captured["entries"] == [("API_KEY", "secret")]
    assert captured["kind"] == "secret"
    assert captured["dry_run"] is True
    assert captured["prune"] is True
    assert captured["migrate_types"] is False
    assert capsys.readouterr().out == "Would sync 1 secret(s); would prune 3 secret(s).\n"


def test_variable_sync_dispatches_only_variable_entries(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    args = cli.build_parser().parse_args(["variable", "sync", "--dry-run", "--prune"])
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        cli,
        "action_values",
        lambda path: [
            ActionValue("API_KEY", "secret", "alpha"),
            ActionValue("REGION", "variable", "eu"),
        ],
    )

    def fake_sync(entries, repo, kind, dry_run, migrate_types=False, prune=False):
        captured["entries"] = [(entry.name, entry.kind) for entry in entries]
        captured["kind"] = kind
        return SyncResult(2, 4)

    monkeypatch.setattr(cli, "sync", fake_sync)

    assert cli.dispatch(args, MemoryStore()) == 0  # type: ignore[arg-type]
    assert captured["entries"] == [("REGION", "variable")]
    assert captured["kind"] == "variable"
    assert capsys.readouterr().out == "Would sync 2 variable(s); would prune 4 variable(s).\n"


def test_secret_sync_summary_uses_secret_singular(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    args = cli.build_parser().parse_args(["secret", "sync"])
    monkeypatch.setattr(cli, "action_values", lambda path: [ActionValue("API_KEY", "secret", "alpha")])
    monkeypatch.setattr(cli, "sync", lambda *args, **kwargs: SyncResult(1, 0))

    assert cli.dispatch(args, MemoryStore()) == 0  # type: ignore[arg-type]
    output = capsys.readouterr().out
    assert output == "Synced 1 secret(s).\n"
    assert "variable" not in output


def test_variable_sync_summary_uses_variable_singular(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    args = cli.build_parser().parse_args(["variable", "sync"])
    monkeypatch.setattr(cli, "action_values", lambda path: [ActionValue("REGION", "variable", "eu")])
    monkeypatch.setattr(cli, "sync", lambda *args, **kwargs: SyncResult(1, 0))

    assert cli.dispatch(args, MemoryStore()) == 0  # type: ignore[arg-type]
    output = capsys.readouterr().out
    assert output == "Synced 1 variable(s).\n"
    assert "secret" not in output


def test_secret_sync_dry_run_summary_uses_secret_singular(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    args = cli.build_parser().parse_args(["secret", "sync", "--dry-run"])
    monkeypatch.setattr(cli, "action_values", lambda path: [ActionValue("API_KEY", "secret", "alpha")])
    monkeypatch.setattr(cli, "sync", lambda *args, **kwargs: SyncResult(1, 0))

    assert cli.dispatch(args, MemoryStore()) == 0  # type: ignore[arg-type]
    output = capsys.readouterr().out
    assert output == "Would sync 1 secret(s).\n"
    assert "variable" not in output


def test_workflow_check_prints_located_diagnostics(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    args = cli.build_parser().parse_args(["workflow", "check"])
    monkeypatch.setattr(cli, "action_values", lambda path: [])
    monkeypatch.setattr(
        cli,
        "check_workflows",
        lambda *args: {
            "unreferenced": [{"file": ".env", "line": 4, "severity": "warning", "name": "LOCAL", "message": "LOCAL is declared as gh-vault variable but not referenced by a workflow"}],
            "type_mismatch": [{"file": "export.yml", "line": 12, "severity": "error", "name": "REGION", "message": "secrets.REGION is referenced but .env declares REGION as gh-vault variable"}],
            "order": [],
            "orphan": [{"file": "export.yml", "line": 13, "severity": "warning", "name": "OPTIONAL", "message": "vars.OPTIONAL is not declared locally and has no fallback default"}],
        },
    )

    assert cli.dispatch(args, MemoryStore()) == 1  # type: ignore[arg-type]
    assert capsys.readouterr().out.splitlines() == [
        ".env:4: warning: LOCAL is declared as gh-vault variable but not referenced by a workflow",
        "export.yml:12: error: secrets.REGION is referenced but .env declares REGION as gh-vault variable",
        "export.yml:13: warning: vars.OPTIONAL is not declared locally and has no fallback default",
    ]


def test_secret_check_reports_missing_remote_secrets(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    args = cli.build_parser().parse_args(["secret", "check"])
    monkeypatch.setattr(cli, "remote_secret_status", lambda *args: RemoteValueStatus(["API_KEY"], [], [], [], [], []))

    assert cli.dispatch(args, MemoryStore()) == 1  # type: ignore[arg-type]
    assert capsys.readouterr().out == "Missing GitHub secrets: API_KEY\n"


def test_secret_check_reports_secret_to_variable_type_drift(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    args = cli.build_parser().parse_args(["secret", "check"])
    monkeypatch.setattr(cli, "remote_secret_status", lambda *args: RemoteValueStatus([], [], [], [], ["SIGNIN_CLIENT_ID"], []))

    assert cli.dispatch(args, MemoryStore()) == 1  # type: ignore[arg-type]
    assert capsys.readouterr().out == "SIGNIN_CLIENT_ID: GitHub variable -> gh-vault secret\n"


def test_secret_check_reports_remote_secrets_absent_from_env(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    args = cli.build_parser().parse_args(["secret", "check"])
    monkeypatch.setattr(cli, "remote_secret_status", lambda *args: RemoteValueStatus([], [], ["OWNCLOUD_SSH_PASSWORD"], [], [], []))

    assert cli.dispatch(args, MemoryStore()) == 1  # type: ignore[arg-type]
    assert capsys.readouterr().out == "GitHub secret OWNCLOUD_SSH_PASSWORD is not declared in .env\n"


def test_secret_check_omits_variable_only_findings(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    args = cli.build_parser().parse_args(["secret", "check"])
    monkeypatch.setattr(
        cli,
        "remote_secret_status",
        lambda *args: RemoteValueStatus([], ["MISSING_VAR"], [], ["REMOTE_VAR"], [], ["JMED_SMTP_FROM"]),
    )

    assert cli.dispatch(args, MemoryStore()) == 0  # type: ignore[arg-type]
    assert capsys.readouterr().out == "All local secret values are configured on GitHub.\n"


def test_secret_check_reports_success_when_only_secrets_match(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    args = cli.build_parser().parse_args(["secret", "check"])
    monkeypatch.setattr(cli, "remote_secret_status", lambda *args: RemoteValueStatus([], [], [], [], [], []))

    assert cli.dispatch(args, MemoryStore()) == 0  # type: ignore[arg-type]
    assert capsys.readouterr().out == "All local secret values are configured on GitHub.\n"


def test_variable_check_reports_missing_remote_variables(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    args = cli.build_parser().parse_args(["variable", "check"])
    monkeypatch.setattr(cli, "remote_secret_status", lambda *args: RemoteValueStatus([], ["REGION"], [], [], [], []))

    assert cli.dispatch(args, MemoryStore()) == 1  # type: ignore[arg-type]
    assert capsys.readouterr().out == "Missing GitHub variables: REGION\n"


def test_variable_check_reports_variable_to_secret_type_drift(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    args = cli.build_parser().parse_args(["variable", "check"])
    monkeypatch.setattr(cli, "remote_secret_status", lambda *args: RemoteValueStatus([], [], [], [], [], ["JMED_SMTP_FROM"]))

    assert cli.dispatch(args, MemoryStore()) == 1  # type: ignore[arg-type]
    assert capsys.readouterr().out == "JMED_SMTP_FROM: GitHub secret -> gh-vault variable\n"


def test_variable_check_reports_remote_variables_absent_from_env(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    args = cli.build_parser().parse_args(["variable", "check"])
    monkeypatch.setattr(cli, "remote_secret_status", lambda *args: RemoteValueStatus([], [], [], ["REMOTE_VAR"], [], []))

    assert cli.dispatch(args, MemoryStore()) == 1  # type: ignore[arg-type]
    assert capsys.readouterr().out == "GitHub variable REMOTE_VAR is not declared in .env\n"


def test_variable_check_omits_secret_only_findings(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    args = cli.build_parser().parse_args(["variable", "check"])
    monkeypatch.setattr(
        cli,
        "remote_secret_status",
        lambda *args: RemoteValueStatus(["MISSING_SECRET"], [], ["ORPHAN_SECRET"], [], ["SIGNIN_CLIENT_ID"], []),
    )

    assert cli.dispatch(args, MemoryStore()) == 0  # type: ignore[arg-type]
    assert capsys.readouterr().out == "All local variable values are configured on GitHub.\n"


def test_variable_check_reports_success_when_only_variables_match(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    args = cli.build_parser().parse_args(["variable", "check"])
    monkeypatch.setattr(cli, "remote_secret_status", lambda *args: RemoteValueStatus([], [], [], [], [], []))

    assert cli.dispatch(args, MemoryStore()) == 0  # type: ignore[arg-type]
    assert capsys.readouterr().out == "All local variable values are configured on GitHub.\n"


def test_list_marks_active_profile(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli._list(MemoryStore()) == 0  # type: ignore[arg-type]
    output = capsys.readouterr().out
    assert "* read" in output
    assert "scopes=contents:read" in output
    assert "expires=2026-12-31 23:59:59 UTC" in output
    assert "token-read" not in output


def test_git_credential_returns_selected_token_only_for_github(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO("protocol=https\nhost=github.com\n\n"))
    assert cli._git_credential(MemoryStore(), "get") == 0  # type: ignore[arg-type]
    assert capsys.readouterr().out == "username=x-access-token\npassword=token-read\n\n"

    monkeypatch.setattr("sys.stdin", io.StringIO("host=example.com\n\n"))
    assert cli._git_credential(MemoryStore(), "get") == 0  # type: ignore[arg-type]
    assert capsys.readouterr().out == ""

    monkeypatch.setattr("sys.stdin", io.StringIO("protocol=http\nhost=github.com\n\n"))
    assert cli._git_credential(MemoryStore(), "get") == 0  # type: ignore[arg-type]
    assert capsys.readouterr().out == ""


def test_run_executes_with_both_supported_environment_variables(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: dict[str, object] = {}

    def fake_exec(file: str, args: list[str], env: dict[str, str]) -> None:
        observed.update(file=file, args=args, gh=env["GH_TOKEN"], github=env["GITHUB_TOKEN"])
        raise RuntimeError("stop exec")

    monkeypatch.setattr(cli.os, "execvpe", fake_exec)
    with pytest.raises(RuntimeError, match="stop exec"):
        cli._run(MemoryStore(), "write", ["--", "gh", "repo", "view"])  # type: ignore[arg-type]

    assert observed == {
        "file": "gh",
        "args": ["gh", "repo", "view"],
        "gh": "token-write",
        "github": "token-write",
    }


def test_run_requires_a_command() -> None:
    with pytest.raises(StoreError, match="requires a command"):
        cli._run(MemoryStore(), None, [])  # type: ignore[arg-type]
