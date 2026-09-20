---
name: phased-plan-refactoring
description: Use when splitting or resequencing active CAP/CHG work while preserving one repository-tracked progress authority per material request.
version: 1.1.0
author: AI Software Blueprint
license: MIT
metadata:
  hermes:
    tags: [planning, refactoring, product, capability, change-records]
    related_skills: [application-records, phased-plan-design, phased-plan-overview]
---

# Phased Plan Refactoring

## Purpose

Change the structure of active material work without losing its progress truth.
A CHG may be revised or split only at a verified boundary. The result must leave
one progress authority for each material request and a clear path back to
`phased-plan-execution`.

## When to use

- A newly discovered prerequisite must precede the current CHG phase.
- One CHG contains independently verifiable material requests that need separate
  ownership or sequencing.
- An explicit dependency changes the safe order of active work.
- A phase is too broad to resume safely in a fresh agent session.

Do not use this skill to execute implementation, mark an unverified phase done,
or create a second progress record just to preserve a personal todo list.

## Procedure

1. Read the applicable DOX chain, `docs/changes/README.md`, affected CAPs, all
   CHGs being changed, and inbound references from the change index or documents.
   Re-check repository status before touching records.
2. Build the actual dependency picture from phase order, explicit prerequisites,
   shared CAP ownership, and verification gates. Do not infer dependency from
   filename dates or topic similarity.
3. Choose a restart-safe cut only after a phase whose gate has passed. Preserve
   every moved phase's goal, steps, gate, and recorded evidence exactly once.
4. For a split, create a new active CHG with its own stable ID, direct external
   request, impacted CAP IDs, baseline, canonical phase table, and an explicit
   dependency on the predecessor record or verified phase. Remove moved rows and
   prose from the source CHG; never duplicate live phase rows.
5. Update the source CHG, new CHG, change index, and any affected CAP links in
   the same change. Keep each record's status and phase table internally valid.
   Assign each review package exactly one owning CHG. If ownership changes, move
   it to `docs/changes/reviews/CHG-<new-number>/` and repair README/owner/inbound
   links; do not duplicate mutable progress or orphan the original package.
6. Run the record validator and required document checks. Use
   `phased-plan-overview` to confirm that the next resumable record is clear;
   execute nothing until `phased-plan-execution` is invoked for that record.

## Invariants

- Exactly one active CHG is the one progress authority for one material request.
- A split preserves the direct request and CAP impact of each resulting request;
  it never turns an archive receipt into an active plan.
- Dependencies are explicit and minimal. Do not repeat transitive dependencies
  in every record.
- Do not split an atomic behaviour/test/CAP slice merely to make files shorter.
- Use a new CHG ID for a genuinely independent material request. Keep an existing
  ID when only its internal phase order changes.

## Verification

Before finishing, confirm every active CHG has valid lifecycle status, exactly
one or zero in-progress phases as its status permits, valid impacted CAP IDs,
resolvable links, and no duplicated or dropped active phase. The record check
and project documentation checks must pass before any execution resumes.
