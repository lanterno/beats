"""Domain models - pure business entities with no external dependencies."""

from datetime import UTC, date, datetime, timedelta

from pydantic import BaseModel, ConfigDict, Field, computed_field


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
        start = self._normalize_tz(self.start)
        end = self._normalize_tz(end)
        return end - start

    @computed_field
    @property
    def day(self) -> date:
        """The date this beat started on."""
        return self.start.date()

    @staticmethod
    def _normalize_tz(dt: datetime) -> datetime:
        """Ensure datetime is timezone-aware (UTC if naive)."""
        if dt.tzinfo is None:
            return dt.replace(tzinfo=UTC)
        return dt


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
    archived: bool = False
