# gh-vault

`gh-vault` keeps named GitHub tokens and project `.env` values in GPG-encrypted `pass` entries. It also syncs declared GitHub Actions values, exports files for `act`, and checks workflow wiring. It never keeps secret values in the checkout or ordinary command output.

## Requirements

- Linux, Python 3.10+, `pass`, and GPG
- `gh` authenticated with access to the target repository for Actions commands

```sh
sudo apt install pass gnupg
gpg --full-generate-key
pass init YOUR_GPG_KEY_ID
uv tool install --editable .
```

## Tokens and Git credentials

```sh
gh-vault add repo-read --scopes contents:read,metadata:read
gh-vault activate repo-read
gh-vault run -- gh repo view owner/repo
git config credential.https://github.com.helper '!gh-vault git-credential'
```

Read a token from standard input for automation:

```sh
printf '%s' "$TOKEN" | gh-vault add ci --stdin
```

## Project environment archive

An archive is identified by the normalized `remote.origin.url` namespace. Values and the current `.env.example` are encrypted separately. `.env` comments are intentionally reconstructed from the template on restore.

```sh
# Run in the project checkout
gh-vault env archive
gh-vault env restore
```

Restore refuses to overwrite an existing `.env`; use `--force` after reviewing it. It uses the checkout's current `.env.example`; add `--restore-example` to restore the archived template too.

Only conservative dotenv syntax is accepted: assignments, quoted values, and explicit `@file:` / `@base64:` values. Shell evaluation is deliberately unsupported.

## GitHub Actions values

Only `GH_SECRET_NAME=value` and `GH_VAR_NAME=value` entries are considered. The prefix is stripped before writing Actions values. Reserved runner names are skipped.

```sh
gh-vault secrets sync --dry-run
gh-vault secrets sync
gh-vault secrets sync --migrate-types
gh-vault secrets export-act
gh-vault secrets check
gh-vault variables import
act workflow_dispatch --secret-file .secrets --var-file .vars
gh-vault workflow check
```

`sync` is repository-scoped, resolves `--repo` from origin by default, and passes values to `gh` on standard input. Ordinary sync never deletes remote values. `--migrate-types` explicitly removes a same-name opposite-type remote value before setting the declared type, preventing stale secret/variable fallbacks after a type change. `secrets check` compares each `GH_SECRET_*` name declared in `.env` with `gh secret list`, returns nonzero for names missing on GitHub, and never changes `.env`. `variables import` reads repository variables with `gh variable list` into `GH_VAR_*` entries, targeting `.env` when it exists and otherwise `.env.example`. Existing entries are retained unless `--force` is supplied. `workflow check` fails for unreferenced local values, single-type mismatches, and expressions that put `vars.X` before `secrets.X`; unknown workflow references are warnings. It does not impose repository-specific namespace mappings.

## Security model

- Tokens, archived values, and archive templates live only in `pass` below `gh-vault/`.
- Metadata is mode `0600` under `${XDG_CONFIG_HOME:-~/.config}/gh-vault/`; it contains no secret values.
- `.env`, `.secrets`, and `.vars` are ignored by Git. Generated files are mode `0600`.
- The only token stdout is the exact credential-helper response Git requires.
