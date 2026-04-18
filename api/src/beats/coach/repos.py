"""Shared repository construction for coach modules.

Both context builders and tool implementations need the same set of repos.
Centralizing here avoids duplicating the constructor calls.
"""

from __future__ import annotations

from dataclasses import dataclass

from beats.infrastructure.database import Database
from beats.infrastructure.repositories import (
    MongoBeatRepository,
    MongoDailyNoteRepository,
    MongoIntentionRepository,
    MongoProjectRepository,
    MongoWeeklyDigestRepository,
)

# Collection names — single source of truth for all coach Mongo collections.
COACH_MEMORY_COLLECTION = "coach_memory"
DAILY_BRIEFS_COLLECTION = "daily_briefs"
REVIEW_ANSWERS_COLLECTION = "review_answers"
COACH_CONVERSATIONS_COLLECTION = "coach_conversations"
LLM_USAGE_COLLECTION = "llm_usage"


@dataclass(frozen=True, slots=True)
class CoachRepos:
    """All user-scoped repositories needed by the coach."""

    project: MongoProjectRepository
    beat: MongoBeatRepository
    intention: MongoIntentionRepository
    note: MongoDailyNoteRepository
    digest: MongoWeeklyDigestRepository


def fmt_minutes(minutes: float) -> str:
    h, m = divmod(int(minutes), 60)
    return f"{h}h {m}m" if h > 0 else f"{m}m"


async def build_repos(user_id: str) -> CoachRepos:
    """Build user-scoped repositories for the coach."""
    db = Database.get_db()
    return CoachRepos(
        project=MongoProjectRepository(db.projects, user_id=user_id),
        beat=MongoBeatRepository(db.timeLogs, user_id=user_id),
        intention=MongoIntentionRepository(db.intentions, user_id=user_id),
        note=MongoDailyNoteRepository(db.dailyNotes, user_id=user_id),
        digest=MongoWeeklyDigestRepository(db.weeklyDigests, user_id=user_id),
    )
