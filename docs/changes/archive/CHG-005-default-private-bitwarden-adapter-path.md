# CHG-005 — Default private Bitwarden adapter path

**Status:** done
**External request:** Direct operator request: “Can we change the default path where the checkout is found to e.g. ~/.config/gh-vault/{gh-vault-bws} and give the user the instructions to git checkout there?” Follow-up: use `~/.local/share` or another standard path if better.
**Impacts:** CAP-002
**Baseline:** `9545ceffe4ed0499b6587eb21ac90e6fb97576d1`

| # | Phase | Status | Verification gate |
| --- | --- | --- | --- |
| 1 | Specify default and preservation boundary | done (direct operator request recorded) | This record names the exact default, the retained override, and the no-fetch boundary. |
| 2 | Resolve the default in every Bitwarden operation | done (132 focused tests) | Focused Bitwarden and parser tests exit 0. |
| 3 | Reconcile contracts and integrate | done (`make verify`: 304 Python and 82 Node tests) | `make verify` exits 0. |

## Phase 1 — Specify default and preservation boundary

**Goal:** Use one documented private checkout path without turning gh-vault into an adapter distributor or updater.

1. Default every adapter-consuming command to `${XDG_DATA_HOME:-~/.local/share}/gh-vault/adapters/gh-vault-bws`, keeping executable source outside the XDG configuration tree.
2. Retain `--adapter-path` for an explicit alternate checkout.
3. Document manual `git clone` checkout only; do not fetch, install, update, or describe Bitwarden SDK call sequences.

**Verification gate:** This record names the exact default, the retained override, and the no-fetch boundary.

## Phase 2 — Resolve the default in every Bitwarden operation

**Goal:** Project, environment, and Actions Bitwarden commands use the manual default when no override is supplied.

1. Add one default-path resolver under the Bitwarden module.
2. Apply it consistently to parser defaults and every adapter loader call.
3. Assert parser and dispatch selection with synthetic adapters.

**Verification gate:** `uv run --no-project --with pytest python -m pytest tests/test_bitwarden_connection.py tests/test_cli.py` exits 0.

## Phase 3 — Reconcile contracts and integrate

**Goal:** Current documentation describes manual private checkout setup and all local gates pass.

1. Update README, CAP-002, architecture, security, design rationale, and relevant DOX contracts.
2. Archive this change after the integration gate passes.

**Verification gate:** `make verify` exits 0.

## Out of scope

- Adapter fetch, update, installation, packaging, or SDK dependency handling by gh-vault.
- Public adapter distribution or SDK call sequences.
- Live GitHub, Bitwarden, GPG, or password-store verification.
