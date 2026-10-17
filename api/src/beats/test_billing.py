"""Tests for the billing arithmetic, on fixed dates.

Most of them read October 2026 in Berlin for one client, Studio Kite, billed
in euros at 85.00/h from 1 January, through one freelance project, Website.
October is a good month to read: Berlin leaves summer time on Sunday 25
October, and Los Angeles a week later, on 1 November.
"""

from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from itertools import count
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from beats.domain.billing import (
    RateSource,
    assemble_billing,
    assemble_client,
    link_change,
    past_change,
    utc_range,
)
from beats.domain.models import (
    Beat,
    BillingTerm,
    Client,
    Project,
    ProjectBilling,
    ProjectKind,
    RateTerm,
)

BERLIN = ZoneInfo("Europe/Berlin")
LOS_ANGELES = ZoneInfo("America/Los_Angeles")
OCT_1, OCT_31 = date(2026, 10, 1), date(2026, 10, 31)
JAN_1 = date(2026, 1, 1)

_ids = count(1)


def _client(
    *rates: tuple[date, int], client_id: str = "c1", currency: str = "EUR", **fields
) -> Client:
    return Client(
        id=client_id,
        name=fields.pop("name", "Studio Kite"),
        currency=currency,
        rates=[RateTerm(effective_from=day, rate_minor=rate) for day, rate in rates],
        **fields,
    )


def _term(effective_from: date, *, billable: bool = True, rate: int | None = None) -> BillingTerm:
    return BillingTerm(effective_from=effective_from, billable=billable, rate_minor=rate)


def _billing(*terms: BillingTerm, project_id: str = "p1", client_id: str = "c1") -> ProjectBilling:
    return ProjectBilling(project_id=project_id, client_id=client_id, terms=list(terms))


def _project(project_id: str = "p1", name: str = "Website", **fields) -> Project:
    return Project(
        id=project_id, name=name, kind=fields.pop("kind", ProjectKind.FREELANCE), **fields
    )


def _beat(
    day: date,
    length: timedelta | None,
    *,
    at: time = time(9),
    project_id: str = "p1",
    tz: ZoneInfo = BERLIN,
) -> Beat:
    """A beat starting at `at` local time on `day`, `length` long in real
    time (None: still running). Built in UTC, where adding a timedelta is
    real time, not wall-clock time."""
    start = datetime.combine(day, at, tz).astimezone(UTC)
    end = start + length if length is not None else None
    return Beat(id=f"b{next(_ids)}", project_id=project_id, start=start, end=end)


def _hours(value: float) -> timedelta:
    return timedelta(hours=value)


def _report(
    client: Client,
    billings: list[ProjectBilling],
    beats: list[Beat],
    overrides: dict[str | None, bool] | None = None,
    *,
    first: date = OCT_1,
    last: date = OCT_31,
    tz: ZoneInfo = BERLIN,
):
    marks = {beat_id: mark for beat_id, mark in (overrides or {}).items() if beat_id is not None}
    return assemble_client(client, billings, {"p1": _project()}, beats, marks, first, last, tz)


def _line(line) -> tuple:
    return (line.rate_minor, line.source, line.first, line.last, line.hours, line.amount_minor)


class TestResolution:
    def test_a_project_rate_beats_the_clients(self):
        report = _report(
            _client((JAN_1, 8500)),
            [_billing(_term(OCT_1, rate=9500))],
            [_beat(date(2026, 10, 2), _hours(2))],
        )
        assert [_line(line) for line in report.lines] == [
            (9500, RateSource.PROJECT, OCT_1, OCT_31, Decimal("2.00"), 19000)
        ]

    def test_a_term_without_a_rate_takes_the_clients_rate_that_day(self):
        report = _report(
            _client((JAN_1, 8500), (date(2026, 10, 15), 9000)),
            [_billing(_term(JAN_1))],
            [_beat(date(2026, 10, 2), _hours(1)), _beat(date(2026, 10, 20), _hours(1))],
        )
        assert [_line(line) for line in report.lines] == [
            (8500, RateSource.CLIENT, OCT_1, date(2026, 10, 14), Decimal("1.00"), 8500),
            (9000, RateSource.CLIENT, date(2026, 10, 15), OCT_31, Decimal("1.00"), 9000),
        ]

    def test_before_the_projects_first_term_an_entry_is_not_billable(self):
        early, late = _beat(date(2026, 10, 5), _hours(2)), _beat(date(2026, 10, 12), _hours(1))
        report = _report(
            _client((JAN_1, 8500)), [_billing(_term(date(2026, 10, 10)))], [early, late]
        )
        assert (report.billable_hours, report.non_billable_hours) == (
            Decimal("1.00"),
            Decimal("2.00"),
        )
        assert [(e.beat_id, e.billable, e.overridden) for e in report.entries] == [
            (early.id, False, False),
            (late.id, True, False),
        ]

    def test_an_override_of_true_before_the_first_term_bills_at_the_clients_rate(self):
        early = _beat(date(2026, 10, 5), _hours(2))
        report = _report(
            _client((JAN_1, 8500)),
            [_billing(_term(date(2026, 10, 10), rate=9500))],
            [early],
            {early.id: True},
        )
        assert [_line(line) for line in report.lines] == [
            (8500, RateSource.CLIENT, OCT_1, date(2026, 10, 9), Decimal("2.00"), 17000)
        ]
        assert [(e.billable, e.overridden, e.rate_minor) for e in report.entries] == [
            (True, True, 8500)
        ]

    def test_an_override_of_false_under_a_billable_term_drops_the_entry(self):
        kept, dropped = _beat(date(2026, 10, 2), _hours(1)), _beat(date(2026, 10, 3), _hours(3))
        report = _report(
            _client((JAN_1, 8500)), [_billing(_term(JAN_1))], [kept, dropped], {dropped.id: False}
        )
        assert (report.billable_hours, report.non_billable_hours, report.amount_minor) == (
            Decimal("1.00"),
            Decimal("3.00"),
            8500,
        )
        assert [(e.billable, e.overridden, e.rate_minor) for e in report.entries] == [
            (True, False, 8500),
            (False, True, None),
        ]

    def test_with_no_rate_at_either_level_the_hours_are_unpriced(self):
        report = _report(_client(), [_billing(_term(JAN_1))], [_beat(OCT_1, _hours(1.5))])
        assert [_line(line) for line in report.lines] == [
            (None, None, OCT_1, OCT_31, Decimal("1.50"), None)
        ]
        assert (report.billable_hours, report.unpriced_hours, report.amount_minor) == (
            Decimal("1.50"),
            Decimal("1.50"),
            0,
        )


class TestLines:
    def test_a_rate_that_goes_85_95_85_is_three_lines(self):
        oct_10, oct_20 = date(2026, 10, 10), date(2026, 10, 20)
        report = _report(
            _client((JAN_1, 8500), (oct_10, 9500), (oct_20, 8500)),
            [_billing(_term(JAN_1))],
            [_beat(date(2026, 10, day), _hours(1)) for day in (2, 12, 15, 25)],
        )
        assert [_line(line) for line in report.lines] == [
            (8500, RateSource.CLIENT, OCT_1, date(2026, 10, 9), Decimal("1.00"), 8500),
            (9500, RateSource.CLIENT, oct_10, date(2026, 10, 19), Decimal("2.00"), 19000),
            (8500, RateSource.CLIENT, oct_20, OCT_31, Decimal("1.00"), 8500),
        ]

    def test_equal_client_and_project_rates_are_two_lines_by_source(self):
        oct_15 = date(2026, 10, 15)
        report = _report(
            _client((JAN_1, 8500)),
            [_billing(_term(JAN_1), _term(oct_15, rate=8500))],
            [_beat(date(2026, 10, 2), _hours(1)), _beat(date(2026, 10, 20), _hours(1))],
        )
        assert [(line.rate_minor, line.source) for line in report.lines] == [
            (8500, RateSource.CLIENT),
            (8500, RateSource.PROJECT),
        ]


class TestBucketing:
    def test_late_evening_utc_is_the_next_local_day_in_berlin(self):
        beat = Beat(
            id="b",
            project_id="p1",
            start=datetime(2026, 9, 30, 22, 30, tzinfo=UTC),
            end=datetime(2026, 9, 30, 23, 30, tzinfo=UTC),
        )
        october = _report(_client((JAN_1, 8500)), [_billing(_term(JAN_1))], [beat])
        assert [(e.beat_id, e.day) for e in october.entries] == [("b", OCT_1)]
        september = _report(
            _client((JAN_1, 8500)),
            [_billing(_term(JAN_1))],
            [beat],
            first=date(2026, 9, 1),
            last=date(2026, 9, 30),
        )
        assert september.entries == []

    def test_the_night_us_summer_time_ends_is_still_october_in_los_angeles(self):
        beat = Beat(
            id="b",
            project_id="p1",
            start=datetime(2026, 11, 1, 3, 0, tzinfo=UTC),  # 20:00 PDT on the 31st
            end=datetime(2026, 11, 1, 4, 0, tzinfo=UTC),
        )
        report = _report(_client((JAN_1, 8500)), [_billing(_term(JAN_1))], [beat], tz=LOS_ANGELES)
        assert [e.day for e in report.entries] == [OCT_31]

    def test_a_beat_across_midnight_on_the_31st_is_octobers_at_the_31sts_rate(self):
        client = _client((JAN_1, 8500), (date(2026, 11, 1), 9500))
        beat = _beat(OCT_31, _hours(2.5), at=time(23))
        october = _report(client, [_billing(_term(JAN_1))], [beat])
        assert [_line(line) for line in october.lines] == [
            (8500, RateSource.CLIENT, OCT_1, OCT_31, Decimal("2.50"), 21250)
        ]
        november = _report(
            client,
            [_billing(_term(JAN_1))],
            [beat],
            first=date(2026, 11, 1),
            last=date(2026, 11, 30),
        )
        assert (november.lines, november.entries) == ([], [])

    def test_the_night_summer_time_ends_counts_the_hours_that_passed(self):
        # 00:30 to 04:30 on the wall clock on 25 October, but the clock went
        # back an hour at 03:00: five hours passed. Built in Berlin time, so
        # the assembler, not the fixture, has to see it.
        beat = Beat(
            id="b",
            project_id="p1",
            start=datetime(2026, 10, 25, 0, 30, tzinfo=BERLIN),
            end=datetime(2026, 10, 25, 4, 30, tzinfo=BERLIN),
        )
        report = _report(_client((JAN_1, 8500)), [_billing(_term(JAN_1))], [beat])
        assert report.billable_hours == Decimal("5.00")

    def test_a_running_beat_is_left_out_and_says_so(self):
        report = _report(
            _client((JAN_1, 8500)),
            [_billing(_term(JAN_1))],
            [_beat(date(2026, 10, 2), _hours(1)), _beat(date(2026, 10, 17), None)],
        )
        assert (report.running, report.billable_hours, len(report.entries)) == (
            True,
            Decimal("1.00"),
            1,
        )

    def test_a_month_is_read_from_local_midnight_to_local_midnight(self):
        # Summer time in Berlin on the 1st, winter time by the 31st.
        assert utc_range(OCT_1, OCT_31, BERLIN) == (
            datetime(2026, 9, 30, 22, 0, tzinfo=UTC),
            datetime(2026, 10, 31, 23, 0, tzinfo=UTC),
        )


class TestRounding:
    def test_eighteen_seconds_rounds_up_to_a_hundredth_of_an_hour(self):
        report = _report(
            _client((JAN_1, 8500)),
            [_billing(_term(JAN_1))],
            [_beat(OCT_1, timedelta(seconds=18))],
        )
        assert (report.billable_hours, report.amount_minor) == (Decimal("0.01"), 85)

    def test_half_a_minor_unit_rounds_up(self):
        # 12 h 20 min is 12.33 h; 12.33 x 86.50 is 1,066.545: half a cent over
        # an even one, so half to even would keep 1,066.54.
        report = _report(
            _client((JAN_1, 8650)),
            [_billing(_term(JAN_1))],
            [_beat(OCT_1, timedelta(hours=12, minutes=20))],
        )
        assert (report.billable_hours, report.amount_minor) == (Decimal("12.33"), 106655)

    @pytest.mark.parametrize(
        ("currency", "rate", "minor_units", "amount"),
        [
            ("JPY", 5000, 0, 6650),  # ¥5,000/h x 1.33 h
            ("KWD", 12345, 3, 16419),  # 12.345 KD/h x 1.33 h = 16.41885
        ],
    )
    def test_currencies_without_two_decimals(self, currency, rate, minor_units, amount):
        report = _report(
            _client((JAN_1, rate), currency=currency),
            [_billing(_term(JAN_1))],
            [_beat(OCT_1, timedelta(hours=1, minutes=20))],
        )
        assert (report.currency, report.minor_units, report.amount_minor) == (
            currency,
            minor_units,
            amount,
        )

    def test_totals_are_the_sums_of_the_lines_to_the_minor_unit(self):
        client = _client((JAN_1, 8550), (date(2026, 10, 16), 9125))
        billing = _billing(_term(JAN_1), _term(date(2026, 10, 20), rate=11111))
        beats = [
            _beat(
                OCT_1 + timedelta(days=n % 31),
                timedelta(seconds=1234 + 37 * n),
                at=time(1 + 6 * (n % 3)),
            )
            for n in range(200)
        ]
        overrides = {beat.id: False for beat in beats[::7] if beat.id is not None}
        report = assemble_billing(
            [client], [billing], {"p1": _project()}, beats, overrides, OCT_1, OCT_31, BERLIN
        )
        [row] = report.clients
        assert len(row.lines) == 3  # 85.50, 91.25, then its own 111.11
        assert row.billable_hours == sum(line.hours for line in row.lines)
        assert row.amount_minor == sum(line.amount_minor or 0 for line in row.lines)
        assert [(t.billable_hours, t.amount_minor) for t in report.totals] == [
            (row.billable_hours, row.amount_minor)
        ]

    def test_each_currency_is_totalled_on_its_own(self):
        euro = _client((JAN_1, 8500))
        dollar = _client((JAN_1, 10000), client_id="c2", name="Acme", currency="USD")
        report = assemble_billing(
            [euro, dollar],
            [_billing(_term(JAN_1)), _billing(_term(JAN_1), project_id="p2", client_id="c2")],
            {"p1": _project(), "p2": _project("p2", "Shop")},
            [_beat(OCT_1, _hours(2)), _beat(OCT_1, _hours(1), project_id="p2")],
            {},
            OCT_1,
            OCT_31,
            BERLIN,
        )
        assert [
            (t.currency, t.minor_units, t.billable_hours, t.amount_minor) for t in report.totals
        ] == [
            ("EUR", 2, Decimal("2.00"), 17000),
            ("USD", 2, Decimal("1.00"), 10000),
        ]


class TestThePeriod:
    def test_who_is_listed(self):
        active = _client((JAN_1, 8500), client_id="c1", name="Studio Kite")
        idle = _client(client_id="c2", name="Acme")
        archived_with_hours = _client((JAN_1, 8500), client_id="c3", name="Old", archived=True)
        archived_idle = _client(client_id="c4", name="Older", archived=True)
        projects = {
            "p1": _project("p1", "Website"),
            "p3": _project("p3", "Legacy", archived=True),
            "p4": _project("p4", "Logo refresh"),
            "p5": _project("p5", "Garden", kind=ProjectKind.SIDE_PROJECT),
        }
        report = assemble_billing(
            [active, idle, archived_with_hours, archived_idle],
            [_billing(_term(JAN_1)), _billing(_term(JAN_1), project_id="p3", client_id="c3")],
            projects,
            [
                _beat(OCT_1, _hours(1)),
                _beat(OCT_1, _hours(2), project_id="p3"),
                _beat(OCT_1, _hours(4), project_id="p4"),
                _beat(OCT_1, _hours(8), project_id="p5"),
                _beat(date(2026, 10, 17), None, project_id="p4"),
            ],
            {},
            OCT_1,
            OCT_31,
            BERLIN,
        )
        assert [c.name for c in report.clients] == ["Acme", "Old", "Studio Kite"]
        assert [(u.project_id, u.name, u.hours) for u in report.unattached] == [
            ("p4", "Logo refresh", Decimal("4.00"))
        ]


MONTH = OCT_1


def _rates(*terms: tuple[date, int]) -> list[RateTerm]:
    return [RateTerm(effective_from=day, rate_minor=rate) for day, rate in terms]


class TestPastChange:
    def test_a_term_in_the_current_month_changes_no_past(self):
        old = _rates((JAN_1, 8500))
        new = _rates((JAN_1, 8500), (date(2026, 10, 5), 9000))
        assert past_change(old, new, MONTH) is None

    @pytest.mark.parametrize(
        ("old", "new", "first"),
        [
            pytest.param(
                _rates((JAN_1, 8500), (date(2026, 3, 1), 9000)),
                _rates((JAN_1, 8500), (date(2026, 3, 1), 9500)),
                date(2026, 3, 1),
                id="an amount edited",
            ),
            pytest.param(
                _rates((JAN_1, 8500), (date(2026, 3, 1), 9000)),
                _rates((JAN_1, 8500)),
                date(2026, 3, 1),
                id="a term removed",
            ),
            pytest.param(
                _rates((JAN_1, 8500)),
                _rates((JAN_1, 8500), (date(2026, 6, 1), 9000)),
                date(2026, 6, 1),
                id="a term added",
            ),
            pytest.param(
                _rates((date(2026, 4, 1), 8500)),
                _rates((date(2026, 3, 1), 8500)),
                date(2026, 3, 1),
                id="a term moved",
            ),
            pytest.param(
                [_term(JAN_1)],
                [_term(JAN_1, billable=False)],
                JAN_1,
                id="billing turned off from a past date",
            ),
        ],
    )
    def test_a_past_term_changed_returns_the_first_day_it_touches(self, old, new, first):
        assert past_change(old, new, MONTH) == first

    def test_identical_terms_change_nothing(self):
        assert past_change(_rates((JAN_1, 8500)), _rates((JAN_1, 8500)), MONTH) is None

    def test_a_new_client_rewrites_from_the_earliest_past_term(self):
        terms = [_term(date(2026, 2, 1)), _term(date(2026, 10, 5), billable=False)]
        assert link_change(terms, MONTH) == date(2026, 2, 1)
        assert link_change([_term(date(2026, 10, 5))], MONTH) is None


class TestModels:
    def test_a_term_that_is_not_billable_takes_no_rate(self):
        with pytest.raises(ValidationError) as caught:
            BillingTerm(effective_from=JAN_1, billable=False, rate_minor=100)
        assert [error["loc"] for error in caught.value.errors()] == [("rate_minor",)]

    @pytest.mark.parametrize("second", [date(2025, 12, 1), JAN_1], ids=["earlier", "same day"])
    def test_terms_and_rates_run_forward_one_a_day(self, second):
        with pytest.raises(ValidationError) as caught:
            _billing(_term(JAN_1), _term(second))
        assert [error["loc"] for error in caught.value.errors()] == [("terms",)]
        with pytest.raises(ValidationError) as caught:
            _client((JAN_1, 8500), (second, 9000))
        assert [error["loc"] for error in caught.value.errors()] == [("rates",)]
