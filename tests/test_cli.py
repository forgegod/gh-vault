from __future__ import annotations

import argparse
import io
from pathlib import Path

import pytest

from gh_vault import cli
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


def test_add_discovers_scopes_and_expiration(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    args = cli.build_parser().parse_args(["add", "release", "--stdin"])
    store = MemoryStore()
    captured: dict[str, object] = {}

    monkeypatch.setattr(cli, "_read_token", lambda use_stdin: "token-value")
    monkeypatch.setattr(cli, "inspect_token", lambda token: TokenMetadata(("repo", "workflow"), "2026-12-31 23:59:59 UTC"))
    monkeypatch.setattr(store, "put", lambda profile, token, replace: captured.update(profile=profile, token=token, replace=replace), raising=False)

    assert cli.dispatch(args, store) == 0  # type: ignore[arg-type]
    assert captured == {
        "profile": Profile("release", ("repo", "workflow"), "", "2026-12-31 23:59:59 UTC"),
        "token": "token-value",
        "replace": False,
    }
    assert capsys.readouterr().out == "Validated GitHub token: scopes=repo,workflow expires=2026-12-31 23:59:59 UTC\nStored profile: release\n"


def test_add_preserves_expiration_with_manual_scopes(monkeypatch: pytest.MonkeyPatch) -> None:
    args = cli.build_parser().parse_args(["add", "release", "--stdin", "--scopes", "read:org"])
    store = MemoryStore()
    captured: dict[str, Profile] = {}

    monkeypatch.setattr(cli, "_read_token", lambda use_stdin: "token-value")
    monkeypatch.setattr(cli, "inspect_token", lambda token: TokenMetadata(("repo",), "2026-12-31 23:59:59 UTC"))
    monkeypatch.setattr(store, "put", lambda profile, token, replace: captured.update(profile=profile), raising=False)

    assert cli.dispatch(args, store) == 0  # type: ignore[arg-type]
    assert captured["profile"] == Profile("release", ("read:org",), "", "2026-12-31 23:59:59 UTC")


def test_add_with_manual_scopes_allows_unavailable_inspection(monkeypatch: pytest.MonkeyPatch) -> None:
    args = cli.build_parser().parse_args(["add", "release", "--stdin", "--scopes", "read:org"])
    store = MemoryStore()
    captured: dict[str, Profile] = {}

    def unavailable(token: str) -> TokenMetadata:
        raise StoreError("GitHub API is unavailable")

    monkeypatch.setattr(cli, "_read_token", lambda use_stdin: "token-value")
    monkeypatch.setattr(cli, "inspect_token", unavailable)
    monkeypatch.setattr(store, "put", lambda profile, token, replace: captured.update(profile=profile), raising=False)

    assert cli.dispatch(args, store) == 0  # type: ignore[arg-type]
    assert captured["profile"] == Profile("release", ("read:org",))


def test_parser_rejects_removed_legacy_migration_command() -> None:
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args(["migrate"])


def test_parser_accepts_variable_import_and_secret_check_commands() -> None:
    args = cli.build_parser().parse_args(["variables", "import", "--force"])
    assert args.variables_command == "import"
    assert args.force is True
    assert cli.build_parser().parse_args(["secrets", "check"]).secrets_command == "check"


def test_secret_check_reports_missing_remote_secrets(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    args = cli.build_parser().parse_args(["secrets", "check"])
    monkeypatch.setattr(cli, "remote_secret_status", lambda *args: (["API_KEY"], [], [], []))

    assert cli.dispatch(args, MemoryStore()) == 1  # type: ignore[arg-type]
    assert capsys.readouterr().out == "Missing GitHub secrets: API_KEY\n"


def test_secret_check_reports_secret_to_variable_migrations(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    args = cli.build_parser().parse_args(["secrets", "check"])
    monkeypatch.setattr(cli, "remote_secret_status", lambda *args: ([], ["API_KEY"], [], []))

    assert cli.dispatch(args, MemoryStore()) == 0  # type: ignore[arg-type]
    assert capsys.readouterr().out == "API_KEY -> GH_VAR_API_KEY\n"


def test_secret_check_reports_remote_secrets_absent_from_env(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    args = cli.build_parser().parse_args(["secrets", "check"])
    monkeypatch.setattr(cli, "remote_secret_status", lambda *args: ([], [], ["OWNCLOUD_SSH_PASSWORD"], []))

    assert cli.dispatch(args, MemoryStore()) == 1  # type: ignore[arg-type]
    assert capsys.readouterr().out == "GH_SECRET_OWNCLOUD_SSH_PASSWORD is not set in .env\n"


def test_secret_check_reports_variable_to_secret_type_drift(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    args = cli.build_parser().parse_args(["secrets", "check"])
    monkeypatch.setattr(cli, "remote_secret_status", lambda *args: ([], [], [], ["JMED_SMTP_FROM"]))

    assert cli.dispatch(args, MemoryStore()) == 1  # type: ignore[arg-type]
    assert capsys.readouterr().out == "GH_SECRET_JMED_SMTP_FROM -> GH_VAR_JMED_SMTP_FROM\n"


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
