"""Beats API router - thin controller for beat CRUD operations."""

import http
from datetime import date

from fastapi import APIRouter, Request

from beats.api.dependencies import BeatServiceDep
from beats.api.rate_limits import account_key, beats_writes_limit, beats_writes_off
from beats.api.routers.auth import limiter
from beats.api.schemas import CreateBeatRequest, UpdateBeatRequest
from beats.domain.models import Beat

router = APIRouter(
    prefix="/api/beats",
    tags=["Beats"],
    responses={404: {"description": "Not found"}},
)


def _write_limit():
    """The three writes share one per-account bucket (`shared_limit`'s
    scope), capped by the account's own ceiling or WRITES_PER_MINUTE_BEATS,
    and uncounted while neither is set. The body parameters are named
    `body`, not `request`: slowapi wants the Starlette Request under that
    name."""
    return limiter.shared_limit(
        beats_writes_limit,
        scope="beats-writes",
        key_func=account_key,
        exempt_when=beats_writes_off,
    )


@router.post("/", status_code=http.HTTPStatus.CREATED)
@_write_limit()
async def create_beat(request: Request, body: CreateBeatRequest, service: BeatServiceDep):
    """Create a new beat (time log entry)."""
    beat = Beat(
        project_id=body.project_id,
        start=body.start,
        end=body.end,
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
@_write_limit()
async def update_beat(request: Request, body: UpdateBeatRequest, service: BeatServiceDep):
    """Edit a beat's project, start, end and — when one is sent — its note:
    a string sets it, an empty string clears it, omitted keeps it as stored
    (#348). Every other stored field stays; the tags are re-derived from the
    new times when the daemon has flow windows for them, and kept when it
    has none. A beat the caller does not hold is a 404; with `expected`, one
    changed since the edit was made is a 409 BEAT_CHANGED."""
    beat = Beat(
        id=body.id,
        project_id=body.project_id,
        start=body.start,
        end=body.end,
    )
    updated = await service.update_beat(beat, note=body.note, expected=body.expected)
    return updated.model_dump()


@router.delete("/{beat_id}")
@_write_limit()
async def delete_beat(request: Request, beat_id: str, service: BeatServiceDep):
    """Delete a beat by ID."""
    deleted = await service.delete_beat(beat_id)
    return {"deleted": deleted}
