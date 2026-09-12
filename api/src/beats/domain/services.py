"""Domain services - business logic that coordinates multiple entities."""

import logging
from collections import defaultdict
from collections.abc import Iterable, Mapping
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from beats.domain.contracts import absences_by_day, balance, expected_on, term_on
from beats.domain.exceptions import (
    AbsenceNotFound,
    InvalidEndTime,
    NoActiveTimer,
    NoContract,
    NoObjectMatched,
    NotADayJob,
    ProjectNotFound,
    TimerAlreadyRunning,
    UnknownHolidayRegion,
)
from beats.domain.holidays import Holiday, check_region, named_holidays_between
from beats.domain.models import (
    Absence,
    Beat,
    Contract,
    ContractDay,
    ContractTerm,
    ContractWeek,
    DayAbsence,
    Project,
    ProjectKind,
)
from beats.domain.ports import (
    AbsenceStore,
    BeatStore,
    FlowWindowReader,
    ProjectBeatReader,
    ProjectReader,
    ProjectStore,
    TimerBeatStore,
    TimerProjectReader,
)
from beats.domain.utils import local_date, normalize_tz

logger = logging.getLogger(__name__)

# Cap on auto-derived tags per session — enough to capture the repos + languages
# a focused session touches without turning the tag cloud into noise.
_MAX_FLOW_TAGS = 6


async def derive_flow_tags(
    flow_repo: FlowWindowReader, start: datetime, end: datetime | None
) -> list[str]:
    """Derive session tags from the ambient daemon's flow-window signals.

    Replaces manual tagging (the app takes no free-text input): tags are the
    distinct repos and editor languages the daemon observed while the session
    ran, over [start, end]. Repos come first (more specific), then languages.
    Best-effort — returns [] when the session has no end yet or no windows
    overlap (e.g. the daemon wasn't running).
    """
    if end is None:
        return []
    windows = await flow_repo.list_by_range(start, end)
    repos = [w.editor_repo.rstrip("/").split("/")[-1] for w in windows if w.editor_repo]
    langs = [w.editor_language.strip().lower() for w in windows if w.editor_language]
    seen: set[str] = set()
    tags: list[str] = []
    for tag in (*repos, *langs):
        if tag and tag not in seen:
            seen.add(tag)
            tags.append(tag)
    return tags[:_MAX_FLOW_TAGS]


def _has_override_for_week(project: Project, week_monday: date) -> bool:
    """Return True iff a goal override resolves for the given week."""
    for o in project.goal_overrides:
        if o.week_of == week_monday:
            return True
    for o in project.goal_overrides:
        if o.effective_from is not None and o.effective_from <= week_monday:
            return True
    return False


class TimerService:
    """Service for managing timer operations.

    Handles the business logic for starting and stopping timers,
    including validation that only one timer can run at a time.
    """

    def __init__(
        self,
        beat_repo: TimerBeatStore,
        project_repo: TimerProjectReader,
        flow_repo: FlowWindowReader | None = None,
    ):
        self.beat_repo = beat_repo
        self.project_repo = project_repo
        self.flow_repo = flow_repo

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
            active_project = await self.project_repo.get_by_id(active.project_id)
            raise TimerAlreadyRunning(
                project_name=active_project.name,
                beat=active.model_dump(mode="json"),
            )

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
        start = normalize_tz(active.start)
        end_normalized = normalize_tz(end)
        if end_normalized < start:
            raise InvalidEndTime()

        active.end = end
        if self.flow_repo is not None:
            active.tags = await derive_flow_tags(self.flow_repo, active.start, end)
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


class BeatService:
    """Service for managing beat CRUD operations."""

    def __init__(self, beat_repo: BeatStore, flow_repo: FlowWindowReader | None = None):
        self.beat_repo = beat_repo
        self.flow_repo = flow_repo

    async def create_beat(self, beat: Beat) -> Beat:
        """Create a new beat, auto-tagging it from daemon flow signals."""
        if self.flow_repo is not None and beat.end is not None:
            beat.tags = await derive_flow_tags(self.flow_repo, beat.start, beat.end)
        return await self.beat_repo.create(beat)

    async def get_beat(self, beat_id: str) -> Beat:
        """Get a beat by ID."""
        return await self.beat_repo.get_by_id(beat_id)

    async def update_beat(self, beat: Beat) -> Beat:
        """Update an existing beat, re-deriving tags from daemon flow signals.

        If the daemon has no windows for the (possibly edited) range we keep the
        beat's existing tags rather than wiping them — non-destructive for any
        tags captured before this range was last touched.
        """
        # Validate the beat can be stopped if end is being set
        if beat.end:
            start = normalize_tz(beat.start)
            end = normalize_tz(beat.end)
            if end < start:
                raise InvalidEndTime()
        if self.flow_repo is not None and beat.end is not None:
            derived = await derive_flow_tags(self.flow_repo, beat.start, beat.end)
            if derived:
                beat.tags = derived
            elif beat.id is not None:
                existing = await self.beat_repo.get_by_id(beat.id)
                beat.tags = existing.tags
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


def _check_contract(project: Project) -> None:
    """What a project write must satisfy beyond the model's own validators.

    A contract lives only on a day job: sent with any other kind it is refused
    (409), on the project routes as on `PUT /{id}/contract`, rather than kept
    dormant on a project that cannot read it. And its holiday region must be
    one the calendar library knows — deliberately not a validator on
    `Contract`: the model is re-validated on every read, and which codes the
    library knows moves with its version. A code it stops recognising must
    make one contract un-editable until it is fixed, not every project of the
    user unreadable.
    """
    contract = project.contract
    if contract is None:
        return
    if project.kind is not ProjectKind.DAY_JOB:
        raise NotADayJob()
    if contract.holiday_country is not None:
        check_region(contract.holiday_country, contract.holiday_subdivision)


class ProjectService:
    """Service for managing project operations and analytics."""

    def __init__(self, project_repo: ProjectStore, beat_repo: ProjectBeatReader):
        self.project_repo = project_repo
        self.beat_repo = beat_repo

    async def create_project(self, project: Project) -> Project:
        """Create a new project."""
        _check_contract(project)
        return await self.project_repo.create(project)

    async def update_project(self, project: Project) -> Project:
        """Update an existing project."""
        _check_contract(project)
        return await self.project_repo.update(project)

    async def replace_contract(self, project_id: str, contract: Contract) -> Project:
        """Replace a day job's whole contract — terms, region, opening balance, end.

        Whole rather than patched, like goal overrides: the terms are a history
        that only makes sense as one list. The kind is not touched here; a
        project that is not a day job has no contract to replace (409).
        """
        project = await self.project_repo.get_by_id(project_id)
        if project.kind is not ProjectKind.DAY_JOB:
            raise NotADayJob()
        project.contract = contract
        return await self.update_project(project)

    async def archive_project(self, project_id: str) -> Project:
        """Archive a project."""
        project = await self.project_repo.get_by_id(project_id)
        project.archived = True
        return await self.project_repo.update(project)

    async def unarchive_project(self, project_id: str) -> Project:
        """Restore an archived project — symmetric to archive_project.

        Using a dedicated endpoint (rather than PUT with archived=false)
        means callers can't silently wipe fields they don't yet know
        about: the UI Project type doesn't carry github_repo, category,
        or autostart_repos yet, so a generic update-based unarchive
        would drop them.
        """
        project = await self.project_repo.get_by_id(project_id)
        project.archived = False
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

    async def get_last_tracked_at(self, project_id: str) -> datetime | None:
        """The timestamp of the project's most recent activity.

        Used by the /projects index page's "last tracked" column (P3.0).
        Falls back to a beat's `start` when `end` is null (running beat) so
        an in-progress timer counts as "just now".
        """
        beats = await self.beat_repo.list_by_project(project_id)
        return self._last_tracked_from_beats(beats)

    # ------------------------------------------------------------------ #
    # FF.15: pure-Python helpers below. Each public method above fetches
    # beats per-project and delegates. The list_projects route (after
    # FF.15) fetches every displayed project's beats in ONE Mongo find and
    # calls these helpers directly, sharing the same in-memory list across
    # the three aggregations. The helpers MUST stay byte-for-byte
    # equivalent to the original public-method bodies — the
    # `*_matches_public_method` tests in test_domain.py guard the drift.
    # ------------------------------------------------------------------ #

    @staticmethod
    def _last_tracked_from_beats(beats: list[Beat]) -> datetime | None:
        if not beats:
            return None
        return max(b.end or b.start for b in beats)

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
        project = await self.project_repo.get_by_id(project_id)
        return self._week_breakdown_from_beats(
            beats, project, weeks_ago=weeks_ago, include_log_details=include_log_details
        )

    @staticmethod
    def _week_breakdown_from_beats(
        beats: list[Beat],
        project: Project | None,
        weeks_ago: int = 0,
        include_log_details: bool = False,
    ) -> dict:
        # Calculate week boundaries
        today = date.today() - timedelta(weeks=weeks_ago)
        start_of_week = today - timedelta(days=today.weekday())  # Monday
        end_of_week = start_of_week + timedelta(days=6)  # Sunday

        # Filter to completed beats in this week
        week_beats = [
            b for b in beats if b.end is not None and start_of_week <= b.start.date() <= end_of_week
        ]

        per_day_logs: dict[str, list] = defaultdict(list)
        per_day_duration: dict[str, timedelta] = defaultdict(timedelta)

        for beat in week_beats:
            day_name = beat.start.strftime("%A")
            per_day_duration[day_name] += beat.duration
            if include_log_details:
                per_day_logs[day_name].append(
                    {
                        "id": beat.id,
                        "start": beat.start.isoformat(),
                        "end": beat.end.isoformat() if beat.end else None,
                        "duration": str(beat.duration),
                    }
                )

        result = {}
        total_duration = timedelta()
        for i in range(7):
            day_date = start_of_week + timedelta(days=i)
            day_name = day_date.strftime("%A")
            duration = per_day_duration.get(day_name, timedelta())
            total_duration += duration
            result[day_name] = (
                per_day_logs.get(day_name, []) if include_log_details else str(duration)
            )

        result["total_hours"] = round(total_duration.total_seconds() / 3600, 2)
        # Canonical Monday for this week, resolved server-side. The UI keys goal
        # overrides off this value so the saved week_of always matches the week
        # the server resolves against — recomputing the Monday client-side drifts
        # across the week boundary whenever the client and server timezones land
        # on different calendar days.
        result["week_start"] = start_of_week.isoformat()

        # Resolve effective goal for this week
        if project:
            eff_goal, eff_type = project.effective_goal(start_of_week)
            result["effective_goal"] = eff_goal
            result["effective_goal_type"] = eff_type.value if eff_type else None
            # True iff a matching override is in effect for this week — lets the
            # UI distinguish "override says no goal" (null + overridden=true,
            # render as "No goal") from "no override and no project default"
            # (null + overridden=false, render as "—").
            result["effective_goal_overridden"] = _has_override_for_week(project, start_of_week)

        return result

    async def get_monthly_totals(self, project_id: str) -> dict:
        """Get total time per month for a project.

        Returns:
            Dict with durations per month, total minutes, and any warnings.
        """
        beats = await self.beat_repo.list_by_project(project_id)
        return self._monthly_totals_from_beats(beats)

    @staticmethod
    def _monthly_totals_from_beats(beats: list[Beat]) -> dict:
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

    async def get_daily_average(self, project_id: str, days: int = 30) -> dict:
        """Get average daily session time for a project over the last N days."""
        beats = await self.beat_repo.list_by_project(project_id)
        cutoff = date.today() - timedelta(days=days)
        completed = [b for b in beats if b.end is not None and b.start.date() >= cutoff]
        if not completed:
            return {"avg_minutes": 0, "days_tracked": 0}
        by_day: dict[date, timedelta] = defaultdict(timedelta)
        for b in completed:
            by_day[b.start.date()] += b.duration
        days_tracked = len(by_day)
        total = sum(by_day.values(), timedelta())
        avg_minutes = round(total.total_seconds() / 60 / days_tracked)
        return {"avg_minutes": avg_minutes, "days_tracked": days_tracked}

    async def get_daily_summary(self, project_id: str) -> dict[str, str]:
        """Get summary of time per day for a project."""
        beats = await self.beat_repo.list_by_project(project_id)

        by_day: dict[date, list[timedelta]] = {}
        for beat in beats:
            if beat.day not in by_day:
                by_day[beat.day] = []
            by_day[beat.day].append(beat.duration)

        return {str(day): str(sum(durations, timedelta())) for day, durations in by_day.items()}


def worked_by_local_day(beats: Iterable[Beat], tz: ZoneInfo) -> dict[date, float]:
    """Hours per local calendar day, by the day each beat *started*.

    A beat that crosses midnight belongs whole to the day it started on: the
    contract counts hours, not which side of twelve they fell, and one late
    session is one session. A running beat counts up to now (`Beat.duration`),
    so the week's `worked` moves while the timer runs.
    """
    hours: dict[date, float] = defaultdict(float)
    for beat in beats:
        hours[local_date(beat.start, tz)] += beat.duration.total_seconds() / 3600
    return hours


def _owes(term: ContractTerm | None) -> bool:
    """Whether a term is time-based: before the first term and under an
    objective term there is no expectation to report, only work."""
    return term is not None and term.hours_per_week is not None


def _hours(value: float) -> float:
    return round(value, 2)


class ContractService:
    """A day job read against its contract, and its absences.

    Writing the contract is `ProjectService.replace_contract`, a project write
    with the region check; this service only reads projects, through a
    user-scoped repository, so someone else's project is not found (404)
    rather than forbidden — the same answer as for a project that does not
    exist. Absences are kept here because their only reader is the week.
    """

    def __init__(
        self,
        project_repo: ProjectReader,
        beat_repo: ProjectBeatReader,
        absence_repo: AbsenceStore,
    ):
        self.project_repo = project_repo
        self.beat_repo = beat_repo
        self.absence_repo = absence_repo

    async def week(self, project_id: str, week_of: date | None, tz: ZoneInfo) -> ContractWeek:
        """The week starting `week_of` (a Monday; None for the current week in
        `tz`) against the contract, with the balance as of today in `tz`."""
        project = await self._day_job(project_id)
        beats = await self.beat_repo.list_by_project(project_id)
        return await self.week_for(project, beats, week_of, tz)

    async def week_for(
        self, project: Project, beats: list[Beat], week_of: date | None, tz: ZoneInfo
    ) -> ContractWeek:
        """`week` for a project whose beats the caller already holds — the
        project index loads every listed project's beats in one query and
        must not load them again per day job.

        One absence read and one calendar build per call, both over the
        union of the week and the contract's life so far: the week needs its
        own days, the balance needs every day since the contract started.
        """
        if project.kind is not ProjectKind.DAY_JOB:
            raise NotADayJob()
        if project.contract is None:
            raise NoContract()
        if project.id is None:
            raise ProjectNotFound()
        contract = project.contract
        today = datetime.now(tz).date()
        if week_of is None:
            week_of = today - timedelta(days=today.weekday())
        start = min(contract.starts_on, week_of)
        end = max(today, week_of + timedelta(days=6))
        absences = await self.absence_repo.list_by_project(project.id, start, end)
        holidays: dict[date, str] = {}
        if contract.holiday_country is not None:
            holidays = named_holidays_between(
                contract.holiday_country, contract.holiday_subdivision, start, end
            )
        worked = worked_by_local_day(beats, tz)
        return self._assemble(contract, absences, holidays, worked, week_of, today)

    async def weeks_for(
        self, projects: Iterable[Project], beats_by_pid: Mapping[str, list[Beat]], tz: ZoneInfo
    ) -> dict[str, ContractWeek]:
        """The current week of every day job with a contract among `projects`,
        by project id — the project index's read, over beats it already holds.

        A project of another kind, or without a contract, is simply absent
        from the result. So is one whose region the calendar library has
        stopped knowing: that makes one contract unreadable — its own week
        route says so — not the whole project list, so it is logged and
        skipped.
        """
        weeks: dict[str, ContractWeek] = {}
        for project in projects:
            if not (project.id and project.kind is ProjectKind.DAY_JOB and project.contract):
                continue
            try:
                weeks[project.id] = await self.week_for(
                    project, beats_by_pid.get(project.id, []), None, tz
                )
            except UnknownHolidayRegion:
                logger.warning("project %s: contract region unknown, week skipped", project.id)
        return weeks

    @staticmethod
    def _assemble(
        contract: Contract,
        absences: Iterable[Absence],
        holidays: Mapping[date, str],
        worked: Mapping[date, float],
        week_of: date,
        today: date,
    ) -> ContractWeek:
        by_day = absences_by_day(absences)
        holiday_days = set(holidays)
        days: list[ContractDay] = []
        expected_raw = 0.0
        worked_raw = 0.0
        for offset in range(7):
            day = week_of + timedelta(days=offset)
            expected_day = expected_on(contract, day, holiday_days, by_day)
            worked_day = worked.get(day, 0.0)
            expected_raw += expected_day
            worked_raw += worked_day
            absence = by_day.get(day)
            days.append(
                ContractDay(
                    date=day,
                    expected=_hours(expected_day),
                    worked=_hours(worked_day),
                    holiday=holidays.get(day),
                    absence=(
                        DayAbsence(type=absence.type, half_day=absence.half_day, note=absence.note)
                        if absence is not None
                        else None
                    ),
                )
            )
        # Weekdays only: Saturday and Sunday owe nothing under any term, so
        # they say nothing about whether the week has an expectation.
        owes = any(_owes(term_on(contract, day.date)) for day in days[:5])
        expected = _hours(expected_raw) if owes else None
        remaining = _hours(expected_raw - worked_raw) if owes else None
        running = (
            _hours(balance(contract, absences, holiday_days, worked, today))
            if _owes(term_on(contract, today))
            else None
        )
        return ContractWeek(
            week_of=week_of,
            expected=expected,
            worked=_hours(worked_raw),
            remaining=remaining,
            balance=running,
            days=days,
        )

    async def holidays(self, project_id: str, year: int | None, tz: ZoneInfo) -> list[Holiday]:
        """The contract region's public holidays in `year` (None for the current
        year in `tz`), for the calendar. Empty when there is no contract or it
        names no region."""
        project = await self._day_job(project_id)
        contract = project.contract
        if contract is None or contract.holiday_country is None:
            return []
        if year is None:
            year = datetime.now(tz).year
        found = named_holidays_between(
            contract.holiday_country,
            contract.holiday_subdivision,
            date(year, 1, 1),
            date(year, 12, 31),
        )
        return [Holiday(date=day, name=name) for day, name in sorted(found.items())]

    async def list_absences(
        self, project_id: str, start: date | None, end: date | None, tz: ZoneInfo
    ) -> list[Absence]:
        """Absences in [start, end], by date; each bound left None defaults on
        its own to the current calendar year in `tz`."""
        await self._day_job(project_id)
        today = datetime.now(tz).date()
        return await self.absence_repo.list_by_project(
            project_id, start or date(today.year, 1, 1), end or date(today.year, 12, 31)
        )

    async def record_absence(self, absence: Absence) -> Absence:
        """Record an absence; one already on that date is replaced."""
        await self._day_job(absence.project_id)
        return await self.absence_repo.upsert(absence)

    async def remove_absence(self, project_id: str, absence_id: str) -> None:
        """Remove an absence; one that is not on this project is not found."""
        await self._day_job(project_id)
        if not await self.absence_repo.delete(project_id, absence_id):
            raise AbsenceNotFound(absence_id)

    async def _day_job(self, project_id: str) -> Project:
        """The project, provided it is a day job — with or without a contract:
        leave can be recorded before the contract is written, and the holidays
        of a job without one are simply none. Only the week needs a contract."""
        project = await self.project_repo.get_by_id(project_id)
        if project.kind is not ProjectKind.DAY_JOB:
            raise NotADayJob()
        return project
