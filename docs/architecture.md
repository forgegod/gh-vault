# Architecture

## Product boundary

gh-vault is a Linux-oriented Python 3.10+ command-line application for named
GitHub tokens, typed project environments, Actions values, workflow wiring, and
explicit Bitwarden project access through an operator-held local adapter.
The `forgegod-gh-vault` distribution installs the `gh-vault` executable;
`python -m gh_vault` delegates to the same dispatcher. Argparse displays the
same product label. The package has no declared third-party Python runtime
dependencies. `pass`, GPG, Git, `gh`, and act are external tools used by the
operations that need them, not embedded services.

The [capability index](product/index.md) owns current material behavior and its
executable evidence. [README](../README.md) is the operator command guide;
[security](security.md) owns trust and plaintext boundaries.

## Runtime boundaries

| Module | Responsibility | External boundary |
| --- | --- | --- |
| `src/gh_vault/cli.py` | Argparse commands, dispatch, output, exit handling, process handoff | TTY/stdin, stdout/stderr, exec |
| `src/gh_vault/store.py` | Token metadata, vault backend, public environment store | `pass`, restrictive JSON files |
| `src/gh_vault/bitwarden.py` | bws profile resolution, local adapter loading, project-result validation | Operator bws config and local `gh_vault_bws` checkout |
| `src/gh_vault/github.py` | Token scope/expiration inspection | HTTPS GET to GitHub user API |
| `src/gh_vault/envfiles.py` | Dotenv syntax, origin identity, archive/restore/migration | Git origin lookup, explicit file inputs |
| `src/gh_vault/actions.py` | Actions selection, sync/check/import, act execution, workflow scanning | `gh`, act child, local workflow files |

`StoreError` is the shared application error boundary. The main CLI converts it
to an argparse error; direct helper tests assert the exception instead. This is
not a blanket catch for every OS error or malformed input.

## Data flow and persistence

1. `set` validates input syntax, attempts GitHub inspection, stores the token
   through `pass`, then records non-secret profile metadata and selection.
2. Bitwarden connection setup reads one explicit named bws profile, validates
   and records its HTTPS endpoint pair plus expected organization, and optionally
   stores a separate access token through `pass`. Project resolution revalidates
   the current Git origin and endpoint binding before passing one explicit UUID
   and selected credential to a versioned local adapter interface.
3. Typed dotenv directives explicitly select secret/variable values. Runtime
   profile references resolve in-process for consumers with a vault store.
   `env run`/`run` inherit the parent environment and replace the current process.
4. Archive identity is a normalized host/path plus an exact origin string.
   Public variables and a value-free index live under the XDG config root;
   secrets and eligible raw templates live in `pass`. Payloads are verified
   before stale values are removed; there is no cross-store transaction.
5. Actions sync hands selected values to `gh` on stdin. Remote operations default
   to repository scope or use an explicit `--github-environment` target after a
   read-only environment preflight. Check operations compare remote names/types,
   not secret values. `--migrate-types` and `--prune` are explicit destructive
   modes confined to that selected scope; their selection boundary is detailed in
   CAP-006.
6. `run-act` manages private temporary files for literal typed values and waits
   for the child. Persistent export supports vault references; ephemeral runs
   reject them. Workflow check is a local line-based reference scanner.

| Artifact | Format/location | Boundary |
| --- | --- | --- |
| Profile metadata | XDG `gh-vault/config.json` | Profile names, scopes, notes, expiration, active selection |
| Tokens | `pass`: `gh-vault/<profile>` | Encrypted backend; single-line token |
| Bitwarden connections | XDG `gh-vault/config.json` | bws config/profile, resolved endpoint pair, expected organization UUID |
| Bitwarden access tokens | `pass`: `gh-vault/bitwarden/<connection>` or selected `BWS_ACCESS_TOKEN` | Separate credential source with no fallback |
| Public variables | XDG `gh-vault/environments/<host>/<path>/env[.<profile>].variables.json` | Version 1, exact origin, string values |
| Environment index | Same directory, `environments.json` | Version 1, origin, per-profile boolean presence fields |
| Archived secrets | `pass`: `gh-vault/projects/<host>/<path>/env[.<profile>].secrets.json` | Version 3, origin, string values |
| Archived template | Same vault base, `env[.<profile>].example` | Raw template text; present only for secret-bearing archives |
| Explicit legacy input | Same vault base, `env[.<profile>].json` | Version 2; read only by archive migration |

The XDG base is `${XDG_CONFIG_HOME:-~/.config}`. The password store root is
`${PASSWORD_STORE_DIR:-~/.password-store}`. GPG owns unlock lifetime. Generated
plaintext environments/exports are local artifacts, not repository records.

## Maintenance structure

- Root/child `AGENTS.md` files own scope, constraints, and maintenance rules.
- `docs/product/capabilities/` describes current behavior; every CAP names source
  and asserting tests. Partial capabilities state the implemented boundary.
- `docs/changes/active/` is created for real material requests; completed or
  cancelled records move to `archive/`. Empty inventories need no placeholder
  files. Private notes and completed plans are not imported as current progress.
- Review assets belong to an owning CHG under `docs/changes/reviews/`; canonical
  visuals belong to product wireframes only when a primary visual surface
  exists. CLI/protocol CAPs declare `none`; branding is owned by `assets/`.
- `skills/software-development/` carries a coherent optional CAP/CHG phase
  family. It does not require agent-profile configuration or authorize commits.
- The dependency-free Node validator and `tests/records/` are developer tooling,
  not part of the Python application runtime. It recognizes pytest and JS/TS
  evidence filenames while preserving lifecycle/review/wireframe checks.

## Verification and release

`make verify` runs `make records-check` plus `make test`: the live record tree,
synthetic Node validator fixtures, and the offline Python suite. The uv test
runner uses `--no-project` so it does not update the application environment or
lockfile. Node.js 22+ is required only for maintenance commands.

`.github/workflows/ci.yml` runs the gate with Python 3.10 and 3.14 on branch pushes
and pull requests, with read-only permissions and no product credentials.
`.github/workflows/publish.yml` is a separate version-tag workflow; its existing
OIDC/environment contract lives in [RELEASING](RELEASING.md). Local success does
not establish remote CI execution, environment protection, or PyPI publication.

Record validation establishes structure and referenced paths, not truthful
assertions, visual freshness, or live integration. Tests mock GitHub/gh/act and
use a fake pass backend. See each CAP and the security contract for evidence
limits. Do not promote a mocked collaborator test into a live-service claim.

## Non-goals

- No hosted service, GUI, application database, or general secrets-provider framework.
- No public/private adapter fetch, SDK dependency in this distribution, region probing, project-name discovery, or project creation.
- No PAT issuance/rotation service or control of GPG-agent caching.
- No shell evaluation, implicit archive migration, or automatic public
  classification of secrets.
- No credentialed external operations in the local/CI gate.
- No parallel material-progress system or invented historical receipts.

Architectural changes require explicit approval and synchronized root DOX,
architecture, affected tests/child contracts, and cross-cutting
[decision rationale](design-decisions.md).
