"""Domain services - business logic that coordinates multiple entities."""

from collections import defaultdict
from datetime import UTC, date, datetime, timedelta

from beats.domain.exceptions import (
    InvalidEndTime,
    NoActiveTimer,
    NoObjectMatched,
    ProjectNotFound,
    TimerAlreadyRunning,
)
from beats.domain.models import Beat, Project
from beats.infrastructure.repositories import BeatRepository, ProjectRepository


class TimerService:
    """Service for managing timer operations.

    Handles the business logic for starting and stopping timers,
    including validation that only one timer can run at a time.
    """

    def __init__(self, beat_repo: BeatRepository, project_repo: ProjectRepository):
        self.beat_repo = beat_repo
        self.project_repo = project_repo

    async def start_timer(self, project_id: str, start_time: datetime | None = None) -> Beat:
        """Start a new timer for a project.

        Args:
            project_id: The ID of the project to track time against.
            start_time: When the timer started. Defaults to now.

        Returns:
            The created Beat with an active timer.

        Raises:
            ProjectNotFound: If the project doesn't exist.
            TimerAlreadyRunning: If another timer is already active.
        """
        # Validate project exists
        if not await self.project_repo.exists(project_id):
            raise ProjectNotFound(project_id)

        # Check no active timer
        active = await self.beat_repo.get_active()
        if active:
            raise TimerAlreadyRunning()

        # Create new beat
        start = start_time or datetime.now(UTC)
        beat = Beat(project_id=project_id, start=start)
        return await self.beat_repo.create(beat)

    async def stop_timer(self, end_time: datetime | None = None) -> Beat:
        """Stop the currently running timer.

        Args:
            end_time: When the timer stopped. Defaults to now.

        Returns:
            The updated Beat with end time set.

        Raises:
            NoActiveTimer: If no timer is currently running.
            InvalidEndTime: If end_time is before the start time.
        """
        active = await self.beat_repo.get_active()
        if not active:
            raise NoActiveTimer()

        end = end_time or datetime.now(UTC)

        # Validate end time is after start
        start = self._normalize_tz(active.start)
        end_normalized = self._normalize_tz(end)
        if end_normalized < start:
            raise InvalidEndTime()

        active.end = end
        return await self.beat_repo.update(active)

    async def get_status(self) -> dict:
        """Get the current timer status.

        Returns:
            Dict with timer status including whether a timer is running,
            the project, duration, etc.
        """
        try:
            active = await self.beat_repo.get_active()
            if active:
                project = await self.project_repo.get_by_id(active.project_id)
                return {
                    "isBeating": True,
                    "project": project.model_dump(),
                    "since": active.start.isoformat(),
                    "so_far": str(active.duration),
                }
        except NoObjectMatched, ProjectNotFound:
            pass

        # No active timer - try to get last beat info
        try:
            last_beat = await self.beat_repo.get_last()
            return {
                "isBeating": False,
                "last_beat": {
                    "id": last_beat.id,
                    "project_id": last_beat.project_id,
                    "end": last_beat.end.isoformat() if last_beat.end else None,
                },
            }
        except NoObjectMatched:
            return {"isBeating": False}

    @staticmethod
    def _normalize_tz(dt: datetime) -> datetime:
        """Ensure datetime is timezone-aware (UTC if naive)."""
        if dt.tzinfo is None:
            return dt.replace(tzinfo=UTC)
        return dt


class BeatService:
    """Service for managing beat CRUD operations."""

    def __init__(self, beat_repo: BeatRepository):
        self.beat_repo = beat_repo

    async def create_beat(self, beat: Beat) -> Beat:
        """Create a new beat."""
        return await self.beat_repo.create(beat)

    async def get_beat(self, beat_id: str) -> Beat:
        """Get a beat by ID."""
        return await self.beat_repo.get_by_id(beat_id)

    async def update_beat(self, beat: Beat) -> Beat:
        """Update an existing beat."""
        # Validate the beat can be stopped if end is being set
        if beat.end:
            start = self._normalize_tz(beat.start)
            end = self._normalize_tz(beat.end)
            if end < start:
                raise InvalidEndTime()
        return await self.beat_repo.update(beat)

    async def delete_beat(self, beat_id: str) -> bool:
        """Delete a beat by ID."""
        return await self.beat_repo.delete(beat_id)

    async def list_beats(
        self,
        project_id: str | None = None,
        date_filter: date | None = None,
    ) -> list[Beat]:
        """List beats with optional filters."""
        return await self.beat_repo.list(project_id=project_id, date_filter=date_filter)

    @staticmethod
    def _normalize_tz(dt: datetime) -> datetime:
        if dt.tzinfo is None:
            return dt.replace(tzinfo=UTC)
        return dt


class ProjectService:
    """Service for managing project operations and analytics."""

    def __init__(self, project_repo: ProjectRepository, beat_repo: BeatRepository):
        self.project_repo = project_repo
        self.beat_repo = beat_repo

    async def create_project(self, project: Project) -> Project:
        """Create a new project."""
        return await self.project_repo.create(project)

    async def get_project(self, project_id: str) -> Project:
        """Get a project by ID."""
        return await self.project_repo.get_by_id(project_id)

    async def update_project(self, project: Project) -> Project:
        """Update an existing project."""
        return await self.project_repo.update(project)

    async def archive_project(self, project_id: str) -> Project:
        """Archive a project."""
        project = await self.project_repo.get_by_id(project_id)
        project.archived = True
        return await self.project_repo.update(project)

    async def list_projects(self, archived: bool = False) -> list[Project]:
        """List projects with optional archived filter."""
        return await self.project_repo.list(archived=archived)

    async def get_today_time(self, project_id: str) -> timedelta:
        """Get total time spent on project today."""
        beats = await self.beat_repo.list_by_project(project_id)
        today = date.today()
        today_beats = [b for b in beats if b.start.date() == today]
        return sum((b.duration for b in today_beats), timedelta())

    async def get_week_breakdown(
        self,
        project_id: str,
        weeks_ago: int = 0,
        include_log_details: bool = False,
    ) -> dict:
        """Get time breakdown for a week.

        Args:
            project_id: The project ID.
            weeks_ago: How many weeks back (0 = current week).
            include_log_details: If True, include individual log entries.

        Returns:
            Dict with time per day and total hours.
        """
        beats = await self.beat_repo.list_by_project(project_id)

        # Calculate week boundaries
        today = date.today() - timedelta(weeks=weeks_ago)
        start_of_week = today - timedelta(days=today.weekday())  # Monday
        end_of_week = start_of_week + timedelta(days=6)  # Sunday

        # Filter to completed beats in this week
        week_beats = [
            b for b in beats if b.end is not None and start_of_week <= b.start.date() <= end_of_week
        ]

        if include_log_details:
            per_day_logs: dict[str, list] = defaultdict(list)
            per_day_duration: dict[str, timedelta] = defaultdict(timedelta)

            for beat in week_beats:
                day_name = beat.start.strftime("%A")
                per_day_logs[day_name].append(
                    {
                        "id": beat.id,
                        "start": beat.start.isoformat(),
                        "end": beat.end.isoformat() if beat.end else None,
                        "duration": str(beat.duration),
                    }
                )
                per_day_duration[day_name] += beat.duration

            result = {}
            total_duration = timedelta()
            for i in range(7):
                day_date = start_of_week + timedelta(days=i)
                day_name = day_date.strftime("%A")
                result[day_name] = per_day_logs.get(day_name, [])
                total_duration += per_day_duration.get(day_name, timedelta())

            result["total_hours"] = round(total_duration.total_seconds() / 3600, 2)
            return result
        else:
            per_day: dict[str, timedelta] = defaultdict(timedelta)
            for beat in week_beats:
                per_day[beat.start.strftime("%A")] += beat.duration

            result = {}
            total_duration = timedelta()
            for i in range(7):
                day_date = start_of_week + timedelta(days=i)
                day_name = day_date.strftime("%A")
                duration = per_day.get(day_name, timedelta())
                result[day_name] = str(duration)
                total_duration += duration

            result["total_hours"] = round(total_duration.total_seconds() / 3600, 2)
            return result

    async def get_monthly_totals(self, project_id: str) -> dict:
        """Get total time per month for a project.

        Returns:
            Dict with durations per month, total minutes, and any warnings.
        """
        beats = await self.beat_repo.list_by_project(project_id)
        warnings: list[str] = []

        # Filter to completed beats and collect durations
        durations_per_month: dict[str, timedelta] = defaultdict(timedelta)
        for beat in beats:
            if beat.end is None:
                continue
            if beat.duration > timedelta(hours=24):
                warnings.append(
                    f"Warning: Log {beat.id} has duration longer than 24 hours ({beat.duration})."
                )
            month_key = beat.start.strftime("%Y-%m")
            durations_per_month[month_key] += beat.duration

        # Calculate totals
        grand_total = sum(durations_per_month.values(), timedelta())
        total_minutes = round(grand_total.total_seconds() / 60)

        # Convert to hours
        result = {
            month: round(duration.total_seconds() / 3600, 2)
            for month, duration in sorted(durations_per_month.items())
        }

        return {
            "durations_per_month": result,
            "total_minutes": total_minutes,
            "warnings": warnings,
        }

    async def get_daily_summary(self, project_id: str) -> dict[str, str]:
        """Get summary of time per day for a project."""
        beats = await self.beat_repo.list_by_project(project_id)

        by_day: dict[date, list[timedelta]] = {}
        for beat in beats:
            if beat.day not in by_day:
                by_day[beat.day] = []
            by_day[beat.day].append(beat.duration)

        return {str(day): str(sum(durations, timedelta())) for day, durations in by_day.items()}
