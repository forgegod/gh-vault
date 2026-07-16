# github_token_safe package

## Purpose

Production package for storing named GitHub tokens through `pass`, selecting an active profile, and supplying a selected token to child commands or Git's credential-helper protocol.

## Ownership

| Item | Role |
|---|---|
| `__init__.py` | Package identity and runtime version. |
| `cli.py` | Argument parsing, profile-name and scope validation, command dispatch, child-process environment injection, and Git credential-helper protocol. |
| `store.py` | Profile metadata model, restrictive config persistence, `pass` subprocess integration, active-profile state, and backend error normalization. |

## Local Contracts

- `github-token-safe` is the only console command and enters `github_token_safe.cli:main` as configured in `pyproject.toml`; do not add acronym aliases that collide with common shell tooling.
- Profile names are 1–64 characters and contain only letters, digits, `.`, `_`, or `-`; the first character is alphanumeric.
- `--scopes` metadata is operator-declared, trimmed, order-preserving, and deduplicated. It is not presented as GitHub-verified.
- Token values are non-empty single lines stored only through `pass` under `github-token-safe/<profile>` in `${PASSWORD_STORE_DIR:-~/.password-store}`; `TokenStore` passes that location explicitly to the backend.
- `${XDG_CONFIG_HOME:-~/.config}/github-token-safe/config.json` contains metadata only. Its directory is mode `0700`, the file is mode `0600`, and writes replace an adjacent temporary file atomically.
- The first added profile becomes active. Removing the active profile leaves no active profile; selection never falls back implicitly.
- `run` sets both `GH_TOKEN` and `GITHUB_TOKEN` only in the exec'd child environment and does not mutate the invoking shell.
- `git-credential get` responds only to HTTPS requests for `github.com`. `store` and `erase` are no-ops, and token output is limited to Git's exact credential response.
- Backend and config failures raise `StoreError`; the CLI converts them into argparse errors without exposing token values.

## Work Guidance

- Keep token values out of command arguments, config files, logs, ordinary stdout, and exception text.
- Preserve the explicit `pass` dependency; do not add plaintext storage or silently choose another profile.
- Keep the default password store and metadata paths in the user's home environment, outside the source checkout.
- When changing a command, update parser wiring, dispatch behavior, tests, and the matching README usage/security text.
- Keep config writes restrictive and crash-safe; metadata changes must not weaken directory or file modes.

## Verification

- `pytest`

## Child DOX Index

No nested AGENTS.md files.

Cross-references:

- `../../tests/AGENTS.md` — executable package contracts and fake `pass` backend.
- `../../README.md` — user-facing command and security behavior.
- `../../pyproject.toml` — package discovery and console entry points.
