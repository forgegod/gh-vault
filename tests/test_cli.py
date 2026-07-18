from __future__ import annotations

import argparse
import io
from pathlib import Path

import pytest

from gh_vault import cli
from gh_vault.actions import ActionValue, RemoteValueStatus, SyncResult
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
        (["secrets", "sync", "--help"], "Set gh-vault secret declarations as GitHub Secrets"),
        (["secrets", "export-act", "--help"], "Write gh-vault secret declarations to .secrets"),
        (["secrets", "check", "--help"], "Compare typed gh-vault declarations"),
        (["variables", "import", "--help"], "Import repository Variables with gh-vault variable directives"),
        (["workflow", "check", "--help"], "Report missing, mismatched, and unreferenced"),
    ],
)
def test_subtool_help_explains_its_operation(arguments: list[str], description: str, capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit, match="0"):
        cli.build_parser().parse_args(arguments)

    assert description in capsys.readouterr().out


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


def test_parser_accepts_variable_import_and_secret_check_commands() -> None:
    args = cli.build_parser().parse_args(["variables", "import", "--force"])
    assert args.variables_command == "import"
    assert args.force is True
    assert cli.build_parser().parse_args(["secrets", "check"]).secrets_command == "check"


def test_sync_rejects_prune_with_type_migration() -> None:
    with pytest.raises(SystemExit, match="2"):
        cli.build_parser().parse_args(["secrets", "sync", "--prune", "--migrate-types"])


def test_sync_dry_run_reports_prune_count(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    args = cli.build_parser().parse_args(["secrets", "sync", "--dry-run", "--prune"])
    monkeypatch.setattr(cli, "action_values", lambda path: [ActionValue("API_KEY", "secret", "value")])
    monkeypatch.setattr(cli, "sync", lambda *args: SyncResult(1, 2))

    assert cli.dispatch(args, MemoryStore()) == 0  # type: ignore[arg-type]
    assert capsys.readouterr().out == "Would sync 1 entry(s); would prune 2 remote value(s).\n"


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
    args = cli.build_parser().parse_args(["secrets", "check"])
    monkeypatch.setattr(cli, "remote_secret_status", lambda *args: RemoteValueStatus(["API_KEY"], [], [], [], [], []))

    assert cli.dispatch(args, MemoryStore()) == 1  # type: ignore[arg-type]
    assert capsys.readouterr().out == "Missing GitHub secrets: API_KEY\n"


def test_secret_check_reports_secret_to_variable_type_drift(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    args = cli.build_parser().parse_args(["secrets", "check"])
    monkeypatch.setattr(cli, "remote_secret_status", lambda *args: RemoteValueStatus([], [], [], [], ["SIGNIN_CLIENT_ID"], []))

    assert cli.dispatch(args, MemoryStore()) == 1  # type: ignore[arg-type]
    assert capsys.readouterr().out == "SIGNIN_CLIENT_ID: GitHub variable -> gh-vault secret\n"


def test_secret_check_reports_remote_secrets_absent_from_env(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    args = cli.build_parser().parse_args(["secrets", "check"])
    monkeypatch.setattr(cli, "remote_secret_status", lambda *args: RemoteValueStatus([], [], ["OWNCLOUD_SSH_PASSWORD"], [], [], []))

    assert cli.dispatch(args, MemoryStore()) == 1  # type: ignore[arg-type]
    assert capsys.readouterr().out == "GitHub secret OWNCLOUD_SSH_PASSWORD is not declared in .env\n"


def test_secret_check_reports_variable_to_secret_type_drift(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    args = cli.build_parser().parse_args(["secrets", "check"])
    monkeypatch.setattr(cli, "remote_secret_status", lambda *args: RemoteValueStatus([], [], [], [], [], ["JMED_SMTP_FROM"]))

    assert cli.dispatch(args, MemoryStore()) == 1  # type: ignore[arg-type]
    assert capsys.readouterr().out == "JMED_SMTP_FROM: GitHub secret -> gh-vault variable\n"


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
