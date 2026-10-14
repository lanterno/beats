#!/usr/bin/env python3
"""Render the day ring from `shared/brand/` into every icon the surfaces ship.

The mark is drawn once, by hand, in four SVGs:

- `mark.svg`      the rounded tile: the PWA's "any" icons.
- `maskable.svg`  the same mark full-bleed, for launchers that cut their own
                  shape (the PWA's maskable icon, iOS's touch icon).
- `favicon.svg`   redrawn on a 32 grid with heavier strokes, so the ring
                  still reads in a browser tab.
- `macos.svg`     the tile on Apple's 1024 grid, with its shadow.

This script copies or rasterizes them into the SPA's `public/` and the Mac
companion's AppIcon set. Change an SVG, run it, commit what it wrote.
Rasterizing needs `rsvg-convert` (`brew install librsvg`).
"""

from __future__ import annotations

import re
import shutil
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "shared" / "brand"
PUBLIC = ROOT / "ui" / "public"
APPICON = ROOT / "companion" / "macos" / "Runner" / "Assets.xcassets" / "AppIcon.appiconset"

MAC_SIZES = (16, 32, 64, 128, 256, 512, 1024)
ICO_SIZES = (16, 32, 48)


def render(svg: Path, size: int, out: Path) -> None:
    subprocess.run(
        ["rsvg-convert", "-w", str(size), "-h", str(size), "-o", str(out), str(svg)],
        check=True,
    )


def sized(svg: Path, size: int) -> str:
    """The SVG's text with its width and height set to [size]."""
    text = svg.read_text()
    text = re.sub(r'width="\d+"', f'width="{size}"', text, count=1)
    return re.sub(r'height="\d+"', f'height="{size}"', text, count=1)


def write_ico(pngs: list[tuple[int, bytes]], out: Path) -> None:
    """An .ico holding each PNG as is, which every current browser reads."""
    header = struct.pack("<HHH", 0, 1, len(pngs))
    offset = len(header) + 16 * len(pngs)
    entries, blobs = b"", b""
    for size, data in pngs:
        dim = 0 if size >= 256 else size
        entries += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(data), offset + len(blobs))
        blobs += data
    out.write_bytes(header + entries + blobs)


def main() -> int:
    if shutil.which("rsvg-convert") is None:
        print("rsvg-convert not found: brew install librsvg", file=sys.stderr)
        return 1

    shutil.copyfile(SOURCE / "favicon.svg", PUBLIC / "favicon.svg")
    (PUBLIC / "pwa-192.svg").write_text(sized(SOURCE / "mark.svg", 192))
    (PUBLIC / "pwa-512.svg").write_text(sized(SOURCE / "mark.svg", 512))
    (PUBLIC / "pwa-maskable-512.svg").write_text(sized(SOURCE / "maskable.svg", 512))
    render(SOURCE / "maskable.svg", 180, PUBLIC / "apple-touch-icon.png")

    with tempfile.TemporaryDirectory() as tmp:
        pngs = []
        for size in ICO_SIZES:
            png = Path(tmp) / f"{size}.png"
            render(SOURCE / "favicon.svg", size, png)
            pngs.append((size, png.read_bytes()))
        write_ico(pngs, PUBLIC / "favicon.ico")

    for size in MAC_SIZES:
        render(SOURCE / "macos.svg", size, APPICON / f"app_icon_{size}.png")

    return 0


if __name__ == "__main__":
    sys.exit(main())
