# docs/

## Purpose

Own current architecture, security boundaries, release operations, capability evidence, and repository-tracked change progress.

## Ownership

- `docs/RELEASING.md` — PyPI trusted-publishing setup, tag-driven publishing
  contract, and local dry-run procedure.
- `architecture.md` — runtime boundaries, data flow, maintenance structure, and non-goals.
- `security.md` — secret/plaintext boundaries and external-service evidence limits.
- `design-decisions.md` — rationale for durable cross-cutting choices, not progress.
- `product/` — current capability contracts and executable evidence.
- `changes/` — active change progress, archived receipts, and optional review packages.

## Local Contracts

- `docs/RELEASING.md` is the source of truth for "what publishes when". README
  links to it; do not duplicate the checklist in README.
- The release contract is: PyPI publishes only when a `v*` tag is pushed, only
  from the `pypi` GitHub environment, and only when the tag (stripped of `v`)
  equals `gh_vault.__version__`. Any change to that contract must update both
  `docs/RELEASING.md` and `.github/workflows/publish.yml` together.
- CAPs describe current behavior; CHGs describe requested-change progress. Neither replaces architecture or security documentation.
- Read product and change child contracts before writing records or choosing visual artifact destinations. No CAP may use proposal artifacts as product evidence.
- Do not copy real tokens, environment values, password-store content, or operator metadata into documentation.

## Work Guidance

- Keep release docs operational: setup steps, commands, what does and does not
  trigger a publish. No historical breadcrumbs.
- Cross-reference owning docs instead of duplicating them.
- Ground every behavior claim in source and assertions, and distinguish mocks from live integration. Document limitations rather than changing application behavior to fit a claim.

## Verification

- Run `make verify` after record or contract changes and validate changed local Markdown links.
- Follow `RELEASING.md` for local package build/metadata checks; these do not prove remote OIDC publishing or environment settings.
- Keep architecture non-goals aligned with root DOX and security boundaries aligned with source.

## Child DOX Index

| Child | Owns | Read when editing… |
|---|---|---|
| `product/AGENTS.md` | Current capabilities and evidence | Product records or visual handoff |
| `changes/AGENTS.md` | Active progress, archive receipts, review packages | Change phases, dependencies, review ownership, or closure |

Parent: `../AGENTS.md`. Release automation: `../.github/AGENTS.md`.