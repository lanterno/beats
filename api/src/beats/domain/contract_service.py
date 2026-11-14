"""The day job read against its contract — the project page's one service.

Split out of `services.py` at the size ceiling (CLAUDE.md § Conventions); it sits
beside the `contracts.py` arithmetic it reads. The shared project guards
(`refuse_locked`, `_refuse_managed`, `organisation_stamp_for_day`) and
`worked_by_local_day` stay in `services.py`, which also writes contracts
(`ProjectService.replace_contract`), so the dependency runs one way.
"""

import logging
from collections.abc import Callable, Iterable, Mapping
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from beats.domain.contracts import (
    absences_by_day,
    balance_terms,
    counts_worked,
    expected_on,
    owes,
    round_hours,
    term_on,
    week_expectation,
)
from beats.domain.exceptions import (
    AbsenceNotFound,
    AdjustmentNotFound,
    AdjustmentOutsideBalance,
    MonthOutsideContract,
    NoContract,
    NotADayJob,
    NoVacationEntitlement,
    ProjectNotFound,
    UnknownHolidayRegion,
    VacationYearOutOfRange,
)
from beats.domain.holidays import (
    Holiday,
    contract_calendar,
    contract_holidays,
)
from beats.domain.ledger import assemble_ledger
from beats.domain.models import (
    Absence,
    AbsenceType,
    BalanceAdjustment,
    Beat,
    Contract,
    ContractDay,
    ContractWeek,
    DayAbsence,
    Ledger,
    Project,
    ProjectKind,
    VacationYear,
)
from beats.domain.ports import (
    AbsenceStore,
    AdjustmentStore,
    PeriodLocks,
    ProjectBeatReader,
    ProjectReader,
)
from beats.domain.services import (
    _refuse_managed,
    organisation_stamp_for_day,
    refuse_locked,
    worked_by_local_day,
)
from beats.domain.timesheet import (
    COMPANY_HOLIDAY,
    Timesheet,
    assemble_timesheet,
    timesheet_range,
)
from beats.domain.vacation import vacation_year

logger = logging.getLogger(__name__)


class ContractService:
    """A day job read against its contract, its absences and its balance
    adjustments.

    Writing the contract is `ProjectService.replace_contract`, a project write
    with the region check; this service only reads projects, through a
    user-scoped repository, so someone else's project is not found (404)
    rather than forbidden — the same answer as for a project that does not
    exist. Absences and balance adjustments are kept here because their only
    readers are the week, the ledger and the vacation year.
    """

    def __init__(
        self,
        project_repo: ProjectReader,
        beat_repo: ProjectBeatReader,
        absence_repo: AbsenceStore,
        adjustment_repo: AdjustmentStore,
        now: Callable[[ZoneInfo], datetime] = datetime.now,
        locks: PeriodLocks | None = None,
    ):
        self.project_repo = project_repo
        self.beat_repo = beat_repo
        self.absence_repo = absence_repo
        self.adjustment_repo = adjustment_repo
        # Stage 3: absence and adjustment writes dated inside an approved
        # timesheet month are refused, like a beat's.
        self.locks = locks
        # The one clock every read here uses: which week is open, which day
        # the balance is as of, which year the calendar defaults to are all
        # "today in the request timezone", and a test hands in a fixed instant
        # to pin that it is the request's and not the server's.
        self._now = now

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

        One absence read, one adjustment read and one calendar build per
        call, over the union of the week and the contract's life so far: the
        week needs its own days, the balance needs every day since the
        contract started. Adjustments before the first day count for
        nothing, so they are not read.
        """
        if project.kind is not ProjectKind.DAY_JOB:
            raise NotADayJob()
        if project.contract is None:
            raise NoContract()
        if project.id is None:
            raise ProjectNotFound()
        contract = project.contract
        today = self._now(tz).date()
        if week_of is None:
            week_of = today - timedelta(days=today.weekday())
        start = min(contract.starts_on, week_of)
        end = max(today, week_of + timedelta(days=6))
        absences = await self.absence_repo.list_by_project(project.id, start, end)
        adjustments = await self.adjustment_repo.list_by_project(
            project.id, contract.starts_on, end
        )
        holidays = contract_holidays(contract, start, end)
        worked = worked_by_local_day(beats, tz)
        return self._assemble(contract, absences, holidays, worked, adjustments, week_of, today)

    async def ledger(self, project_id: str, weeks: int, tz: ZoneInfo) -> Ledger:
        """The last `weeks` weeks of any project, newest first, ending with the
        current week in `tz`, and the balance as of today in `tz` with the
        terms that make it — the project page's one read for every week
        figure (`domain/ledger.py`).

        One beats read, and on a day job with a contract one absence read,
        one adjustment read and one calendar build, over the union of the
        weeks shown and the contract's life so far: each week's closing
        balance needs every day since the contract started. A project of another kind, or a day job
        without a contract, gets its goal and its hours and nothing is read
        for a contract. A region the calendar library has stopped knowing is
        this project's own error (400), as it is on the week route.
        """
        project = await self.project_repo.get_by_id(project_id)
        today = self._now(tz).date()
        monday = today - timedelta(days=today.weekday())
        contract = project.contract if project.kind is ProjectKind.DAY_JOB else None
        # Only the sessions that can reach a day the ledger shows: from the
        # contract's first day, since every close needs every day since then,
        # or from the oldest week shown when nothing governs. A day before
        # that is in no figure, and reading every session a project ever had
        # was the API's slowest read (#376). The extra day is for the
        # timezone: a session is bucketed by its local start day, and a tz
        # behind UTC can pull a UTC instant back onto the day before.
        first_day = monday - timedelta(weeks=weeks - 1)
        if contract is not None:
            first_day = min(contract.starts_on, first_day)
        since = datetime.combine(first_day - timedelta(days=1), time.min, tzinfo=UTC)
        beats = await self.beat_repo.list_by_project(project_id, since)
        absences: list[Absence] = []
        adjustments: list[BalanceAdjustment] = []
        holidays: dict[date, str] = {}
        if contract is not None and project.id is not None:
            start = min(contract.starts_on, monday - timedelta(weeks=weeks - 1))
            end = max(today, monday + timedelta(days=6))
            absences = await self.absence_repo.list_by_project(project.id, start, end)
            adjustments = await self.adjustment_repo.list_by_project(
                project.id, contract.starts_on, end
            )
            holidays = contract_holidays(contract, start, end)
        worked = worked_by_local_day(beats, tz)
        return assemble_ledger(
            project, contract, absences, holidays, worked, adjustments, today, weeks
        )

    async def timesheet(self, project_id: str, month: date, tz: ZoneInfo) -> Timesheet:
        """The finished days of `month` (its 1st) inside the contract, a row
        each, with the balance brought forward and carried forward
        (`domain/timesheet.py`). Today is the request's, in `tz`: the sheet
        runs through yesterday, and a running timer counts up to now on the
        day it started, as on the ledger.

        One beats read, one absence read, one adjustment read and one
        calendar build, over the contract's life through the sheet's last
        day: every close needs every day since the contract started, not
        only the month's. A company holiday goes by `COMPANY_HOLIDAY`, not
        the name typed for it. 409 on a project that is not a day job
        (NOT_A_DAY_JOB), without a contract (NO_CONTRACT), or for a month
        with no finished day inside the contract (OUTSIDE_CONTRACT).
        """
        project = await self._day_job(project_id)
        contract = project.contract
        if contract is None:
            raise NoContract()
        span = timesheet_range(contract, month, self._now(tz).date())
        if span is None:
            raise MonthOutsideContract()
        first, last = span
        beats = await self.beat_repo.list_by_project(project_id)
        absences = await self.absence_repo.list_by_project(project_id, contract.starts_on, last)
        adjustments = await self.adjustment_repo.list_by_project(
            project_id, contract.starts_on, last
        )
        holidays = contract_holidays(
            contract, contract.starts_on, last, company_name=COMPANY_HOLIDAY
        )
        worked = worked_by_local_day(beats, tz)
        return assemble_timesheet(contract, absences, holidays, worked, adjustments, first, last)

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

    async def current_weeks(
        self, projects: Iterable[Project], tz: ZoneInfo, as_of: date
    ) -> dict[str, ContractWeek]:
        """The current week of every day job with a contract among `projects`,
        by project id, provided `as_of` is today in `tz` — the coach's read,
        which holds no beats of its own.

        Empty for any other day: the figures are today's (the balance is as
        of today, the week is today's), and this service's clock is the one
        that says which day that is, so a backdated brief does not quote
        today's balance as its own and a test that fixes the clock fixes
        both sides. Otherwise one beats read per day job — a running beat
        counts, as on the project page — and then the index's read
        (`weeks_for`), so the figures are the week route's to the decimal
        and a region the library has stopped knowing skips that project.
        """
        if as_of != self._now(tz).date():
            return {}
        day_jobs = [p for p in projects if p.id and p.kind is ProjectKind.DAY_JOB and p.contract]
        beats_by_pid = {p.id: await self.beat_repo.list_by_project(p.id) for p in day_jobs if p.id}
        return await self.weeks_for(day_jobs, beats_by_pid, tz)

    async def expected_for_week(self, project: Project, week_of: date) -> float | None:
        """What the contract expects of the week starting `week_of` — the week
        route's `expected` on its own, for the readers that quote a figure
        beside it: the Inbox's planning line, the pacing card, the
        stale-project card. None on anything but a day job with a
        contract, and under the null rule (`week_expectation`).

        One absence read and one calendar build, over the week alone — the
        balance is not wanted here, so nothing before the week is. A region
        the calendar library has stopped knowing costs the figure, not the
        reader: logged and None, as the index does.
        """
        if not (project.id and project.kind is ProjectKind.DAY_JOB and project.contract):
            return None
        contract = project.contract
        end = week_of + timedelta(days=6)
        absences = await self.absence_repo.list_by_project(project.id, week_of, end)
        try:
            holidays = set(contract_holidays(contract, week_of, end))
        except UnknownHolidayRegion:
            logger.warning("project %s: contract region unknown, expectation skipped", project.id)
            return None
        return week_expectation(contract, absences, holidays, week_of)

    @staticmethod
    def _assemble(
        contract: Contract,
        absences: Iterable[Absence],
        holidays: Mapping[date, str],
        worked: Mapping[date, float],
        adjustments: Iterable[BalanceAdjustment],
        week_of: date,
        today: date,
    ) -> ContractWeek:
        by_day = absences_by_day(absences)
        holiday_days = set(holidays)
        days: list[ContractDay] = []
        expected_raw = 0.0
        worked_raw = 0.0
        counted_raw = 0.0  # worked as the balance counts it (`counts_worked`)
        for offset in range(7):
            day = week_of + timedelta(days=offset)
            expected_day = expected_on(contract, day, holiday_days, by_day)
            worked_day = worked.get(day, 0.0)
            expected_raw += expected_day
            worked_raw += worked_day
            if counts_worked(contract, day):
                counted_raw += worked_day
            absence = by_day.get(day)
            days.append(
                ContractDay(
                    date=day,
                    expected=round_hours(expected_day),
                    worked=round_hours(worked_day),
                    holiday=holidays.get(day),
                    absence=(
                        DayAbsence(type=absence.type, half_day=absence.half_day, note=absence.note)
                        if absence is not None
                        else None
                    ),
                )
            )
        # The same function every other reader of the figure goes through,
        # so the card, the history row and the planning line cannot drift.
        expected = week_expectation(contract, absences, holiday_days, week_of)
        # Rounded from the raw sums, as every other figure here is: 8.545 h
        # of a 40 h week reads 8.54 worked and 31.45 remaining, which the
        # page shows as 8.5 and 31.4 and the coach says as the page does.
        # The page's figures need not add up at the decimal it shows.
        remaining = round_hours(expected_raw - counted_raw) if expected is not None else None
        running = (
            balance_terms(contract, absences, holiday_days, worked, adjustments, today)
            if owes(term_on(contract, today))
            else None
        )
        return ContractWeek(
            week_of=week_of,
            expected=expected,
            worked=round_hours(worked_raw),
            remaining=remaining,
            balance=round_hours(running.balance) if running else None,
            days=days,
            balance_as_of=today if running else None,
            balance_opening=round_hours(running.opening) if running else None,
            balance_worked=round_hours(running.worked) if running else None,
            balance_expected_through=(round_hours(running.expected_through) if running else None),
            balance_adjusted=round_hours(running.adjusted) if running else None,
        )

    async def holidays(
        self, project_id: str, year: int | None, tz: ZoneInfo, *, include_not_given: bool = False
    ) -> list[Holiday]:
        """The contract's holidays in `year` (None for the current year in
        `tz`), by date, for the calendar: the region's the employer gives and
        the company's own, and with `include_not_given` the region's it does
        not give as well. Empty when there is no contract."""
        project = await self._day_job(project_id)
        contract = project.contract
        if contract is None:
            return []
        if year is None:
            year = self._now(tz).year
        return contract_calendar(
            contract, date(year, 1, 1), date(year, 12, 31), include_not_given=include_not_given
        )

    async def vacation(self, project_id: str, year: int | None, tz: ZoneInfo) -> VacationYear:
        """One year of the contract's vacation entitlement (None for the
        current year in `tz`, the only thing the clock is read for), from
        the opening on: `domain/vacation.py` chains every year before it.

        One absence read, from the opening through the end of `year` (or
        `ended_on`), and one calendar build over the span of the vacation
        days in it alone, so a chain of many years does not build a
        calendar for each. 409 without a contract, without an entitlement,
        or for a year before the opening's or after the one the contract
        ends in.
        """
        project = await self._day_job(project_id)
        contract = project.contract
        if contract is None:
            raise NoContract()
        entitlement = contract.vacation
        if entitlement is None:
            raise NoVacationEntitlement()
        if year is None:
            year = self._now(tz).year
        first = entitlement.opening_on.year
        last = contract.ended_on.year if contract.ended_on is not None else None
        if year < first or (last is not None and year > last):
            raise VacationYearOutOfRange(first, last)
        end = date(year, 12, 31)
        if contract.ended_on is not None:
            end = min(end, contract.ended_on)
        absences = await self.absence_repo.list_by_project(project_id, entitlement.opening_on, end)
        days_off = [a.date for a in absences if a.type is AbsenceType.VACATION]
        holidays = (
            set(contract_holidays(contract, min(days_off), max(days_off))) if days_off else set()
        )
        return vacation_year(contract, absences, holidays, year)

    async def list_absences(
        self, project_id: str, start: date | None, end: date | None, tz: ZoneInfo
    ) -> list[Absence]:
        """Absences in [start, end], by date; each bound left None defaults on
        its own to the current calendar year in `tz`."""
        await self._day_job(project_id)
        today = self._now(tz).date()
        return await self.absence_repo.list_by_project(
            project_id, start or date(today.year, 1, 1), end or date(today.year, 12, 31)
        )

    async def record_absence(self, absence: Absence) -> Absence:
        """Record an absence; one already on that date is replaced. On an
        organisation's project it is stamped as that organisation's record,
        as a beat there is — and, as a beat is, only from the day the member
        shares from. Where the employer manages the contract the member asks
        instead (409 CONTRACT_MANAGED), and a date inside an approved month
        is refused."""
        project = await self._day_job(absence.project_id)
        _refuse_managed(project)
        await refuse_locked(self.locks, project, None, absence.date)
        absence.organisation_id = organisation_stamp_for_day(project, absence.date)
        return await self.absence_repo.upsert(absence)

    async def remove_absence(self, project_id: str, absence_id: str) -> None:
        """Remove an absence; one that is not on this project is not found.
        On a managed assignment the days off are the employer's to change,
        and one dated inside an approved month is refused — removing a day
        off moves the month's expectation exactly as booking one does."""
        project = await self._day_job(project_id)
        _refuse_managed(project)
        day = await self.absence_repo.day_of(project_id, absence_id)
        if day is not None:
            await refuse_locked(self.locks, project, None, day)
        if not await self.absence_repo.delete(project_id, absence_id):
            raise AbsenceNotFound(absence_id)

    async def record_adjustment(
        self, adjustment: BalanceAdjustment, tz: ZoneInfo
    ) -> BalanceAdjustment:
        """Record a balance adjustment; one already on that date is replaced
        and keeps its id. It needs a contract (without one there is no
        balance to adjust) and a date from the contract's first day through
        today in `tz`: before the first day it would count for nothing, and a
        future one would move a balance nobody can see yet. After `ended_on`
        is allowed: that is how a final balance is paid out."""
        project = await self._day_job(adjustment.project_id)
        _refuse_managed(project)
        await refuse_locked(self.locks, project, None, adjustment.date)
        contract = project.contract
        if contract is None:
            raise NoContract()
        today = self._now(tz).date()
        if not contract.starts_on <= adjustment.date <= today:
            raise AdjustmentOutsideBalance()
        return await self.adjustment_repo.upsert(adjustment)

    async def remove_adjustment(self, project_id: str, adjustment_id: str) -> None:
        """Remove a balance adjustment; one that is not on this project is
        not found. On a managed assignment they are the employer's, and one
        dated inside an approved month is refused: the frozen balance was
        taken with it counted."""
        project = await self._day_job(project_id)
        _refuse_managed(project)
        day = await self.adjustment_repo.day_of(project_id, adjustment_id)
        if day is not None:
            await refuse_locked(self.locks, project, None, day)
        if not await self.adjustment_repo.delete(project_id, adjustment_id):
            raise AdjustmentNotFound(adjustment_id)

    async def _day_job(self, project_id: str) -> Project:
        """The project, provided it is a day job — with or without a contract:
        leave can be recorded before the contract is written, and the holidays
        of a job without one are simply none. Only the week needs a contract."""
        project = await self.project_repo.get_by_id(project_id)
        if project.kind is not ProjectKind.DAY_JOB:
            raise NotADayJob()
        return project
