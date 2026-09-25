# tests

## Purpose

Deterministic pytest coverage for CLI and credential boundaries, GitHub token metadata inspection, local Bitwarden adapter isolation, profile/connection persistence, and the `pass` integration contract.

## Ownership

| Item | Role |
|---|---|
| `test_cli.py` | Parser helpers, token metadata integration, profile listing, Git credential output filtering, migrations, and `run` / `env run` / `run-act` dispatch behavior using an in-memory store. |
| `test_store.py` | Token and environment store lifecycle, restrictive permissions, payload/index isolation, replacement rules, validation, missing-secret errors, and a temporary executable fake `pass` backend. |
| `test_bitwarden_connection.py` | Synthetic bws profile parsing, connection drift, credential-source isolation, explicit local-adapter loading, and project-result validation. |
| `test_bitwarden_environments.py` | Synthetic exact-name Bitwarden reads/writes, previewed upload, fresh-clone dotenv recovery, response isolation, portable round trips, and atomic replacement. |
| `test_bitwarden_actions.py` | Synthetic Bitwarden-to-GitHub standby preview/apply plus dual-provider artifact generation, selectors, aliases/defaults, scope isolation, stdin writes, read-back verification, partial failure, and value-free metadata. |
| `test_vault_features.py` | Project-origin namespace normalization, dotenv and two-stage migration contracts, split archive/restore/show boundaries, remote Actions type checks, persistent exports, ephemeral `act` lifecycle, and workflow-wiring checks. |
| `test_capability_boundaries.py` | End-to-end local characterization of documented limitations and generated dual-provider diagnostics, with only external subprocess boundaries replaced. |
| `records/` | Synthetic Node record-validator regressions, isolated from Python product tests. |

## Local Contracts

- Tests never use real GitHub tokens, the operator's password store, or the operator's config directory.
- Store integration tests pass explicit temporary config and password-store directories plus a fake `pass_tool`; fake secrets remain under pytest's temporary directory.
- Secret assertions use synthetic values and verify that metadata does not contain them.
- CLI process replacement is intercepted with `monkeypatch`; tests must not exec real child commands.
- Environment and workflow tests use temporary files plus mocked Git/GitHub subprocess boundaries; they must not read a real `.env`, password store, or GitHub account.
- Bitwarden tests use synthetic TOML, UUIDs, access tokens, and local adapter packages under pytest temporary directories. They never import the SDK, read the operator's bws config, or contact Bitwarden.
- Bitwarden environment tests recreate and upload only temporary `.env` files through synthetic adapter responses; local-only entries remain outside adapter requests, write read-backs are validated in-process, and no cached mapping is assumed.
- Bitwarden Actions tests publish only synthetic adapter values through mocked `gh` processes and generate value-free workflow fragments from synthetic UUIDs. They assert explicit repository/Environment scope, no delete/selector mutation, exact Variable read-back, Secret name/type-only evidence, provider branch isolation, selector rules, duplicate rejection, and metadata/artifacts with no values or hashes.
- Environment-scoped Actions tests assert the read-only GitHub Environment preflight and every `--env` argument, including the scope-local delete/migration boundary.
- Git credential tests cover allowed protocol/host combinations and assert the exact protocol response.
- Permission checks target POSIX mode `0700` for config/environment/publication directories and `0600` for metadata, payload, and index JSON files.

## Work Guidance

- Add regression coverage at the public behavior boundary that changed; use private helpers only when they are the boundary under test.
- Profile-reference directive coverage lives in `test_vault_features.py` alongside the typed-dotenv tests; `MemoryVault` exposes `get` and `profiles` to satisfy the `VaultStore` duck-type used by `action_values` and `runtime_environment`.
- Keep tests offline and independent of installed `pass`, GPG keys, `gh`, and GitHub access.
- Preserve explicit synthetic token values so leakage into output or metadata is detectable.
- Extend the fake backend only for behavior required by `TokenStore`; do not turn it into a general password-store emulator.

## Verification

- `make test-python` runs isolated offline pytest without updating the project lockfile.
- `make test` runs both the offline Python suite and the Node record suite; `make verify` also checks the live records.

## Child DOX Index

| Child | Owns | Read when editing… |
| --- | --- | --- |
| `records/AGENTS.md` | Node record-validator tests and synthetic fixture trees | Maintenance validator evidence or fixtures |

Cross-references:

- `../src/gh_vault/AGENTS.md` — production contracts exercised here.
- `../pyproject.toml` — pytest discovery and import-path configuration.
