"""Tests for the report link arithmetic, on fixed dates (docs/billing.md,
phase 1c).

They reuse `test_billing.py`'s Studio Kite, billed in euros at 85.00/h from
1 January through Website, and mostly read September and October 2026 in
Berlin, which leaves summer time on Sunday 25 October. The last two classes
are the public read's contracts between layers: the reader asks its narrow
ports for one client's billed projects and nothing else, and the beat read
leaves tags, and notes unless shown, in Mongo.
"""

import json
import os
import re
from collections import defaultdict
from collections.abc import Iterable
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError
from pymongo import AsyncMongoClient

from beats.domain.billing import assemble_billing, assemble_client
from beats.domain.exceptions import RangeNotOver, ReportLinkExpiryOutOfRange
from beats.domain.models import (
    Beat,
    BillableOverride,
    Client,
    Project,
    ProjectBilling,
    ReportLink,
    ReportLinkFields,
    ReportScope,
)
from beats.domain.report_link_service import PublicReportReader
from beats.domain.report_links import (
    TOKEN_SHAPE,
    HoursReport,
    PricedReport,
    check_expiry,
    check_range_over,
    day_rows,
    is_live,
    merge_hours,
    new_token,
    public_report,
    report_months,
    token_hash,
    well_formed,
)
from beats.infrastructure.repositories import MongoBeatRepository
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

KEY_A = b"a" * 32
KEY_B = b"b" * 32
UTC_ZONE = ZoneInfo("UTC")
SEP_1, SEP_15, SEP_30 = date(2026, 9, 1), date(2026, 9, 15), date(2026, 9, 30)
OCT_15, OCT_18 = date(2026, 10, 15), date(2026, 10, 18)
NOV_1 = date(2026, 11, 1)
PROJECTS = {"p1": _project(), "p2": _project("p2", "Logo")}


def _scope(**fields) -> dict:
    return {
        "client_id": "c1",
        "project_ids": ["p1"],
        "first": SEP_1,
        "last": SEP_30,
        "show_amounts": False,
        "show_notes": False,
        **fields,
    }


def _link(**fields) -> ReportLink:
    return ReportLink.model_validate(
        _scope(
            label=None,
            expires_on=OCT_18,
            token_hash="0" * 64,
            key_id="1" * 64,
            tz="Europe/Berlin",
            **fields,
        )
    )


def _public(
    client: Client,
    billings: list[ProjectBilling],
    beats: list[Beat],
    *,
    overrides: dict[str, bool] | None = None,
    notes: dict[str, str] | None = None,
    projects: dict[str, Project] = PROJECTS,
    first: date = OCT_1,
    last: date = OCT_31,
    tz: ZoneInfo = BERLIN,
    amounts: bool = False,
    show_notes: bool = False,
) -> PricedReport | HoursReport:
    """A report as the public read builds it: the months, then the shape."""
    scope = ReportScope.model_validate(
        _scope(
            client_id=client.id,
            project_ids=[billing.project_id for billing in billings],
            first=first,
            last=last,
            show_amounts=amounts,
            show_notes=show_notes,
        )
    )
    own = {billing.project_id: projects[billing.project_id] for billing in billings}
    months = report_months(client, billings, own, beats, overrides or {}, first, last, tz)
    names = {project_id: project.name for project_id, project in own.items()}
    return public_report(scope, client, names, months, notes if show_notes else None)


def _key_sets(dump: dict) -> dict[str, set[frozenset[str]]]:
    """The key sets found at each depth of a dumped report, by level."""
    levels: dict[str, set[frozenset[str]]] = defaultdict(set)
    levels["report"].add(frozenset(dump))
    levels["shows"].add(frozenset(dump["shows"]))
    if "money" in dump:
        levels["money"].add(frozenset(dump["money"]))
    for month in dump["months"]:
        levels["month"].add(frozenset(month))
        for line in month["lines"]:
            levels["line"].add(frozenset(line))
        for day in month["days"]:
            levels["day"].add(frozenset(day))
    return dict(levels)


HOURS_ONLY_KEYS = {
    "report": {frozenset({"client_name", "first", "last", "shows", "billable_hours", "months"})},
    "shows": {frozenset({"amounts", "notes"})},
    "month": {
        frozenset({"month", "first", "last", "whole_month", "billable_hours", "lines", "days"})
    },
    "line": {frozenset({"project_name", "hours"})},
    "day": {frozenset({"day", "project_name", "hours"})},
}


class TestToken:
    def test_a_new_token_is_lpr_and_43_url_safe_characters(self):
        token, hashed = new_token(KEY_A)
        assert TOKEN_SHAPE.fullmatch(token)
        assert well_formed(token)
        assert hashed == token_hash(token, KEY_A)
        assert re.fullmatch(r"[0-9a-f]{64}", hashed)

    def test_two_tokens_differ(self):
        assert new_token(KEY_A)[0] != new_token(KEY_A)[0]

    def test_the_hash_is_keyed(self):
        token, _ = new_token(KEY_A)
        assert token_hash(token, KEY_A) != token_hash(token, KEY_B)

    @pytest.mark.parametrize(
        "token",
        [
            "lpr_" + "a" * 42,
            "lpr_" + "a" * 44,
            "lpr_" + "a" * 42 + "+",
            "lpr_" + "a" * 42 + "/",
            "lpr_" + "a" * 43 + "\n",
            "LPR_" + "a" * 43,
            "a" * 47,
            "",
        ],
        ids=["42", "44", "plus", "slash", "newline", "upper prefix", "no prefix", "empty"],
    )
    def test_malformed_tokens_are_not_well_formed(self, token):
        assert not well_formed(token)


class TestMonths:
    def test_two_whole_months_equal_the_clients_page(self):
        client = _client((JAN_1, 8500))
        billings = [
            _billing(_term(date(2026, 9, 5)), _term(OCT_15, rate=9500)),
            _billing(_term(JAN_1), project_id="p2"),
        ]
        before_the_first_term = _beat(date(2026, 9, 2), _hours(2))
        under_a_billable_term = _beat(date(2026, 9, 10), _hours(3))
        beats = [
            before_the_first_term,
            under_a_billable_term,
            _beat(date(2026, 9, 7), _hours(1.5)),
            _beat(SEP_30, _hours(2.5), at=time(23)),  # to 01:30 on 1 October: September's
            _beat(date(2026, 10, 9), _hours(4)),
            _beat(date(2026, 10, 20), _hours(2.25)),
            _beat(date(2026, 10, 25), _hours(3), at=time(1)),  # the night summer time ends
            _beat(date(2026, 9, 21), _hours(1), project_id="p2"),
            _beat(date(2026, 10, 21), _hours(0.75), project_id="p2"),
        ]
        overrides = {
            beat.id: mark
            for beat, mark in ((before_the_first_term, True), (under_a_billable_term, False))
            if beat.id is not None
        }

        months = report_months(client, billings, PROJECTS, beats, overrides, SEP_1, OCT_31, BERLIN)

        assert [(month.first, month.last, month.whole_month) for month in months] == [
            (SEP_1, SEP_30, True),
            (OCT_1, OCT_31, True),
        ]
        for month in months:
            page = assemble_billing(
                [client], billings, PROJECTS, beats, overrides, month.first, month.last, BERLIN
            )
            assert month.billing.lines == page.clients[0].lines
            assert month.billing.billable_hours == page.clients[0].billable_hours
            assert month.billing.amount_minor == page.clients[0].amount_minor
        assert [len(month.billing.lines) for month in months] == [2, 3]

    def test_months_are_not_one_range(self):
        # 1 h 0 m 18 s is 1.005 h: 1.01 h in each month's line, 2.02 h in
        # all — where one line over both days would round once, to 2.01 h.
        client = _client((JAN_1, 8500))
        billings = [_billing(_term(JAN_1))]
        beats = [
            _beat(OCT_31, timedelta(hours=1, seconds=18), tz=UTC_ZONE),
            _beat(NOV_1, timedelta(hours=1, seconds=18), tz=UTC_ZONE),
        ]

        report = _public(
            client, billings, beats, first=OCT_31, last=NOV_1, tz=UTC_ZONE, amounts=True
        )

        assert isinstance(report, PricedReport)
        assert [(month.billable_hours, month.amount_minor) for month in report.months] == [
            (1.01, 8585),
            (1.01, 8585),
        ]
        assert (report.billable_hours, report.money.amount_minor) == (2.02, 17170)
        one_range = assemble_client(client, billings, PROJECTS, beats, {}, OCT_31, NOV_1, UTC_ZONE)
        assert (one_range.billable_hours, one_range.amount_minor) == (Decimal("2.01"), 17085)

    def test_a_partial_month_is_rounded_on_its_own_days(self):
        months = report_months(
            _client((JAN_1, 8500)),
            [_billing(_term(JAN_1))],
            PROJECTS,
            [_beat(date(2026, 9, 3), _hours(1)), _beat(date(2026, 9, 20), _hours(2))],
            {},
            SEP_15,
            OCT_31,
            BERLIN,
        )
        assert [(month.first, month.last, month.whole_month) for month in months] == [
            (SEP_15, SEP_30, False),
            (OCT_1, OCT_31, True),
        ]
        [line] = months[0].billing.lines
        assert (line.first, line.last, line.hours) == (SEP_15, SEP_30, Decimal("2.00"))
        assert months[1].billing.lines == []

    def test_a_month_cut_short_at_its_end_is_not_whole(self):
        months = report_months(
            _client((JAN_1, 8500)),
            [_billing(_term(JAN_1))],
            PROJECTS,
            [],
            {},
            OCT_1,
            OCT_18,
            BERLIN,
        )
        assert [(month.first, month.last, month.whole_month) for month in months] == [
            (OCT_1, OCT_18, False)
        ]


class TestHoursOnly:
    def test_a_rate_change_merges_into_one_row(self):
        report = assemble_client(
            _client((JAN_1, 8500)),
            [_billing(_term(JAN_1), _term(OCT_15, rate=9500))],
            PROJECTS,
            [
                _beat(date(2026, 10, 2), timedelta(hours=1, seconds=18)),
                _beat(date(2026, 10, 20), timedelta(hours=1, seconds=18)),
            ],
            {},
            OCT_1,
            OCT_31,
            BERLIN,
        )
        assert [(line.project_name, line.hours) for line in report.lines] == [
            ("Website", Decimal("1.01")),
            ("Website", Decimal("1.01")),
        ]
        assert merge_hours(report.lines) == [("Website", Decimal("2.02"))]

    def test_a_project_rate_equal_to_the_clients_still_merges(self):
        report = assemble_client(
            _client((JAN_1, 8500)),
            [_billing(_term(JAN_1), _term(OCT_15, rate=8500))],
            PROJECTS,
            [_beat(date(2026, 10, 2), _hours(1)), _beat(date(2026, 10, 20), _hours(2))],
            {},
            OCT_1,
            OCT_31,
            BERLIN,
        )
        assert len(report.lines) == 2
        assert merge_hours(report.lines) == [("Website", Decimal("3.00"))]

    def test_one_row_per_project_by_name(self):
        report = assemble_client(
            _client((JAN_1, 8500)),
            [_billing(_term(JAN_1)), _billing(_term(JAN_1), project_id="p2")],
            PROJECTS,
            [
                _beat(date(2026, 10, 2), _hours(1)),
                _beat(date(2026, 10, 3), _hours(2), project_id="p2"),
            ],
            {},
            OCT_1,
            OCT_31,
            BERLIN,
        )
        assert merge_hours(report.lines) == [
            ("Logo", Decimal("2.00")),
            ("Website", Decimal("1.00")),
        ]


def _entries(beats: list[Beat], overrides: dict[str, bool] | None = None, **days):
    first, last = days.get("first", OCT_1), days.get("last", OCT_31)
    return assemble_client(
        _client((JAN_1, 8500)),
        [_billing(_term(JAN_1)), _billing(_term(JAN_1), project_id="p2")],
        PROJECTS,
        beats,
        overrides or {},
        first,
        last,
        BERLIN,
    ).entries


class TestDayRows:
    def test_two_18_second_beats_on_one_day_are_a_hundredth(self):
        beats = [
            _beat(date(2026, 10, 2), timedelta(seconds=18)),
            _beat(date(2026, 10, 2), timedelta(seconds=18), at=time(10)),
        ]
        [row] = day_rows(_entries(beats), None)
        assert (row.day, row.project_id, row.hours) == (date(2026, 10, 2), "p1", Decimal("0.01"))

    def test_a_beat_over_midnight_belongs_to_its_start_day(self):
        [row] = day_rows(_entries([_beat(date(2026, 10, 9), _hours(2), at=time(23))]), None)
        assert (row.day, row.hours) == (date(2026, 10, 9), Decimal("2.00"))

    def test_dst_days_count_their_real_length(self):
        # Berlin's clocks go forward on 29 March and back on 25 October:
        # local midnight to local midnight is 23 hours, then 25.
        beats = [
            _beat(date(2026, 3, 29), _hours(23), at=time(0)),
            _beat(date(2026, 10, 25), _hours(25), at=time(0)),
        ]
        rows = day_rows(_entries(beats, first=date(2026, 3, 1), last=OCT_31), None)
        assert [(row.day, row.hours) for row in rows] == [
            (date(2026, 3, 29), Decimal("23.00")),
            (date(2026, 10, 25), Decimal("25.00")),
        ]

    def test_an_end_before_its_start_adds_nothing(self):
        assert day_rows(_entries([_beat(date(2026, 10, 2), _hours(-1))]), None) == []

    def test_non_billable_entries_have_no_row(self):
        beat = _beat(date(2026, 10, 2), _hours(1))
        assert beat.id is not None
        entries = _entries([beat], {beat.id: False})
        assert len(entries) == 1
        assert day_rows(entries, None) == []

    def test_projects_on_one_day_are_rows_of_their_own(self):
        beats = [
            _beat(date(2026, 10, 2), _hours(1)),
            _beat(date(2026, 10, 2), _hours(2), project_id="p2"),
            _beat(date(2026, 10, 1), _hours(3), project_id="p2"),
        ]
        rows = day_rows(_entries(beats), None)
        assert sorted((row.day, row.project_id, row.hours) for row in rows) == [
            (OCT_1, "p2", Decimal("3.00")),
            (date(2026, 10, 2), "p1", Decimal("1.00")),
            (date(2026, 10, 2), "p2", Decimal("2.00")),
        ]

    def test_notes_in_start_order_blank_ones_dropped(self):
        day = date(2026, 10, 2)
        beats = [
            _beat(day, _hours(0.5), at=time(10)),
            _beat(day, _hours(0.5), at=time(11)),
            _beat(day, _hours(0.5), at=time(9)),
        ]
        notes = {beats[0].id: "b", beats[1].id: "  ", beats[2].id: " a "}
        [row] = day_rows(_entries(beats), {k: v for k, v in notes.items() if k is not None})
        assert row.notes == ("a", "b")

    def test_without_notes_a_row_has_no_notes(self):
        beats = [_beat(date(2026, 10, 2), _hours(1)), _beat(date(2026, 10, 3), _hours(1))]
        rows = day_rows(_entries(beats), None)
        assert len(rows) == 2
        assert all(row.notes == () for row in rows)


class TestRules:
    def test_the_range_must_be_over(self):
        check_range_over(date(2026, 10, 17), OCT_18)
        with pytest.raises(RangeNotOver):
            check_range_over(OCT_18, OCT_18)
        with pytest.raises(RangeNotOver):
            check_range_over(date(2026, 10, 19), OCT_18)

    def test_the_expiry_runs_from_today_to_366_days(self):
        check_expiry(OCT_18, OCT_18)
        check_expiry(OCT_18 + timedelta(days=366), OCT_18)
        for expires_on in (date(2026, 10, 17), OCT_18 + timedelta(days=367)):
            with pytest.raises(ReportLinkExpiryOutOfRange) as caught:
                check_expiry(expires_on, OCT_18)
            assert [field["path"] for field in caught.value.fields] == ["expires_on"]

    def test_a_link_is_live_through_its_last_day(self):
        link = _link()
        assert is_live(link, OCT_18)
        assert not is_live(link, date(2026, 10, 19))


class TestModels:
    def test_366_days_pass_and_367_do_not(self):
        ReportScope.model_validate(_scope(first=JAN_1, last=date(2027, 1, 1)))
        with pytest.raises(ValidationError) as caught:
            ReportScope.model_validate(_scope(first=JAN_1, last=date(2027, 1, 2)))
        assert [error["loc"] for error in caught.value.errors()] == [("last",)]

    def test_last_before_first_is_refused(self):
        ReportScope.model_validate(_scope(first=SEP_15, last=SEP_15))
        with pytest.raises(ValidationError) as caught:
            ReportScope.model_validate(_scope(first=SEP_15, last=date(2026, 9, 14)))
        assert [error["loc"] for error in caught.value.errors()] == [("last",)]

    @pytest.mark.parametrize(
        "project_ids",
        [["p1", "p2", "p1"], [], [f"p{n}" for n in range(51)]],
        ids=["named twice", "none", "51"],
    )
    def test_the_projects_are_one_to_fifty_named_once(self, project_ids):
        ReportScope.model_validate(_scope(project_ids=[f"p{n}" for n in range(50)]))
        with pytest.raises(ValidationError) as caught:
            ReportScope.model_validate(_scope(project_ids=project_ids))
        assert [error["loc"] for error in caught.value.errors()] == [("project_ids",)]

    @pytest.mark.parametrize("key", ["show_amounts", "show_notes"])
    def test_a_string_is_not_a_bool(self, key):
        with pytest.raises(ValidationError) as caught:
            ReportScope.model_validate(_scope(**{key: "true"}))
        assert [error["loc"] for error in caught.value.errors()] == [(key,)]

    def test_every_key_of_the_create_is_required(self):
        body = {**_scope(), "label": None, "expires_on": OCT_18}
        ReportLinkFields.model_validate(body)
        for key in body:
            with pytest.raises(ValidationError) as caught:
                ReportLinkFields.model_validate({k: v for k, v in body.items() if k != key})
            assert [error["loc"] for error in caught.value.errors()] == [(key,)]

    def test_a_blank_label_is_refused(self):
        body = {**_scope(), "expires_on": OCT_18}
        assert ReportLinkFields.model_validate({**body, "label": "  Q3  "}).label == "Q3"
        assert ReportLinkFields.model_validate({**body, "label": None}).label is None
        with pytest.raises(ValidationError) as caught:
            ReportLinkFields.model_validate({**body, "label": "   "})
        assert [error["loc"] for error in caught.value.errors()] == [("label",)]

    def test_a_stored_link_reads_back_with_no_projects_and_no_label(self):
        # The document MongoStore writes leaves a None out, and a project
        # leaving its client is pulled out of `project_ids`, down to none.
        stored = _link().model_dump(mode="json", exclude_none=True)
        assert "label" not in stored
        stored["project_ids"] = []
        link = ReportLink.model_validate(stored)
        assert (link.project_ids, link.label) == ([], None)
        with pytest.raises(ValidationError):
            ReportScope.model_validate(_scope(project_ids=[]))

    def test_a_stored_link_still_names_a_project_once(self):
        with pytest.raises(ValidationError) as caught:
            _link(project_ids=["p1", "p1"])
        assert [error["loc"] for error in caught.value.errors()] == [("project_ids",)]


def _shape_fixture(**flags) -> PricedReport | HoursReport:
    website = _beat(date(2026, 10, 2), _hours(2))
    return _public(
        _client((JAN_1, 8500)),
        [_billing(_term(JAN_1), _term(OCT_15, rate=9500)), _billing(_term(JAN_1), project_id="p2")],
        [
            website,
            _beat(date(2026, 10, 20), _hours(1)),
            _beat(date(2026, 9, 28), _hours(1.5), project_id="p2"),
        ],
        notes={website.id: "Navigation fixes"} if website.id else None,
        first=SEP_15,
        **flags,
    )


class TestPublicShape:
    def test_an_hours_only_report_has_no_money_at_any_depth(self):
        report = _shape_fixture()
        assert isinstance(report, HoursReport)
        assert _key_sets(report.model_dump(mode="json")) == HOURS_ONLY_KEYS
        assert [
            [(line.project_name, line.hours) for line in month.lines] for month in report.months
        ] == [[("Logo", 1.5)], [("Website", 3.0)]]

    def test_amounts_add_exactly_their_keys(self):
        report = _shape_fixture(amounts=True)
        assert isinstance(report, PricedReport)
        assert _key_sets(report.model_dump(mode="json")) == {
            **HOURS_ONLY_KEYS,
            "report": {next(iter(HOURS_ONLY_KEYS["report"])) | {"money"}},
            "money": {frozenset({"currency", "minor_units", "amount_minor", "unpriced_hours"})},
            "month": {next(iter(HOURS_ONLY_KEYS["month"])) | {"amount_minor", "unpriced_hours"}},
            "line": {
                next(iter(HOURS_ONLY_KEYS["line"]))
                | {"first", "last", "rate_minor", "amount_minor"}
            },
        }
        assert report.money.model_dump() == {
            "currency": "EUR",
            "minor_units": 2,
            "amount_minor": 12750 + 17000 + 9500,
            "unpriced_hours": 0.0,
        }

    def test_notes_add_exactly_their_key(self):
        report = _shape_fixture(show_notes=True)
        assert _key_sets(report.model_dump(mode="json")) == {
            **HOURS_ONLY_KEYS,
            "day": {next(iter(HOURS_ONLY_KEYS["day"])) | {"notes"}},
        }
        days = [day.model_dump(mode="json") for month in report.months for day in month.days]
        assert days == [
            {"day": "2026-09-28", "project_name": "Logo", "hours": 1.5, "notes": []},
            {
                "day": "2026-10-02",
                "project_name": "Website",
                "hours": 2.0,
                "notes": ["Navigation fixes"],
            },
            {"day": "2026-10-20", "project_name": "Website", "hours": 1.0, "notes": []},
        ]

    def test_the_link_says_what_it_shows(self):
        dump = _shape_fixture(amounts=True).model_dump(mode="json")
        assert dump["shows"] == {"amounts": True, "notes": False}
        assert (dump["client_name"], dump["first"], dump["last"]) == (
            "Studio Kite",
            "2026-09-15",
            "2026-10-31",
        )
        assert [
            (month["month"], month["first"], month["last"], month["whole_month"])
            for month in dump["months"]
        ] == [
            ("2026-09", "2026-09-15", "2026-09-30", False),
            ("2026-10", "2026-10-01", "2026-10-31", True),
        ]

    def test_an_unpriced_line_is_null_not_absent(self):
        report = _public(
            _client(),
            [_billing(_term(JAN_1))],
            [_beat(date(2026, 10, 2), _hours(12))],
            amounts=True,
        )
        assert isinstance(report, PricedReport)
        [line] = report.months[0].lines
        dump = line.model_dump(mode="json")
        assert (dump["rate_minor"], dump["amount_minor"], dump["hours"]) == (None, None, 12.0)
        assert (report.money.unpriced_hours, report.money.amount_minor) == (12.0, 0)
        assert report.months[0].unpriced_hours == 12.0

    def test_days_are_by_day_then_project_name(self):
        report = _public(
            _client((JAN_1, 8500)),
            [_billing(_term(JAN_1)), _billing(_term(JAN_1), project_id="p2")],
            [
                _beat(date(2026, 10, 3), _hours(1)),
                _beat(date(2026, 10, 2), _hours(1)),
                _beat(date(2026, 10, 2), _hours(1), project_id="p2", at=time(14)),
            ],
        )
        assert [(day.day, day.project_name) for day in report.months[0].days] == [
            (date(2026, 10, 2), "Logo"),
            (date(2026, 10, 2), "Website"),
            (date(2026, 10, 3), "Website"),
        ]

    def test_no_id_crosses(self):
        # Ids shaped as Mongo's: an ObjectId carries its creation time, and
        # one on two links would tie them together.
        client_id = "65f1a2b3c4d5e6f7a8b9c0d1"
        website, logo = "65f1a2b3c4d5e6f7a8b9c0d2", "65f1a2b3c4d5e6f7a8b9c0d3"
        start = datetime(2026, 10, 2, 9, tzinfo=UTC)
        beats = [
            Beat(
                id=f"65f1a2b3c4d5e6f7a8b9c1{n:02d}",
                project_id=project_id,
                start=start + timedelta(days=n),
                end=start + timedelta(days=n, hours=1),
            )
            for n, project_id in enumerate([website, logo, website])
        ]
        for amounts in (False, True):
            report = _public(
                _client((JAN_1, 8500), client_id=client_id),
                [
                    _billing(_term(JAN_1), project_id=website, client_id=client_id),
                    _billing(_term(JAN_1), project_id=logo, client_id=client_id),
                ],
                beats,
                notes={beat.id: "a note" for beat in beats if beat.id},
                projects={website: _project(website), logo: _project(logo, "Logo")},
                amounts=amounts,
                show_notes=True,
            )
            text = json.dumps(report.model_dump(mode="json"))
            assert "Website" in text
            assert not re.search(r"[0-9a-f]{24}", text)


class _Recorder:
    """The calls the fakes below were asked, by method."""

    def __init__(self) -> None:
        self.calls: dict[str, list] = defaultdict(list)


class _Clients:
    def __init__(self, recorder: _Recorder, client: Client) -> None:
        self.recorder, self.client = recorder, client

    async def get_by_id(self, client_id: str) -> Client:
        self.recorder.calls["get_by_id"].append(client_id)
        return self.client


class _Billings:
    def __init__(self, recorder: _Recorder, billings: list[ProjectBilling]) -> None:
        self.recorder, self.billings = recorder, billings

    async def list_by_client(self, client_id: str) -> list[ProjectBilling]:
        self.recorder.calls["list_by_client"].append(client_id)
        return [billing for billing in self.billings if billing.client_id == client_id]


class _Names:
    def __init__(self, recorder: _Recorder, names: dict[str, str]) -> None:
        self.recorder, self.names = recorder, names

    async def names_of(self, project_ids: Iterable[str]) -> dict[str, str]:
        asked = sorted(project_ids)
        self.recorder.calls["names_of"].append(asked)
        return {project_id: self.names[project_id] for project_id in asked}


class _Beats:
    def __init__(self, recorder: _Recorder, beats: list[Beat]) -> None:
        self.recorder, self.beats = recorder, beats

    async def list_finished_between(
        self, project_ids: Iterable[str], start: datetime, end: datetime, *, notes: bool
    ) -> list[Beat]:
        ids = sorted(project_ids)
        self.recorder.calls["list_finished_between"].append((ids, start, end, notes))
        return [beat for beat in self.beats if beat.project_id in ids]


class _Overrides:
    def __init__(self, recorder: _Recorder) -> None:
        self.recorder = recorder

    async def list_for(self, beat_ids: Iterable[str]) -> list[BillableOverride]:
        self.recorder.calls["list_for"].append(sorted(beat_ids))
        return []


class TestReaderPorts:
    @pytest.mark.parametrize("show_notes", [False, True])
    async def test_the_reader_reaches_only_its_ports(self, show_notes):
        # Fakes with only the narrow Protocols' methods: a reader that asked
        # for anything else, a list of every client or project among them,
        # would fail here with an AttributeError.
        recorder = _Recorder()
        beats = [
            _beat(date(2026, 10, 2), _hours(2)),
            _beat(date(2026, 10, 3), _hours(1), project_id="p2"),
            _beat(date(2026, 10, 4), _hours(4), project_id="p3"),
        ]
        reader = PublicReportReader(
            clients=_Clients(recorder, _client((JAN_1, 8500))),
            billings=_Billings(
                recorder,
                [
                    _billing(_term(JAN_1)),
                    _billing(_term(JAN_1), project_id="p2"),
                    _billing(_term(JAN_1), project_id="p3", client_id="c2"),
                ],
            ),
            projects=_Names(recorder, {"p1": "Website", "p2": "Logo", "p3": "API"}),
            beats=_Beats(recorder, beats),
            overrides=_Overrides(recorder),
        )
        # p2 is billed to the client and left out; p3 is another client's.
        scope = ReportScope.model_validate(
            _scope(project_ids=["p1", "p3"], first=OCT_1, last=OCT_31, show_notes=show_notes)
        )

        report = await reader.read(scope, BERLIN)

        assert [line.project_name for month in report.months for line in month.lines] == ["Website"]
        assert recorder.calls["get_by_id"] == ["c1"]
        assert recorder.calls["names_of"] == [["p1"]]
        [(ids, start, end, notes)] = recorder.calls["list_finished_between"]
        assert (ids, notes) == (["p1"], show_notes)
        assert (start, end) == (
            datetime(2026, 9, 30, 22, tzinfo=UTC),
            datetime(2026, 10, 31, 23, tzinfo=UTC),
        )
        assert recorder.calls["list_for"] == [[beats[0].id]]


@pytest.fixture
async def db():
    client = AsyncMongoClient(os.environ.get("DB_DSN", "mongodb://localhost:27017"))
    try:
        yield client[os.environ.get("DB_NAME", "beats_test")]
    finally:
        await client.close()


class TestReportBeatRead:
    """The public report's beat read leaves `tags` in Mongo, and `note` too
    unless the link shows notes. A response cannot show that — a read that
    fetched them and dropped them later would pass every HTTP test — so it
    is pinned on the repository."""

    USER = "report-beat-reader"

    async def test_tags_never_leave_mongo_and_notes_only_when_shown(self, db):
        beats = MongoBeatRepository(db.timeLogs, user_id=self.USER)
        start = datetime(2026, 3, 10, 9, tzinfo=UTC)
        await db.timeLogs.delete_many({"user_id": self.USER})
        try:
            stored = await beats.create(
                Beat(
                    project_id="p1",
                    start=start,
                    end=start + timedelta(hours=1),
                    note="a note",
                    tags=["a tag"],
                )
            )
            await beats.create(Beat(project_id="p1", start=start + timedelta(hours=2)))
            span = (start - timedelta(days=1), start + timedelta(days=1))

            without = await beats.list_finished_between(["p1"], *span, notes=False)
            noted = await beats.list_finished_between(["p1"], *span, notes=True)
        finally:
            await db.timeLogs.delete_many({"user_id": self.USER})

        assert [(beat.id, beat.note, beat.tags) for beat in without] == [(stored.id, None, [])]
        assert [(beat.id, beat.note, beat.tags) for beat in noted] == [(stored.id, "a note", [])]
