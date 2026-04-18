"""Coach memory persistence.

Each user has a single Markdown document that the coach rewrites weekly.
Stored in the `coach_memory` Mongo collection. The content becomes part of
the cached UserContextBlock, so the coach's personality evolves over time.
"""

from __future__ import annotations

from datetime import UTC, datetime

from motor.motor_asyncio import AsyncIOMotorDatabase

from beats.coach.repos import COACH_MEMORY_COLLECTION


class MemoryStore:
    def __init__(self, db: AsyncIOMotorDatabase, user_id: str) -> None:
        self._col = db[COACH_MEMORY_COLLECTION]
        self._user_id = user_id

    async def read(self) -> str | None:
        doc = await self._col.find_one({"user_id": self._user_id})
        if doc is None:
            return None
        return doc.get("content")

    async def write(self, content: str) -> None:
        now = datetime.now(UTC)
        existing = await self._col.find_one({"user_id": self._user_id})
        previous = existing.get("content", "") if existing else ""

        await self._col.update_one(
            {"user_id": self._user_id},
            {
                "$set": {
                    "content": content,
                    "updated_at": now,
                },
                "$push": {
                    "history": {
                        "content": previous,
                        "replaced_at": now,
                    }
                },
                "$setOnInsert": {
                    "user_id": self._user_id,
                    "created_at": now,
                },
            },
            upsert=True,
        )
