# gh-vault

![gh-vault](assets/logo-1024.png)

`gh-vault` keeps named GitHub tokens and secret project values in GPG-encrypted `pass` entries while allowing explicitly declared public variables in a restrictive XDG archive. It archives and restores per-project environments, syncs declared GitHub Actions values, runs local Actions with ephemeral files, and checks workflow wiring. Secret values never enter public metadata or ordinary command output.

## Requirements

- Linux, Python 3.10+, `pass`, and GPG
- `gh` authenticated with access to the target repository for Actions commands

```sh
sudo apt install pass gnupg
gpg --full-generate-key
pass init YOUR_GPG_KEY_ID
```

## Installation

Install `gh-vault` from PyPI:

```sh
uv tool install forgegod-gh-vault
```

This installs the released version into the active uv tool environment and provides the `gh-vault` console script on your `PATH`.

Releases are tag-driven via GitHub Actions trusted publishing. The full setup checklist, environment rules, and tag conventions live in [`docs/RELEASING.md`](docs/RELEASING.md). In short: bump `gh_vault.__version__`, commit, push a `v<version>` tag — nothing else publishes.

## Development installation

When working from a repository checkout — either to develop `gh-vault` itself or to test a local change — pick the mode that matches how you intend to use the checkout.

### Live edit mode (`--editable`)

```sh
uv tool install --editable .
```

Installs a `.pth` shim that points back at `src/` in this checkout. Edits to the source tree take effect the next time you invoke `gh-vault` — no reinstall needed. Use this when you are developing `gh-vault` itself.

### Snapshot mode (`--force --from .`)

```sh
uv tool install --force --from . gh-vault
```

Builds a regular install from this checkout and copies the package into `~/.local/share/uv/tools/gh-vault/`. The installed tool is frozen at the current source state; subsequent edits are invisible until you reinstall. Use this when you want the checkout's current state to behave like a release build, or when you do not want local edits to bleed into the running tool.

### When to choose which

| Goal | Mode |
|---|---|
| Developing or debugging `gh-vault` | Live edit (`--editable .`) |
| Trying the current checkout as a release-like build | Snapshot (`--force --from . gh-vault`) |
| Switching back to live edits after a snapshot install | `uv tool install --editable .` (overwrites the snapshot) |
| Returning to the released version after any checkout install | `uv tool install --force forgegod-gh-vault` |

The `--force` flag in snapshot mode only matters when `gh-vault` is already installed in that tool venv — it forces overwrite instead of skipping. Omit it on a clean install.

## Storage locations

| Artifact | Location | Mode |
|---|---|---|
| Token values | `pass` entries under `gh-vault/<profile>` | GPG-encrypted |
| Archived secret values and eligible templates | `pass` entries under `gh-vault/projects/<host>/<owner>/<repo>/` | GPG-encrypted |
| Archived public variable values | `${XDG_CONFIG_HOME:-~/.config}/gh-vault/environments/<host>/<owner>/<repo>/env[.<profile>].variables.json` | `0600`; parent directories `0700` |
| Value-free environment index | `${XDG_CONFIG_HOME:-~/.config}/gh-vault/environments/<host>/<owner>/<repo>/environments.json` | `0600`; parent directories `0700` |
| Profile metadata (scopes, notes, expiration) | `${XDG_CONFIG_HOME:-~/.config}/gh-vault/config.json` | `0600` |
| Generated `.env`, `.secrets`, `.vars` | Project checkout (gitignored) | `0600` |

The password store root follows `${PASSWORD_STORE_DIR:-~/.password-store}`. Metadata contains no secret values — only profile names, scopes, notes, and expiration timestamps.

## Token profiles

A profile is a named GitHub token stored in the encrypted vault. Profile names are 1–64 characters: letters, digits, `.`, `_`, or `-`; the first character is alphanumeric.

### Create or replace a profile

```sh
# Interactive prompt; creates or replaces the named profile
gh-vault set repo-read

# Explicit scope override (disables automatic scope detection)
gh-vault set repo-read --scopes contents:read,metadata:read

# Add an operator note shown in `gh-vault list`
gh-vault set production --note "org-wide deploy key"

# Read token from stdin for automation
printf '%s' "$TOKEN" | gh-vault set ci --stdin
```

`set` always creates or replaces the profile. When `--scopes` is omitted, `set` makes one authenticated request to `https://api.github.com/user`. A successful response validates the token and records:

- Classic PATs: scopes from the `X-OAuth-Scopes` header, expiration from `GitHub-Authentication-Token-Expiration` when present.
- Fine-grained tokens: scope list stays empty (GitHub does not expose classic scopes), expiration is still recorded when GitHub provides it.

When `--scopes` is supplied, the manual scopes are stored verbatim and scope detection is skipped. If the token cannot be validated against GitHub but `--scopes` was supplied, the profile is still created without validation. Without `--scopes`, a failed validation aborts the profile creation.

The first profile created becomes the active profile.

### List, select, and inspect profiles

```sh
gh-vault list                    # all profiles, scopes, expiration, notes; * marks active
gh-vault activate repo-read      # select the default profile
gh-vault status                  # show the active profile; exits 1 if none
```

To check whether a token is already stored without exposing every vault value:

```sh
printf '%s' "$TOKEN" | gh-vault find --stdin
```

`find` prints each matching profile name and exits `0` when at least one match exists. An unknown token produces no output and exits `1`. The token is accepted only through explicit `--stdin`; empty and multiline values are rejected.

### Remove a profile

```sh
gh-vault remove ci
```

Removing the active profile leaves no active profile. Selection never falls back implicitly to another profile.

### Run a command with a token

```sh
# Uses the active profile
gh-vault run -- gh repo view owner/repo

# Name a specific profile
gh-vault run --name production -- gh repo clone owner/repo
```

Sets both `GH_TOKEN` and `GITHUB_TOKEN` only in the exec'd child environment. The invoking shell is not mutated.

### Pipe a token to standard input

```sh
gh-vault output | docker login ghcr.io --username USERNAME --password-stdin
gh-vault output --name production | docker login ghcr.io --username USERNAME --password-stdin
```

`output` intentionally prints only the selected token plus a trailing newline. This is the credential-output boundary for tools that accept secrets on standard input; do not use it where stdout is logged. GitHub Container Registry requires a classic personal access token with the necessary package scopes (`read:packages` to pull and `write:packages` to push).

### Git credential helper

```sh
git config credential.https://github.com.helper '!gh-vault git-credential'
```

Responds only to HTTPS requests for `github.com`. The `get` operation outputs the standard credential-helper protocol response (`username=x-access-token` + the token as `password`). `store` and `erase` are no-ops. Outside this protocol, only the explicit `output` command writes a token to stdout.

To switch from `gh auth git-credential`:

```sh
git config --unset credential.https://github.com.helper
git config credential.https://github.com.helper '!gh-vault git-credential'
```

## Project environment archive

Archives split typed `.env` and `.env.<profile>` declarations by sensitivity under the normalized `remote.origin.url` namespace (`<host>/<owner>/<repo>`): `variable` values use restrictive JSON below `${XDG_CONFIG_HOME:-~/.config}/gh-vault/environments/`, while `secret` values remain encrypted in `pass`. Unmarked local values are never archived. Templates are encrypted only for profiles containing secrets.

### Archive

```sh
# Run in the project checkout
gh-vault env archive

# Archive named variants; repeat --env-file for multiple profiles
gh-vault env archive --env-file .env.development --env-file .env.production

# An explicit template path is supported for one selected environment
gh-vault env archive --env-file .env.production --example-file deploy/production.template
```

Named files use their profile name in both stores. `gh-vault env list` reads the value-free public index and lists every archived variant plus whether an encrypted template exists. `gh-vault env show [--env-file .env.<profile>]` prints only public variables and never reads `pass`; an empty profile prints `No archived variables`.

### Restore

```sh
gh-vault env restore                          # uses current .env.example, refuses overwrite
gh-vault env restore --force                  # overwrite existing .env
gh-vault env restore --restore-example        # restore the archived template too
gh-vault env restore --force --restore-example
gh-vault env restore --env-file .env.production
gh-vault env restore --key API_KEY            # append only API_KEY to the target .env
gh-vault env restore --key API_KEY --env-file .env.production
gh-vault env list
gh-vault env show
```

Restore checks that every payload origin matches the current checkout. `--env-file .env.<profile>` selects that named archive and uses `.env.example.<profile>` unless `--example-file` is supplied. It merges public variables and encrypted secrets onto the local template while preserving comments and directives; archived keys absent from the template are appended under `# Local additions`. Variable-only restores require the local template and never access `pass`. `--restore-example` works only when an encrypted template exists. Legacy monolithic archives are not read implicitly by normal commands.

`--key NAME` writes only the named archived key to the target `.env` with a synthetic `# gh-vault: secret` or `# gh-vault: variable` directive line. The type is read from the archive: the key is in the public variable store if it was archived as a variable, otherwise in the encrypted secret store. If the target `.env` already exists, the directive line is appended; otherwise the file is created with the directive + assignment only. `--key` does not require `--force` and refuses to combine with `--restore-example`. The key name must match `[A-Za-z_][A-Za-z0-9_]*`; an unknown key raises `StoreError` naming the target env file. The appended line is exactly two lines (`# gh-vault: <kind>\nKEY=VALUE\n`), so it composes cleanly with existing content as long as the file is already newline-terminated.

### Run with project environment

```sh
gh-vault env run -- ./scripts/report.sh
gh-vault env run -- python exporter.py --test --verbose
```

Injects only values marked by an adjacent `# gh-vault: secret` or `# gh-vault: variable` directive, under their ordinary dotenv key. Unmarked local values are deliberately excluded. The command uses the conservative dotenv parser (see below), never the shell.

## GitHub Actions values

An adjacent directive selects the GitHub Actions store while keeping a standard dotenv key:

```dotenv
# gh-vault: variable
REGION=eu-west-1

# gh-vault: secret
API_KEY=synthetic-value

LOCAL_ONLY=local
```

The directive applies only to the immediately following assignment. Unmarked values are local-only and ignored by Actions commands. Legacy `GH_SECRET_*` and `GH_VAR_*` declarations are rejected. Names matching `GITHUB_*`, `RUNNER_*`, `CI`, or `GH_TOKEN` are reserved and skipped.

The directive is gh-vault's opt-in declaration for archive storage, GitHub synchronization, and workflow validation. GitHub may contain manually managed Secrets or Variables, but gh-vault does not treat them as managed workflow values without the matching local directive.

### Migrate legacy declarations and archives

Migration is explicitly two-stage so classification is reviewed before any value enters clear-text storage:

```sh
gh-vault actions migrate-env --env-file .env
# Review every generated secret/variable directive.
gh-vault env migrate --env-file .env
```

`actions migrate-env` rewrites only `GH_SECRET_*` and `GH_VAR_*` assignments in the selected environment and matching template. It preserves comments and commented template assignments, leaves unprefixed values local-only, and refuses collisions or unsupported syntax before replacing either file. `env migrate` is the only command that reads the legacy encrypted archive. It partitions values by the reviewed directives, verifies the new public and encrypted payloads, excludes local-only values, and removes the legacy payload last. Run both commands separately for each `.env.<profile>`.

### Sync declared values to GitHub

`secret sync` and `variable sync` are independent and each set only their own GitHub Actions store. `--prune` and `--migrate-types` are mutually exclusive on each command.

```sh
# Secret side: preview, set, migrate, prune
gh-vault secret sync --dry-run
gh-vault secret sync
gh-vault secret sync --migrate-types
gh-vault secret sync --prune
gh-vault secret sync --repo owner/repo

# Variable side: matching options for the Variables store
gh-vault variable sync --dry-run
gh-vault variable sync
gh-vault variable sync --migrate-types
gh-vault variable sync --prune
gh-vault variable sync --repo owner/repo
```

`secret sync` creates or updates only GitHub Secrets and never touches GitHub Variables. `variable sync` creates or updates only GitHub Variables and never touches GitHub Secrets. On either side, ordinary sync never deletes. `--migrate-types` resolves a type change in one direction only: `secret sync --migrate-types` removes a same-name GitHub Variable before setting the Secret, and `variable sync --migrate-types` removes a same-name GitHub Secret before setting the Variable. `--prune` removes remote values in the target store whose names have no typed local declaration; same-name opposite-type local declarations protect their remote counterpart. `--dry-run` reports counts without touching GitHub.

### Check local declarations against GitHub

`secret check` and `variable check` are independent and scoped to their own GitHub Actions type. Each one is nonzero-exit until every finding in its scope is resolved and never modifies `.env`.

```sh
# Local secret declarations vs. GitHub Secrets only
gh-vault secret check
gh-vault secret check --repo owner/repo

# Local variable declarations vs. GitHub Variables only
gh-vault variable check
gh-vault variable check --repo owner/repo
```

`secret check` reports three categories, all nonzero-exit until resolved:

- Missing secrets (declared locally, absent on GitHub)
- Remote-only secrets (exist on GitHub but not in `.env`)
- Secret-to-variable drift (declared as Secret locally, exists as Variable remotely)

`variable check` reports three categories, all nonzero-exit until resolved:

- Missing variables (declared locally, absent on GitHub)
- Remote-only variables (exist on GitHub but not in `.env`)
- Variable-to-secret drift (declared as Variable locally, exists as Secret remotely)

Findings for the opposite type belong to the other command; they do not affect the current command's exit code.

Before pushing changes that affect Actions declarations, run the matching remote review sequence for each touched type. Local commits use `gh-vault workflow check` as the offline wiring gate; remote secret/variable checks are not a local-commit prerequisite.

```sh
# Secret-side changes
gh-vault secret sync --dry-run
gh-vault secret check

# Variable-side changes (run alongside the secret pair when both types moved)
gh-vault variable sync --dry-run
gh-vault variable check
```

### Type transitions

Changing a directive changes both archive storage and GitHub synchronization eligibility. An unclassified local-only value is not archived by gh-vault. GitHub uses separate Secret and Variable stores, so cross-type remote changes are deliberately explicit.

| Source | Target | Exact directive edit | Resulting archive | Archive command | GitHub behavior and follow-up |
|---|---|---|---|---|---|
| `secret` | `secret` | Keep `# gh-vault: secret`; edit value only | Encrypted `pass` payload | `gh-vault env archive` | Ordinary `gh-vault secret sync` updates it |
| `variable` | `variable` | Keep `# gh-vault: variable`; edit value only | Public XDG payload | `gh-vault env archive` | Ordinary `gh-vault variable sync` updates it |
| local-only | local-only | Keep no directive; edit value only | No gh-vault archive | `gh-vault env archive` removes any stale archive | Remote values are untouched |
| `secret` | `variable` | Replace `secret` with `variable` | Public XDG payload; stale encrypted payload removed after verification | `gh-vault env archive` | Run `variable sync --dry-run`, then `variable sync --migrate-types` |
| `variable` | `secret` | Replace `variable` with `secret` | Encrypted `pass` payload; stale public payload removed after verification | `gh-vault env archive` | Run `secret sync --dry-run`, then `secret sync --migrate-types` |
| local-only | `secret` | Add `# gh-vault: secret` immediately above the assignment | Encrypted `pass` payload | `gh-vault env archive` | Review with `secret sync --dry-run`, then ordinary `secret sync` |
| local-only | `variable` | Add `# gh-vault: variable` immediately above the assignment | Public XDG payload | `gh-vault env archive` | Review with `variable sync --dry-run`, then ordinary `variable sync` |
| `secret` | local-only | Remove the adjacent `secret` directive | No gh-vault archive for that value | `gh-vault env archive` | Remote Secret remains. Before `secret sync --prune`, run the full pre-push review sequence above |
| `variable` | local-only | Remove the adjacent `variable` directive | No gh-vault archive for that value | `gh-vault env archive` | Remote Variable remains. Before `variable sync --prune`, run the full pre-push review sequence above |

### Import repository Variables into `.env`

```sh
gh-vault variable import
gh-vault variable import --repo owner/repo
gh-vault variable import --force    # overwrite existing variable declarations
```

Reads repository variables via `gh variable list` and writes standard keys with `# gh-vault: variable` directives. Targets `.env` when it exists, otherwise writes commented assignments in `.env.example`. Existing entries are retained unless `--force` is supplied; force overwrites only an existing `variable` declaration and refuses to reclassify a secret or local-only key.

### Run local Actions with ephemeral values

```sh
gh-vault run-act -- act workflow_dispatch
# or, equivalently, when only the gh CLI is on PATH:
gh-vault run-act -- gh act workflow_dispatch
```

`run-act` creates separate secret and variable files in a mode-`0700` temporary directory, appends `--secret-file` and `--var-file` to the supplied `act` command, and removes the files after success or child failure. Both files always exist at mode `0600`, even when empty. Unmarked local values are excluded. Supplying either managed file flag manually is rejected. `SIGKILL` or a host crash can prevent normal cleanup.

`gh-vault secret export-act` remains available when explicit persistent `.secrets` and `.vars` files are required. Multi-line values use the `@base64:` prefix understood by [act](https://github.com/nektos/act).

### Validate workflow wiring

```sh
gh-vault workflow check
gh-vault workflow check --json      # machine-readable output
gh-vault workflow check --fix       # print suggested env block for unreferenced values
```

Scans `.github/workflows/*.yml` and `*.yaml` for `secrets.NAME` and `vars.NAME` references, then cross-checks against local declarations. Reports four finding types, each as `file:line: severity: explanation`:

| Severity | Finding | Description |
|---|---|---|
| `error` | Unreferenced local value | A typed declaration in `.env` is never referenced by any workflow |
| `error` | Type mismatch | Workflow uses `vars.NAME` but `.env` marks `NAME` as `secret`, or vice versa |
| `error` | Fallback order | Expression puts `vars.X` before `secrets.X` in a `\|\|` chain |
| `warning` | Orphan reference | Workflow references a name not declared locally and with no fallback default |

Excludes GitHub-provided names like `GITHUB_TOKEN`. Exits nonzero if any errors exist (warnings alone do not fail). `--fix` prints a suggested `env:` block for unreferenced local values. Does not impose repository-specific namespace mappings.

## Dotenv syntax reference

`gh-vault` uses a conservative dotenv parser — never `eval`, never shell expansion. Accepted syntax:

| Syntax | Behavior |
|---|---|
| `KEY=value` | Bare assignment |
| `export KEY=value` | Leading `export` is stripped |
| `KEY="value"` | Double-quoted; JSON-style escapes decoded (`\n`, `\t`, `\"`, `\\`) |
| `KEY='value'` | Single-quoted; content taken verbatim, no escapes |
| `KEY=@file:path` | Reads the file content (relative to `.env` directory) |
| `KEY=@base64:data` | Base64-decodes the data |
| `# gh-vault: secret` | Marks the immediately following assignment as a GitHub Secret |
| `# gh-vault: variable` | Marks the immediately following assignment as a GitHub Variable |
| `# comment` | Comment line, ignored |
| `value # trailing` | Inline comment stripped (space before `#` required) |

Rejected syntax: `$(command)`, `${variable}`, backticks, and any construct requiring shell evaluation. This is deliberate — `.env` files are data, not executable scripts.

Templates retain classification without activating assignments:

```dotenv
# gh-vault: variable
# REGION=

# gh-vault: secret
# API_KEY=
```

The directive must remain immediately adjacent to the commented assignment. This keeps conventional `.env.example` placeholders while preserving type metadata for migration and restore.

Values with embedded newlines are stored as `@base64:` when written to `.env` or exported for `act`.

## Security model

- Tokens, secret environment values, and eligible archive templates live only in `pass` under `gh-vault/`.
- Only values explicitly marked `# gh-vault: variable` may enter the public XDG archive. Operators must classify them as safe for clear-text local storage before archiving or migration.
- Public variable payloads and value-free indexes are mode `0600` below `${XDG_CONFIG_HOME:-~/.config}/gh-vault/environments/`, with mode-`0700` directories. Secret and local-only values never enter those files or `config.json`.
- `.env`, `.secrets`, and `.vars` are ignored by Git. Generated files are mode `0600`.
- The only token stdout is the exact credential-helper response Git requires.
- Token validation against `https://api.github.com/user` sends the token to GitHub over HTTPS; no third party is involved.
- Config writes are atomic (temp file + `fsync` + `os.replace`) and always set mode `0700` directory / `0600` file.

## License

MIT — see [LICENSE](LICENSE).
