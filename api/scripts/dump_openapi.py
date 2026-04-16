"""Dump the FastAPI OpenAPI schema to a JSON file.

Usage: uv run python scripts/dump_openapi.py <output_path>

Imports the app without triggering the lifespan (no DB connection required) and
writes a pretty-printed, key-sorted JSON schema. The deterministic ordering lets
CI detect drift with a plain `git diff --exit-code`.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from server import app


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: dump_openapi.py <output_path>", file=sys.stderr)
        return 2

    out = Path(argv[1])
    out.parent.mkdir(parents=True, exist_ok=True)
    schema = app.openapi()
    out.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n")
    print(f"wrote {out} ({out.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
