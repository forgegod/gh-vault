# CHG-004 — Bitwarden integration review

**Status:** review-only
**Owner:** [CHG-004](../../active/CHG-004-bitwarden-environments.md)

This package contains upstream findings and a proposed contract, not implemented
behavior or a second progress tracker. The owner's Phase 1 records approval and
remaining work. Current CAPs and architecture are unchanged.

## Approved license and loading boundary

The official Python SDK can avoid secret values in argv, but this published MIT
CLI cannot adopt it. The `bitwarden-sdk` 2.1.0 wheel contains the **Bitwarden
Software Development Kit License Agreement**, not MIT. The owning CHG records
the reading under "SDK license boundary".

- Section 3.1 restricts permitted uses and says a Compatible Application may not
  be offered, licensed, or sold to a third party. Publishing an open-source
  project that uses the SDK is outside that grant.
- Section 3.4 restricts copying, modification, and redistribution, subject to its
  stated exceptions; section 3.5 separately addresses open-source components.
- An optional dependency, a public installer, or an agent implementation recipe
  does not remove those restrictions.

See the [release's Python SDK license][sdk-license] and [root license][root-license].
Both license copies inside the published Linux x86-64 wheel were inspected and
contain those clauses. No SDK runtime dependency has been added or SDK credential
operation executed.

The approved continuation compatible with that reading is an interface and
non-functional mock in this repository, plus an operator-held private module
loaded from a local path. A command that fetches or updates that module is not
compatible. This approves implementation work, not current product behavior. Do
not bypass the boundary with secret argv, custom cryptography, or raw REST.

## Verified upstream boundaries

### Official clients and packaging

- `bws 2.1.0` and Python SDK 2.1.0 are published releases in `bitwarden/sdk-sm`.
  The Python release tag resolves to
  `0520690b9710af7a8b1e47aad776f002f369688f`.
- Running `bws secret create --help` and `bws secret edit --help` with a cleared
  environment and scratch HOME confirms positional `<VALUE>` for create and
  `--value <VALUE>` for edit. No stdin/value-file option is exposed. The
  [command source][bws-secret] confirms this write boundary; do not use it for
  gh-vault value writes.
- The [bws configuration][bws-config] is TOML at `~/.config/bws/config`, with
  `[profiles.NAME]` containing `server_base`, `server_api`, `server_identity`,
  `state_dir`, and `state_opt_out`. Explicit API/identity URLs override derivation
  from the base. An explicitly missing profile errors.
- Native [profile selection][bws-selection] permits a server URL override,
  token-ID-based profile selection, then a default profile. That is not the
  proposed gh-vault boundary: select and validate endpoints before resolving a
  credential, and never inherit an implicit US target.
- The [Python wrapper][sdk-client] accepts values in-process, explicitly configured
  API/identity URLs, organization-scoped project and secret-identifier lists,
  exact-ID gets, create, and update. Updates supply the full desired fields;
  preserve notes/project membership rather than replacing them with defaults.
- Published [PyPI metadata][pypi] lists `cp39-abi3` wheels for Linux glibc x86-64
  and aarch64, macOS x86-64 and arm64, and Windows amd64. Stable-ABI tags cover
  conventional CPython 3.10–3.14; this is metadata evidence, not an executed
  installation matrix. The runtime dependency is `python-dateutil>=2.6.0`.
  There is no listed sdist or musl wheel for this release.
- Wheel schemas expose project `organizationId`, identifier `projectIds`, and
  retrieved secret `projectId`. Identifier listing returns names/IDs, not values;
  filter to the selected project before retrieving declared IDs. The Python
  wrapper exposes no pagination parameter. Completeness of underlying listing
  and wrong-organization behavior cannot be delegated to the official CLI.
- A credential-free TLS probe ran the installed `bws 2.1.0` against a local
  synthetic server using the SDK's published test vector. The client exchanged
  the synthetic machine credential at the selected identity endpoint, took the
  organization UUID from the returned token, and issued exactly one authenticated
  `GET /api/organizations/<uuid>/projects`. When that response contained an empty
  `data` array plus a nonempty `continuationToken`, `bws` exited `0`, printed an
  empty list, and made no second request. The bundled SDK list path likewise
  discards the response continuation token. Native `bws project list` accepts no
  expected-organization or continuation input. It therefore cannot prove complete
  name discovery or independently bind an empty result to configured organization
  metadata. Reusing bws profile endpoints remains viable; using the CLI as the
  discovery implementation does not.

### Official GitHub action

The selected candidate is
`bitwarden/sm-action@1238aae8fc64b212641190a9227c8a734ab1a793`, the verified commit
behind [v3.0.1][action-release]. The [help page][action-help] still demonstrates
`@v2`; prefer the reviewed source, not that moving example.

- [action.yml][action-yml] uses Node 24. Inputs include `access_token`, per-entry
  `secrets` mappings, `cloud_region`, base/API/identity URLs, and `set_env`
  (default `true`). Runner compatibility must be checked for the consuming
  runner; this review has not executed GitHub's runner.
- [Configuration][action-config] maps explicit `eu`/`us` to their cloud endpoints.
  An absent or unrecognized region with no URLs falls back to US. Generated
  integration must reject invalid selectors before this action and always supply
  the intended region or validated endpoint pair.
- [Retrieval][action-main] consumes `UUID > NAME` mappings, not a project ID.
  Duplicate UUIDs overwrite the prior alias with a warning; variable names are
  not validated here. Generation must validate names and uniqueness. Runtime
  retrieval iterates returned entries without its own exact-result-set check.
- `set_secret` masks first, conditionally writes `GITHUB_ENV`, and always writes
  `GITHUB_OUTPUT`. `set_env: false` therefore permits step-output-to-consumer-env
  wiring; `GITHUB_ENV` is job-wide for subsequent steps, not step-scoped.
- [File commands][action-ci] use randomized delimiters and raw string content;
  masking escapes percent/CR/LF. Source supports empty/multiline serialization,
  but that does not prove server storage or GitHub expression execution. Masking
  is not protection against an untrusted consumer or arbitrary transformations.
- **Pinning limit:** the [Node launcher][action-launcher] downloads a release
  binary selected by `version.json` (or `SM_ACTION_VERSION`) without a digest
  check, and can build with Cargo on download failure. A full action commit SHA
  does not make that executable transitively immutable. The operator explicitly
  accepted this residual upstream release-asset trust for the pinned candidate;
  generated diagnostics must not claim transitive binary immutability.

### Empty values and evidence limits

[GitHub Secrets documentation][github-secrets] and [variable contexts][github-contexts]
state that unset references evaluate to an empty string. A presence/type listing
cannot prove Secret contents, and a runtime expression alone cannot distinguish
missing from stored-empty. No live test of storing empty GitHub or Bitwarden
values was performed.

Proposed conservative boundary: preserve present-empty for local/BWS operations
only if the official-client probe and later live canary establish support; reject
empty selected values for reversible Actions publication/delivery. Require every
selected CI consumer value to be nonempty before execution, without per-key
provider fallback. This prevents missing outputs being silently treated as valid
empty configuration. Do not infer requiredness from example values.

## Proposed integration checklist

These approved choices define the integration boundary. Current implemented
behavior belongs to the affected CAPs and operator README; later phases remain
change-record scope rather than claims in this review package.

| Topic | Proposed boundary |
| --- | --- |
| CLI names | Separate `gh-vault bitwarden` group: `connection set/list`, `credential set/remove`, `project resolve`, `env restore/upload`, `actions publish/generate`. No existing command silently changes backend. |
| Connection | Every remote operation requires `--connection NAME`. Operator metadata binds a named bws profile/config path, validated resolved HTTPS endpoint pair, and expected organization UUID. Endpoint drift requires explicit rebinding before credential access. No repository TOML or region probing. |
| Credential selection | Explicit `--credential-source env` (default) or `vault`; missing/empty selected source fails, never falls back. Environment source reads only `BWS_ACCESS_TOKEN`; vault source uses a separate typed entry below `gh-vault/bitwarden/`, never a GitHub profile. Storage accepts hidden prompt/stdin, not argv. |
| Conflicts and state | Reject conflicting ambient bws endpoint/profile overrides. The private local-path module receives both endpoints and the expected organization explicitly, with no persistent auth state file; `bws` is not the runtime discovery client. Keep GitHub injection and active-profile selection untouched. |
| Discovery | Validate Git origin and require `--project-id` in the initial scope. Validate UUID spelling before parsing. Require an accessible project in the expected organization and verify IDs/org/project membership on every response. No name listing or project creation. Name derivation remains excluded until the official client exposes complete paging. |
| Named dotenv profiles | `--env-file .env.NAME` requires an explicit project selector. Neither filename nor directive selects a GitHub Environment. |
| Required/default/optional | All managed template keys required. No managed optional/default syntax in initial scope; missing fails rather than substituting examples. Local-only assignments stay inactive in restored output; comments and directives remain. |
| Profile references | Reject `# gh-vault: secret PROFILE` in BWS-managed declarations before token/file/network access. Never upload its empty placeholder or automatically copy the GitHub PAT. |
| Portable values | Resolve only explicit source `@file:` / `@base64:` markers on upload. Store decoded UTF-8 content, not source-machine paths. Restore through an unambiguous representation, including literal marker-prefixed values and trailing newlines; reject NUL. |
| Restore | Validate all selected data before writing; no overwrite without `--force`. Adjacent private-from-creation file and atomic replacement; retain old target on failure. No implicit local archive fallback. |
| Upload authorization | Default preview; `--apply` authorizes creates, `--apply --update-existing` also authorizes updates. Preflight all duplicates/type/input constraints. Read back exact ID/key/org/project/value internally. Stop on failure and report partial completion, not a transaction; no automatic retry of uncertain creates or deletion. |
| Publication | Default preview; explicit `--apply`, destination `--repo`, and optional `--github-environment`. Reject type drift/empty values before writes; stdin-only gh writes with value-free errors. Read back Variables exactly and Secret names/types only. Never flip the selector or prune. |
| Standby evidence | Restrictive operator metadata records destination, project/entry IDs, remote revisions, publication time and per-key result, never values/hashes. It is not proof of secret equality, credential validity, or rollback readiness. Explicit refresh plus a safe probe remains required. |
| Mapping destination | Generated literal `secrets:` workflow input, not a remote configuration variable. Retain the declared per-job key subset alongside the generated block for reproducible offline checks; derive UUIDs from discovery, never hand-edit a second inventory. |
| Provider selector | Repository `CONFIG_SOURCE`: unset/empty means `github`; other than exact `github`/`bitwarden` fails. Manual input `config_source` chooses `repository`, `github`, or `bitwarden`; scheduled runs use repository selection. Resolve once per job. |
| Delivery | Explicit provider branches, `set_env: false`, consumer step env/input bindings, and a nonempty required-output check. No `A && secret || other_provider` value selection, secret cross-job outputs, shell interpolation, or silent fallback. Aliases reuse a validated fetched output. |
| Bootstrap and trust | Separate read-only project-restricted CI token in GitHub Secrets; retain native GitHub token, region, selector, and pre-job runner/container/deployment controls. Preserve Environment approvals; reject untrusted PR execution. GitHub rollback never fetches BWS first. |

## Reproducible baseline finding

A synthetic call to current `format_dotenv_value` followed by `_decode` passed
for empty, Unicode, carriage-return, and multiline cases, but changed the literal
`@base64:YWJj` to `abc` and attempted a file read for literal
`@file:missing-synthetic`. The owner ranges this in Phase 3. New recovery cannot
blindly reuse that formatter. Existing `actions.sync` also propagates child stderr
and does not read back writes; the owner ranges the new publication boundary in
Phase 5. Neither issue was patched during this contract-only phase.

## Evidence boundary

Public release metadata, pinned source, wheel contents, sanitized local CLI help,
the credential-free local TLS client probe, and the synthetic baseline formatter
probe were checked. No live credentials, Bitwarden/GitHub value writes, consuming
workflows, SDK install matrix, or completed official-action test run establish
runtime behavior. Phase 1 is complete because its contract decisions and local
verification gate are recorded; later phases must supply implementation and live
evidence. Synthetic probes and source inspection must never be reported as the
Phase 7 live canary.

[sdk-license]: https://github.com/bitwarden/sdk-sm/blob/0520690b9710af7a8b1e47aad776f002f369688f/languages/python/LICENSE
[root-license]: https://github.com/bitwarden/sdk-sm/blob/0520690b9710af7a8b1e47aad776f002f369688f/LICENSE
[sdk-client]: https://github.com/bitwarden/sdk-sm/blob/0520690b9710af7a8b1e47aad776f002f369688f/languages/python/bitwarden_sdk/bitwarden_client.py
[bws-secret]: https://github.com/bitwarden/sdk-sm/blob/0520690b9710af7a8b1e47aad776f002f369688f/crates/bws/src/command/secret.rs
[bws-config]: https://github.com/bitwarden/sdk-sm/blob/0520690b9710af7a8b1e47aad776f002f369688f/crates/bws/src/config.rs
[bws-selection]: https://github.com/bitwarden/sdk-sm/blob/0520690b9710af7a8b1e47aad776f002f369688f/crates/bws/src/main.rs
[pypi]: https://pypi.org/pypi/bitwarden-sdk/2.1.0/json
[action-release]: https://github.com/bitwarden/sm-action/releases/tag/v3.0.1
[action-help]: https://bitwarden.com/help/github-actions-integration/
[action-yml]: https://github.com/bitwarden/sm-action/blob/1238aae8fc64b212641190a9227c8a734ab1a793/action.yml
[action-config]: https://github.com/bitwarden/sm-action/blob/1238aae8fc64b212641190a9227c8a734ab1a793/src/config.rs
[action-main]: https://github.com/bitwarden/sm-action/blob/1238aae8fc64b212641190a9227c8a734ab1a793/src/main.rs
[action-ci]: https://github.com/bitwarden/sm-action/blob/1238aae8fc64b212641190a9227c8a734ab1a793/src/ci.rs
[action-launcher]: https://github.com/bitwarden/sm-action/blob/1238aae8fc64b212641190a9227c8a734ab1a793/index.js
[github-secrets]: https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-secrets
[github-contexts]: https://docs.github.com/en/actions/reference/workflows-and-actions/contexts
