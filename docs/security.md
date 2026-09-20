# Security and data boundaries

## Trust model

The operator controls the local account, `pass`/GPG, `gh` authentication, project
files, and invoked child commands. gh-vault is not a sandbox against a malicious
same-user process, compromised executables, hostile dotenv inputs, or an
untrusted child. It does not issue/revoke PATs or enforce stored scope/expiration
metadata. GPG-agent configuration controls unlock duration.

Do not inspect real credentials as part of development. Use synthetic inputs
and temporary roots; tests must not read the operator's `.env`, password store,
or XDG configuration. Tokens and profile data do not belong in CAPs, CHGs,
review assets, or fixtures.

## Stored and emitted data

| Data | Permitted destination | Operator responsibility |
| --- | --- | --- |
| GitHub token | `pass`, in-process memory, GitHub inspection request, selected child environment, explicit credential stdout | Restrict profile access and downstream consumers |
| Typed secret | Encrypted archive, selected child/process stdin, requested plaintext restore/export | Do not mark it `variable` |
| Typed variable | Public XDG JSON, selected child, GitHub Variables, public show/restore/export | Classify it as safe for plaintext first |
| Local-only assignment | Input file and any independently inherited environment | Not included in archive value payloads or injected from dotenv |
| Profile metadata/index | Restrictive local JSON | Names, notes, paths, and metadata are not encrypted; do not put secrets there |
| Eligible template | Raw encrypted template, explicit restore | Keep example files free of real/local-only values; raw text is preserved |

Only `output` and an eligible `git-credential get` response deliberately emit
token bytes to stdout. Do not invoke them in a logged context. Public `env show`
prints variables by design. Values passed to `gh ... set` or `pass insert` use
stdin, not arguments. Child stdout/stderr is not redacted; external `gh`/`pass`
error text is propagated and must not be assumed safe for indiscriminate logging.

GitHub token inspection sends an Authorization header to
`https://api.github.com/user`. Actions operations use the operator's `gh`
credentials; a stored profile is not automatically the remote authentication
identity. No separate telemetry service is implemented.

## Filesystem guarantees and limits

- Config, public payload, and index JSON writes create/chmod private directories
  to `0700`, write a `0600` adjacent temporary file, fsync the file, and replace
  the destination. This is per-file atomic replacement, not concurrent-writer
  coordination or a transaction with the password store.
- Restore/import and persistent act export use write-then-chmod and finish with
  `0600`; they do not guarantee private mode from the first byte on a newly
  created file. Use private directories and a restrictive umask. Symlink/race
  hardening and crash durability are not established by the test suite.
- `run-act` places both files in a `0700` temporary directory and cleans them
  after ordinary completion or launch failure. SIGKILL or a host crash can leave
  files behind. Persistent `.secrets`/`.vars` exports remain operator-owned;
  empty kinds do not clear pre-existing files.
- Base64 is an encoding, not encryption. Explicit `@file:` reads are not confined
  to a project directory. Quoting prevents evaluation, not access to arbitrary
  explicitly named files.
- `.gitignore` excludes dotenv/runtime exports in this repository, not in every
  consuming project. Verify ignore rules there before generating files.

## Destructive operations

`--migrate-types` removes an opposite-type remote value before setting the new
one; failure is not rolled back. `--prune` compares remote names against selected
nonempty values of the current type only. A same-name opposite-type or empty
local declaration does not protect that remote value. Run the same destructive
flags with `--dry-run` first; previews skip mutations but may query GitHub and
resolve encrypted profile references. Scope/name checks cannot verify GitHub
Secret values, which are not returned by the API.

Archive transitions and migration verify destination payloads before removing
stale/legacy entries, but multiple stores/files are not a single transaction.
Review explicit secret-to-variable classification before allowing public storage.
Full restore preserves template directives and appends extra keys without new
directives; review output before further synchronization.

## Evidence

[CAP verification sections](product/index.md) map behavior to executable tests.
The store suite runs a temporary fake pass program. GitHub inspection and gh/act
subprocess boundaries are replaced in tests. Restrictive file modes, data
partitioning, selected output shapes, cleanup, and destructive-command sequences
are asserted locally; these are not a cryptographic audit or proof of live
GitHub permissions, GPG operation, act compatibility, or PyPI trusted publishing.

There is no blanket redaction, sandbox, concurrency, interruption-recovery, or
malicious-filesystem guarantee. A material hardening change must update its CAP,
tests, active CHG, and affected DOX rather than silently strengthening these
claims in documentation.
