#!/usr/bin/env python3
"""Render the day ring from `shared/brand/` into every icon the surfaces ship.

The mark is drawn once, by hand, in four SVGs:

- `mark.svg`      the rounded tile: the PWA's "any" icons.
- `maskable.svg`  the same mark full-bleed, for launchers that cut their own
                  shape (the PWA's maskable icon, iOS's touch icon).
- `favicon.svg`   redrawn on a 32 grid with heavier strokes and no tile, so
                  the ring reads in a browser tab and the tab strip shows
                  through; it carries its own light and dark colours.
- `macos.svg`     the tile on Apple's 1024 grid, with its shadow.

This script copies or rasterizes them into the SPA's `public/` and every
target of the companion: the macOS and iOS AppIcon sets, Android's launcher
mipmaps, the Windows .ico and the Flutter web shell. Android's adaptive icon
is a vector drawable kept by hand beside the mipmaps, not rendered here.
Change an SVG, run this, commit what it wrote.
Rasterizing needs `rsvg-convert` (`brew install librsvg`).
"""

from __future__ import annotations

import json
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
COMPANION = ROOT / "companion"
APPICON = COMPANION / "macos" / "Runner" / "Assets.xcassets" / "AppIcon.appiconset"
IOS_APPICON = COMPANION / "ios" / "Runner" / "Assets.xcassets" / "AppIcon.appiconset"
ANDROID_RES = COMPANION / "android" / "app" / "src" / "main" / "res"
WINDOWS_ICO = COMPANION / "windows" / "runner" / "resources" / "app_icon.ico"
COMPANION_WEB = COMPANION / "web"

MAC_SIZES = (16, 32, 64, 128, 256, 512, 1024)
ICO_SIZES = (16, 32, 48)
# Android's legacy launcher icon is 48dp, at each density bucket.
ANDROID_SIZES = {"mdpi": 48, "hdpi": 72, "xhdpi": 96, "xxhdpi": 144, "xxxhdpi": 192}
WINDOWS_SIZES = (16, 24, 32, 48, 64, 128, 256)


def render(svg: Path, size: int, out: Path) -> None:
    subprocess.run(
        ["rsvg-convert", "-w", str(size), "-h", str(size), "-o", str(out), str(svg)],
        check=True,
    )


def rendered(svg: Path, size: int, tmp: Path) -> bytes:
    out = tmp / f"{svg.stem}-{size}.png"
    render(svg, size, out)
    return out.read_bytes()


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
        write_ico(
            [(size, rendered(SOURCE / "favicon.svg", size, Path(tmp))) for size in ICO_SIZES],
            PUBLIC / "favicon.ico",
        )
        write_ico(
            [(size, rendered(SOURCE / "mark.svg", size, Path(tmp))) for size in WINDOWS_SIZES],
            WINDOWS_ICO,
        )

    for size in MAC_SIZES:
        render(SOURCE / "macos.svg", size, APPICON / f"app_icon_{size}.png")

    # iOS cuts its own corners and refuses transparency: the full-bleed copy.
    contents = json.loads((IOS_APPICON / "Contents.json").read_text())
    for image in contents["images"]:
        points = float(image["size"].split("x")[0])
        scale = int(image["scale"].rstrip("x"))
        render(SOURCE / "maskable.svg", round(points * scale), IOS_APPICON / image["filename"])

    for bucket, size in ANDROID_SIZES.items():
        render(SOURCE / "mark.svg", size, ANDROID_RES / f"mipmap-{bucket}" / "ic_launcher.png")

    render(SOURCE / "favicon.svg", 16, COMPANION_WEB / "favicon.png")
    for size in (192, 512):
        render(SOURCE / "mark.svg", size, COMPANION_WEB / "icons" / f"Icon-{size}.png")
        render(SOURCE / "maskable.svg", size, COMPANION_WEB / "icons" / f"Icon-maskable-{size}.png")

    return 0


if __name__ == "__main__":
    sys.exit(main())
