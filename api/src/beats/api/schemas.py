"""API request and response schemas."""

from datetime import UTC, date, datetime

from pydantic import BaseModel, Field

# Request schemas


class RecordTimeRequest(BaseModel):
    """Request body for recording time (start/stop timer)."""

    time: datetime = Field(default_factory=lambda: datetime.now(UTC))


class CreateProjectRequest(BaseModel):
    """Request body for creating a project."""

    name: str
    description: str | None = None
    estimation: str | None = None
    weekly_goal: float | None = None  # Weekly goal in hours


class UpdateProjectRequest(BaseModel):
    """Request body for updating a project."""

    id: str
    name: str
    description: str | None = None
    estimation: str | None = None
    archived: bool = False
    weekly_goal: float | None = None  # Weekly goal in hours
    goal_type: str = "target"  # "target" or "cap"


class CreateBeatRequest(BaseModel):
    """Request body for creating a beat."""

    project_id: str
    start: datetime = Field(default_factory=lambda: datetime.now(UTC))
    end: datetime | None = None


class UpdateBeatRequest(BaseModel):
    """Request body for updating a beat."""

    id: str
    project_id: str
    start: datetime
    end: datetime | None = None


# Response schemas


class BeatResponse(BaseModel):
    """Response schema for a beat."""

    id: str
    project_id: str
    start: datetime
    end: datetime | None = None
    duration: str
    is_active: bool


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
    date: date | None = None
    planned_minutes: int = 60


class UpdateIntentionRequest(BaseModel):
    """Request body for updating an intention."""

    completed: bool | None = None
    planned_minutes: int | None = None


class IntentionResponse(BaseModel):
    """Response schema for an intention."""

    id: str
    project_id: str
    date: date
    planned_minutes: int
    completed: bool


# DailyNote schemas


class UpsertDailyNoteRequest(BaseModel):
    """Request body for creating or updating a daily note."""

    date: date | None = None
    note: str = ""
    mood: int | None = None  # 1-5


class DailyNoteResponse(BaseModel):
    """Response schema for a daily note."""

    id: str
    date: date
    note: str
    mood: int | None = None
    created_at: datetime
