"""`ProjectService` and `ContractService`: the project CRUD, the week's
expectation, the ledger index, balance adjustments and the vacation
year's default.

Split out of `test_domain.py` at the ceiling in roadmaps/file-sizes.md;
the shared fakes and factories are `domain_fakes.py`'s.
"""

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from beats.domain.exceptions import (
    AdjustmentBeforeStart,
    AdjustmentOutsideBalance,
    ProjectNotFound,
    UnknownHolidayRegion,
)
from beats.domain.models import (
    Absence,
    AbsenceType,
    AdjustmentKind,
    BalanceAdjustment,
    Beat,
    Contract,
    ContractTerm,
    Project,
    ProjectKind,
    ScheduleType,
)
from beats.domain_fakes import (
    CONTRACT_START,
    _day_job,
    _FakeAbsenceRepo,
    _FakeAdjustmentRepo,
    _FakeBeatRepoForServices,
    _FakeProjectRepoForServices,
    _project,
    _project_service,
)


class TestProjectServiceCrud:
    """ProjectService.create/update/archive/list_projects. Mostly a
    pass-through to ProjectRepository, but archive_project carries
    the load-then-mutate-then-save pattern that needs pinning, and
    the writes are where a contract's holiday region is checked — on
    purpose not in the model, which is re-validated on every read."""

    async def test_create_accepts_a_known_holiday_region(self):
        svc = _project_service()
        created = await svc.create_project(
            _day_job(holiday_country="GB", holiday_subdivision="ENG")
        )
        assert created.contract is not None
        assert created.contract.holiday_subdivision == "ENG"

    @pytest.mark.parametrize(
        ("country", "subdivision"),
        [("XX", None), ("CH", "XX")],
        ids=["unknown country", "unknown subdivision"],
    )
    async def test_create_refuses_an_unknown_holiday_region(self, country, subdivision):
        svc = _project_service()
        with pytest.raises(UnknownHolidayRegion):
            await svc.create_project(
                _day_job(holiday_country=country, holiday_subdivision=subdivision)
            )

    async def test_update_refuses_an_unknown_holiday_region(self):
        stored = _day_job("p1", holiday_country="GB")
        svc = _project_service(projects=[stored])
        with pytest.raises(UnknownHolidayRegion):
            await svc.update_project(
                _day_job("p1", holiday_country="XX"), previous_contract=stored.contract
            )

    async def test_create_round_trips(self):
        svc = _project_service()
        p = _project("p1", "Alpha", weekly_goal=5.0)
        created = await svc.create_project(p)
        assert created.id == "p1"
        listed = await svc.list_projects()
        assert [x.id for x in listed] == ["p1"]

    async def test_update_persists_field_changes(self):
        p = _project("p1", "Alpha", weekly_goal=5.0)
        svc = _project_service(projects=[p])
        renamed = p.model_copy(update={"name": "Alpha 2", "weekly_goal": 10.0})
        result = await svc.update_project(renamed, previous_contract=None)
        assert result.name == "Alpha 2"
        assert result.weekly_goal == 10.0

    async def test_archive_project_sets_archived_true(self):
        """archive_project loads the project, flips archived,
        saves. Pin the load-then-flip-then-save sequence so a
        refactor can't accidentally archive a stale copy."""
        p = _project("p1", "Alpha", weekly_goal=5.0)
        svc = _project_service(projects=[p])
        archived = await svc.archive_project("p1")
        assert archived.archived is True
        # Confirm the archived state is reflected in list filters
        active = await svc.list_projects(archived=False)
        gone = await svc.list_projects(archived=True)
        assert [x.id for x in active] == []
        assert [x.id for x in gone] == ["p1"]

    async def test_archive_raises_on_missing_id(self):
        """archive_project of a non-existent id surfaces the
        ProjectNotFound the repo raises. The API route maps that
        to a 404."""

        svc = _project_service()
        with pytest.raises(ProjectNotFound):
            await svc.archive_project("ghost")

    async def test_list_projects_default_returns_active_only(self):
        """list_projects() defaults archived=False — pin so a
        refactor can't quietly start showing archived projects in
        the UI's main project picker."""
        active = _project("p1", "Active", weekly_goal=5.0)
        archived = _project("p2", "Archived", archived=True)
        svc = _project_service(projects=[active, archived])
        result = await svc.list_projects()
        assert [p.id for p in result] == ["p1"]

    async def test_list_projects_archived_true_returns_archived_only(self):
        """archived=True scopes to the archive view — used by the
        Settings → Archived projects panel."""
        active = _project("p1", "Active", weekly_goal=5.0)
        archived = _project("p2", "Archived", archived=True)
        svc = _project_service(projects=[active, archived])
        result = await svc.list_projects(archived=True)
        assert [p.id for p in result] == ["p2"]


class TestWeekExpectation:
    """`week_expectation` is the one function the week card, the history row
    and the Inbox readers go through. Its null rule reads the week's weekdays
    alone: Saturday and Sunday owe nothing under any term, so a term in force
    on them says nothing about whether the week has an expectation."""

    def test_a_term_starting_on_saturday_leaves_its_week_before_the_contract(self):
        from beats.domain.contracts import week_expectation

        saturday = date(2026, 3, 7)
        term = ContractTerm(
            effective_from=saturday, schedule_type=ScheduleType.FULL_TIME, full_time_hours=40
        )
        contract = Contract(terms=[term])

        # Before the contract — the card says so — not "Expected 0.0 h".
        assert week_expectation(contract, [], set(), date(2026, 3, 2)) is None
        assert week_expectation(contract, [], set(), date(2026, 3, 9)) == 40


class TestContractServiceIndex:
    """`weeks_for` is the project index's read, and holds the one policy the
    HTTP suite cannot reach: `check_region` keeps a region the library
    rejects from ever being written, so only a fake can hold a stored region
    the library has since stopped knowing. That costs the one project its
    contract fields, not the whole list its response."""

    async def test_unknown_region_skips_that_project_only(self):
        from beats.domain.contract_service import ContractService

        known = _day_job("p1")
        unknown = _day_job("p2", holiday_country="XX")
        side = _project("p3", "Side", weekly_goal=5.0)
        service = ContractService(
            project_repo=_FakeProjectRepoForServices([known, unknown, side]),
            beat_repo=_FakeBeatRepoForServices(),
            absence_repo=_FakeAbsenceRepo(),
            adjustment_repo=_FakeAdjustmentRepo(),
        )
        weeks = await service.weeks_for([known, unknown, side], {}, ZoneInfo("UTC"))
        assert set(weeks) == {"p1"}
        assert weeks["p1"].expected == 40


class TestContractServiceLedger:
    """`ledger` is the project page's one read. The assembly is tested on fixed
    dates in `test_ledger.py`; what the service adds is the clock and the read
    plan, and four things about them are worth pinning: today is the request
    timezone's, its current week is the week route's (same beats, same tz,
    same bucketing), the absence window reaches back to the contract's first
    day and forward to the week's end, and one bad contract is that project's
    own error, not skipped as the index does. The clock is handed in, so each
    runs at a fixed instant."""

    ZURICH = ZoneInfo("Europe/Zurich")
    UTC_TZ = ZoneInfo("UTC")

    @staticmethod
    def _service(*, at: datetime, beats=(), absences=(), project=None):
        from beats.domain.contract_service import ContractService

        return ContractService(
            project_repo=_FakeProjectRepoForServices([project or _day_job("p1")]),
            beat_repo=_FakeBeatRepoForServices(list(beats)),
            absence_repo=_FakeAbsenceRepo(list(absences)),
            adjustment_repo=_FakeAdjustmentRepo(),
            now=lambda tz: at.astimezone(tz),
        )

    async def test_today_is_the_request_timezones(self):
        # Sunday 8 March 23:30 UTC is Monday 00:30 in Zürich: the open week
        # is the new one there and still the old one in UTC, on both routes.
        service = self._service(at=datetime(2026, 3, 8, 23, 30, tzinfo=UTC))

        assert (await service.ledger("p1", 1, self.ZURICH)).weeks[0].week_of == date(2026, 3, 9)
        assert (await service.ledger("p1", 1, self.UTC_TZ)).weeks[0].week_of == date(2026, 3, 2)
        assert (await service.week("p1", None, self.ZURICH)).week_of == date(2026, 3, 9)
        assert (await service.week("p1", None, self.UTC_TZ)).week_of == date(2026, 3, 2)

    async def test_current_week_agrees_with_the_week_route_across_midnight(self):
        # A beat at 23:30 UTC on Monday 9 March — 00:30 on the Tuesday in
        # Zürich, running to 01:30. Bucketed whole to the day it started, in
        # the request timezone, on both routes: Tuesday, not Monday.
        started = datetime(2026, 3, 9, 23, 30, tzinfo=UTC)
        beat = Beat(id="b1", project_id="p1", start=started, end=started + timedelta(hours=1))
        service = self._service(at=datetime(2026, 3, 11, 12, tzinfo=UTC), beats=[beat])

        ledger = await service.ledger("p1", 2, self.ZURICH)
        week = await service.week("p1", None, self.ZURICH)

        assert ledger.weeks[0].week_of == week.week_of == date(2026, 3, 9)
        assert ledger.weeks[0].worked == week.worked == 1
        assert ledger.weeks[0].days == [d.worked for d in week.days] == [0, 1, 0, 0, 0, 0, 0]
        assert ledger.totals is not None
        assert ledger.totals.balance == week.balance

    async def test_each_week_figure_is_rounded_from_the_raw_hours(self):
        # 8 h 32 m 42 s is 8.545 h, a half-way hundredth: worked rounds it to
        # 8.54 and remaining rounds 31.455 to 31.45, each on its own, so the
        # two miss 40 by a hundredth. Taking remaining off the rounded 8.54
        # instead would read 31.46, which the page shows as 31.5 h, not 31.4.
        started = datetime(2026, 3, 10, 8, tzinfo=UTC)
        beat = Beat(id="b1", project_id="p1", start=started, end=started + timedelta(seconds=30762))
        service = self._service(at=datetime(2026, 3, 11, 12, tzinfo=UTC), beats=[beat])

        week = await service.week("p1", None, self.UTC_TZ)

        assert (week.expected, week.worked, week.remaining) == (40, 8.54, 31.45)

    async def test_absences_are_read_from_the_contracts_first_day_to_the_weeks_end(self):
        # Read on Thursday 5 March for two weeks. A day off on 12 January is
        # well before the weeks shown but still charges nothing to the
        # balance; one on Friday 6 March is after today but still lowers
        # this week's expectation. Missing either would read as a working day.
        at = datetime(2026, 3, 5, 12, tzinfo=UTC)
        absences = [
            Absence(project_id="p1", date=date(2026, 1, 12), type=AbsenceType.VACATION),
            Absence(project_id="p1", date=date(2026, 3, 6), type=AbsenceType.VACATION),
        ]
        with_absences = await self._service(at=at, absences=absences).ledger("p1", 2, self.UTC_TZ)
        without = await self._service(at=at).ledger("p1", 2, self.UTC_TZ)

        assert with_absences.weeks[0].contract_expected == 32
        assert without.weeks[0].contract_expected == 40
        assert with_absences.totals is not None
        assert without.totals is not None
        assert without.totals.expected == 344  # 8 weeks of 40 and Mon–Wed of this one
        assert with_absences.totals.expected == without.totals.expected - 8

    async def test_unknown_region_is_this_projects_own_error(self):
        service = self._service(
            at=datetime(2026, 3, 5, 12, tzinfo=UTC),
            project=_day_job("p2", holiday_country="XX"),
        )
        with pytest.raises(UnknownHolidayRegion):
            await service.ledger("p2", 1, self.UTC_TZ)

    async def test_it_reads_only_the_sessions_it_can_use(self):
        """The read is bounded at the contract's first day, because that is
        as far back as any figure reaches: every close is built from every
        day since the contract started, and no day before it is in anything.

        Reading every session a project ever had was the API's slowest read
        (#376) — the companion asks for one ledger per project on every timer
        change, so the cost is paid again and again on a project tracked for
        years, for documents in no figure.
        """
        service = self._service(at=datetime(2026, 3, 5, 12, tzinfo=UTC))
        repo = service.beat_repo

        await service.ledger("p1", 8, self.UTC_TZ)

        [(project_id, since)] = repo.ranges_read
        assert project_id == "p1"
        assert since is not None
        # A day before the contract's first, for the timezone: a session is
        # bucketed by its local start day, and a tz behind UTC can pull a UTC
        # instant back onto the day before.
        assert since.date() == CONTRACT_START - timedelta(days=1)

    async def test_the_bound_is_the_oldest_week_when_no_contract_governs(self):
        """On a project with no contract there are no closes, so nothing
        reaches further back than the oldest week shown."""
        side = _project("p3", "Side", weekly_goal=5.0)
        service = self._service(at=datetime(2026, 3, 5, 12, tzinfo=UTC), project=side)

        await service.ledger("p3", 2, self.UTC_TZ)

        [(_, since)] = service.beat_repo.ranges_read
        assert since is not None
        # Monday 2 March is the open week; two weeks reaches 23 February.
        assert since.date() == date(2026, 2, 23) - timedelta(days=1)

    async def test_a_session_before_the_bound_is_in_no_figure(self):
        """The bound is safe because nothing before it counts — pinned
        against the figures, not only against the query."""
        old = datetime(2025, 6, 2, 9, tzinfo=UTC)
        service = self._service(
            at=datetime(2026, 3, 5, 12, tzinfo=UTC),
            beats=[Beat(id="b0", project_id="p1", start=old, end=old + timedelta(hours=8))],
        )
        bare = self._service(at=datetime(2026, 3, 5, 12, tzinfo=UTC))

        with_old = await service.ledger("p1", 8, self.UTC_TZ)
        without = await bare.ledger("p1", 8, self.UTC_TZ)

        assert with_old.totals is not None
        assert without.totals is not None
        assert with_old.totals.worked == without.totals.worked
        assert [w.balance_end for w in with_old.weeks] == [w.balance_end for w in without.weeks]


def _adjustment(day: date, project_id: str = "p1") -> BalanceAdjustment:
    return BalanceAdjustment(
        id=f"a-{day}", project_id=project_id, date=day, kind=AdjustmentKind.DELTA, hours=-8
    )


class TestRecordAdjustment:
    """The date rule is "from the first day through today in the request's
    timezone". The HTTP suite runs on the server's clock, so whose today it
    is can only be pinned here, at a fixed instant: 23:30 UTC on Sunday 8
    March is already Monday 9 March in Berlin."""

    @staticmethod
    def _service(repo: _FakeAdjustmentRepo):
        from beats.domain.contract_service import ContractService

        at = datetime(2026, 3, 8, 23, 30, tzinfo=UTC)
        return ContractService(
            project_repo=_FakeProjectRepoForServices([_day_job("p1")]),
            beat_repo=_FakeBeatRepoForServices(),
            absence_repo=_FakeAbsenceRepo(),
            adjustment_repo=repo,
            now=lambda tz: at.astimezone(tz),
        )

    async def test_today_is_the_request_timezones(self):
        repo = _FakeAdjustmentRepo()
        service = self._service(repo)
        monday = date(2026, 3, 9)

        with pytest.raises(AdjustmentOutsideBalance):
            await service.record_adjustment(_adjustment(monday), ZoneInfo("UTC"))
        await service.record_adjustment(_adjustment(monday), ZoneInfo("Europe/Berlin"))

        assert [a.date for a in await repo.list_by_project("p1", monday, monday)] == [monday]


class TestVacationYearDefault:
    """Which year `/vacation` reads when none is asked for: the current one in
    the request's timezone, pinned at a fixed instant since the HTTP suite
    runs on the server's clock. 23:30 UTC on New Year's Eve is already 2027
    in Zürich."""

    async def test_the_default_year_is_the_request_timezones(self):
        from beats.domain.contract_service import ContractService
        from beats.domain.models import CarryOver, VacationEntitlement

        project = _day_job("p1")
        assert project.contract is not None
        project.contract.vacation = VacationEntitlement(
            days_per_year=25,
            carry_over=CarryOver.ALL,
            opening_on=date(2026, 3, 2),
            opening_days=12,
        )
        at = datetime(2026, 12, 31, 23, 30, tzinfo=UTC)
        service = ContractService(
            project_repo=_FakeProjectRepoForServices([project]),
            beat_repo=_FakeBeatRepoForServices(),
            absence_repo=_FakeAbsenceRepo(),
            adjustment_repo=_FakeAdjustmentRepo(),
            now=lambda tz: at.astimezone(tz),
        )

        assert (await service.vacation("p1", None, ZoneInfo("UTC"))).year == 2026
        assert (await service.vacation("p1", None, ZoneInfo("Europe/Zurich"))).year == 2027


class TestReconcileAdjustments:
    """A contract write against the balance adjustments of the contract it
    replaces. The drawer resends the whole contract on every edit, so the
    one thing this must never do is refuse a write that leaves the first
    day where it was."""

    async def _write(self, stored: Project, new: Contract | None, repo: _FakeAdjustmentRepo):
        svc = _project_service(projects=[stored], adjustments=repo)
        project = stored.model_copy(update={"contract": new})
        return await svc.update_project(project, previous_contract=stored.contract)

    async def test_an_unchanged_contract_never_reads_its_adjustments(self):
        # A rename resends the contract as it is: no adjustment is read or
        # deleted. An orphan dated before the first day (a raw import can
        # leave one) is ignored by the arithmetic, and must not block it.
        stored = _day_job("p1")
        orphan = _adjustment(CONTRACT_START - timedelta(days=30))
        repo = _FakeAdjustmentRepo([orphan])

        await self._write(stored, stored.contract, repo)

        assert repo.calls == []
        assert await repo.earliest("p1", date.min) == orphan.date

    async def test_a_contract_from_none_clears_what_is_left_over(self):
        stored = Project(id="p1", name="Day job", kind=ProjectKind.DAY_JOB)
        repo = _FakeAdjustmentRepo(
            [_adjustment(date(2026, 2, 2)), _adjustment(date(2026, 2, 2), "p2")]
        )

        await self._write(stored, _day_job("p1").contract, repo)

        assert await repo.earliest("p1", date.min) is None
        assert await repo.earliest("p2", date.min) == date(2026, 2, 2)

    async def test_the_contract_going_takes_its_adjustments(self):
        stored = _day_job("p1")
        repo = _FakeAdjustmentRepo([_adjustment(date(2026, 2, 2))])

        saved = await self._write(stored, None, repo)

        assert saved.contract is None
        assert await repo.earliest("p1", date.min) is None

    @pytest.mark.parametrize(
        ("new_start", "refused"),
        [
            (date(2026, 2, 9), True),  # past the adjustment on 2 February
            (date(2026, 2, 2), False),  # onto it: it still counts
            (date(2025, 12, 1), False),  # earlier
        ],
        ids=["later past one", "later onto one", "earlier"],
    )
    async def test_the_first_day_moved_later_past_an_adjustment_is_refused(
        self, new_start, refused
    ):
        stored = _day_job("p1")
        repo = _FakeAdjustmentRepo([_adjustment(date(2026, 2, 2))])
        new = _day_job("p1", starts_on=new_start).contract

        if refused:
            with pytest.raises(AdjustmentBeforeStart):
                await self._write(stored, new, repo)
        else:
            saved = await self._write(stored, new, repo)
            assert saved.contract == new
        assert await repo.earliest("p1", date.min) == date(2026, 2, 2)

    async def test_the_first_day_moved_later_past_none_is_written(self):
        stored = _day_job("p1")
        repo = _FakeAdjustmentRepo([_adjustment(date(2026, 3, 2))])
        new = _day_job("p1", starts_on=date(2026, 2, 2)).contract

        saved = await self._write(stored, new, repo)

        assert saved.contract == new
