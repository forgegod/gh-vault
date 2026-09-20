# CAP-006 — GitHub Actions synchronization and comparison

**Status:** implemented
**Primary surface:** none

## Behaviour

- `secret sync` selects only Secret values; `variable sync` selects only Variables. Ordinary sync issues only target-type `gh ... set` calls with values on stdin, not argv, and never deletes.
- Remote commands default to repository scope. `secret sync/check`, `variable sync/check`, and `variable import` accept `--github-environment NAME` to operate on one existing GitHub Environment; local `.env.<profile>` names do not select a remote environment implicitly.
- `--migrate-types` explicitly deletes a same-name opposite-type value before setting the target. `--prune` deletes target-store names absent from the selected sync entries. Both operations are confined to the selected repository or environment scope, and the options are mutually exclusive.
- `--dry-run` skips all remote sets/deletes. Prune/type-migration previews still list remote names; value selection may resolve vault references even during a preview.
- `secret check` and `variable check` fetch remote names and report missing, remote-only, and opposite-type findings. Each command's exit status reflects only its own finding categories, without modifying dotenv files.
- `variable import` writes repository or environment-scoped Variables as typed declarations into an existing selected `.env`, or its matching `.env.example` with commented assignments. Existing declarations are retained unless forced; force cannot reclassify a secret or local-only key.

## Implementation

- `src/gh_vault/actions.py` — action_values, sync, remote_secret_status, import_variables, default_repo.
- `src/gh_vault/cli.py` — _run_sync and type-scoped check renderers.

## Rules and boundaries

- Prune protection is scoped to selected, nonempty values of the synced type. Opposite-type declarations, empty literals, and skipped reserved names do not protect a target-store name from deletion. Review with the same flags in dry-run before destructive use.
- Type migration is delete-then-set with no rollback. A set error prints a manual-restoration warning; the error text alone does not prove that a deletion occurred.
- An environment-scoped operation first reads the named deployment environment through `gh api`; an absent or inaccessible environment stops the operation before it lists, sets, deletes, or imports values. gh-vault does not create or configure GitHub Environments or their protection rules.
- Checks compare names/types, not remote Secret contents or permission adequacy. Their reserved-name filtering differs from profile-reference selection: a reserved name may be selected for sync but excluded from the local comparison set.
- Values are selected before type filtering: an unresolved secret profile can also block a variable sync. Remote commands rely on the operator's authenticated `gh`; storing a profile does not automatically select it for `gh` authentication.

## Verification

- `tests/test_vault_features.py` — `test_sync_ordinary_never_lists_or_deletes`, `test_sync_ordinary_variable_sets_only_variables`, both `test_sync_migrates_a_stale_*` tests, both target-type prune tests, `test_sync_dry_run_reports_counts_without_mutation`, and `test_sync_failure_after_migration_delete_preserves_manual_restore_hint` assert mocked subprocess sequences and stdin values.
- `tests/test_cli.py` — secret/variable sync dispatch and check tests assert type filtering, option exclusivity, summaries, finding isolation, and exit statuses.
- `tests/test_vault_features.py` — `test_remote_secret_status_identifies_secret_variable_type_drift`, `test_environment_scoped_status_preflights_and_lists_only_that_environment`, `test_environment_scoped_sync_preflights_and_migrates_only_that_environment`, `test_environment_preflight_failure_prevents_mutation`, and the `test_import_variables_*` family assert repository/environment isolation, preflight, comparison, and import behavior.
- `tests/test_capability_boundaries.py` — `test_cli_prune_does_not_preserve_opposite_type_or_empty_declarations` exercises real CLI selection through sync with a mocked external command boundary for both types.
- Run `uv run --no-project --with pytest python -m pytest`.
- No test authenticates against GitHub or reads back live Secrets/Variables. Profile-reference selection evidence is not proof that GitHub accepts every selected name.

## Related contracts

- [Typed environments](CAP-003-typed-environments.md)
- [Security](../../security.md)
