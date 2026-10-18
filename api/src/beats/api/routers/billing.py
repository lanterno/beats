"""Billing API router — which freelance projects are billed to which client
on what terms, which entries are marked otherwise, what a month comes to,
and the billing budgets on clients and billed projects.

Its own prefix, not under /api/projects or /api/beats: both are device-token
prefixes, matched by prefix, and a paired device sees no money (see
`DEVICE_ALLOWED_PREFIXES` in `server.py`, and docs/billing.md). A project or
a beat that is not the caller's is not found (404), never forbidden.
"""

import http

from fastapi import APIRouter, Query, Response

from beats.api.dependencies import BillingServiceDep, RequiredTimezoneDep
from beats.api.params import MonthQuery
from beats.api.schemas import (
    BillableOverrideRequest,
    BillableOverrideResponse,
    BillingBudgetRequest,
    BillingBudgetResponse,
    BillingBudgetStatusResponse,
    BillingMonthResponse,
    ProjectBillingRequest,
    ProjectBillingResponse,
)
from beats.domain.billing_service import BilledProject, BillingBudgetRecord
from beats.domain.currencies import minor_units
from beats.domain.models import BillingBudgetScope

router = APIRouter(
    prefix="/api/billing",
    tags=["Billing"],
    responses={404: {"description": "Not found"}},
)


def _billing_response(billed: BilledProject) -> ProjectBillingResponse:
    return ProjectBillingResponse(
        project_id=billed.billing.project_id,
        client_id=billed.billing.client_id,
        currency=billed.client.currency,
        minor_units=minor_units(billed.client.currency),
        terms=billed.billing.terms,
    )


def _billing_budget_response(record: BillingBudgetRecord) -> BillingBudgetResponse:
    return BillingBudgetResponse.model_validate(
        {
            **record.budget.model_dump(),
            "client_id": record.client.id,
            "currency": record.client.currency,
            "minor_units": minor_units(record.client.currency),
        }
    )


@router.get("/projects", response_model=list[ProjectBillingResponse])
async def list_project_billings(service: BillingServiceDep):
    """Every billed project's billing: one per project, a small set."""
    return [_billing_response(billed) for billed in await service.list_project_billings()]


@router.put("/projects/{project_id}", response_model=ProjectBillingResponse)
async def set_project_billing(
    project_id: str,
    request: ProjectBillingRequest,
    service: BillingServiceDep,
    tz: RequiredTimezoneDep,
):
    """Bill a freelance project to a client under dated terms, replacing
    what it had: from each term's `effective_from`, whether its hours are
    billable and, optionally, at a rate of its own (`rate_minor`, in the
    client's currency); without one they take the client's rate in force
    that day. Strictly ascending, one a day.

    404 for a project, or a client (CLIENT_NOT_FOUND), that is not the
    caller's; 409 NOT_FREELANCE for a project of another kind; 409
    CURRENCY_MISMATCH for a move to a client in another currency while a
    rate of the project's own, a billable term before the current month, or
    an entry before it marked billable would be read in it. Attaching a
    project the first time is not gated; after that, a change to terms dated
    before the current month in `tz`, or a move to another client while one
    is or an entry there is marked billable, is a 409 RETROACTIVE_CHANGE
    without `rewrite_past: true`."""
    billed = await service.set_project_billing(
        project_id,
        request.client_id,
        request.terms,
        rewrite_past=request.rewrite_past,
        tz=tz,
    )
    return _billing_response(billed)


@router.delete("/projects/{project_id}", status_code=http.HTTPStatus.NO_CONTENT)
async def remove_project_billing(
    project_id: str,
    service: BillingServiceDep,
    tz: RequiredTimezoneDep,
    rewrite_past: bool = Query(
        description="The caller has confirmed a change to figures before the current month."
    ),
) -> Response:
    """Stop billing a project, in every month. 404 when it is not billed;
    409 RETROACTIVE_CHANGE without `rewrite_past=true` when a term is dated
    before the current month in `tz`, or an entry there is marked billable."""
    await service.remove_project_billing(project_id, rewrite_past=rewrite_past, tz=tz)
    return Response(status_code=http.HTTPStatus.NO_CONTENT)


@router.get("/entries", response_model=list[BillableOverrideResponse])
async def list_billable_overrides(service: BillingServiceDep):
    """Every entry marked billable or not against its project's term. They
    are exceptions, so the list is small."""
    return [override.model_dump() for override in await service.list_overrides()]


@router.put("/entries/{beat_id}", response_model=BillableOverrideResponse)
async def set_billable_override(
    beat_id: str, request: BillableOverrideRequest, service: BillingServiceDep
):
    """Mark one entry billable or not, whatever its project's term says. It
    counts while the entry's project is billed, and survives a move to
    another project. 404 when the entry is not the caller's."""
    override = await service.set_override(beat_id, request.billable)
    return override.model_dump()


@router.delete("/entries/{beat_id}", status_code=http.HTTPStatus.NO_CONTENT)
async def clear_billable_override(beat_id: str, service: BillingServiceDep) -> Response:
    """Return an entry to its project's rule. Always 204: with no mark, or
    no entry, there is nothing left to clear."""
    await service.clear_override(beat_id)
    return Response(status_code=http.HTTPStatus.NO_CONTENT)


@router.get("/month", response_model=BillingMonthResponse)
async def get_billing_month(month: MonthQuery, service: BillingServiceDep, tz: RequiredTimezoneDep):
    """What each client is owed for a month, in its own currency, with a
    total per currency and the freelance hours billed to no one.

    A finished entry belongs whole to the local day it started on in `tz`,
    which picks both its month and its rate; a running timer is left out
    (`running` on its client) until it stops. The current month runs
    through today in `tz`; a later one is a 409 MONTH_NOT_STARTED. Money is
    integer minor units; each line's amount is its hours times its rate,
    rounded once, and every total is a sum of lines."""
    period = await service.month(month, tz)
    return BillingMonthResponse.model_validate(
        {"month": f"{month:%Y-%m}", **period._asdict()}, from_attributes=True
    )


@router.get("/budgets", response_model=list[BillingBudgetStatusResponse])
async def list_billing_budgets(service: BillingServiceDep, tz: RequiredTimezoneDep):
    """Every billing budget, read as of today in `tz`, by client name: a
    client's own first, then its projects' by name. `[]` when there are none.

    What is spent is what 1a's lines bill — billable hours, or their priced
    amount in the client's currency — summed month by month so a total
    agrees with the months invoiced. Hours with no rate are reported as
    `unpriced_hours` and never counted as money. A running timer is in no
    figure: `running` gives the instants it alone would cross the warning
    and the limit. A budget on an archived client or project is read with
    `active: false`."""
    statuses = await service.billing_budget_statuses(tz)
    return [
        BillingBudgetStatusResponse.model_validate(status._asdict(), from_attributes=True)
        for status in statuses
    ]


@router.put("/budgets/clients/{client_id}", response_model=BillingBudgetResponse)
async def set_client_billing_budget(
    client_id: str, request: BillingBudgetRequest, service: BillingServiceDep
):
    """Give a client its billing budget, over every project billed to it,
    replacing the one it had: in hours or in money (its currency), monthly
    or in total from `starts_on`, with a warning at `warn_at_percent` and
    again at 100 %. 404 CLIENT_NOT_FOUND for a client that is not the
    caller's. Not gated: a budget changes no billable figure."""
    record = await service.set_billing_budget(BillingBudgetScope.CLIENT, client_id, request)
    return _billing_budget_response(record)


@router.put("/budgets/projects/{project_id}", response_model=BillingBudgetResponse)
async def set_project_billing_budget(
    project_id: str, request: BillingBudgetRequest, service: BillingServiceDep
):
    """Give a billed project its billing budget, replacing the one it had;
    money is in the currency of the client its billing names. 404 for a
    project that is not the caller's; 409 BILLING_BUDGET_NEEDS_BILLING for
    one that is not billed."""
    record = await service.set_billing_budget(BillingBudgetScope.PROJECT, project_id, request)
    return _billing_budget_response(record)


@router.delete("/budgets/clients/{client_id}", status_code=http.HTTPStatus.NO_CONTENT)
async def remove_client_billing_budget(client_id: str, service: BillingServiceDep) -> Response:
    """Take a client's billing budget away. Always 204: with no budget, or no
    client, there is nothing left to clear."""
    await service.remove_billing_budget(BillingBudgetScope.CLIENT, client_id)
    return Response(status_code=http.HTTPStatus.NO_CONTENT)


@router.delete("/budgets/projects/{project_id}", status_code=http.HTTPStatus.NO_CONTENT)
async def remove_project_billing_budget(project_id: str, service: BillingServiceDep) -> Response:
    """Take a project's billing budget away. Always 204, as for a client."""
    await service.remove_billing_budget(BillingBudgetScope.PROJECT, project_id)
    return Response(status_code=http.HTTPStatus.NO_CONTENT)
