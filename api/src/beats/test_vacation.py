"""Tests for the vacation arithmetic — one example per rule, each built from
its arguments. Holidays arrive as a `set[date]`, as they do for the hours:
which days a region keeps is the library's suite, and that a company day is
in the set is `contract_holidays`'s, in `test_contracts.py`.

What the constraints on `VacationEntitlement` refuse is Pydantic's to test;
the one hand-written rule (a cap only with `capped`) and the leaf paths are
pinned over HTTP in `test_api.py`.
"""

from datetime import date

import pytest

from beats.domain.models import (
    Absence,
    AbsenceType,
    CarryOver,
    Contract,
    ContractTerm,
    ScheduleType,
    VacationEntitlement,
)
from beats.domain.vacation import vacation_year

# Monday 2 March 2026, the opening in most cases below.
OPENING = date(2026, 3, 2)


def _entitlement(
    *,
    days: float = 25,
    carry_over: CarryOver = CarryOver.ALL,
    cap: float | None = None,
    opening_on: date = OPENING,
    opening_days: float = 12,
) -> VacationEntitlement:
    return VacationEntitlement(
        days_per_year=days,
        carry_over=carry_over,
        carry_over_max_days=cap,
        opening_on=opening_on,
        opening_days=opening_days,
    )


def _contract(
    entitlement: VacationEntitlement,
    *,
    starts_on: date = date(2026, 1, 5),
    ended_on: date | None = None,
    schedule: ScheduleType = ScheduleType.FULL_TIME,
) -> Contract:
    hours = {"full_time_hours": 40} if schedule is ScheduleType.FULL_TIME else {}
    term = ContractTerm(effective_from=starts_on, schedule_type=schedule, **hours)
    return Contract(terms=[term], ended_on=ended_on, vacation=entitlement)


def _off(day: date, kind: AbsenceType = AbsenceType.VACATION, *, half: bool = False) -> Absence:
    return Absence(project_id="p1", date=day, type=kind, half_day=half)


def _weekdays_off(start: date, count: int) -> list[Absence]:
    """`count` days off in a row from `start` — weekdays only, given a Monday
    and at most five."""
    return [_off(date.fromordinal(start.toordinal() + n)) for n in range(count)]


class TestTheOpening:
    def test_a_contract_started_years_back_counts_from_the_opening_only(self):
        # Every contract the startup migration made starts at the project's
        # first beat, possibly years ago. Nothing before the opening is
        # reconstructed: no years of unrecorded leave credited, no day off
        # before it charged, and the opening year is the opening alone.
        contract = _contract(_entitlement(), starts_on=date(2020, 1, 6))
        absences = [
            _off(date(2025, 6, 2)),  # a year before the opening's
            _off(date(2026, 2, 16)),  # the opening's year, before the opening
            _off(date(2026, 3, 10)),  # after it: this one costs a day
        ]

        year = vacation_year(contract, absences, set(), 2026)

        assert (year.accrued, year.carried_in, year.available) == (None, 0, 12)
        assert (year.booked, year.remaining) == (1, 11)
        with pytest.raises(ValueError, match="outside"):
            vacation_year(contract, absences, set(), 2025)

    def test_the_year_after_the_opening_is_a_full_year_plus_the_carry(self):
        contract = _contract(_entitlement())
        absences = [*_weekdays_off(date(2026, 8, 3), 2), *_weekdays_off(date(2027, 8, 2), 3)]

        year = vacation_year(contract, absences, set(), 2027)

        assert (year.accrued, year.carried_in, year.available) == (25, 10, 35)
        assert (year.booked, year.remaining) == (3, 32)

    def test_a_negative_opening_carries_as_a_deficit(self):
        contract = _contract(_entitlement(opening_days=-2.5))

        year = vacation_year(contract, [], set(), 2027)

        assert (year.carried_in, year.available, year.remaining) == (-2.5, 22.5, 22.5)


class TestTheEndYear:
    def test_the_year_of_ended_on_is_pro_rated_by_calendar_days(self):
        # 2028 is a leap year: 274 of 366 days of 25 is 18.72, so 18.5. Over
        # 365 it would have been 18.77, and 19.
        contract = _contract(_entitlement(), ended_on=date(2028, 9, 30))

        assert vacation_year(contract, [], set(), 2028).accrued == 18.5
        assert vacation_year(contract, [], set(), 2027).accrued == 25
        with pytest.raises(ValueError, match="outside"):
            vacation_year(contract, [], set(), 2029)

    def test_a_quarter_day_rounds_up_to_the_half(self):
        # 30.5 days × 15 / 366 is exactly 1.25: half up gives 1.5, where
        # banker's rounding would give 1.
        contract = _contract(
            _entitlement(days=30.5, opening_on=date(2027, 1, 4)),
            starts_on=date(2027, 1, 4),
            ended_on=date(2028, 1, 15),
        )

        assert vacation_year(contract, [], set(), 2028).accrued == 1.5

    def test_the_opening_year_is_taken_as_typed_even_when_the_job_ends_in_it(self):
        contract = _contract(_entitlement(), ended_on=date(2026, 6, 30))

        year = vacation_year(contract, [_off(date(2026, 7, 1))], set(), 2026)

        assert (year.accrued, year.available, year.booked) == (None, 12, 0)


class TestWhatCostsADay:
    def test_only_a_vacation_on_a_counted_weekday_costs_leave(self):
        wednesday = date(2026, 3, 4)
        contract = _contract(_entitlement(), ended_on=date(2026, 12, 18))
        absences = [
            _off(date(2026, 3, 3)),  # a Tuesday: 1
            _off(date(2026, 3, 5), half=True),  # a half day: ½
            _off(wednesday),  # a holiday of the contract: 0
            _off(date(2026, 3, 7)),  # a Saturday: 0
            _off(date(2026, 3, 9), AbsenceType.SICK),  # sick: 0
            _off(date(2026, 3, 10), AbsenceType.OTHER),  # other: 0
            _off(date(2026, 12, 21)),  # after ended_on: 0
        ]

        year = vacation_year(contract, absences, {wednesday}, 2026)

        assert year.booked == 1.5

    def test_a_day_under_an_objective_term_still_costs_one(self):
        # The term owes no hours, so expected_on would read the day as free;
        # but leave is part of the job, not of its schedule.
        contract = _contract(_entitlement(), schedule=ScheduleType.OBJECTIVE)

        assert vacation_year(contract, [_off(date(2026, 3, 3))], set(), 2026).booked == 1


class TestCarryOver:
    @pytest.mark.parametrize(
        ("carry_over", "cap", "carried"),
        [(CarryOver.ALL, None, 10), (CarryOver.CAPPED, 5, 5), (CarryOver.NONE, None, 0)],
        ids=["all", "capped", "none"],
    )
    def test_what_is_left_carries_by_the_rule(self, carry_over, cap, carried):
        contract = _contract(_entitlement(carry_over=carry_over, cap=cap))
        absences = _weekdays_off(date(2026, 8, 3), 2)  # 12 - 2 = 10 left

        assert vacation_year(contract, absences, set(), 2027).carried_in == carried

    def test_a_deficit_carries_whole_even_where_unused_days_lapse(self):
        # The rule limits what is kept, not what is owed.
        contract = _contract(_entitlement(carry_over=CarryOver.NONE, opening_days=2))
        absences = [*_weekdays_off(date(2026, 8, 3), 5), _off(date(2026, 8, 10), half=True)]

        year = vacation_year(contract, absences, set(), 2027)

        assert year.carried_in == -3.5
        assert year.available == 21.5

    def test_the_chain_runs_through_every_year_between(self):
        # 2026 leaves 12, capped to 5; 2027 books 28 of 30 and leaves 2; 2028
        # starts from 25 + 2.
        contract = _contract(_entitlement(carry_over=CarryOver.CAPPED, cap=5))
        absences = [
            _off(date.fromordinal(date(2027, 1, 4).toordinal() + 7 * week + day))
            for week in range(6)
            for day in range(5)
        ][:28]

        year = vacation_year(contract, absences, set(), 2028)

        assert (year.carried_in, year.available) == (2, 27)
