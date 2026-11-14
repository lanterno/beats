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
# An erasure request logged this long ago with no erasure queued needs
# somebody: PRIVACY.md promises deletion seven days after queueing, inside
# the legal month, so the risk is a mail forgotten before anything is queued.
# The month is a calendar month (GDPR Art. 12(3); the back office's
# `deadlineOf`), 28 days at its shortest: 14 here and the 7 of the window
# are 21, inside it.
ERASURE_REQUEST_ATTENTION_DAYS = 14

# How much of one account's coach spend its page draws. Long enough to show
# the shape of a month that is running away, short enough that the answer
# stays one small list.
ACCOUNT_COACH_SPEND_DAYS = 30

# How many days of the platform's coach cost Capacity reads, today included:
# a 30-day chart, and the whole of this month on its 31st, which the month's
# spend is summed over. Bounded, so the answer stays one small list however
# long the platform has run.
COACH_COST_DAYS = 31

# The database's sizes, one a UTC day, kept by the job runner
# (infrastructure/database_sizes.py): this many days, by a TTL index, and the
# series Capacity draws is every one of them. A year and a bit, so a month
# can be set beside the same month a year before.
SIZE_KEEP_DAYS = 400
# The pace is read over this many days back from the newest size kept: long
# enough that one day's purge or restore does not swing it, short enough to
# be the current pace rather than the platform's whole history.
GROWTH_PACE_DAYS = 30


@dataclass(frozen=True)
class AttentionCounts:
    """The landing page: each count links to the thing."""

    organisations_without_owner: int
    controls_paused: int
    organisations_all_owners_suspended: int
    jobs_queued: int
    jobs_failed: int
    approvals_superseded_over_30d: int
    absence_requests_pending_over_14d: int
    accounts_near_coach_cap: int
    erasure_requests_overdue: int


QueueKind = Literal[
    "organisation_without_owner",
    "organisation_all_owners_suspended",
    "job_failed",
    "job_queued",
    "approvals_superseded",
    "absence_requests_pending",
    "account_near_coach_cap",
    "control_paused",
    "control_slowed",
    "control_slowed_network",
    "erasure_request_open",
]


@dataclass(frozen=True)
class QueueRow:
    """One row behind an Attention count: what it is, which id, since when,
    and when it is due. Ids and dates only. Nothing stores that a row was
    handled; it leaves when its condition clears.

    Superseded approvals and absence requests are one row per organisation
    (`count` of them, `since` the oldest), with no member named.

    A control in force is a row by what it does and to whom:
    `control_paused` stops one kind of work for everyone, `control_slowed`
    holds every sign-up to a ceiling, and `control_slowed_network` is the
    networks slowed one by one — a single row, `count` of them and `since`
    the soonest end, with no network named."""

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
    A control is due when it ends (`since` is its `until`): until then it
    stands on purpose, and the row says so. A condition with no stored date
    is due `now`."""
    if since is None:
        return now
    if kind == "approvals_superseded":
        return since + timedelta(days=SUPERSEDED_ATTENTION_DAYS)
    if kind == "absence_requests_pending":
        return since + timedelta(days=ABSENCE_REQUEST_ATTENTION_DAYS)
    if kind == "erasure_request_open":
        return since + timedelta(days=ERASURE_REQUEST_ATTENTION_DAYS)
    return since


@dataclass(frozen=True)
class ControlState:
    """One control as the Access page shows it. The operator's own text
    (`reason`) is theirs to read back; a user never sees it.

    `network` is the opaque key of the one network a `signups` slow-down
    covers, and None for a control that covers everyone; there may be any
    number of the first beside the second. The page says "one network",
    never the key, and hands the key back in a command's body to change or
    lift that control alone — never in a URL, which Cloud Run logs, and
    never into `operator_audit`, whose rows say `one_network` instead."""

    name: str
    in_force: bool
    until: datetime | None
    value: int | None
    reason: str | None
    set_by: str | None
    set_at: datetime | None
    network: str | None = None


ErasureRequestStatus = Literal["open", "erasure_queued", "erasure_ran", "closed"]


@dataclass(frozen=True)
class ErasureRequestState:
    """One logged erasure request: the day it arrived, the operator's
    reference, the account by id or none, and where it stands — read off
    the job queue, never stored."""

    id: str
    reference: str
    received_on: date
    subject_id: str | None
    status: ErasureRequestStatus
    closed_at: datetime | None
    closed_reason: str | None


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


# The signal shows a group only at or above this size: below it, nothing.
SIGNUP_NETWORK_MIN_GROUP = 5
# How many of the same hour of the week make the "usual" figure.
SIGNUP_BASELINE_WEEKS = 8
# An hour is called above usual only from this many sign-ups, and only at
# twice the usual or more: against a usual of none, one sign-up is more,
# and is still nothing to look at.
SIGNUP_WAVE_MIN = 5


def signups_above_usual(completed: int, usual: float) -> bool:
    """Whether this hour's sign-ups are worth the page's attention: at least
    `SIGNUP_WAVE_MIN` of them, and at least twice the usual for the hour."""
    return completed >= SIGNUP_WAVE_MIN and completed >= 2 * usual


@dataclass(frozen=True)
class SignupWave:
    """This hour's sign-ups against the usual for this hour of the week, and
    the largest network's share — the key is opaque and day-scoped, the page
    says "Network A", and no account is joined to it anywhere.

    Nothing about a network below `SIGNUP_NETWORK_MIN_GROUP` is said, not
    even how many there are: a count of networks this hour, beside the
    hour's accounts, would tell small groups apart."""

    hour: str
    completed: int
    usual: float
    # `signups_above_usual(completed, usual)`: the page judges nothing itself.
    above_usual: bool
    accounts_with_writes: int
    largest_group: int | None
    largest_key: str | None


@dataclass(frozen=True)
class AbuseReport:
    coach_spend_per_account: list[AccountFigure]
    flow_windows_per_account_today: list[AccountFigure]
    sessions_created_7d_per_account: list[AccountFigure]
    report_links_per_account: list[AccountFigure]
    webhook_domains: list[DomainFigure]
    devices_per_account: list[AccountFigure]
    signups_per_day: list[DayFigure]
    signup_wave: SignupWave | None = None


@dataclass(frozen=True)
class CollectionSize:
    name: str
    documents: int
    storage_bytes: int
    # What the collection's indexes take up besides.
    index_bytes: int = 0
    # Its pace between the two days the database's is read between
    # (`DatabaseGrowth`): bytes a month, and that as a share of what it took
    # up on the first of them. None when there is no pace yet, or the
    # collection was not kept on both days; the share is None too when it
    # took up nothing on the first.
    growth_bytes_a_month: float | None = None
    growth_share_a_month: float | None = None


@dataclass(frozen=True)
class SizeDay:
    """The database's size on disk as the job runner kept it that UTC day:
    every collection's `storage_bytes` added up, as the page's own total is."""

    day: date
    storage_bytes: int


@dataclass(frozen=True)
class DatabaseGrowth:
    """The pace: what the database moved between two days kept, carried to a
    month of 30 days. `until` is the newest size kept and `since` the oldest
    within `GROWTH_PACE_DAYS` before it — or, when the runner kept none in
    that span, the one kept just before `until`."""

    since: date
    until: date
    change_bytes: int
    bytes_a_month: float


@dataclass(frozen=True)
class DatabaseConnections:
    """`serverStatus`'s connections as the cluster answers them: those open
    now, and how many it allows — open and still available together, which on
    Atlas's free tier is its 500."""

    current: int
    allowed: int


@dataclass(frozen=True)
class CoachCostDay:
    day: str
    model: str
    cost_usd: float
    # Uncached input; what came from the cache is `cache_read_tokens`.
    input_tokens: int
    cache_read_tokens: int
    calls: int
    # What the cache saved that day on that model, at its rates
    # (`coach/pricing.py`): reads not billed as input, less what writes
    # paid over it. Negative when the writes cost more.
    cache_saved_usd: float


@dataclass(frozen=True)
class CapacityReport:
    collections: list[CollectionSize]
    # The last COACH_COST_DAYS days (UTC), newest first, one row per day and
    # model; a day nothing was spent has no row.
    coach_cost: list[CoachCostDay]
    # Every size the job runner has kept, oldest first; a day it did not run
    # has no row. Empty until its first run.
    sizes: list[SizeDay] = field(default_factory=list)
    # None below two days kept: one size is where the database stands, not
    # a pace.
    growth: DatabaseGrowth | None = None
    # None when the cluster would not say: a database user without the
    # serverStatus action, or a server that refuses the command.
    connections: DatabaseConnections | None = None


class OperatorReads(Protocol):
    """The aggregates the operator's pages read, and nothing else."""

    async def attention(self) -> AttentionCounts: ...
    async def queue(self) -> list[QueueRow]: ...
    async def controls(self) -> list[ControlState]: ...
    async def erasure_requests(self) -> list[ErasureRequestState]: ...
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
