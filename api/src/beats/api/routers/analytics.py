"""Analytics API endpoints for insights and aggregations."""

from datetime import date

from fastapi import APIRouter, Query

from beats.api.dependencies import AnalyticsServiceDep, BeatServiceDep
from beats.api.schemas import HeatmapDayResponse, RhythmSlotResponse

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


@router.get("/heatmap", response_model=list[HeatmapDayResponse])
async def get_heatmap(
    service: AnalyticsServiceDep,
    year: int = Query(default_factory=lambda: date.today().year),
    project_id: str | None = Query(default=None),
    tag: str | None = Query(default=None),
):
    """Get daily activity heatmap for a given year."""
    return await service.get_heatmap(year, project_id=project_id, tag=tag)


@router.get("/rhythm", response_model=list[RhythmSlotResponse])
async def get_daily_rhythm(
    service: AnalyticsServiceDep,
    period: str = Query(default="all", pattern="^(week|month|all)$"),
    project_id: str | None = Query(default=None),
    tag: str | None = Query(default=None),
):
    """Get average activity by time of day in half-hour slots."""
    return await service.get_daily_rhythm(period, project_id=project_id, tag=tag)


@router.get("/gaps")
async def get_untracked_gaps(
    service: AnalyticsServiceDep,
    target_date: date = Query(default_factory=date.today),
):
    """Get untracked gaps between sessions on a given date."""
    return await service.get_untracked_gaps(target_date)


@router.get("/tags", response_model=list[str])
async def get_all_tags(beat_service: BeatServiceDep):
    """Get all unique tags used across all sessions, sorted alphabetically."""
    beats = await beat_service.beat_repo.list()
    tags: set[str] = set()
    for beat in beats:
        tags.update(beat.tags)
    return sorted(tags)
