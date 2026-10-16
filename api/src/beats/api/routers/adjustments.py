"""Balance adjustments API router — a payout, a reset or a cap on a day job's
balance, dated, instead of an edit to the opening balance.

Nested under the project because an adjustment belongs to one contract's
balance, and the write shape is an absence's: one per date, a post on a taken
date replacing what is there, and a delete by id. There is no list: the ledger
(`GET /{id}/ledger`) carries every adjustment with what it moved the balance
by, which is all a reader wants of one. Every route answers 404 for a project
that is not the caller's, never 403, and 409 (NOT_A_DAY_JOB) for a project of
another kind.
"""

import http

from fastapi import APIRouter, Response

from beats.api.dependencies import ContractServiceDep, RequiredTimezoneDep
from beats.api.schemas import AdjustmentResponse
from beats.domain.models import BalanceAdjustment, BalanceAdjustmentFields

router = APIRouter(
    prefix="/api/projects",
    tags=["Adjustments"],
    responses={404: {"description": "Not found"}},
)


@router.post(
    "/{project_id}/adjustments",
    status_code=http.HTTPStatus.CREATED,
    response_model=AdjustmentResponse,
)
async def record_adjustment(
    project_id: str,
    request: BalanceAdjustmentFields,
    service: ContractServiceDep,
    tz: RequiredTimezoneDep,
):
    """Record a balance adjustment: `delta` moves the balance by `hours`
    (negative for a payout), `reset` sets it to `hours`, `cap` brings it down
    to `hours` if it is above. Each takes effect at the start of its day.
    One per date: posting again for a date replaces the adjustment there,
    keeps its id and still answers 201.

    `tz` is required: the date must fall from the contract's first day
    through today in `tz` (409 ADJUSTMENT_OUTSIDE_BALANCE). 409 NO_CONTRACT
    when the day job has no contract, and so no balance, yet."""
    adjustment = BalanceAdjustment(
        project_id=project_id,
        date=request.date,
        kind=request.kind,
        hours=request.hours,
        note=request.note,
    )
    saved = await service.record_adjustment(adjustment, tz)
    return saved.model_dump(mode="json")


@router.delete("/{project_id}/adjustments/{adjustment_id}", status_code=http.HTTPStatus.NO_CONTENT)
async def delete_adjustment(
    project_id: str, adjustment_id: str, service: ContractServiceDep
) -> Response:
    """Remove a balance adjustment. 404 when it is not on this project."""
    await service.remove_adjustment(project_id, adjustment_id)
    return Response(status_code=http.HTTPStatus.NO_CONTENT)
