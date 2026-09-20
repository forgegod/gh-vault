# CHG-003 — Environment-scoped GitHub Actions values

**Status:** done
**External request:** Direct operator request: Implement explicit GitHub Environment targeting for Actions secret and variable synchronization, comparison, and import while retaining repository scope as the default.
**Impacts:** CAP-006
**Baseline:** `d97de53`

| # | Phase | Status | Verification gate |
|---|---|---|---|
| 1 | Specify scoped remote-operation contract | done (`uv run --no-project --with pytest python -m pytest tests/test_vault_features.py -k environment_scoped` failed as expected) | Focused regression tests demonstrate the absent environment-target capability |
| 2 | Implement scoped remote operations | done (`uv run --no-project --with pytest python -m pytest tests/test_vault_features.py tests/test_cli.py` passed) | Focused offline pytest coverage exits 0 |
| 3 | Integrate current-state records | done (`make verify` passed) | `make verify` exits 0 |

## Phase 1 — Specify scoped remote-operation contract

**Goal:** Separate a local dotenv source profile from an explicit GitHub Environment target.

1. Add regression coverage for repository-default and `--github-environment` command routing.
2. Require environment existence preflight before any environment-scoped list, set, delete, or import operation.
3. Keep repository and environment stores independent for comparisons, type migration, and prune.

**Verification gate:** Focused regression tests demonstrate the absent environment-target capability.

## Phase 2 — Implement scoped remote operations

**Goal:** Route secret/variable sync, check, and variable import through either repository scope or one explicitly named GitHub Environment.

1. Add `--github-environment NAME` to the remote Actions commands; no flag retains repository scope.
2. Preflight a specified environment through the GitHub deployment-environments API without creating or configuring it.
3. Pass the selected environment to every `gh` secret/variable list, set, remove, delete, and import operation in that request.
4. Keep `--prune` and `--migrate-types` strictly within the selected scope.

**Verification gate:** Focused offline pytest coverage exits 0.

## Phase 3 — Integrate current-state records

**Goal:** Publish the verified current contract and archive the completed change receipt.

1. Update CAP-006, README, architecture, design rationale, and affected DOX with the explicit remote-scope contract.
2. Run the full record and offline test gate.
3. Set this CHG to `done`, move it to `archive/`, and refresh the change index.

**Verification gate:** `make verify` exits 0.

## Out of scope

- Creating, deleting, or configuring GitHub Environments, protection rules, required reviewers, wait timers, or deployment branch policies.
- Inferring a GitHub Environment from an `.env.<profile>` filename.
- Per-declaration environment-target syntax.
- Parsing job-level `environment:` mappings in `workflow check`.
