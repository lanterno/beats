"""Employment API router — stage 3 and 4 of organisations
(docs/organisations.md), under the same prefix as the organisations router
and the same rules: every route resolves the caller's membership first, a
non-member reads 404, and no device token reaches any of it.

Who may do what is the roles' three capabilities (`OrgRole`): owners and
admins administer; owners, admins and managers decide — a manager only for
the members of their teams (403 OUTSIDE_MANAGER_SCOPE); everyone above a
member reads the record. The timesheet lock these routes create is enforced
in the member-side services, not here: a beat, absence or adjustment dated
inside an approved month answers 409 PERIOD_APPROVED wherever it is written.
"""

import http
from datetime import date, datetime
from typing import Annotated

from fastapi import APIRouter, Query, Response
from pydantic import BaseModel, Field, StringConstraints

from beats.api.dependencies import (
    CurrentUserId,
    OrganisationServiceDep,
    TimezoneDep,
    absence_repository_for,
    adjustment_repository_for,
    beat_repository_for,
)
from beats.api.params import MonthQuery
from beats.api.schemas import AdjustmentResponse
from beats.domain.employment import compliance_csv, record_csv
from beats.domain.models import (
    AbsenceType,
    BalanceAdjustment,
    BalanceAdjustmentFields,
    Contract,
    FrozenMonth,
    OrgAbsenceRequest,
    OrgTeam,
    OrgTimesheet,
    RequestStatus,
    TimesheetEvent,
    TimesheetStatus,
)
from beats.domain.organisations import OrgLabels

router = APIRouter(
    prefix="/api/organisations",
    tags=["Employment"],
    responses={404: {"description": "Not found"}},
)


# --- schemas -----------------------------------------------------------------


class TeamRequest(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
    member_ids: list[str] = Field(default_factory=list, max_length=500)


class TeamResponse(BaseModel):
    id: str
    name: str
    member_ids: list[str]


class ManagedContractRequest(BaseModel):
    """The employer's contract on an assignment. `managed` true takes the
    terms under the organisation's hand; false hands them back. `contract`
    left null keeps what the assignment has."""

    contract: Contract | None = None
    managed: bool


class ManagedContractResponse(BaseModel):
    project_id: str
    user_id: str
    managed: bool
    contract: Contract | None


class EnterTimeRequest(BaseModel):
    start: datetime
    end: datetime
    note: Annotated[str, StringConstraints(max_length=500)] | None = None


class AbsenceRequestBody(BaseModel):
    project_id: str
    date: date
    type: AbsenceType
    half_day: bool = False
    note: Annotated[str, StringConstraints(max_length=500)] | None = None


class AbsenceRequestResponse(BaseModel):
    """A request as its decider and its asker read it. The names come with
    it: a decider reads a project's name here, having no right to the
    organisation's project list, and a member who has since left is still
    named rather than left as an id."""

    id: str
    project_id: str
    project_name: str | None
    user_id: str
    member_name: str | None
    date: date
    type: AbsenceType
    half_day: bool
    note: str | None
    status: RequestStatus
    requested_at: datetime
    decided_at: datetime | None
    decided_by: str | None
    decided_by_name: str | None
    comment: str | None


class DecisionBody(BaseModel):
    approve: bool
    comment: Annotated[str, StringConstraints(max_length=500)] | None = None


class SubmitTimesheetBody(BaseModel):
    project_id: str
    month: date  # any day of it; the 1st is stored


class TimesheetResponse(BaseModel):
    """A timesheet as both sides read it. `frozen` is set only while
    approved: the figures as approval saw them, which the lock then keeps.
    The names come with it, for the reasons `AbsenceRequestResponse` gives."""

    id: str
    project_id: str
    project_name: str | None
    user_id: str
    member_name: str | None
    month: date
    status: TimesheetStatus
    submitted_at: datetime
    decided_at: datetime | None
    decided_by: str | None
    decided_by_name: str | None
    comment: str | None
    frozen: FrozenMonth | None
    history: list[TimesheetEvent]


class ReopenBody(BaseModel):
    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]


class AuditEventResponse(BaseModel):
    at: datetime
    actor_user_id: str | None
    event: str
    subject_user_id: str | None
    project_id: str | None
    details: dict


def _team(team: OrgTeam) -> TeamResponse:
    return TeamResponse(id=team.id or "", name=team.name, member_ids=team.member_ids)


def _request(request: OrgAbsenceRequest, labels: OrgLabels) -> AbsenceRequestResponse:
    return AbsenceRequestResponse(
        **request.model_dump(exclude={"organisation_id"}),
        project_name=labels.projects.get(request.project_id),
        member_name=labels.members.get(request.user_id),
        decided_by_name=labels.members.get(request.decided_by) if request.decided_by else None,
    )


def _sheet(sheet: OrgTimesheet, labels: OrgLabels) -> TimesheetResponse:
    return TimesheetResponse(
        **sheet.model_dump(exclude={"organisation_id"}),
        project_name=labels.projects.get(sheet.project_id),
        member_name=labels.members.get(sheet.user_id),
        decided_by_name=labels.members.get(sheet.decided_by) if sheet.decided_by else None,
    )


# --- teams (stage 4) ----------------------------------------------------------


@router.get("/{organisation_id}/teams", response_model=list[TeamResponse])
async def list_teams(organisation_id: str, user_id: CurrentUserId, service: OrganisationServiceDep):
    """The teams, for anyone who reads the record — a manager's scope is the
    teams they are in."""
    return [_team(t) for t in await service.teams(organisation_id, user_id)]


@router.post(
    "/{organisation_id}/teams", status_code=http.HTTPStatus.CREATED, response_model=TeamResponse
)
async def create_team(
    organisation_id: str,
    body: TeamRequest,
    user_id: CurrentUserId,
    service: OrganisationServiceDep,
):
    """A team: a name and who is in it. Ids that are not active members are
    dropped. Admins."""
    return _team(await service.create_team(organisation_id, user_id, body.name, body.member_ids))


@router.put("/{organisation_id}/teams/{team_id}", response_model=TeamResponse)
async def update_team(
    organisation_id: str,
    team_id: str,
    body: TeamRequest,
    user_id: CurrentUserId,
    service: OrganisationServiceDep,
):
    """Replace a team's name and members. Admins."""
    return _team(
        await service.update_team(organisation_id, user_id, team_id, body.name, body.member_ids)
    )


@router.delete("/{organisation_id}/teams/{team_id}", status_code=http.HTTPStatus.NO_CONTENT)
async def delete_team(
    organisation_id: str, team_id: str, user_id: CurrentUserId, service: OrganisationServiceDep
) -> Response:
    """Delete a team: its managers lose that scope, nothing else changes. Admins."""
    await service.delete_team(organisation_id, user_id, team_id)
    return Response(status_code=http.HTTPStatus.NO_CONTENT)


# --- managed contracts (stage 3) ------------------------------------------------


@router.get(
    "/{organisation_id}/projects/{project_id}/members/{member_user_id}/contract",
    response_model=ManagedContractResponse,
)
async def read_managed_contract(
    organisation_id: str,
    project_id: str,
    member_user_id: str,
    user_id: CurrentUserId,
    service: OrganisationServiceDep,
):
    """The assignment's contract, for the decider editing it."""
    assignment = await service.read_contract(organisation_id, user_id, project_id, member_user_id)
    return ManagedContractResponse(
        project_id=project_id,
        user_id=member_user_id,
        managed=assignment.contract_managed,
        contract=assignment.contract,
    )


@router.put(
    "/{organisation_id}/projects/{project_id}/members/{member_user_id}/contract",
    response_model=ManagedContractResponse,
)
async def set_managed_contract(
    organisation_id: str,
    project_id: str,
    member_user_id: str,
    body: ManagedContractRequest,
    user_id: CurrentUserId,
    service: OrganisationServiceDep,
):
    """Write the employer's contract on an assignment, or hand it back
    (docs/organisations.md, stage 3). Taking a contract under management
    starts from the terms the member recorded — nothing is rewritten
    silently — and from then on the member's own contract, absence and
    adjustment writes answer 409 CONTRACT_MANAGED. Deciders; a manager for
    their teams."""
    assignment = await service.set_contract(
        organisation_id,
        user_id,
        project_id,
        member_user_id,
        body.contract,
        body.managed,
        adjustment_repository_for(member_user_id),
    )
    return ManagedContractResponse(
        project_id=project_id,
        user_id=member_user_id,
        managed=assignment.contract_managed,
        contract=assignment.contract,
    )


@router.post(
    "/{organisation_id}/projects/{project_id}/members/{member_user_id}/adjustments",
    status_code=http.HTTPStatus.CREATED,
    response_model=AdjustmentResponse,
)
async def enter_adjustment(
    organisation_id: str,
    project_id: str,
    member_user_id: str,
    body: BalanceAdjustmentFields,
    user_id: CurrentUserId,
    service: OrganisationServiceDep,
):
    """A balance adjustment — a payout, a reset, a cap — on a managed
    assignment: the employer's act, audited, on the member's own balance.
    The member's route answers 409 CONTRACT_MANAGED there; this one answers
    409 NOT_MANAGED where the member still writes their own."""
    saved = await service.enter_adjustment(
        organisation_id,
        user_id,
        project_id,
        member_user_id,
        adjustment_repository_for(member_user_id),
        BalanceAdjustment(
            project_id=project_id,
            date=body.date,
            kind=body.kind,
            hours=body.hours,
            note=body.note,
        ),
    )
    return saved.model_dump(mode="json")


@router.post(
    "/{organisation_id}/projects/{project_id}/members/{member_user_id}/entries",
    status_code=http.HTTPStatus.CREATED,
)
async def enter_time(
    organisation_id: str,
    project_id: str,
    member_user_id: str,
    body: EnterTimeRequest,
    user_id: CurrentUserId,
    service: OrganisationServiceDep,
):
    """Enter a finished session for a member (docs/organisations.md, stage
    3): the entry lands on the member's own timeline, stamped as the
    organisation's record and marked with who entered it, and the act is in
    the audit log. Refused inside an approved month."""
    beat = await service.enter_time(
        organisation_id,
        user_id,
        project_id,
        member_user_id,
        beat_repository_for(member_user_id),
        body.start,
        body.end,
        body.note,
    )
    return beat.model_dump(mode="json")


# --- absence requests (stage 3) ---------------------------------------------------


@router.post(
    "/{organisation_id}/absence-requests",
    status_code=http.HTTPStatus.CREATED,
    response_model=AbsenceRequestResponse,
)
async def request_absence(
    organisation_id: str,
    body: AbsenceRequestBody,
    user_id: CurrentUserId,
    service: OrganisationServiceDep,
):
    """Ask for a day off on a managed assignment. The note is addressed to
    the decider; the organisation's record never carries it (rule 3). On an
    unmanaged assignment the member books directly, as ever (409
    NOT_MANAGED here)."""
    request = await service.request_absence(
        organisation_id,
        user_id,
        body.project_id,
        body.date,
        body.type,
        body.half_day,
        body.note,
    )
    return _request(request, await service.labels(organisation_id))


@router.get("/{organisation_id}/absence-requests", response_model=list[AbsenceRequestResponse])
async def list_absence_requests(
    organisation_id: str,
    user_id: CurrentUserId,
    service: OrganisationServiceDep,
    pending: Annotated[bool, Query(description="Only the undecided ones.")] = False,
):
    """A member's own requests; a decider's whole scope — an owner's or
    admin's everyone, a manager's their teams."""
    requests = await service.absence_requests(organisation_id, user_id, pending_only=pending)
    labels = await service.labels(organisation_id)
    return [_request(r, labels) for r in requests]


@router.post(
    "/{organisation_id}/absence-requests/{request_id}/decision",
    response_model=AbsenceRequestResponse,
)
async def decide_absence_request(
    organisation_id: str,
    request_id: str,
    body: DecisionBody,
    user_id: CurrentUserId,
    service: OrganisationServiceDep,
):
    """Approve — which books the absence, stamped as the organisation's — or
    decline with a comment. Once: a second decision answers 409."""
    decided = await service.decide_absence(
        organisation_id,
        user_id,
        request_id,
        absence_repository_for,
        approve=body.approve,
        comment=body.comment,
    )
    return _request(decided, await service.labels(organisation_id))


@router.delete(
    "/{organisation_id}/absence-requests/{request_id}", status_code=http.HTTPStatus.NO_CONTENT
)
async def withdraw_absence_request(
    organisation_id: str, request_id: str, user_id: CurrentUserId, service: OrganisationServiceDep
) -> Response:
    """Take a pending request of one's own back; a decided one stays."""
    await service.withdraw_absence(organisation_id, user_id, request_id)
    return Response(status_code=http.HTTPStatus.NO_CONTENT)


# --- timesheets (stage 3) ----------------------------------------------------------


@router.post(
    "/{organisation_id}/timesheets",
    status_code=http.HTTPStatus.CREATED,
    response_model=TimesheetResponse,
)
async def submit_timesheet(
    organisation_id: str,
    body: SubmitTimesheetBody,
    user_id: CurrentUserId,
    service: OrganisationServiceDep,
):
    """Submit a month of one's own on an organisation project, once it has
    ended in the organisation's timezone (409 MONTH_NOT_ENDED before). A
    sheet sent back or reopened resubmits the same way; an approved one is
    refused until reopened (409 TIMESHEET_APPROVED)."""
    sheet = await service.submit_timesheet(organisation_id, user_id, body.project_id, body.month)
    return _sheet(sheet, await service.labels(organisation_id))


@router.get("/{organisation_id}/timesheets", response_model=list[TimesheetResponse])
async def list_timesheets(
    organisation_id: str,
    user_id: CurrentUserId,
    service: OrganisationServiceDep,
    month: MonthQuery | None = None,
):
    """A member's own sheets; a decider's or viewer's whole scope."""
    sheets = await service.timesheets(organisation_id, user_id, month=month)
    labels = await service.labels(organisation_id)
    return [_sheet(s, labels) for s in sheets]


@router.post("/{organisation_id}/timesheets/{sheet_id}/decision", response_model=TimesheetResponse)
async def decide_timesheet(
    organisation_id: str,
    sheet_id: str,
    body: DecisionBody,
    user_id: CurrentUserId,
    service: OrganisationServiceDep,
):
    """Approve — freezing the month's figures as they stand and locking every
    write dated inside it — or send the sheet back with a comment. Approval
    waits while a stamped timer still runs in the month (409
    PERIOD_APPROVED names it). Deciders."""
    decided = await service.decide_timesheet(
        organisation_id, user_id, sheet_id, approve=body.approve, comment=body.comment
    )
    return _sheet(decided, await service.labels(organisation_id))


@router.post("/{organisation_id}/timesheets/{sheet_id}/reopen", response_model=TimesheetResponse)
async def reopen_timesheet(
    organisation_id: str,
    sheet_id: str,
    body: ReopenBody,
    user_id: CurrentUserId,
    service: OrganisationServiceDep,
):
    """Lift an approved month's lock, with a reason, recorded in the sheet's
    history and the audit log. The frozen figures go with it; re-approval
    freezes afresh. Deciders."""
    reopened = await service.reopen_timesheet(organisation_id, user_id, sheet_id, body.reason)
    return _sheet(reopened, await service.labels(organisation_id))


# --- the audit log and the report CSVs (stage 4) -------------------------------------


@router.get("/{organisation_id}/audit", response_model=list[AuditEventResponse])
async def read_audit(
    organisation_id: str,
    user_id: CurrentUserId,
    service: OrganisationServiceDep,
    before: Annotated[
        datetime | None, Query(description="Only events before this instant; for paging.")
    ] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
):
    """The audit log, newest first — written since the first organisation
    existed, readable from stage 4 on. Owners and admins."""
    events = await service.audit_log(organisation_id, user_id, before=before, limit=limit)
    return [
        AuditEventResponse(
            at=e.at,
            actor_user_id=e.actor_user_id,
            event=e.event,
            subject_user_id=e.subject_user_id,
            project_id=e.project_id,
            details=e.details,
        )
        for e in events
    ]


@router.get(
    "/{organisation_id}/record.csv",
    response_class=Response,
    responses={200: {"description": "The month's record as CSV.", "content": {"text/csv": {}}}},
)
async def read_record_csv(
    organisation_id: str,
    month: MonthQuery,
    user_id: CurrentUserId,
    service: OrganisationServiceDep,
    tz: TimezoneDep,
) -> Response:
    """The month's record as CSV, a row per entry — the report an accountant
    files. Whoever reads the record; a manager's is their teams'."""
    record = await service.scoped_record(organisation_id, user_id, month, tz)
    return Response(
        content=record_csv(record),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment"},
    )


@router.get(
    "/{organisation_id}/visible.csv",
    response_class=Response,
    responses={
        200: {
            "description": "What the organisation sees of the caller, as CSV.",
            "content": {"text/csv": {}},
        }
    },
)
async def read_visible_csv(
    organisation_id: str,
    month: MonthQuery,
    user_id: CurrentUserId,
    service: OrganisationServiceDep,
    tz: TimezoneDep,
) -> Response:
    """The month the organisation holds about the caller, as the same CSV its
    record exports — the person can always take away exactly what is seen of
    them, not just read it. Members and former members, like `/visible`."""
    record = await service.visible(organisation_id, user_id, month, tz)
    return Response(
        content=record_csv(record),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment"},
    )


@router.get(
    "/{organisation_id}/compliance.csv",
    response_class=Response,
    responses={
        200: {"description": "The month's compliance record as CSV.", "content": {"text/csv": {}}}
    },
)
async def read_compliance_csv(
    organisation_id: str,
    month: MonthQuery,
    user_id: CurrentUserId,
    service: OrganisationServiceDep,
    tz: TimezoneDep,
) -> Response:
    """The compliance record (docs/organisations.md, stage 3): per member,
    per day — first start, last end, breaks, total, and the warnings a
    working-time authority would raise (a day over 10 hours, rest under 11,
    taken over every project the member is on). Whoever reads the record."""
    record = await service.scoped_record(organisation_id, user_id, month, tz)
    return Response(
        content=compliance_csv(record),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment"},
    )
