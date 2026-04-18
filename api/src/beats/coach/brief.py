"""Daily brief generation.

Assembles the system + user + day context, sends to the gateway with caching,
and persists the result. The brief is the first ritual — the lowest-risk coach
surface, and the one users will see every morning.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from beats.coach.context import build_coach_messages
from beats.coach.gateway import complete
from beats.coach.prompts import BRIEF_PROMPT
from beats.infrastructure.database import Database

COLLECTION = "daily_briefs"


async def generate_brief(user_id: str, target_date: date | None = None) -> dict:
    """Generate and persist a daily brief. Returns the stored document."""
    today = target_date or datetime.now(UTC).date()
    prompt = BRIEF_PROMPT.format(today=today.isoformat())
    system, messages, spec = await build_coach_messages(user_id, prompt, target_date=today)

    result = await complete(
        user_id=user_id,
        system=system,
        messages=messages,
        cache_spec=spec,
        temperature=0.4,
        max_tokens=1024,
        purpose="brief",
    )

    body = ""
    for block in result.content:
        if hasattr(block, "text"):
            body += block.text

    doc = {
        "user_id": user_id,
        "date": today.isoformat(),
        "body": body.strip(),
        "model": result.model,
        "cost_usd": result.cost_usd,
        "input_tokens": result.input_tokens,
        "output_tokens": result.output_tokens,
        "cache_read": result.cache_read_input_tokens,
        "created_at": datetime.now(UTC),
    }

    db = Database.get_db()
    await db[COLLECTION].update_one(
        {"user_id": user_id, "date": today.isoformat()},
        {"$set": doc},
        upsert=True,
    )

    return doc


async def get_brief(user_id: str, target_date: date | None = None) -> dict | None:
    today = target_date or datetime.now(UTC).date()
    db = Database.get_db()
    return await db[COLLECTION].find_one(
        {"user_id": user_id, "date": today.isoformat()},
        {"_id": 0},
    )


async def list_briefs(user_id: str, limit: int = 14) -> list[dict]:
    db = Database.get_db()
    cursor = db[COLLECTION].find({"user_id": user_id}, {"_id": 0}).sort("date", -1).limit(limit)
    return await cursor.to_list(limit)
