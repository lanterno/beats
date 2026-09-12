"""Tests for the contract arithmetic — the interesting inputs only.

Holidays arrive as a `set[date]`, so no test here asserts that a region *has*
a holiday; that is the library's suite. Two tests go through
`holidays_between` all the same. One is for range logic that is ours: a week
spanning New Year must consult both years' calendars. The other is there
because the arithmetic leans on the library's observed-day behaviour — a
substitute Monday comes back as an ordinary holiday, and being a weekday it
costs its day — and that dependency should be visible from the suite.

The region check is not here: it runs where a contract is written, so it is
tested with `ProjectService` in `test_domain.py`.
"""

import os
from datetime import date, timedelta

import pytest
from pymongo import AsyncMongoClient

from beats.domain.contracts import balance, expected_hours, term_on
from beats.domain.holidays import holidays_between
from beats.domain.models import (
    Absence,
    AbsenceType,
    Contract,
    ContractTerm,
    ScheduleType,
)
from beats.infrastructure.repositories import MongoAbsenceRepository

# A week with nothing special about it. Monday 2 March 2026 through Friday 6 March.
MON = date(2026, 3, 2)
TUE, WED, THU, FRI, SAT, SUN = (MON + timedelta(days=n) for n in range(1, 7))
LONG_AGO = date(2020, 1, 1)


def _term(
    effective_from: date,
    schedule: ScheduleType,
    *,
    full_time_hours: float | None = None,
    percentage: float | None = None,
    weekly_hours: float | None = None,
) -> ContractTerm:
    return ContractTerm(
        effective_from=effective_from,
        schedule_type=schedule,
        full_time_hours=full_time_hours,
        percentage=percentage,
        weekly_hours=weekly_hours,
    )


def _full_time(effective_from: date = LONG_AGO, hours: float = 40) -> ContractTerm:
    return _term(effective_from, ScheduleType.FULL_TIME, full_time_hours=hours)


def _contract(*terms: ContractTerm, **fields) -> Contract:
    return Contract(terms=list(terms) or [_full_time()], **fields)


def _absence(day: date, *, half_day: bool = False) -> Absence:
    return Absence(project_id="p1", date=day, type=AbsenceType.VACATION, half_day=half_day)


def _week(contract: Contract, *, holidays: set[date] | None = None, absences=()) -> float:
    return expected_hours(contract, absences, holidays or set(), MON, SUN)


class TestContractTermHours:
    def test_percentage_applies_to_its_basis(self):
        term = _term(LONG_AGO, ScheduleType.PART_TIME, full_time_hours=42, percentage=0.8)
        assert term.hours_per_week == pytest.approx(33.6)
        assert term.hours_per_day == pytest.approx(6.72)


class TestExpectedHours:
    def test_holiday_on_a_saturday_costs_nothing(self):
        assert _week(_contract(), holidays={SAT}) == 40

    def test_holiday_on_a_weekday_costs_its_day(self):
        assert _week(_contract(), holidays={WED}) == 32

    def test_substitute_weekday_for_a_sunday_holiday_costs_its_day(self):
        # New Year's Day 2023 was a Sunday; the library observes it in GB on
        # Monday 2 January, and a Monday costs its day.
        monday = date(2023, 1, 2)
        holidays = holidays_between("GB", None, monday, monday + timedelta(days=6))
        expected = expected_hours(_contract(), [], holidays, monday, monday + timedelta(days=6))
        assert expected == 32

    def test_half_day_costs_half_the_day(self):
        assert _week(_contract(), absences=[_absence(WED, half_day=True)]) == 36

    def test_half_day_on_a_holiday_charges_nothing_back(self):
        # The holiday already zeroed the day; an absence on it must not
        # re-introduce base / 2.
        week = _week(_contract(), holidays={WED}, absences=[_absence(WED, half_day=True)])
        assert week == 32

    @pytest.mark.parametrize("half_day_first", [True, False])
    def test_two_absences_on_one_day_are_one_and_the_full_day_wins(self, half_day_first):
        absences = [_absence(WED, half_day=True), _absence(WED)]
        if not half_day_first:
            absences.reverse()
        assert _week(_contract(), absences=absences) == 32

    def test_terms_changing_on_a_wednesday_split_the_week(self):
        contract = _contract(
            _full_time(),
            _term(WED, ScheduleType.PART_TIME, full_time_hours=42, percentage=0.5),
        )
        # Mon-Tue at 8 h, Wed-Fri at 4.2 h.
        assert _week(contract) == pytest.approx(16 + 3 * 4.2)
        assert term_on(contract, TUE) is contract.terms[0]
        assert term_on(contract, WED) is contract.terms[1]

    def test_contract_starting_on_a_thursday(self):
        assert _week(_contract(_full_time(THU))) == 16
        assert term_on(_contract(_full_time(THU)), WED) is None

    def test_ended_on_midweek_owes_nothing_after(self):
        assert _week(_contract(ended_on=TUE)) == 16

    def test_objective_term_contributes_zero(self):
        contract = _contract(_full_time(), _term(WED, ScheduleType.OBJECTIVE))
        assert _week(contract) == 16
        # No expectation at all, as distinct from an expectation of nought:
        # the week card shows nothing rather than 0 h.
        assert contract.terms[1].hours_per_week is None


class TestHolidaysBetween:
    def test_range_spans_years_and_includes_both_ends(self):
        # Christmas 2025 sits on the start bound, New Year 2026 on the end
        # bound, and the two are in different years: one calendar per year,
        # both bounds inclusive.
        found = holidays_between("GB", None, date(2025, 12, 25), date(2026, 1, 1))
        assert found == {date(2025, 12, 25), date(2025, 12, 26), date(2026, 1, 1)}


class TestBalance:
    def test_excludes_today_expectation_and_includes_today_work(self):
        contract = _contract(_full_time(MON), opening_balance_hours=10)
        worked = {MON: 8.0, TUE: 8.0, WED: 3.0}
        # Opening 10, worked 19 including Wednesday's 3, expected Mon-Tue only.
        assert balance(contract, [], set(), worked, today=WED) == 10 + 19 - 16

    def test_ended_on_freezes_both_sides(self):
        contract = _contract(_full_time(MON), ended_on=TUE)
        worked = {MON: 8.0, TUE: 8.0, WED: 5.0}
        # Wednesday's 5 h neither count as overtime nor were expected.
        assert balance(contract, [], set(), worked, today=FRI) == 0


class TestContractValidation:
    @pytest.mark.parametrize("second", [WED, MON], ids=["same day", "earlier"])
    def test_terms_must_strictly_ascend(self, second):
        with pytest.raises(ValueError, match="ascending"):
            _contract(_full_time(WED), _full_time(second))

    def test_no_terms_rejected(self):
        with pytest.raises(ValueError, match="at least one term"):
            Contract(terms=[])

    def test_ended_on_before_the_first_term_rejected(self):
        with pytest.raises(ValueError, match="ended_on"):
            _contract(_full_time(WED), ended_on=MON)

    @pytest.mark.parametrize("percentage", [0, 1.2])
    def test_percentage_outside_unit_interval_rejected(self, percentage):
        with pytest.raises(ValueError, match=r"\(0, 1\]"):
            _term(MON, ScheduleType.PART_TIME, full_time_hours=40, percentage=percentage)

    def test_full_time_below_hundred_percent_rejected(self):
        with pytest.raises(ValueError, match="full_time term is 100%"):
            _term(MON, ScheduleType.FULL_TIME, full_time_hours=40, percentage=0.8)

    def test_part_time_at_hundred_percent_rejected(self):
        with pytest.raises(ValueError, match="use full_time"):
            _term(MON, ScheduleType.PART_TIME, full_time_hours=40, percentage=1.0)

    def test_objective_with_hours_rejected(self):
        with pytest.raises(ValueError, match="carries no hours"):
            _term(MON, ScheduleType.OBJECTIVE, weekly_hours=40)

    def test_custom_without_hours_rejected(self):
        with pytest.raises(ValueError, match="weekly_hours"):
            _term(MON, ScheduleType.CUSTOM)

    def test_subdivision_without_country_rejected(self):
        with pytest.raises(ValueError, match="holiday_country"):
            _contract(holiday_subdivision="ZH")


class TestMongoAbsenceRepository:
    """One round trip, for what the pure tests cannot see: the upsert key is
    the serialised date, so a second absence on a day replaces the first."""

    async def test_upsert_replaces_on_date(self):
        client = AsyncMongoClient(os.environ.get("DB_DSN", "mongodb://localhost:27017"))
        try:
            collection = client[os.environ.get("DB_NAME", "beats_test")].absences
            repo = MongoAbsenceRepository(collection, user_id="user-1")

            first = await repo.upsert(
                Absence(
                    project_id="p1", date=WED, type=AbsenceType.VACATION, half_day=True, note="x"
                )
            )
            second = await repo.upsert(Absence(project_id="p1", date=WED, type=AbsenceType.SICK))

            assert second.id == first.id
            listed = await repo.list_by_project("p1", MON, SUN)
            assert [(a.type, a.half_day, a.note) for a in listed] == [
                (AbsenceType.SICK, False, None)
            ]
            assert await repo.list_by_project("p1", THU, SUN) == []

            assert first.id is not None
            assert await repo.delete(first.id) is True
            assert await repo.list_by_project("p1", MON, SUN) == []
        finally:
            await client.close()
