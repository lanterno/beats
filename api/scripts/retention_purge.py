#!/usr/bin/env python3
"""Purge working-time records past each organisation's retention period.

Usage: uv run python scripts/retention_purge.py [--apply]

Dry by default: prints per organisation what would go — tombstoned
ex-members' rows deleted, living members' rows unstamped (they keep them),
old timesheets and audit events gone — and touches nothing without
`--apply`. What expiry means, and why, is
`beats.infrastructure.retention`; the floors and the default are
`beats.domain.retention`. Talks to the database the API's settings name
(`DB_DSN`, `DB_NAME`). Nothing schedules this: it is the operator's act,
audited per organisation as `retention.purged`.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from beats.infrastructure.database import Database
from beats.infrastructure.retention import purge_expired_records


async def run(apply: bool) -> int:
    await Database.connect()
    try:
        report = await purge_expired_records(Database.get_db(), apply=apply)
    finally:
        await Database.disconnect()
    mode = "purged" if report.applied else "would purge (dry run; pass --apply)"
    print(f"{mode}, as of {report.today}:")
    for org in report.organisations:
        touched = {k: v for k, v in org.counts.items() if v}
        line = ", ".join(f"{k} {v}" for k, v in sorted(touched.items())) or "nothing expired"
        print(f"  {org.name} ({org.years}y, before {org.cutoff}): {line}")
    return 0


def main(argv: list[str]) -> int:
    apply = "--apply" in argv
    unknown = [a for a in argv if a not in ("--apply",)]
    if unknown:
        print(__doc__, file=sys.stderr)
        return 2
    return asyncio.run(run(apply))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
