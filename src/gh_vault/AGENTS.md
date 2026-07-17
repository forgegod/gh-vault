# gh_vault package

## Purpose

Production package for storing named GitHub tokens and project environment archives through `pass`, selecting an active profile, syncing Actions values, and supplying a selected token to child commands or Git's credential-helper protocol.

## Ownership

| Item | Role |
|---|---|
| `__init__.py` | Package identity and runtime version. |
| `__main__.py` | Module entry point delegating to the CLI. |
| `cli.py` | Command dispatch for profiles, archives, Actions sync, workflow checks, child-process injection, and Git credential helper. |
| `store.py` | Profile metadata, restrictive config persistence, `pass` integration, legacy migration, and backend errors. |
| `envfiles.py` | Safe dotenv parsing, origin namespace resolution, encrypted archive and reconstruction. |
| `actions.py` | GitHub Actions value selection, `gh` sync, `act` exports, and workflow references. |

## Local Contracts

- `gh-vault` is the only console command and enters `gh_vault.cli:main`; do not add aliases that collide with shell tooling.
- Profile names are 1–64 characters and contain only letters, digits, `.`, `_`, or `-`; the first character is alphanumeric.
- `--scopes` metadata is operator-declared, trimmed, order-preserving, and deduplicated. It is not presented as GitHub-verified.
- Token values are non-empty single lines stored only through `pass` under `gh-vault/<profile>` in `${PASSWORD_STORE_DIR:-~/.password-store}`; archive data also stays below that namespace.
- `${XDG_CONFIG_HOME:-~/.config}/gh-vault/config.json` contains metadata only. Its directory is mode `0700`, the file is mode `0600`, and writes replace an adjacent temporary file atomically.
- The first added profile becomes active. Removing the active profile leaves no active profile; selection never falls back implicitly.
- `run` sets both `GH_TOKEN` and `GITHUB_TOKEN` only in the exec'd child environment and does not mutate the invoking shell.
- `git-credential get` responds only to HTTPS requests for `github.com`. `store` and `erase` are no-ops, and token output is limited to Git's exact credential response.
- Backend and config failures raise `StoreError`; the CLI converts them into argparse errors without exposing token values.
- Environment archives require `remote.origin.url`, refuse to overwrite `.env` without `--force`, and reconstruct comments from `.env.example`.
- Actions sync accepts only `GH_SECRET_*` and `GH_VAR_*` values and sends them to `gh` on stdin. `--migrate-types` is the explicit destructive path: remove only a same-name opposite-type remote value, then set the declared type.

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
