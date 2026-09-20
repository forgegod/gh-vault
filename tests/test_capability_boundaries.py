"""Characterize source-backed capability limits without live credentials.

These tests describe the current boundary, not a recommendation to preserve a
limitation forever. A material fix must update its CAP and assertions together.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from gh_vault import actions, cli
from gh_vault.envfiles import parse_dotenv
from gh_vault.store import StoreError, VaultStore


@pytest.mark.parametrize("kind,opposite", [("secret", "variable"), ("variable", "secret")])
def test_cli_prune_does_not_preserve_opposite_type_or_empty_declarations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: str, opposite: str
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        f"# gh-vault: {kind}\nKEEP=synthetic-value\n"
        f"# gh-vault: {opposite}\nOTHER=synthetic-value\n"
        f"# gh-vault: {kind}\nEMPTY=\n",
        encoding="utf-8",
    )
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        assert command[:2] == ["gh", kind]
        if command[2] == "list":
            return subprocess.CompletedProcess(command, 0, "KEEP\nOTHER\nEMPTY\n", "")
        assert command[2] in {"set", "remove", "delete"}
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(actions.subprocess, "run", fake_run)
    args = cli.build_parser().parse_args([
        kind, "sync", "--prune", "--repo", "example/project", "--env-file", str(env_file),
    ])
    store = VaultStore(config_dir=tmp_path / "config", pass_tool="unused-pass")
    assert cli.dispatch(args, store, tmp_path) == 0
    removal = "remove" if kind == "secret" else "delete"
    assert [command[3] for command, _ in calls if command[2] == removal] == ["EMPTY", "OTHER"]
    sets = [(command, kwargs) for command, kwargs in calls if command[2] == "set"]
    assert len(sets) == 1
    assert sets[0][0][3] == "KEEP"
    assert sets[0][1]["input"] == "synthetic-value"
    assert "synthetic-value" not in " ".join(sets[0][0])


def test_run_act_rejects_profile_references_before_starting_child(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("# gh-vault: secret ci-token\nAPI_KEY=\n", encoding="utf-8")

    def unexpected_run(*args, **kwargs):
        pytest.fail("run-act must reject the unsupported reference before any child starts")

    monkeypatch.setattr(actions.subprocess, "run", unexpected_run)
    with pytest.raises(StoreError, match="requires a vault store"):
        actions.run_act(env_file, ["--", "act", "workflow_dispatch"], tmp_path)


@pytest.mark.parametrize("flags", [[], ["--json"], ["--fix"]])
def test_workflow_unreferenced_warning_alone_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], flags: list[str]
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("# gh-vault: variable\nUNUSED=synthetic\n", encoding="utf-8")
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "ci.yml").write_text("name: Synthetic workflow\n", encoding="utf-8")
    args = cli.build_parser().parse_args([
        "workflow", "check", "--env-file", str(env_file), *flags,
    ])
    store = VaultStore(config_dir=tmp_path / "config", pass_tool="unused-pass")
    assert cli.dispatch(args, store, tmp_path) == 1
    output = capsys.readouterr().out
    if flags == ["--json"]:
        result = json.loads(output)
        assert result["unreferenced"][0]["severity"] == "warning"
        assert result["type_mismatch"] == result["order"] == result["orphan"] == []
    else:
        assert ".env:2: warning: UNUSED" in output
        if flags == ["--fix"]:
            assert "Suggested env block:\n  UNUSED: ${{ vars.UNUSED }}" in output
    assert env_file.read_text(encoding="utf-8") == "# gh-vault: variable\nUNUSED=synthetic\n"


def test_persistent_export_leaves_empty_kind_file_untouched(tmp_path: Path) -> None:
    secrets = tmp_path / ".secrets"
    variables = tmp_path / ".vars"
    secrets.write_text("STALE=synthetic-old\n", encoding="utf-8")
    assert actions.export_act(
        [actions.ActionValue("REGION", "variable", "synthetic-region")], secrets, variables
    ) == (0, 1)
    assert secrets.read_text(encoding="utf-8") == "STALE=synthetic-old\n"
    assert variables.read_text(encoding="utf-8") == "REGION=synthetic-region\n"
    assert variables.stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize("literal", ["$(command)", "${NAME}", "`command`"])
def test_quoted_shell_metacharacters_remain_literal(tmp_path: Path, literal: str) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(f"SINGLE='{literal}'\nDOUBLE={json.dumps(literal)}\n", encoding="utf-8")
    assert parse_dotenv(env_file) == {"SINGLE": literal, "DOUBLE": literal}
