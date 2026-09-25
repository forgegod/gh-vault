# CHG-004 — Bitwarden environments and reversible Actions delivery

**Status:** blocked
**External request:** Direct operator request: Apply the result in ../../rb/gh-vault/ using the ../../rb/gh-vault/skills/software-development/phased-plan-design/
**Impacts:** CAP-001, CAP-002, CAP-003, CAP-004, CAP-006, CAP-008
**Baseline:** `70562afa934e2c713d3d77003d365c76ef4138dd` (0.3.0)
**Review package:** [Integration contract and upstream findings](../reviews/CHG-004/README.md)

## Request and execution boundary

Extend the operator-facing gh-vault behavior, not a second public tool, to store
declared secrets and variables in Bitwarden Secrets Manager, recreate `.env`
from `.env.example`, and optionally retrieve configuration directly in GitHub
Actions with an explicit switch back to GitHub Secrets/Variables. SDK-calling
implementation takes effect only in the private sibling `../gh-vault-bws`. This
repository implements the CLI, credential boundary, local-path loader, and
non-functional mock. The operator approved externally provisioned machine
accounts, operator-level region configuration, optional local encrypted token
storage, and an explicit project ID for the initial scope instead of incomplete
project-name listing or a mandatory repository TOML binding file.

This record is the sole phased plan, not a claim of fully implemented support.
Phases 1–5 are complete at verified checkpoints. Later phases remain pending,
and the record is blocked between phases until another execution cycle is
selected. No commit, push, release, live credential access, or remote write is
authorized by this plan.

The operator explicitly approved the narrow Bitwarden extension and local-path
split in Phase 1. Phases 2–5 implement connection metadata, optional encrypted
credential storage, the explicit local loader, project/result validation,
fresh-clone dotenv recovery, previewed explicit upload, and reviewed GitHub
standby publication through a compatible adapter. Dual-provider workflow
delivery remains unimplemented.

## SDK license boundary

Publishing an open-source project that uses the Bitwarden Secrets Manager SDK
is not allowed. The grant is the Bitwarden Software Development Kit License
Agreement, Version 1, 17 March 2023, in `sdk-sm` `LICENSE` (the same text as
the published Python wheel). This is a reading of that text, not a legal opinion.

- Section 3.1 limits use to developing, testing, and demonstrating a Compatible
  Application; personal or family use; or internal business operations in
  connection with a paid Bitwarden server-product license. In every case that
  application may not be offered, licensed, or sold to a third party. A public
  GitHub project that uses the SDK does both. A paid Secrets Manager license
  does not remove that proviso.
- Section 3.4 forbids copying, modifying, redistributing, or making derivative
  works of the SDK, except its stated CLA and third-party open-source
  exceptions. Section 3.5 does not relicense the SDK or a Compatible
  Application. This MIT tree must not vendor SDK source or binaries, depend on
  the SDK, or republish it.

Operator proposal for continuing realization: a private `github.com/forgegod/`
project holds the SDK implementation; this repository holds a mock and an agent
guide for implementing that mock; a `bws install` command loads the private
module from a local directory or from GitHub, including `git pull` updates.

That proposal is not adoptable as stated.

- A command in this published CLI that clones, pulls, or auto-updates the SDK
  module offers that Compatible Application to third parties. Private repository
  visibility does not repair an installer shipped here. Do not add `bws install`,
  a GitHub fetch, or a `git pull` updater for the module.
- An agent guide in this tree that specifies how to implement the mock against
  the SDK is a public recipe for the same application. Keep SDK imports, call
  sequences, and implementation steps out of this repository. Public text may
  name only the interface a substitute must satisfy: inputs, outputs, and
  value-free errors.

Approved implementation boundary:

- This repository defines an interface and a non-functional mock. No
  SDK dependency, import, source, binary, or call recipe.
- The organization that holds the paid license keeps the private module in the
  sibling checkout `../gh-vault-bws`, linked to the private repository
  `https://github.com/forgegod/gh-vault-bws`. Its build contract is that
  repository's `docs/specification.md`. gh-vault loads that module only from a
  local path the operator already has. The operator updates
  that checkout. gh-vault does not fetch it.
- Do not add this repository as a git submodule of gh-vault. A submodule is a
  fetch path in the published tree and is not required for simultaneous edits
  of the sibling checkouts.
- SDK calls, including authentication, project listing, secret reads, creates,
  and updates, are implemented in
  `../gh-vault-bws` against that repository's `docs/specification.md` and its own
  change record. Do not implement those calls in this repository. Phases below
  that say "adapter" mean the local-path loader or mock in
  `src/gh_vault/bitwarden.py`, which delegates to the loaded module.

## Concept to carry forward

### Authority and operator setup

- `.env.example` remains the versioned declaration of keys, adjacent
  `# gh-vault: secret` / `variable` classification, documentation, and safe
  defaults. Bitwarden holds configured values for both types. Local-only
  assignments are not silently uploaded or reconstructed as managed values.
- Bitwarden projects, machine accounts, permissions, and access tokens are
  provisioned outside gh-vault. An account may access multiple projects with
  different permissions; another token for the same account does not narrow
  its project access.
- Select the server/region before any authentication or discovery. Prefer
  existing named `bws` profiles (`~/.config/bws/config`), with expected
  organization and credential references in operator-level metadata outside
  repositories. Do not probe regions with a token or silently use the US service.
- Accept externally supplied `BWS_ACCESS_TOKEN`; optionally keep a separately
  typed Bitwarden credential in gh-vault's local `pass`/GPG vault. Resolve the
  token only into the selected client process; never apply GitHub PAT validation,
  GitHub API inspection, `GH_TOKEN`, or `GITHUB_TOKEN` injection to it. No global
  shell mutation or plaintext credential metadata. Local GPG provides independent
  bootstrap recovery; the access token must not live only behind itself in BWS.
- An operator account may span managed projects. CI uses a separate read-only,
  project-restricted machine account, not the operator's multi-project credential.
  Restoring local access requires independently provisioned authorization after
  a fresh clone; repository contents alone do not grant access.

### Repository and key discovery without mandatory TOML

- Under the explicitly selected connection/organization, require `--project-id`
  in the initial scope and match declared dotenv keys to exact Bitwarden entry
  names inside that project. Validate the Git origin and UUID before lookup; do
  not fuzzy-match, infer sensitivity from names, or silently choose a project.
  Project-name derivation remains excluded until the official client exposes a
  complete paged listing boundary.
- Missing, inaccessible, wrong-organization, or mismatched IDs fail with
  value-free diagnostics. Discovery is read-only; creating/updating entries is a
  separate previewed operation. Do not automatically create projects. No
  mandatory `.gh-vault.toml` and no hidden durable cache are required for
  fresh-clone recovery; the operator supplies the project ID explicitly.
- UUIDs identify resolved targets for the current operation and generated CI
  mappings. Renames and deleted/recreated entries require explicit reconciliation;
  a published UUID mapping must not silently rebind by name at runtime. Detecting
  replacement between independent name-only local lookups is not guaranteed.
- Named `.env` profiles require an explicitly selected Bitwarden target in the
  initial scope; never infer a project or GitHub Environment from the filename.
  GitHub deployment scope remains the existing explicit `--github-environment`.

### Value lifecycle and portability

- Bitwarden becomes the value authority for opted-in projects. Importing existing
  local values is explicit; restoring locally and publishing to GitHub are
  directional operations, not automatic bidirectional synchronization. Existing
  local archive behavior remains available without implicit migration/fallback.
- Preserve missing versus present-empty values, literal characters, multiline
  content, and template comments/directives. Missing configured keys must not
  silently become example passwords. Phase 1 must settle required/optional/default
  semantics because current directives encode type, not requiredness.
- Resolve explicit `@file:` / `@base64:` inputs intentionally. A local file path
  is not a portable backup of its contents. Define a reconstructable representation
  and prove a round trip on a second synthetic checkout. Do not silently upload
  placeholders for `# gh-vault: secret PROFILE` references.
- Preview names, types, targets, and operations only. Never print values, value
  diffs, credential-bearing errors, or public hashes of secret values. Remote
  writes require read-back verification in-process; failures must not claim a
  completed import or cross-store transaction. No automatic remote deletion.

### Reversible GitHub Actions delivery

- Two explicit modes supply the same application environment: `github` reads
  reviewed published Secrets/Variables; `bitwarden` retrieves selected keys using
  the official `bitwarden/sm-action`. Applications remain provider-agnostic.
- Proposed control `CONFIG_SOURCE` is a non-secret repository variable: unset
  retains `github`, invalid non-empty values fail. A manual dispatch override
  selects repository default, GitHub, or Bitwarden; scheduled runs use the
  repository setting. Resolve once per job, without truthiness-based per-key
  provider fallbacks. These names are proposed, not existing CLI/API contracts.
- GitHub mode makes no Bitwarden requests and needs no Bitwarden client/token.
  Bitwarden failure stops the job, never silently mixes providers. Switching
  affects a fresh run, not configuration halfway through a running job.
- Retain an explicitly provisioned Bitwarden access token in GitHub Secrets,
  explicit EU/server configuration, native `GITHUB_TOKEN`, and control values
  needed before steps can run. Runner/container selection and deployment
  authorization cannot depend on a later fetch step. Preserve GitHub Environment
  approvals and permissions; do not expose credentials to untrusted PR code.
- Generate per-job UUID-to-variable mappings from declarations and discovery;
  never maintain a second hand-written key/UUID inventory. The official action
  needs individual secret UUIDs, not just the project ID. Choose one derived
  mapping destination in Phase 1: workflow input or GitHub configuration variable.
  The latter requires a locally reproducible representation for offline checking.
- Fetch only the job's required values before their first consumer, including
  submodule/registry authentication. Existing step `env:` bindings must not
  overwrite the selected provider's values. Preserve aliases, safe defaults,
  and deliberate runner-local overrides. Prefer step-scoped delivery; no secret
  artifacts, cross-job secret outputs, or value interpolation into shell source.
- Keep GitHub values as warm standby by default; refresh them explicitly after
  reviewed rotations/configuration changes. Record value-free publication
  metadata, not secret fingerprints. Presence/type checks cannot prove secret
  equality or credential validity; a safe authentication probe establishes the
  narrower operational evidence. During a Bitwarden outage, rollback must not
  require fetching Bitwarden first. Removing standby copies forfeits immediate
  outage rollback and is a separate operator decision.

## Baseline and affected contracts

- [CAP-001](../../product/capabilities/CAP-001-token-profiles.md) and
  [CAP-002](../../product/capabilities/CAP-002-credential-delivery.md):
  `src/gh_vault/cli.py` validates GitHub tokens and injects GitHub-specific
  environment names. `src/gh_vault/store.py` owns encrypted storage and metadata.
  Add a distinct credential boundary, not a relaxation of GitHub token checks.
- [CAP-003](../../product/capabilities/CAP-003-typed-environments.md) and
  [CAP-004](../../product/capabilities/CAP-004-environment-archives.md):
  `envfiles.py` owns parsing, origin identity, archive/restore, and
  `render_template`. `actions.py:action_values` and `runtime_environment` currently
  omit empty literals. `_write_private` writes before chmod. New recovery promises
  therefore require explicit tests and private-from-creation writes, not blind
  reuse or untested claims about all existing writers.
- [CAP-006](../../product/capabilities/CAP-006-actions-values.md):
  `actions.py` already selects types and sends values to `gh` on stdin, with
  explicit GitHub Environment scope. Retain that boundary for standby publication.
- [CAP-008](../../product/capabilities/CAP-008-workflow-validation.md):
  `check_workflows` is a limited line-based scanner. Extend only the supported
  generated dual-provider shape; do not bypass it or claim general YAML evaluation.
- Read [architecture](../../architecture.md), [security](../../security.md),
  [design decisions](../../design-decisions.md), production/test DOX, and affected
  CAPs before each slice. Existing local Actions behavior (CAP-007) needs regression
  coverage, not a redesign. All planned surfaces are CLI/protocol (`none`).

## Phases

Commands run from the repository root. New test paths below are planned artifacts,
not existing evidence. Each implementation phase updates affected CAPs, owning
DOX, README/security contracts where applicable, and this record together.

| # | Phase | Status | Verification gate |
| --- | --- | --- | --- |
| 1 | Resolve integration contracts and approval | done (`make verify`: 206 Python tests, 82 Node tests, record validation; operator decisions recorded) | `make records-check` exits 0; integration-contract checklist below is resolved and explicitly approved |
| 2 | Operator connection and project discovery | done (143 focused tests; record validation; `make verify`: 238 Python tests and 82 Node tests) | `uv run --no-project --with pytest python -m pytest tests/test_bitwarden_connection.py tests/test_cli.py tests/test_store.py` exits 0; `make records-check` exits 0 |
| 3 | Fresh-clone dotenv recovery | done (102 focused tests; `make verify`: 256 Python tests, 82 Node tests, record validation) | `uv run --no-project --with pytest python -m pytest tests/test_bitwarden_environments.py tests/test_vault_features.py` exits 0; `make records-check` exits 0 |
| 4 | Explicit upload to Bitwarden | done (55 focused tests; `make verify`: 275 Python tests, 82 Node tests, record validation) | `uv run --no-project --with pytest python -m pytest tests/test_bitwarden_environments.py tests/test_bitwarden_connection.py` exits 0; `make records-check` exits 0 |
| 5 | Publish GitHub standby values | done (206 focused tests; record validation; `make verify`: 287 Python tests and 82 Node tests) | `uv run --no-project --with pytest python -m pytest tests/test_bitwarden_actions.py tests/test_vault_features.py tests/test_cli.py` exits 0; `make records-check` exits 0 |
| 6 | Dual-provider Actions and offline diagnostics | pending | `uv run --no-project --with pytest python -m pytest tests/test_bitwarden_actions.py tests/test_capability_boundaries.py` exits 0; `make records-check` exits 0 |
| 7 | Integrate recovery evidence and current-state records | pending | `make verify` exits 0; documented opt-in live canary proves Bitwarden delivery and independent GitHub rollback |

## Phase 1 — Resolve integration contracts and approval

**Goal:** Agree an implementable, secret-safe boundary before changing product code.

1. Re-read this plan, the source/CAP boundaries above, and upstream client/action
   documentation. Obtain explicit approval to extend the root's backend non-goal.
2. Settle the integration-contract checklist: CLI operation names; connection and
   credential precedence; organization verification; explicit project overrides
   and named-profile targeting; missing/empty/default handling; profile references;
   portable multiline/file representation; derived per-job mapping destination;
   safe publication/read-back behavior; selector authority and standby metadata.
3. Verify actual official client behavior with synthetic inputs only. Prefer
   `bws` profiles for operator endpoint configuration; its documented write
   interface puts values in argv, and its project-list path neither accepts an
   expected organization nor follows a returned continuation token, so do not use
   the CLI for value writes or discovery. Never weaken the no-secret-argv rule or
   implement cryptography/raw REST. Do not adopt the SDK in this repository. The
   distribution question is closed in "SDK license boundary" above: an open-source
   project that uses the SDK is outside section 3.1. Operations that need the SDK
   stay in an operator-held private module loaded from a local path, and only after
   the approvals named there. An optional dependency, installer, or agent recipe
   does not reopen it.
4. Reconcile the help page's action major with the upstream release, verify
   `cloud_region`, `set_env`, masking/outputs, runner requirements, and choose a
   full commit SHA. Check actual empty-value support end-to-end, including GitHub
   storage and expressions; reject unsupported cases rather than silently change
   them. No fabricated canary results or real operator credentials.
   Review the launcher's release-binary download separately from its commit pin;
   the v3.0.1 launcher has no binary digest verification. Require an explicit
   supply-chain decision and required-output checks for missing results.
5. Record the agreed contract in a linked `reviews/CHG-004/README.md` review-only
   package if detail exceeds this plan, following changes DOX. Add its owner link
   when created. Keep executable specification and future CAP claims out of the
   current product inventory until implementation. Update later gates if verified
   tool constraints require it; keep one progress authority.

**Verification gate:** `make records-check` exits 0; integration-contract checklist
above is resolved and explicitly approved. This is contract approval, not proof
of implemented behavior; do not change current CAP claims in this phase.

**Completion evidence:** Public-source and wheel inspection, isolated `bws 2.1.0`
help, a credential-free local TLS client probe, and a synthetic baseline formatter
probe are recorded in the review package. `bws` authenticated to the selected
synthetic endpoints and made one organization-scoped project request, but silently
discarded a nonempty continuation token. `make verify` passes (206 Python tests,
82 Node tests, record validation). The operator approved the narrow backend
extension and local-path split, selected explicit project-ID-only discovery for
the initial scope, and accepted the pinned action launcher's residual unverified
release-asset trust. No current CAP changed because no behavior is implemented.
Phase 1 is the verified checkpoint for the selected Phase 2 execution.
**Operator decision:** do not publish an open-source project that uses the SDK.
The suggested public `bws install` / GitHub `git pull` path is rejected. Retain
upload and later phases under the local-path split; do not substitute read-only
support, drop upload, or weaken argv and cryptography constraints. Do not
implement outside that approved boundary.

## Phase 2 — Operator connection and project discovery

**Goal:** Resolve an authorized repository project without repository-local setup.

1. Add focused synthetic failing tests, then implement the agreed CLI/connection
   boundary in `cli.py`, `store.py`, and a new `src/gh_vault/bitwarden.py` adapter.
   That module path is proposed; update production DOX if introduced. The adapter
   in this repository is an interface and non-functional mock, or a loader for a
   local path the operator already has. It must not import, vendor, fetch, or
   call the SDK. Authentication, endpoint binding, and project listing take
   effect in `../gh-vault-bws`. Tests here fake that boundary. The public loader
   requests only the explicit project and requires a versioned, structured result
   carrying the selected project and expected organization IDs; it does not expose
   the private implementation's project-list response or SDK operations.
2. Support external token injection and optional independent encrypted credential
   storage; bind it to the explicit server/profile and expected organization.
   Refuse conflicts instead of trying credentials against another server. Preserve
   GitHub profile storage/selection and credential-helper behavior.
3. Require and verify an explicit project UUID after validating Git origin; cover
   missing/invalid/inaccessible projects, wrong organization, renamed origin, and
   region mismatch. Never list by name or auto-create in the initial scope. With
   no repository binding file or durable project cache, a valid renamed origin is
   revalidated for the current invocation rather than compared with hidden history;
   the explicit project UUID remains the target authority.
4. Add `tests/test_bitwarden_connection.py` with fake client/process boundaries;
   assert no token/value output, argv leakage, metadata leakage, shell mutation,
   unsolicited cross-project access, or accidental GitHub token inspection.
5. Update affected CAP-001/CAP-002 and root/architecture/security/decision/child
   contracts for the approved implemented extension. Preserve the no-hosted-service
   and offline-test boundaries; do not introduce a general provider framework.

**Verification gate:** `uv run --no-project --with pytest python -m pytest tests/test_bitwarden_connection.py tests/test_cli.py tests/test_store.py` exits 0; `make records-check` exits 0.

**Completion evidence:** The CLI stores value-free named connection metadata,
keeps optional Bitwarden credentials in separate `pass` entries, validates Git
origin and bws endpoint drift before credential access, and resolves only an
explicit project through adapter API version 1 loaded from an explicit local
path. Synthetic tests cover inaccessible/mismatched targets, organization and
region mismatch, renamed-origin revalidation, credential-source isolation,
value-free errors/output, temporary state cleanup, and GitHub-profile regression.
The focused gate passes on Python 3.10 and 3.11 (143 tests); `make records-check`
and `make verify` pass (238 Python tests, 82 Node tests). No live Bitwarden call,
SDK import, remote write, commit, or push occurred.

## Phase 3 — Fresh-clone dotenv recovery

**Goal:** Recreate a usable private `.env` from the template and selected project.

1. Extend the loader or mock and `envfiles.py`/CLI with the agreed read-only
   restore path. Value retrieval takes effect in `../gh-vault-bws`. This
   repository consumes only declared managed keys and the approved
   default/optional policy. Read and validate all selected values before
   touching the target file.
2. Add `tests/test_bitwarden_environments.py` proving restoration in a fresh
   temporary checkout without cached UUIDs or an original `.env`. Cover comments,
   directives, quoted metacharacters, Unicode, empty versus absent values,
   multiline/transport markers, reserved keys, duplicates, unavailable service,
   explicit profile targets, and local-only exclusion.
   Include literal values beginning `@file:` / `@base64:`: the current formatter
   emits these unquoted and parsing interprets them as transport instructions.
   A synthetic Phase 1 probe reproduced changed content and an unintended file
   lookup; the new recovery path must encode them without reinterpretation.
3. Refuse overwrite unless explicitly requested; use private-from-creation files
   and replacement that leaves the old target intact on validation/write failure.
   Do not automatically restore source-machine `@file:` paths or unrelated entries.
4. Preserve ordinary local archive/restore behavior; update CAP-003/CAP-004 and
   documentation only for the newly implemented boundary. Show the independent
   authorization bootstrap and no-TOML recovery flow.

**Verification gate:** `uv run --no-project --with pytest python -m pytest tests/test_bitwarden_environments.py tests/test_vault_features.py` exits 0; `make records-check` exits 0.

**Completion evidence:** `bitwarden env restore` preflights one explicit template,
connection, project, adapter path, and credential source; requests only typed
declarations; validates exact entry IDs, names, organization, project membership,
and value shape; and atomically installs a mode-`0600` target only after the full
response passes. Synthetic tests cover fresh and named checkouts, comments,
directives, local-only deactivation, metacharacters, Unicode, empty/missing,
multiline and literal transport markers, reserved names, duplicate/extra entries,
scope mismatch, unavailable service, profile references, overwrite refusal, and
replacement failure. The focused gate passes (102 tests) and `make records-check`
passes; `make verify` also passes (256 Python tests and 82 Node tests). No live
Bitwarden call, SDK import, remote write, commit, or push occurred.

## Phase 4 — Explicit upload to Bitwarden

**Goal:** Seed or intentionally update declared values without stale-file auto-sync.

1. Implement previewed create/update selection in the CLI and the loader or mock.
   Create and update calls take effect in `../gh-vault-bws`. Matching alone never
   overwrites; require the agreed explicit write/update authorization. Keep
   project creation, remote deletion, and machine-account management excluded.
2. Handle variables and secrets identically as encrypted Bitwarden entries while
   retaining their template classification. Resolve transport markers and the
   approved profile-reference policy without sending local placeholders.
3. Read back the exact written entry and verify target/key/value internally;
   report partial failure honestly. Do not claim a multi-entry transaction.
   Prove reruns do not create duplicate keys after partial completion.
4. Extend environment/client tests for read-only credentials, wrong-project
   responses, duplicate names, update rejection, write/read-back failure, trailing
   newlines, safe client arguments, and hostile error/output text. Test uploading
   from one synthetic checkout and restoring into a second one.
5. Update implemented CAP/README/security boundaries and evidence; keep local
   data unchanged until the operator explicitly chooses a later restore.

**Verification gate:** `uv run --no-project --with pytest python -m pytest tests/test_bitwarden_environments.py tests/test_bitwarden_connection.py` exits 0; `make records-check` exits 0.

**Completion evidence:** `bitwarden env upload` preflights one explicit dotenv,
connection, project, adapter path, required adapter operations, and credential
source. The default value-free preview classifies exact-name creates, updates,
and unchanged entries; `--apply` authorizes creates and `--update-existing`
explicitly includes updates. Upload resolves explicit transport markers, preserves
quoted literal markers, excludes local-only declarations, rejects profile
references/NUL, and validates exact operation, ID, key, value, organization, and
project membership from adapter read-back. Synthetic tests cover duplicate names,
read-only/update failures, wrong targets, incomplete or changed read-back, hostile
adapter text, trailing newlines, empty values, partial-failure reporting, rerun
deduplication, and upload/restore across separate temporary checkouts. The focused
gate passes (55 tests); `make records-check` and `make verify` pass (275 Python
tests and 82 Node tests). No live Bitwarden call, SDK import, private-sibling
implementation, remote write, commit, or push occurred.

## Phase 5 — Publish GitHub standby values

**Goal:** Keep a reviewed GitHub copy usable independently of Bitwarden at runtime.

1. Add `tests/test_bitwarden_actions.py` and reuse the existing typed `actions.py`
   publication boundary from resolved values, without requiring a logged plaintext
   export. Separate Bitwarden reads from GitHub write authorization. Those reads
   take effect in `../gh-vault-bws`; this phase publishes already resolved values.
2. Preserve dry-run, type classification, explicit repository/Environment scope,
   and stdin-only writes. Do not infer remote scope from source profiles or make
   pruning/type migration part of ordinary standby refresh.
   Reuse the stdin/scope boundary, not raw error propagation: existing `sync`
   includes child stderr and has no read-back. The new publication path must
   suppress credential-bearing child diagnostics and add the verification below.
3. Record publication scope, time/revision metadata, and success/failure without
   values or secret hashes. Read back exact GitHub Variable targets internally;
   check Secret names/types only and label the inability to verify their contents.
4. Test destination scope, type mismatches, partial publication, omitted/empty
   values under the approved contract, token separation, and no implicit deletion
   or selector flip. Do not claim rollback readiness from metadata alone.
5. Update CAP-006 and the rotation procedure: explicitly refresh standby copies,
   exercise safe authentication, and only then consider them usable for rollback.

**Verification gate:** `uv run --no-project --with pytest python -m pytest tests/test_bitwarden_actions.py tests/test_vault_features.py tests/test_cli.py` exits 0; `make records-check` exits 0.

**Completion evidence:** `bitwarden actions publish` derives typed names from one
explicit template, reads exact entries and IDs through the selected local adapter,
and requires an explicit GitHub repository plus optional Environment. Preview is
the default; `--apply` performs stdin-only create/update calls after empty-value
and type-drift checks. Applied Variables require exact name/value read-back;
Secrets require same-scope name/type presence. Child diagnostics are discarded,
partial failures remain explicit, and restrictive origin-bound metadata records
scope, source IDs, remote revisions, time, and per-key results without values or
hashes. Synthetic tests cover repository/Environment isolation, no deletion or
selector mutation, Bitwarden-token removal from every `gh` child environment,
hostile diagnostics, adapter cleanup, partial failure, and verification mismatch.
The focused gate passes (206 tests), and `make records-check` plus `make verify`
pass (287 Python tests and 82 Node tests).
No live Bitwarden/GitHub call, remote write, commit, or push occurred.

## Phase 6 — Dual-provider Actions and offline diagnostics

**Goal:** Supply one application contract from either provider without hidden fallback.

1. Produce the agreed per-job mapping/integration artifact through gh-vault;
   keep hand-maintained declarations separate from derived UUIDs. Include explicit
   region, pinned official action, bootstrap exclusions, aliases/defaults, and a
   declaration of the job's required key subset. Do not rewrite arbitrary workflows.
2. Implement the explicit selector and manual override in the supported workflow
   shape. Verify both providers reach the same consumer without empty-value
   fallback, GitHub step-env shadowing, or mixing sources. GitHub mode must work
   with no Bitwarden token, client, or network access. Record provider only.
3. Extend `check_workflows` and tests to recognize that shape offline, including
   the bootstrap token/control variables, mappings, required consumers, stale or
   inconsistent declarations, and safe ordering. Do not require Bitwarden secrets
   or remote lookups for local commit checks. Retain diagnostics for ordinary
   GitHub workflows and document unsupported YAML/expression constructs.
4. Test schedule/manual selection, invalid mode, missing bootstrap credential,
   retrieval failure, absent/empty values, aliases, multiline output safety,
   submodule authentication ordering, and the rollback branch. Use synthetic
   workflows/processes; distinguish those tests from GitHub expression execution.
   Cover duplicate UUID/alias rejection, incomplete action results, and the
   approved release-binary trust boundary; a pinned launcher is not by itself
   a verified immutable executable.
5. Document step-level versus job-start bootstrap constraints, approvals, untrusted
   fork/PR exclusions, masking limits, and derived-map refresh after UUID changes.
   Update CAP-008 and other actually affected CAPs in this slice. Select any new
   CAP identity only when an implemented boundary and tests exist.

**Verification gate:** `uv run --no-project --with pytest python -m pytest tests/test_bitwarden_actions.py tests/test_capability_boundaries.py` exits 0; `make records-check` exits 0.

## Phase 7 — Integrate recovery evidence and current-state records

**Goal:** Prove recovery and provider reversal, and leave truthful maintained contracts.

1. Run all offline gates, including existing GitHub credentials, local archives,
   explicit migrations, local Actions, scope/prune, and record-validator regressions.
   Validate links and confirm all affected CAPs still honestly declare primary
   surface `none`; no product wireframes are required for these CLI surfaces.
2. Obtain separate operator approval and a disposable project/repository for an
   opt-in live canary using synthetic values and externally provisioned credentials.
   Exercise upload/read-back, fresh-clone recovery, declared type publication,
   direct official-action retrieval, and GitHub-mode rollback with Bitwarden
   unavailable to that run. Include deliberate empty/multiline cases supported by
   the agreed contract. Do not use production credentials, email, or deployments.
3. Record only verifiable run IDs/URLs, selected modes, outcomes, and safe probe
   conclusions. Verify remote effects by reading the exact target. If canary access
   is unavailable, keep this phase incomplete and state the blocker; mocked tests
   are not a substitute. Any cleanup is explicit and limited to canary-owned data.
4. Reconcile root/child DOX, README, architecture/security/design decisions, CAP
   evidence, and indexes. Document independent token recovery, naming exceptions,
   rotation/standby upkeep, stale-map failure, and the loss of immediate rollback
   if GitHub copies are removed. Retain any review package at its stable path.
5. Only after all gates pass, mark the record done, move it to `archive/`, repair
   links, refresh the changes index, and rerun `make verify`. Archiving does not
   authorize committing, pushing, publishing, or migrating consuming repositories.

**Verification gate:** `make verify` exits 0; documented opt-in live canary proves
Bitwarden delivery and independent GitHub rollback.

## Out of scope

- Changes to consuming repositories, including itops-reporting, in this CHG;
  provide the integration here, then request separate rollout authorization.
- Automatic account/project provisioning, token issuance/rotation, organization
  policy changes, or replacing GitHub deployment protections.
- Removing GitHub bootstrap credentials, assuming OIDC support, automatic provider
  fallback, automatic pruning, background bidirectional sync, or broad CI tokens.
- A mandatory repository binding file, general secrets-provider framework,
  application runtime changes, hand-written cryptography, or a new hosted service.
- Vendoring the SDK, depending on it, documenting SDK call sequences, or a
  command that clones, pulls, or updates an SDK-backed module.
- A git submodule, or any other fetch path, for the private SDK module.
- Production data access or remote operations in ordinary tests/local commit
  checks. GitHub remote dry-run/check remains explicit pre-push/operator review.

## Sources and handoff

Phase 1 evidence and operator decisions are recorded above and in the review
package. The phase table records Phases 1–5 complete and two later rows pending.
CAP-001–CAP-004 and CAP-006, root/child DOX, README, architecture, security, and
design decisions describe the implemented local connection, project,
environment recovery/upload, and GitHub standby publication boundaries. They do
not claim dual-provider workflow delivery, live service behavior, rollback
readiness, or SDK implementation in this repository.

Public references inform the concept; recheck supported versions in Phase 1:

- [Bitwarden machine accounts](https://bitwarden.com/help/machine-accounts/)
- [Access tokens](https://bitwarden.com/help/access-tokens/)
- [Secrets Manager CLI](https://bitwarden.com/help/secrets-manager-cli/)
- [Secrets Manager SDK](https://bitwarden.com/help/secrets-manager-sdk/)
- [GitHub Actions integration](https://bitwarden.com/help/github-actions-integration/)
- [Official action source and inputs](https://github.com/bitwarden/sm-action)

Resume with the repository-local
[phased-plan-execution](../../../skills/software-development/phased-plan-execution/SKILL.md)
and this record. Phase 5 is complete and the record is blocked between phases;
select Phase 6 in a new execution cycle before changing its implementation scope.
