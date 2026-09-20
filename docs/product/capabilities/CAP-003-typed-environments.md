# CAP-003 — Typed dotenv values and runtime references

**Status:** implemented
**Primary surface:** none

## Behaviour

- Dotenv is parsed as data, never sourced: ordinary assignments, leading `export`, single/double quotes, explicit `@file:` reads, and UTF-8 `@base64:` decoding are supported. Unquoted shell substitutions/backticks are rejected; quoted metacharacters remain literal data.
- An immediately adjacent `# gh-vault: secret` or `# gh-vault: variable` classifies an assignment. Untyped values are local-only. The typed parser rejects duplicate keys, unsupported directives, broken adjacency, and legacy prefixed keys; commented template assignments require explicit parser opt-in.
- `# gh-vault: secret PROFILE` resolves through the selected named vault profile for `env run`, secret sync/export, and workflow selection. A variable directive cannot reference a profile. Missing profiles fail with the source location.
- `env run -- COMMAND` injects selected typed values into a copy of the parent environment. Literal empty and reserved `GITHUB_*`, `RUNNER_*`, `CI`, and `GH_TOKEN` keys are skipped; profile references bypass that reserved-name filter. Local-only declarations are not added from the file.

## Implementation

- `src/gh_vault/envfiles.py` — parse_dotenv, parse_typed_dotenv, _decode, _split_directive, format_dotenv_value.
- `src/gh_vault/actions.py` — action_values and runtime_environment.
- `src/gh_vault/cli.py` — _env_run and selection call sites.

## Rules and boundaries

- Keys match `[A-Za-z_][A-Za-z0-9_]*`. `@file:` is explicit and may reference an absolute or home-expanded path; it is not confined to the checkout. Do not use untrusted dotenv files.
- Typed parsing still decodes the literal assignment before runtime profile resolution; leave profile-reference values empty.
- Skipping a file declaration does not remove a same-name inherited process variable. Archives reject profile references rather than storing placeholders.
- `run-act` is not a profile-reference consumer: it calls selection without a vault store and rejects those declarations; see CAP-007.

## Verification

- `tests/test_vault_features.py` — `test_parse_dotenv_decodes_explicit_values_without_sourcing`, `test_parse_dotenv_rejects_shell_syntax`, and the `test_parse_typed_dotenv_*` family assert parsing, directive adjacency, duplicates, legacy rejection, and profile syntax.
- `tests/test_vault_features.py` — `test_runtime_environment_resolves_profile_references`, `test_runtime_environment_rejects_unknown_profile`, `test_action_values_resolves_profile_references`, and `test_action_values_without_store_rejects_profile_reference` prove selection with in-memory stores.
- `tests/test_cli.py` — `test_env_run_injects_declared_actions_values` and `test_env_run_requires_an_explicit_command_separator` assert dispatch using intercepted exec.
- `tests/test_capability_boundaries.py` — `test_quoted_shell_metacharacters_remain_literal` asserts the quoted-data boundary.
- Run `uv run --no-project --with pytest python -m pytest`.
- No real token store or child application is exercised by these selection tests.

## Related contracts

- [Archive and restore](CAP-004-environment-archives.md)
- [Local Actions](CAP-007-local-actions.md)
- [Security](../../security.md)
