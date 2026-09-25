# CAP-004 — Project environment archive and restore

**Status:** implemented
**Primary surface:** none

## Behaviour

- Archive identity comes from `remote.origin.url`: supported SSH/HTTP(S) spellings normalize to a host/path namespace; `.env` selects the default profile and `.env.NAME` a named profile. Payload reads also require the exact stored origin string.
- `env archive` stores typed variables as public XDG JSON, typed secrets as encrypted version-3 vault payloads, and excludes local-only assignments from value payloads. Only profiles with secrets may archive their template. The separate public index contains profile/type/template presence, not values.
- Writes verify new value payloads before deleting stale opposite-store payloads. Reclassification to local-only removes the corresponding archived value; removing the last value removes the profile from the index.
- `env list` and `env show` use the public index/payload without decrypting secrets. Variable-only archive/restore uses no vault; full variable-only restore needs a local template.
- Full restore refuses an existing target unless forced, merges values onto the local template or archived fallback, preserves unmatched template text, and appends archived keys missing from the template. `--restore-example` additionally writes the archived template when available.
- `env restore --key NAME` appends or creates just that archived key with a synthetic type directive. It validates the key, rejects `--restore-example`, and does not require `--force`.
- `bitwarden env restore` is a separate fresh-clone path: it uses the local template plus one explicit connection/project/adapter, requires all managed keys, and never reads or falls back to an archive. It refuses overwrite unless forced and installs the fully validated result through a private adjacent file and atomic replacement.

## Implementation

- `src/gh_vault/envfiles.py` — project_namespace, archive_environment, restore_environment, render_template, list_environments, show_environment.
- `src/gh_vault/bitwarden.py` — structured exact-project environment retrieval validation.
- `src/gh_vault/store.py` — EnvironmentStore and restrictive JSON persistence.
- `src/gh_vault/cli.py` — local/archive and Bitwarden environment dispatch plus repeatable archive selection.

## Rules and boundaries

- Secret/local assignment values never enter public variable/index JSON. Templates are raw text: do not place real credentials or local-only values in example files.
- Full restore preserves template declarations rather than deriving every directive from archive type. Extra keys appended under `# Local additions` have no generated type directive; review them before sync/rearchive. Single-key restore does generate the directive but does not deduplicate an existing key.
- The origin string is exact even if two origin spellings normalize to the same namespace. Archive operations spanning the public store and `pass` are not a cross-store transaction. Normal commands do not fall back to monolithic legacy archives.
- Restored files finish with `0600` mode, but their writer is write-then-chmod, not atomic replacement. See the security contract.
- The preceding write-then-chmod limit applies to local archive restore. Bitwarden recovery uses private-from-creation atomic replacement, validates all remote values first, and leaves an existing target intact on failure.

## Verification

- `tests/test_vault_features.py` — `test_project_namespace_normalizes_ssh_origin`, `test_project_namespace_normalizes_url_origins`, `test_project_namespace_rejects_unsafe_origins`, `test_archive_and_restore_uses_template_comments`, and `test_archive_lists_and_restores_named_environments` assert identity and round-trip behavior with mocked origin lookup and an in-memory vault.
- `tests/test_vault_features.py` — `test_variable_only_archive_and_show_never_use_the_vault`, `test_archive_type_transitions_remove_stale_payloads`, `test_list_and_restore_do_not_fallback_to_legacy_default_archive`, `test_archive_environment_rejects_profile_references`, `test_restore_environment_preserves_profile_reference_directive`, and the `test_restore_with_key_*` family assert isolation and restore boundaries.
- `tests/test_store.py` — `test_environment_store_separates_variable_payload_and_manifest`, `test_environment_store_validates_payload_origin_and_data`, `test_environment_store_rejects_invalid_paths_and_manifest_details`, and `test_environment_store_removes_only_the_selected_payload` assert public persistence and modes.
- `tests/test_bitwarden_environments.py` — `test_bitwarden_restore_recreates_fresh_environment_from_declared_keys`, `test_restore_refuses_existing_target_before_remote_access`, `test_restore_keeps_forced_target_when_remote_validation_fails`, and `test_atomic_restore_keeps_old_target_when_replace_fails` prove fresh-checkout reconstruction and replacement boundaries with a fake adapter.
- Run `uv run --no-project --with pytest python -m pytest tests/test_bitwarden_environments.py tests/test_vault_features.py tests/test_store.py`.
- These tests do not prove crash recovery across stores, real GPG encryption, or live Bitwarden behavior.

## Related contracts

- [Typed environments](CAP-003-typed-environments.md)
- [Explicit migrations](CAP-005-explicit-migrations.md)
- [Security](../../security.md)
