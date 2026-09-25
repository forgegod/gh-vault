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


def test_workflow_check_accepts_generated_dual_provider_block_and_rejects_bootstrap_leak(
    tmp_path: Path,
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "# gh-vault: variable\nREGION=eu\n"
        "# gh-vault: secret\nAPI_KEY=synthetic\n",
        encoding="utf-8",
    )
    artifact = actions.render_dual_provider_workflow(
        (
            actions.WorkflowValue(
                "REGION",
                "variable",
                "33333333-3333-4333-8333-333333333331",
                "APP_REGION",
                None,
            ),
            actions.WorkflowValue(
                "API_KEY",
                "secret",
                "33333333-3333-4333-8333-333333333332",
                "APP_API_KEY",
                None,
            ),
        ),
        connection="eu-production",
        project_id="22222222-2222-4222-8222-222222222222",
        organization_id="11111111-1111-4111-8111-111111111111",
        repo="owner/repo",
        github_environment=None,
        region="eu",
        consumer_command="python app.py",
    )
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    workflow = workflows / "dual.yml"
    workflow.write_text(
        "name: Synthetic dual provider\n"
        "on:\n"
        "  workflow_dispatch:\n"
        "    inputs:\n"
        "      config_source:\n"
        "        type: choice\n"
        "        default: repository\n"
        "        options:\n"
        "          - repository\n"
        "          - github\n"
        "          - bitwarden\n"
        "jobs:\n"
        "  test:\n"
        "    runs-on: ubuntu-latest\n"
        "    steps:\n"
        + artifact.text,
        encoding="utf-8",
    )
    entries = actions.action_values(env_file, VaultStore(config_dir=tmp_path / "config", pass_tool="unused-pass"))
    result = actions.check_workflows(tmp_path, entries)
    assert result["bootstrap"] == []
    assert result["unreferenced"] == []
    assert result["type_mismatch"] == []
    assert result["order"] == []

    original = workflow.read_text(encoding="utf-8")
    workflow.write_text(
        original.replace(
            "33333333-3333-4333-8333-333333333331 > APP_REGION",
            "33333333-3333-4333-8333-333333333339 > APP_REGION",
            1,
        ),
        encoding="utf-8",
    )
    result = actions.check_workflows(tmp_path, entries)
    assert any("mapping for REGION is stale or missing" in str(finding["message"]) for finding in result["order"])

    workflow.write_text(
        original.replace(
            '[ -n "$APP_API_KEY" ] || { echo "::error::Missing Bitwarden value: APP_API_KEY"; exit 1; }\n',
            "",
        ),
        encoding="utf-8",
    )
    result = actions.check_workflows(tmp_path, entries)
    assert any("required bitwarden value APP_API_KEY" in str(finding["message"]) for finding in result["order"])

    workflow.write_text(
        original.replace(
            "# gh-vault: dual-provider-v1\n",
            "      - uses: actions/checkout@v4\n"
            "        with:\n"
            "          submodules: recursive\n"
            "# gh-vault: dual-provider-v1\n",
            1,
        ),
        encoding="utf-8",
    )
    result = actions.check_workflows(tmp_path, entries)
    assert any("retrieval must precede checkout with submodules" in str(finding["message"]) for finding in result["order"])

    workflow.write_text(original, encoding="utf-8")

    workflow.write_text(
        workflow.read_text(encoding="utf-8")
        + "      - name: Leak bootstrap\n"
        + "        env:\n"
        + "          LEAK: ${{ secrets.BWS_ACCESS_TOKEN }}\n"
        + "        run: echo bad\n",
        encoding="utf-8",
    )
    result = actions.check_workflows(tmp_path, entries)
    assert result["bootstrap"] == [
        {
            "file": "dual.yml",
            "line": len(workflow.read_text(encoding="utf-8").splitlines()) - 1,
            "severity": "error",
            "name": "BWS_ACCESS_TOKEN",
            "message": "BWS_ACCESS_TOKEN reference outside a recognized dual-provider block",
        }
    ]
