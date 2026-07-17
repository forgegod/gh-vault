#!/usr/bin/env python3
"""Generate the canonical gh-vault brand assets."""

from __future__ import annotations

import html
import subprocess
from functools import lru_cache
from pathlib import Path
from typing import Any, cast

from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont

CRIMSON = "#ca1a0f"
FLAME = "#ff6a3d"
DEEP_RED = "#7a0d06"
INK = "#120706"
PALE = "#fff1e8"
MUTED = "#e9b3a8"
OUT = Path(__file__).resolve().parent
FONT_PATH = OUT / "fonts" / "LibreBaskerville-wght.ttf"
WORDMARK = "GH-VAULT"
BAND_Y = 172
BAND_HEIGHT = 22
MARK_SIZE = 240
TAGLINE = "Encrypted GitHub credentials and project environments."
BOUNDARY = "GPG-encrypted in pass · no plaintext fallback"


@lru_cache(maxsize=1)
def _font() -> TTFont:
    if not FONT_PATH.is_file():
        raise SystemExit(f"required bundled font not found: {FONT_PATH}")
    variable_font = TTFont(FONT_PATH, recalcBBoxes=False, recalcTimestamp=False)
    return instantiateVariableFont(variable_font, {"wght": 700}, inplace=False)


def _text_geometry(
    text: str, *, size: float, letter_spacing: float = 0
) -> tuple[list[tuple[str, float]], float, float]:
    font = _font()
    head = cast(Any, font["head"])
    scale = size / int(head.unitsPerEm)
    cmap = font.getBestCmap()
    if cmap is None:
        raise ValueError("bundled font has no Unicode character map")
    glyph_set = font.getGlyphSet()
    metrics = font["hmtx"].metrics
    cursor = 0.0
    glyphs: list[tuple[str, float]] = []
    for index, character in enumerate(text):
        glyph_name = cmap.get(ord(character))
        if glyph_name is None:
            raise ValueError(f"bundled font has no glyph for {character!r}")
        pen = SVGPathPen(glyph_set)
        glyph_set[glyph_name].draw(pen)
        path = pen.getCommands()
        if path:
            glyphs.append((path, cursor))
        cursor += metrics[glyph_name][0]
        if index < len(text) - 1:
            cursor += letter_spacing / scale
    return glyphs, cursor * scale, scale


def _path_group(
    text: str,
    *,
    x: float,
    baseline: float,
    size: float,
    fill: str,
    letter_spacing: float = 0,
    clip_id: str | None = None,
) -> tuple[str, float]:
    glyphs, width, scale = _text_geometry(
        text, size=size, letter_spacing=letter_spacing
    )
    paths = "".join(
        f'<path d="{path}" transform="translate({offset:.4f} 0)"/>'
        for path, offset in glyphs
    )
    group = (
        f'<g transform="translate({x} {baseline}) scale({scale:.8f} {-scale:.8f})" '
        f'fill="{fill}">{paths}</g>'
    )
    if clip_id:
        group = f'<g clip-path="url(#{clip_id})">{group}</g>'
    return group, width


def _wordmark(
    *, x: float, baseline: float, size: float, prefix: str, band_y: float
) -> tuple[str, float]:
    spacing = 8 * size / 154
    crimson, width = _path_group(
        WORDMARK,
        x=x,
        baseline=baseline,
        size=size,
        fill=CRIMSON,
        letter_spacing=spacing,
    )
    flame, _ = _path_group(
        WORDMARK,
        x=x,
        baseline=baseline,
        size=size,
        fill=FLAME,
        letter_spacing=spacing,
        clip_id=f"{prefix}-word-band",
    )
    return (
        f'  <defs><clipPath id="{prefix}-word-band">'
        f'<rect x="{x - 4:.2f}" y="{band_y:.2f}" width="{width + 8:.2f}" '
        f'height="{BAND_HEIGHT:.2f}"/></clipPath></defs>\n'
        f'  {crimson}\n  {flame}',
        width,
    )


# An octagonal vault door carries a Git branch as its locking mechanism. The
# centered keyhole terminates the branch, tying repository access to encryption.
VAULT_BODY = "M72 18H168L222 72V168L168 222H72L18 168V72Z"
INNER_RING = "M120 48A72 72 0 1 1 119.9 48Z"
BRANCH = "M120 80V154M120 112H78V82M120 126H164V96"
KEYHOLE = "M120 143A15 15 0 0 1 130 169L136 197H104L110 169A15 15 0 0 1 120 143Z"


def _mark(*, x: float, y: float, scale: float, prefix: str, band_y: float) -> str:
    tx = x
    ty = y
    outer_band_y = (band_y - ty) / scale
    return f"""  <defs>
    <clipPath id="{prefix}-mark-band">
      <rect x="0" y="{outer_band_y:.3f}" width="{MARK_SIZE}" height="{BAND_HEIGHT / scale:.3f}"/>
    </clipPath>
  </defs>
  <g transform="translate({tx} {ty}) scale({scale})">
    <path d="{VAULT_BODY}" fill="{CRIMSON}"/>
    <path d="{VAULT_BODY}" fill="{FLAME}" clip-path="url(#{prefix}-mark-band)"/>
    <path d="{INNER_RING}" fill="none" stroke="{DEEP_RED}" stroke-width="12"/>
    <path d="{BRANCH}" fill="none" stroke="{DEEP_RED}" stroke-width="13" stroke-linecap="round" stroke-linejoin="round"/>
    <circle cx="78" cy="76" r="13" fill="{DEEP_RED}"/>
    <circle cx="164" cy="90" r="13" fill="{DEEP_RED}"/>
    <circle cx="120" cy="73" r="13" fill="{DEEP_RED}"/>
    <path d="{KEYHOLE}" fill="{INK}"/>
    <circle cx="120" cy="159" r="8" fill="{FLAME}"/>
  </g>"""


def _logo_svg() -> str:
    mark_x, mark_y, mark_scale = 42, 18, 1.0
    word_x = 342
    word, width = _wordmark(
        x=word_x,
        baseline=208,
        size=154,
        prefix="gh-vault",
        band_y=BAND_Y,
    )
    mark = _mark(
        x=mark_x,
        y=mark_y,
        scale=mark_scale,
        prefix="gh-vault",
        band_y=BAND_Y,
    )
    total_width = round(word_x + width + 62)
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {total_width} 276"
  role="img" aria-labelledby="title desc">
  <title id="title">gh-vault</title>
  <desc id="desc">An octagonal vault door with a Git branch lock beside the GH-VAULT wordmark</desc>
{mark}
{word}
</svg>
"""


def _mark_svg() -> str:
    mark = _mark(
        x=40,
        y=40,
        scale=1.0,
        prefix="gh-vault-mark",
        band_y=194,
    )
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 320 320"
  role="img" aria-labelledby="title desc">
  <title id="title">gh-vault mark</title>
  <desc id="desc">An octagonal vault door with a Git branch locking mechanism and keyhole</desc>
{mark}
</svg>
"""


def _solid_text(text: str, *, x: float, baseline: float, size: float, fill: str) -> str:
    group, _ = _path_group(text, x=x, baseline=baseline, size=size, fill=fill)
    return group


def _social_card_svg() -> str:
    band_y = 169
    mark = _mark(
        x=70,
        y=58,
        scale=0.72,
        prefix="social",
        band_y=band_y,
    )
    word, _ = _wordmark(
        x=286,
        baseline=196,
        size=112,
        prefix="social",
        band_y=band_y,
    )
    tagline = _solid_text(TAGLINE, x=78, baseline=360, size=30, fill=PALE)
    boundary = _solid_text(BOUNDARY, x=78, baseline=520, size=22, fill=MUTED)
    description = html.escape(f"{TAGLINE} {BOUNDARY}.")
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 630"
  role="img" aria-labelledby="title desc">
  <title id="title">gh-vault — encrypted GitHub credentials</title>
  <desc id="desc">{description}</desc>
  <rect width="1200" height="630" fill="{INK}"/>
  <path d="M0 500C225 420 390 590 620 500C830 418 970 458 1200 398V630H0Z" fill="{DEEP_RED}" opacity="0.45"/>
  <path d="M0 556C235 478 402 626 650 532C864 452 1012 506 1200 448V630H0Z" fill="{CRIMSON}" opacity="0.42"/>
{mark}
{word}
  <rect x="78" y="274" width="1044" height="3" fill="{FLAME}"/>
  {tagline}
  <rect x="78" y="468" width="1044" height="1" fill="{DEEP_RED}"/>
  {boundary}
</svg>
"""


def _render(svg_path: Path, png_path: Path, *, width: int) -> None:
    subprocess.run(
        [
            "inkscape",
            str(svg_path),
            "--export-type=png",
            f"--export-filename={png_path}",
            f"--export-width={width}",
        ],
        check=True,
        cwd=OUT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def main() -> None:
    logo_svg = OUT / "logo.svg"
    mark_svg = OUT / "logo-mark.svg"
    social_svg = OUT / "social-card.svg"
    logo_svg.write_text(_logo_svg(), encoding="utf-8")
    mark_svg.write_text(_mark_svg(), encoding="utf-8")
    social_svg.write_text(_social_card_svg(), encoding="utf-8")
    for width in (256, 512, 1024):
        _render(logo_svg, OUT / f"logo-{width}.png", width=width)
    _render(social_svg, OUT / "social-card.png", width=1200)
    print("wrote logo, mark, and social-card assets")


if __name__ == "__main__":
    main()
