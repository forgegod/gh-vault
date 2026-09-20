# CAP-002 — Credential delivery and lookup

**Status:** implemented
**Primary surface:** none

## Behaviour

- `find --stdin` compares a single-line candidate against configured token values in-process, prints matching profile names only, and returns `0` for a match or `1` silently for no match. It does not apply the stricter `set` length/alphabet gates.
- `output [--name PROFILE]` intentionally prints only the selected token plus a newline, suitable for a consumer's stdin.
- `run [--name PROFILE] -- COMMAND` copies the parent environment, overwrites `GH_TOKEN` and `GITHUB_TOKEN` with the selected token, and replaces the process with the command. It does not change the invoking shell.
- `git-credential get` emits Git's username/password response only for HTTPS requests whose normalized host is `github.com`. Other hosts/protocols and `store`/`erase` produce no credentials.

## Implementation

- `src/gh_vault/cli.py` — _find, _run, _git_credential, _credential_host, dispatch, main.
- `src/gh_vault/store.py` — VaultStore token selection and lookup.
- `src/gh_vault/__main__.py` — module entry point.
- `pyproject.toml` — installed forgegod-gh-vault console entry point.

## Rules and boundaries

- The installed executable is `forgegod-gh-vault`; argparse's usage label remains `gh-vault`. `python -m gh_vault` uses the same dispatcher.
- Credential stdout is intentional only for `output` and the credential-helper response. Do not run those in a logged terminal or capture their output in records.
- Child environment delivery is not a sandbox: the child inherits the rest of the environment and can disclose its token. StoreError becomes an argparse error at the main CLI boundary.

## Verification

- `tests/test_cli.py` — `test_find_prints_matching_profile_names_only`, `test_find_returns_one_without_output_when_token_is_unknown`, `test_find_requires_explicit_stdin`, and `test_find_rejects_empty_token` cover lookup outcomes.
- `tests/test_cli.py` — `test_output_prints_only_selected_token`, `test_git_credential_returns_selected_token_only_for_github`, `test_run_executes_with_both_supported_environment_variables`, and `test_run_requires_a_command` prove response shapes and intercepted process handoff.
- `tests/test_cli.py` — `test_parser_uses_public_command_name` pins the usage label, not executable installation. Wheel installation and `forgegod-gh-vault --help` are separate packaging checks.
- Run `uv run --no-project --with pytest python -m pytest tests/test_cli.py`.
- Credential tests use synthetic tokens; exec is intercepted. They do not authenticate Git or a downstream consumer.

## Related contracts

- [Token profiles](CAP-001-token-profiles.md)
- [Security](../../security.md)
