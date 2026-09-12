"""Absences API router — the days a day job's contract does not expect work on.

Nested under the project because an absence belongs to one contract: two day
jobs on the same day are two absences. Every route answers 404 for a project
that is not the caller's, never 403 — the project repository is user-scoped,
so someone else's project simply does not exist here — and 409
(NOT_A_DAY_JOB) for a project of another kind.
"""

import http
from datetime import date

from fastapi import APIRouter, Query, Response

from beats.api.dependencies import ContractServiceDep, TimezoneDep
from beats.api.schemas import AbsenceRequest, AbsenceResponse
from beats.domain.models import Absence

router = APIRouter(
    prefix="/api/projects",
    tags=["Absences"],
    responses={404: {"description": "Not found"}},
)


@router.get("/{project_id}/absences", response_model=list[AbsenceResponse])
async def list_absences(
    project_id: str,
    service: ContractServiceDep,
    tz: TimezoneDep,
    start: date | None = Query(default=None, description="Defaults to 1 January of this year."),
    end: date | None = Query(default=None, description="Defaults to 31 December of this year."),
):
    """Absences on the project within [start, end], by date. Each bound
    defaults on its own to the current calendar year in `tz`."""
    absences = await service.list_absences(project_id, start, end, tz)
    return [a.model_dump(mode="json") for a in absences]


@router.post(
    "/{project_id}/absences",
    status_code=http.HTTPStatus.CREATED,
    response_model=AbsenceResponse,
)
async def record_absence(project_id: str, request: AbsenceRequest, service: ContractServiceDep):
    """Record an absence. One per date: posting again for the same date
    replaces the first and still answers 201, since the client asked to
    create and gets back the absence now on record."""
    absence = Absence(
        project_id=project_id,
        date=request.date,
        type=request.type,
        half_day=request.half_day,
        note=request.note,
    )
    saved = await service.record_absence(absence)
    return saved.model_dump(mode="json")


@router.delete("/{project_id}/absences/{absence_id}", status_code=http.HTTPStatus.NO_CONTENT)
async def delete_absence(project_id: str, absence_id: str, service: ContractServiceDep) -> Response:
    """Remove an absence. 404 when it is not on this project."""
    await service.remove_absence(project_id, absence_id)
    return Response(status_code=http.HTTPStatus.NO_CONTENT)
