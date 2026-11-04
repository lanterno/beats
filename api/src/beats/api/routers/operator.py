"""The operator's routes — mounted only by `operator_server`, never here.

`server.py` must not import this module (a test pins that), and this module
must not import `beats.api.dependencies` or anything else that loads the
API's settings: the operator deployment never holds `JWT_SECRET`. Providers
come from `beats.operator.dependencies`; the error envelope is the shared one
(`beats.api.errors` loads no settings).

Every route is a read in this step (roadmaps/backoffice.md step 2); the
commands arrive with step 3 through one runner, so the audit cannot be
forgotten. A `GET` changes nothing, and the account lookup takes its address
in the **body** — an address in a URL is in Cloud Run's request log for 30
days, the reason `/api/reports` takes its token in a header.
"""

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from beats.operator.dependencies import CommandContextDep, CurrentOperator, OperatorReadsDep
from beats.operator.reads import (
    AbuseReport,
    AccountDetail,
    AccountMatch,
    AttentionCounts,
    CapacityReport,
    OrganisationDetail,
    OrganisationSummary,
    OrgAuditRow,
)
from beats.operator.runner import run_command

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
    """The operator's own audit — empty until step 3's commands write it."""
    return await reads.audit_log(limit)


class CommandRequest(BaseModel):
    args: dict = Field(default_factory=dict)
    # What the operator typed back — the account's email, the organisation's
    # name — compared by the runner against the subject, never stored.
    confirmation: str | None = None


@router.post("/commands/{name}")
async def run(name: str, body: CommandRequest, ctx: CommandContextDep) -> dict:
    """The one path a mutation takes (roadmaps/backoffice.md § Commands are
    objects): role, confirmation, describe, execute, audit — so nothing is
    unaudited and no rule lives in a handler. Answers the audit entry, and
    the job when one was queued (step 4)."""
    return await run_command(ctx, name, body.args, body.confirmation)


@router.get("/jobs")
async def jobs(
    operator: CurrentOperator,
    reads: OperatorReadsDep,
    limit: int = Query(default=200, ge=1, le=1000),
) -> list[dict]:
    """The job queue — empty until step 4's jobs exist."""
    return await reads.jobs(limit)
