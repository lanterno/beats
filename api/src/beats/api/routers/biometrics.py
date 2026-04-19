"""Biometrics API router — daily health data from companion app or integrations."""

from datetime import UTC, datetime, timedelta
from datetime import date as date_type

from fastapi import APIRouter, Query, status
from pydantic import BaseModel, Field

from beats.api.dependencies import BiometricRepoDep, CurrentUserId
from beats.domain.models import BiometricDay

router = APIRouter(prefix="/api/biometrics", tags=["biometrics"])


class BiometricDayRequest(BaseModel):
    date: date_type
    source: str  # healthkit, health_connect, fitbit, oura
    sleep_minutes: int | None = None
    sleep_efficiency: float | None = None
    hrv_ms: float | None = None
    resting_hr_bpm: int | None = None
    steps: int | None = None
    readiness_score: int | None = None
    workouts: list[dict] = Field(default_factory=list)


class BiometricDayResponse(BaseModel):
    id: str
    date: date_type
    source: str
    sleep_minutes: int | None
    sleep_efficiency: float | None
    hrv_ms: float | None
    resting_hr_bpm: int | None
    steps: int | None
    readiness_score: int | None
    workouts: list[dict]


@router.post("/daily", status_code=status.HTTP_200_OK)
async def post_biometric_day(
    body: BiometricDayRequest,
    user_id: CurrentUserId,
    repo: BiometricRepoDep,
) -> dict[str, str]:
    """Upsert a day of biometric data (device token or session token)."""
    day = BiometricDay(
        date=body.date,
        source=body.source,
        sleep_minutes=body.sleep_minutes,
        sleep_efficiency=body.sleep_efficiency,
        hrv_ms=body.hrv_ms,
        resting_hr_bpm=body.resting_hr_bpm,
        steps=body.steps,
        readiness_score=body.readiness_score,
        workouts=body.workouts,
    )
    result = await repo.upsert(day)
    return {"id": result.id or ""}


@router.get("/", response_model=list[BiometricDayResponse])
async def list_biometrics(
    user_id: CurrentUserId,
    repo: BiometricRepoDep,
    start: date_type = Query(
        default_factory=lambda: (datetime.now(UTC) - timedelta(days=30)).date()
    ),
    end: date_type = Query(default_factory=lambda: datetime.now(UTC).date()),
) -> list[BiometricDayResponse]:
    """List biometric data for a date range."""
    days = await repo.list_by_range(start, end)
    return [
        BiometricDayResponse(
            id=d.id or "",
            date=d.date,
            source=d.source,
            sleep_minutes=d.sleep_minutes,
            sleep_efficiency=d.sleep_efficiency,
            hrv_ms=d.hrv_ms,
            resting_hr_bpm=d.resting_hr_bpm,
            steps=d.steps,
            readiness_score=d.readiness_score,
            workouts=d.workouts,
        )
        for d in days
    ]


@router.delete("/", status_code=status.HTTP_200_OK)
async def delete_all_biometrics(
    user_id: CurrentUserId,
    repo: BiometricRepoDep,
) -> dict[str, int]:
    """Delete all biometric data for the current user (privacy)."""
    deleted = await repo.delete_all()
    return {"deleted": deleted}
