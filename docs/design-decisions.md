# Cross-cutting design decisions

These entries explain durable choices, not implementation progress. The live
contracts are [architecture](architecture.md), [security](security.md), root
DOX, and the [capability records](product/index.md).

## Delegate cryptography and unlocking

Tokens and secret archives use `pass`/GPG rather than an application-owned key
store. Key management and passphrase cache lifetime stay with the operator's
GPG agent. gh-vault owns profile selection and command integration, not a second
unlock/session mechanism.

## Separate public variables from secrets

An adjacent explicit directive is the sensitivity decision. Public variables
can be inspected/restored without decrypting a secret; tokens and secret values
remain behind the encrypted backend. A value-free public index supports archive
inventory. Secret-to-variable migration requires reviewed classification because
it permits plaintext persistence, not merely a different API name.

## Bind archives to repository origin

A normalized host/path gives stable storage placement, while exact origin
metadata rejects a mismatched payload. The same repository reached through a
different URL spelling can share the namespace but still fail the origin check;
normalization does not authorize rewriting stored origin metadata.

## Keep GitHub deployment scope explicit

Repository-scoped Actions values remain the default. A GitHub Environment is
selected only by `--github-environment`, never inferred from a local dotenv
profile or encoded in a value directive. This keeps local archive identity and
remote deployment policy separate, makes destructive scope visible at the
command boundary, and permits GitHub Environment names outside the local profile
grammar. Environment-targeted operations verify the target exists but do not
create or configure deployment policy.

## Make credential delivery explicit

Child-only environments, stdin for external tool writes, and narrowly named
stdout commands provide explicit consumer boundaries. They do not make the
child trusted or prevent it from logging credentials. No implicit profile
fallback is used when selection is absent.

## Keep Bitwarden SDK use behind an operator-held local boundary

The published package records only value-free named-connection metadata and a
versioned interface for one explicit project lookup. The adapter implementation
and SDK dependency remain in a separately licensed private sibling checkout that
the operator supplies by local path; gh-vault does not fetch, install, vendor, or
submodule it. This preserves the public distribution boundary without replacing
safe in-process credential transfer with argv, raw REST, or application-owned
cryptography.

Connection setup resolves an existing named bws profile before any credential is
read. Each project request rechecks that endpoint pair and rejects ambient bws
profile/server overrides, so an access token is never probed against an implicit
or drifted region. Environment and encrypted-vault credential sources are
explicit and mutually non-fallback.

## Separate current behavior, progress, and rationale

CAPs state behavior with executable evidence. An active CHG carries material
change progress; tickets state requests and archives retain receipts. DOX owns
maintenance rules, and these decisions explain cross-cutting tradeoffs. None is
a substitute for source and assertions.

The record validator is kept as dependency-free Node developer tooling so its
lifecycle, review, and visual-inventory regressions remain executable. Python
test filenames are recognized without broadening arbitrary modules into test
evidence. This does not add a JavaScript application stack or a runtime
installation requirement.
