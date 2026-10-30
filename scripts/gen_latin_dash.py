#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["fonttools>=4.50,<5"]
# ///
"""Cut the companion's Latin face for two characters out of M PLUS Rounded 1c.

Zen Maru Gothic, the companion's body face, draws the em dash as the
full-width Japanese bar: a hairline a whole character wide, set above the
hyphen and running past its own advance, so it touches the words either side.
Its en dash is already a Latin one. Flutter has no `unicode-range`, but it
does fall back per character: a face that holds those characters and nothing
else, first in the body stack with Zen Maru behind it, draws them and leaves
every other character to Zen Maru. That is the web's "Latin Dash" face
(`ui/client/global.css`) by the only route Flutter has; `SkyType` in
`companion/lib/theme/sky.dart` puts it in front.

The minus sign is the second character, added in #376. Zen Maru draws U+2212
at 922 units against a digit's 504 — nearly two digits wide — and the balance
chip and the coach's standing set it in body text ("−25m behind overall"), so
the gap after the sign read as a gap in the sentence. M PLUS's is 734.

The ellipsis, U+2026, was proposed with it and is not here: Zen Maru draws it
at 922 and M PLUS at 1000, so taking it from M PLUS would make it wider, not
narrower. Nothing in the two faces the companion already carries draws a
Latin-width ellipsis, and the fix is a third face or different copy, not this
script. The web has neither problem once its unicode-range covers both
characters, because its Latin face is the system's.

The glyphs are M PLUS Rounded 1c's, the companion's other rounded face, at the
two weights body text is set in. The face takes Zen Maru's line metrics, so a
line with one in it is as tall as a line without, and an underline runs
straight through it.

Run it with `uv run scripts/gen_latin_dash.py`, which brings fontTools, and
commit what it wrote. The source is pinned to a google/fonts commit and each
file's hash, so a run writes the same bytes.
"""

from __future__ import annotations

import hashlib
import sys
import urllib.request
from io import BytesIO
from pathlib import Path

from fontTools import subset
from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "companion" / "assets" / "fonts"
FAMILY = "LatinDash"
SOURCE = (
    "https://raw.githubusercontent.com/google/fonts/"
    "84efd8ad78c3710ad14bd909e3bc407151885628/ofl/mplusrounded1c/MPLUSRounded1c-{style}.ttf"
)
SHA256 = {
    "Regular": "b75708b53e45b06d17d470aeeca5b766e3d1b3999f03f13ec4eb863ca846c14c",
    "Bold": "c358630584e8e2d8fbd6121d0f4693255ffef6d1e6d4f3441fd6e5a963a11f9e",
}
# The characters this face stands in for, and only these: anything more would
# take that character from Zen Maru in every line of body text. Each one is
# here because Zen Maru's is the full-width Japanese form, and M PLUS's is
# measurably narrower — check the advance before adding a third.
EM_DASH = 0x2014
MINUS = 0x2212
HELD = {EM_DASH, MINUS}

# Zen Maru Gothic's own line metrics, at the weight each face stands in for.
# Flutter lays a line out to the tallest ascent and the deepest descent among
# its runs, so a dash face with M PLUS's (1075/-320, a different split) would
# make every line holding a dash a little taller than its neighbours; and it
# draws an underline or a strike-through run by run, so M PLUS's would step
# down and thicken under the dash.
_VERTICAL = {
    "hhea": {"ascent": 1160, "descent": -288, "lineGap": 0},
    "OS/2": {
        "sTypoAscender": 880,
        "sTypoDescender": -120,
        "sTypoLineGap": 0,
        "usWinAscent": 1160,
        "usWinDescent": 288,
        "yStrikeoutSize": 20,
    },
    "post": {"underlinePosition": -133, "underlineThickness": 20},
}
ZEN_MARU = {
    "Regular": _VERTICAL | {"OS/2": _VERTICAL["OS/2"] | {"yStrikeoutPosition": 287}},
    "Bold": _VERTICAL | {"OS/2": _VERTICAL["OS/2"] | {"yStrikeoutPosition": 289}},
}

# Copyright, the names, and the licence and its URL: OFL wants the notice and
# the licence to travel with every copy, and a subset keeps only what it is told.
NAME_IDS = [0, 1, 2, 3, 4, 5, 6, 13, 14]


def fetch(style: str) -> bytes:
    url = SOURCE.format(style=style)
    with urllib.request.urlopen(url) as response:
        data = response.read()
    digest = hashlib.sha256(data).hexdigest()
    if digest != SHA256[style]:
        sys.exit(f"{url}\n  sha256 {digest}, expected {SHA256[style]}")
    return data


def cut(data: bytes, style: str) -> TTFont:
    font = TTFont(BytesIO(data), recalcTimestamp=False)
    options = subset.Options()
    options.name_IDs = NAME_IDS
    options.layout_features = []  # a glyph each: nothing to substitute or kern
    subsetter = subset.Subsetter(options)
    subsetter.populate(unicodes=sorted(HELD))
    subsetter.subset(font)

    for table, values in ZEN_MARU[style].items():
        for key, value in values.items():
            setattr(font[table], key, value)

    # A modified font should not pass for the original.
    for record in font["name"].names:
        if record.nameID == 1:
            record.string = FAMILY
        elif record.nameID in (3, 6):
            record.string = f"{FAMILY}-{style}"
        elif record.nameID == 4:
            record.string = f"{FAMILY} {style}"

    held = set(font.getBestCmap())
    if held != HELD:
        sys.exit(
            f"{style}: the face holds {sorted(hex(c) for c in held)}, "
            f"not {sorted(hex(c) for c in HELD)}"
        )
    return font


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    for style in SHA256:
        path = OUT / f"{FAMILY}-{style}.ttf"
        cut(fetch(style), style).save(path)
        print(f"wrote {path.relative_to(ROOT)} ({path.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
