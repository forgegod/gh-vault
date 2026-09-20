# CHG-001 — Adopt source-backed maintenance records

**Status:** done
**Impacts:** CAP-001, CAP-002, CAP-003, CAP-004, CAP-005, CAP-006, CAP-007, CAP-008, CAP-009
**External request:** Direct operator request: migrage ../gh-vault/ project to this structure by reverse engineer it's functionality and documents as proposed by this blueprint. Do not modify this project. Modify the ../gh-vault project instead to this structure and rules
**Baseline:** `b89ca9be10285b8b0f6128d143aef88c591d5050`

## Why

Adopt the maintenance structure in the existing application, deriving present
behavior from source and assertions instead of copying the blueprint's fictional
product boundary or importing completed plans as active progress.

## Scope

- Establish gh-vault-owned DOX, architecture, security, decision rationale,
  CAP inventory, and change lifecycle; retain the existing runtime, entry points,
  secret storage, public version, release workflow, and branding.
- Reverse-engineer runtime capabilities with explicit evidence and limits; correct
  contradictory command/install, prune, profile-reference, and diagnostic docs.
- Add offline limitation characterizations, the record validator with pytest
  evidence recognition, its regressions, optional playbooks, and a credential-free
  Makefile/CI gate. Do not commit, push, publish, or access real credentials.
- The sibling blueprint is read-only. Existing untracked `uv.lock` and private
  historical planning material are not migration inputs to rewrite or discard.

## Acceptance criteria

- [x] Product CAPs state current source/test-backed behavior, with an honest partial
  boundary for ephemeral act profile references and no unsupported safety claims.
- [x] Every CAP names asserting tests, implementation paths, and `Primary surface: none`.
- [x] Root and child DOX index all durable boundaries; local playbooks require no
  sibling checkout or agent-profile installation.
- [x] `make verify`, documentation checks, isolated package build/metadata/CLI
  smoke, and supported Python test runs pass.
- [x] Final scope review confirms unchanged runtime, publish workflow, branding,
  original untracked lockfile, and a clean sibling blueprint.

## Phases

| # | Phase | Status | Verification gate |
| --- | --- | --- | --- |
| 1 | Source/test evidence inventory and contracts | done (source/assertion review and record check) | Capability ownership and documented boundaries agree with definitions and callers |
| 2 | Maintenance tooling and bounded characterization tests | done (make test) | Offline pytest plus Node validator regressions |
| 3 | Integration, package/docs checks, and scope review | done (full local gates below) | make verify; link/table checks; package build/check/help; Git scope review |

## Phase 1 — Source-backed contracts

**Goal:** Establish present behavior without adopting a foreign product stack.

Read source, callers, asserting tests, and existing DOX; map capabilities and
reconcile operator documentation. Preserve runtime and credential boundaries.

**Verification gate:** `make records-check` and source/assertion review.

## Phase 2 — Executable maintenance

**Goal:** Make the adopted lifecycle independently checkable.

Add pytest evidence naming to the validator, local fixture tests, packaged
playbooks, limitation characterizations, and the offline local/CI gate.

**Verification gate:** `make test`.

## Phase 3 — Integrated handoff

**Goal:** Verify the adopted target without changing the sibling blueprint.

Run full tests, package/docs checks, and the final DOX/scope pass. Record results,
then archive this request only when the gate passes.

**Verification gate:** `make verify`, supported Python runs, isolated package
build/Twine/help, documentation checks, and Git scope review.

## Verification evidence

- `make verify`: passed; 9 CAPs and this CHG validate, 194 Python tests and
  82 Node tests pass. The validator differs from the blueprint only in pytest
  evidence-filename recognition; all other validation logic is preserved.
- `uv run --no-project --python 3.10 --with pytest python -m pytest` and the
  equivalent `--python 3.14` command: 194 passed each. The default runner also passes.
- `npx --yes --package=node@22 node --test "tests/records/*.test.mjs"`: 82 passed.
- `uv build --out-dir /tmp/gh-vault-adoption-dist` and `uvx --from twine twine check
  /tmp/gh-vault-adoption-dist/*`: wheel and sdist built; both metadata checks passed.
  The wheel entry point and a disposable `uv tool install --force .` both pass
  `forgegod-gh-vault --help`; no short executable is installed.
- CI YAML parses and event/permission/Python-matrix assertions pass. No remote CI
  run is claimed. Markdown table structure and DOX parent indexes pass.
- The profile Markdown-link checker reports six inline-regex false positives.
  Every reported target was verified inside an inline-code span; no actual broken
  link remains. Record-local link validation also passes.
- Git diff checks pass. Tracked runtime modules, package manifest/version, publish
  workflow, branding/assets contract, license, and ignore rules are unchanged.
  The pre-existing untracked lockfile and private plans were not rewritten.
  The sibling blueprint remains clean. No credentials were inspected.
- CLI-level regression evidence confirms target-type-only prune protection,
  run-act profile-reference rejection, warning-only workflow failure, stale
  persistent export retention, and literal quoted shell metacharacters.
- Runtime modules are not changed to fix these boundaries during adoption. CAPs
  and operator docs disclose them; any material correction needs its own CHG.
- Visual handoff: all surfaces are CLI/protocol/developer tooling, with `none`
  declarations. No product wireframes or review packages are required or created;
  existing branding remains owned by `assets/AGENTS.md`.
- Live GitHub, pass/GPG, act, CI, and PyPI publication are outside this credential-free gate.

## Outcome

Adoption is complete and verified in the working tree. No commit, push, tag,
publish, or remote-state mutation was requested or performed. This is a receipt
for maintenance adoption, not a fabricated implementation history of the existing
features. CAPs are the current behavior authority; future changes use new CHGs.

DOX closeout: updated the owning root, source, tests, documentation, scripts,
automation, and playbook contracts and their child indexes. `assets/AGENTS.md`
remains unchanged because branding generation and artifacts are unaffected.
