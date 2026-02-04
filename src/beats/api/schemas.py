"""API request and response schemas."""

from datetime import UTC, datetime

from pydantic import BaseModel, Field

from beats.domain.models import Beat, Project

# Request schemas


class RecordTimeRequest(BaseModel):
    """Request body for recording time (start/stop timer)."""

    time: datetime = Field(default_factory=lambda: datetime.now(UTC))


class CreateProjectRequest(BaseModel):
    """Request body for creating a project."""

    name: str
    description: str | None = None
    estimation: str | None = None


class UpdateProjectRequest(BaseModel):
    """Request body for updating a project."""

    id: str
    name: str
    description: str | None = None
    estimation: str | None = None
    archived: bool = False


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

    @classmethod
    def from_domain(cls, beat: Beat) -> BeatResponse:
        """Create response from domain model."""
        return cls(
            id=beat.id or "",
            project_id=beat.project_id,
            start=beat.start,
            end=beat.end,
            duration=str(beat.duration),
            is_active=beat.is_active,
        )


class ProjectResponse(BaseModel):
    """Response schema for a project."""

    id: str
    name: str
    description: str | None = None
    estimation: str | None = None
    archived: bool = False

    @classmethod
    def from_domain(cls, project: Project) -> ProjectResponse:
        """Create response from domain model."""
        return cls(
            id=project.id or "",
            name=project.name,
            description=project.description,
            estimation=project.estimation,
            archived=project.archived,
        )


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
