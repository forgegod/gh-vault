# CAP-007 — Local Actions files and execution

**Status:** partial
**Primary surface:** none

## Behaviour

- `run-act -- act ...` and `run-act -- gh act ...` create separate secret/variable files under a `0700` temporary directory, append managed `--secret-file`/`--var-file` flags, and return the child status. Both files exist with `0600` mode even for empty selections.
- Caller-supplied managed flags are rejected before temporary allocation. The temporary directory is removed after normal success, nonzero child exit, or a child launch error.
- `secret export-act` writes explicit persistent files for nonempty kinds, at `0600` after writing. Multiline values are encoded with `@base64:`. This path can use a passed vault store to resolve profile references.

## Implementation

- `src/gh_vault/actions.py` — run_act, export_act, action_values.
- `src/gh_vault/cli.py` — run-act and secret export-act dispatch.

## Rules and boundaries

- The partial boundary is vault-reference support: persistent export supports it; `run-act` passes no vault store to selection and rejects a profile reference before starting the child. Literal typed values work. Do not describe ephemeral execution as supporting references.
- Persistent export leaves an existing file untouched when its kind has no selected values; stale contents are not automatically cleared. Use fresh paths or explicitly inspect/remove old exports before reuse.
- Files are plaintext, not encrypted; base64 is encoding. The temporary workflow cannot guarantee cleanup after SIGKILL or a host crash. Persistent files remain the operator's responsibility.
- The child inherits process environment and stdout/stderr; gh-vault does not redact its output or validate the Actions workflow itself.

## Verification

- `tests/test_vault_features.py` — `test_run_act_uses_private_ephemeral_files`, `test_run_act_accepts_gh_act_invocation`, `test_run_act_creates_empty_files_for_no_typed_values`, `test_run_act_cleans_up_when_the_child_cannot_start`, and managed-flag rejection tests assert modes, arguments, status propagation, and cleanup with a mocked child.
- `tests/test_vault_features.py` — `test_export_act_and_workflow_check` and `test_export_act_resolves_profile_referenced_secrets` assert persistent export contents using synthetic values.
- `tests/test_capability_boundaries.py` — `test_run_act_rejects_profile_references_before_starting_child` and `test_persistent_export_leaves_empty_kind_file_untouched` prove the partial/stale-file boundaries.
- Run `uv run --no-project --with pytest python -m pytest tests/test_vault_features.py tests/test_capability_boundaries.py`.
- Tests do not run real act, Docker, or Actions jobs; they do not prove downstream decoding or workflow compatibility.

## Related contracts

- [Typed environments](CAP-003-typed-environments.md)
- [Security](../../security.md)
