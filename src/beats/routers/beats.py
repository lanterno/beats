import http
from datetime import date
from typing import Optional

from fastapi import APIRouter

from beats.db_helpers import serialize_from_document, serialize_to_document
from beats.domain import Beat, BeatRepository


router = APIRouter(
    prefix="/api/beats", tags=["Beats"],
    responses={404: {"description": "Not found"}},
)


@router.post("/", status_code=http.HTTPStatus.CREATED)
async def create_beat(log: Beat):
    log = BeatRepository.create(log.dict(exclude_none=True))
    return serialize_from_document(log)


@router.get("/")
async def list_beats(project_id: Optional[str] = None, date: Optional[date] = None):
    filters = {}
    if project_id:
        filters.update({"project_id": project_id})
    if date:
        filters.update({"date": date})

    logs = list(BeatRepository.list(filters))
    return [serialize_from_document(log) for log in logs]


@router.get("/{beat_id}")
async def get_beat(beat_id: str):
    beat = BeatRepository.retrieve_by_id(beat_id)
    return serialize_from_document(beat)


@router.put("/")
async def update_beat(log: Beat):
    log = BeatRepository.update(serialize_to_document(log.dict()))
    return serialize_from_document(log)
