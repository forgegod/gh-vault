# GitHub automation

## Purpose

Own credential-free quality checks and the separate tag-driven PyPI release workflow.

## Ownership

| Path | Owns |
| --- | --- |
| `workflows/ci.yml` | Record and test gate for branch pushes and pull requests |
| `workflows/publish.yml` | Version-tag build and PyPI trusted publishing |

## Local Contracts

- CI runs `make verify` with Python, uv, and Node.js 22. It does not access a password store, real dotenv data, GitHub Secrets/Variables, or PyPI.
- CI permissions are read-only, and checkout does not persist credentials.
- Publishing remains restricted to `v*` tag pushes whose version equals `gh_vault.__version__`, using the `pypi` environment and OIDC. `../docs/RELEASING.md` owns the operator contract.
- A green local gate does not prove remote environment configuration or a successful publish. Do not trigger releases as a test.

## Work Guidance

Keep CI commands aligned with root `Makefile` and DOX. Update release documentation alongside any publishing-trigger, permission, environment, or version-gate change.

## Verification

Run `make verify`, validate workflow syntax, and inspect event/permission scopes. Follow `../docs/RELEASING.md` for local package checks; external release verification requires operator authorization.

## Child DOX Index

No child DOX documents. Parent: `../AGENTS.md`.
