"""API request and response schemas."""

from datetime import UTC, datetime

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
