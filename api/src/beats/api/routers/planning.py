"""Planning API router — structured weekly plans (per-project hour budgets)."""

from datetime import date, timedelta

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from beats.api.dependencies import WeeklyPlanRepoDep
from beats.domain.models import WeeklyPlan

router = APIRouter(prefix="/api/plans", tags=["planning"])


# =========================================================================
# Weekly Plans
# =========================================================================


class WeeklyPlanBudget(BaseModel):
    project_id: str
    planned_hours: float


class UpsertWeeklyPlanRequest(BaseModel):
    week_of: date
    budgets: list[WeeklyPlanBudget] = Field(default_factory=list)


@router.get("/weekly")
async def get_weekly_plan(
    repo: WeeklyPlanRepoDep,
    week_of: date = Query(default=None),
):
    """Get the weekly plan for a given week (defaults to current week's Monday)."""
    if week_of is None:
        week_of = date.today() - timedelta(days=date.today().weekday())
    plan = await repo.get_by_week(week_of)
    if plan:
        return plan.model_dump(mode="json")
    return {"week_of": week_of.isoformat(), "budgets": []}


@router.put("/weekly")
async def upsert_weekly_plan(request: UpsertWeeklyPlanRequest, repo: WeeklyPlanRepoDep):
    """Create or update a weekly plan."""
    plan = WeeklyPlan(
        week_of=request.week_of,
        budgets=[b.model_dump() for b in request.budgets],
    )
    saved = await repo.upsert(plan)
    return saved.model_dump(mode="json")
