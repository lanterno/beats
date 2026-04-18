"""Daily Notes API router — end-of-day reflections."""

from datetime import UTC, date, datetime

from fastapi import APIRouter

from beats.api.dependencies import DailyNoteRepoDep
from beats.api.schemas import DailyNoteResponse, UpsertDailyNoteRequest
from beats.domain.models import DailyNote

router = APIRouter(prefix="/api/daily-notes", tags=["daily-notes"])


@router.get("", response_model=DailyNoteResponse | None)
async def get_daily_note(
    repo: DailyNoteRepoDep,
    target_date: date | None = None,
) -> DailyNoteResponse | None:
    """Get the daily note for a given date (defaults to today)."""
    d = target_date or datetime.now(UTC).date()
    note = await repo.get_by_date(d)
    if not note:
        return None
    return DailyNoteResponse.model_validate(note, from_attributes=True)


@router.put("", response_model=DailyNoteResponse)
async def upsert_daily_note(
    repo: DailyNoteRepoDep,
    body: UpsertDailyNoteRequest,
) -> DailyNoteResponse:
    """Create or update the daily note for a date."""
    note = DailyNote(
        date=body.date or datetime.now(UTC).date(),
        note=body.note,
        mood=body.mood,
    )
    saved = await repo.upsert(note)
    return DailyNoteResponse.model_validate(saved, from_attributes=True)
