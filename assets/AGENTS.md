# assets/

## Purpose

Own the canonical gh-vault identity, deterministic generator, raster renders, and bundled font license.

## Ownership

- `build_brand_assets.py` is the source of generated geometry, palette, copy, and rendering.
- `logo.svg` and `logo-mark.svg` are canonical transparent vector assets.
- `social-card.svg` is the canonical social-preview composition.
- PNG files are deterministic renders generated from the SVG assets.
- `fonts/` contains the bundled Libre Baskerville font and its OFL license.

## Local Contracts

- Keep the octagonal vault-door mark with its Git-branch locking mechanism and keyhole.
- Use the ForgeGod-derived crimson `#ca1a0f`, flame `#ff6a3d`, deep red `#7a0d06`, and near-black `#120706` palette.
- Keep logo and mark backgrounds transparent.
- Render wordmarks as generated SVG paths from the bundled font; do not depend on system fonts.
- Do not hand-edit generated SVG or PNG files; edit and run `build_brand_assets.py`.

## Work Guidance

- Run `python assets/build_brand_assets.py` with FontTools installed and Inkscape available.
- Generate SVG sources before rendering PNG files from them.

## Verification

- Run the generator twice and compare hashes.
- Confirm PNG dimensions, alpha content, accessible SVG titles, and social-card copy.
- Inspect the logo, mark, and social card for clipping, contrast, and small-size legibility.

## Child DOX Index

| Path | Owns |
|---|---|
| `build_brand_assets.py` | Deterministic geometry, typography, copy, and rendering. |
| `logo.svg`, `logo-mark.svg` | Canonical lockup and standalone mark. |
| `logo-*.png` | 256, 512, and 1024 pixel lockup renders. |
| `social-card.svg`, `social-card.png` | Canonical social-preview source and render. |
| `fonts/` | Libre Baskerville font and OFL license. |

See [`/AGENTS.md`](../AGENTS.md).
