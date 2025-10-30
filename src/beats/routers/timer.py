
from fastapi import APIRouter

from beats.db_helpers import serialize_from_document
from beats.domain import Beat, BeatRepository
from beats.exceptions import NoObjectMatched

router = APIRouter(
    prefix="/api/timer", tags=["Timer"],
    responses={404: {"description": "Not found"}},
)


@router.get("/status")
async def heart_status() -> dict:
    try:
        last_beat = Beat(**serialize_from_document(BeatRepository.get_last()))
    except NoObjectMatched:
        return {
            "isBeating": False,
            "project": None,
        }
    
    if last_beat.is_beating():
        return {
            "isBeating": True,
            "project": last_beat.project_id,
            "since": last_beat.start,
            "so_far": str(last_beat.duration)
        }
    else:
        return {
            "isBeating": False,
            "lastBeatOn": last_beat.project_id,
            "for": str(last_beat.duration)
        }
