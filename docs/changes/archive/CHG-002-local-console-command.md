# CHG-002 — Install the short console command

**Status:** done
**External request:** Direct operator request: Change local installation from forgegod-gh-vault to gh-vault even if the project is called forgegod-gh-vault
**Impacts:** CAP-002
**Baseline:** `197e10ce6e1995b69fe99a5b8d0cb9fafe1237bd`

| # | Phase | Status | Verification gate |
|---|---|---|---|
| 1 | Specify changed installation contract | done (`tests/test_cli.py -k project_declares_short_console_command` failed as expected) | Focused packaging assertion fails because `gh-vault` is not declared |
| 2 | Implement package entry point | done (focused pytest and isolated install passed) | Fresh isolated install exposes `gh-vault` and not `forgegod-gh-vault` |
| 3 | Integrate current-state records | done (`make verify` passed) | `make verify` exits 0 |

Mark a phase `in-progress` while executing it, `done (<evidence>)` only after its gate passes, and leave later phases `pending`.

## Phase 1 — Specify changed installation contract

**Goal:** Pin the desired installed command independently from the PyPI distribution name.

1. Keep `[project].name` as `forgegod-gh-vault`.
2. Add a focused assertion requiring `gh-vault` as the sole declared console command.

**Verification gate:** Focused packaging assertion fails because `gh-vault` is not declared.

## Phase 2 — Implement package entry point

**Goal:** Make a clean local installation create `gh-vault` without a `forgegod-gh-vault` executable.

1. Replace the console-script key in `pyproject.toml` without changing the package or module name.
2. Amend CAP-002, command documentation, and affected DOX contracts to name `gh-vault` while retaining the `forgegod-gh-vault` distribution.
3. Build and install the package in an isolated environment, then inspect the generated executable names and run `gh-vault --help`.

**Verification gate:** Fresh isolated install exposes `gh-vault` and not `forgegod-gh-vault`.

## Phase 3 — Integrate current-state records

**Goal:** Validate the complete repository state and archive this implementation receipt.

1. Run the full record and offline test gate.
2. Set this CHG to `done`, move it to `archive/`, and refresh the change index.

**Verification gate:** `make verify` exits 0.

## Out of scope

- Renaming the PyPI distribution, Python package, module entry point, repository, or storage namespace.
- Keeping `forgegod-gh-vault` as a compatibility executable.