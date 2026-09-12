"""Domain models - pure business entities with no external dependencies."""

from datetime import UTC, datetime, timedelta
from datetime import date as date_type
from enum import StrEnum
from itertools import pairwise

from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator

from beats.domain.utils import TzNormalizedModel, normalize_tz


class User(TzNormalizedModel):
    """A registered user of the Beats system.

    A user may hold two independent ways in: passkeys registered against
    beats itself (`credentials` collection), and at most one linked
    `home.space` identity (the `sso_*` fields). Neither implies the other,
    and either alone is enough to sign in.
    """

    model_config = ConfigDict(populate_by_name=True)

    id: str | None = None
    email: str
    display_name: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    # --- Linked home.space identity -----------------------------------
    #
    # Keyed on (sso_issuer, sso_subject), never on a name or an email.
    # `sso_subject` is a did:key derived from the device's public key:
    # stable, unique, and not reassignable. `sso_holder_name` is the
    # enrollment label ("Primary Laptop") and is refreshed from the
    # credential on each login, since the issuer owns it.
    sso_issuer: str | None = None
    sso_subject: str | None = None
    sso_holder_name: str | None = None
    sso_roles: list[str] = Field(default_factory=list)
    sso_linked_at: datetime | None = None

    # True when the account was created BY an SSO login rather than
    # linked to one afterwards. Purely informational — it is what lets
    # the UI explain why an account has no passkey yet, and what makes
    # "unlink" refuse on an account that would have no way back in.
    sso_provisioned: bool = False

    @property
    def has_sso_link(self) -> bool:
        return bool(self.sso_subject)


class GoalType(StrEnum):
    """Type of weekly goal: target to reach or cap to stay under."""

    TARGET = "target"
    CAP = "cap"


class GoalOverride(BaseModel):
    """A per-week or date-range override of a project's weekly goal.

    Exactly one of week_of or effective_from must be set:
    - week_of: one-off override for a single week (identified by its Monday)
    - effective_from: permanent override from a date forward (must be a Monday)

    weekly_goal=None means "no goal applies for this window" (e.g. a holiday
    week, or the user giving up on a target from a given Monday forward).
    """

    week_of: date_type | None = None
    effective_from: date_type | None = None
    weekly_goal: float | None = None
    goal_type: GoalType | None = None  # None = inherit project default
    note: str | None = None

    @model_validator(mode="after")
    def validate_override_type(self) -> GoalOverride:
        has_week = self.week_of is not None
        has_from = self.effective_from is not None
        if has_week == has_from:
            msg = "Exactly one of week_of or effective_from must be set"
            raise ValueError(msg)
        if self.week_of is not None and self.week_of.weekday() != 0:
            msg = "week_of must be a Monday"
            raise ValueError(msg)
        if self.effective_from is not None and self.effective_from.weekday() != 0:
            msg = "effective_from must be a Monday"
            raise ValueError(msg)
        if self.weekly_goal is not None and self.weekly_goal <= 0:
            msg = "weekly_goal must be positive"
            raise ValueError(msg)
        return self


class ProjectKind(StrEnum):
    """What a project is to the person tracking it. A contract is read only on a day job."""

    DAY_JOB = "day_job"
    FREELANCE = "freelance"
    SIDE_PROJECT = "side_project"


class ScheduleType(StrEnum):
    """How a contract term states the hours it owes."""

    FULL_TIME = "full_time"  # percentage fixed at 1.0
    PART_TIME = "part_time"  # percentage < 1.0
    CUSTOM = "custom"  # weekly_hours given directly
    OBJECTIVE = "objective"  # no expectation, no balance


# A week owes hours_per_week; a day off owes a fifth of it less. There is no
# working pattern (decision 3): we never ask which weekdays are worked.
WORKDAYS_PER_WEEK = 5


class ContractTerm(BaseModel):
    """One stretch of a contract, from `effective_from` until the next term takes over.

    A time-based term (full_time / part_time) owes `full_time_hours × percentage`
    a week — a percentage needs its basis, since 80% of 42 is not 80% of 40. A
    custom term states `weekly_hours` outright. An objective term owes nothing
    and carries no numbers at all. Hence the rules:

    - `percentage` lies in (0, 1]; a full_time term is 1 — filled in when
      omitted, rejected when it says otherwise — and a part_time term is
      less than 1, or it would be full-time under another name.
    - `weekly_hours` is required for custom and must be left out for the
      time-based types, where it is derived (`hours_per_week`).
    - `full_time_hours` and `percentage` belong to the time-based types only.

    `effective_from` may be any day of the week: a contract that changes on a
    Wednesday charges Monday and Tuesday at the old rate.
    """

    effective_from: date_type
    schedule_type: ScheduleType
    # Finite only: a NaN here would ride through hours_per_day into every
    # expectation and the balance, and compare as neither over nor under.
    full_time_hours: float | None = Field(default=None, allow_inf_nan=False)
    percentage: float | None = Field(default=None, allow_inf_nan=False)
    weekly_hours: float | None = Field(default=None, allow_inf_nan=False)
    note: str | None = None

    @model_validator(mode="after")
    def validate_hours_for_schedule(self) -> ContractTerm:
        if self.full_time_hours is not None and self.full_time_hours <= 0:
            msg = "full_time_hours must be positive"
            raise ValueError(msg)
        if self.percentage is not None and not 0 < self.percentage <= 1:
            msg = "percentage must be in (0, 1]"
            raise ValueError(msg)
        if self.weekly_hours is not None and self.weekly_hours < 0:
            msg = "weekly_hours must not be negative"
            raise ValueError(msg)

        schedule = self.schedule_type
        if schedule is ScheduleType.OBJECTIVE:
            if (self.full_time_hours, self.percentage, self.weekly_hours) != (None, None, None):
                msg = "an objective term carries no hours"
                raise ValueError(msg)
        elif schedule is ScheduleType.CUSTOM:
            if self.weekly_hours is None:
                msg = "a custom term requires weekly_hours"
                raise ValueError(msg)
            if self.full_time_hours is not None or self.percentage is not None:
                msg = "a custom term states weekly_hours directly, not a basis and percentage"
                raise ValueError(msg)
        else:
            if self.full_time_hours is None:
                msg = f"a {schedule} term requires full_time_hours"
                raise ValueError(msg)
            if self.weekly_hours is not None:
                msg = f"weekly_hours is derived for a {schedule} term"
                raise ValueError(msg)
            if schedule is ScheduleType.FULL_TIME:
                if self.percentage is None:
                    self.percentage = 1.0
                elif self.percentage != 1:
                    msg = "a full_time term is 100%; use part_time for less"
                    raise ValueError(msg)
            elif self.percentage is None:
                msg = "a part_time term requires percentage"
                raise ValueError(msg)
            elif self.percentage == 1:
                msg = "a part_time term is less than 100%; use full_time for a full week"
                raise ValueError(msg)
        return self

    @property
    def hours_per_week(self) -> float | None:
        """Hours the week owes under this term; None for an objective term."""
        if self.schedule_type is ScheduleType.CUSTOM:
            return self.weekly_hours
        if self.full_time_hours is None or self.percentage is None:
            return None  # objective; the validator leaves no other way here
        return self.full_time_hours * self.percentage

    @property
    def hours_per_day(self) -> float | None:
        """What one weekday owes, and what a day off costs."""
        weekly = self.hours_per_week
        return None if weekly is None else weekly / WORKDAYS_PER_WEEK

    @property
    def is_time_based(self) -> bool:
        """Whether the term owes hours at all — false only for an objective term."""
        return self.hours_per_week is not None


class Contract(BaseModel):
    """A day job's terms as they changed over time, plus what frames them.

    `terms` is the history — part-time, then 80%, then full-time — kept in
    order of `effective_from` with no two starting on the same day, because
    the day decides which term applies. The region names the employer's
    public holidays: `holiday_subdivision` only means something inside a
    `holiday_country`. Both must be codes the holidays library knows, but
    that is checked where a contract is written (`ProjectService`), not
    here: this model is re-validated on every read, and the set of codes the
    library knows moves with its version — a code it stops recognising must
    make one contract un-editable, not every project of the user unreadable.
    `opening_balance_hours` is what was banked (or owed) before Beats started
    counting; `ended_on` freezes the balance from that day on.
    """

    terms: list[ContractTerm]
    holiday_country: str | None = None  # ISO 3166-1 alpha-2, e.g. "CH"
    holiday_subdivision: str | None = None  # ISO 3166-2 part, e.g. "ZH"
    opening_balance_hours: float = Field(default=0, allow_inf_nan=False)
    ended_on: date_type | None = None

    @model_validator(mode="after")
    def validate_terms(self) -> Contract:
        if not self.terms:
            msg = "a contract needs at least one term"
            raise ValueError(msg)
        for earlier, later in pairwise(self.terms):
            if later.effective_from <= earlier.effective_from:
                msg = "terms must be in ascending order of effective_from, with no two on one day"
                raise ValueError(msg)
        if self.ended_on is not None and self.ended_on < self.terms[0].effective_from:
            msg = "ended_on is before the first term starts"
            raise ValueError(msg)
        if self.holiday_subdivision is not None and self.holiday_country is None:
            msg = "holiday_subdivision needs a holiday_country"
            raise ValueError(msg)
        return self

    @property
    def starts_on(self) -> date_type:
        """The first day anything is expected: the first term's `effective_from`."""
        return self.terms[0].effective_from

    def term_on(self, day: date_type) -> ContractTerm | None:
        """The term in force on `day`: the latest whose `effective_from` is not after it.

        None before the first term. `ended_on` is not consulted — a term is
        still the term that applied, it just stops owing anything.
        """
        current: ContractTerm | None = None
        for term in self.terms:  # the validator keeps these ascending
            if term.effective_from > day:
                break
            current = term
        return current


class AbsenceType(StrEnum):
    """Why a day was not worked. For the record and the calendar's colour only —
    the arithmetic treats all three the same."""

    VACATION = "vacation"
    SICK = "sick"
    OTHER = "other"


class Absence(BaseModel):
    """A day, or half of one, the contract does not expect work on.

    One per (project, date): a second absence on the same day replaces the
    first rather than stacking. Weekends and holidays already cost nothing,
    so an absence recorded on one changes nothing.
    """

    model_config = ConfigDict(populate_by_name=True)

    id: str | None = None
    project_id: str
    date: date_type
    half_day: bool = False
    type: AbsenceType
    note: str | None = None


class DayAbsence(BaseModel):
    """An absence as one day of the week report shows it — the record without
    its keys, which the day already supplies."""

    type: AbsenceType
    half_day: bool
    note: str | None = None


class ContractDay(BaseModel):
    """One day of a contract week: what it owed, what was worked, and why it
    owed less if it did."""

    date: date_type
    expected: float
    worked: float
    holiday: str | None = None  # the holiday's name
    absence: DayAbsence | None = None


class ContractWeek(BaseModel):
    """A day job's week against its contract, plus the running balance.

    Typed because it crosses the wire (see `ProjectBreakdownEntry`).
    `expected` and `remaining` are None when the contract owes nothing by
    nature that week — no weekday has a time-based term in force — as
    distinct from 0, which is a week the contract owed nothing by
    circumstance (every weekday a holiday, or after `ended_on`). `balance`
    is None on the same rule for today. `remaining` goes negative once the
    week is over its expectation.
    """

    week_of: date_type
    expected: float | None
    worked: float
    remaining: float | None
    balance: float | None
    days: list[ContractDay]


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
