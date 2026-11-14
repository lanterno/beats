"""Domain models - pure business entities with no external dependencies.

The vocabulary is one name — `beats.domain.models` — however many files it
is written in. Past the size ceiling (CLAUDE.md § Conventions), three sections
moved to modules of their own and are re-exported here, so no import site
changed: goals and work contracts (`models_contracts.py`), billing
(`models_billing.py`) and organisations (`models_organisations.py`). The
dependency runs one way — contracts knows nothing of the other two, and
organisations reads contracts — so the facade cannot cycle.
"""

from datetime import UTC, datetime, timedelta
from datetime import date as date_type
from enum import StrEnum
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    computed_field,
)

from beats.domain.models_billing import (
    BILLING_BUDGET_HOURS_MAX,
    BILLING_BUDGET_MINOR_MAX,
    RATE_MINOR_MAX,
    REPORT_RANGE_MAX_DAYS,
    BillableOverride,
    BillingBudget,
    BillingBudgetFields,
    BillingBudgetPeriod,
    BillingBudgetScope,
    BillingBudgetUnit,
    BillingTerm,
    Client,
    ClientFields,
    ProjectBilling,
    ProjectBillingFields,
    RateTerm,
    ReportLink,
    ReportLinkFields,
)

# The domain vocabulary is one name — `beats.domain.models` — however many
# files it is written in. Contracts, billing and organisations each have
# their own module (the size ceiling, CLAUDE.md § Conventions); re-exported here with the
# explicit `X as X` form, so every import site is unchanged and the
# re-export is a declaration rather than an unused import.
from beats.domain.models_contracts import (
    WORKDAYS_PER_WEEK,
    Absence,
    AbsenceType,
    AdjustmentKind,
    BalanceAdjustment,
    BalanceAdjustmentFields,
    CarryOver,
    CompanyHoliday,
    Contract,
    ContractDay,
    ContractTerm,
    ContractWeek,
    DayAbsence,
    GoalOverride,
    GoalType,
    Ledger,
    LedgerAdjustment,
    LedgerNote,
    LedgerNoteKind,
    LedgerTotals,
    LedgerWeek,
    ProjectKind,
    ScheduleType,
    VacationEntitlement,
    VacationYear,
)
from beats.domain.models_organisations import (
    ActorKind,
    FrozenMonth,
    JoinDecision,
    MembershipEnd,
    MemberTotals,
    OrgAbsenceRequest,
    Organisation,
    OrganisationFields,
    OrgAssignment,
    OrgAuditEvent,
    OrgInvite,
    OrgJoinRequest,
    OrgMembership,
    OrgProject,
    OrgRole,
    OrgTeam,
    OrgTimesheet,
    RequestStatus,
    TimesheetAction,
    TimesheetEvent,
    TimesheetStatus,
    WeekStart,
)
from beats.domain.utils import TzNormalizedModel, normalize_tz


class LinkedIdentity(BaseModel):
    """An identity at an OpenID Connect provider that signs into this account.

    Keyed on (issuer, subject), never on a name or an email: `subject` is the
    provider's `sub`, stable and never reassigned within its issuer, while a
    name or an address can change hands. `name` and `email` are refreshed on
    each sign-in and are shown, not matched.
    """

    # The configured provider's id it arrived through (`OIDC_PROVIDERS`).
    provider: str
    issuer: str
    subject: str
    name: str | None = None
    email: str | None = None
    linked_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class SuspensionKind(StrEnum):
    """Why an account is suspended. The kind picks the refusal's wording
    (an erasure's names the day it ends), and a cancelled erasure lifts
    only its own kind — never a suspension for abuse."""

    ABUSE = "abuse"
    ERASURE = "erasure"
    OTHER = "other"


class User(TzNormalizedModel):
    """A registered user of the Beats system.

    A user may hold two independent ways in: passkeys registered against
    beats itself (`credentials` collection), and identities at OpenID
    Connect providers (`identities`, at most one per provider). Neither
    implies the other, and either alone is enough to sign in.
    """

    model_config = ConfigDict(populate_by_name=True)

    id: str | None = None
    email: str
    display_name: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    identities: list[LinkedIdentity] = Field(default_factory=list)

    # True when the account was created BY a sign-in through a provider
    # rather than linked to one afterwards. Such an account has no passkey
    # until its owner registers one, and keeps a provider-chosen display name
    # in step with the provider until then.
    sso_provisioned: bool = False

    # Suspension: refused everywhere the account can act, 403
    # ACCOUNT_SUSPENDED (docs/account-controls.md § Suspension, end to end).
    # `suspended_at` set is what "suspended" means; the reason is the
    # operator's own and is never shown to the person.
    suspended_at: datetime | None = None
    suspended_by: str | None = None
    suspended_kind: SuspensionKind | None = None
    suspended_reason: str | None = None

    # Sign out everywhere: a session whose sign-in (`auth_time`) is older
    # than this is refused. One field — no token list to share between
    # instances.
    sessions_valid_after: datetime | None = None

    # The day (UTC) a request last carried this account's credential. A
    # date, not a time: a session's times are the account's own business,
    # and a day is all the operator's "is this account in use?" needs.
    last_seen_on: date_type | None = None

    def identity_for(self, provider: str) -> LinkedIdentity | None:
        return next((i for i in self.identities if i.provider == provider), None)

    @property
    def suspended(self) -> bool:
        return self.suspended_at is not None


class AccountLimits(TzNormalizedModel):
    """One account's operator-set ceilings (docs/account-controls.md § Per-account limits).

    A document exists only when something is overridden; None on a field
    means the global setting. Keyed on `user_id` **deliberately**, unlike the
    operator's own collections, so erasure's sweep takes it with the rest of
    the account.
    """

    model_config = ConfigDict(populate_by_name=True)

    id: str | None = None
    user_id: str
    coach_monthly_budget_usd: float | None = None
    writes_per_minute_beats: int | None = None
    writes_per_minute_signals: int | None = None
    imports_per_hour: int | None = None
    # On the account, not the webhook: a per-webhook flag is undone by
    # deleting and re-creating the same URL.
    webhooks_disabled: bool = False
    set_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    # The operator's sub.
    set_by: str = ""


class Beat(TzNormalizedModel):
    """A time tracking entry (heartbeat) for a project.

    Represents a work session with a start time and optional end time.
    When end is None, the timer is considered active.
    """

    model_config = ConfigDict(populate_by_name=True)

    id: str | None = None
    project_id: str
    start: datetime = Field(default_factory=lambda: datetime.now(UTC))
    end: datetime | None = None
    note: str | None = None
    tags: list[str] = Field(default_factory=list)
    # Set when an organisation's admin or manager entered the time for the
    # member (docs/organisations.md, stage 3): who, so the entry says so on
    # the member's own timeline and in the record. Never set by the member's
    # own writes.
    entered_by: str | None = None
    # Set when the beat was tracked on an organisation's project: this beat is
    # that organisation's working-time record, and the stamp is what says so
    # on the document itself, so the question is answered per row — by the
    # organisation's read, which asks for its own stamp and nothing else, and
    # by an account's erasure, which keeps the stamped rows and nothing else
    # (docs/organisations.md). Written by the services that write a beat
    # against its project, and by connecting a project over its shared
    # history; moving a beat to a personal project clears it.
    organisation_id: str | None = None

    @computed_field
    @property
    def is_active(self) -> bool:
        """Check if this beat represents an active timer."""
        return self.end is None

    @computed_field
    @property
    def duration(self) -> timedelta:
        """Calculate the duration of this beat.

        For active beats, calculates time elapsed since start.
        For completed beats, calculates time between start and end.
        """
        end = self.end or datetime.now(UTC)
        # Ensure both datetimes are timezone-aware before subtraction
        start = normalize_tz(self.start)
        end = normalize_tz(end)
        return end - start

    @computed_field
    @property
    def day(self) -> date_type:
        """The date this beat started on."""
        return self.start.date()


def _same_instant(a: datetime | None, b: datetime | None) -> bool:
    """Equal to the millisecond, the precision a BSON date keeps: a client
    that sent an instant with microseconds reads it back truncated."""
    if a is None or b is None:
        return a is b

    def ms(dt: datetime) -> datetime:
        dt = normalize_tz(dt)
        return dt.replace(microsecond=dt.microsecond - dt.microsecond % 1000)

    return ms(a) == ms(b)


class ExpectedBeat(TzNormalizedModel):
    """A session as a client last saw it, sent with a write made against it.

    A client that queues writes while offline replays them later, when another
    device may have changed the same session in between. A write carrying this
    applies only while the stored session still matches, and is refused with a
    409 otherwise, so a replay never stops or rewrites what someone else
    changed meanwhile. `end` None is a running session."""

    project_id: str
    start: datetime
    end: datetime | None = None

    def matches(self, beat: Beat) -> bool:
        return (
            beat.project_id == self.project_id
            and _same_instant(beat.start, self.start)
            and _same_instant(beat.end, self.end)
        )


class ProjectOrganisation(BaseModel):
    """The organisation that owns a project, as its member sees it on the
    project: enough to mark it in a list, and the instant from which the
    member's hours on it are the organisation's (docs/organisations.md).
    `shared_from` is the member's own choice when they connected a project of
    theirs, and the moment of assignment otherwise."""

    id: str
    name: str
    logo_url: str | None = None
    shared_from: datetime
    # What the member kept back when they handed the project over: on a
    # project they connected, rows before this instant are theirs alone,
    # and nothing stamps them (rule 4, `organisation_stamp`). Null on a
    # project the organisation has owned all along, where the member had no
    # history to keep back and a back-dated entry is its record like any
    # other.
    #
    # Not `shared_from`, which a reassignment moves forward to the new
    # assignment's day: what was private at the connect stays private for
    # good. The day is kept beside the instant because an absence is dated
    # and not timed, and `private_before` is that day's local midnight in a
    # timezone nothing stores.
    private_before: datetime | None = None
    private_before_day: date_type | None = None
    # The employer writes the contract (docs/organisations.md, stage 3): the
    # member reads their week and balance as ever, but the contract, the
    # absences (which become requests) and the balance adjustments are the
    # organisation's to change, through its own routes.
    contract_managed: bool = False


# On an organisation's project, which fields are whose. The organisation's
# fields live on the project document and only an organisation admin writes
# them; the personal fields live on the member's assignment, so two members
# of one project each keep their own goal, their own local repo paths and —
# until an employer owns it (stage 3) — their own contract. The repository
# merges the two on read and splits them on write; `ProjectService` refuses a
# member's write that changes an organisation field (409 ORGANISATION_PROJECT).
ORGANISATION_FIELDS = frozenset(
    {"name", "description", "color", "archived", "kind", "github_repo", "category"}
)
PERSONAL_FIELDS = frozenset(
    {"weekly_goal", "goal_type", "goal_overrides", "autostart_repos", "contract"}
)


class Project(BaseModel):
    """A project to track time against.

    Projects are named entities that can accumulate time through beats.
    They can be archived when no longer active.
    """

    model_config = ConfigDict(populate_by_name=True)

    id: str | None = None
    name: str
    description: str | None = None
    color: str | None = None  # User-chosen hex color, e.g. "#5B9CF6"
    archived: bool = False
    weekly_goal: float | None = None  # Weekly goal in hours
    goal_type: GoalType = GoalType.TARGET  # target or cap
    goal_overrides: list[GoalOverride] = Field(default_factory=list)
    github_repo: str | None = None  # GitHub repo in "owner/repo" format
    category: str | None = None  # Activity category: coding, design, writing, etc.
    autostart_repos: list[str] = Field(default_factory=list)  # Local repo paths for auto-timer
    kind: ProjectKind = ProjectKind.SIDE_PROJECT
    contract: Contract | None = None  # only meaningful when kind == day_job
    # Who owns the project when it is not the person reading it. Read-only:
    # set by the repository when it merges an organisation's project with the
    # reader's assignment to it, never by a request. On such a project the
    # organisation's fields (`ORGANISATION_FIELDS`) are the organisation's to
    # write and the personal ones (`PERSONAL_FIELDS`) stay the member's.
    organisation: ProjectOrganisation | None = None

    def goal_term(self, week_monday: date_type) -> ContractTerm | None:
        """The contract term that governs this week's goal, or None when the personal goal does.

        The contract sets the goal on a day job whose term in force on the
        week's Monday is time-based; that term's `hours_per_week` is what the
        week owes, nominally. A term of 0 hours — the migration's reading of
        an override that said "no goal from here", or a custom term typed as
        0 — governs too, so the personal goal does not resurface under it,
        and `effective_goal` reports it as no goal at all. Before the first
        term, under an objective term, on a day job without a contract, and
        on every other kind, the personal goal applies. A term changing
        mid-week takes over the following Monday: the week is one figure, and
        its Monday decides.

        `ended_on` is not consulted, as `Contract.term_on` does not: the last
        term stays the goal after the contract ends, and the UI hides the
        personal goal on the same rule, so no goal reappears that the form
        cannot show. Archiving is what takes a finished job out of the readers.
        """
        if self.kind is not ProjectKind.DAY_JOB or self.contract is None:
            return None
        term = self.contract.term_on(week_monday)
        return term if term is not None and term.is_time_based else None

    def goal_overridden(self, week_monday: date_type) -> bool:
        """Whether a goal override resolves for the week — what lets the UI
        tell "override says no goal" (None, overridden) from "no override and
        no project default" (None, not overridden).

        False on a week the contract governs: `effective_goal` does not read
        the overrides there, so none is in effect however many are stored.
        """
        if self.goal_term(week_monday) is not None:
            return False
        return any(
            o.week_of == week_monday
            or (o.effective_from is not None and o.effective_from <= week_monday)
            for o in self.goal_overrides
        )

    def effective_goal(self, week_monday: date_type) -> tuple[float | None, GoalType]:
        """Resolve the effective goal for a given week (identified by its Monday).

        A contract that governs the week (`goal_term`) is the goal — its plain
        weekly hours, not adjusted for holidays or absences (the week route
        reports the adjusted expectation), always a target, and the personal
        goal and its overrides are not read at all. A governing term of 0
        hours is no goal (None), as the "no goal" override it was migrated
        from was, not a goal of nothing. Otherwise the precedence is one-off
        week_of > latest effective_from <= week_monday > project default.
        """
        term = self.goal_term(week_monday)
        if term is not None:
            return term.hours_per_week or None, GoalType.TARGET

        # 1. One-off override
        for o in self.goal_overrides:
            if o.week_of == week_monday:
                return o.weekly_goal, o.goal_type or self.goal_type

        # 2. Permanent override — the latest one that has taken effect by then
        in_effect = [
            o
            for o in self.goal_overrides
            if o.effective_from is not None and o.effective_from <= week_monday
        ]
        if in_effect:
            best = max(in_effect, key=lambda o: o.effective_from)
            return best.weekly_goal, best.goal_type or self.goal_type

        # 3. Default
        return self.weekly_goal, self.goal_type


class ProjectBreakdownEntry(BaseModel):
    """One project's share of a week, as a digest reports it.

    Typed rather than a bare dict because it crosses the wire: it is what
    the UI's digest list renders, and an untyped `list[dict]` publishes an
    OpenAPI `array of object` with no properties, which leaves every client
    casting the rows back into a shape by hand.
    """

    project_id: str
    name: str
    hours: float


class WeeklyDigest(TzNormalizedModel):
    """A generated weekly summary with insights and productivity score."""

    model_config = ConfigDict(populate_by_name=True)

    id: str | None = None
    week_of: date_type  # Monday of the week
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    total_hours: float
    session_count: int
    active_days: int
    top_project_id: str | None = None
    top_project_name: str | None = None
    top_project_hours: float = 0
    vs_last_week_pct: float | None = None
    longest_day: str | None = None  # Day name, e.g. "Wednesday"
    longest_day_hours: float = 0
    best_streak: int = 0
    observation: str = ""
    project_breakdown: list[ProjectBreakdownEntry] = Field(default_factory=list)
    productivity_score: int = 0


class InsightCard(BaseModel):
    """A single detected pattern or insight."""

    id: str  # uuid for dismiss tracking
    type: str  # day_pattern, time_pattern, stale_project, session_trend, etc.
    title: str
    body: str
    data: dict = Field(default_factory=dict)
    priority: int = 3  # 1-5, higher = more important


class UserInsights(TzNormalizedModel):
    """Cached pattern detection results for a user."""

    model_config = ConfigDict(populate_by_name=True)

    id: str | None = None
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    insights: list[InsightCard] = Field(default_factory=list)
    dismissed_ids: list[str] = Field(default_factory=list)


class WeeklyPlan(BaseModel):
    """A weekly time budget plan with per-project allocations."""

    model_config = ConfigDict(populate_by_name=True)

    id: str | None = None
    week_of: date_type  # Monday of the week
    budgets: list[dict] = Field(default_factory=list)  # [{project_id, planned_hours}]
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class PairingCode(BaseModel):
    """A short-lived pairing code for daemon-to-API authentication.

    The raw code is shown to the user once; only its SHA-256 hash is stored.
    Expires after 5 minutes via MongoDB TTL index on expires_at.
    """

    model_config = ConfigDict(populate_by_name=True)

    id: str | None = None
    user_id: str
    code_hash: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime = Field(default_factory=lambda: datetime.now(UTC) + timedelta(minutes=5))


class SSOFlow(BaseModel):
    """A sign-in through a provider, between leaving for it and coming back.

    Held server-side, so nothing the browser carries back can change what is
    checked: the nonce the ID token must repeat, the PKCE verifier that
    proves the code was asked for here, and — for a link — whose account the
    identity goes on. Keyed by a hash of the `state` sent through the
    provider, taken exactly once, and expired by a TTL index after ten minutes.
    """

    state_hash: str
    provider: str
    nonce: str
    code_verifier: str
    intent: Literal["sign_in", "link"]
    # Set for a link: the account that asked, which must also finish it.
    user_id: str | None = None
    expires_at: datetime = Field(default_factory=lambda: datetime.now(UTC) + timedelta(minutes=10))


class DeviceRegistration(BaseModel):
    """A registered daemon device paired to a user account.

    Created when a daemon exchanges a pairing code for a long-lived device token.
    The device token is a JWT with type="device" scoped to signal-writing endpoints.
    """

    model_config = ConfigDict(populate_by_name=True)

    id: str | None = None
    user_id: str
    device_id: str
    device_name: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_seen: datetime | None = None
    revoked: bool = False


class GitHubIntegration(BaseModel):
    """A connected GitHub OAuth integration (per-user)."""

    model_config = ConfigDict(populate_by_name=True)

    id: str | None = None
    access_token: str = ""
    github_username: str = ""
    enabled: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class CalendarIntegration(TzNormalizedModel):
    """A connected Google Calendar OAuth integration."""

    model_config = ConfigDict(populate_by_name=True)

    id: str | None = None
    provider: str = "google"
    access_token: str = ""
    refresh_token: str = ""
    token_expiry: datetime | None = None
    calendar_ids: list[str] = Field(default_factory=lambda: ["primary"])
    enabled: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class FitbitIntegration(BaseModel):
    """A connected Fitbit OAuth integration (per-user)."""

    model_config = ConfigDict(populate_by_name=True)

    id: str | None = None
    access_token: str = ""
    refresh_token: str = ""
    token_expiry: datetime | None = None
    fitbit_user_id: str = ""
    enabled: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class OuraIntegration(BaseModel):
    """A connected Oura integration using a personal access token."""

    model_config = ConfigDict(populate_by_name=True)

    id: str | None = None
    access_token: str = ""
    oura_user_id: str = ""
    enabled: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class BiometricDay(TzNormalizedModel):
    """A single day of biometric data from any source.

    Keyed by (user_id, date, source) for upsert. Multiple sources per day
    are allowed (e.g. HealthKit + Oura). Priority: HealthKit > Oura > Fitbit.
    """

    model_config = ConfigDict(populate_by_name=True)

    id: str | None = None
    date: date_type = Field(default_factory=lambda: datetime.now(UTC).date())
    source: str = ""  # healthkit, health_connect, fitbit, oura
    sleep_minutes: int | None = None
    sleep_efficiency: float | None = None  # 0.0–1.0
    hrv_ms: float | None = None
    resting_hr_bpm: int | None = None
    steps: int | None = None
    readiness_score: int | None = None  # Oura 0–100
    workouts: list[dict] = Field(default_factory=list)  # [{kind, minutes, avg_hr}]
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class PendingSuggestion(TzNormalizedModel):
    """An auto-timer suggestion the API has surfaced but the user hasn't
    yet acted on.

    Created on the API side whenever the daemon's POST to
    `/api/signals/suggest-timer` returns `should_suggest=True`. The
    companion's notification poller pulls these via
    `GET /api/signals/pending-suggestions`, fires
    `notifyAutoTimerSuggestion`, and dedupes by id. There's no separate
    "ack" — staleness is handled by the read endpoint's `since` window.
    """

    model_config = ConfigDict(populate_by_name=True)

    id: str | None = None
    project_id: str
    project_name: str
    suggested_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    # The categorical signal that triggered the suggestion. Stored for
    # debugging / future analytics — the companion notification body
    # doesn't reference it today.
    dominant_category: str = ""
    # When the match came from an editor-repo → autostart_repos hit
    # (rather than the looser category fallback), we keep the repo path
    # so a future "yes" tap can confirm "start tracking on this repo".
    editor_repo: str | None = None


class FlowWindow(TzNormalizedModel):
    """A computed flow-state window from the daemon's signal collector.

    Represents a 1-minute window of aggregated desktop activity. The daemon
    computes the flow score locally and sends only the aggregate to the API.
    """

    model_config = ConfigDict(populate_by_name=True)

    id: str | None = None
    device_id: str = ""
    window_start: datetime = Field(default_factory=lambda: datetime.now(UTC))
    window_end: datetime = Field(default_factory=lambda: datetime.now(UTC))
    flow_score: float = 0.0
    cadence_score: float = 0.0
    coherence_score: float = 0.0
    category_fit_score: float = 0.0
    idle_fraction: float = 0.0
    dominant_bundle_id: str = ""
    dominant_category: str = ""
    context_switches: int = 0
    active_project_id: str | None = None
    # Editor context — populated by the daemon from the most recent fresh
    # heartbeat received from an editor extension (today: VS Code via
    # `daemon/internal/editor/listener.go`). All three default to None when
    # no editor was active during the window.
    editor_repo: str | None = None
    editor_branch: str | None = None
    editor_language: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class SignalSummary(TzNormalizedModel):
    """Hourly aggregation of signal categories for the privacy dashboard.

    Stores per-category sample counts without any raw signal data.
    Keyed by (user_id, device_id, hour) for upsert.
    """

    model_config = ConfigDict(populate_by_name=True)

    id: str | None = None
    device_id: str = ""
    hour: datetime = Field(default_factory=lambda: datetime.now(UTC))
    categories: dict[str, int] = Field(default_factory=dict)
    total_samples: int = 0
    idle_samples: int = 0
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Webhook(TzNormalizedModel):
    """A registered webhook URL that receives timer events.

    Events: timer.start, timer.stop — both dispatched from the timer routes
    in `api/routers/projects.py`. `events` is not validated against that set,
    so a row can name an event nothing emits; it simply never fires.
    """

    model_config = ConfigDict(populate_by_name=True)

    id: str | None = None
    url: str
    events: list[str] = Field(default_factory=lambda: ["timer.start", "timer.stop"])
    active: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


# The facade: `models.py` is the one name every import site uses for the
# domain vocabulary, and `__all__` is what makes the three sections above
# part of this module's surface rather than unused imports.
__all__ = [
    "BILLING_BUDGET_HOURS_MAX",
    "BILLING_BUDGET_MINOR_MAX",
    "ORGANISATION_FIELDS",
    "PERSONAL_FIELDS",
    "RATE_MINOR_MAX",
    "REPORT_RANGE_MAX_DAYS",
    "WORKDAYS_PER_WEEK",
    "Absence",
    "AbsenceType",
    "AccountLimits",
    "ActorKind",
    "AdjustmentKind",
    "BalanceAdjustment",
    "BalanceAdjustmentFields",
    "Beat",
    "BillableOverride",
    "BillingBudget",
    "BillingBudgetFields",
    "BillingBudgetPeriod",
    "BillingBudgetScope",
    "BillingBudgetUnit",
    "BillingTerm",
    "BiometricDay",
    "CalendarIntegration",
    "CarryOver",
    "Client",
    "ClientFields",
    "CompanyHoliday",
    "Contract",
    "ContractDay",
    "ContractTerm",
    "ContractWeek",
    "DayAbsence",
    "DeviceRegistration",
    "ExpectedBeat",
    "FitbitIntegration",
    "FlowWindow",
    "FrozenMonth",
    "GitHubIntegration",
    "GoalOverride",
    "GoalType",
    "InsightCard",
    "JoinDecision",
    "Ledger",
    "LedgerAdjustment",
    "LedgerNote",
    "LedgerNoteKind",
    "LedgerTotals",
    "LedgerWeek",
    "LinkedIdentity",
    "MemberTotals",
    "MembershipEnd",
    "OrgAbsenceRequest",
    "OrgAssignment",
    "OrgAuditEvent",
    "OrgInvite",
    "OrgJoinRequest",
    "OrgMembership",
    "OrgProject",
    "OrgRole",
    "OrgTeam",
    "OrgTimesheet",
    "Organisation",
    "OrganisationFields",
    "OuraIntegration",
    "PairingCode",
    "PendingSuggestion",
    "Project",
    "ProjectBilling",
    "ProjectBillingFields",
    "ProjectBreakdownEntry",
    "ProjectKind",
    "ProjectOrganisation",
    "RateTerm",
    "ReportLink",
    "ReportLinkFields",
    "RequestStatus",
    "SSOFlow",
    "ScheduleType",
    "SignalSummary",
    "SuspensionKind",
    "TimesheetAction",
    "TimesheetEvent",
    "TimesheetStatus",
    "User",
    "UserInsights",
    "VacationEntitlement",
    "VacationYear",
    "Webhook",
    "WeekStart",
    "WeeklyDigest",
    "WeeklyPlan",
]
