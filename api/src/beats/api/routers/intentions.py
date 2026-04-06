"""Intentions API router — daily time-boxed plans."""

from datetime import UTC, date, datetime

from fastapi import APIRouter, Query

from beats.api.dependencies import IntentionRepoDep
from beats.api.schemas import (
    CreateIntentionRequest,
    IntentionResponse,
    UpdateIntentionRequest,
)
from beats.domain.models import Intention

router = APIRouter(prefix="/api/intentions", tags=["intentions"])


@router.get("", response_model=list[IntentionResponse])
async def list_intentions(
    repo: IntentionRepoDep,
    target_date: date | None = Query(default=None),
) -> list[IntentionResponse]:
    """List intentions for a given date (defaults to today)."""
    d = target_date or datetime.now(UTC).date()
    intentions = await repo.list_by_date(d)
    return [
        IntentionResponse(
            id=i.id,
            project_id=i.project_id,
            date=i.date,
            planned_minutes=i.planned_minutes,
            completed=i.completed,
        )
        for i in intentions
    ]


@router.post("", response_model=IntentionResponse, status_code=201)
async def create_intention(
    repo: IntentionRepoDep,
    body: CreateIntentionRequest,
) -> IntentionResponse:
    """Create a daily intention."""
    intention = Intention(
        project_id=body.project_id,
        date=body.date or datetime.now(UTC).date(),
        planned_minutes=body.planned_minutes,
    )
    created = await repo.create(intention)
    return IntentionResponse(
        id=created.id,
        project_id=created.project_id,
        date=created.date,
        planned_minutes=created.planned_minutes,
        completed=created.completed,
    )


@router.patch("/{intention_id}", response_model=IntentionResponse)
async def update_intention(
    repo: IntentionRepoDep,
    intention_id: str,
    body: UpdateIntentionRequest,
) -> IntentionResponse:
    """Update an intention (toggle completion or change planned minutes)."""
    intentions = await repo.list_by_date(datetime.now(UTC).date())
    intention = next((i for i in intentions if i.id == intention_id), None)
    if not intention:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Intention not found")

    if body.completed is not None:
        intention.completed = body.completed
    if body.planned_minutes is not None:
        intention.planned_minutes = body.planned_minutes

    updated = await repo.update(intention)
    return IntentionResponse(
        id=updated.id,
        project_id=updated.project_id,
        date=updated.date,
        planned_minutes=updated.planned_minutes,
        completed=updated.completed,
    )


@router.delete("/{intention_id}", status_code=204)
async def delete_intention(
    repo: IntentionRepoDep,
    intention_id: str,
) -> None:
    """Delete an intention."""
    await repo.delete(intention_id)
