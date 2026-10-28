"""API request and response schemas."""

from datetime import UTC, datetime
from datetime import date as date_type
from typing import Literal

from pydantic import BaseModel, Field

from beats.domain.billing import RateSource
from beats.domain.billing_budgets import BillingBudgetState
from beats.domain.models import (
    AbsenceType,
    AdjustmentKind,
    BillingBudgetFields,
    BillingBudgetPeriod,
    BillingBudgetScope,
    BillingBudgetUnit,
    BillingTerm,
    ClientFields,
    Contract,
    GoalType,
    JoinDecision,
    MembershipEnd,
    MemberTotals,
    OrganisationFields,
    OrgProject,
    OrgRole,
    ProjectBillingFields,
    ProjectBreakdownEntry,
    ProjectKind,
    ProjectOrganisation,
    RateTerm,
    ReportLinkFields,
)


class RecordTimeRequest(BaseModel):
    """Request body for recording time (start/stop timer)."""

    time: datetime = Field(default_factory=lambda: datetime.now(UTC))


class CreateProjectRequest(BaseModel):
    """Request body for creating a project.

    Accepts every field UpdateProjectRequest does, bar `id` and `archived`.
    A field settable only on update leaves a freshly created project at its
    default until a separate PUT the create form has no way to make: the
    daemon's flow-score category_fit silently could not match work to a new
    project until `category` was added here, and a GitHub repo, autostart
    path or goal type typed at creation was dropped the same way.
    """

    name: str
    description: str | None = None
    color: str | None = None
    weekly_goal: float | None = None  # Weekly goal in hours
    goal_type: GoalType = GoalType.TARGET
    github_repo: str | None = None  # "owner/repo"
    category: str | None = None  # Activity category for flow score matching
    autostart_repos: list[str] = Field(default_factory=list)  # Local repo paths
    kind: ProjectKind = ProjectKind.SIDE_PROJECT
    # The domain Contract itself, so its validators are the request's: a bad
    # term is a 422 whose `fields` name the term (`contract.terms.1`). Only
    # meaningful on a day job; the model does not refuse it elsewhere.
    contract: Contract | None = None


class UpdateProjectRequest(BaseModel):
    """Request body for updating a project.

    Only `id` and `name` are required, and every other field is read by
    presence (`model_fields_set`): left out, the stored value is kept; sent,
    it replaces it. A client sends what it edits, and must not wipe what it
    does not know: the project page's colour picker sends no GitHub repo,
    category or autostart repos, and while "not sent" read as "clear" every
    colour change reset all three. The defaults below are therefore never
    written over a stored value.

    `null` clears `description`, `color`, `weekly_goal`, `github_repo`,
    `category` and `contract`; `[]` clears `autostart_repos`. `archived` and
    `goal_type` have no empty state and refuse null (422); `kind` has none
    either, and reads null as left out. A day job moved to another kind
    loses its contract with it; a contract sent with any other kind is a 409.
    """

    id: str
    name: str
    description: str | None = None
    color: str | None = None
    archived: bool = False
    weekly_goal: float | None = None  # Weekly goal in hours
    # GoalType is a StrEnum so the JSON wire format stays {"goal_type": "target"} —
    # but invalid values now fail at request validation (clean 422 with the
    # allowed list) instead of bubbling up as a 500 from Project() construction.
    goal_type: GoalType = GoalType.TARGET
    github_repo: str | None = None  # "owner/repo"
    category: str | None = None  # Activity category for flow score matching
    autostart_repos: list[str] = Field(default_factory=list)  # Local repo paths
    kind: ProjectKind | None = None
    contract: Contract | None = None


class GoalOverrideRequest(BaseModel):
    """Request body for a goal override.

    weekly_goal=None means "no goal for this window" (one-off or permanent).
    """

    week_of: date_type | None = None
    effective_from: date_type | None = None
    weekly_goal: float | None = None
    goal_type: GoalType | None = None
    # No note: overrides carry only structured targets, no free-text reason.


class CreateBeatRequest(BaseModel):
    """Request body for creating a beat.

    No note/tags: the app takes no free-text input. Tags are auto-derived
    server-side from the daemon's flow signals (see BeatService).
    """

    project_id: str
    start: datetime = Field(default_factory=lambda: datetime.now(UTC))
    end: datetime | None = None


class UpdateBeatRequest(BaseModel):
    """Request body for editing a beat: these fields, and only these, change.
    Tags are auto-derived, not sent. The note (#348): a string sets it, an
    empty string clears it, and omitted or null keeps it as stored — so every
    client that never sends one (the daemon, the companion, the extension)
    keeps meaning what it meant. On an organisation's project the note is
    part of the organisation's record (rule 3), which is why the one input
    that writes it carries the marker saying who reads it."""

    id: str
    project_id: str
    start: datetime
    end: datetime | None = None
    note: str | None = Field(default=None, max_length=2000)


class GoalOverrideResponse(BaseModel):
    """Response schema for a goal override (mirrors the request shape)."""

    week_of: date_type | None = None
    effective_from: date_type | None = None
    weekly_goal: float | None = None
    goal_type: GoalType | None = None
    note: str | None = None


class ProjectResponse(BaseModel):
    """Canonical response shape for a project — every field of the domain
    Project the API exposes. Previously declared only 6 of 11 fields;
    list/update routes returned `model_dump()` with no response_model
    declared, so the OpenAPI contract was silently widened. Now precise so
    generated clients see the full shape.

    `contract` is the domain model as stored — the terms, region, opening
    balance and end date — and is only meaningful when `kind` is `day_job`.
    """

    id: str
    name: str
    description: str | None = None
    color: str | None = None
    archived: bool = False
    weekly_goal: float | None = None
    goal_type: GoalType = GoalType.TARGET
    goal_overrides: list[GoalOverrideResponse] = Field(default_factory=list)
    github_repo: str | None = None
    category: str | None = None
    autostart_repos: list[str] = Field(default_factory=list)
    kind: ProjectKind = ProjectKind.SIDE_PROJECT
    contract: Contract | None = None
    # The organisation that owns the project, when it is not the caller: its
    # name and logo mark the project in a list, and `shared_from` is the
    # instant from which the caller's hours on it are the organisation's.
    # Null on a personal project (docs/organisations.md).
    organisation: ProjectOrganisation | None = None


class ProjectsListItemResponse(ProjectResponse):
    """The list response shape — same fields as ProjectResponse, plus
    optional aggregations populated when GET /api/projects/ is called
    with `include=totals,this_week,last_tracked`. Each field is None
    when its corresponding include flag wasn't requested. Backward
    compatible because absent values stay None.

    Added in P3.0 of the project-management revamp so the /projects
    index page (P3.1) can load with a single round-trip instead of
    the previous N+1 fan-out the UI did per project.
    """

    total_minutes: float | None = None
    weekly_minutes: float | None = None
    effective_goal: float | None = None
    effective_goal_type: GoalType | None = None
    effective_goal_overridden: bool | None = None
    last_tracked_at: datetime | None = None
    # With `this_week`, on a day job with a contract: the current week
    # against the contract and the balance as of today, both in the request
    # timezone — what GET /{id}/contract/week reports, so the index does not
    # need a request per project. Null on any other project, and — except
    # `contract_worked`, which a day job reports under an objective term too,
    # as the week route does — on a day job whose term this week is objective
    # (see ContractWeek).
    #
    # `contract_worked` is carried even though `weekly_minutes` sits beside
    # it, because the two are not the same figure: `weekly_minutes` is the
    # personal goal's — completed beats only, bucketed by UTC date — while the
    # contract counts a running timer and buckets by local start day in `tz`.
    # A card showing expected · worked · remaining must read all three here.
    contract_expected: float | None = None
    contract_worked: float | None = None
    contract_remaining: float | None = None
    balance: float | None = None


class AbsenceRequest(BaseModel):
    """Request body for recording an absence.

    One per (project, date): a second one posted for the same date replaces
    the first, so this is also how a half day becomes a full one.
    """

    date: date_type
    type: AbsenceType
    half_day: bool = False
    note: str | None = None


class AbsenceResponse(BaseModel):
    """Response schema for an absence. `organisation_id` is set on one
    recorded on an organisation's project: that organisation's record."""

    id: str
    project_id: str
    date: date_type
    type: AbsenceType
    half_day: bool = False
    note: str | None = None
    organisation_id: str | None = None


class AdjustmentResponse(BaseModel):
    """Response schema for a balance adjustment: the record as stored. What
    it moved the balance by is the ledger's (`applied`), worked out on every
    read."""

    id: str
    project_id: str
    date: date_type
    kind: AdjustmentKind
    hours: float
    note: str | None = None


class ClientWriteRequest(ClientFields):
    """Request body for adding a client: the domain's fields, every key
    required, null where it may be. Its rates are `rate_minor` per hour in
    the currency's minor units, strictly ascending by `effective_from`."""


class ClientUpdateRequest(ClientFields):
    """Request body for replacing a client: the same keys, and
    `rewrite_past`, required, saying the caller has confirmed a change to
    figures before the current month."""

    rewrite_past: bool = Field(strict=True)


class ClientResponse(BaseModel):
    """A client as stored, with its currency's minor units from the API's
    table, and whether its currency is locked: something is priced in it,
    or a money billing budget is in it, so it can no longer change."""

    id: str
    name: str
    contact_name: str | None = None
    contact_email: str | None = None
    currency: str
    minor_units: int
    rates: list[RateTerm]
    archived: bool
    created_at: datetime
    currency_locked: bool


class ProjectBillingRequest(ProjectBillingFields):
    """Request body for billing a project: its client and the whole list of
    terms, and `rewrite_past`, all required."""

    rewrite_past: bool = Field(strict=True)


class ProjectBillingResponse(BaseModel):
    """A project's billing, with its client's currency and minor units, the
    currency every `rate_minor` in it is in."""

    project_id: str
    client_id: str
    currency: str
    minor_units: int
    terms: list[BillingTerm]


class BillableOverrideRequest(BaseModel):
    """Request body for marking one entry billable or not."""

    billable: bool = Field(strict=True)


class BillableOverrideResponse(BaseModel):
    """One entry's billable mark, against its project's term."""

    beat_id: str
    billable: bool


class BillingLineResponse(BaseModel):
    """A run of consecutive days of one project at one rate from one source.
    `rate_minor`, `source` and `amount_minor` are all null on an unpriced
    run. `hours` are to the hundredth, and `amount_minor` is `hours` times
    `rate_minor`, to a whole minor unit, half-up."""

    project_id: str
    project_name: str
    rate_minor: int | None
    source: RateSource | None
    first: date_type
    last: date_type
    hours: float
    amount_minor: int | None


class BillingEntryResponse(BaseModel):
    """A finished entry of a billed project, billable or not. `day` is the
    local day it started on, which decides its month and its rate. `hours`
    is for display; the lines are the figures."""

    beat_id: str
    project_id: str
    day: date_type
    start: datetime
    end: datetime
    hours: float
    billable: bool
    overridden: bool
    rate_minor: int | None


class ClientBillingResponse(BaseModel):
    """One client's figures for the month, in its one currency. The hours and
    the amount are sums of the lines; `unpriced_hours` is the part of
    `billable_hours` with no rate. `running`: a billable timer is running,
    and counts once it stops."""

    client_id: str
    name: str
    archived: bool
    currency: str
    minor_units: int
    running: bool
    billable_hours: float
    non_billable_hours: float
    unpriced_hours: float
    amount_minor: int
    lines: list[BillingLineResponse]
    entries: list[BillingEntryResponse]


class CurrencyTotalResponse(BaseModel):
    """Every listed client in one currency, summed: no figure holds two."""

    currency: str
    minor_units: int
    billable_hours: float
    unpriced_hours: float
    amount_minor: int


class UnattachedHoursResponse(BaseModel):
    """A freelance project with finished hours in the month and no client:
    hours in no figure of the report."""

    project_id: str
    name: str
    hours: float


class BillingMonthResponse(BaseModel):
    """What is billable in a month, per client and per currency: the whole
    month once it has ended, `first` through today while it runs."""

    month: str  # YYYY-MM
    first: date_type
    last: date_type
    totals: list[CurrencyTotalResponse]
    clients: list[ClientBillingResponse]
    unattached: list[UnattachedHoursResponse]


class ReportLinkRequest(ReportLinkFields):
    """Request body for minting a report link: the range, the timezone its
    days are bucketed in, and the two flags, every key required. The range
    runs forward and covers at most 366 days."""


class ReportLinkResponse(BaseModel):
    """A report link as its owner sees it, token included: the owner has to
    be able to re-copy the link they sent a client last month."""

    id: str
    client_id: str
    token: str
    first: date_type
    last: date_type
    tz: str
    show_amounts: bool
    show_entries: bool
    created_at: datetime


# ---------------------------------------------------------------------- #
# The public report (phase 1c)
#
# These three are what a reader with no session sees, and they are written
# out field by field on purpose: they do not inherit from
# `ClientBillingResponse`, `BillingLineResponse` or `BillingEntryResponse`,
# so a field added to the private month report later cannot reach a client's
# eyes by inheritance. Deliberately absent, though the assembler has them:
# `client_id`, `project_id` and `beat_id` (a client has no use for the
# owner's internal ids), `source` and `overridden` (how a figure was arrived
# at), `non_billable_hours` (hours the client is not billed for) and
# `running` (a report says nothing about now). See docs/billing.md, 1c
# decisions 4, 5 and 7.
# ---------------------------------------------------------------------- #


class ReportLineResponse(BaseModel):
    """A run of consecutive days of one project at one rate. `rate_minor` and
    `amount_minor` are null on an unpriced run, and on every line when the
    link does not show amounts."""

    project_name: str
    first: date_type
    last: date_type
    hours: float
    rate_minor: int | None
    amount_minor: int | None


class ReportEntryResponse(BaseModel):
    """One billable entry: the local day it started on, when it ran, and how
    long. Empty on a link that does not show entries."""

    day: date_type
    start: datetime
    end: datetime
    hours: float


class ReportResponse(BaseModel):
    """What `GET /api/reports/{token}` answers: one client's billable work
    over the link's frozen range.

    With `show_amounts` false, `currency`, `minor_units`, `unpriced_hours`,
    `amount_minor` and every line's rate and amount are null, and the hours
    still add up — a proof of time with the price left out.
    """

    client_name: str
    first: date_type
    last: date_type
    show_amounts: bool
    show_entries: bool
    currency: str | None
    minor_units: int | None
    billable_hours: float
    unpriced_hours: float | None
    amount_minor: int | None
    lines: list[ReportLineResponse]
    entries: list[ReportEntryResponse]


class BillingBudgetRequest(BillingBudgetFields):
    """Request body for a billing budget: the domain's fields, every key
    required, null where it may be. Exactly the limit of its `unit` is set
    (`limit_hours` to the hundredth, or `limit_minor` in the client's
    currency), and `starts_on` only on a total."""


class BillingBudgetResponse(BaseModel):
    """A billing budget as stored, with its client and that client's
    currency and minor units, the currency a `limit_minor` is in."""

    scope: BillingBudgetScope
    scope_id: str
    client_id: str
    currency: str
    minor_units: int
    unit: BillingBudgetUnit
    period: BillingBudgetPeriod
    limit_hours: float | None
    limit_minor: int | None
    starts_on: date_type | None
    warn_at_percent: int


class BillingBudgetRunningResponse(BaseModel):
    """A running timer that counts on a billing budget, and the instants,
    in UTC, at which it alone would cross the warning and the limit: null
    once crossed, and both null when it has no rate under a money budget or
    another timer counts too."""

    project_id: str
    since: datetime
    priced: bool
    near_at: datetime | None
    over_at: datetime | None


class BillingBudgetStatusResponse(BaseModel):
    """A billing budget read as of today: the current month, or a total from
    `starts_on`, through `through`. The three figures are there whatever the
    unit; only the unit's own `remaining_…` is set, negative when over. No
    figure counts a running timer: `running` answers it. An upcoming total
    has no figures, no projection and no running timer. `active` is false
    while its client or its project is archived: it is read, but never
    alerts."""

    scope: BillingBudgetScope
    scope_id: str
    client_id: str
    name: str
    active: bool
    currency: str
    minor_units: int
    unit: BillingBudgetUnit
    period: BillingBudgetPeriod
    limit_hours: float | None
    limit_minor: int | None
    starts_on: date_type | None
    warn_at_percent: int
    upcoming: bool
    first: date_type
    last: date_type | None
    through: date_type | None
    billable_hours: float
    unpriced_hours: float
    amount_minor: int
    remaining_hours: float | None
    remaining_minor: int | None
    percent_used: int
    state: BillingBudgetState
    runs_out_on: date_type | None
    running: BillingBudgetRunningResponse | None


class CurrencyResponse(BaseModel):
    """A currency a client may be billed in, and its minor units."""

    code: str
    minor_units: int


class ImportCounts(BaseModel):
    """How many of each record a backup import wrote."""

    projects: int
    beats: int
    absences: int
    balance_adjustments: int
    clients: int
    project_billing: int
    billable_overrides: int
    billing_budgets: int


class ImportSkip(BaseModel):
    """A record in a backup that the import left out, with the code and
    detail its own route would have answered. An absence on a project that
    is no longer a day job is one; an adjustment dated outside the contract
    the backup restored is another; an organisation's project the account
    is no longer assigned to (ORGANISATION_PROJECT), and every session,
    absence and adjustment on it, is a third — a backup does not restore a
    project the organisation owns (docs/organisations.md)."""

    collection: Literal["projects", "beats", "absences", "balance_adjustments"]
    project_id: str
    date: date_type | None
    code: str
    detail: str


class ImportResponse(BaseModel):
    """What `POST /api/export/import` did with a backup."""

    status: Literal["ok"]
    imported: ImportCounts
    skipped: list[ImportSkip]


class TimerStatusResponse(BaseModel):
    """Response schema for timer status."""

    isBeating: bool
    project: ProjectResponse | None = None
    since: str | None = None
    so_far: str | None = None
    last_beat: dict | None = None


class DurationResponse(BaseModel):
    """Response schema for duration queries."""

    duration: str


class MonthlyTotalsResponse(BaseModel):
    """Response schema for monthly totals."""

    durations_per_month: dict[str, float]
    total_minutes: int
    warnings: list[str]


class HeatmapDayResponse(BaseModel):
    """Response schema for a single day in the contribution heatmap."""

    date: str
    total_minutes: int
    session_count: int
    project_count: int


class RhythmSlotResponse(BaseModel):
    """Response schema for a half-hour slot in the daily rhythm chart."""

    slot: int
    minutes: float


class ProductivityScoreResponse(BaseModel):
    """Response schema for productivity score."""

    score: int
    components: dict[str, int]


class ScoreHistoryItem(BaseModel):
    """A single week's productivity score."""

    week_of: str
    score: int


class WeeklyDigestResponse(BaseModel):
    """Response schema for a weekly digest."""

    id: str | None = None
    week_of: date_type
    generated_at: datetime
    total_hours: float
    session_count: int
    active_days: int
    top_project_id: str | None = None
    top_project_name: str | None = None
    top_project_hours: float = 0
    vs_last_week_pct: float | None = None
    longest_day: str | None = None
    longest_day_hours: float = 0
    best_streak: int = 0
    observation: str = ""
    project_breakdown: list[ProjectBreakdownEntry] = Field(default_factory=list)
    productivity_score: int = 0


class InsightCardResponse(BaseModel):
    """Response schema for a pattern insight card."""

    id: str
    type: str
    title: str
    body: str
    data: dict = Field(default_factory=dict)
    priority: int = 3


class PatternsResponse(BaseModel):
    """Response schema for pattern detection results."""

    insights: list[InsightCardResponse]
    generated_at: datetime


class SuggestionResponse(BaseModel):
    """Response schema for a daily plan suggestion."""

    project_id: str
    project_name: str
    suggested_minutes: int
    reasoning: str


class FocusScoreResponse(BaseModel):
    """Response schema for a focus quality score."""

    beat_id: str
    score: int
    components: dict[str, int]


class ProjectHealthResponse(BaseModel):
    """Response schema for project health metrics."""

    project_id: str
    project_name: str
    days_since_last: int | None = None
    weekly_goal_trend: list[float] = Field(default_factory=list)
    avg_session_length_trend: list[float] = Field(default_factory=list)
    alert: str | None = None


class InboxItemResponse(BaseModel):
    """A single card in the unified Inbox.

    Normalizes outputs from the intelligence module (patterns, suggestions,
    project health alerts) into one shape the dashboard can render.
    """

    id: str
    kind: str  # "pattern" | "suggestion" | "project_health"
    severity: str  # "high" | "medium" | "low"
    title: str
    body: str
    cta_label: str | None = None
    cta_href: str | None = None
    data: dict = Field(default_factory=dict)


class InboxResponse(BaseModel):
    """Response schema for the aggregated intelligence Inbox."""

    items: list[InboxItemResponse]
    generated_at: datetime


# --- Organisations (docs/organisations.md) ------------------------------------


class OrganisationResponse(OrganisationFields):
    id: str
    created_at: datetime


class MembershipResponse(BaseModel):
    """One of the caller's organisations, with their standing in it. A
    membership that ended (`left_at`) is listed too: the archive of the
    person's own hours there is reached through it.

    `user_id` is the caller's own, so a client can tell which row of
    `/members` or which timesheet is theirs without matching on the address
    they joined under — which an account that changed its email, or signed
    in through a provider, no longer has."""

    user_id: str
    organisation: OrganisationResponse
    role: OrgRole
    joined_at: datetime
    left_at: datetime | None
    left_reason: MembershipEnd | None


class MemberResponse(BaseModel):
    """A member as the organisation lists them: the name and address they
    joined under. `user_id` is a tombstone once the account has been erased."""

    user_id: str
    name: str
    email: str
    role: OrgRole
    joined_at: datetime
    left_at: datetime | None


class RoleRequest(BaseModel):
    role: OrgRole


class InviteRequest(BaseModel):
    """An invitation to one address, or with `email` null an invite link.
    `requires_approval` is read on a link alone; no invite carries the
    owner role (403 OWNER_ROLE_RESERVED)."""

    email: str | None = Field(default=None, max_length=254)
    role: OrgRole = OrgRole.MEMBER
    requires_approval: bool = False
    expires_in_days: int = Field(default=14, ge=1, le=90)


class InviteResponse(BaseModel):
    id: str
    email: str | None
    role: OrgRole
    requires_approval: bool
    token: str
    created_at: datetime
    expires_at: datetime
    accepted_at: datetime | None


class OrganisationCardResponse(BaseModel):
    """An organisation as a joiner sees it before joining: the name and logo."""

    id: str
    name: str
    logo_url: str | None


class InvitationResponse(BaseModel):
    """An open invitation addressed to the caller's own address: who, and as
    what. Not the token — an address is not verified at sign-up, so the way
    in is the link the inviter passed on, which the join route then checks
    against the address too."""

    role: OrgRole
    expires_at: datetime
    organisation: OrganisationCardResponse


class InvitePreviewResponse(BaseModel):
    organisation: OrganisationCardResponse
    role: OrgRole
    requires_approval: bool
    addressed: bool  # to the caller's address, as opposed to a link
    already_member: bool


class JoinResponse(BaseModel):
    """`joined`, with the membership; or `pending`, when the link has an
    approval step and a request is now waiting."""

    status: Literal["joined", "pending"]
    membership: MembershipResponse | None = None


class JoinRequestResponse(BaseModel):
    """A join request with the role approving it grants — the invite's, so
    the admin decides knowing what they are handing over."""

    id: str
    user_id: str
    name: str
    email: str
    role: OrgRole
    requested_at: datetime


class DecideRequest(BaseModel):
    decision: JoinDecision


class OrgProjectRequest(BaseModel):
    """The organisation's fields of one of its projects. On an update a
    field left out is kept and `null` clears a nullable one."""

    name: str = Field(min_length=1, max_length=120)
    description: str | None = None
    color: str | None = None
    kind: ProjectKind = ProjectKind.SIDE_PROJECT
    github_repo: str | None = None
    category: str | None = None
    archived: bool = False


class MergeProjectRequest(BaseModel):
    """Which project the merged one folds into."""

    into: str = Field(min_length=1)


class AssignmentResponse(BaseModel):
    user_id: str
    name: str | None
    shared_from: datetime
    assigned_at: datetime
    ended_at: datetime | None
    has_contract: bool


class OrgProjectResponse(OrgProject):
    members: list[AssignmentResponse]


class ConnectProjectRequest(BaseModel):
    """Connect one of the caller's own projects: from `share_from` (a local
    day in `tz`) the hours and absences on it are the organisation's; null
    starts fresh from now."""

    project_id: str
    share_from: date_type | None = None


class RecordEntryResponse(BaseModel):
    """One finished entry as the organisation reads it: when, how long, and
    the note (decision 1). Nothing about the person beyond that."""

    id: str
    day: date_type
    start: datetime
    end: datetime
    hours: float
    note: str | None


class RecordAbsenceResponse(BaseModel):
    date: date_type
    type: str
    half_day: bool


class MemberBalanceResponse(BaseModel):
    as_of: date_type
    balance: float
    opening: float
    worked: float
    expected_through: float
    adjusted: float


class MemberRecordResponse(BaseModel):
    user_id: str
    name: str
    shared_from: datetime
    active: bool
    hours: float
    entries: list[RecordEntryResponse]
    absences: list[RecordAbsenceResponse]
    has_contract: bool
    balance: MemberBalanceResponse | None
    totals: MemberTotals


class ProjectRecordResponse(BaseModel):
    project: OrgProject
    members: list[MemberRecordResponse]


class RecordResponse(BaseModel):
    """What the organisation sees (`GET /{id}/record`), and what it sees of
    one member (`GET /{id}/visible`) — the same shape from the same read,
    narrowed to one person. Written field by field, as the public report
    is, so what crosses cannot grow by inheritance."""

    organisation: OrganisationCardResponse
    month: str
    first: date_type
    last: date_type
    projects: list[ProjectRecordResponse]


class ArchiveProjectResponse(BaseModel):
    project_id: str
    name: str
    color: str | None
    hours: float
    entries: list[RecordEntryResponse]
    absences: list[RecordAbsenceResponse]


class ArchiveResponse(BaseModel):
    """The person's own hours stamped as one organisation's record, after
    leaving or before: read-only, grouped by project."""

    organisation: OrganisationCardResponse
    role: OrgRole
    joined_at: datetime
    left_at: datetime | None
    hours: float
    projects: list[ArchiveProjectResponse]
