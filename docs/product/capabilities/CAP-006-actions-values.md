# CAP-006 — GitHub Actions synchronization, comparison, and standby publication

**Status:** implemented
**Primary surface:** none

## Behaviour

- `secret sync` selects only Secret values; `variable sync` selects only Variables. Ordinary sync issues only target-type `gh ... set` calls with values on stdin, not argv, and never deletes.
- Remote commands default to repository scope. `secret sync/check`, `variable sync/check`, and `variable import` accept `--github-environment NAME` to operate on one existing GitHub Environment; local `.env.<profile>` names do not select a remote environment implicitly.
- `--migrate-types` explicitly deletes a same-name opposite-type value before setting the target. `--prune` deletes target-store names absent from the selected sync entries. Both operations are confined to the selected repository or environment scope, and the options are mutually exclusive.
- `--dry-run` skips all remote sets/deletes. Prune/type-migration previews still list remote names; value selection may resolve vault references even during a preview.
- `secret check` and `variable check` fetch remote names and report missing, remote-only, and opposite-type findings. Each command's exit status reflects only its own finding categories, without modifying dotenv files.
- `variable import` writes repository or environment-scoped Variables as typed declarations into an existing selected `.env`, or its matching `.env.example` with commented assignments. Existing declarations are retained unless forced; force cannot reclassify a secret or local-only key.
- `bitwarden actions publish` derives managed names/types from one explicit template, retrieves exact-name values and entry IDs from one explicit Bitwarden project, and requires an explicit destination repository. `--github-environment` is the only Environment selector; the local dotenv profile never infers it.
- Publication defaults to a value-free create/update preview. `--apply` writes all selected values to GitHub on stdin, never deletes or migrates types, rejects empty values and opposite-type targets before writes, then verifies Variables by exact name/value and Secrets by name/type presence only.
- Applied success and partial failure write restrictive, origin-bound metadata containing source entry IDs, destination scope, attempt time, GitHub revisions, operations, and per-key results. Metadata contains no values or value hashes and does not prove Secret equality, credential validity, or rollback readiness.
- `bitwarden actions generate` inspects UUIDs for an explicit managed-key subset and emits a value-free mode-`0644` fragment with one selector, a pinned Bitwarden action step, required-output validation, and identical consumer commands behind separate GitHub and Bitwarden branches. Kinds come only from typed declarations; aliases/defaults are explicit, defaults are variable-only, and `BWS_ACCESS_TOKEN`/`CONFIG_SOURCE` remain bootstrap inputs rather than fetched values.

## Implementation

- `src/gh_vault/actions.py` — action_values, sync, remote_secret_status, import_variables, default_repo.
- `src/gh_vault/actions.py` — publish_standby and its value-free GitHub inspection/read-back boundary.
- `src/gh_vault/actions.py` — render_dual_provider_workflow and resolve_config_source define the generated provider contract.
- `src/gh_vault/bitwarden.py` — read_environment_entries retains validated source IDs for publication evidence.
- `src/gh_vault/envfiles.py` — prepare_bitwarden_actions derives types from the selected template.
- `src/gh_vault/store.py` — ActionsPublicationStore persists value-free publication results.
- `src/gh_vault/cli.py` — _run_sync, type-scoped check renderers, and _bitwarden_actions_publish.

## Rules and boundaries

- Prune protection is scoped to selected, nonempty values of the synced type. Opposite-type declarations, empty literals, and skipped reserved names do not protect a target-store name from deletion. Review with the same flags in dry-run before destructive use.
- Type migration is delete-then-set with no rollback. A set error prints a manual-restoration warning; the error text alone does not prove that a deletion occurred.
- An environment-scoped operation first reads the named deployment environment through `gh api`; an absent or inaccessible environment stops the operation before it lists, sets, deletes, or imports values. gh-vault does not create or configure GitHub Environments or their protection rules.
- Checks compare names/types, not remote Secret contents or permission adequacy. Their reserved-name filtering differs from profile-reference selection: a reserved name may be selected for sync but excluded from the local comparison set.
- Values are selected before type filtering: an unavailable secret profile, including an on-demand Bitwarden binding, can also block a variable sync. Remote commands rely on the operator's authenticated `gh`; storing or binding a profile does not automatically select it for `gh` authentication.
- Standby publication uses the separately selected Bitwarden credential only for the local adapter call and the operator's ambient `gh` authentication only for GitHub. Every `gh` child environment removes the Bitwarden access token and bws configuration/profile overrides; the command never injects one credential into the other boundary or relays child stderr.
- A failed standby batch is not rolled back. Metadata records completed and failed names without values, but a safe consumer/authentication probe is still required before treating a refreshed copy as usable rollback evidence.

## Verification

- `tests/test_vault_features.py` — `test_sync_ordinary_never_lists_or_deletes`, `test_sync_ordinary_variable_sets_only_variables`, both `test_sync_migrates_a_stale_*` tests, both target-type prune tests, `test_sync_dry_run_reports_counts_without_mutation`, and `test_sync_failure_after_migration_delete_preserves_manual_restore_hint` assert mocked subprocess sequences and stdin values.
- `tests/test_cli.py` — secret/variable sync dispatch and check tests assert type filtering, option exclusivity, summaries, finding isolation, and exit statuses.
- `tests/test_vault_features.py` — `test_remote_secret_status_identifies_secret_variable_type_drift`, `test_environment_scoped_status_preflights_and_lists_only_that_environment`, `test_environment_scoped_sync_preflights_and_migrates_only_that_environment`, `test_environment_preflight_failure_prevents_mutation`, and the `test_import_variables_*` family assert repository/environment isolation, preflight, comparison, and import behavior.
- `tests/test_capability_boundaries.py` — `test_cli_prune_does_not_preserve_opposite_type_or_empty_declarations` exercises real CLI selection through sync with a mocked external command boundary for both types.
- `tests/test_bitwarden_actions.py` — `test_bitwarden_actions_publish_previews_exact_bws_values_without_writes_or_metadata`, `test_bitwarden_actions_publish_applies_with_stdin_readback_and_value_free_metadata`, `test_bitwarden_actions_publish_closes_adapter_after_preview`, `test_bitwarden_actions_publish_keeps_every_github_call_in_selected_environment`, `test_bitwarden_actions_publish_rejects_empty_values_before_github_access`, `test_bitwarden_actions_publish_rejects_type_drift_before_writes`, `test_bitwarden_actions_publish_records_partial_failure_without_child_diagnostics`, `test_bitwarden_actions_publish_rejects_changed_variable_readback`, and `test_bitwarden_actions_publish_does_not_leak_child_diagnostics_through_stderr` prove exact source selection, adapter cleanup, credential-isolated scope, stdin-only writes, value-free diagnostics, type/empty rejection, partial failure, read-back, and metadata boundaries with synthetic collaborators.
- `tests/test_bitwarden_actions.py` — `test_dual_provider_artifact_uses_explicit_branches_and_declared_types`, `test_resolve_config_source_matches_schedule_and_manual_contract`, `test_resolve_config_source_rejects_invalid_nonempty_values`, `test_dual_provider_artifact_rejects_duplicate_ids_aliases_and_secret_defaults`, `test_bitwarden_actions_generate_uses_explicit_subset_aliases_and_defaults`, and `test_bitwarden_actions_generate_rejects_invalid_subset_before_credentials` prove generated mapping, selector, alias/default, duplicate, preflight, and value-free artifact behavior.
- Run `uv run --no-project --with pytest python -m pytest`.
- No test authenticates against GitHub or reads back live Secrets/Variables. Mocked Variable read-back and Secret name/type presence do not prove live GitHub acceptance, Secret equality, credential validity, or rollback readiness.

## Related contracts

- [Typed environments](CAP-003-typed-environments.md)
- [Security](../../security.md)
