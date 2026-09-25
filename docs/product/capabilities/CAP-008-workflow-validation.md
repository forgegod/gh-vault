# CAP-008 — Offline workflow wiring diagnostics

**Status:** implemented
**Primary surface:** none

## Behaviour

- `workflow check` scans `.github/workflows/*.yml` and `*.yaml` against selected typed dotenv values. It emits located findings for unreferenced declarations, type mismatches, vars-before-secrets ordering, and undeclared references without a recognized fallback.
- Findings have file basename, line, severity, name, and message. `--json` returns grouped findings; `--fix` prints suggested env mappings for unreferenced entries without editing files.
- Unreferenced findings are labeled warnings but still fail the command. Type mismatches/order findings also fail. Orphan warnings alone do not fail; reserved GitHub/runner names and detected defaults suppress orphan findings.
- Marked `dual-provider-v1` blocks receive additional offline checks for a single ordered marker pair, local key/type agreement, unique UUIDs and aliases, exact generated mappings, pinned `bitwarden/sm-action`, explicit region, `set_env: false`, bootstrap-token placement, required-output checks, identical nonempty consumer commands, dispatch input choices/default, and retrieval before submodule checkout. Structural findings use the existing `order` group; a new `bootstrap` group fails the command when `BWS_ACCESS_TOKEN` appears outside the marked block.

## Implementation

- `src/gh_vault/actions.py` — check_workflows, _dual_provider_findings, suggested_env, json_result.
- `src/gh_vault/cli.py` — workflow rendering and exit status.

## Rules and boundaries

- This is a line-based expression scanner, not a YAML or GitHub expression parser. It recognizes uppercase dot-name references inside single-line expression delimiters; multiline expressions, bracket lookups, and mixed/lowercase names are not fully modeled.
- Fallback/default detection is heuristic; ordering aggregates references across a line, not an expression syntax tree. Do not treat a clean check as proof of a runnable workflow.
- Dual-provider validation applies only inside exact generated start/end markers. It compares marker JSON with literal generated lines and does not evaluate GitHub expressions, execute shell steps, contact providers, or prove the pinned action's downloaded executable is immutable.
- The check does not contact GitHub, but dotenv selection can read explicit files or resolve profile references. Use synthetic inputs for development/CI rather than the operator's real environment.

## Verification

- `tests/test_vault_features.py` — `test_export_act_and_workflow_check` asserts a clean mapped workflow and `test_workflow_check_omits_defaulted_and_github_orphans` asserts default/reserved-name filtering and located orphan diagnostics.
- `tests/test_cli.py` — `test_workflow_check_prints_located_diagnostics` asserts grouped diagnostic rendering and failure status using injected findings.
- `tests/test_capability_boundaries.py` — `test_workflow_unreferenced_warning_alone_fails` runs real selection/scanning/rendering in text, JSON, and fix modes, asserting failure on the warning alone and no file modification.
- `tests/test_capability_boundaries.py` — `test_workflow_check_accepts_generated_dual_provider_block_and_rejects_bootstrap_leak` asserts a clean generated block, stale UUID detection, required-output enforcement, submodule ordering, and a located bootstrap-token leak.
- Run `uv run --no-project --with pytest python -m pytest tests/test_bitwarden_actions.py tests/test_cli.py tests/test_vault_features.py tests/test_capability_boundaries.py`.
- These tests do not execute GitHub's YAML/expression evaluator or validate workflows on GitHub.

## Related contracts

- [Typed environments](CAP-003-typed-environments.md)
- [Architecture](../../architecture.md)
