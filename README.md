# gh-vault

![gh-vault](assets/logo-1024.png)

`gh-vault` keeps named GitHub tokens and project `.env` values in GPG-encrypted `pass` entries. It also records available token scope and expiration metadata, syncs declared GitHub Actions values, exports files for `act`, and checks workflow wiring. It never keeps secret values in the checkout or ordinary command output.

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
gh-vault set repo-read # creates or replaces the profile
gh-vault set repo-read --scopes contents:read,metadata:read # explicit scope override
gh-vault activate repo-read
gh-vault run -- gh repo view owner/repo
git config credential.https://github.com.helper '!gh-vault git-credential'
```

Read a token from standard input for automation:

```sh
printf '%s' "$TOKEN" | gh-vault set ci --stdin
```

When `--scopes` is omitted, `set` makes one authenticated request to `https://api.github.com/user`; a successful response validates the token and prints its discovered scopes plus its expiration when available. `set` always creates or replaces the named profile. Classic PATs expose their granted scopes in `X-OAuth-Scopes`; GitHub supplies an expiration timestamp in `GitHub-Authentication-Token-Expiration` when one exists. Fine-grained tokens do not expose classic scopes, so their scope list remains empty. `--scopes` retains manual metadata while `set` still records an expiration when GitHub provides it. `gh-vault list` displays the saved expiration.

## Project environment archive

An archive is identified by the normalized `remote.origin.url` namespace. Values and the current `.env.example` are encrypted separately. `.env` comments are intentionally reconstructed from the template on restore.

```sh
# Run in the project checkout
gh-vault env archive
gh-vault env restore
gh-vault env run -- ./scripts/report.sh
```

Restore refuses to overwrite an existing `.env`; use `--force` after reviewing it. It uses the checkout's current `.env.example`; add `--restore-example` to restore the archived template too. `env run -- <command> ...` injects parsed local values and maps `GH_VAR_<KEY>` / `GH_SECRET_<KEY>` to `<KEY>`; a Secret wins when both prefixes declare the same key. It uses the conservative dotenv parser rather than sourcing the file, so quoted values and valid double-quote escapes are decoded without shell evaluation.

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

`sync` is repository-scoped, resolves `--repo` from origin by default, and passes values to `gh` on standard input. Ordinary sync never deletes remote values. `--migrate-types` explicitly removes a same-name opposite-type remote value before setting the declared type, preventing stale secret/variable fallbacks after a type change. `--prune` removes only remote Secrets and Variables whose names have no `GH_SECRET_` or `GH_VAR_` declaration locally; it deliberately leaves same-name opposite types alone and cannot be combined with `--migrate-types`. With `--dry-run`, it reports the number of remote values it would prune. `secrets check` compares `GH_SECRET_*` and `GH_VAR_*` names in `.env` with both GitHub types. The local prefix is authoritative: a GitHub Variable for `GH_SECRET_NAME` is reported as `GH_VAR_NAME -> GH_SECRET_NAME`, while a GitHub Secret for `GH_VAR_NAME` is reported as `GH_SECRET_NAME -> GH_VAR_NAME`; both return nonzero until synchronized. Missing and remote-only values also return nonzero. It never changes `.env`. `variables import` reads repository variables with `gh variable list` into `GH_VAR_*` entries, targeting `.env` when it exists and otherwise `.env.example`. Existing entries are retained unless `--force` is supplied. `workflow check` fails for unreferenced local values, single-type mismatches, and expressions that put `vars.X` before `secrets.X`; it warns only for unknown references without a workflow fallback and excludes GitHub-provided names such as `GITHUB_TOKEN`. Each finding is one `file:line: severity: explanation` line. It does not impose repository-specific namespace mappings.

## Security model

- Tokens, archived values, and archive templates live only in `pass` below `gh-vault/`.
- Metadata is mode `0600` under `${XDG_CONFIG_HOME:-~/.config}/gh-vault/`; it contains no secret values.
- `.env`, `.secrets`, and `.vars` are ignored by Git. Generated files are mode `0600`.
- The only token stdout is the exact credential-helper response Git requires.

## License

MIT — see [LICENSE](LICENSE).

## Releasing to PyPI

`gh-vault` uses a single source of truth for its version: `src/gh_vault/__init__.py` → `__version__`. The release workflow is: bump that string, tag, build, upload.

Prerequisites: a PyPI account and an API token scoped to the `gh-vault` project (or account-wide). Configure the token once:

```sh
# Re-authenticate at any time; this overwrites the stored token.
uv publish --token PYPI_API_TOKEN    # placeholder; set the env var instead
```

Prefer the `UV_PUBLISH_TOKEN` environment variable and avoid storing the token on disk. `gh-vault secrets sync` can keep the value in `pass` for this repo if you maintain it locally.

### Publish a release

```sh
# 1. Update __version__ in src/gh_vault/__init__.py
$EDITOR src/gh_vault/__init__.py

# 2. Update the changelog and commit the version bump.
git add src/gh_vault/__init__.py
git commit -m "chore(release): vX.Y.Z"
git tag vX.Y.Z

# 3. Clean previous builds, then build sdist + wheel from the source checkout.
rm -rf dist/ build/ src/gh_vault.egg-info/
uv build

# 4. Verify the artifact (metadata, license file, README) before upload.
uv publish --dry-run

# 5. Upload to PyPI.
uv publish

# 6. Push the tag so the release on GitHub matches PyPI.
git push origin vX.Y.Z
```

`uv build` reads the version dynamically from `gh_vault.__version__`, so both the sdist and the wheel inherit the single `__version__` string — no separate `VERSION` file or duplicated `version =` field. The `LICENSE` file ships inside the sdist and the wheel; PyPI's license expression resolves to MIT through `license = "MIT"` and `license-files = ["LICENSE"]` in `pyproject.toml`.

### Version policy

Follow [Semantic Versioning](https://semver.org/). Before `1.0.0`, minor bumps may include breaking changes; the project documents these in release notes. The `feat(vault)!: replace add with set` commit history shows the convention: `!` marks breaking changes and the CLI entry point stays at `gh_vault.cli:main`.