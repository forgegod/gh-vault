<p align="center">
  <img src="https://raw.githubusercontent.com/forgegod/gh-vault/main/assets/logo-1024.png" alt="gh-vault" width="720">
</p>

<p align="center">
  <a href="https://github.com/forgegod/gh-vault"><img src="https://img.shields.io/badge/GitHub-forgegod%2Fgh--vault-181717?logo=github" alt="GitHub"></a>
  <a href="https://pypi.org/project/forgegod-gh-vault/"><img src="https://img.shields.io/pypi/v/forgegod-gh-vault?logo=pypi&label=PyPI" alt="PyPI"></a>
</p>

`gh-vault` keeps named GitHub tokens and secret project values in GPG-encrypted `pass` entries while allowing explicitly declared public variables in a restrictive XDG archive. It archives and restores per-project environments, syncs declared GitHub Actions values, runs local Actions with ephemeral files, checks workflow wiring, and resolves explicitly configured Bitwarden projects and dotenv values through an operator-held local adapter. Secret values never enter public metadata or ordinary command output.

## Requirements

- Linux, Python 3.10+, `pass`, and GPG
- `gh` authenticated with access to the target repository for Actions commands
- For Bitwarden project resolution or dotenv recovery: an existing named bws profile, externally provisioned machine account, and compatible `gh_vault_bws` package in a local checkout

```sh
sudo apt install pass gnupg
gpg --full-generate-key
pass init YOUR_GPG_KEY_ID
```

### GPG unlock duration

`gh-vault` delegates encryption and decryption to `pass` and GPG. The GPG
agent, not `gh-vault`, decides when the private key's passphrase must be
entered. Configure the user-level agent cache in `~/.gnupg/gpg-agent.conf`:

```conf
# Seconds; 12 hours.
default-cache-ttl 43200
max-cache-ttl 43200
```

Then reload the agent configuration:

```sh
gpgconf --reload gpg-agent
```

Set both values: `default-cache-ttl` controls the idle timeout, while
`max-cache-ttl` is the absolute limit. With both at `43200`, unlock once and
GPG will ask again after at most 12 hours, even if the vault is used during
that period. Choose any positive number of seconds to configure a different
duration. This policy applies to every GPG private-key operation by the user,
not only `gh-vault`. To clear cached access early, run
`gpgconf --kill gpg-agent` or end the user session.

## Installation

Install `gh-vault` from PyPI:

```sh
uv tool install forgegod-gh-vault
```

This installs the `forgegod-gh-vault` distribution and provides `gh-vault` on your `PATH`. `python -m gh_vault` is the equivalent module entry point.

Releases are tag-driven via GitHub Actions trusted publishing. The full setup checklist, environment rules, and tag conventions live in [`docs/RELEASING.md`](docs/RELEASING.md). In short: bump `gh_vault.__version__`, commit, push a `v<version>` tag — nothing else publishes.

## Development installation

When working from a repository checkout — either to develop `gh-vault` itself or to test a local change — pick the mode that matches how you intend to use the checkout.

### Live edit mode (`--editable`)

```sh
uv tool install --editable .
```

Installs a `.pth` shim that points back at `src/` in this checkout. Edits to the source tree take effect the next time you invoke `gh-vault` — no reinstall needed. Use this when you are developing `gh-vault` itself.

### Snapshot mode (`--force .`)

```sh
uv tool install --force .
```

Builds a regular install from this checkout and copies the package into `~/.local/share/uv/tools/forgegod-gh-vault/`. The installed tool is frozen at the current source state; subsequent edits are invisible until you reinstall. Use this when you want the checkout's current state to behave like a release build, or when you do not want local edits to bleed into the running tool.

### When to choose which

| Goal | Mode |
|---|---|
| Developing or debugging `gh-vault` | Live edit (`--editable .`) |
| Trying the current checkout as a release-like build | Snapshot (`--force .`) |
| Switching back to live edits after a snapshot install | `uv tool install --editable .` (overwrites the snapshot) |
| Returning to the released version after any checkout install | `uv tool install --force forgegod-gh-vault` |

The `--force` flag in snapshot mode only matters when the `forgegod-gh-vault` distribution is already installed in that tool venv — it forces overwrite instead of skipping. Omit it on a clean install.

## Storage locations

| Artifact | Location | Mode |
|---|---|---|
| Token values | `pass` entries under `gh-vault/<profile>` | GPG-encrypted |
| Bitwarden access tokens | `pass` entries under `gh-vault/bitwarden/<connection>` | GPG-encrypted; optional alternative to `BWS_ACCESS_TOKEN` |
| Bitwarden connection metadata | `${XDG_CONFIG_HOME:-~/.config}/gh-vault/config.json` | Value-free config/profile, HTTPS endpoints, and organization UUID |
| Archived secret values and eligible templates | `pass` entries under `gh-vault/projects/<host>/<owner>/<repo>/` | GPG-encrypted |
| Archived public variable values | `${XDG_CONFIG_HOME:-~/.config}/gh-vault/environments/<host>/<owner>/<repo>/env[.<profile>].variables.json` | `0600`; parent directories `0700` |
| Value-free environment index | `${XDG_CONFIG_HOME:-~/.config}/gh-vault/environments/<host>/<owner>/<repo>/environments.json` | `0600`; parent directories `0700` |
| Profile metadata (scopes, notes, expiration) | `${XDG_CONFIG_HOME:-~/.config}/gh-vault/config.json` | `0600` |
| Generated `.env`, `.secrets`, `.vars` | Project checkout (gitignored) | `0600` |

The password store root follows `${PASSWORD_STORE_DIR:-~/.password-store}`. Metadata contains no secret values — only profile names, scopes, notes, and expiration timestamps.

## Token profiles

A profile is a named GitHub token stored in the encrypted vault. Profile names match the pattern `[A-Za-z0-9][A-Za-z0-9._-]{0,63}` — 1 to 64 characters, the first character must be a letter or digit, and the remaining characters may be letters, digits, `.`, `_`, or `-`. Leading `-`, `_`, or `.` is rejected. The validator's error message names both rules.

### Create or replace a profile

```sh
# Interactive prompt; creates or replaces the named profile
gh-vault set repo-read

# Explicit scope override (GitHub inspection is still attempted)
gh-vault set repo-read --scopes contents:read,metadata:read

# Add an operator note shown in `gh-vault list`
gh-vault set production --note "org-wide deploy key"

# Read token from stdin for automation
printf '%s' "$TOKEN" | gh-vault set ci --stdin

# Pipe the live GitHub CLI token into a profile. Choose any valid name, e.g.
# the GitHub login or a topic-scoped alias. Profile names cannot start with
# `_`, `-`, or `.`.
gh auth token | gh-vault set ghcli-forgegod --stdin
```

`set` always creates or replaces the profile. When `--scopes` is omitted, `set` makes one authenticated request to `https://api.github.com/user`. A successful response validates the token and records:

- Classic PATs: scopes from the `X-OAuth-Scopes` header, expiration from `GitHub-Authentication-Token-Expiration` when present.

Before contacting GitHub, `--stdin` rejects inputs that are empty, multiline, shorter than 36 or longer than 255 characters, contain characters outside `[A-Za-z0-9_]`, or match the masked-output sentinel that `gh auth status` prints without `-t` (a recognised `gh[pousr]_*` or `github_pat_*` prefix followed by run of `*`). The error message names the failing gate so a misconfigured pipeline fails fast instead of being stored as a worthless token.
- Fine-grained tokens: scope list stays empty (GitHub does not expose classic scopes), expiration is still recorded when GitHub provides it.

When `--scopes` is supplied, GitHub inspection is still attempted; manual scopes are trimmed, deduplicated, and override the discovered scopes. Successful inspection still supplies expiration metadata. If inspection fails, explicit scopes allow profile creation without validation; without `--scopes`, that failure aborts creation.

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

## Bitwarden connection and project resolution

Bitwarden support is explicit and separate from GitHub token profiles. Machine
accounts, projects, permissions, access tokens, and the private adapter checkout
are provisioned outside gh-vault. The published package does not include the
Bitwarden SDK, fetch an adapter, probe regions, list projects by name, or create
projects.

Create a named connection from an existing bws profile. The default bws config is
`~/.config/bws/config`; use `--bws-config` to select another file. The profile
must resolve both API and identity endpoints over HTTPS.

```sh
gh-vault bitwarden connection set eu-production \
  --bws-profile eu \
  --organization-id 11111111-1111-4111-8111-111111111111

gh-vault bitwarden connection list
```

Connection metadata is restrictive but not encrypted and contains no access
token. Re-running `connection set` explicitly rebinds the name. A later project
request rereads the bws profile and refuses endpoint drift rather than trying the
credential against another region.

Choose exactly one credential source. Environment mode is the default and reads
only an already exported `BWS_ACCESS_TOKEN`. Vault mode stores the token separately
through `pass`; stdin or a hidden TTY prompt is required, never an argv value.

```sh
printf '%s' "$BWS_ACCESS_TOKEN" | \
  gh-vault bitwarden credential set eu-production --stdin

gh-vault bitwarden credential remove eu-production
```

Resolve one pre-known project UUID through an operator-held local checkout. The
path must contain `gh_vault_bws/__init__.py` implementing adapter API version 1.
The interface receives explicit endpoint, credential, organization, project, and
temporary-state inputs. Project resolution returns the selected project and
organization IDs; environment reads additionally return exact-name entries with
their IDs and project membership. SDK implementation details stay in the private
adapter repository.

For API version 1, `resolve_project(**request)` is required. Dotenv recovery also
requires `read_environment(**request)`. The latter receives `api_url`,
`identity_url`, `access_token`, `organization_id`, `project_id`, the ordered
`keys` tuple, and `state_file`. It returns exactly `project_id`,
`organization_id`, and `entries`; each entry contains exactly `id`, `key`,
`value`, `organization_id`, and `project_ids`. This is the public normalized
interface only; SDK call sequences remain private.

```sh
# Read only BWS_ACCESS_TOKEN; this is the default credential source.
gh-vault bitwarden project resolve \
  --connection eu-production \
  --project-id 22222222-2222-4222-8222-222222222222 \
  --adapter-path ../gh-vault-bws

# Use the independently encrypted credential; never fall back to the environment.
gh-vault bitwarden project resolve \
  --connection eu-production \
  --project-id 22222222-2222-4222-8222-222222222222 \
  --adapter-path ../gh-vault-bws \
  --credential-source vault
```

Run project resolution inside a checkout with a valid `remote.origin.url`.
`BWS_CONFIG_FILE`, `BWS_PROFILE`, and `BWS_SERVER_URL` are rejected for this
operation because the named connection is authoritative. A valid renamed origin
is revalidated for the current invocation; no hidden repository/project binding
cache exists. Success prints the selected UUID and connection name. Adapter
stdout, stderr, raw errors, access tokens, and project listings are not relayed.

### Restore a fresh dotenv from Bitwarden

`bitwarden env restore` reads every typed declaration in the selected template
from one explicit project. All `secret` and `variable` keys are required; example
values are documentation, not defaults. Untyped local assignments are not
requested and remain commented in the generated file. Profile-referenced
secrets are rejected before credential or adapter access.

```sh
gh-vault bitwarden env restore \
  --connection eu-production \
  --project-id 22222222-2222-4222-8222-222222222222 \
  --adapter-path ../gh-vault-bws

gh-vault bitwarden env restore \
  --connection eu-production \
  --project-id 22222222-2222-4222-8222-222222222222 \
  --adapter-path ../gh-vault-bws \
  --credential-source vault \
  --env-file .env.production \
  --force
```

The default target/template pair is `.env` and `.env.example`; a named target
uses `.env.example.<profile>` unless `--example-file` is explicit. The command
validates the complete response before writing, preserves empty, Unicode, and
multiline values, rejects NUL, and quotes literal values beginning `@file:` or
`@base64:` so they are not reinterpreted. It refuses overwrite without
`--force` and atomically installs a mode-`0600` file. There is no local-archive
fallback or cached UUID mapping.

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

`--key NAME` writes only the named archived key to the target `.env` with a synthetic `# gh-vault: secret` or `# gh-vault: variable` directive line. The type is read from the archive: the key is in the public variable store if it was archived as a variable, otherwise in the encrypted secret store. If the target `.env` already exists, the directive line is appended; otherwise the file is created with the directive + assignment only. `--key` does not require `--force` and refuses to combine with `--restore-example`. The key name must match `[A-Za-z_][A-Za-z0-9_]*`; an unknown key raises `StoreError` naming the target env file. The appended entry is two lines (`# gh-vault: <kind>\nKEY=VALUE\n`); a missing trailing newline in existing content is added first. An existing same-name key is not replaced or deduplicated.

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

# gh-vault: secret hermes-agent
GITHUB_TOKEN=

LOCAL_ONLY=local
```

The directive applies only to the immediately following assignment. Unmarked values are local-only and ignored by Actions commands. Legacy `GH_SECRET_*` and `GH_VAR_*` declarations are rejected. Names matching `GITHUB_*`, `RUNNER_*`, `CI`, or `GH_TOKEN` are reserved and skipped — except for profile-referenced secrets, which intentionally override the reserved guard so `GITHUB_TOKEN` can be resolved from a stored profile.

The `# gh-vault: secret <profile>` shape references a token stored in `pass` under `gh-vault/<profile>`. The value on the next line is irrelevant — leave it empty. Supported resolution paths are:

- `gh-vault env run` injects the resolved token into the child process environment under the assignment key.
- `gh-vault secret sync` and `secret export-act` resolve the token and push/write it; `secret sync --migrate-types` and `--prune` apply the same way as for literal secrets.
- `gh-vault workflow check` resolves profile-referenced entries as declared local secrets before scanning references.

`run-act` does not pass a vault store to value selection and rejects profile references. Use literal typed values for ephemeral runs; persistent `secret export-act` supports references but leaves plaintext files behind.

`gh-vault env archive` and `gh-vault env migrate` refuse profile-referenced declarations — their values are not real secrets, so archiving a placeholder literal would be wrong. Profile references are valid for `secret` only; `# gh-vault: variable <profile>` is rejected because vault profiles hold GitHub tokens, not variables.

The directive is gh-vault's opt-in declaration for archive storage, GitHub synchronization, and workflow validation. GitHub may contain manually managed Secrets or Variables, but gh-vault does not treat them as managed workflow values without the matching local directive.

### Select repository or GitHub Environment scope

Remote Actions commands target the repository by default. Add `--github-environment NAME` to target one existing GitHub Environment instead. The dotenv filename remains a local source/archive profile: `.env.production` does not implicitly select a remote `production` environment.

```sh
# Repository scope
gh-vault secret sync --env-file .env

# Existing GitHub Environment scope
gh-vault secret sync --env-file .env.production --github-environment production
gh-vault variable sync --env-file .env.production --github-environment production
gh-vault secret check --env-file .env.production --github-environment production
gh-vault variable check --env-file .env.production --github-environment production
```

Before an environment-scoped sync, check, or import, gh-vault reads that environment through the GitHub API and refuses an unknown target. It does not create an Environment or configure reviewers, wait timers, deployment policies, or protection rules. `--prune` and `--migrate-types` read, delete, and compare values only in the selected repository or environment scope; same-name values in another scope are independent.

### Rotate a linked personal access token

Use a profile reference when a GitHub Actions Secret must receive the token stored in a named gh-vault profile:

```dotenv
# gh-vault: secret ci-pat
GITHUB_TOKEN=
```

Create the replacement PAT in GitHub's token settings with the same required access. `gh auth refresh` only reauthorizes the GitHub CLI's OAuth credentials and scopes; neither it nor gh-vault can create or rotate a PAT. Keep the current PAT valid until the replacement is verified.

```sh
# Replace the profile's encrypted pass entry; the PAT never appears in argv.
printf '%s' "$NEW_PAT" | gh-vault set ci-pat --stdin

# Resolve the profile reference and update the GitHub Actions Secret.
gh-vault secret sync --dry-run
gh-vault secret sync

# Confirm the declaration exists as a GitHub Secret with the expected type.
gh-vault secret check
```

Then run the workflow or authenticated operation that consumes `GITHUB_TOKEN`. `secret check` cannot confirm a Secret's value because GitHub never returns stored Secret values. Revoke the previous PAT in GitHub only after that operation succeeds. This process replaces the vault profile and GitHub Actions Secret; it does not archive the profile reference or modify the `.env` placeholder.

### Migrate legacy declarations and archives

Migration is explicitly two-stage so classification is reviewed before any value enters clear-text storage:

```sh
gh-vault actions migrate-env --env-file .env
# Review every generated secret/variable directive.
gh-vault env migrate --env-file .env
```

`actions migrate-env` rewrites only `GH_SECRET_*` and `GH_VAR_*` assignments in the selected environment and matching template. It preserves comments and commented template assignments, leaves unprefixed values local-only, and refuses collisions or unsupported syntax before replacing either file. `env migrate` is the only command that reads the legacy encrypted archive. It partitions values by the reviewed directives, verifies the new public and encrypted payloads, excludes local-only values, and removes the legacy payload last. Run both commands separately for each `.env.<profile>`.

### Sync declared values to GitHub

`secret sync` and `variable sync` are independent and each set only their own GitHub Actions store in the selected repository or GitHub Environment scope. `--prune` and `--migrate-types` are mutually exclusive on each command.

```sh
# Secret side: preview, set, migrate, prune
gh-vault secret sync --dry-run
gh-vault secret sync
gh-vault secret sync --migrate-types
gh-vault secret sync --prune
gh-vault secret sync --repo owner/repo
gh-vault secret sync --env-file .env.production --github-environment production

# Variable side: matching options for the Variables store
gh-vault variable sync --dry-run
gh-vault variable sync
gh-vault variable sync --migrate-types
gh-vault variable sync --prune
gh-vault variable sync --repo owner/repo
gh-vault variable sync --env-file .env.production --github-environment production
```

`secret sync` creates or updates only GitHub Secrets and never touches GitHub Variables. `variable sync` creates or updates only GitHub Variables and never touches GitHub Secrets. On either side, ordinary sync never deletes. `--migrate-types` resolves a type change in one direction only: `secret sync --migrate-types` removes a same-name GitHub Variable before setting the Secret, and `variable sync --migrate-types` removes a same-name GitHub Secret before setting the Variable. `--prune` removes remote values in the selected repository or environment store whose names are absent from the selected sync entries; only selected, nonempty values of the synced type protect a remote name. Opposite-type declarations, empty literals, and skipped reserved names do not protect names from pruning. `--dry-run` reports counts without remote mutation. With `--prune` or `--migrate-types`, it still lists remote names; profile-reference selection can still decrypt local tokens. Preview destructive operations using the same flags you intend to apply.

### Check local declarations against GitHub

`secret check` and `variable check` are independent and scoped to their own GitHub Actions type plus the selected repository or GitHub Environment. Each one is nonzero-exit until every finding in its scope is resolved and never modifies `.env`.

```sh
# Local secret declarations vs. GitHub Secrets only
gh-vault secret check
gh-vault secret check --repo owner/repo
gh-vault secret check --env-file .env.production --github-environment production

# Local variable declarations vs. GitHub Variables only
gh-vault variable check
gh-vault variable check --repo owner/repo
gh-vault variable check --env-file .env.production --github-environment production
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

### Import GitHub Variables into `.env`

```sh
gh-vault variable import
gh-vault variable import --repo owner/repo
gh-vault variable import --env-file .env.production --github-environment production
gh-vault variable import --force    # overwrite existing variable declarations
```

Reads repository or environment-scoped variables via `gh variable list` and writes standard keys with `# gh-vault: variable` directives. Targets the selected `.env` file when it exists, otherwise writes commented assignments in its matching `.env.example` variant. Existing entries are retained unless `--force` is supplied; force overwrites only an existing `variable` declaration and refuses to reclassify a secret or local-only key.

### Run local Actions with ephemeral values

```sh
gh-vault run-act -- act workflow_dispatch
# or, equivalently, when only the gh CLI is on PATH:
gh-vault run-act -- gh act workflow_dispatch
```

`run-act` creates separate secret and variable files in a mode-`0700` temporary directory, appends `--secret-file` and `--var-file` to the supplied `act` command, and removes the files after success or child failure. Both files always exist at mode `0600`, even when empty. Unmarked local values are excluded. Supplying either managed file flag manually is rejected. `SIGKILL` or a host crash can prevent normal cleanup.

`gh-vault secret export-act` remains available when explicit persistent `.secrets` and `.vars` files are required. Multi-line values use `@base64:` encoding for [act](https://github.com/nektos/act). Export writes only nonempty kinds: an existing `.secrets` or `.vars` file is left untouched when that kind is empty. Use fresh paths or remove stale exports explicitly before reuse.

### Validate workflow wiring

```sh
gh-vault workflow check
gh-vault workflow check --json      # machine-readable output
gh-vault workflow check --fix       # print suggested env block for unreferenced values
```

Scans `.github/workflows/*.yml` and `*.yaml` for `secrets.NAME` and `vars.NAME` references, then cross-checks against local declarations. Reports four finding types, each as `file:line: severity: explanation`:

| Severity | Finding | Description |
|---|---|---|
| `warning` | Unreferenced local value | A typed declaration in `.env` is never referenced by any workflow |
| `error` | Type mismatch | Workflow uses `vars.NAME` but `.env` marks `NAME` as `secret`, or vice versa |
| `error` | Fallback order | Expression puts `vars.X` before `secrets.X` in a `\|\|` chain |
| `warning` | Orphan reference | Workflow references a name not declared locally and with no fallback default |

Excludes GitHub-provided names like `GITHUB_TOKEN`. Exits nonzero for unreferenced declarations, type mismatches, or fallback-order findings. An unreferenced warning therefore fails; orphan warnings alone do not. `--fix` prints a suggested `env:` block for unreferenced local values. Does not impose repository-specific namespace mappings. The scanner is line-based, not a full YAML/expression parser: use uppercase dot-name references inside single-line expressions. A clean check does not certify a runnable workflow.

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
| `# gh-vault: secret <profile>` | Resolves the assignment to the token stored under `gh-vault/<profile>` in `pass`; the literal value is ignored |
| `# comment` | Comment line, ignored |
| `value # trailing` | Inline comment stripped (space before `#` required) |

Unquoted `$(command)`, `${variable}`, and backticks are rejected. Quoted values keep these characters literally; no value is evaluated as shell code. Keys match `[A-Za-z_][A-Za-z0-9_]*`. Explicit `@file:` paths may be absolute or home-expanded and are not confined to the checkout: only use trusted dotenv inputs.

Templates retain classification without activating assignments:

```dotenv
# gh-vault: variable
# REGION=

# gh-vault: secret
# API_KEY=
```

The directive must remain immediately adjacent to the commented assignment. This keeps conventional `.env.example` placeholders while preserving type metadata for migration and restore.

Values with embedded newlines are stored as `@base64:` when written to `.env` or exported for `act`. Literal values beginning `@file:` or `@base64:` are quoted so a later parse does not reinterpret them as transport instructions.

## Security model

- Tokens, secret environment values, and eligible archive templates live only in `pass` under `gh-vault/`.
- Bitwarden connection metadata contains no credential. Bitwarden access tokens come only from the explicitly selected `BWS_ACCESS_TOKEN` or `pass` entry below `gh-vault/bitwarden/`; there is no fallback, GitHub validation, child-process injection, or token output.
- Bitwarden project/environment access loads only the explicit local adapter path, validates endpoint binding before credential access, and uses temporary per-request state. Environment responses are accepted only for the requested names, organization, and project. The adapter is trusted same-user code, not a sandbox.
- Only values explicitly marked `# gh-vault: variable` may enter the public XDG archive. Operators must classify them as safe for clear-text local storage before archiving or migration.
- Public variable payloads and value-free indexes are mode `0600` below `${XDG_CONFIG_HOME:-~/.config}/gh-vault/environments/`, with mode-`0700` directories. Secret and local-only values never enter those files or `config.json`.
- `.env`, `.secrets`, and `.vars` are ignored by Git. Generated files are mode `0600`; Bitwarden restore uses an adjacent private temporary file and atomic replacement.
- `output` and Git's exact credential-helper response deliberately emit token bytes. Other command output must not disclose them. Child processes and external tool diagnostics are not an output-redaction sandbox.
- Token validation against `https://api.github.com/user` sends the token to GitHub over HTTPS; no third party is involved.
- Config writes are atomic (temp file + `fsync` + `os.replace`) and always set mode `0700` directory / `0600` file.

## Maintenance and verification

Current behavior and its evidence are indexed in [product capabilities](docs/product/index.md).
Read [architecture](docs/architecture.md), [security boundaries](docs/security.md),
and [design decisions](docs/design-decisions.md) for cross-cutting contracts.
Material implementation progress belongs in [active CHGs](docs/changes/README.md),
not private plans. The [repository playbooks](skills/AGENTS.md) are optional aids.

Development checks need Python 3.10+, uv, Node.js 22+, and make. Node is used only
for maintenance validation; the installed Python application does not need it.
No Node package manager or Python runtime dependency is added.

```sh
make verify          # records + offline Python tests + validator regressions
make records-check   # record structure, lifecycle, references, visual inventory
make test-python     # isolated pytest runner; does not update uv.lock
make test-records    # synthetic node:test validator fixtures
```

CI runs the same gate on branch pushes and pull requests. Tests use temporary
files, a fake password-store executable, and mocked external services; they do
not authenticate against GitHub, decrypt real data, or execute real act jobs.
The local gate does not prove remote PyPI publishing; use the separate
[release contract](docs/RELEASING.md).

Operational limits are explicit in the CAPs: destructive prune does not protect
opposite-type/empty declarations, `run-act` rejects profile references, and
unreferenced workflow warnings fail the command. These are documented behavior,
not promises of stronger safety guarantees.

## License

MIT — see [LICENSE](LICENSE).
