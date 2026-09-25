# Capability index

Current contracts are grounded in the Python implementation and offline assertions.
`implemented` describes the stated boundary, not exhaustive branch coverage or live-service certification.

| Capability | Status |
| --- | --- |
| [CAP-001 — Token profiles and encrypted storage](capabilities/CAP-001-token-profiles.md) | implemented |
| [CAP-002 — Credential delivery and lookup](capabilities/CAP-002-credential-delivery.md) | implemented |
| [CAP-003 — Typed dotenv values and runtime references](capabilities/CAP-003-typed-environments.md) | implemented |
| [CAP-004 — Project environment archive and restore](capabilities/CAP-004-environment-archives.md) | implemented |
| [CAP-005 — Explicit declaration and archive migrations](capabilities/CAP-005-explicit-migrations.md) | implemented |
| [CAP-006 — GitHub Actions synchronization, comparison, and standby publication](capabilities/CAP-006-actions-values.md) | implemented |
| [CAP-007 — Local Actions files and execution](capabilities/CAP-007-local-actions.md) | partial |
| [CAP-008 — Offline workflow wiring diagnostics](capabilities/CAP-008-workflow-validation.md) | implemented |
| [CAP-009 — Maintenance records and quality gates](capabilities/CAP-009-maintenance-records.md) | implemented |

## Evidence boundaries

- GitHub API inspection, `gh`, and act boundaries are mocked. The fake `pass` executable proves command/payload behavior, not cryptography or GPG-agent unlocking. Tests do not access live credentials.
- CAP-007 is partial: ephemeral act execution rejects vault-profile references even though persistent export supports them.
- Destructive prune is scoped to selected values of one type; opposite-type or empty declarations are not protected. Bitwarden standby metadata does not prove Secret equality or rollback readiness (CAP-006). Workflow warning severity does not alone determine exit status (CAP-008).
- File permissions are tested; concurrent writes, symlink defense, crash durability, and cross-store rollback are not established. Remote PyPI/OIDC publishing is an operator contract in [RELEASING](../RELEASING.md), not a tested product capability.
- CAPs classify their primary surface as `none`: command-line/protocol interactions have no canonical visual screen. Brand assets are not product wireframes.

[Record authoring](README.md) · [Architecture](../architecture.md) · [Security](../security.md) · [Change progress](../changes/README.md)
