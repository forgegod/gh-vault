---
name: application-records
description: Use when a material change needs canonical CAP, CHG, decision records, and CAP-linked wireframes for primary human-facing surfaces.
version: 1.5.0
author: Hermes contributors
license: MIT
metadata:
  hermes:
    tags: [product, capability, change-records, documentation]
    related_skills: [capability-wireframes, phased-plan-design, phased-plan-execution, phased-plan-overview, phased-plan-refactoring]
---

# Application Records

## Overview

Keep three distinct truths: an external request explains why work is wanted; a
capability record (CAP) describes shipped behaviour; and an active change record
(CHG) tracks implementation progress. Code and executable tests remain the final
proof of behaviour.

This skill defines the portable canonical layout:

- `docs/product/capabilities/CAP-*.md` for current behaviour;
- `docs/changes/active/CHG-*.md` for active progress;
- `docs/changes/archive/CHG-*.md` for completed implementation receipts; and
- `docs/changes/reviews/CHG-<number>/` for optional review packages, never a second progress authority.

Projects adopting this skill use these names and paths. Their contributor
instructions supply product-specific policy, tests, and validation commands.

## When to Use

- A request adds, removes, fixes, or changes material user-visible behaviour.
- A permission, privacy, data-handling, or operator-visible outcome changes.
- An agent needs to create, resume, split, complete, or archive a CHG record.
- A durable choice must be classified as capability-local or cross-cutting.

Do not use for a refactor, formatting change, dependency update, or internal
hardening that preserves observable behaviour. Do not use a CAP or CHG to
replace architecture, privacy, security, or deployment documentation.

## Authoritative Surfaces

Read these before changing a record:

| Need | Read |
| --- | --- |
| Repository-wide obligations | The target repository's root contributor instructions and applicable child contracts. |
| Current capability contract | `docs/product/README.md` and affected `docs/product/capabilities/CAP-*.md`. |
| Change-progress lifecycle | `docs/changes/README.md` and affected `docs/changes/{active,archive}/CHG-*.md`. |
| Durable cross-cutting decision | `docs/architecture.md`, `docs/privacy.md`, `docs/design-decisions.md`, and equivalent local contracts. |

## Phase sequencing

For a material change, the active CHG is the execution plan. Use the packaged
phase skills instead of creating a private plan that duplicates CHG progress:

- `phased-plan-design` creates or reshapes the CHG phase table before work.
- `phased-plan-overview` finds active CHGs and identifies the selected record to
  resume without relying on commit recency or chat memory.
- `phased-plan-execution` runs one CHG phase, verifies its gate, and synchronizes
  its CAP/CHG evidence before the checkpoint.
- `phased-plan-refactoring` splits or resequences active CHGs only at verified
  boundaries while preserving one progress authority per request.

For a non-material refactor, use the adopting repository's ordinary planning
convention. Do not create CAP/CHG churn simply because the work has phases.

## Procedure

1. **Classify the request.**
   - If it is vague or blocked by unresolved decisions, use Wayfinder only to
     resolve the decision frontier. The tracker map remains discovery material.
   - If it changes material behaviour, identify affected CAP IDs and create or
     resume one CHG record before implementation. Use `phased-plan-design` for
     a new CHG or `phased-plan-overview` to select an existing one.
   - If it preserves observable behaviour, state that no CAP/CHG change is
     needed and proceed under the applicable implementation contract.

2. **Create or resume the CHG authority.**
   - Follow `docs/changes/README.md`'s canonical shape and lifecycle.
   - Link the external ticket or write `Direct operator request: <verbatim request>`
     when no ticket exists. Never invent a ticket ID.
   - Start with executable phase gates. `phased-plan-execution` sets one phase
     to `in-progress` when it begins that phase.
   - For material work, the tracked CHG is the execution plan. Do not create a
     competing private plan carrying the same progress.
   - Before choosing a visual destination, read both product and change DOX and
     the wireframe child if present. Keep pending proposal assets and design notes
     in `docs/changes/reviews/CHG-<number>/`, not beside active/archive records.
     Link its `README.md` from the owner; the README declares `**Status:** review-only`
     and links the artifacts. Do not allocate a future CAP ID or add a proposal
     to the product manifest. Follow `docs/changes/README.md` for package lifecycle.

3. **Make current behaviour explicit.**
   - Add or amend the affected CAP in the same vertical slice as implementation
     and behaviour tests.
   - State only present-tense, falsifiable outcomes. Link architecture and
     privacy/security contracts instead of copying their rules.
   - If code/tests contradict the CAP, fix the code or CAP before
     completion; do not leave an ambiguous claim.
   - Every CAP declares `**Primary surface:** human` or `none`. For new or existing
     human-facing CAPs, load `capability-wireframes` and update the canonical
     generator, regenerate HTML, render PNG, and synchronize manifest/index/CAP
     links in the same slice as the changed interaction and behavior tests.
     Review packages are never promoted by simply moving their files.

4. **Place decisions correctly.**
   - Record a capability-local rule in its CAP only when it changes how the
     implemented behaviour must be understood.
   - Record irreversible or cross-cutting runtime, authentication,
     authorization, persistence, privacy, or observability choices in
     `docs/design-decisions.md` and update the live contracts in the same change.
   - Leave short-lived implementation reasoning in the CHG or Git history.

5. **Prove and record progress.**
   - Run the current phase through `phased-plan-execution`. Mark it done only
     after its gate passes.
   - Run the project's record-validation integration plus affected tests and the
     required workspace/release gate for cross-boundary work.
   - Update the CHG before the implementation commit so a new session can resume
     from repository truth.

6. **Close the change.**
   - Confirm affected CAPs describe merged behaviour and link executable tests.
   - Complete the visual handoff gate: current canonical HTML/PNG for affected
     human-facing CAPs, honest `none` declarations elsewhere, and generation,
     rendering, and visual inspection evidence in the CHG. Inventory checks alone
     do not establish render freshness or correct surface classification.
   - Retain review packages at their same paths as frozen review-only receipts
     for done or cancelled owners. Repair links on archive; remove packages when
     their owners are removed. Cancellation does not claim implementation.
   - Run the project's full integration gate.
   - Set the CHG done, move it from `active/` to `archive/`, and retain it as an
     implementation receipt, not a feature specification. Return to
     `phased-plan-overview` rather than guessing the next active change.

## Common Pitfalls

1. **Tracker-shaped truth.** A ticket marked complete is not proof of merged or
   deployed behaviour. Link it from a CHG; do not copy its status into a CAP.
2. **Plan-shaped truth.** A completed phase table explains work history. It does
   not describe current behaviour; the CAP must carry that outcome.
3. **CAP churn.** Do not update a CAP because implementation details changed.
   Update it only when a material outcome changed.
4. **Unproved claims.** A CAP without behaviour-test evidence is a coverage
   gap, not an implemented proof. Add focused coverage or state the bounded
   gap precisely before calling the record complete.
5. **Decision inflation.** Do not create a decision record for local naming or
   code-layout choices. Reserve it for durable cross-cutting forks.
6. **Premature promotion.** Do not move a CHG review screenshot, Pencil file,
   or planned screen into `docs/product/wireframes/`. Regenerate a CAP-linked
   HTML/PNG pair only when its product surface and evidence exist.
7. **Parallel progress.** Do not mirror a CHG in a profile-private plan, a
   temporary note, or a tracker checklist. Add a prerequisite phase or use
   `phased-plan-refactoring` to make parallel scope explicit.

## Verification Checklist

- [ ] Every material changed behaviour has an affected CAP and behaviour-test evidence.
- [ ] Every qualifying primary human-facing surface has a current CAP-linked
      HTML and PNG wireframe.
- [ ] Review packages have an owning CHG, a linked review-only README, and valid
      artifact links; no CAP or product manifest references their files.
- [ ] Every active material request has exactly one CHG progress authority.
- [ ] Every CHG references its source request and valid CAP IDs.
- [ ] The project's record-validation integration exits 0.
- [ ] The active phase gate and required workspace checks pass.
- [ ] Completed CHGs are in `archive/`; active CHGs are not marked done.
