"""Planning API router — weekly plans, recurring intentions, weekly reviews, intention streaks."""

import http
from datetime import date, timedelta

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from beats.api.dependencies import (
    IntentionRepoDep,
    RecurringIntentionRepoDep,
    WeeklyPlanRepoDep,
    WeeklyReviewRepoDep,
)
from beats.domain.models import Intention, RecurringIntention, WeeklyPlan, WeeklyReview

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


# =========================================================================
# Recurring Intentions
# =========================================================================


class CreateRecurringIntentionRequest(BaseModel):
    project_id: str
    planned_minutes: int = 60
    days_of_week: list[int] = Field(default_factory=lambda: [0, 1, 2, 3, 4])


@router.get("/recurring")
async def list_recurring_intentions(repo: RecurringIntentionRepoDep):
    """List all recurring intention templates."""
    items = await repo.list_all()
    return [i.model_dump(mode="json") for i in items]


@router.post("/recurring", status_code=http.HTTPStatus.CREATED)
async def create_recurring_intention(
    request: CreateRecurringIntentionRequest, repo: RecurringIntentionRepoDep
):
    """Create a new recurring intention template."""
    intention = RecurringIntention(
        project_id=request.project_id,
        planned_minutes=request.planned_minutes,
        days_of_week=request.days_of_week,
    )
    created = await repo.create(intention)
    return created.model_dump(mode="json")


@router.delete("/recurring/{intention_id}")
async def delete_recurring_intention(intention_id: str, repo: RecurringIntentionRepoDep):
    """Delete a recurring intention template."""
    deleted = await repo.delete(intention_id)
    return {"deleted": deleted}


@router.post("/recurring/apply")
async def apply_recurring_intentions(
    recurring_repo: RecurringIntentionRepoDep,
    intention_repo: IntentionRepoDep,
):
    """Apply recurring intentions for today — creates intentions that don't already exist."""
    today = date.today()
    day_of_week = today.weekday()

    templates = await recurring_repo.list_all()
    existing = await intention_repo.list_by_date(today)
    existing_project_ids = {i.project_id for i in existing}

    created_count = 0
    for t in templates:
        if not t.enabled or day_of_week not in t.days_of_week:
            continue
        if t.project_id in existing_project_ids:
            continue
        intention = Intention(
            project_id=t.project_id,
            date=today,
            planned_minutes=t.planned_minutes,
        )
        await intention_repo.create(intention)
        created_count += 1

    return {"created": created_count, "date": today.isoformat()}


# =========================================================================
# Weekly Reviews
# =========================================================================


class UpsertWeeklyReviewRequest(BaseModel):
    week_of: date
    went_well: str = ""
    didnt_go_well: str = ""
    to_change: str = ""


@router.get("/reviews/weekly")
async def get_weekly_review(
    repo: WeeklyReviewRepoDep,
    week_of: date = Query(default=None),
):
    """Get a weekly review for a given week."""
    if week_of is None:
        week_of = date.today() - timedelta(days=date.today().weekday())
    review = await repo.get_by_week(week_of)
    if review:
        return review.model_dump(mode="json")
    return {"week_of": week_of.isoformat(), "went_well": "", "didnt_go_well": "", "to_change": ""}


@router.put("/reviews/weekly")
async def upsert_weekly_review(request: UpsertWeeklyReviewRequest, repo: WeeklyReviewRepoDep):
    """Create or update a weekly review."""
    review = WeeklyReview(
        week_of=request.week_of,
        went_well=request.went_well,
        didnt_go_well=request.didnt_go_well,
        to_change=request.to_change,
    )
    saved = await repo.upsert(review)
    return saved.model_dump(mode="json")


@router.get("/reviews/weekly/recent")
async def list_recent_reviews(repo: WeeklyReviewRepoDep, limit: int = Query(default=12)):
    """List recent weekly reviews."""
    reviews = await repo.list_recent(limit)
    return [r.model_dump(mode="json") for r in reviews]


# =========================================================================
# Intention Streaks
# =========================================================================


@router.get("/intention-streaks")
async def get_intention_streaks(intention_repo: IntentionRepoDep):
    """Compute consecutive days with all intentions completed."""
    all_intentions = await intention_repo.list_all()
    if not all_intentions:
        return {"current_streak": 0, "best_streak": 0}

    # Group by date
    by_date: dict[str, list] = {}
    for i in all_intentions:
        d = i.date.isoformat() if hasattr(i.date, "isoformat") else str(i.date)
        by_date.setdefault(d, []).append(i)

    # Find dates where ALL intentions are completed
    completed_dates = set()
    for d, intentions in by_date.items():
        if all(i.completed for i in intentions):
            completed_dates.add(d)

    if not completed_dates:
        return {"current_streak": 0, "best_streak": 0}

    sorted_dates = sorted(completed_dates)

    # Current streak (working backwards from today)
    today = date.today()
    current = 0
    cursor = today
    while cursor.isoformat() in completed_dates:
        current += 1
        cursor -= timedelta(days=1)

    # Best streak
    best = 1
    run = 1
    for i in range(1, len(sorted_dates)):
        prev = date.fromisoformat(sorted_dates[i - 1])
        curr = date.fromisoformat(sorted_dates[i])
        if (curr - prev).days == 1:
            run += 1
            best = max(best, run)
        else:
            run = 1

    return {"current_streak": current, "best_streak": best}
