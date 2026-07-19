# docs/

## Purpose

Release workflow documentation and any other durable, repo-wide reference
material that does not fit under `src/`, `tests/`, or `assets/`.

## Ownership

- `docs/RELEASING.md` — PyPI trusted-publishing setup, tag-driven publishing
  contract, and local dry-run procedure.
- Future docs that document cross-cutting repo contracts belong here.

## Local Contracts

- `docs/RELEASING.md` is the source of truth for "what publishes when". README
  links to it; do not duplicate the checklist in README.
- The release contract is: PyPI publishes only when a `v*` tag is pushed, only
  from the `pypi` GitHub environment, and only when the tag (stripped of `v`)
  equals `gh_vault.__version__`. Any change to that contract must update both
  `docs/RELEASING.md` and `.github/workflows/publish.yml` together.

## Work Guidance

- Keep release docs operational: setup steps, commands, what does and does not
  trigger a publish. No historical breadcrumbs.
- Cross-reference owning docs instead of duplicating them.

## Verification

Empty until a check that exercises the release workflow exists (e.g. a
workflow run on a test tag, or a `twine check` step wired into CI).

## Child DOX Index

| Child | Owns | Read when editing… |
|---|---|---|
| `docs/RELEASING.md` | PyPI trusted-publishing setup, tag conventions, dry-run procedure | `.github/workflows/publish.yml`, PyPI environment, release tagging |