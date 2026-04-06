"""Beats API router - thin controller for beat CRUD operations."""

import http
from datetime import date

from fastapi import APIRouter

from beats.api.dependencies import BeatServiceDep
from beats.api.schemas import CreateBeatRequest, UpdateBeatRequest
from beats.domain.models import Beat

router = APIRouter(
    prefix="/api/beats",
    tags=["Beats"],
    responses={404: {"description": "Not found"}},
)


@router.post("/", status_code=http.HTTPStatus.CREATED)
async def create_beat(request: CreateBeatRequest, service: BeatServiceDep):
    """Create a new beat (time log entry)."""
    beat = Beat(
        project_id=request.project_id,
        start=request.start,
        end=request.end,
    )
    created = await service.create_beat(beat)
    return created.model_dump()


@router.get("/")
async def list_beats(
    service: BeatServiceDep,
    project_id: str | None = None,
    date_filter: date | None = None,
):
    """List beats with optional filters."""
    beats = await service.list_beats(project_id=project_id, date_filter=date_filter)
    return [b.model_dump() for b in beats]


@router.get("/{beat_id}")
async def get_beat(beat_id: str, service: BeatServiceDep):
    """Get a specific beat by ID."""
    beat = await service.get_beat(beat_id)
    return beat.model_dump()


@router.put("/")
async def update_beat(request: UpdateBeatRequest, service: BeatServiceDep):
    """Update an existing beat."""
    beat = Beat(
        id=request.id,
        project_id=request.project_id,
        start=request.start,
        end=request.end,
    )
    updated = await service.update_beat(beat)
    return updated.model_dump()


@router.delete("/{beat_id}")
async def delete_beat(beat_id: str, service: BeatServiceDep):
    """Delete a beat by ID."""
    deleted = await service.delete_beat(beat_id)
    return {"deleted": deleted}
