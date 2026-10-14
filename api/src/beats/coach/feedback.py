"""How the user found their briefs: a rating per brief, and the lines that
carry recent ratings into the coach's context so the next brief leans toward
the ones that helped.

Kept apart from brief.py, which imports the context this module feeds.
"""

from __future__ import annotations

import re
from datetime import UTC, date, datetime
from typing import Literal

from pymongo import ReturnDocument

from beats.coach.repos import DAILY_BRIEFS_COLLECTION
from beats.infrastructure.database import Database

BriefRating = Literal["helpful", "not_useful"]

_RATING_WORDS = {"helpful": "helpful", "not_useful": "not useful"}


async def set_brief_feedback(
    user_id: str, brief_date: date, rating: BriefRating | None
) -> dict | None:
    """Records [rating] on the user's brief for [brief_date], or clears it
    when None. Returns the updated brief, or None when there is no brief that
    day."""
    db = Database.get_db()
    update = (
        {"$set": {"feedback": rating, "feedback_at": datetime.now(UTC)}}
        if rating
        else {"$unset": {"feedback": "", "feedback_at": ""}}
    )
    return await db[DAILY_BRIEFS_COLLECTION].find_one_and_update(
        {"user_id": user_id, "date": brief_date.isoformat()},
        update,
        projection={"_id": 0},
        return_document=ReturnDocument.AFTER,
    )


async def recent_rated_briefs(user_id: str, limit: int = 14) -> list[dict]:
    """The user's last [limit] briefs that carry a rating, newest first."""
    db = Database.get_db()
    cursor = (
        db[DAILY_BRIEFS_COLLECTION]
        .find({"user_id": user_id, "feedback": {"$in": list(_RATING_WORDS)}}, {"_id": 0})
        .sort("date", -1)
        .limit(limit)
    )
    return await cursor.to_list(limit)


def _opening(body: str, limit: int = 90) -> str:
    """The brief's first sentence, without markdown marks, cut at [limit]."""
    plain = re.sub(r"[*_`#>]", "", body).strip()
    first = re.split(r"(?<=[.!?])\s", plain, maxsplit=1)[0].strip()
    return first if len(first) <= limit else first[: limit - 1].rstrip() + "…"


def brief_feedback_lines(briefs: list[dict]) -> list[str]:
    """A context section on how recent briefs landed, or [] when none are
    rated. Each line names the day, the rating and how that brief opened, so
    the model can tell what helped from what didn't."""
    rated = [b for b in briefs if b.get("feedback") in _RATING_WORDS]
    if not rated:
        return []
    helpful = sum(1 for b in rated if b["feedback"] == "helpful")
    return [
        "",
        "### How recent briefs landed",
        f"  The user marked {helpful} of the last {len(rated)} rated briefs helpful. "
        "Write more like the helpful ones and less like the rest.",
        *[
            f"  {b['date']}: {_RATING_WORDS[b['feedback']]} — opened with "
            f'"{_opening(b.get("body") or "")}"'
            for b in rated
        ],
    ]
