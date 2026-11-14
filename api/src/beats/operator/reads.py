"""What the operator's pages read, as shapes and a Protocol.

Queries have no service layer (docs/backoffice.md § Architecture): "accounts
created per day" and "organisations with no owner" are aggregation pipelines
with no rule to enforce, so a domain service
in front of them would be a pass-through. The router calls
`MongoOperatorReads` (infrastructure/operator_reads.py) through this
Protocol so a test can fake it.

Every field here is the left-hand column of the line — ids, counts, dates,
states, domains — never what someone tracked. The wall test
(`test_operator.py`) plants a sentinel in every right-column thing and greps
every response for it, so a field added here that leaks is a failing test,
not a review comment.
"""

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Literal, Protocol

# The landing page's thresholds. They decide only what the operator is shown,
# never what a user is allowed, so constants are enough; changing one is a
# deploy, and no user notices it.
COACH_CAP_ATTENTION_FRACTION = 0.8
SUPERSEDED_ATTENTION_DAYS = 30
ABSENCE_REQUEST_ATTENTION_DAYS = 14

# How much of one account's coach spend its page draws. Long enough to show
# the shape of a month that is running away, short enough that the answer
# stays one small list.
ACCOUNT_COACH_SPEND_DAYS = 30


@dataclass(frozen=True)
class AttentionCounts:
    """The landing page: each count links to the thing."""

    organisations_without_owner: int
    organisations_all_owners_suspended: int
    jobs_queued: int
    jobs_failed: int
    approvals_superseded_over_30d: int
    absence_requests_pending_over_14d: int
    accounts_near_coach_cap: int


QueueKind = Literal[
    "organisation_without_owner",
    "organisation_all_owners_suspended",
    "job_failed",
    "job_queued",
    "approvals_superseded",
    "absence_requests_pending",
    "account_near_coach_cap",
]


@dataclass(frozen=True)
class QueueRow:
    """One row behind an Attention count: what it is, which id, since when,
    and when it is due. Ids and dates only. Nothing stores that a row was
    handled; it leaves when its condition clears.

    Superseded approvals and absence requests are one row per organisation
    (`count` of them, `since` the oldest), with no member named."""

    kind: QueueKind
    subject_id: str
    since: datetime | None
    due: datetime
    count: int = 1


def queue_due(kind: QueueKind, since: datetime | None, now: datetime) -> datetime:
    """When a queue row is due, from the same constants Attention counts by.

    A superseded approval is due `SUPERSEDED_ATTENTION_DAYS` after it was
    superseded and an absence request `ABSENCE_REQUEST_ATTENTION_DAYS` after
    it was made — the moment Attention starts counting it. A queued job is
    due when its window ends, the last moment it can still be cancelled
    (`since` is its `run_after`). Everything else needs somebody now: a
    failed job, an organisation nobody can manage, a coach cap in reach.
    A condition with no stored date is due `now`."""
    if since is None:
        return now
    if kind == "approvals_superseded":
        return since + timedelta(days=SUPERSEDED_ATTENTION_DAYS)
    if kind == "absence_requests_pending":
        return since + timedelta(days=ABSENCE_REQUEST_ATTENTION_DAYS)
    return since


@dataclass(frozen=True)
class AccountMatch:
    """One row of the exact-email lookup. Case-insensitive, so one mail can
    match two accounts spelled apart."""

    id: str
    email: str
    created_at: datetime | None
    last_seen_on: date | None
    suspended: bool


@dataclass(frozen=True)
class DeviceSummary:
    device_id: str
    created_at: datetime | None
    last_seen: datetime | None
    revoked: bool


@dataclass(frozen=True)
class MembershipSummary:
    organisation_id: str
    organisation_name: str
    role: str
    active: bool


@dataclass(frozen=True)
class AccountDetail:
    id: str
    email: str
    created_at: datetime | None
    last_seen_on: date | None
    suspended_at: datetime | None
    suspended_kind: str | None
    suspended_by: str | None
    sessions_valid_after: datetime | None
    passkeys: int
    sso_providers: list[str] = field(default_factory=list)
    devices: list[DeviceSummary] = field(default_factory=list)
    organisations: list[MembershipSummary] = field(default_factory=list)
    # Counts and an estimate, never the rows: how big, not what.
    projects: int = 0
    sessions: int = 0
    biometric_rows: int = 0
    storage_bytes: int = 0
    coach_spend_usd: float = 0.0
    coach_budget_usd: float | None = None
    integrations: list[str] = field(default_factory=list)
    limits_overridden: bool = False


@dataclass(frozen=True)
class OrganisationSummary:
    id: str
    name: str
    created_at: datetime | None
    members_by_role: dict[str, int]
    active_assignments: int
    retention_years: int | None
    closes_on: date | None
    owners: int
    all_owners_suspended: bool


@dataclass(frozen=True)
class OrganisationDetail:
    summary: OrganisationSummary
    projects: int
    connected_projects: int
    timesheets_by_status: dict[str, int]


@dataclass(frozen=True)
class OrgAuditRow:
    """An audit event **without its `details`**, which carry what the
    organisation wrote: a reopened month's reason, a created project's or
    team's name."""

    at: datetime
    event: str
    actor_user_id: str | None
    actor_kind: str | None
    subject_user_id: str | None
    project_id: str | None


@dataclass(frozen=True)
class AccountFigure:
    """One account on an abuse axis: an id and a number, nothing else."""

    user_id: str
    value: float


@dataclass(frozen=True)
class DomainFigure:
    """Webhook destinations by domain: outbound HTTP from our servers to
    arbitrary URLs is ours to answer for. The domain, never the full URL."""

    domain: str
    value: int


@dataclass(frozen=True)
class DayFigure:
    day: str
    value: float


@dataclass(frozen=True)
class AbuseReport:
    coach_spend_per_account: list[AccountFigure]
    flow_windows_per_account_today: list[AccountFigure]
    sessions_created_7d_per_account: list[AccountFigure]
    report_links_per_account: list[AccountFigure]
    webhook_domains: list[DomainFigure]
    devices_per_account: list[AccountFigure]
    signups_per_day: list[DayFigure]


@dataclass(frozen=True)
class CollectionSize:
    name: str
    documents: int
    storage_bytes: int


@dataclass(frozen=True)
class CoachCostDay:
    day: str
    model: str
    cost_usd: float
    input_tokens: int
    cache_read_tokens: int
    calls: int


@dataclass(frozen=True)
class CapacityReport:
    collections: list[CollectionSize]
    coach_cost: list[CoachCostDay]


class OperatorReads(Protocol):
    """The aggregates the operator's pages read, and nothing else."""

    async def attention(self) -> AttentionCounts: ...
    async def queue(self) -> list[QueueRow]: ...
    async def audit_log(self, limit: int = 200, subject_id: str | None = None) -> list[dict]: ...
    async def account_coach_spend(self, user_id: str, days: int = 30) -> list[DayFigure]: ...
    async def jobs(self, limit: int = 200) -> list[dict]: ...
    async def find_accounts(self, email: str) -> list[AccountMatch]: ...
    async def account(self, user_id: str) -> AccountDetail | None: ...
    async def organisations(self) -> list[OrganisationSummary]: ...
    async def organisation(self, organisation_id: str) -> OrganisationDetail | None: ...
    async def organisation_audit(
        self, organisation_id: str, limit: int = 200
    ) -> list[OrgAuditRow]: ...
    async def abuse(self) -> AbuseReport: ...
    async def capacity(self) -> CapacityReport: ...
