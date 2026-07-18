# gh-vault

![gh-vault](assets/logo-1024.png)

`gh-vault` keeps named GitHub tokens and project `.env` values in GPG-encrypted `pass` entries. It validates and records token scope and expiration metadata, archives and restores per-project environments, syncs declared GitHub Actions values, exports files for local `act` runs, and checks workflow wiring. It never keeps secret values in the checkout or ordinary command output.

## Requirements

- Linux, Python 3.10+, `pass`, and GPG
- `gh` authenticated with access to the target repository for Actions commands

```sh
sudo apt install pass gnupg
gpg --full-generate-key
pass init YOUR_GPG_KEY_ID
uv tool install --editable .
```

## Storage locations

| Artifact | Location | Mode |
|---|---|---|
| Token values | `pass` entries under `gh-vault/<profile>` | GPG-encrypted |
| Archived environments | `pass` entries under `gh-vault/projects/<host>/<owner>/<repo>/` | GPG-encrypted |
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

### Git credential helper

```sh
git config credential.https://github.com.helper '!gh-vault git-credential'
```

Responds only to HTTPS requests for `github.com`. The `get` operation outputs the standard credential-helper protocol response (`username=x-access-token` + the token as `password`). `store` and `erase` are no-ops. No other token stdout exists.

To switch from `gh auth git-credential`:

```sh
git config --unset credential.https://github.com.helper
git config credential.https://github.com.helper '!gh-vault git-credential'
```

## Project environment archive

Archives store the complete `.env` content and the `.env.example` template as separate encrypted entries in `pass`, identified by the normalized `remote.origin.url` namespace (`<host>/<owner>/<repo>`).

### Archive

```sh
# Run in the project checkout
gh-vault env archive

# Custom file paths
gh-vault env archive --env-file .env.production --example-file .env.example.production
```

Writes two `pass` entries under `gh-vault/projects/<host>/<owner>/<repo>/`: `env.json` (values + origin URL + version) and `env.example` (the template text).

### Restore

```sh
gh-vault env restore                          # uses current .env.example, refuses overwrite
gh-vault env restore --force                  # overwrite existing .env
gh-vault env restore --restore-example        # restore the archived template too
gh-vault env restore --force --restore-example
```

Restore checks that the archived origin matches the current checkout's `remote.origin.url`. It reconstructs `.env` by applying archived values onto the template: template lines with matching keys get the archived value; template lines without a key (comments, blank lines) are preserved; archived keys absent from the template are appended under a `# Local additions` section.

### Run with project environment

```sh
gh-vault env run -- ./scripts/report.sh
gh-vault env run -- python exporter.py --test --verbose
```

Injects all parsed `.env` values into the child environment. `GH_VAR_<KEY>` and `GH_SECRET_<KEY>` are mapped to unprefixed `<KEY>`; when both prefixes declare the same key, the Secret wins. The command uses the conservative dotenv parser (see below), never the shell.

## GitHub Actions values

Only entries prefixed `GH_SECRET_NAME=value` or `GH_VAR_NAME=value` in `.env` are treated as Actions values. The prefix is stripped before any GitHub operation. Names matching `GITHUB_*`, `RUNNER_*`, `CI`, or `GH_TOKEN` are reserved and skipped.

### Sync declared values to GitHub

```sh
# Preview without changes
gh-vault secrets sync --dry-run

# Set all declared GH_SECRET_ as Secrets and GH_VAR_ as Variables
gh-vault secrets sync

# Resolve type mismatches: remove opposite-type remote value, then set declared type
gh-vault secrets sync --migrate-types

# Remove remote values absent from .env (leaves same-name opposite types alone)
gh-vault secrets sync --prune

# Target a specific repository (defaults to origin)
gh-vault secrets sync --repo owner/repo
```

Ordinary sync creates or updates remote Secrets and Variables but never deletes. `--migrate-types` handles type changes: if `GH_SECRET_API_KEY` is declared but a GitHub Variable `API_KEY` exists, it removes the Variable first, then sets the Secret. `--prune` removes remote Secrets and Variables whose names have no local declaration; it deliberately leaves same-name opposite types alone and cannot be combined with `--migrate-types`. `--dry-run` reports the count of what would be synced or pruned without touching GitHub.

### Check local declarations against GitHub

```sh
gh-vault secrets check
gh-vault secrets check --repo owner/repo
```

Compares every `GH_SECRET_*` and `GH_VAR_*` declaration against both GitHub Actions stores. The local prefix is authoritative — a GitHub Variable for a `GH_SECRET_NAME` entry is reported as `GH_VAR_NAME -> GH_SECRET_NAME` and vice versa. Reports four categories, all nonzero-exit until resolved:

- Missing secrets or variables (declared locally, absent on GitHub)
- Remote-only values (exist on GitHub but not in `.env`)
- Secret-to-variable drift (declared as Secret locally, exists as Variable remotely)
- Variable-to-secret drift (declared as Variable locally, exists as Secret remotely)

Never modifies `.env`.

### Import repository Variables into `.env`

```sh
gh-vault variables import
gh-vault variables import --repo owner/repo
gh-vault variables import --force    # overwrite existing GH_VAR_ entries
```

Reads repository variables via `gh variable list` and writes them as `GH_VAR_*` entries. Targets `.env` when it exists, otherwise `.env.example`. Existing entries are retained unless `--force` is supplied.

### Export values for local `act` runs

```sh
gh-vault secrets export-act
act workflow_dispatch --secret-file .secrets --var-file .vars
```

`export-act` splits `.env` entries into two files: `.secrets` (from `GH_SECRET_*`) and `.vars` (from `GH_VAR_*`). Both are mode `0600` and gitignored. Multi-line values are base64-encoded with the `@base64:` prefix that `act` consumes natively.

The two-flag invocation is required because [act](https://github.com/nektos/act) populates `secrets.*` from `--secret-file` only — it does not map `vars.*` from a secret file. Without `--var-file .vars`, workflow references to `vars.X` resolve to empty and the run fails. If a workflow cannot use separate variable files, add `vars.X || secrets.X` fallbacks in the workflow YAML.

### Validate workflow wiring

```sh
gh-vault workflow check
gh-vault workflow check --json      # machine-readable output
gh-vault workflow check --fix       # print suggested env block for unreferenced values
```

Scans `.github/workflows/*.yml` and `*.yaml` for `secrets.NAME` and `vars.NAME` references, then cross-checks against local declarations. Reports four finding types, each as `file:line: severity: explanation`:

| Severity | Finding | Description |
|---|---|---|
| `error` | Unreferenced local value | `GH_SECRET_*` or `GH_VAR_*` declared in `.env` but never referenced by any workflow |
| `error` | Type mismatch | Workflow uses `vars.NAME` but `.env` declares `GH_SECRET_NAME`, or vice versa |
| `error` | Fallback order | Expression puts `vars.X` before `secrets.X` in a `||` chain |
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
| `# comment` | Comment line, ignored |
| `value # trailing` | Inline comment stripped (space before `#` required) |

Rejected syntax: `$(command)`, `${variable}`, backticks, and any construct requiring shell evaluation. This is deliberate — `.env` files are data, not executable scripts.

Values with embedded newlines are stored as `@base64:` when written to `.env` or exported for `act`.

## Security model

- Tokens, archived values, and archive templates live only in `pass` under `gh-vault/`.
- Metadata is mode `0600` under `${XDG_CONFIG_HOME:-~/.config}/gh-vault/`; it contains no secret values.
- `.env`, `.secrets`, and `.vars` are ignored by Git. Generated files are mode `0600`.
- The only token stdout is the exact credential-helper response Git requires.
- Token validation against `https://api.github.com/user` sends the token to GitHub over HTTPS; no third party is involved.
- Config writes are atomic (temp file + `fsync` + `os.replace`) and always set mode `0700` directory / `0600` file.

## License

MIT — see [LICENSE](LICENSE).

## Releasing to PyPI

`gh-vault` uses a single source of truth for its version: `src/gh_vault/__init__.py` → `__version__`. The release workflow is: bump that string, tag, build, upload.

Prerequisites: a PyPI account and an API token scoped to the `gh-vault` project. Configure the token once:

```sh
# Re-authenticate at any time; this overwrites the stored token.
uv publish --token PYPI_API_TOKEN    # placeholder; set the env var instead
```

Prefer the `UV_PUBLISH_TOKEN` environment variable and avoid storing the token on disk. `gh-vault secrets sync` can keep the value in `pass` for this repo if you maintain it locally.

### Publish a release

```sh
# 1. Update __version__ in src/gh_vault/__init__.py
$EDITOR src/gh_vault/__init__.py

# 2. Update the changelog and commit the version bump.
git add src/gh_vault/__init__.py
git commit -m "chore(release): vX.Y.Z"
git tag vX.Y.Z

# 3. Clean previous builds, then build sdist + wheel from the source checkout.
rm -rf dist/ build/ src/gh_vault.egg-info/
uv build

# 4. Verify the artifact (metadata, license file, README) before upload.
uv publish --dry-run

# 5. Upload to PyPI.
uv publish

# 6. Push the tag so the release on GitHub matches PyPI.
git push origin vX.Y.Z
```

`uv build` reads the version dynamically from `gh_vault.__version__`, so both the sdist and the wheel inherit the single `__version__` string — no separate `VERSION` file or duplicated `version =` field. The `LICENSE` file ships inside the sdist and the wheel; PyPI's license expression resolves to MIT through `license = "MIT"` and `license-files = ["LICENSE"]` in `pyproject.toml`.

### Version policy

Follow [Semantic Versioning](https://semver.org/). Before `1.0.0`, minor bumps may include breaking changes; the project documents these in release notes.
