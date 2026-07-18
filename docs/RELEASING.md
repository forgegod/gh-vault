# Releasing to PyPI

`gh-vault` uses a single source of truth for its version: `src/gh_vault/__init__.py` → `__version__`. The release workflow is: bump that string, tag, build, upload.

## Prerequisites

A PyPI account and an API token scoped to the `gh-vault` project (or account-wide). Configure the token once:

```sh
# Re-authenticate at any time; this overwrites the stored token.
uv publish --token PYPI_API_TOKEN    # placeholder; set the env var instead
```

Prefer the `UV_PUBLISH_TOKEN` environment variable and avoid storing the token on disk. `gh-vault secrets sync` can keep the value in `pass` for this repo if you maintain it locally.

## Publish a release

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

## Version policy

Follow [Semantic Versioning](https://semver.org/). Before `1.0.0`, minor bumps may include breaking changes; the project documents these in release notes.
