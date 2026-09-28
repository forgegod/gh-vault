# DOX framework

- DOX is highly performant AGENTS.md hierarchy installed here
- Agent must follow DOX instructions across any edits

## Core Contract

- AGENTS.md files are binding work contracts for their subtrees
- Work products, source materials, instructions, records, assets, and durable docs must stay understandable from the nearest applicable AGENTS.md plus every parent AGENTS.md above it

## Read Before Editing

1. Read the root AGENTS.md
2. Identify every file or folder you expect to touch
3. Walk from the repository root to each target path
4. Read every AGENTS.md found along each route
5. If a parent AGENTS.md lists a child AGENTS.md whose scope contains the path, read that child and continue from there
6. Use the nearest AGENTS.md as the local contract and parent docs for repo-wide rules
7. If docs conflict, the closer doc controls local work details, but no child doc may weaken DOX

Do not rely on memory. Re-read the applicable DOX chain in the current session before editing.

## Update After Editing

Every meaningful change requires a DOX pass before the task is done.

Update the closest owning AGENTS.md when a change affects:

- purpose, scope, ownership, or responsibilities
- durable structure, contracts, workflows, or operating rules
- required inputs, outputs, permissions, constraints, side effects, or artifacts
- user preferences about behavior, communication, process, organization, or quality
- AGENTS.md creation, deletion, move, rename, or index contents

Update parent docs when parent-level structure, ownership, workflow, or child index changes. Update child docs when parent changes alter local rules. Remove stale or contradictory text immediately. Small edits that do not change behavior or contracts may leave docs unchanged, but the DOX pass still must happen.

## Hierarchy

- Root AGENTS.md is the DOX rail: project-wide instructions, global preferences, durable workflow rules, and the top-level Child DOX Index
- Child AGENTS.md files own domain-specific instructions and their own Child DOX Index
- Each parent explains what its direct children cover and what stays owned by the parent
- The closer a doc is to the work, the more specific and practical it must be

## Child Doc Shape

- Create a child AGENTS.md when a folder becomes a durable boundary with its own purpose, rules, responsibilities, workflow, materials, or quality standards
- Work Guidance must reflect the current standards of the project or user instructions; if there are no specific standards or instructions yet, leave it empty
- Verification must reflect an existing check; if no verification framework exists yet, leave it empty and update it when one exists

Default section order:
- Purpose
- Ownership
- Local Contracts
- Work Guidance
- Verification
- Child DOX Index

## Style

- Keep docs concise, current, and operational
- Document stable contracts, not diary entries
- Put broad rules in parent docs and concrete details in child docs
- Prefer direct bullets with explicit names
- Do not duplicate rules across many files unless each scope needs a local version
- Delete stale notes instead of explaining history
- Trim obvious statements, repeated rules, misplaced detail, and warnings for risks that no longer exist

## Closeout

1. Re-check changed paths against the DOX chain
2. Update nearest owning docs and any affected parents or children
3. Refresh every affected Child DOX Index
4. Remove stale or contradictory text
5. Run existing verification when relevant
6. Report any docs intentionally left unchanged and why

## User Preferences

- Documentation describes the current project state only; git carries the timeline and retired designs.
- Keep documentation concise and cross-reference owning docs rather than duplicating them.
- Private adapter installation and update recipes belong to the `gh-vault-bws` README. Public docs describe the adapter interface/location and refer to that setup; ordinary usage uses one `gh-vault` command on `PATH`.
- Use explicit markers such as `@file:` rather than inferring file-path intent.
- Use synthetic fixtures, never operator credentials or real project environments, for verification.
- Local-commit checks are offline. Remote `secret sync --dry-run` / `secret check` and the matching variable commands belong to pre-push review when their declarations change, not to ordinary local tests.
- Do not commit, tag, publish, or push without an explicit operator request.

## Project intent

gh-vault is a Python CLI for named GitHub tokens, typed project environment archives, GitHub Actions values, local workflow validation, and explicitly configured Bitwarden project access, on-demand token-profile bindings, dotenv recovery, previewed upload, and reviewed GitHub standby publication through an operator-held local adapter. It delegates local encryption to `pass`/GPG and remote Actions operations to `gh`. The PyPI distribution is `forgegod-gh-vault`; its installed console command and argparse product name are `gh-vault`. `python -m gh_vault` is the module entry point.

## Architectural decisions

- **Agent harness protected by tirith.sh.** Reading passwords or access tokens is prohibited. Extract variables from `.env` / config files without relaying their values; use environment variables by importing them for Bash execution. `***` in output is a tirith redaction marker, not a literal value — never "fix" it to a variable ref.
- **Explicit token-profile sources.** A profile is either a local token in `pass` below `gh-vault/` or an on-demand binding to one exact Bitwarden project entry. Binding metadata is value-free and pins the connection, project ID, entry ID, key, adapter path, and non-fallback credential source; it never caches or mirrors the GitHub token. Explicit `# gh-vault: variable` values may use the restrictive XDG archive store; local and secret values must never enter it or metadata indexes. Explicit Bitwarden upload writes managed values only to the selected remote project through the local adapter.
- **Local-only Bitwarden adapter.** The published package may store value-free Bitwarden connection metadata and load the `gh_vault_bws` interface from the operator-managed `${XDG_DATA_HOME:-~/.local/share}/gh-vault/adapters/gh-vault-bws` checkout or an explicit `--adapter-path`. It validates explicit project resolution plus exact-name environment inspection, read, and write results before use. The adapter implementation and SDK dependency stay in the private checkout; gh-vault never fetches, installs, updates, vendors, or documents SDK call sequences. Bitwarden access tokens come only from `BWS_ACCESS_TOKEN` or separate `pass` entries below `gh-vault/bitwarden/`.
- **Explicit GitHub Environment scope.** Remote Actions values use repository scope by default; `--github-environment NAME` is the only Environment selector. A local `.env.<profile>` or a typed directive must never infer a remote Environment. Environment-targeted operations preflight the existing target and keep comparison, type migration, and prune within that scope.
- **Reviewed Bitwarden standby publication.** `bitwarden actions publish` reads exact declared values from one explicit Bitwarden project and targets an explicit GitHub repository plus optional Environment. Preview is the default; `--apply` performs create/update only, rejects empty values and type drift, verifies Variables by value and Secrets by name/type, suppresses child diagnostics, and records value-free result metadata. Publication never prunes, migrates types, flips a workflow selector, or proves rollback readiness.
- **Generated dual-provider workflow boundary.** `bitwarden actions generate` derives one explicit job subset from typed declarations plus inspected Bitwarden UUIDs and emits separate GitHub and Bitwarden consumer branches guarded by one validated provider selector. Repository `CONFIG_SOURCE` defaults to `github`; manual dispatch may explicitly choose `repository`, `github`, or `bitwarden`. There is no per-key provider fallback, automatic selector mutation, or runtime Bitwarden access on the GitHub branch.
- **Intentional credential output boundary.** The explicit `output` command and Git's exact `git-credential get` response may emit a token. Ordinary status, listing, diagnostics, and metadata must not. See `docs/security.md` for plaintext process/file boundaries.
- **Unlock lifetime belongs to GPG.** `gh-vault` delegates passphrase caching to the user-level `gpg-agent`; it does not own or override the cache timeout. User documentation shows both `default-cache-ttl` and `max-cache-ttl` so an operator can choose the unlock duration.
- **Record authority.** `docs/product/capabilities/CAP-*.md` describes current material behavior at this revision, backed by implementation and executable tests. Code and tests decide conflicts; documentation must be reconciled in the same change.
- **Change progress.** `docs/changes/active/CHG-*.md` is the single repository authority for progress on a material request. Tickets explain requests; archived CHGs are receipts, not current product contracts. Private plans are not resumable project authority.
- **Material slices.** A material behavior change updates the affected CAP, tests, and active CHG together. Behavior-preserving refactors do not create record churn. Completed changes archive only after their integration gates pass and CAPs describe the resulting behavior.
- **Visual lifecycle.** Every CAP declares `Primary surface: human` or `none`. The command-line/protocol surfaces have no primary visual screen. A future primary screen or visual interaction requires canonical generated HTML/PNG under `docs/product/wireframes/`; proposals belong to CHG-owned `docs/changes/reviews/CHG-<number>/` packages.
- **Tooling boundary.** Python remains the product runtime. Node.js 22+ is development-only tooling for the dependency-free record validator and its synthetic regression tests; no Node package manager or application dependency is required.

## Architectural non-goals

- No hosted service, graphical application, application database, or general secrets-provider framework.
- No PAT issuance/rotation service and no control over GPG agent cache lifetime.
- No shell evaluation of dotenv data, implicit legacy-archive migration, or automatic secret-to-public reclassification.
- No GitHub Environment creation, deletion, protection-rule, reviewer, wait-timer, or deployment-policy management.
- No live GitHub, GPG, password-store, or release operations in the credential-free test gate.
- No duplicate progress system or fabricated historical change receipts.

## Architecture change control

Stop for explicit approval before changing an architectural decision or non-goal. An approved change updates this rail, `docs/architecture.md`, affected child DOX and behavior tests, and `docs/design-decisions.md` for irreversible or cross-cutting forks. Read `docs/security.md` for secret-handling changes.

## Product and change records

- Read `docs/product/README.md` and `docs/changes/README.md` before creating, editing, splitting, or closing records.
- Read both product/change child DOX and the wireframe child if present before choosing visual artifact paths. Review packages never replace canonical product visuals or behavior tests.
- Use the repository-local `skills/software-development/application-records/SKILL.md` and matching `phased-plan-*` family for material work. Read these files directly if an installed skill of the same name uses a different lifecycle. Their execution aids cannot override DOX or authorize commits.

## Workspace verification

- `make verify` runs record validation, Node validator regressions, and the offline Python suite.
- `make records-check` runs `node scripts/check-product-records.mjs`.
- `make test` runs `node --test "tests/records/*.test.mjs"` and `uv run --no-project --with pytest python -m pytest` without changing the application environment or lockfile.
- `.github/workflows/ci.yml` runs the same gate on pushes and pull requests. Tag-driven publishing remains separate under `docs/RELEASING.md`.
- Record checks prove structure, links, and lifecycle, not truth of CAP claims, live service behavior, visual freshness, or approval. Review those boundaries explicitly.

## Codebase Knowledge Graph (codebase-memory-mcp)

Prefer the indexed graph for structural discovery and call relationships. Verify its coverage before trusting results; use source searches for literals, non-code files, unavailable or incomplete graph results. Actual source and assertions remain authoritative.

## Child DOX Index

| Child | Owns | Read when editing… |
|---|---|---|
| `assets/AGENTS.md` | Brand identity, deterministic asset generation, vector sources, raster renders, and bundled font | `assets/**`, logo geometry, palette, typography, or social-preview copy |
| `src/gh_vault/AGENTS.md` | Production Python package, CLI behavior, secret backend, environment archives, and metadata persistence | `src/gh_vault/**`, console command behavior, storage, archive, or security contracts |
| `tests/AGENTS.md` | Pytest fixtures and executable CLI/store contracts | `tests/**`, test conventions, or verification coverage |
| `docs/AGENTS.md` | Architecture, security, release documentation, product and change records | `docs/**`, current behavior, evidence, or change progress |
| `scripts/AGENTS.md` | Dependency-free product-record validator | `scripts/**`, record validation rules |
| `.github/AGENTS.md` | Credential-free CI and tag-driven publishing | `.github/**`, quality gates or publishing |
| `skills/AGENTS.md` | Repository-local CAP/CHG and visual-handoff playbooks | `skills/**`, agent workflow packaging |

Root-owned artifacts:

- `README.md` — user-facing requirements, installation, command usage, security model, and release workflow.
- `pyproject.toml` — package metadata, dynamic version (`gh_vault.__version__`), PyPI license/classifiers/URLs, console entry points, source layout, and pytest configuration.
- `.gitignore` — generated and local-only artifacts excluded from version control.
- `LICENSE` — MIT license terms (mode `0644`; bundled into sdist and wheel).
- `Makefile` — maintenance record and test gates; no product build-system replacement.
