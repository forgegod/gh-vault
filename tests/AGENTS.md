# tests

## Purpose

Deterministic pytest coverage for the CLI boundary, GitHub token metadata inspection, credential-helper filtering, child-process token injection, profile metadata persistence, and the `pass` integration contract.

## Ownership

| Item | Role |
|---|---|
| `test_cli.py` | Parser helpers, token metadata integration, profile listing, Git credential output filtering, and `run` / `env run` process-environment behavior using an in-memory store. |
| `test_store.py` | Store lifecycle, restrictive permissions, replacement rules, token validation, missing-secret errors, and a temporary executable fake `pass` backend. |
| `test_vault_features.py` | Project-origin namespace normalization, mocked GitHub token metadata, encrypted default and named environment archive/restore/list behavior, remote Actions type checks, `act` exports, and workflow-wiring checks. |

## Local Contracts

- Tests never use real GitHub tokens, the operator's password store, or the operator's config directory.
- Store integration tests pass explicit temporary config and password-store directories plus a fake `pass_tool`; fake secrets remain under pytest's temporary directory.
- Secret assertions use synthetic values and verify that metadata does not contain them.
- CLI process replacement is intercepted with `monkeypatch`; tests must not exec real child commands.
- Environment and workflow tests use temporary files plus mocked Git/GitHub subprocess boundaries; they must not read a real `.env`, password store, or GitHub account.
- Git credential tests cover allowed protocol/host combinations and assert the exact protocol response.
- Permission checks target POSIX mode `0700` for the config directory and `0600` for `config.json`.

## Work Guidance

- Add regression coverage at the public behavior boundary that changed; use private helpers only when they are the boundary under test.
- Keep tests offline and independent of installed `pass`, GPG keys, `gh`, and GitHub access.
- Preserve explicit synthetic token values so leakage into output or metadata is detectable.
- Extend the fake backend only for behavior required by `TokenStore`; do not turn it into a general password-store emulator.

## Verification

- `pytest`

## Child DOX Index

No nested AGENTS.md files.

Cross-references:

- `../src/gh_vault/AGENTS.md` — production contracts exercised here.
- `../pyproject.toml` — pytest discovery and import-path configuration.
