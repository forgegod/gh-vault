# CHG-006 — Bitwarden-backed token profiles

**Status:** done
**External request:** Direct operator request: "Implement the on-demand binding as the new explicit profile backend"
**Impacts:** CAP-001, CAP-002, CAP-003, CAP-006, CAP-007
**Baseline:** `f399f258602095f300b2bfdabe28f3275fd9fba5`

| # | Phase | Status | Verification gate |
| --- | --- | --- | --- |
| 1 | Specify the binding boundary and evidence | done (binding metadata and consumer/error contracts reviewed) | Binding contract, affected CAPs, and focused regression cases are reviewed |
| 2 | Implement one explicit profile backend | done (`uv run --no-project --with pytest python -m pytest tests/test_store.py tests/test_bitwarden_connection.py tests/test_bitwarden_profiles.py tests/test_cli.py tests/test_vault_features.py -q`) | Focused token, Bitwarden, CLI, and dotenv tests exit 0 |
| 3 | Integrate and close records | done (`make verify`) | `make verify` exits 0; current CAPs and contracts agree; archived CHG is indexed |

## Phase 1 — Specify the binding boundary and evidence

**Goal:** Replace the pass-only token-profile assumption with an explicit local or Bitwarden backend without copying or caching a GitHub token.

1. Keep existing `set` profiles backed by `pass` and compatible with existing metadata.
2. Add an explicit binding command that records only a configured connection, canonical project and entry IDs, expected key, selected local adapter path, and one non-fallback Bitwarden credential source.
3. Resolve a Bitwarden-bound profile only when a token consumer requests it. Revalidate the connection endpoint and reject ambient bws overrides; load only the selected local adapter; require exact project, organization, key, and entry-ID validation. Do not persist token bytes, hashes, or a fallback pass copy.
4. Make profile removal backend-aware: delete only pass-backed token entries; unbind Bitwarden-backed metadata without mutating the remote item.
5. Preserve intentionally explicit consumer boundaries: output and Git credential can emit a resolved token; run and dotenv consumers receive it only in-process. `find` resolves each configured profile without printing values.

**Verification gate:** Synthetic tests prove value-free metadata, exact remote entry validation before binding, and errors for endpoint drift, ambient bws overrides, missing selected credentials, entry-ID/key mismatches, and metadata-only profile removal. Existing consumer tests exercise the shared `VaultStore.get` resolution boundary without printing token values.

## Phase 2 — Implement one explicit profile backend

**Goal:** Add the parser, metadata model, unified resolver, and public consumer behavior.

1. Add the binding parser and local profile metadata schema with legacy pass-profile compatibility.
2. Implement exact Bitwarden binding validation and on-demand retrieval through the existing local-adapter read contract.
3. Route profile consumers and typed dotenv references through the unified resolver.

**Verification gate:** `uv run --no-project --with pytest python -m pytest tests/test_cli.py tests/test_store.py tests/test_bitwarden_connection.py tests/test_bitwarden_profiles.py tests/test_vault_features.py` exits 0.

## Phase 3 — Integrate and close records

**Goal:** Reconcile the approved storage-backend decision and current operator documentation with tested behavior.

1. Update the affected CAPs, root/child DOX, architecture, security, design decisions, and README without documenting token values or adapter SDK calls.
2. Run records and full offline verification, then archive this receipt and refresh the change index.

**Verification gate:** `make verify` exits 0.

## Out of scope

- Automatic pass-to-Bitwarden migration, mirroring, caching, polling, or remote deletion.
- Changes to the private Bitwarden adapter API or SDK implementation.
- Fallback between Bitwarden and pass, or fallback between Bitwarden credential sources.
- Live Bitwarden, GitHub, GPG, password-store, or release operations.
