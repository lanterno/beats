"""Domain models - pure business entities with no external dependencies."""

from datetime import UTC, datetime, timedelta
from datetime import date as date_type
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator

from beats.domain.utils import TzNormalizedModel, normalize_tz


class User(TzNormalizedModel):
    """A registered user of the Beats system."""

    model_config = ConfigDict(populate_by_name=True)

    id: str | None = None
    email: str
    display_name: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class GoalType(StrEnum):
    """Type of weekly goal: target to reach or cap to stay under."""

    TARGET = "target"
    CAP = "cap"


class GoalOverride(BaseModel):
    """A per-week or date-range override of a project's weekly goal.

    Exactly one of week_of or effective_from must be set:
    - week_of: one-off override for a single week (identified by its Monday)
    - effective_from: permanent override from a date forward (must be a Monday)
    """

    week_of: date_type | None = None
    effective_from: date_type | None = None
    weekly_goal: float
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
        if self.weekly_goal <= 0:
            msg = "weekly_goal must be positive"
            raise ValueError(msg)
        return self


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
    estimation: str | None = None
    color: str | None = None  # User-chosen hex color, e.g. "#5B9CF6"
    archived: bool = False
    weekly_goal: float | None = None  # Weekly goal in hours
    goal_type: GoalType = GoalType.TARGET  # target or cap
    goal_overrides: list[GoalOverride] = Field(default_factory=list)
    github_repo: str | None = None  # GitHub repo in "owner/repo" format
    category: str | None = None  # Activity category: coding, design, writing, etc.
    autostart_repos: list[str] = Field(default_factory=list)  # Local repo paths for auto-timer

    def effective_goal(self, week_monday: date_type) -> tuple[float | None, GoalType]:
        """Resolve the effective goal for a given week (identified by its Monday).

        Precedence: one-off week_of > latest effective_from <= week_monday > project default.
        """
        # 1. One-off override
        for o in self.goal_overrides:
            if o.week_of == week_monday:
                return o.weekly_goal, o.goal_type or self.goal_type

        # 2. Permanent override (latest effective_from <= week_monday)
        best: GoalOverride | None = None
        for o in self.goal_overrides:
            if o.effective_from is not None and o.effective_from <= week_monday:
                if best is None or best.effective_from is None:
                    best = o
                elif o.effective_from > best.effective_from:
                    best = o
        if best is not None:
            return best.weekly_goal, best.goal_type or self.goal_type

        # 3. Default
        return self.weekly_goal, self.goal_type


class Intention(BaseModel):
    """A daily time-boxed intention for a project.

    Users set 1-3 intentions each morning: "2h on API refactor."
    Auto-checked when tracked time exceeds the planned duration.
    """

    model_config = ConfigDict(populate_by_name=True)

    id: str | None = None
    project_id: str
    date: date_type = Field(default_factory=lambda: datetime.now(UTC).date())
    planned_minutes: int = 60
    completed: bool = False


class DailyNote(TzNormalizedModel):
    """An end-of-day reflection with optional mood rating.

    Captures how the day went with a brief text note and mood score.
    """

    model_config = ConfigDict(populate_by_name=True)

    id: str | None = None
    date: date_type = Field(default_factory=lambda: datetime.now(UTC).date())
    note: str = ""
    mood: int | None = None  # 1-5 scale
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


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
    project_breakdown: list[dict] = Field(default_factory=list)
    productivity_score: int = 0


class InsightCard(BaseModel):
    """A single detected pattern or insight."""

    id: str  # uuid for dismiss tracking
    type: str  # day_pattern, time_pattern, stale_project, mood_correlation, etc.
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


class RecurringIntention(BaseModel):
    """A template for auto-creating daily intentions."""

    model_config = ConfigDict(populate_by_name=True)

    id: str | None = None
    project_id: str
    planned_minutes: int = 60
    days_of_week: list[int] = Field(default_factory=lambda: [0, 1, 2, 3, 4])  # Mon-Fri
    enabled: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class WeeklyReview(BaseModel):
    """A weekly reflection stored alongside the digest."""

    model_config = ConfigDict(populate_by_name=True)

    id: str | None = None
    week_of: date_type  # Monday of the week
    went_well: str = ""
    didnt_go_well: str = ""
    to_change: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class AutoStartRule(BaseModel):
    """A rule for auto-starting the timer based on webhooks or schedules."""

    model_config = ConfigDict(populate_by_name=True)

    id: str | None = None
    type: str  # "webhook_trigger" or "schedule"
    project_id: str
    config: dict = Field(default_factory=dict)  # repo name for webhook, cron for schedule
    enabled: bool = True
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

    Events: timer.start, timer.stop, daily.summary
    """

    model_config = ConfigDict(populate_by_name=True)

    id: str | None = None
    url: str
    events: list[str] = Field(default_factory=lambda: ["timer.start", "timer.stop"])
    active: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
