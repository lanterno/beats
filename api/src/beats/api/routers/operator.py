"""The operator's routes — mounted only by `operator_server`, never here.

`server.py` must not import this module (a test pins that), and this module
must not import `beats.api.dependencies` or anything else that loads the
API's settings: the operator deployment never holds `JWT_SECRET`. Providers
come from `beats.operator.dependencies`; the error envelope is the shared one
(`beats.api.errors` loads no settings).

The reads have no service layer; every mutation goes through one runner
(docs/backoffice.md § Commands), so the audit cannot be forgotten. A `GET`
changes nothing, and the account lookup takes its address
in the **body** — an address in a URL is in Cloud Run's request log for 30
days, the reason `/api/reports` takes its token in a header.
"""

from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

from beats.operator.dependencies import CommandContextDep, CurrentOperator, OperatorReadsDep
from beats.operator.health import HealthReport
from beats.operator.reads import (
    AbuseReport,
    AccountDetail,
    AccountMatch,
    AttentionCounts,
    CapacityReport,
    ControlState,
    DayFigure,
    ErasureRequestState,
    OrganisationDetail,
    OrganisationSummary,
    OrgAuditRow,
    QueueRow,
)
from beats.operator.runner import CommandPreview, preview_command, run_command

router = APIRouter(prefix="/api/operator", tags=["operator"])


class OperatorMe(BaseModel):
    sub: str
    email: str
    role: str


class AccountLookupRequest(BaseModel):
    """Exact email (case-insensitive) or an account id. The common entry is a
    support or erasure mail carrying a full address; exact match serves that
    and is useless for fishing."""

    email: str = Field(default="", max_length=320)
    id: str = Field(default="", max_length=64)


@router.get("/me", response_model=OperatorMe)
async def me(operator: CurrentOperator) -> OperatorMe:
    """The signed-in operator, as the allowlist knows them."""
    return OperatorMe(sub=operator.sub, email=operator.email, role=operator.role)


@router.get("/attention", response_model=AttentionCounts)
async def attention(operator: CurrentOperator, reads: OperatorReadsDep) -> AttentionCounts:
    """The landing page's counts: the reason to open the control plane."""
    return await reads.attention()


@router.get("/queue", response_model=list[QueueRow])
async def queue(operator: CurrentOperator, reads: OperatorReadsDep) -> list[QueueRow]:
    """The rows behind the Attention counts, soonest due first: ids and
    dates, never a member's name. Nothing stores that a row was handled; it
    leaves when its condition clears."""
    return await reads.queue()


@router.post("/accounts/lookup", response_model=list[AccountMatch])
async def lookup_accounts(
    body: AccountLookupRequest, operator: CurrentOperator, reads: OperatorReadsDep
) -> list[AccountMatch]:
    """Every account an address matches, case-insensitively — `Ana@` and
    `ana@` can be two accounts, and a mail from either spelling must find
    both. A read, despite the POST: the body keeps the address out of the
    request log."""
    if bool(body.email) == bool(body.id):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Send exactly one of email and id",
        )
    if body.id:
        detail = await reads.account(body.id)
        if detail is None:
            return []
        return [
            AccountMatch(
                id=detail.id,
                email=detail.email,
                created_at=detail.created_at,
                last_seen_on=detail.last_seen_on,
                suspended=detail.suspended_at is not None,
            )
        ]
    return await reads.find_accounts(body.email)


@router.get("/accounts/{user_id}", response_model=AccountDetail)
async def account(
    user_id: str, operator: CurrentOperator, reads: OperatorReadsDep
) -> AccountDetail:
    """One account: state, counts and a storage estimate — how big, never
    what. Which identities it holds per provider is a fact the account
    stores; which door a sign-in used is deliberately not kept, and must not
    grow out of this page."""
    detail = await reads.account(user_id)
    if detail is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
    return detail


@router.get("/accounts/{user_id}/coach", response_model=list[DayFigure])
async def account_coach_spend(
    user_id: str, operator: CurrentOperator, reads: OperatorReadsDep
) -> list[DayFigure]:
    """One account's coach cost a day, for the shape of a month running
    away. The cost of the calls, never a word of what was in them."""
    return await reads.account_coach_spend(user_id)


@router.get("/accounts/{user_id}/audit")
async def account_audit(
    user_id: str,
    operator: CurrentOperator,
    reads: OperatorReadsDep,
    limit: int = Query(default=50, ge=1, le=200),
) -> list[dict]:
    """What the back office has done to this account. The operator's own
    audit filtered to one subject, so the account page does not read the
    whole log to find three rows."""
    return await reads.audit_log(limit, subject_id=user_id)


@router.get("/organisations", response_model=list[OrganisationSummary])
async def organisations(
    operator: CurrentOperator, reads: OperatorReadsDep
) -> list[OrganisationSummary]:
    return await reads.organisations()


@router.get("/organisations/{organisation_id}", response_model=OrganisationDetail)
async def organisation(
    organisation_id: str, operator: CurrentOperator, reads: OperatorReadsDep
) -> OrganisationDetail:
    detail = await reads.organisation(organisation_id)
    if detail is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organisation not found")
    return detail


@router.get("/organisations/{organisation_id}/audit", response_model=list[OrgAuditRow])
async def organisation_audit(
    organisation_id: str,
    operator: CurrentOperator,
    reads: OperatorReadsDep,
    limit: int = Query(default=200, ge=1, le=1000),
) -> list[OrgAuditRow]:
    """The organisation's log without each event's `details`, which carry
    what the organisation wrote."""
    return await reads.organisation_audit(organisation_id, limit)


@router.get("/controls", response_model=list[ControlState])
async def controls(operator: CurrentOperator, reads: OperatorReadsDep) -> list[ControlState]:
    """The platform's switches and global limits as they stand
    (docs/backoffice.md § Controls). Written only through `control.set` and
    `control.clear`."""
    return await reads.controls()


class AccessEntry(BaseModel):
    email: str
    role: str


@router.get("/access", response_model=list[AccessEntry])
async def access(request: Request, operator: CurrentOperator) -> list[AccessEntry]:
    """Who can reach this back office, read off the allowlist the deployment
    was started with. Read-only: the list is an environment value, and
    changing it is a deploy (terraform/README.md § Operator Deployment)."""
    allowlist = request.app.state.operator_settings.allowlist
    return [AccessEntry(email=i.email, role=i.role) for i in allowlist]


@router.get("/health", response_model=HealthReport)
async def health(request: Request, operator: CurrentOperator) -> HealthReport:
    """Whether the product is healthy, from Cloud Monitoring: availability,
    the share of 5xx, p95 latency, instances against their ceiling and
    refused writes per route. Cached a minute; a Google failure answers the
    last figures and their age, and off Google Cloud it answers
    "unavailable" — never an invented number."""
    state = request.app.state
    return await state.health_cache.report(
        state.health_source, state.operator_settings.api_max_instances
    )


@router.get("/erasure-requests", response_model=list[ErasureRequestState])
async def erasure_requests(
    operator: CurrentOperator, reads: OperatorReadsDep
) -> list[ErasureRequestState]:
    """The erasure request log: when each mail arrived and where it stands.
    A reference and an id, never an address."""
    return await reads.erasure_requests()


@router.get("/abuse", response_model=AbuseReport)
async def abuse(operator: CurrentOperator, reads: OperatorReadsDep) -> AbuseReport:
    """Outliers rather than guessed thresholds: who is far from the median on
    the axes a hostile account shows on."""
    return await reads.abuse()


@router.get("/capacity", response_model=CapacityReport)
async def capacity(operator: CurrentOperator, reads: OperatorReadsDep) -> CapacityReport:
    """What the platform will cost: documents and storage per collection, and
    the coach's cost by day and model with the cache-hit ratio's inputs.
    Latency and error rates are Cloud Monitoring's — link, don't rebuild."""
    return await reads.capacity()


@router.get("/audit")
async def audit_log(
    operator: CurrentOperator,
    reads: OperatorReadsDep,
    limit: int = Query(default=200, ge=1, le=1000),
) -> list[dict]:
    """The operator's own audit: every command the runner executed."""
    return await reads.audit_log(limit)


class CommandRequest(BaseModel):
    args: dict = Field(default_factory=dict)
    # What the operator typed back — the account's email, the organisation's
    # name — compared by the runner against the subject, never stored.
    confirmation: str | None = None


class PreviewRequest(BaseModel):
    args: dict = Field(default_factory=dict)


@router.post("/commands/{name}/preview", response_model=CommandPreview)
async def preview(name: str, body: PreviewRequest, ctx: CommandContextDep) -> CommandPreview:
    """What the command would do, before it does any of it.

    A POST because it carries the same arguments the act does, an account's
    id among them, and because the operator's credential is IAP's cookie:
    every state-changing shape is a POST with an Origin the app checks, and
    this one is shaped like the act it previews. It writes nothing, queues
    nothing, and takes the same role — a `viewer` gets the same 403 here as
    on the act, because a preview it could read would be a way to probe
    whether an id exists."""
    return await preview_command(ctx, name, body.args)


@router.post("/commands/{name}")
async def run(name: str, body: CommandRequest, ctx: CommandContextDep) -> dict:
    """The one path a mutation takes (docs/backoffice.md § Commands are
    objects): role, confirmation, describe, execute, audit — so nothing is
    unaudited and no rule lives in a handler. Answers the audit entry, and
    the job when one was queued."""
    return await run_command(ctx, name, body.args, body.confirmation)


@router.get("/jobs")
async def jobs(
    operator: CurrentOperator,
    reads: OperatorReadsDep,
    limit: int = Query(default=200, ge=1, le=1000),
) -> list[dict]:
    """The job queue: the irreversible work waiting out its window."""
    return await reads.jobs(limit)
