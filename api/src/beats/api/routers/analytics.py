"""Analytics API endpoints for insights and aggregations."""

from datetime import date

from fastapi import APIRouter, Query

from beats.api.dependencies import AnalyticsServiceDep
from beats.api.schemas import HeatmapDayResponse, RhythmSlotResponse

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


@router.get("/heatmap", response_model=list[HeatmapDayResponse])
async def get_heatmap(
    service: AnalyticsServiceDep,
    year: int = Query(default_factory=lambda: date.today().year),
    project_id: str | None = Query(default=None),
):
    """Get daily activity heatmap for a given year."""
    return await service.get_heatmap(year, project_id=project_id)


@router.get("/rhythm", response_model=list[RhythmSlotResponse])
async def get_daily_rhythm(
    service: AnalyticsServiceDep,
    period: str = Query(default="all", pattern="^(week|month|all)$"),
    project_id: str | None = Query(default=None),
):
    """Get average activity by time of day in half-hour slots."""
    return await service.get_daily_rhythm(period, project_id=project_id)
