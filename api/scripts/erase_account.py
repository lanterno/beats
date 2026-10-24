#!/usr/bin/env python3
"""Erase an account, keeping each organisation's working-time record.

Usage: uv run python scripts/erase_account.py <email> --yes

What is deleted and what is kept is `beats.infrastructure.erasure`, and the
promise it keeps is PRIVACY.md's. Talks to the database the API's settings
name (`DB_DSN`, `DB_NAME`, from the environment or `api/.env`).
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from beats.infrastructure.database import Database
from beats.infrastructure.erasure import erase_account


async def run(email: str) -> int:
    await Database.connect()
    try:
        db = Database.get_db()
        user = await db.users.find_one({"email": email})
        if user is None:
            print(f"no account with the address {email}", file=sys.stderr)
            return 1
        report = await erase_account(db, str(user["_id"]))
    finally:
        await Database.disconnect()
    print(f"erased {email}")
    for name, count in sorted(report.deleted.items()):
        print(f"  deleted {count:>6}  {name}")
    for name, count in sorted(report.retained.items()):
        print(f"  kept    {count:>6}  {name}  (an organisation's record)")
    return 0


def main(argv: list[str]) -> int:
    if len(argv) != 3 or argv[2] != "--yes":
        print("usage: erase_account.py <email> --yes", file=sys.stderr)
        return 2
    return asyncio.run(run(argv[1]))


if __name__ == "__main__":
    sys.exit(main(sys.argv))
