# CAP-008 — Offline workflow wiring diagnostics

**Status:** implemented
**Primary surface:** none

## Behaviour

- `workflow check` scans `.github/workflows/*.yml` and `*.yaml` against selected typed dotenv values. It emits located findings for unreferenced declarations, type mismatches, vars-before-secrets ordering, and undeclared references without a recognized fallback.
- Findings have file basename, line, severity, name, and message. `--json` returns grouped findings; `--fix` prints suggested env mappings for unreferenced entries without editing files.
- Unreferenced findings are labeled warnings but still fail the command. Type mismatches/order findings also fail. Orphan warnings alone do not fail; reserved GitHub/runner names and detected defaults suppress orphan findings.

## Implementation

- `src/gh_vault/actions.py` — check_workflows, suggested_env, json_result.
- `src/gh_vault/cli.py` — workflow rendering and exit status.

## Rules and boundaries

- This is a line-based expression scanner, not a YAML or GitHub expression parser. It recognizes uppercase dot-name references inside single-line expression delimiters; multiline expressions, bracket lookups, and mixed/lowercase names are not fully modeled.
- Fallback/default detection is heuristic; ordering aggregates references across a line, not an expression syntax tree. Do not treat a clean check as proof of a runnable workflow.
- The check does not contact GitHub, but dotenv selection can read explicit files or resolve profile references. Use synthetic inputs for development/CI rather than the operator's real environment.

## Verification

- `tests/test_vault_features.py` — `test_export_act_and_workflow_check` asserts a clean mapped workflow and `test_workflow_check_omits_defaulted_and_github_orphans` asserts default/reserved-name filtering and located orphan diagnostics.
- `tests/test_cli.py` — `test_workflow_check_prints_located_diagnostics` asserts grouped diagnostic rendering and failure status using injected findings.
- `tests/test_capability_boundaries.py` — `test_workflow_unreferenced_warning_alone_fails` runs real selection/scanning/rendering in text, JSON, and fix modes, asserting failure on the warning alone and no file modification.
- Run `uv run --no-project --with pytest python -m pytest tests/test_cli.py tests/test_vault_features.py tests/test_capability_boundaries.py`.
- These tests do not execute GitHub's YAML/expression evaluator or validate workflows on GitHub.

## Related contracts

- [Typed environments](CAP-003-typed-environments.md)
- [Architecture](../../architecture.md)
