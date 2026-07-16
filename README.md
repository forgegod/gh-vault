# github-token-safe

`gts` stores GitHub tokens under names such as `repo-read` or `release-write`, then runs `gh`, `git`, or another command with the chosen token. Token values are GPG-encrypted by `pass`, not stored in the project or the tool's config file.

## Requirements

- Linux and Python 3.10+
- `pass` with a GPG key

Ubuntu/Debian:

```sh
sudo apt install pass gnupg
gpg --full-generate-key
pass init YOUR_GPG_KEY_ID
```

If you already use `pass`, keep the existing initialization. `gts` stores entries below `github-token-safe/` in `${PASSWORD_STORE_DIR:-~/.password-store}` and deliberately does not fall back to plaintext token files.

## Install

Install the command from a development checkout into an isolated user tool environment:

```sh
uv tool install --editable .
```

Run this from the repository root. The editable install makes source changes available without reinstalling. `uv` keeps the command environment outside the checkout; if `gts` is not on `PATH`, run `uv tool update-shell` once and start a new shell.

## Use

Add tokens without putting them in shell history or process arguments:

```sh
gts add repo-read --scopes contents:read,metadata:read
gts add release-write --scopes contents:write --note "fine-grained PAT for releases"
```

The prompt does not echo input. For automation, pass the token on standard input:

```sh
printf '%s' "$TOKEN" | gts add ci --stdin
```

List and select profiles:

```sh
gts list
gts activate release-write
gts status
```

Run a command with the active token:

```sh
gts run -- gh auth status
gts run -- git fetch
```

Use another profile for one command without changing the active profile:

```sh
gts run --name repo-read -- gh repo view owner/repo
```

`run` sets both `GH_TOKEN` and `GITHUB_TOKEN` only in the child process. It does not print the token and does not modify your shell.

Remove a profile:

```sh
gts remove release-write
```

## Git credential helper

To make HTTPS Git operations use the active profile in this repository:

```sh
git config credential.https://github.com.helper '!gts git-credential'
```

Or configure it globally by adding `--global`. The helper responds only for HTTPS requests to `github.com`; it does not persist credentials supplied by Git. Removing the active profile leaves no profile active rather than selecting another token implicitly.

## Scope labels

`--scopes` records operator-supplied metadata so `gts list` explains each profile's purpose. GitHub does not expose a reliable common scope API for both classic and fine-grained PATs, so `gts` does not claim to verify those labels.

## Security model

- Tokens are GPG-encrypted by `pass` below `github-token-safe/` in `${PASSWORD_STORE_DIR:-~/.password-store}`. The password store is outside the development checkout unless you explicitly override `PASSWORD_STORE_DIR` to point there.
- Metadata is stored at `${XDG_CONFIG_HOME:-~/.config}/github-token-safe/config.json` with mode `0600`.
- Neither token values nor profile metadata are stored in the development checkout.
- Tokens are passed to child commands through environment variables. A same-user process with sufficient inspection rights may read another process's environment; this is also how `gh` consumes `GH_TOKEN`.
- `gts` does not write token values to config files, logs, or command arguments. The only stdout exception is the strict response expected when Git invokes `gts git-credential get`.
