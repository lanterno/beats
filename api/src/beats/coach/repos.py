"""Shared repository construction for coach modules.

Both context builders and tool implementations need the same set of repos.
Centralizing here avoids duplicating the constructor calls.
"""

from __future__ import annotations

from dataclasses import dataclass

from beats.domain.ports import CompletedBeatReader, FlowWindowReader, ProjectLister
from beats.infrastructure.database import Database
from beats.infrastructure.repositories import (
    MongoBeatRepository,
    MongoFlowWindowRepository,
    MongoProjectRepository,
)

# Collection names — single source of truth for all coach Mongo collections.
COACH_MEMORY_COLLECTION = "coach_memory"
DAILY_BRIEFS_COLLECTION = "daily_briefs"
COACH_CONVERSATIONS_COLLECTION = "coach_conversations"
LLM_USAGE_COLLECTION = "llm_usage"


@dataclass(frozen=True, slots=True)
class CoachRepos:
    """The user-scoped repositories the coach reads.

    Each field names only what the coach reads: the project list, completed
    beats (directly, and again through IntelligenceService), and flow windows. Typed by
    protocol rather than by the Mongo classes that satisfy it, so the coach has
    no business knowing where the data lives and the tests' in-memory fakes are
    as valid here as the real thing.

    There was a fourth field, `digest`, that nothing read.
    """

    project: ProjectLister
    beat: CompletedBeatReader
    flow: FlowWindowReader


def fmt_minutes(minutes: float) -> str:
    h, m = divmod(int(minutes), 60)
    return f"{h}h {m}m" if h > 0 else f"{m}m"


async def build_repos(user_id: str) -> CoachRepos:
    """Build user-scoped repositories for the coach."""
    db = Database.get_db()
    return CoachRepos(
        project=MongoProjectRepository(db.projects, user_id=user_id),
        beat=MongoBeatRepository(db.timeLogs, user_id=user_id),
        flow=MongoFlowWindowRepository(db.flow_windows, user_id=user_id),
    )
