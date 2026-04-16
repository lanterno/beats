"""Shared repository construction for coach modules.

Both context builders and tool implementations need the same set of repos.
Centralizing here avoids duplicating the constructor calls.
"""

from __future__ import annotations

from beats.infrastructure.database import Database
from beats.infrastructure.repositories import (
    MongoBeatRepository,
    MongoDailyNoteRepository,
    MongoIntentionRepository,
    MongoProjectRepository,
    MongoWeeklyDigestRepository,
)


def fmt_minutes(minutes: float) -> str:
    h, m = divmod(int(minutes), 60)
    return f"{h}h {m}m" if h > 0 else f"{m}m"


async def build_repos(user_id: str):
    """Return (project_repo, beat_repo, intention_repo, note_repo, digest_repo)."""
    db = Database.get_db()
    return (
        MongoProjectRepository(db.projects, user_id=user_id),
        MongoBeatRepository(db.timeLogs, user_id=user_id),
        MongoIntentionRepository(db.intentions, user_id=user_id),
        MongoDailyNoteRepository(db.dailyNotes, user_id=user_id),
        MongoWeeklyDigestRepository(db.weeklyDigests, user_id=user_id),
    )
