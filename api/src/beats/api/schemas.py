"""API request and response schemas."""

from datetime import UTC, datetime
from datetime import date as date_type

from pydantic import BaseModel, Field

from beats.domain.models import GoalType

# Request schemas


class RecordTimeRequest(BaseModel):
    """Request body for recording time (start/stop timer)."""

    time: datetime = Field(default_factory=lambda: datetime.now(UTC))


class CreateProjectRequest(BaseModel):
    """Request body for creating a project."""

    name: str
    description: str | None = None
    estimation: str | None = None
    color: str | None = None
    weekly_goal: float | None = None  # Weekly goal in hours


class UpdateProjectRequest(BaseModel):
    """Request body for updating a project."""

    id: str
    name: str
    description: str | None = None
    estimation: str | None = None
    color: str | None = None
    archived: bool = False
    weekly_goal: float | None = None  # Weekly goal in hours
    goal_type: str = "target"  # "target" or "cap"


class GoalOverrideRequest(BaseModel):
    """Request body for a goal override."""

    week_of: date_type | None = None
    effective_from: date_type | None = None
    weekly_goal: float
    goal_type: GoalType | None = None
    note: str | None = None


class CreateBeatRequest(BaseModel):
    """Request body for creating a beat."""

    project_id: str
    start: datetime = Field(default_factory=lambda: datetime.now(UTC))
    end: datetime | None = None
    note: str | None = None
    tags: list[str] = Field(default_factory=list)


class UpdateBeatRequest(BaseModel):
    """Request body for updating a beat."""

    id: str
    project_id: str
    start: datetime
    end: datetime | None = None
    note: str | None = None
    tags: list[str] = Field(default_factory=list)


# Response schemas


class BeatResponse(BaseModel):
    """Response schema for a beat."""

    id: str
    project_id: str
    start: datetime
    end: datetime | None = None
    duration: str
    is_active: bool
    note: str | None = None
    tags: list[str] = Field(default_factory=list)


class ProjectResponse(BaseModel):
    """Response schema for a project."""

    id: str
    name: str
    description: str | None = None
    estimation: str | None = None
    archived: bool = False
    weekly_goal: float | None = None  # Weekly goal in hours


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


class WeekBreakdownResponse(BaseModel):
    """Response schema for weekly breakdown."""

    Monday: str | list | None = None
    Tuesday: str | list | None = None
    Wednesday: str | list | None = None
    Thursday: str | list | None = None
    Friday: str | list | None = None
    Saturday: str | list | None = None
    Sunday: str | list | None = None
    total_hours: float
    effective_goal: float | None = None
    effective_goal_type: str | None = None


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


# Intention schemas


class CreateIntentionRequest(BaseModel):
    """Request body for creating a daily intention."""

    project_id: str
    date: date_type | None = None
    planned_minutes: int = 60


class UpdateIntentionRequest(BaseModel):
    """Request body for updating an intention."""

    completed: bool | None = None
    planned_minutes: int | None = None


class IntentionResponse(BaseModel):
    """Response schema for an intention."""

    id: str
    project_id: str
    date: date_type
    planned_minutes: int
    completed: bool


# DailyNote schemas


class UpsertDailyNoteRequest(BaseModel):
    """Request body for creating or updating a daily note."""

    date: date_type | None = None
    note: str = ""
    mood: int | None = None  # 1-5


class DailyNoteResponse(BaseModel):
    """Response schema for a daily note."""

    id: str
    date: date_type
    note: str
    mood: int | None = None
    created_at: datetime


# Intelligence schemas


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
    project_breakdown: list[dict] = Field(default_factory=list)
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


class MoodCorrelationResponse(BaseModel):
    """Response schema for mood-productivity correlation."""

    mood_trend: list[dict]
    correlation: dict
    high_mood_avg_hours: float
    low_mood_avg_hours: float
    high_mood_avg_sessions: float
    low_mood_avg_sessions: float


class EstimationAccuracyResponse(BaseModel):
    """Response schema for estimation accuracy per project."""

    project_id: str
    project_name: str
    avg_planned_min: float
    avg_actual_min: float
    accuracy_pct: float
    bias: str


class ProjectHealthResponse(BaseModel):
    """Response schema for project health metrics."""

    project_id: str
    project_name: str
    days_since_last: int | None = None
    weekly_goal_trend: list[float] = Field(default_factory=list)
    avg_session_length_trend: list[float] = Field(default_factory=list)
    alert: str | None = None
