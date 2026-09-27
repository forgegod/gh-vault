# CAP-002 — Credential delivery and lookup

**Status:** implemented
**Primary surface:** none

## Behaviour

- `find --stdin` compares a single-line candidate against configured local or Bitwarden-bound token profiles in-process, prints matching profile names only, and returns `0` for a match or `1` silently for no match. It does not apply the stricter `set` length/alphabet gates.
- `output [--name PROFILE]` intentionally prints only the selected token plus a newline, suitable for a consumer's stdin. A bound profile is read and identity-validated on demand first.
- `run [--name PROFILE] -- COMMAND` copies the parent environment, overwrites `GH_TOKEN` and `GITHUB_TOKEN` with the selected token, and replaces the process with the command. It does not change the invoking shell; a bound profile has no local-token fallback.
- `git-credential get` emits Git's username/password response only for HTTPS requests whose normalized host is `github.com`. Other hosts/protocols and `store`/`erase` produce no credentials.
- Bitwarden commands use `${XDG_DATA_HOME:-~/.local/share}/gh-vault/adapters/gh-vault-bws` by default. The operator manually creates and clones that private checkout; gh-vault never fetches, installs, or updates it. `--adapter-path` explicitly selects another checkout for one command.
- `bitwarden project resolve` requires an explicit connection, canonical project UUID, and `env` or `vault` credential source. It validates the current Git origin and the saved bws profile's HTTPS endpoints before reading the selected token, rejects ambient bws endpoint/profile overrides, and never falls back between credential sources.
- Project resolution loads `gh_vault_bws` only from the selected default or override checkout, passes one requested project and expected organization to its versioned interface, suppresses adapter output/raw errors, and accepts only the same project/organization IDs in response. Success prints identifiers only, never the access token or a project listing.

## Implementation

- `src/gh_vault/cli.py` — _find, _run, _git_credential, _credential_host, dispatch, main.
- `src/gh_vault/store.py` — VaultStore token selection and lookup.
- `src/gh_vault/bitwarden.py` — default adapter path, local adapter loader, temporary state path, request boundary, and result validation.
- `src/gh_vault/__main__.py` — module entry point.
- `pyproject.toml` — `gh-vault` console entry point for the `forgegod-gh-vault` distribution.

## Rules and boundaries

- The `forgegod-gh-vault` distribution installs `gh-vault`; `python -m gh_vault` uses the same dispatcher. `forgegod-gh-vault` is not an installed compatibility executable.
- Credential stdout is intentional only for `output` and the credential-helper response. Do not run those in a logged terminal or capture their output in records.
- Child environment delivery is not a sandbox: the child inherits the rest of the environment and can disclose its token. StoreError becomes an argparse error at the main CLI boundary.
- The local Bitwarden adapter is operator-trusted code loaded in-process, not a sandbox or bundled backend. gh-vault does not fetch it, expose an SDK dependency, probe regions, list projects by name, or persist adapter authentication state. The XDG data default is only an operator convention; it is not a downloaded package registry or update channel.

## Verification

- `tests/test_cli.py` — `test_find_prints_matching_profile_names_only`, `test_find_returns_one_without_output_when_token_is_unknown`, `test_find_requires_explicit_stdin`, and `test_find_rejects_empty_token` cover lookup outcomes.
- `tests/test_cli.py` — `test_output_prints_only_selected_token`, `test_git_credential_returns_selected_token_only_for_github`, `test_run_executes_with_both_supported_environment_variables`, and `test_run_requires_a_command` prove response shapes and intercepted process handoff.
- `tests/test_cli.py` — `test_parser_uses_public_command_name` and `test_project_declares_short_console_command` pin the shared parser label and declared console-script boundary. Isolated-install verification exercises the generated executable.
- `tests/test_bitwarden_profiles.py` — `test_bitwarden_profile_resolution_reads_and_validates_the_exact_bound_entry`, `test_bitwarden_profile_resolution_rejects_an_entry_id_change`, and the pre-adapter rejection tests prove on-demand bound-profile delivery with synthetic adapters.
- Run `uv run --no-project --with pytest python -m pytest tests/test_bitwarden_connection.py tests/test_cli.py`.
- Credential tests use synthetic tokens; exec is intercepted. They do not authenticate Git or a downstream consumer.

## Related contracts

- [Token profiles](CAP-001-token-profiles.md)
- [Architecture](../../architecture.md)
- [Security](../../security.md)
