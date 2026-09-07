#!/usr/bin/env python3
"""Regenerate the bundle-id → app-name tables from `shared/app-labels.json`.

The same 26 mappings are needed by the daemon (Go), the web UI (TypeScript) and
the companion (Dart), and were maintained by hand in all three. They happened to
agree, but nothing enforced it: the parity tests assert shared *cases*, not that
the tables match, so adding an app to one and forgetting the others would pass.

Run with --check to fail when the committed tables are stale, which is what CI
and the pre-push hook do.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "shared" / "app-labels.json"

BANNER = "Generated from shared/app-labels.json by scripts/gen_app_labels.py — do not edit."


def _go(labels: dict[str, str]) -> str:
    width = max(len(f'"{k}":') for k in labels)
    rows = "\n".join(f'\t{f'"{k}":':<{width}} "{v}",' for k, v in labels.items())
    return f"// {BANNER}\nvar appLabels = map[string]string{{\n{rows}\n}}\n"


def _ts(labels: dict[str, str]) -> str:
    rows = "\n".join(f'\t"{k}": "{v}",' for k, v in labels.items())
    return f"// {BANNER}\nconst APP_LABELS: Record<string, string> = {{\n{rows}\n}};\n"


def _dart(labels: dict[str, str]) -> str:
    rows = "\n".join(f"  '{k}': '{v}'," for k, v in labels.items())
    return f"// {BANNER}\nconst Map<String, String> _appLabels = {{\n{rows}\n}};\n"


TARGETS = [
    (ROOT / "daemon/internal/bundle/label.go", "var appLabels = map[string]string{", "}\n", _go),
    (
        ROOT / "ui/client/shared/lib/bundleLabel.ts",
        "const APP_LABELS: Record<string, string> = {",
        "};\n",
        _ts,
    ),
    (
        ROOT / "companion/lib/services/bundle_label.dart",
        "const Map<String, String> _appLabels = {",
        "};\n",
        _dart,
    ),
]


def render(path: Path, start: str, end: str, build) -> str:
    """Splice a freshly built table into the file, leaving everything else alone."""
    text = path.read_text(encoding="utf-8")
    begin = text.index(start)
    # Swallow a banner line previously emitted above the table, so repeated
    # runs replace it rather than stacking another copy on top.
    line_start = text.rfind("\n", 0, begin - 1) + 1
    if BANNER in text[line_start:begin]:
        begin = line_start
    finish = text.index(end, text.index(start)) + len(end)
    return text[:begin] + build(json.loads(SOURCE.read_text())) + text[finish:]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="fail if a table is out of date")
    args = parser.parse_args()

    stale: list[Path] = []
    for path, start, end, build in TARGETS:
        updated = render(path, start, end, build)
        if updated == path.read_text(encoding="utf-8"):
            continue
        if args.check:
            stale.append(path)
        else:
            path.write_text(updated, encoding="utf-8")
            print(f"regenerated {path.relative_to(ROOT)}")

    if stale:
        print(
            "app-label tables are out of date:\n  "
            + "\n  ".join(str(p.relative_to(ROOT)) for p in stale)
            + "\nRun: python3 scripts/gen_app_labels.py",
            file=sys.stderr,
        )
        return 1
    if args.check:
        print("app-label tables are up to date")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
