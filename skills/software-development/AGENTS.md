# Product-record development playbooks

## Purpose

Own repository-local procedures for maintaining current capabilities and executing material changes through tracked CHGs.

## Ownership

| Path | Owns |
| --- | --- |
| `application-records/SKILL.md` | Classification, record lifecycle, evidence, and handoff |
| `capability-wireframes/SKILL.md` | Canonical HTML/PNG workflow if a primary visual surface exists |
| `phased-plan-design/SKILL.md` | Executable CHG phases and gates |
| `phased-plan-execution/SKILL.md` | One verified phase at a time |
| `phased-plan-overview/SKILL.md` | Active-record selection and resume |
| `phased-plan-refactoring/SKILL.md` | Verified splitting and resequencing |

## Local Contracts

- `docs/product/capabilities/CAP-*.md` is current behavior; `docs/changes/active/CHG-*.md` is mutable progress; archives are receipts.
- Do not use private plans as a second material-change authority.
- CHG review packages remain separate from canonical product wireframes and stay at stable paths after closure.
- `make records-check` is the record gate and `make verify` is the integration gate. Root Git and credential policies control every procedure.

## Work Guidance

Read `application-records` before choosing a phase workflow. Use the repository's product/change READMEs as the canonical record schemas. Activate wireframes only for an actual primary visual surface, not ordinary command-line input/output.

## Verification

Run `make verify`; check changed frontmatter, relative links, and completion criteria against the product/change contracts.

## Child DOX Index

No child DOX documents. Parent: `../AGENTS.md`.
