# gh-vault brand assets

![gh-vault](logo.svg)

The mark is an octagonal vault door whose locking mechanism is a Git branch ending in a keyhole. It combines repository access, encrypted storage, and the project's explicit no-plaintext-fallback boundary.

## Assets

| File | Use |
|---|---|
| `logo.svg` | Canonical transparent lockup. |
| `logo-mark.svg` | Canonical transparent vault-door mark. |
| `logo-256.png`, `logo-512.png`, `logo-1024.png` | Raster lockup renders. |
| `social-card.svg`, `social-card.png` | Repository social preview. |

The ForgeGod-derived palette is crimson `#ca1a0f`, flame orange `#ff6a3d`, deep red `#7a0d06`, and near-black `#120706`.

## Regeneration

Install FontTools and Inkscape, then run:

```sh
python assets/build_brand_assets.py
```

`build_brand_assets.py` converts the bundled OFL-licensed Libre Baskerville font to SVG paths, writes the SVG sources, and renders the PNG files. Generated files must not be hand-edited.
