# gh_vault package

## Purpose

Production package for storing named GitHub tokens and project environment archives through `pass`, selecting an active profile, syncing Actions values, and supplying a selected token to child commands or Git's credential-helper protocol.

## Ownership

| Item | Role |
|---|---|
| `__init__.py` | Package identity and runtime version. |
| `__main__.py` | Module entry point delegating to the CLI. |
| `cli.py` | Command dispatch for profiles, archives, explicit migrations, Actions sync, workflow checks, child-process injection, and Git credential helper. |
| `store.py` | Profile metadata, restrictive config and public environment persistence, `pass` integration, and backend errors. |
| `envfiles.py` | Safe ordinary and typed dotenv parsing, origin namespace resolution, split archive migration, public inspection, and reconstruction. |
| `github.py` | GitHub token metadata inspection without exposing token values. |
| `actions.py` | GitHub Actions value selection, explicit legacy declaration migration, remote-variable import, `gh` sync, persistent exports, ephemeral `act` execution, and workflow references. |

## Local Contracts

- `gh-vault` is the only console command and enters `gh_vault.cli:main`; do not add aliases that collide with shell tooling.
- Profile names are 1–64 characters and contain only letters, digits, `.`, `_`, or `-`; the first character is alphanumeric.
- `set` always creates or replaces the named profile.
- `set` validates a token with GitHub, prints its discovered scopes and available expiration without printing the token, and discovers classic-PAT scopes when `--scopes` is absent; explicit `--scopes` is trimmed, order-preserving, and deduplicated. GitHub-provided token expiration metadata is stored when available.
- Token values are non-empty single lines stored only through `pass` under `gh-vault/<profile>` in `${PASSWORD_STORE_DIR:-~/.password-store}`. Encrypted environment payloads stay below the same namespace; only explicitly public variable payloads may use `EnvironmentStore`. Secret reads remove only the single record-separator newline emitted by `pass`, preserving newlines that belong to multiline payloads.
- `${XDG_CONFIG_HOME:-~/.config}/gh-vault/config.json` contains metadata only. Its directory is mode `0700`, the file is mode `0600`, and writes replace an adjacent temporary file atomically.
- `EnvironmentStore` keeps explicitly public variable payloads and value-free environment indexes below `${XDG_CONFIG_HOME:-~/.config}/gh-vault/environments/<host>/<owner>/<repo>/`; every directory is mode `0700`, every JSON file is mode `0600`, and payload/index schemas remain separate and origin-bound.
- The first set profile becomes active. Removing the active profile leaves no active profile; selection never falls back implicitly.
- `run` sets both `GH_TOKEN` and `GITHUB_TOKEN` only in the exec'd child environment and does not mutate the invoking shell.
- `git-credential get` responds only to HTTPS requests for `github.com`. `store` and `erase` are no-ops, and token output is limited to Git's exact credential response.
- Backend and config failures raise `StoreError`; the CLI converts them into argparse errors without exposing token values.
- Environment archives require `remote.origin.url` and split typed declarations: variables use `EnvironmentStore`, secrets use version-3 encrypted entries below `gh-vault/projects/<host>/<path>/`, local values are excluded, and only profiles containing secrets may archive their matching template.
- `env list` and `env show` read only the public index/payload. Variable-only restore requires a local template and does not access `pass`; normal restore merges public variables and encrypted secrets without reconstructing local-only values.
- Typed dotenv parsing recognizes only an adjacent `# gh-vault: secret` or `# gh-vault: variable` directive, rejects duplicate and legacy-prefixed declarations, and reads commented template assignments only when explicitly requested. Ordinary `parse_dotenv()` behavior remains directive-agnostic.
- `env run -- <command> ...` execs a child with only typed `secret` and `variable` declarations under their ordinary keys; unmarked local values are excluded. The conservative dotenv parser decodes quotes and valid escapes without sourcing the file.
- `run-act -- act ...` creates mode-`0600` secret and variable files beneath a mode-`0700` temporary directory, appends both managed file flags, rejects caller-supplied file flags before allocation, and removes the directory after normal child completion.
- Migration is two-stage and explicit. `actions migrate-env` atomically rewrites only legacy-prefixed source/template assignments after full preflight validation. `env migrate` is the sole legacy archive reader; it partitions by reviewed directives, verifies destination payloads and index, rejects conflicting destinations, and removes the legacy payload last.
- Actions sync is type-scoped: `secret sync` sets only GitHub Secrets and `variable sync` sets only GitHub Variables. Each command accepts only typed declarations of its own kind and sends values to `gh` on stdin. `--migrate-types` is the explicit destructive path on each side: `secret sync --migrate-types` removes a same-name GitHub Variable before setting the Secret, and `variable sync --migrate-types` removes a same-name GitHub Secret before setting the Variable. `--prune` removes remote-only target-store names but preserves names declared locally under either type, and is mutually exclusive with type migration.
- `secret check` and `variable check` are independent and each compare local typed declarations with their own GitHub Actions type. `secret check` reports missing secrets, remote-only secrets, and secrets found remotely as Variables; `variable check` reports missing variables, remote-only variables, and variables found remotely as Secrets. Each command is nonzero for findings in its own scope only and never modifies `.env`. `workflow check` reports unknown workflow references only when they lack a fallback and are not GitHub-provided names; every finding is one located `file:line: severity: explanation` line. `variable import` reads repository variables with `gh variable list`, writes standard keys with adjacent `variable` directives, preserves commented template assignments, and force-overwrites only existing variable declarations.
- Every nested command provides operation-specific `--help` text explaining its effect and its relevant GitHub Actions type mapping.

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
