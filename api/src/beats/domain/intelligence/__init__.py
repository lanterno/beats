"""Productivity scoring, pattern detection, and smart suggestions.

This was one 930-line class whose banner comments marked six subjects. Those
are now six modules of plain functions, and `IntelligenceService` is the thin
object the routers already depend on: it holds the two repositories and hands
them down.

The functions are the useful unit. Every detector is pure, so it can be tested
against a list of beats without constructing a service that exists only to
carry repositories it does not need.
"""

from datetime import date
from zoneinfo import ZoneInfo

from beats.domain.models import InsightCard, WeeklyDigest
from beats.domain.ports import ProjectLister, RangeBeatReader

# _monday_of is re-exported because the domain tests import it from here.
from ._support import UTC_TZ, _monday_of
from .digest import generate_observation, generate_weekly_digest
from .focus import compute_focus_scores, find_peak_block, focus_score_for_beat
from .health import get_project_health
from .patterns import (
    detect_chronotype,
    detect_day_pattern,
    detect_goal_pacing,
    detect_patterns,
    detect_peak_hours,
    detect_session_trend,
    detect_stale_projects,
)
from .planning import suggest_daily_plan
from .scoring import compute_productivity_score, compute_productivity_score_history

__all__ = [
    "UTC_TZ",
    "IntelligenceService",
    "_monday_of",
    "compute_focus_scores",
    "compute_productivity_score",
    "compute_productivity_score_history",
    "detect_chronotype",
    "detect_day_pattern",
    "detect_goal_pacing",
    "detect_patterns",
    "detect_peak_hours",
    "detect_session_trend",
    "detect_stale_projects",
    "find_peak_block",
    "focus_score_for_beat",
    "generate_observation",
    "generate_weekly_digest",
    "get_project_health",
    "suggest_daily_plan",
]


class IntelligenceService:
    """Binds the repositories to the intelligence functions.

    Kept because the routers and the coach already depend on it; it adds
    nothing but the two repositories.
    """

    def __init__(self, beat_repo: RangeBeatReader, project_repo: ProjectLister):
        self.beat_repo = beat_repo
        self.project_repo = project_repo

    async def compute_productivity_score(self, tz: ZoneInfo = UTC_TZ) -> dict:
        return await compute_productivity_score(self.beat_repo, self.project_repo, tz)

    async def compute_productivity_score_history(
        self, weeks: int = 8, tz: ZoneInfo = UTC_TZ
    ) -> list[dict]:
        return await compute_productivity_score_history(
            self.beat_repo, self.project_repo, weeks, tz
        )

    async def generate_weekly_digest(
        self, week_monday: date, tz: ZoneInfo = UTC_TZ
    ) -> WeeklyDigest:
        return await generate_weekly_digest(self.beat_repo, self.project_repo, week_monday, tz)

    async def detect_patterns(self, tz: ZoneInfo = UTC_TZ) -> list[InsightCard]:
        return await detect_patterns(self.beat_repo, self.project_repo, tz)

    async def suggest_daily_plan(self, target_date: date, tz: ZoneInfo = UTC_TZ) -> list[dict]:
        return await suggest_daily_plan(self.beat_repo, self.project_repo, target_date, tz)

    async def compute_focus_scores(self, target_date: date, tz: ZoneInfo = UTC_TZ) -> list[dict]:
        return await compute_focus_scores(self.beat_repo, target_date, tz)

    async def get_project_health(self, tz: ZoneInfo = UTC_TZ) -> list[dict]:
        return await get_project_health(self.beat_repo, self.project_repo, tz)
