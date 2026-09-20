# CAP-005 — Explicit declaration and archive migrations

**Status:** implemented
**Primary surface:** none

## Behaviour

- `actions migrate-env` rewrites legacy `GH_SECRET_`/`GH_VAR_` keys in one environment file and its matching template to ordinary keys with adjacent type directives. It preserves template comments and preflights key collisions before replacing files.
- `env migrate` is the explicit version-2 encrypted archive reader. It requires reviewed typed declarations, partitions legacy values into public variables and encrypted secrets, excludes unclassified/local values, verifies destination values and index, and removes the legacy entry last.
- An existing split destination must agree with the intended payload; conflicting data aborts without deleting the legacy entry. A publication failure also leaves the legacy archive available.

## Implementation

- `src/gh_vault/actions.py` — migrate_env_source and _render_legacy_declarations.
- `src/gh_vault/envfiles.py` — migrate_environment_archive and profile-reference rejection.
- `src/gh_vault/cli.py` — separate declaration/archive migration commands.

## Rules and boundaries

- Run and review declaration migration before archive migration, separately for each profile. Moving a value to `variable` explicitly permits plaintext storage.
- Profile-referenced assignments are not literal archival values and are rejected. Legacy payload version, exact origin, and data shape must match; this is not a universal importer for all historical formats.
- File replacement is atomic per file, not a transaction over the environment/template pair. Cross-store migration is verification-before-delete, not rollback of every partial write. A rerun after successful deletion requires a legacy entry; do not assume no-op idempotence without it.

## Verification

- `tests/test_vault_features.py` — `test_migrate_env_source_rewrites_environment_and_commented_template` and `test_migrate_env_source_preflights_collisions_before_writing` assert rewrite counts, content, modes, and unchanged inputs on collision.
- `tests/test_vault_features.py` — `test_migrate_environment_archive_partitions_and_removes_legacy` asserts partitioning, no secret in public JSON, matching destination handling when a legacy entry is present, and conflict refusal.
- `tests/test_vault_features.py` — `test_migrate_environment_archive_keeps_legacy_when_publication_fails` injects index-publication failure and asserts legacy retention.
- `tests/test_cli.py` — migration dispatch tests verify the separate public command paths.
- Run `uv run --no-project --with pytest python -m pytest tests/test_vault_features.py -k migrate`.
- Mocks/in-memory stores do not establish real password-store failure recovery or interruption safety between file replacements.

## Related contracts

- [Archive and restore](CAP-004-environment-archives.md)
- [Security](../../security.md)
