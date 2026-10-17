"""API request and response schemas."""

from datetime import UTC, datetime
from datetime import date as date_type
from typing import Literal

from pydantic import BaseModel, Field

from beats.domain.billing import RateSource
from beats.domain.models import (
    AbsenceType,
    AdjustmentKind,
    BillingTerm,
    ClientFields,
    Contract,
    GoalType,
    ProjectBillingFields,
    ProjectBreakdownEntry,
    ProjectKind,
    RateTerm,
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

    The update is a wholesale replace, so a client that predates a field
    would reset it on every colour change if "not sent" read as "clear".
    `kind` and `contract` therefore tell the two apart through
    `model_fields_set`: left out, the stored value is kept; `contract: null`
    clears the contract. `kind` has no empty state, so null reads as left
    out there.
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
    """Request body for updating a beat. Tags are auto-derived, not sent."""

    id: str
    project_id: str
    start: datetime
    end: datetime | None = None


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
    """Response schema for an absence."""

    id: str
    project_id: str
    date: date_type
    type: AbsenceType
    half_day: bool = False
    note: str | None = None


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
    so it can no longer change."""

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


class ImportSkip(BaseModel):
    """An absence or a balance adjustment in a backup that the import left
    out, because the rule its own route applies refused it: `code` and
    `detail` are what that route would have answered. An absence on a
    project that is no longer a day job is one; an adjustment dated outside
    the contract the backup restored is another."""

    collection: Literal["absences", "balance_adjustments"]
    project_id: str
    date: date_type
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
