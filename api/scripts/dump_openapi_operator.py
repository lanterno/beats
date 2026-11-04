"""Dump the operator API's OpenAPI schema to a JSON file.

Usage: uv run python scripts/dump_openapi_operator.py <output_path>

The shape of dump_openapi.py: imports the app without running the lifespan —
no database, no IAP. `OperatorSettings` refuses to load with neither the IAP
audience nor the dev stand-in set, so the stand-in is set here (it gates
nothing at import time; the schema is the same either way) along with an env
file that doesn't exist, so a developer's .env.operator cannot change the
dumped schema.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

os.environ.setdefault("BEATS_OPERATOR_ENV_FILE", ".env.operator.does-not-exist")
os.environ.setdefault("BACKOFFICE_DEV_OPERATOR", "schema-dump")

from operator_server import app  # the env above must be set first


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: dump_openapi_operator.py <output_path>", file=sys.stderr)
        return 2

    out = Path(argv[1])
    out.parent.mkdir(parents=True, exist_ok=True)
    schema = app.openapi()
    out.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n")
    print(f"wrote {out} ({out.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
