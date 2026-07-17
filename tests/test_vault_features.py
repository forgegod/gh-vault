from __future__ import annotations

import stat
from pathlib import Path

from gh_vault.actions import ActionValue, action_values, check_workflows, export_act, sync
from gh_vault.envfiles import archive_environment, project_namespace, restore_environment


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
