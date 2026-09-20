---
name: phased-plan-design
description: Use when designing a phased plan and a material change must use a CAP/CHG record as its progress authority.
version: 1.1.0
author: AI Software Blueprint
license: MIT
metadata:
  hermes:
    tags: [planning, product, capability, change-records]
    related_skills: [application-records, phased-plan-execution]
---

# Phased Plan Design

## Purpose

Design restart-safe execution phases with explicit verification. For a material
behaviour change in a repository using CAP/CHG records, the active CHG is the
plan. Do not create a private, profile-local, or parallel plan that duplicates
its phase status.

## When to use

- A material request needs a new or revised `docs/changes/active/CHG-*.md`.
- An active CHG needs executable phases before implementation starts.
- A non-material change is complex enough to need a durable project plan.

Use `application-records` first to classify the request. This skill designs the
phase structure; `phased-plan-execution` performs a selected phase.

## Material-change procedure

1. Read the root and applicable child `AGENTS.md` files, `docs/product/README.md`,
   `docs/changes/README.md`, affected CAPs, and active CHGs.
2. Name the direct request verbatim and identify affected CAP IDs. If the desired
   outcome is not yet clear, resolve that decision before creating a CHG.
3. Create one active CHG using the repository's documented shape. Start it as
   `planned` with every phase `pending`; do not mark a phase `in-progress` until
   execution begins.
4. Make each phase a restart-safe vertical slice. A row needs a concrete result,
   an owned file or behaviour boundary, and an executable verification gate.
   For a changed primary visual surface, define the visual handoff: affected new
   or existing CAPs, canonical generator and rendering commands, HTML/PNG/CAP
   link updates, and behavior tests. Read both product/change DOX before choosing
   artifact paths. Put proposals in the owning CHG review package, not in the
   product inventory or beside the CHG record.
5. Include a final integration phase that confirms the CAP states current
   behaviour, the record check passes, affected tests pass, and the project gate
   passes. Its visual handoff gate confirms current canonical visuals for human
   CAPs (honest `Primary surface: none` elsewhere) and stable-path retention of
   review packages. Only that phase may archive the CHG.
6. Hand the CHG path to `phased-plan-execution`.

Use this phase-table shape:

```markdown
| # | Phase | Status | Verification gate |
| --- | --- | --- | --- |
| 1 | Specify behaviour and evidence | pending | CAP and focused test change reviewed |
| 2 | Implement the vertical slice | pending | Targeted test command exits 0 |
| 3 | Integrate current-state records | pending | `make verify` exits 0 |
```

For every phase section, state an observable goal, exact steps, and the same
verification gate named in the table. Keep exactly one phase `in-progress` while
executing. Record `done (<evidence>)` only after that gate passes.

## Non-material plans

For refactors or operational work that does not change observable behaviour,
use the adopting repository's durable plan location and conventions. Name the
scope, phases, and gates, but do not manufacture CAP or CHG records. If the work
later changes a material outcome, stop and create or resume an active CHG before
implementation.

## Boundaries

- A CHG describes progress; a CAP describes current behaviour. Neither replaces
  architecture, security, privacy, or deployment contracts.
- Do not make a phase a vague task such as "finish implementation". The gate
  must be a command or an inspectable repository state.
- Do not use a phase table to schedule unrelated later ideas. Split them through
  `phased-plan-refactoring` or leave them out of the active request.
- A visual primary surface also follows `capability-wireframes` in the phase that
  implements its CAP.

## Verification

Before handing off, verify that the CHG has the required metadata, valid CAP IDs,
a canonical phase table, a numbered section for every row, one executable gate
per row, and no competing plan with the same progress. Run the repository record
validator after creating or amending the record.
