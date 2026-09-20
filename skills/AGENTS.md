# Repository agent playbooks

## Purpose

Own portable execution aids for gh-vault's capability, change, and visual-handoff contracts.

## Ownership

- `software-development/` — the coherent CAP/CHG lifecycle and phase-workflow family.

## Local Contracts

- DOX and the owning project documents remain authoritative; skills do not define product behavior or duplicate change progress.
- Read these repository files directly when an installed skill of the same name follows a different lifecycle. No profile changes or Hermes installation are required.
- Skills use portable `SKILL.md` frontmatter and contain no credentials, private paths, or agent-local state.
- Material work uses active CHGs. Playbooks do not authorize commits, pushes, releases, or remote credential operations.

## Work Guidance

Keep product-specific verification commands and policy in the project contracts. Preserve the complete local phase family when updating a shared lifecycle rule. Do not ship one-time initialization playbooks or blueprint proof records as product content.

## Verification

Run `make verify`, check changed local Markdown links, and inspect changed skill frontmatter and cross-references.

## Child DOX Index

| Child | Owns | Read when editing… |
| --- | --- | --- |
| `software-development/AGENTS.md` | CAP/CHG and visual-handoff procedures | Lifecycle, phase design/execution, or skill packaging |

Parent: `../AGENTS.md`.
