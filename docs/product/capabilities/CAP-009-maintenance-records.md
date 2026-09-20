# CAP-009 — Maintenance records and quality gates

**Status:** implemented
**Primary surface:** none

## Purpose

Keep current capability contracts, material implementation progress, executable
evidence, and optional agent procedures coherent without changing the Python
application's runtime dependencies.

## Behaviour

- `make records-check` validates CAP/CHG names, IDs, required fields/sections,
  lifecycle placement, request/baseline metadata, phase-table shape and
  in-progress count, and referenced paths. Invalid records produce located errors and a nonzero process result.
- Implemented/partial CAPs require implementation and behavior-test file
  references. Python evidence uses pytest naming (`test_*.py` or `*_test.py`);
  existing JS/TS spec/test evidence remains accepted. An arbitrary Python helper
  is not test evidence. Validation checks paths/naming, not assertion semantics.
- Human-surface CAPs require canonical HTML/PNG inventory; `none` CAPs do not.
  Review packages require a CHG owner, review-only README, and artifact links;
  they cannot substitute for product evidence or become CAP dependencies.
- `make verify` runs the live record check, offline Python suite, and Node
  validator/package regressions. The uv runner uses `--no-project` to avoid
  rewriting the project lockfile. Branch/PR CI invokes the same gate with
  read-only permissions; the tag-publish workflow remains separate.
- Six indexed repository-local playbooks cover record classification, canonical
  visuals, and phase design/execution/overview/restructuring. Package tests verify
  their inventory and gate wiring, not that an agent will follow them. The
  repository test also verifies named pytest citations against referenced files.

## Rules and boundaries

- No application GUI, database, Node package manager, or new Python runtime
  dependency is introduced. The developer gate needs Node, uv, and make.
- The validator does not execute evidence tests, verify replacement-link symmetry,
  establish truthful claims,
  classify surfaces, inspect PNG freshness, approve designs, or prove review
  freezing. Actual test execution and review remain separate gates.
- No initializer, blueprint proof CAP/CHG, foreign project data, or private
  progress system is required. No live credential use is part of the gate.
- Local test success does not claim a remote CI run or successful release.

## Implementation

- `scripts/check-product-records.mjs` — validateRecords and CLI.
- `Makefile` and `.github/workflows/ci.yml` — local and CI gates.
- `skills/software-development/AGENTS.md` — playbook inventory.

## Verification

- `make verify` runs the complete local gate.
- `tests/records/evidence.test.mjs` — pytest prefix/suffix/nested paths,
  missing tests, helpers/JS-style Python filenames rejected as evidence, and
  capability-status enforcement with Python evidence.
- `tests/records/records.test.mjs` — valid records, required sections/status,
  implementation/test references, duplicate CAP IDs, index links, and local links.
- `tests/records/changes.test.mjs` — active/archive status placement, phase
  counts/shape, unknown CAP impacts, and required request metadata.
- `tests/records/artifacts.test.mjs` — required
  canonical inventory, orphan reviews, declaration/ownership/artifact links,
  deleted owners, and forbidden CAP-to-review evidence.
- `tests/records/playbooks.test.mjs` — indexed
  playbook family, runtime/gate separation, and actual pytest citation names.
