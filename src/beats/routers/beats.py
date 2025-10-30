import http
from datetime import UTC, date, datetime, time

from fastapi import APIRouter

from beats.db_helpers import serialize_from_document, serialize_to_document
from beats.domain import Beat, BeatRepository

router = APIRouter(
    prefix="/api/beats",
    tags=["Beats"],
    responses={404: {"description": "Not found"}},
)


@router.post("/", status_code=http.HTTPStatus.CREATED)
async def create_beat(log: Beat) -> dict:
    created_beat = BeatRepository.create(log.model_dump(exclude_none=True))
    return serialize_from_document(created_beat)


@router.get("/")
async def list_beats(
    project_id: str | None = None, date_filter: date | None = None
) -> list[dict]:
    filters = {}
    if project_id:
        filters.update({"project_id": project_id})
    if date_filter:
        start_of_day = datetime.combine(date_filter, time.min, tzinfo=UTC)
        end_of_day = datetime.combine(date_filter, time.max, tzinfo=UTC)
        filters.update({"start": {"$gte": start_of_day, "$lte": end_of_day}})

    logs = list(BeatRepository.list(filters))
    return [serialize_from_document(log) for log in logs]


@router.get("/{beat_id}")
async def get_beat(beat_id: str) -> dict:
    beat = BeatRepository.retrieve_by_id(beat_id)
    return serialize_from_document(beat)


@router.put("/")
async def update_beat(log: Beat) -> dict:
    updated_beat = BeatRepository.update(
        serialize_to_document(log.model_dump(exclude_none=True))
    )
    return serialize_from_document(updated_beat)


@router.delete("/{beat_id}")
async def delete_beat(beat_id: str) -> dict:
    BeatRepository.delete(beat_id)
    return {"status": "deleted!"}
