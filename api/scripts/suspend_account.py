#!/usr/bin/env python3
"""Suspend or unsuspend an account, or sign it out everywhere.

Usage:
  uv run python scripts/suspend_account.py <email> suspend --kind abuse --reason "..." --yes
  uv run python scripts/suspend_account.py <email> unsuspend --yes
  uv run python scripts/suspend_account.py <email> sign-out --yes

The rules are `beats.domain.accounts.AccountService`, which the control
plane's commands will drive once it exists (roadmaps/backoffice.md step 3);
until then this script is the way the operator invokes them. Enforcement is
the API middleware's cached lookup, so a change here takes effect on every
instance within its TTL (30 seconds). The reason is the operator's own and is
never shown to the person. Talks to the database the API's settings name
(`DB_DSN`, `DB_NAME`, from the environment or `api/.env`).
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from beats.domain.accounts import AccountService
from beats.domain.models import SuspensionKind
from beats.infrastructure.database import Database
from beats.infrastructure.repositories import MongoUserRepository
from beats.settings import settings


async def run(email: str, args: argparse.Namespace) -> int:
    await Database.connect(settings.db_dsn, settings.db_name)
    try:
        db = Database.get_db()
        doc = await db.users.find_one({"email": email})
        if doc is None:
            print(f"no account with the address {email}", file=sys.stderr)
            return 1
        service = AccountService(MongoUserRepository(db.users))
        user_id = str(doc["_id"])
        if args.action == "suspend":
            await service.suspend(
                user_id,
                kind=SuspensionKind(args.kind),
                reason=args.reason,
                by="script",
            )
            print(f"suspended {email} ({args.kind})")
        elif args.action == "unsuspend":
            await service.unsuspend(user_id)
            print(f"unsuspended {email}")
        else:
            await service.sign_out_everywhere(user_id)
            print(f"signed {email} out everywhere (devices stay paired)")
    finally:
        await Database.disconnect()
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Suspend or unsuspend an account, or sign it out everywhere."
    )
    parser.add_argument("email", help="the exact address on the account")
    sub = parser.add_subparsers(dest="action", required=True)

    suspend = sub.add_parser("suspend")
    suspend.add_argument(
        "--kind",
        choices=[k.value for k in SuspensionKind if k is not SuspensionKind.ERASURE],
        default=SuspensionKind.ABUSE.value,
        help="erasure suspensions belong to the erasure job, not this script",
    )
    suspend.add_argument("--reason", required=True, help="for the record; never shown")
    suspend.add_argument("--yes", action="store_true")

    for name in ("unsuspend", "sign-out"):
        p = sub.add_parser(name)
        p.add_argument("--yes", action="store_true")

    args = parser.parse_args(argv[1:])
    if not args.yes:
        print("refusing without --yes", file=sys.stderr)
        return 2
    return asyncio.run(run(args.email, args))


if __name__ == "__main__":
    sys.exit(main(sys.argv))
