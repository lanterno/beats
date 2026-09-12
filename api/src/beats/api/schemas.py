"""API request and response schemas."""

from datetime import UTC, datetime
from datetime import date as date_type

from pydantic import BaseModel, ConfigDict, Field

from beats.domain.models import AbsenceType, Contract, GoalType, ProjectBreakdownEntry, ProjectKind


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


class WeekBreakdownLogResponse(BaseModel):
    """One completed session of a day, when `display_each_log_duration` is set."""

    id: str | None
    start: str
    end: str | None
    duration: str


class WeekBreakdownResponse(BaseModel):
    """GET /{id}/week/: the week's tracked time by day and in total, its
    Monday, and the goal resolved for it.

    Each day is the time tracked as a duration string (`"2:30:00"`), or —
    with `display_each_log_duration` — that day's completed sessions.
    `effective_goal` is the goal as `Project.effective_goal` resolves it for
    the week: on a day job the contract governs, the term's plain hours.
    `contract_expected` is what the contract expects of that week after
    holidays and absences — the week card's figure, which the history row
    shows in place of the nominal hours — on a day job with a contract; None
    elsewhere, and under the null rule (a term of 0 hours, a week before the
    first term).
    """

    model_config = ConfigDict(populate_by_name=True)

    monday: str | list[WeekBreakdownLogResponse] = Field(alias="Monday")
    tuesday: str | list[WeekBreakdownLogResponse] = Field(alias="Tuesday")
    wednesday: str | list[WeekBreakdownLogResponse] = Field(alias="Wednesday")
    thursday: str | list[WeekBreakdownLogResponse] = Field(alias="Thursday")
    friday: str | list[WeekBreakdownLogResponse] = Field(alias="Friday")
    saturday: str | list[WeekBreakdownLogResponse] = Field(alias="Saturday")
    sunday: str | list[WeekBreakdownLogResponse] = Field(alias="Sunday")
    total_hours: float
    week_start: date_type
    effective_goal: float | None = None
    effective_goal_type: GoalType | None = None
    effective_goal_overridden: bool = False
    contract_expected: float | None = None


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
