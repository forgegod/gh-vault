# Release workflow

PyPI publishing is fully automated via GitHub Actions trusted publishing
(OIDC). Commits and PRs never publish; only version tags do.

## One-time setup

1. Add a pending trusted publisher on https://pypi.org/manage/account/publishing/
   (and the same on https://test.pypi.org/ if you want a dry-run target):

   - Owner: `forgegod`
   - Repository: `gh-vault`
   - Workflow filename: `publish.yml`
   - Environment name: `pypi`

   The PyPI project name must match the wheel's `Name:` field — that comes
   from `pyproject.toml`'s `[project] name`, `forgegod-gh-vault`.
   Create the PyPI project with that exact name (PyPI will accept the first
   trusted-publisher upload as the project's initial release if no project of
   that name exists yet).

2. In the GitHub repo: Settings → Environments → New environment named `pypi`.
   Under "Deployment branches" add a rule restricting deployments to the tag
   pattern `v*`. This is the gate that keeps non-tag pushes from publishing.

## Cutting a release

1. Run `make verify`, then bump `gh_vault.__version__` in `src/gh_vault/__init__.py`.
2. Commit on `main`.
3. Tag with the exact same version, prefixed `v`, and push the tag:

   ```bash
   git tag -s v0.1.0 -m "release 0.1.0"
   git push origin v0.1.0
   ```

   The tag push triggers `.github/workflows/publish.yml`, which:

   - asserts the tag (stripped of `v`) equals `gh_vault.__version__` and fails
     the build if they drift,
   - builds sdist + wheel,
   - publishes to PyPI via trusted publishing.

4. Draft a GitHub release from the tag so the changelog URL in `pyproject.toml`
   is useful.

## What does NOT publish

- Any push to a branch, including `main`.
- Any pull request.
- A tag whose version does not match `gh_vault.__version__` — the workflow
  fails before upload.
- Builds that do not land in the `pypi` environment — the GitHub environment
  gate blocks them.

## Local dry-run

```bash
uv build
uvx --from twine twine check dist/*
```

These commands build and validate package metadata; they do not upload anything.
Use a fresh output directory (`uv build --out-dir PATH`) when old artifacts are
present. Local Twine does not obtain GitHub Actions OIDC credentials merely
because a trusted publisher exists. Any TestPyPI upload needs its own authorized
authentication path and is not part of this check.

The branch/PR quality workflow runs `make verify` without credentials. The
separate tag publishing workflow builds and publishes; it does not itself run
the product test gate. Check the release revision before tagging.

## Rotation / teardown

- Trusted publishers are scoped per repo + workflow filename + environment.
  Renaming the workflow or the `pypi` environment invalidates the publisher —
  re-add it on PyPI.
- No API token is stored in GitHub, so there is nothing to rotate. To revoke
  access, delete the trusted publisher on PyPI and the `pypi` environment on
  GitHub.