# Record validator regressions

## Purpose

Prove the maintenance validator's structural and lifecycle checks independently of product behavior.

## Ownership

- `fixtures.mjs` creates disposable synthetic repositories.
- `records.test.mjs` checks capability records and evidence paths.
- `changes.test.mjs` checks CHG metadata, phase shape, and lifecycle placement.
- `artifacts.test.mjs` checks review ownership and canonical wireframe inventory.
- `evidence.test.mjs` checks Python evidence recognition without weakening other checks.
- `playbooks.test.mjs` checks local playbook/gate packaging and cited pytest names, not assertion semantics.

## Local Contracts

- All fixtures live in temporary directories and are removed after each test.
- Fixture CAPs, CHGs, source files, and visual artifacts are synthetic validator inputs, never gh-vault product records or evidence of application behavior.
- Keep the validator import relative to this repository; no sibling checkout or package installation is required.
- File-name recognition is not proof that a referenced test actually asserts a CAP claim; that remains review work.

## Work Guidance

Add positive and negative fixtures when changing an invariant. Preserve existing lifecycle, review-package, and visual-handoff regression coverage.

## Verification

Run `node --test "tests/records/*.test.mjs"` or `make test-records`, followed by `make records-check` against the live tree.

## Child DOX Index

No child DOX documents. Parent: `../AGENTS.md`. Validator owner: `../../scripts/AGENTS.md`.
