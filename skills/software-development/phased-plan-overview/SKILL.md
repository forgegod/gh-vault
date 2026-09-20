---
name: phased-plan-overview
description: Use when inspecting active CAP/CHG-backed work and selecting a repository-tracked change record to resume, inspect, or close.
version: 1.0.0
author: AI Software Blueprint
license: MIT
metadata:
  hermes:
    tags: [planning, overview, product, change-records]
    related_skills: [application-records, phased-plan-execution, phased-plan-refactoring]
---

# Phased Plan Overview

## Purpose

Provide a restart-safe view of material work from repository truth. Active
`docs/changes/active/CHG-*.md` records—not chat history, commit recency, tracker
status, or private plans—state what can be resumed.

## Procedure

1. Read the applicable `AGENTS.md` chain and `docs/changes/README.md`.
2. Enumerate `docs/changes/active/CHG-*.md` and read each record's identity,
   status, external request, impacts, phase table, and any explicit dependency.
3. For every active CHG, report: status, affected CAPs, the one in-progress phase
   or first pending phase, its verification gate, and any explicit blocker.
4. Validate obvious drift before acting: an active record is not `done`, an
   in-progress record has exactly one in-progress phase, and named CAPs exist.
   Use the repository record validator for structural confirmation.
5. Resume only the CHG chosen by the operator or unambiguously identified by an
   explicit dependency/order rule. Hand its path to `phased-plan-execution`.
6. Inspect a blocked or ambiguous record without changing it. If no active CHG
   exists, report that no material work is scheduled; do not synthesize work from
   archives or old commits.

## Selection rules

- An explicit dependency or an existing in-progress phase wins over filename,
  modification time, creation date, and ticket priority.
- If several independent CHGs are pending and the repository does not define a
  priority rule, present them as choices. Do not invent an order.
- A completed record belongs in `docs/changes/archive/`. It can be inspected as a
  receipt but cannot be resumed as active progress.
- A material request with no active CHG routes to `application-records` and then
  `phased-plan-design`; a refactor with no material outcome does not.

## Verification

The overview is correct when a fresh agent can identify the selected CHG, its
next phase, the phase gate, affected CAPs, and any blocker without relying on
memory. It makes no source or status change until `phased-plan-execution` starts
the selected phase.
