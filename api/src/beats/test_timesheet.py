"""Tests for the monthly timesheet, on fixed dates.

One fixture carries most of them, read on Thursday 16 April 2026: a full-time
contract (8 h a day) from Wednesday 14 January, 80 % of it (6.4 h a day)
from Wednesday 11 February, 2 h brought in. 7.5 h every weekday worked, bar
a week's vacation in March and two Easter holidays; 1.5 h on Saturday
7 February; a half day off on Friday 20 March; a 10 h payout on Tuesday
31 March. So January starts mid-month, February changes term mid-month and
has weekend work, March has the vacation, the half day and the payout, and
April is cut short at yesterday. The months, worked out by hand:

    month  brought  expected  worked  difference  adjusted  carried
    Jan      2.0     104.0     97.5     −6.5        0       −4.5
    Feb     −4.5     139.2    151.5     12.3        0        7.8
    Mar      7.8     105.6    127.5     21.9      −10       19.7
    Apr     19.7      57.6     67.5      9.9        0       29.6
"""

from datetime import date, timedelta
from itertools import pairwise

import pytest

from beats.domain.models import (
    Absence,
    AbsenceType,
    AdjustmentKind,
    BalanceAdjustment,
    Contract,
    ContractTerm,
    ScheduleType,
)
from beats.domain.timesheet import assemble_timesheet, timesheet_range

TODAY = date(2026, 4, 16)  # a Thursday
FIRST_TERM = date(2026, 1, 14)  # full time, 40 h: 8 h a day
SECOND_TERM = date(2026, 2, 11)  # 80 %: 6.4 h a day
VACATION = date(2026, 3, 9)  # Mon–Fri off
HALF_DAY = date(2026, 3, 20)  # a Friday
PAYOUT = date(2026, 3, 31)  # a Tuesday
GOOD_FRIDAY, HOLY_SATURDAY, EASTER_MONDAY = date(2026, 4, 3), date(2026, 4, 4), date(2026, 4, 6)
SATURDAY_WORKED = date(2026, 2, 7)
OPENING = 2.0

HOLIDAYS = {
    GOOD_FRIDAY: "Good Friday",
    HOLY_SATURDAY: "Holy Saturday",
    EASTER_MONDAY: "Easter Monday",
}


def _full_time(effective_from: date = FIRST_TERM) -> ContractTerm:
    return ContractTerm(
        effective_from=effective_from, schedule_type=ScheduleType.FULL_TIME, full_time_hours=40
    )


def _part_time(effective_from: date = SECOND_TERM) -> ContractTerm:
    return ContractTerm(
        effective_from=effective_from,
        schedule_type=ScheduleType.PART_TIME,
        full_time_hours=40,
        percentage=0.8,
    )


def _objective(effective_from: date) -> ContractTerm:
    return ContractTerm(effective_from=effective_from, schedule_type=ScheduleType.OBJECTIVE)


def _contract(*terms: ContractTerm, **fields) -> Contract:
    return Contract(
        terms=list(terms) or [_full_time(), _part_time()],
        opening_balance_hours=OPENING,
        **fields,
    )


def _vacation_week() -> set[date]:
    return {VACATION + timedelta(days=n) for n in range(5)}


def _worked() -> dict[date, float]:
    hours: dict[date, float] = {SATURDAY_WORKED: 1.5}
    day = FIRST_TERM
    while day < TODAY:
        if day.weekday() < 5 and day not in _vacation_week() and day not in HOLIDAYS:
            hours[day] = 7.5
        day += timedelta(days=1)
    return hours


def _absences() -> list[Absence]:
    days = [
        Absence(project_id="p1", date=day, type=AbsenceType.VACATION)
        for day in sorted(_vacation_week())
    ]
    days.append(Absence(project_id="p1", date=HALF_DAY, type=AbsenceType.OTHER, half_day=True))
    # Booked on a public holiday: the holiday already gave the day.
    days.append(Absence(project_id="p1", date=EASTER_MONDAY, type=AbsenceType.VACATION))
    return days


def _payout() -> list[BalanceAdjustment]:
    return [
        BalanceAdjustment(
            id="a1", project_id="p1", date=PAYOUT, kind=AdjustmentKind.DELTA, hours=-10
        )
    ]


def _sheet(
    month: date,
    contract: Contract | None = None,
    *,
    absences=None,
    worked=None,
    adjustments=None,
    today: date = TODAY,
):
    contract = contract or _contract()
    span = timesheet_range(contract, month, today)
    assert span is not None
    return assemble_timesheet(
        contract,
        _absences() if absences is None else absences,
        HOLIDAYS,
        _worked() if worked is None else worked,
        _payout() if adjustments is None else adjustments,
        *span,
    )


def _months(contract: Contract | None = None, **kwargs):
    return [_sheet(date(2026, m, 1), contract, **kwargs) for m in (1, 2, 3, 4)]


def _row(sheet, day: date):
    return next(row for row in sheet.days if row.date == day)


class TestTimesheetRange:
    def test_the_first_sheet_starts_on_the_first_term(self):
        assert timesheet_range(_contract(), date(2026, 1, 1), TODAY) == (
            FIRST_TERM,
            date(2026, 1, 31),
        )

    def test_ended_on_stops_the_sheet(self):
        contract = _contract(ended_on=date(2026, 3, 18))
        assert timesheet_range(contract, date(2026, 3, 1), TODAY) == (
            date(2026, 3, 1),
            date(2026, 3, 18),
        )

    def test_the_current_month_runs_through_yesterday(self):
        assert timesheet_range(_contract(), date(2026, 4, 1), TODAY) == (
            date(2026, 4, 1),
            date(2026, 4, 15),
        )

    @pytest.mark.parametrize(
        ("month", "today", "ended_on"),
        [
            (date(2026, 4, 1), date(2026, 4, 1), None),  # the current month on its 1st
            (date(2026, 5, 1), TODAY, None),  # still to come
            (date(9999, 12, 1), TODAY, None),  # the calendar's last month, no overflow
            (date(2025, 12, 1), TODAY, None),  # wholly before the first term
            (date(2026, 4, 1), TODAY, date(2026, 3, 18)),  # wholly after the end
        ],
    )
    def test_a_month_without_a_finished_day_in_the_contract_has_no_sheet(
        self, month, today, ended_on
    ):
        assert timesheet_range(_contract(ended_on=ended_on), month, today) is None

    def test_february_of_a_leap_year_ends_on_the_29th(self):
        contract = _contract(_full_time(date(2028, 1, 3)))
        assert timesheet_range(contract, date(2028, 2, 1), date(2028, 6, 1)) == (
            date(2028, 2, 1),
            date(2028, 2, 29),
        )


class TestTimesheetMonths:
    def test_the_months_by_hand(self):
        figures = [
            (s.brought_forward, s.expected, s.worked, s.difference, s.adjusted, s.carried_forward)
            for s in _months()
        ]
        assert figures == [
            (2.0, 104.0, 97.5, -6.5, 0, -4.5),
            (-4.5, 139.2, 151.5, 12.3, 0, 7.8),
            (7.8, 105.6, 127.5, 21.9, -10, 19.7),
            (19.7, 57.6, 67.5, 9.9, 0, 29.6),
        ]

    def test_the_first_sheet_brings_forward_the_opening_balance(self):
        january = _sheet(date(2026, 1, 1))
        assert january.brought_forward == OPENING
        assert january.days[0].date == FIRST_TERM

    def test_each_month_carries_forward_what_the_next_brings_forward(self):
        # Across the term change, the vacation month and the payout.
        for month, following in pairwise(_months()):
            assert month.carried_forward == following.brought_forward

    def test_brought_forward_plus_the_month_is_carried_forward(self):
        # The proof a reader does on the total row, adjustments included.
        for sheet in _months():
            assert sheet.brought_forward is not None
            assert sheet.carried_forward is not None
            assert sheet.expected is not None
            assert (
                sheet.brought_forward + sheet.worked - sheet.expected + sheet.adjusted
                == pytest.approx(sheet.carried_forward, abs=0.025)
            )

    def test_each_row_moves_the_balance_by_its_difference_and_its_adjustment(self):
        for sheet in _months():
            closes = [sheet.brought_forward, *(row.balance_end for row in sheet.days)]
            for (before, after), row in zip(pairwise(closes), sheet.days, strict=True):
                assert before is not None
                assert after is not None
                assert row.difference is not None
                assert after - before == pytest.approx(
                    row.difference + (row.adjusted or 0), abs=0.025
                )

    def test_carried_forward_is_the_last_rows_balance(self):
        for sheet in _months():
            assert sheet.carried_forward == sheet.days[-1].balance_end

    def test_one_row_per_finished_day(self):
        april = _sheet(date(2026, 4, 1))
        assert [row.date for row in april.days] == [
            date(2026, 4, 1) + timedelta(days=n) for n in range(15)
        ]
        assert (april.first, april.last, april.month) == (
            date(2026, 4, 1),
            date(2026, 4, 15),
            date(2026, 4, 1),
        )


class TestTimesheetDays:
    def test_a_term_change_mid_month_charges_each_side_its_own_day(self):
        february = _sheet(date(2026, 2, 1))
        assert _row(february, SECOND_TERM - timedelta(days=1)).expected == 8
        assert _row(february, SECOND_TERM).expected == 6.4

    def test_weekend_work_is_a_row_with_nothing_expected(self):
        saturday = _row(_sheet(date(2026, 2, 1)), SATURDAY_WORKED)
        assert (saturday.expected, saturday.worked, saturday.difference) == (0, 1.5, 1.5)

    def test_a_holiday_on_a_weekday_is_named_and_counted(self):
        april = _sheet(date(2026, 4, 1))
        good_friday = _row(april, GOOD_FRIDAY)
        assert (good_friday.holiday, good_friday.expected) == ("Good Friday", 0)
        assert april.holidays == 2

    def test_a_holiday_on_a_saturday_is_neither_named_nor_counted(self):
        assert _row(_sheet(date(2026, 4, 1)), HOLY_SATURDAY).holiday is None

    def test_a_vacation_on_a_public_holiday_is_shown_but_not_counted(self):
        april = _sheet(date(2026, 4, 1))
        monday = _row(april, EASTER_MONDAY)
        assert (monday.holiday, monday.absence) == ("Easter Monday", AbsenceType.VACATION)
        assert april.absence_days == 0

    def test_a_half_day_counts_half_and_expects_half(self):
        march = _sheet(date(2026, 3, 1))
        half = _row(march, HALF_DAY)
        assert (half.absence, half.half_day, half.expected) == (AbsenceType.OTHER, True, 3.2)
        assert march.absence_days == 5.5
        assert _row(march, VACATION).half_day is False

    def test_the_payout_is_its_days_adjustment_and_moves_that_days_balance(self):
        march = _sheet(date(2026, 3, 1))
        before, payout = _row(march, PAYOUT - timedelta(days=1)), _row(march, PAYOUT)
        assert (payout.adjustment, payout.adjusted) == (AdjustmentKind.DELTA, -10)
        assert (before.balance_end, payout.balance_end) == (28.6, 19.7)
        assert (before.adjustment, before.adjusted) == (None, None)

    def test_a_reset_on_the_first_is_the_months_and_not_brought_forward(self):
        # A reset takes effect as its day starts, against the close of the
        # day before: April brings forward March's close, and moves from it.
        reset = BalanceAdjustment(
            project_id="p1", date=date(2026, 4, 1), kind=AdjustmentKind.RESET, hours=0
        )
        april = _sheet(date(2026, 4, 1), adjustments=[*_payout(), reset])
        assert april.brought_forward == 19.7
        assert (april.days[0].adjustment, april.days[0].adjusted) == (AdjustmentKind.RESET, -19.7)
        assert (april.adjusted, april.carried_forward) == (-19.7, 9.9)


class TestTimesheetNullRule:
    def test_an_objective_stretch_inside_the_month_expects_nothing_and_its_hours_count(self):
        # Objective from Monday 9 March to Sunday 22 March: those days have no
        # expectation and no balance, but both ends of the month do, and the
        # hours worked in between move the balance as they do on the ledger.
        contract = _contract(
            _full_time(), _objective(date(2026, 3, 9)), _part_time(date(2026, 3, 23))
        )
        march = _sheet(date(2026, 3, 1), contract, absences=[], adjustments=[])
        objective = _row(march, date(2026, 3, 16))
        assert (objective.expected, objective.difference, objective.balance_end) == (
            None,
            None,
            None,
        )
        assert objective.worked == 7.5
        assert march.brought_forward is not None
        assert march.carried_forward is not None
        assert march.expected is not None
        assert march.brought_forward + march.worked - march.expected == pytest.approx(
            march.carried_forward, abs=0.025
        )
        # 5 days at 8 h, then 7 at 6.4 h; the objective weekdays expect nothing.
        assert march.expected == pytest.approx(5 * 8 + 7 * 6.4)

    def test_a_month_starting_inside_an_objective_stretch_brings_nothing_forward(self):
        contract = _contract(
            _full_time(), _objective(date(2026, 2, 16)), _full_time(date(2026, 3, 16))
        )
        march = _sheet(date(2026, 3, 1), contract, absences=[], adjustments=[])
        assert march.brought_forward is None
        assert _row(march, date(2026, 3, 13)).expected is None
        assert _row(march, date(2026, 3, 13)).balance_end is None
        assert _row(march, date(2026, 3, 16)).expected == 8
        assert march.carried_forward is not None

    def test_a_month_wholly_objective_has_no_expected_total(self):
        contract = _contract(_full_time(), _objective(date(2026, 2, 16)))
        march = _sheet(date(2026, 3, 1), contract, absences=[], adjustments=[])
        assert (march.brought_forward, march.expected, march.difference) == (None, None, None)
        assert march.carried_forward is None
        assert march.worked == 22 * 7.5 - 5 * 7.5  # the vacation week was not worked
