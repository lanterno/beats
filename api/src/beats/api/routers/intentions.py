"""Intentions API router — daily time-boxed plans."""

from datetime import UTC, date, datetime

from fastapi import APIRouter, HTTPException

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
    target_date: date | None = None,
) -> list[IntentionResponse]:
    """List intentions for a given date (defaults to today)."""
    d = target_date or datetime.now(UTC).date()
    intentions = await repo.list_by_date(d)
    return [IntentionResponse.model_validate(i, from_attributes=True) for i in intentions]


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
    return IntentionResponse.model_validate(created, from_attributes=True)


@router.patch("/{intention_id}", response_model=IntentionResponse)
async def update_intention(
    repo: IntentionRepoDep,
    intention_id: str,
    body: UpdateIntentionRequest,
) -> IntentionResponse:
    """Update an intention (toggle completion or change planned minutes).

    Looks up by id directly. The previous implementation listed
    today's intentions and filtered, which silently 404'd any
    update on yesterday-or-earlier intentions — even though the
    list endpoint accepted target_date for any day. Asymmetric
    surface: users could VIEW historical intentions but couldn't
    toggle them off.
    """
    intention = await repo.get_by_id(intention_id)
    if not intention:
        raise HTTPException(status_code=404, detail="Intention not found")

    if body.completed is not None:
        intention.completed = body.completed
    if body.planned_minutes is not None:
        intention.planned_minutes = body.planned_minutes

    updated = await repo.update(intention)
    return IntentionResponse.model_validate(updated, from_attributes=True)


@router.delete("/{intention_id}", status_code=204)
async def delete_intention(
    repo: IntentionRepoDep,
    intention_id: str,
) -> None:
    """Delete an intention."""
    await repo.delete(intention_id)
