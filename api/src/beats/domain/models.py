"""Domain models - pure business entities with no external dependencies."""

from datetime import UTC, date, datetime, timedelta
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, computed_field

from beats.domain.utils import normalize_tz


class GoalType(str, Enum):
    """Type of weekly goal: target to reach or cap to stay under."""

    TARGET = "target"
    CAP = "cap"


class Beat(BaseModel):
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
    def day(self) -> date:
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


class Intention(BaseModel):
    """A daily time-boxed intention for a project.

    Users set 1-3 intentions each morning: "2h on API refactor."
    Auto-checked when tracked time exceeds the planned duration.
    """

    model_config = ConfigDict(populate_by_name=True)

    id: str | None = None
    project_id: str
    date: date = Field(default_factory=lambda: datetime.now(UTC).date())
    planned_minutes: int = 60
    completed: bool = False


class DailyNote(BaseModel):
    """An end-of-day reflection with optional mood rating.

    Captures how the day went with a brief text note and mood score.
    """

    model_config = ConfigDict(populate_by_name=True)

    id: str | None = None
    date: date = Field(default_factory=lambda: datetime.now(UTC).date())
    note: str = ""
    mood: int | None = None  # 1-5 scale
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Webhook(BaseModel):
    """A registered webhook URL that receives timer events.

    Events: timer.start, timer.stop
    """

    model_config = ConfigDict(populate_by_name=True)

    id: str | None = None
    url: str
    events: list[str] = Field(default_factory=lambda: ["timer.start", "timer.stop"])
    active: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
