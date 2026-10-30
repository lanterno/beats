#!/usr/bin/env python3
"""Stamp the product name from `shared/brand.json` into every surface that shows it.

The name people see is needed by the SPA, the API and the companion, and the
companion alone carries it in eight native files — Info.plists, the Android
manifest, the Windows and Linux runners, its web shell — none of which can
import code. Each surface keeps one constant its own code reads (`brand.ts`,
`brand.py`, `brand.dart`); this script writes the same value into those and into
the native files, so changing the name is one edit here plus one run.

Build identifiers are deliberately not targets: bundle IDs, package and binary
names, `beats_companion.app`. They are not shown as a name, and changing them
changes the installed app's identity.

Run with --check to fail when a target is stale, which is what CI and the
pre-push hook do. A target whose pattern no longer matches exactly once is an
error either way: it means the file moved on and the stamp would silently miss.

--check also reads the three code trees for the name written out by hand,
which the stamp cannot catch and so used to accumulate (#376 found five in
one companion screen). A literal is not stale, it is simply not the constant,
and a rename would leave it saying the old name in the middle of the new one.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "shared" / "brand.json"

# The name lands inside Dart, TS, Python, C, XML, JSON and .rc string literals.
# Keeping it to characters none of them escape is simpler than escaping for each.
SAFE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9 .-]*")

# (file, text before the name, text after it). Both are regexes; the name
# between them is whatever is there now, so a rename rewrites the old value.
TARGETS: list[tuple[str, str, str]] = [
    ("ui/client/shared/config/brand.ts", r'export const APP_NAME = "', r'";'),
    ("api/src/beats/brand.py", r'APP_NAME = "', r'"'),
    ("companion/lib/brand.dart", r"const String appName = '", r"';"),
    ("companion/macos/Runner/Info.plist", r"<key>CFBundleName</key>\s*<string>", r"</string>"),
    (
        "companion/macos/Runner/Info.plist",
        r"<key>CFBundleDisplayName</key>\s*<string>",
        r"</string>",
    ),
    ("companion/ios/Runner/Info.plist", r"<key>CFBundleName</key>\s*<string>", r"</string>"),
    (
        "companion/ios/Runner/Info.plist",
        r"<key>CFBundleDisplayName</key>\s*<string>",
        r"</string>",
    ),
    ("companion/android/app/src/main/AndroidManifest.xml", r'android:label="', r'"'),
    ("companion/web/manifest.json", r'"name": "', r'"'),
    ("companion/web/manifest.json", r'"short_name": "', r'"'),
    ("companion/web/index.html", r'"apple-mobile-web-app-title" content="', r'"'),
    ("companion/web/index.html", r"<title>", r"</title>"),
    ("companion/windows/runner/main.cpp", r'window\.Create\(L"', r'"'),
    ("companion/windows/runner/Runner.rc", r'"FileDescription", "', r'"'),
    ("companion/windows/runner/Runner.rc", r'"ProductName", "', r'"'),
    ("companion/linux/runner/my_application.cc", r'gtk_header_bar_set_title\(header_bar, "', r'"'),
    ("companion/linux/runner/my_application.cc", r'gtk_window_set_title\(window, "', r'"'),
]


# The code that may name the product: the constants the stamp writes, which
# every other file reads through. A name in any other file under these trees
# is a literal, whatever it is spelled in.
CODE_TREES = ("ui/client", "api/src", "companion/lib")
CODE_SUFFIXES = (".ts", ".tsx", ".py", ".dart")
NAMING_FILES = {
    "ui/client/shared/config/brand.ts",
    "api/src/beats/brand.py",
    "companion/lib/brand.dart",
}
# A comment may say the name — it is prose about the product, not text anyone
# reads in the app. Crude but on the right side of the mistake: a false
# negative here is a literal that stays, a false positive is a failing check
# nobody can satisfy.
COMMENT = re.compile(r"\s*(//|///|#|\*|/\*)")


def literals(name: str) -> list[str]:
    """Where the name is written out instead of read from the constant."""
    found = []
    for tree in CODE_TREES:
        for path in sorted((ROOT / tree).rglob("*")):
            if path.suffix not in CODE_SUFFIXES or not path.is_file():
                continue
            rel = path.relative_to(ROOT).as_posix()
            if rel in NAMING_FILES:
                continue
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if name in line and not COMMENT.match(line):
                    found.append(f"{rel}:{number}: {line.strip()}")
    return found


def load_name() -> str:
    name = json.loads(SOURCE.read_text(encoding="utf-8"))["name"]
    if not SAFE_NAME.fullmatch(name):
        raise SystemExit(
            f"{SOURCE.relative_to(ROOT)}: name {name!r} must be letters, digits, spaces, "
            "dots or hyphens"
        )
    return name


def stamp(text: str, before: str, after: str, name: str, where: str) -> str:
    pattern = re.compile(f"({before})[^\"'<\\n]*({after})")
    stamped, count = pattern.subn(lambda m: m.group(1) + name + m.group(2), text)
    if count != 1:
        raise SystemExit(f"{where}: expected one match for {before!r}, found {count}")
    return stamped


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="fail if a target is out of date")
    args = parser.parse_args()

    name = load_name()
    files: dict[str, str] = {}
    for rel, before, after in TARGETS:
        if rel not in files:
            files[rel] = (ROOT / rel).read_text(encoding="utf-8")
        files[rel] = stamp(files[rel], before, after, name, rel)

    stale: list[str] = []
    for rel, updated in files.items():
        path = ROOT / rel
        if updated == path.read_text(encoding="utf-8"):
            continue
        if args.check:
            stale.append(rel)
        else:
            path.write_text(updated, encoding="utf-8")
            print(f"stamped {rel}")

    if stale:
        print(
            "the product name is out of date in:\n  "
            + "\n  ".join(stale)
            + "\nRun: python3 scripts/gen_brand.py",
            file=sys.stderr,
        )
        return 1
    if args.check:
        written_out = literals(name)
        if written_out:
            print(
                f"the product name is written out rather than read from the constant:\n  "
                + "\n  ".join(written_out)
                + "\nRead it from brand.ts / brand.py / brand.dart instead.",
                file=sys.stderr,
            )
            return 1
        print(f"product name {name!r} is current in {len(files)} files, and written out nowhere")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
