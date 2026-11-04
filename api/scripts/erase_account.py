#!/usr/bin/env python3
"""Erase an account, keeping each organisation's working-time record.

Usage:
  uv run python scripts/erase_account.py --id <account id> --yes
  uv run python scripts/erase_account.py <email>            # list matches, stop

The break-glass path beside the control plane's erasure job. It takes an
account **id**: sign-up stores an address as typed under a unique index with
no collation, so `Ana@` and `ana@` can be two accounts, and the old exact
`find_one` could miss the account a mail came from. Given an address instead,
it lists every case-insensitive match and stops, so the operator picks the id
with their eyes open. What is deleted and what is kept is
`beats.infrastructure.erasure`, and the promise it keeps is PRIVACY.md's.
Talks to the database the API's settings name (`DB_DSN`, `DB_NAME`).
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from beats.infrastructure.database import Database
from beats.infrastructure.erasure import erase_account
from beats.settings import settings


async def list_matches(email: str) -> int:
    await Database.connect(settings.db_dsn, settings.db_name)
    try:
        db = Database.get_db()
        cursor = db.users.find({"email": email}, collation={"locale": "en", "strength": 2})
        matches = [doc async for doc in cursor]
    finally:
        await Database.disconnect()
    if not matches:
        print(f"no account matches the address {email}", file=sys.stderr)
        return 1
    for doc in matches:
        print(f"{doc['_id']}  {doc.get('email', '')}")
    print("rerun with: erase_account.py --id <account id> --yes", file=sys.stderr)
    return 0


async def erase(user_id: str) -> int:
    await Database.connect(settings.db_dsn, settings.db_name)
    try:
        db = Database.get_db()
        report = await erase_account(db, user_id)
    finally:
        await Database.disconnect()
    print(f"erased {user_id}")
    for name, count in sorted(report.deleted.items()):
        print(f"  deleted {count:>6}  {name}")
    for name, count in sorted(report.retained.items()):
        print(f"  kept    {count:>6}  {name}  (an organisation's record)")
    return 0


def main(argv: list[str]) -> int:
    if len(argv) == 4 and argv[1] == "--id" and argv[3] == "--yes":
        return asyncio.run(erase(argv[2]))
    if len(argv) == 2 and not argv[1].startswith("--"):
        return asyncio.run(list_matches(argv[1]))
    print(
        "usage: erase_account.py --id <account id> --yes | erase_account.py <email>",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
