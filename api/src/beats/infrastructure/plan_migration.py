"""Startup pass: move weekly plans stored under a Sunday onto their Monday.

The Plan page keyed a week by its Monday's local midnight read back through
`toISOString()`, which names the UTC date. East of Greenwich that is the
Sunday before, so every plan saved there was stored under a Sunday and read
back under it. The page now keys the week by the local date, and a Sunday
plan would no longer be found; this pass moves each one to the Monday after
it, which is the week it was written for. West of Greenwich the UTC date is
the Monday itself, so nothing there needs to move.

Where the user already has a plan under that Monday (saved since the page
was fixed), the Monday plan is the newer one and wins; the Sunday plan is
left where it is and named in the log, never deleted.

Idempotent: it acts on plans whose `week_of` is a Sunday, and a second boot
finds only the ones it chose to leave.
"""

import logging
from datetime import date, timedelta

from pymongo.asynchronous.database import AsyncDatabase

logger = logging.getLogger(__name__)

SUNDAY = 6  # date.weekday()


async def move_sunday_plans_to_monday(db: AsyncDatabase) -> list[str]:
    """Re-key each Sunday plan to the next day; return the ids of plans left in place."""
    moved = 0
    left: list[str] = []
    async for doc in db.weekly_plans.find({}, {"user_id": 1, "week_of": 1}):
        stored = doc.get("week_of")
        try:
            week_of = date.fromisoformat(stored) if isinstance(stored, str) else None
        except ValueError:
            week_of = None
        if week_of is None or week_of.weekday() != SUNDAY:
            continue
        monday = (week_of + timedelta(days=1)).isoformat()
        taken = await db.weekly_plans.count_documents(
            {"user_id": doc.get("user_id"), "week_of": monday}, limit=1
        )
        if taken:
            left.append(str(doc["_id"]))
            continue
        result = await db.weekly_plans.update_one(
            {"_id": doc["_id"], "week_of": stored}, {"$set": {"week_of": monday}}
        )
        moved += result.modified_count

    if moved:
        logger.info("Moved %d weekly plan(s) from a Sunday to its Monday", moved)
    for plan_id in left:
        logger.warning(
            "Weekly plan %s is stored under a Sunday, and its Monday already has a plan: "
            "left in place",
            plan_id,
        )
    return left
