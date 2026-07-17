# DOX framework

- DOX is highly performant AGENTS.md hierarchy installed here
- Agent must follow DOX instructions across any edits

## Core Contract

- AGENTS.md files are binding work contracts for their subtrees
- Work products, source materials, instructions, records, assets, and durable docs must stay understandable from the nearest applicable AGENTS.md plus every parent AGENTS.md above it

## Read Before Editing

1. Read the root AGENTS.md
2. Identify every file or folder you expect to touch
3. Walk from the repository root to each target path
4. Read every AGENTS.md found along each route
5. If a parent AGENTS.md lists a child AGENTS.md whose scope contains the path, read that child and continue from there
6. Use the nearest AGENTS.md as the local contract and parent docs for repo-wide rules
7. If docs conflict, the closer doc controls local work details, but no child doc may weaken DOX

Do not rely on memory. Re-read the applicable DOX chain in the current session before editing.

## Update After Editing

Every meaningful change requires a DOX pass before the task is done.

Update the closest owning AGENTS.md when a change affects:

- purpose, scope, ownership, or responsibilities
- durable structure, contracts, workflows, or operating rules
- required inputs, outputs, permissions, constraints, side effects, or artifacts
- user preferences about behavior, communication, process, organization, or quality
- AGENTS.md creation, deletion, move, rename, or index contents

Update parent docs when parent-level structure, ownership, workflow, or child index changes. Update child docs when parent changes alter local rules. Remove stale or contradictory text immediately. Small edits that do not change behavior or contracts may leave docs unchanged, but the DOX pass still must happen.

## Hierarchy

- Root AGENTS.md is the DOX rail: project-wide instructions, global preferences, durable workflow rules, and the top-level Child DOX Index
- Child AGENTS.md files own domain-specific instructions and their own Child DOX Index
- Each parent explains what its direct children cover and what stays owned by the parent
- The closer a doc is to the work, the more specific and practical it must be

## Child Doc Shape

- Create a child AGENTS.md when a folder becomes a durable boundary with its own purpose, rules, responsibilities, workflow, materials, or quality standards
- Work Guidance must reflect the current standards of the project or user instructions; if there are no specific standards or instructions yet, leave it empty
- Verification must reflect an existing check; if no verification framework exists yet, leave it empty and update it when one exists

Default section order:
- Purpose
- Ownership
- Local Contracts
- Work Guidance
- Verification
- Child DOX Index

## Style

- Keep docs concise, current, and operational
- Document stable contracts, not diary entries
- Put broad rules in parent docs and concrete details in child docs
- Prefer direct bullets with explicit names
- Do not duplicate rules across many files unless each scope needs a local version
- Delete stale notes instead of explaining history
- Trim obvious statements, repeated rules, misplaced detail, and warnings for risks that no longer exist

## Closeout

1. Re-check changed paths against the DOX chain
2. Update nearest owning docs and any affected parents or children
3. Refresh every affected Child DOX Index
4. Remove stale or contradictory text
5. Run existing verification when relevant
6. Report any docs intentionally left unchanged and why

## User Preferences

When the user requests a durable behavior change, record it here or in the relevant child AGENTS.md.

Project-wide durable preferences (style, workflow, conventions) live in user memory; this section is reserved for contract-level rules that bind every child doc.

- Documentation describes the current project state only; git carries the timeline and retired designs.
- Keep documentation concise and cross-reference owning docs rather than duplicating them.

## Architectural decisions

- **Agent harness protected by tirith.sh.** Reading passwords or access tokens is prohibited. Extract variables from `.env` / config files without relaying their values; use environment variables by importing them for Bash execution. `***` in output is a tirith redaction marker, not a literal value — never "fix" it to a variable ref.
- **Encrypted vault backend.** Tokens, archived project environment values, and templates belong only in `pass` entries below `gh-vault/`; project files and metadata config must never contain plaintext secret values or a fallback.
- **Intentional credential output boundary.** Token values must not reach stdout except for the exact `git-credential get` response Git requires.

## Codebase exploration — mandatory graph-first workflow

For source-code discovery, tracing, debugging, review, or impact analysis,
MUST use the `code-review-graph` MCP before `search_files`, `read_file`, grep,
glob, find, or directory scans.

1. Load the `code-review-graph` skill.
2. Call `get_minimal_context_tool` first with the explicit `repo_root`.
3. Use the recommended graph query to identify symbols, relationships, flows,
   affected files, and tests.
4. Only then use targeted file reads to verify exact implementation details.

Do not silently bypass the graph. If unavailable or stale, retry with
`repo_root`, build/update it when possible, and report the failure before
falling back to targeted file tools.

## Child DOX Index

| Child | Owns | Read when editing… |
|---|---|---|
| `src/gh_vault/AGENTS.md` | Production Python package, CLI behavior, secret backend, environment archives, and metadata persistence | `src/gh_vault/**`, console command behavior, storage, archive, or security contracts |
| `tests/AGENTS.md` | Pytest fixtures and executable CLI/store contracts | `tests/**`, test conventions, or verification coverage |

Root-owned artifacts:

- `README.md` — user-facing requirements, installation, command usage, and security model.
- `pyproject.toml` — package metadata, Python requirement, console entry points, source layout, and pytest configuration.
- `.gitignore` — generated and local-only artifacts excluded from version control.
- `LICENSE` — MIT license terms.
