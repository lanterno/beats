"""Tests for the billing budget arithmetic, on fixed dates.

They reuse `test_billing.py`'s Studio Kite, billed in euros at 85.00/h from
1 January through Website, and mostly read Sunday 18 October 2026 in Berlin.
Berlin leaves summer time a week later, on Sunday 25 October.
"""

from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError

from beats.domain.billing import assemble_client
from beats.domain.billing_budgets import (
    BillingBudgetState,
    billing_budget_state,
    billing_budget_status,
    percent_used,
    runs_out_on,
)
from beats.domain.models import (
    Beat,
    BillingBudget,
    BillingBudgetFields,
    BillingBudgetPeriod,
    BillingBudgetScope,
    BillingBudgetUnit,
    Client,
    ProjectBilling,
)
from beats.test_billing import (
    BERLIN,
    JAN_1,
    OCT_1,
    OCT_31,
    _beat,
    _billing,
    _client,
    _hours,
    _project,
    _term,
)

OCT_18 = date(2026, 10, 18)
NOV_1 = date(2026, 11, 1)
HOURS, MONEY = BillingBudgetUnit.HOURS, BillingBudgetUnit.MONEY
MONTHLY, TOTAL = BillingBudgetPeriod.MONTHLY, BillingBudgetPeriod.TOTAL
UNDER, NEAR, USED_UP = BillingBudgetState.UNDER, BillingBudgetState.NEAR, BillingBudgetState.USED_UP
PROJECTS = {"p1": _project(), "p2": _project("p2", "Shop")}


def _budget(
    unit: BillingBudgetUnit,
    limit: str | int,
    *,
    period: BillingBudgetPeriod = MONTHLY,
    starts_on: date | None = None,
    warn: int = 80,
    scope: BillingBudgetScope = BillingBudgetScope.CLIENT,
    scope_id: str = "c1",
) -> BillingBudget:
    return BillingBudget(
        scope=scope,
        scope_id=scope_id,
        unit=unit,
        period=period,
        limit_hours=Decimal(limit) if unit is HOURS else None,
        limit_minor=int(limit) if unit is MONEY else None,
        starts_on=starts_on,
        warn_at_percent=warn,
    )


def _status(
    budget: BillingBudget,
    beats: list[Beat],
    *,
    today: date = OCT_18,
    client: Client | None = None,
    billings: list[ProjectBilling] | None = None,
    overrides: dict[str | None, bool] | None = None,
    active: bool = True,
):
    if billings is None:
        billings = [_billing(_term(JAN_1))]
    if budget.scope is BillingBudgetScope.PROJECT:
        billings = [billing for billing in billings if billing.project_id == budget.scope_id]
    marks = {beat_id: mark for beat_id, mark in (overrides or {}).items() if beat_id is not None}
    return billing_budget_status(
        budget,
        client or _client((JAN_1, 8500)),
        billings,
        PROJECTS,
        beats,
        marks,
        today,
        BERLIN,
        active,
    )


def _daily(first: date, last: date, length: timedelta, **fields) -> list[Beat]:
    """One beat a day, `first` through `last`."""
    return [
        _beat(first + timedelta(days=n), length, **fields) for n in range((last - first).days + 1)
    ]


def _running(day: date, at: time, **fields) -> Beat:
    return _beat(day, None, at=at, **fields)


class TestSpend:
    def test_a_total_sums_whole_months_as_the_invoices_rounded_them(self):
        # 1 h 0 m 18 s is 1.005 h: 1.01 h in each month's line, 2.02 h in
        # all — where one line over both days would round once, to 2.01 h.
        beats = [
            _beat(OCT_31, timedelta(hours=1, seconds=18)),
            _beat(NOV_1, timedelta(hours=1, seconds=18)),
        ]
        status = _status(
            _budget(MONEY, 100000, period=TOTAL, starts_on=OCT_1), beats, today=date(2026, 11, 5)
        )
        assert (status.billable_hours, status.amount_minor) == (Decimal("2.02"), 17170)
        one_range = assemble_client(
            _client((JAN_1, 8500)),
            [_billing(_term(JAN_1))],
            PROJECTS,
            beats,
            {},
            OCT_1,
            date(2026, 11, 5),
            BERLIN,
        )
        assert (one_range.billable_hours, one_range.amount_minor) == (Decimal("2.01"), 17085)

    def test_a_monthly_reading_is_the_month_to_date_report(self):
        client = _client((JAN_1, 8500), (date(2026, 10, 12), 9000))
        billings = [_billing(_term(JAN_1))]
        beats = [
            _beat(date(2026, 9, 30), _hours(4)),
            *_daily(OCT_1, OCT_18, timedelta(hours=1, minutes=7)),
        ]
        status = _status(_budget(HOURS, "40"), beats, client=client, billings=billings)
        report = assemble_client(client, billings, PROJECTS, beats, {}, OCT_1, OCT_18, BERLIN)
        assert (status.first, status.last, status.through) == (OCT_1, OCT_31, OCT_18)
        assert (status.billable_hours, status.amount_minor) == (
            report.billable_hours,
            report.amount_minor,
        )

    def test_a_project_scope_counts_its_project_and_a_client_scope_all_of_them(self):
        billings = [
            _billing(_term(JAN_1, rate=9500)),
            _billing(_term(JAN_1), project_id="p2"),
        ]
        beats = [
            _beat(date(2026, 10, 5), _hours(2)),
            _beat(date(2026, 10, 6), _hours(3), project_id="p2"),
        ]
        client = _status(_budget(MONEY, 100000), beats, billings=billings)
        website = _status(
            _budget(MONEY, 100000, scope=BillingBudgetScope.PROJECT, scope_id="p1"),
            beats,
            billings=billings,
        )
        assert (client.name, client.billable_hours, client.amount_minor) == (
            "Studio Kite",
            Decimal("5.00"),
            19000 + 25500,
        )
        assert (website.name, website.billable_hours, website.amount_minor) == (
            "Website",
            Decimal("2.00"),
            19000,
        )

    def test_overrides_decide_an_entry_either_way(self):
        # Billable from the 10th: an entry marked billable before it counts
        # at the client's rate, one marked not billable after it does not.
        early, late = _beat(date(2026, 10, 5), _hours(2)), _beat(date(2026, 10, 12), _hours(3))
        status = _status(
            _budget(HOURS, "40"),
            [early, late],
            billings=[_billing(_term(date(2026, 10, 10)))],
            overrides={early.id: True, late.id: False},
        )
        assert (status.billable_hours, status.amount_minor) == (Decimal("2.00"), 17000)

    def test_a_beat_started_at_23_30_on_the_31st_is_octobers(self):
        beats = [_beat(OCT_31, _hours(1), at=time(23, 30))]  # until 00:30 on 1 November
        october = _status(_budget(HOURS, "40"), beats, today=OCT_31)
        november = _status(_budget(HOURS, "40"), beats, today=NOV_1)
        total = _status(_budget(HOURS, "40", period=TOTAL, starts_on=OCT_1), beats, today=NOV_1)
        assert october.billable_hours == total.billable_hours == Decimal("1.00")
        assert (november.first, november.billable_hours) == (NOV_1, Decimal("0.00"))


class TestState:
    @pytest.mark.parametrize(
        ("limit", "spent", "warn", "state"),
        [
            (4000, 3199, 80, UNDER),  # 31.99 of 40 h, warned at 80 %
            (4000, 3200, 80, NEAR),
            (4000, 3999, 80, NEAR),
            (4000, 4000, 80, USED_UP),
            (333, 266, 80, UNDER),  # 79.88 %, in minor units
            (333, 267, 80, NEAR),
            (100, 7, 7, NEAR),  # 0.07 x 100 is 7.000000000000001 in floats
        ],
    )
    def test_thresholds_are_compared_in_integers(self, limit, spent, warn, state):
        assert billing_budget_state(limit, spent, warn) is state

    def test_percent_used_is_rounded_down_and_not_capped(self):
        assert [percent_used(4000, spent) for spent in (3984, 4000, 4350)] == [99, 100, 108]

    def test_over_is_a_negative_remaining(self):
        status = _status(_budget(HOURS, "40"), _daily(OCT_1, date(2026, 10, 3), _hours(14.5)))
        assert (status.state, status.remaining_hours, status.remaining_minor) == (
            USED_UP,
            Decimal("-3.50"),
            None,
        )

    def test_a_money_budget_is_judged_on_the_priced_amount_and_does_not_project(self):
        # Website has a rate of its own, Shop none at either level: 3.5 h of
        # Shop would make the budget near if they were priced at 85.00.
        client = _client()
        billings = [
            _billing(_term(JAN_1, rate=8500)),
            _billing(_term(JAN_1), project_id="p2"),
        ]
        priced = _daily(OCT_1, OCT_18, _hours(1))
        unpriced = [_beat(date(2026, 10, 9), _hours(3.5), project_id="p2")]
        budget = _budget(MONEY, 200000)
        status = _status(budget, priced + unpriced, client=client, billings=billings)
        assert (status.amount_minor, status.unpriced_hours) == (153000, Decimal("3.50"))
        assert (status.state, status.percent_used, status.runs_out_on) == (UNDER, 76, None)
        assert _status(budget, priced, client=client, billings=billings).runs_out_on == date(
            2026, 10, 24
        )

    def test_an_upcoming_total_has_no_figures_yet(self):
        budget = _budget(HOURS, "120", period=TOTAL, starts_on=NOV_1)
        beats = [*_daily(OCT_1, date(2026, 10, 17), _hours(3)), _running(OCT_18, time(9))]
        status = _status(budget, beats)
        assert (status.upcoming, status.first, status.last, status.through) == (
            True,
            NOV_1,
            None,
            None,
        )
        assert (status.billable_hours, status.amount_minor, status.remaining_hours) == (
            Decimal("0.00"),
            0,
            Decimal("120.00"),
        )
        assert (status.state, status.runs_out_on, status.running) == (UNDER, None, None)


def _utc(day: date, hour: int, minute: int = 0, second: int = 0) -> datetime:
    return datetime(day.year, day.month, day.day, hour, minute, second, tzinfo=UTC)


class TestRunning:
    def test_hours_cross_at_the_hours_left(self):
        # 30 h spent of 40, warned at 32: a timer since 09:10 (07:10 UTC).
        beats = [*_daily(OCT_1, date(2026, 10, 10), _hours(3)), _running(OCT_18, time(9, 10))]
        status = _status(_budget(HOURS, "40"), beats)
        assert status.billable_hours == Decimal("30.00")  # the running beat is in no figure
        assert status.running == (
            "p1",
            _utc(OCT_18, 7, 10),
            True,
            _utc(OCT_18, 9, 10),
            _utc(OCT_18, 17, 10),
        )

    def test_money_crosses_at_the_start_days_rate_rounded_up_to_the_second(self):
        # Started at 22:00 on the 18th at 85.00/h; the rate doubles at
        # midnight, but the beat is the 18th's. 80.00 of 100.00 is 0.9412 h,
        # 3388.2 s; 100.00 is 1.1765 h, 4235.3 s.
        client = _client((JAN_1, 8500), (date(2026, 10, 19), 17000))
        status = _status(_budget(MONEY, 10000), [_running(OCT_18, time(22))], client=client)
        assert status.running == (
            "p1",
            _utc(OCT_18, 20),
            True,
            _utc(OCT_18, 20, 56, 29),
            _utc(OCT_18, 21, 10, 36),
        )

    def test_a_start_part_way_through_a_second_still_crosses_on_a_whole_one(self):
        # A timer's start is stamped to the microsecond: 09:10:00.5, 8 h and
        # 16 h before the warning and the limit.
        beats = [
            *_daily(OCT_1, date(2026, 10, 8), _hours(3)),
            _running(OCT_18, time(9, 10, 0, 500000)),
        ]
        status = _status(_budget(HOURS, "40"), beats)
        assert status.running is not None
        assert (status.running.near_at, status.running.over_at) == (
            _utc(OCT_18, 15, 10, 1),
            _utc(OCT_18, 23, 10, 1),
        )

    def test_an_unpriced_beat_spends_hours_but_no_money(self):
        client = _client((date(2026, 10, 19), 8500))  # no rate yet on the 18th
        beats = [_running(OCT_18, time(9))]
        money = _status(_budget(MONEY, 10000), beats, client=client)
        hours = _status(_budget(HOURS, "10"), beats, client=client)
        assert money.running == ("p1", _utc(OCT_18, 7), False, None, None)
        assert hours.running == ("p1", _utc(OCT_18, 7), False, _utc(OCT_18, 15), _utc(OCT_18, 17))

    def test_a_beat_marked_not_billable_does_not_count(self):
        beat = _running(OCT_18, time(9))
        assert _status(_budget(HOURS, "40"), [beat], overrides={beat.id: False}).running is None

    def test_a_beat_started_before_the_period_belongs_to_it_and_not_this_one(self):
        beats = [_running(OCT_31, time(23))]
        assert _status(_budget(HOURS, "40"), beats, today=NOV_1).running is None
        total = _status(_budget(HOURS, "40", period=TOTAL, starts_on=OCT_1), beats, today=NOV_1)
        assert total.running is not None
        assert total.running.since == _utc(OCT_31, 22)

    def test_a_threshold_already_crossed_has_no_instant(self):
        beats = [*_daily(OCT_1, date(2026, 10, 11), _hours(3)), _running(OCT_18, time(9))]
        near = _status(_budget(HOURS, "40"), beats)  # 33 h: past the warning
        used_up = _status(_budget(HOURS, "33"), beats)
        assert near.running == ("p1", _utc(OCT_18, 7), True, None, _utc(OCT_18, 14))
        assert used_up.running == ("p1", _utc(OCT_18, 7), True, None, None)

    def test_two_running_beats_name_the_earliest_and_give_no_instant(self):
        beats = [_running(OCT_18, time(11), project_id="p2"), _running(OCT_18, time(9))]
        billings = [_billing(_term(JAN_1)), _billing(_term(JAN_1), project_id="p2")]
        status = _status(_budget(HOURS, "40"), beats, billings=billings)
        assert status.running == ("p1", _utc(OCT_18, 7), True, None, None)

    def test_the_night_the_clocks_go_back_is_elapsed_time(self):
        # From 23:00 summer time on Saturday the 24th, 5 h left: the clocks
        # go back an hour at 03:00, so it runs out at 03:00 winter time.
        beats = [
            *_daily(OCT_1, date(2026, 10, 7), _hours(5)),
            _running(date(2026, 10, 24), time(23)),
        ]
        status = _status(_budget(HOURS, "40"), beats, today=date(2026, 10, 25))
        assert status.running is not None
        assert status.running.over_at == _utc(date(2026, 10, 25), 2)
        assert status.running.over_at.astimezone(BERLIN).time() == time(3)


class TestProjection:
    @pytest.mark.parametrize(
        ("window_spend", "window_days", "remaining", "today", "last", "elapsed", "expected"),
        [
            # 35.5 of 40 h by the 18th: 1.97 h a day, so 4.5 h is 2.3 days.
            (3550, 18, 450, OCT_18, OCT_31, 18, date(2026, 10, 21)),
            (600, 6, 400, date(2026, 10, 6), OCT_31, 6, None),  # fewer than 7 days in
            (700, 7, 300, date(2026, 10, 7), OCT_31, 7, date(2026, 10, 10)),
            (0, 18, 450, OCT_18, OCT_31, 18, None),  # nothing spent in the window
            (1800, 18, 0, OCT_18, OCT_31, 18, None),  # used up
            (1800, 18, -200, OCT_18, OCT_31, 18, None),  # over
            (1800, 18, 2000, OCT_18, OCT_31, 18, None),  # after the month's end
            (1800, 18, 2000, OCT_18, None, 18, date(2026, 11, 7)),  # a total runs on
            (2800, 28, 36500, OCT_18, None, 100, date(2027, 10, 18)),  # 365 days away
            (2800, 28, 36600, OCT_18, None, 100, None),  # 366
        ],
    )
    def test_the_guards(self, window_spend, window_days, remaining, today, last, elapsed, expected):
        assert (
            runs_out_on(window_spend, window_days, remaining, today, last, elapsed, False)
            == expected
        )

    def test_an_incomplete_money_figure_has_no_projection(self):
        assert runs_out_on(3550, 18, 450, OCT_18, OCT_31, 18, True) is None

    def test_a_monthly_budget_first_projects_on_the_7th(self):
        beats = _daily(OCT_1, date(2026, 10, 7), _hours(1))
        on_6th = _status(_budget(HOURS, "10"), beats[:6], today=date(2026, 10, 6))
        on_7th = _status(_budget(HOURS, "10"), beats, today=date(2026, 10, 7))
        assert (on_6th.runs_out_on, on_7th.runs_out_on) == (None, date(2026, 10, 10))

    def test_the_pace_is_the_last_28_days(self):
        # July at 10 h a day, then 1 h a day from 21 September: 62 h left
        # lasts 62 days at the recent pace, not 21 at the period's.
        beats = [
            *_daily(date(2026, 7, 1), date(2026, 7, 31), _hours(10)),
            *_daily(date(2026, 9, 21), OCT_18, _hours(1)),
        ]
        budget = _budget(HOURS, "400", period=TOTAL, starts_on=date(2026, 7, 1))
        status = _status(budget, beats)
        assert (status.remaining_hours, status.runs_out_on) == (
            Decimal("62.00"),
            date(2026, 12, 19),
        )


class TestModels:
    @staticmethod
    def _fields(**changes):
        body = {
            "unit": "hours",
            "period": "monthly",
            "limit_hours": 40,
            "limit_minor": None,
            "starts_on": None,
            "warn_at_percent": 80,
        }
        return BillingBudgetFields.model_validate({**body, **changes})

    @staticmethod
    def _refused(**changes) -> list[tuple]:
        with pytest.raises(ValidationError) as caught:
            TestModels._fields(**changes)
        return [error["loc"] for error in caught.value.errors()]

    def test_each_unit_takes_its_own_limit_and_only_it(self):
        assert self._refused(limit_hours=None) == [("limit_hours",)]
        assert self._refused(limit_minor=8500) == [("limit_minor",)]
        assert self._refused(unit="money") == [("limit_hours",), ("limit_minor",)]
        assert self._fields(unit="money", limit_hours=None, limit_minor=8500).limit_minor == 8500

    def test_a_total_takes_a_start_and_a_monthly_budget_none(self):
        assert self._refused(period="total") == [("starts_on",)]
        assert self._refused(starts_on="2026-10-01") == [("starts_on",)]
        assert self._fields(period="total", starts_on="2026-10-01").starts_on == OCT_1

    def test_an_unknown_unit_or_period_is_the_only_error(self):
        assert self._refused(unit="days") == [("unit",)]
        assert self._refused(period="weekly", starts_on="2026-10-01") == [("period",)]

    @pytest.mark.parametrize("warn", [0, 100, True, 80.0])
    def test_the_warning_is_a_whole_percent_from_1_to_99(self, warn):
        assert self._refused(warn_at_percent=warn) == [("warn_at_percent",)]
