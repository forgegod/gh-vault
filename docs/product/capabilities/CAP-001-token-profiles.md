# CAP-001 — Token profiles and encrypted storage

**Status:** implemented
**Primary surface:** none

## Behaviour

- `set` creates or replaces a named token profile. CLI names are 1–64 characters, begin with a letter/digit, and otherwise contain letters, digits, dot, underscore, or hyphen.
- Token input is an explicit stdin stream or a hidden TTY prompt. After trimming trailing stdin line endings, `set` rejects empty, multiline, masked, out-of-range (36–255 characters), or non-alphanumeric/underscore input before inspection.
- `set` attempts GitHub metadata inspection even with `--scopes`. Without that option an inspection failure aborts; with it, trimmed/deduplicated manual scopes are stored and inspection failure is tolerated. Successful inspection preserves available expiration metadata.
- Tokens go through `pass`; config holds profile metadata and active selection, not token values. Config writes use a private temporary file and atomic replacement, with directory/file modes `0700`/`0600`.
- Creating a profile when no profile is active selects it. Explicit activation changes selection; removing the active profile clears selection without choosing another. `list` marks the active profile and prints metadata only.
- `bitwarden connection set` creates or replaces value-free operator metadata for a named existing bws profile: the absolute config path, resolved HTTPS API/identity endpoints, and expected organization UUID. `bitwarden connection list` reads no credential.
- `bitwarden credential set` stores a nonempty single-line access token separately under `gh-vault/bitwarden/<connection>` through `pass`; `credential remove` deletes only that token. Neither operation creates or changes a GitHub token profile.

## Implementation

- `src/gh_vault/cli.py` — profile_name, _read_token, _validate_token_format, _set, _list, _status, dispatch.
- `src/gh_vault/store.py` — Profile, VaultStore, _write_restrictive_json.
- `src/gh_vault/store.py` — BitwardenConnection plus separate connection-metadata and credential methods.
- `src/gh_vault/bitwarden.py` — named bws-profile parsing and HTTPS endpoint validation.
- `src/gh_vault/github.py` — inspect_token and TokenMetadata.

## Rules and boundaries

- `pass`/GPG owns encryption and unlocking. Metadata is not encrypted; operators must not put credentials in notes or profile names.
- Name validation is a CLI boundary, not a claim that every direct VaultStore call performs the same regex check. No active profile is an error for consumers needing a default token.
- Expiration/scopes are stored metadata, not local enforcement of token authorization or expiry. Manual scopes are an override, not proof that a token has those permissions.
- Bitwarden connection metadata is not authorization. Machine accounts, organization/project permissions, and access-token issuance remain externally provisioned. Stored Bitwarden credentials have no active/default selection and cannot be consumed through GitHub profile commands.

## Verification

- `tests/test_cli.py` — `test_profile_name_validation`, `test_validate_token_format`, `test_read_token_rstrips_newlines_before_format_gate`, and `test_parse_scopes_trims_and_deduplicates` assert the input gates.
- `tests/test_cli.py` — `test_set_discovers_scopes_and_expiration`, `test_set_preserves_expiration_with_manual_scopes`, `test_set_with_manual_scopes_allows_unavailable_inspection`, and `test_list_marks_active_profile` prove metadata handling with injected inspection/store collaborators.
- `tests/test_store.py` — `test_add_select_get_and_remove`, `test_config_permissions_are_restrictive`, `test_replace_requires_force`, `test_missing_backend_has_actionable_error`, and `test_secret_round_trip_preserves_trailing_newlines` exercise persistence using a temporary executable fake `pass`.
- `tests/test_store.py` — `test_bitwarden_connection_metadata_and_credential_are_separated`, `test_bitwarden_connection_replacement_does_not_change_github_selection`, and `test_bitwarden_credential_requires_connection_and_removes_only_credential` prove the split credential boundary.
- `tests/test_bitwarden_connection.py` — `test_load_bws_endpoints_resolves_base_and_explicit_overrides` and `test_connection_and_credential_commands_keep_tokens_out_of_metadata_and_output` prove connection resolution and value-free metadata.
- Run `uv run --no-project --with pytest python -m pytest tests/test_bitwarden_connection.py tests/test_cli.py tests/test_store.py`.
- These tests do not establish live GitHub validation, real GPG encryption, agent cache behavior, crash consistency, or concurrent-writer safety.

## Related contracts

- [Architecture](../../architecture.md)
- [Security](../../security.md)
