"""What the project page reads off the contract: the ledger, the monthly
timesheet, the vacation year, absences, balance adjustments, and the
holiday reference data behind the region picker.

Split out of `test_api.py` at the size ceiling (CLAUDE.md § Conventions); the
harness is `conftest.py`'s and the shared fixtures `api_helpers.py`'s.
"""

import csv
import io
from datetime import UTC, date, datetime, timedelta

import pytest

from api_helpers import (
    COMPANY_DAY,
    CONTRACT_START,
    EASTER_MONDAY,
    FULL_TIME,
    VACATION,
    _create_project,
    _day_job,
    _log,
    _put_contract,
)


class TestLedgerAPI:
    """GET /api/projects/{id}/ledger — every week figure on the project page,
    from one read. The assembly is tested on fixed dates in `test_ledger.py`;
    this is the wire: the shape, the bounds, the timezone, the scoping, and
    that its current week is the week route's."""

    def _ledger(self, client, headers, project_id: str, **params) -> dict:
        resp = client.get(f"/api/projects/{project_id}/ledger", params=params, headers=headers)
        assert resp.status_code == 200, resp.text
        return resp.json()

    @staticmethod
    def _this_monday() -> date:
        today = datetime.now(UTC).date()
        return today - timedelta(days=today.weekday())

    def test_eight_weeks_newest_first_by_default(self, client, auth_headers):
        project = _day_job(client, auth_headers, opening_balance_hours=2.25)
        monday = self._this_monday()
        last_monday = monday - timedelta(weeks=1)
        _log(client, auth_headers, project["id"], f"{monday}T09:00:00+00:00", 47)
        _log(client, auth_headers, project["id"], f"{last_monday}T09:00:00+00:00", 95)

        ledger = self._ledger(client, auth_headers, project["id"])

        assert [w["week_of"] for w in ledger["weeks"]] == [
            (monday - timedelta(weeks=n)).isoformat() for n in range(8)
        ]
        current, last = ledger["weeks"][:2]
        assert current["worked"] == 0.78
        assert current["days"] == [0.78, 0, 0, 0, 0, 0, 0]
        assert current["balance_end"] is None  # not closed yet
        assert current["balance_moved"] is None
        assert current["contract_expected"] == 40
        assert (current["effective_goal"], current["effective_goal_type"]) == (40, "target")
        assert current["effective_goal_overridden"] is False
        assert current["notes"] == []
        assert last["worked"] == 1.58
        # Last week's close is the week before's moved by last week's own
        # worked − expected: the row is its own week's, not a neighbour's.
        assert last["balance_end"] - ledger["weeks"][2]["balance_end"] == pytest.approx(
            last["worked"] - last["contract_expected"], abs=0.01
        )
        assert last["balance_moved"] == pytest.approx(
            last["balance_end"] - ledger["weeks"][2]["balance_end"], abs=0.01
        )
        assert ledger["since"] == CONTRACT_START
        totals = ledger["totals"]
        assert totals["adjusted"] == 0
        assert 2.25 + totals["worked"] - totals["expected"] + totals["adjusted"] == pytest.approx(
            totals["balance"], abs=0.025
        )
        # The current week is the week route's, to the decimal, and so is
        # today's balance.
        resp = client.get(f"/api/projects/{project['id']}/contract/week", headers=auth_headers)
        assert resp.status_code == 200, resp.text
        week = resp.json()
        assert current["worked"] == week["worked"]
        assert totals["balance"] == week["balance"]
        assert (totals["worked"], totals["expected"]) == (
            week["balance_worked"],
            week["balance_expected_through"],
        )

    def test_a_week_carries_the_adjusted_expectation_beside_the_nominal_goal(
        self, client, auth_headers
    ):
        # The row reads what the week expects after holidays and absences — the
        # week route's figure — while `effective_goal` stays the term's nominal
        # hours, which is what the score and the coach want (the readers'
        # decision).
        project = _day_job(client, auth_headers)
        wednesday = self._this_monday() + timedelta(days=2)
        resp = client.post(
            f"/api/projects/{project['id']}/absences",
            json={"date": wednesday.isoformat(), "type": "vacation"},
            headers=auth_headers,
        )
        assert resp.status_code == 201, resp.text

        current = self._ledger(client, auth_headers, project["id"], weeks=1)["weeks"][0]

        assert current["contract_expected"] == 32
        assert current["effective_goal"] == 40
        # And it is the week route's own figure for that Monday, to the decimal.
        resp = client.get(
            f"/api/projects/{project['id']}/contract/week",
            params={"week_of": current["week_of"]},
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["expected"] == current["contract_expected"]

    def test_a_company_holiday_is_a_holiday_note(self, client, auth_headers):
        project = _day_job(client, auth_headers)
        wednesday = (self._this_monday() + timedelta(days=2)).isoformat()
        _put_contract(
            client,
            auth_headers,
            project["id"],
            company_holidays=[{"date": wednesday, "name": "Company day"}],
        )

        current = self._ledger(client, auth_headers, project["id"], weeks=1)["weeks"][0]

        assert current["notes"] == [
            {"date": wednesday, "kind": "holiday", "half_day": None, "name": "Company day"}
        ]
        assert current["contract_expected"] == 32

    def test_weeks_out_of_range_is_422_naming_the_parameter(self, client, auth_headers):
        project = _day_job(client, auth_headers)
        resp = client.get(
            f"/api/projects/{project['id']}/ledger", params={"weeks": 105}, headers=auth_headers
        )
        assert resp.status_code == 422, resp.text
        body = resp.json()
        assert body["code"] == "VALIDATION_ERROR"
        assert [f["path"] for f in body["fields"]] == ["weeks"]

    def test_days_follow_the_request_timezone(self, client, auth_headers):
        project = _day_job(client, auth_headers)
        monday = self._this_monday()
        # 23:30 UTC on Monday, running into Tuesday — which in Zürich began
        # at 00:30 (or 01:30) on the Tuesday. Whole to its local start day.
        _log(client, auth_headers, project["id"], f"{monday}T23:30:00+00:00", 60)

        # Two weeks, looked up by Monday: late on a Sunday, Zürich is already
        # in the next week while UTC is not.
        def week_of(ledger: dict) -> dict:
            return next(w for w in ledger["weeks"] if w["week_of"] == monday.isoformat())

        in_utc = week_of(self._ledger(client, auth_headers, project["id"], weeks=2))
        assert in_utc["days"][:2] == [1, 0]

        in_zurich = week_of(
            self._ledger(client, auth_headers, project["id"], weeks=2, tz="Europe/Zurich")
        )
        assert in_zurich["days"][:2] == [0, 1]
        assert in_zurich["worked"] == in_utc["worked"] == 1

    def test_side_project_carries_the_goal_and_the_hours_only(self, client, auth_headers):
        project = _create_project(client, auth_headers, weekly_goal=5)
        monday = self._this_monday()
        _log(client, auth_headers, project["id"], f"{monday}T09:00:00+00:00", 90)

        ledger = self._ledger(client, auth_headers, project["id"], weeks=2)

        assert (ledger["since"], ledger["totals"]) == (None, None)
        assert all(
            (w["contract_expected"], w["balance_end"], w["notes"]) == (None, None, [])
            for w in ledger["weeks"]
        )
        assert ledger["weeks"][0]["effective_goal"] == 5
        assert ledger["weeks"][0]["worked"] == 1.5

    def test_someone_elses_project_is_404(self, client, auth_headers, other_auth_headers):
        mine = _day_job(client, auth_headers)
        resp = client.get(f"/api/projects/{mine['id']}/ledger", headers=other_auth_headers)
        assert resp.status_code == 404, resp.text
        assert resp.json()["code"] == "NOT_FOUND"
        resp = client.get("/api/projects/not-an-id/ledger", headers=auth_headers)
        assert resp.status_code == 404, resp.text
        assert resp.json()["code"] == "NOT_FOUND"


# 80 % of 42 h: 6.72 h a day, which a day worked to the second rounds to
# −0.0 against.
PART_TIME_80 = [
    {
        "effective_from": CONTRACT_START,
        "schedule_type": "part_time",
        "full_time_hours": 42,
        "percentage": 0.8,
    }
]


class TestTimesheetAPI:
    """GET /api/projects/{id}/timesheet.csv — a day job's month as a CSV. The
    assembly is tested on fixed dates in `test_timesheet.py`; this is the
    wire: the file's shape, the -0.00 a day worked to contract would print,
    the read over the contract's whole life, the timezone, the refusals.
    Only last month and the month before are asked for: both are always
    finished and inside CONTRACT_START, so no test breaks on the 1st."""

    @staticmethod
    def _month(back: int) -> date:
        """The 1st of the month `back` months before the current one, in UTC."""
        first = datetime.now(UTC).date().replace(day=1)
        for _ in range(back):
            first = (first - timedelta(days=1)).replace(day=1)
        return first

    @staticmethod
    def _get(client, headers, project_id: str, month: str | None, **params):
        query = {} if month is None else {"month": month}
        return client.get(
            f"/api/projects/{project_id}/timesheet.csv",
            params={**query, **params},
            headers=headers,
        )

    def _rows(self, client, headers, project_id: str, month: date, **params) -> list[list[str]]:
        resp = self._get(client, headers, project_id, month.strftime("%Y-%m"), **params)
        assert resp.status_code == 200, resp.text
        return list(csv.reader(io.StringIO(resp.text)))

    @staticmethod
    def _by_date(rows: list[list[str]]) -> dict[str, dict[str, str]]:
        header = rows[0]
        return {row[0]: dict(zip(header, row, strict=True)) for row in rows[1:]}

    @staticmethod
    def _first_weekday(month: date) -> date:
        day = month
        while day.weekday() >= 5:
            day += timedelta(days=1)
        return day

    def test_the_month_as_csv_a_row_per_day(self, client, auth_headers):
        project = _day_job(client, auth_headers, opening_balance_hours=2.5)
        month = self._month(1)
        resp = self._get(client, auth_headers, project["id"], month.strftime("%Y-%m"))

        assert resp.status_code == 200, resp.text
        assert resp.headers["content-type"].startswith("text/csv")
        assert resp.headers["content-disposition"] == "attachment"
        rows = list(csv.reader(io.StringIO(resp.text)))
        assert rows[0] == [
            "date",
            "weekday",
            "expected",
            "worked",
            "difference",
            "holiday",
            "absence",
            "half_day",
            "adjustment",
            "adjusted",
            "balance",
        ]
        assert rows[1][0] == "brought forward"
        assert rows[-1][0] == "total"
        days = [row[0] for row in rows[2:-1]]
        assert days[0] == month.isoformat()
        assert [date.fromisoformat(d) for d in days] == [
            month + timedelta(days=n) for n in range(len(days))
        ]
        assert (date.fromisoformat(days[-1]) + timedelta(days=1)).day == 1
        assert {len(row) for row in rows} == {11}

    def test_a_day_worked_to_contract_differs_by_0_00(self, client, auth_headers):
        project = _day_job(client, auth_headers, terms=PART_TIME_80)
        day = self._first_weekday(self._month(1))
        begun = datetime(day.year, day.month, day.day, 9, tzinfo=UTC)
        resp = client.post(
            "/api/beats/",
            json={
                "project_id": project["id"],
                "start": begun.isoformat(),
                "end": (begun + timedelta(seconds=24192)).isoformat(),
            },
            headers=auth_headers,
        )
        assert resp.status_code == 201, resp.text

        rows = self._rows(client, auth_headers, project["id"], self._month(1))
        row = self._by_date(rows)[day.isoformat()]

        assert (row["expected"], row["worked"], row["difference"]) == ("6.72", "6.72", "0.00")

    def test_a_month_brings_forward_what_the_one_before_carried(self, client, auth_headers):
        # Work logged before both months and in each, and a payout in the
        # later one: the month before's close is last month's opening only if
        # the read runs over the contract's whole life, not the month's. The
        # month before also has an absence, an adjustment and a company
        # holiday, one for each read besides the beats: any of them read from
        # the later month's 1st would move its brought-forward figure.
        before, last = self._month(2), self._month(1)
        weekdays = [d for d in (before + timedelta(days=n) for n in range(28)) if d.weekday() < 5]
        worked_day, off_day, adjusted_day, company_day = weekdays[:4]
        project = _day_job(
            client,
            auth_headers,
            opening_balance_hours=1.25,
            company_holidays=[{"date": company_day.isoformat(), "name": "Founders' Day"}],
        )
        payday = self._first_weekday(last)
        _log(client, auth_headers, project["id"], f"{CONTRACT_START}T09:00:00+00:00", 300)
        _log(client, auth_headers, project["id"], f"{worked_day}T09:00:00+00:00", 600)
        _log(client, auth_headers, project["id"], f"{payday}T09:00:00+00:00", 450)
        resp = client.post(
            f"/api/projects/{project['id']}/absences",
            json={"date": off_day.isoformat(), "type": "vacation"},
            headers=auth_headers,
        )
        assert resp.status_code == 201, resp.text
        for day, hours in ((adjusted_day, 2.0), (payday, -3.5)):
            resp = client.post(
                f"/api/projects/{project['id']}/adjustments",
                params={"tz": "UTC"},
                json={"date": day.isoformat(), "kind": "delta", "hours": hours},
                headers=auth_headers,
            )
            assert resp.status_code == 201, resp.text

        earlier = self._rows(client, auth_headers, project["id"], before)
        later = self._rows(client, auth_headers, project["id"], last)

        assert earlier[-1][-1] == later[1][-1]
        row = self._by_date(later)[payday.isoformat()]
        assert (row["adjustment"], row["adjusted"]) == ("delta", "-3.50")
        total = dict(zip(later[0], later[-1], strict=True))
        assert total["adjusted"] == "-3.50"
        moved = float(total["worked"]) - float(total["expected"]) + float(total["adjusted"])
        assert float(later[1][-1]) + moved == pytest.approx(float(total["balance"]), abs=0.025)

    def test_a_company_holiday_is_named_as_one_not_as_typed(self, client, auth_headers):
        project = _day_job(client, auth_headers)
        day = self._first_weekday(self._month(1))
        _put_contract(
            client,
            auth_headers,
            project["id"],
            company_holidays=[{"date": day.isoformat(), "name": "Founders' Day"}],
        )

        rows = self._rows(client, auth_headers, project["id"], self._month(1))

        row = self._by_date(rows)[day.isoformat()]
        assert (row["holiday"], row["expected"]) == ("company holiday", "0.00")
        assert not any("Founders" in cell for r in rows for cell in r)

    def test_days_follow_the_request_timezone(self, client, auth_headers):
        project = _day_job(client, auth_headers)
        day = self._month(1) + timedelta(days=9)
        # 23:30 UTC, which in Zürich is already the next day.
        _log(client, auth_headers, project["id"], f"{day}T23:30:00+00:00", 60)
        next_day = (day + timedelta(days=1)).isoformat()

        in_utc = self._by_date(self._rows(client, auth_headers, project["id"], self._month(1)))
        in_zurich = self._by_date(
            self._rows(client, auth_headers, project["id"], self._month(1), tz="Europe/Zurich")
        )

        assert (in_utc[day.isoformat()]["worked"], in_utc[next_day]["worked"]) == ("1.00", "0.00")
        assert (in_zurich[day.isoformat()]["worked"], in_zurich[next_day]["worked"]) == (
            "0.00",
            "1.00",
        )

    def test_a_side_project_or_a_day_job_without_a_contract_is_409(self, client, auth_headers):
        month = self._month(1).strftime("%Y-%m")
        side = _create_project(client, auth_headers)
        resp = self._get(client, auth_headers, side["id"], month)
        assert resp.status_code == 409, resp.text
        assert resp.json()["code"] == "NOT_A_DAY_JOB"
        bare = _create_project(client, auth_headers, kind="day_job")
        resp = self._get(client, auth_headers, bare["id"], month)
        assert resp.status_code == 409, resp.text
        assert resp.json()["code"] == "NO_CONTRACT"

    @pytest.mark.parametrize("which", ["next", "before the start"])
    def test_a_month_without_a_finished_day_in_the_contract_is_409(
        self, client, auth_headers, which
    ):
        project = _day_job(client, auth_headers)
        if which == "next":
            month = (self._month(0) + timedelta(days=31)).strftime("%Y-%m")
        else:
            month = "2025-12"
        resp = self._get(client, auth_headers, project["id"], month)
        assert resp.status_code == 409, resp.text
        assert resp.json()["code"] == "OUTSIDE_CONTRACT"

    @pytest.mark.parametrize("month", ["2026-13", "2026-9", "0000-01", "2026-09-01", None])
    def test_a_month_that_is_not_yyyy_mm_is_422_naming_it(self, client, auth_headers, month):
        project = _day_job(client, auth_headers)
        resp = self._get(client, auth_headers, project["id"], month)
        assert resp.status_code == 422, resp.text
        body = resp.json()
        assert body["code"] == "VALIDATION_ERROR"
        assert [f["path"] for f in body["fields"]] == ["month"]

    def test_someone_elses_project_is_404(self, client, auth_headers, other_auth_headers):
        mine = _day_job(client, auth_headers)
        resp = self._get(client, other_auth_headers, mine["id"], self._month(1).strftime("%Y-%m"))
        assert resp.status_code == 404, resp.text
        assert resp.json()["code"] == "NOT_FOUND"


class TestVacationAPI:
    """GET /api/projects/{id}/vacation. The arithmetic is tested on fixed
    dates in `test_vacation.py`, and which year is the default in
    `test_project_service.py` at a fixed instant; this is the wire."""

    @staticmethod
    def _vacation(client, headers, project_id: str, **params):
        return client.get(f"/api/projects/{project_id}/vacation", params=params, headers=headers)

    @staticmethod
    def _off(client, headers, project_id: str, day: str, kind: str, **fields) -> None:
        resp = client.post(
            f"/api/projects/{project_id}/absences",
            json={"date": day, "type": kind, **fields},
            headers=headers,
        )
        assert resp.status_code in (200, 201), resp.text

    def test_a_year_reads_the_opening_then_the_carry(self, client, auth_headers):
        # From the opening on Monday 2 March 2026 with 12 days left: Tuesday
        # costs a day, Wednesday is the company's holiday and costs none,
        # Thursday's half day costs ½, and Friday's sick day is not leave.
        project = _day_job(client, auth_headers)
        _put_contract(
            client, auth_headers, project["id"], company_holidays=[COMPANY_DAY], vacation=VACATION
        )
        for day, kind, fields in [
            ("2026-03-03", "vacation", {}),
            (COMPANY_DAY["date"], "vacation", {}),
            ("2026-03-05", "vacation", {"half_day": True}),
            ("2026-03-06", "sick", {}),
        ]:
            self._off(client, auth_headers, project["id"], day, kind, **fields)

        resp = self._vacation(client, auth_headers, project["id"], year=2026)
        assert resp.status_code == 200, resp.text
        assert resp.json() == {
            "year": 2026,
            "accrued": None,
            "carried_in": 0,
            "available": 12,
            "booked": 1.5,
            "remaining": 10.5,
        }
        resp = self._vacation(client, auth_headers, project["id"], year=2027)
        assert resp.status_code == 200, resp.text
        assert resp.json() == {
            "year": 2027,
            "accrued": 25,
            "carried_in": 10.5,
            "available": 35.5,
            "booked": 0,
            "remaining": 35.5,
        }

    def test_a_vacation_recorded_moves_booked(self, client, auth_headers):
        project = _day_job(client, auth_headers, vacation=VACATION)
        before = self._vacation(client, auth_headers, project["id"], year=2026).json()

        self._off(client, auth_headers, project["id"], "2026-09-01", "vacation")

        after = self._vacation(client, auth_headers, project["id"], year=2026).json()
        assert (before["booked"], after["booked"]) == (0, 1)
        assert after["remaining"] == before["remaining"] - 1

    def test_a_year_before_the_opening_is_409_naming_the_range(self, client, auth_headers):
        project = _day_job(client, auth_headers, ended_on="2028-06-30", vacation=VACATION)
        resp = self._vacation(client, auth_headers, project["id"], year=2025)
        assert resp.status_code == 409, resp.text
        assert resp.json()["code"] == "VACATION_YEAR_OUT_OF_RANGE"
        assert resp.json()["detail"] == "Vacation is counted from 2026 through 2028"
        resp = self._vacation(client, auth_headers, project["id"], year=2029)
        assert resp.status_code == 409, resp.text

    def test_a_contract_without_an_entitlement_is_409(self, client, auth_headers):
        project = _day_job(client, auth_headers)
        resp = self._vacation(client, auth_headers, project["id"])
        assert resp.status_code == 409, resp.text
        assert resp.json()["code"] == "NO_VACATION_ENTITLEMENT"

    def test_a_day_job_without_a_contract_is_409(self, client, auth_headers):
        project = _create_project(client, auth_headers, kind="day_job")
        resp = self._vacation(client, auth_headers, project["id"])
        assert resp.status_code == 409, resp.text
        assert resp.json()["code"] == "NO_CONTRACT"

    def test_a_side_project_is_409(self, client, auth_headers):
        project = _create_project(client, auth_headers)
        resp = self._vacation(client, auth_headers, project["id"])
        assert resp.status_code == 409, resp.text
        assert resp.json()["code"] == "NOT_A_DAY_JOB"

    def test_a_malformed_project_id_is_404(self, client, auth_headers):
        resp = self._vacation(client, auth_headers, "not-an-id")
        assert resp.status_code == 404, resp.text
        assert resp.json()["code"] == "NOT_FOUND"


class TestAbsencesAPI:
    """/api/projects/{id}/absences — scoping and the delete."""

    def test_absences_are_scoped_to_the_user(self, client, auth_headers, other_auth_headers):
        mine = _day_job(client, auth_headers)
        other = other_auth_headers
        url = f"/api/projects/{mine['id']}/absences"

        # Someone else's project does not exist to them: 404, never 403.
        resp = client.post(url, json={"date": "2026-03-04", "type": "sick"}, headers=other)
        assert resp.status_code == 404, resp.text
        assert client.get(url, headers=other).status_code == 404

        # Nor can they reach one of mine by id through a day job of their own.
        created = client.post(
            url, json={"date": "2026-03-04", "type": "sick"}, headers=auth_headers
        ).json()
        theirs = _day_job(client, other)
        resp = client.delete(
            f"/api/projects/{theirs['id']}/absences/{created['id']}", headers=other
        )
        assert resp.status_code == 404, resp.text
        assert [a["id"] for a in client.get(url, headers=auth_headers).json()] == [created["id"]]

    def test_delete_is_204_and_then_gone(self, client, auth_headers):
        project = _day_job(client, auth_headers)
        url = f"/api/projects/{project['id']}/absences"
        created = client.post(
            url, json={"date": "2026-03-04", "type": "other"}, headers=auth_headers
        ).json()
        assert created["project_id"] == project["id"]

        resp = client.delete(f"{url}/{created['id']}", headers=auth_headers)
        assert resp.status_code == 204, resp.text
        assert client.get(url, headers=auth_headers).json() == []
        resp = client.delete(f"{url}/{created['id']}", headers=auth_headers)
        assert resp.status_code == 404, resp.text
        assert resp.json()["code"] == "NOT_FOUND"

    def test_delete_is_scoped_to_the_project_in_the_path(self, client, auth_headers):
        # Two day jobs of one user: an absence on the first is not reachable
        # through the second's URL, so the 404 means "not on this project".
        first = _day_job(client, auth_headers)
        second = _day_job(client, auth_headers)
        created = client.post(
            f"/api/projects/{first['id']}/absences",
            json={"date": "2026-03-04", "type": "sick"},
            headers=auth_headers,
        ).json()
        resp = client.delete(
            f"/api/projects/{second['id']}/absences/{created['id']}", headers=auth_headers
        )
        assert resp.status_code == 404, resp.text
        listed = client.get(f"/api/projects/{first['id']}/absences", headers=auth_headers).json()
        assert [a["id"] for a in listed] == [created["id"]]

    def test_absence_on_a_side_project_is_409(self, client, auth_headers):
        project = _create_project(client, auth_headers)
        resp = client.post(
            f"/api/projects/{project['id']}/absences",
            json={"date": "2026-03-04", "type": "vacation"},
            headers=auth_headers,
        )
        assert resp.status_code == 409, resp.text
        assert resp.json()["code"] == "NOT_A_DAY_JOB"


class TestAdjustmentsAPI:
    """/api/projects/{id}/adjustments — the write side of the ledger, and what
    the balance makes of it on the two reads. The arithmetic is tested on
    fixed dates in `test_contracts.py` and `test_ledger.py`, and whose today
    the date rule reads in `test_project_service.py`; this is the wire."""

    @staticmethod
    def _last_monday() -> date:
        today = datetime.now(UTC).date()
        return today - timedelta(days=today.weekday() + 7)

    @staticmethod
    def _post(client, headers, project_id: str, tz: str | None = "UTC", **body):
        params = {} if tz is None else {"tz": tz}
        return client.post(
            f"/api/projects/{project_id}/adjustments", params=params, json=body, headers=headers
        )

    def _record(self, client, headers, project_id: str, **body) -> dict:
        resp = self._post(client, headers, project_id, **body)
        assert resp.status_code == 201, resp.text
        return resp.json()

    @staticmethod
    def _ledger(client, headers, project_id: str) -> dict:
        resp = client.get(
            f"/api/projects/{project_id}/ledger", params={"weeks": 2}, headers=headers
        )
        assert resp.status_code == 200, resp.text
        return resp.json()

    def test_a_payout_moves_the_balance_and_shows_in_its_week(self, client, auth_headers):
        project = _day_job(client, auth_headers, opening_balance_hours=10)
        monday = self._last_monday().isoformat()

        created = self._record(
            client, auth_headers, project["id"], date=monday, kind="delta", hours=-4, note="paid"
        )

        assert created == {
            "id": created["id"],
            "project_id": project["id"],
            "date": monday,
            "kind": "delta",
            "hours": -4,
            "note": "paid",
        }
        resp = client.get(f"/api/projects/{project['id']}/contract/week", headers=auth_headers)
        assert resp.status_code == 200, resp.text
        week = resp.json()
        assert week["balance_adjusted"] == -4
        proof = (
            week["balance_opening"]
            + week["balance_worked"]
            - week["balance_expected_through"]
            + week["balance_adjusted"]
        )
        assert proof == pytest.approx(week["balance"], abs=0.025)
        ledger = self._ledger(client, auth_headers, project["id"])
        assert ledger["totals"]["adjusted"] == -4
        assert ledger["totals"]["balance"] == week["balance"]
        assert ledger["weeks"][0]["adjustments"] == []
        assert ledger["weeks"][1]["adjustments"] == [
            {
                "id": created["id"],
                "date": monday,
                "kind": "delta",
                "hours": -4,
                "note": "paid",
                "applied": -4,
            }
        ]
        assert ledger["ended_balance"] is None

    def test_a_second_post_on_a_date_replaces_the_first(self, client, auth_headers):
        # Two writes, one record: the unique index the fake cannot see.
        project = _day_job(client, auth_headers)
        monday = self._last_monday().isoformat()
        first = self._record(
            client, auth_headers, project["id"], date=monday, kind="delta", hours=-4, note="x"
        )
        second = self._record(
            client, auth_headers, project["id"], date=monday, kind="reset", hours=0
        )

        assert second["id"] == first["id"]
        (adjustment,) = self._ledger(client, auth_headers, project["id"])["weeks"][1]["adjustments"]
        assert (adjustment["kind"], adjustment["hours"], adjustment["note"]) == ("reset", 0, None)

    def test_without_a_balance_there_is_nothing_to_adjust(self, client, auth_headers):
        monday = self._last_monday().isoformat()
        side = _create_project(client, auth_headers)
        resp = self._post(client, auth_headers, side["id"], date=monday, kind="delta", hours=1)
        assert resp.status_code == 409, resp.text
        assert resp.json()["code"] == "NOT_A_DAY_JOB"

        no_contract = _create_project(client, auth_headers, kind="day_job")
        resp = self._post(
            client, auth_headers, no_contract["id"], date=monday, kind="delta", hours=1
        )
        assert resp.status_code == 409, resp.text
        assert resp.json()["code"] == "NO_CONTRACT"

    @pytest.mark.parametrize(
        "day",
        [date(2026, 1, 4), datetime.now(UTC).date() + timedelta(days=2)],
        ids=["before the first term", "after today"],
    )
    def test_a_date_outside_the_balance_is_409(self, client, auth_headers, day):
        project = _day_job(client, auth_headers)
        resp = self._post(
            client, auth_headers, project["id"], date=day.isoformat(), kind="cap", hours=0
        )
        assert resp.status_code == 409, resp.text
        assert resp.json()["code"] == "ADJUSTMENT_OUTSIDE_BALANCE"

    @pytest.mark.parametrize("hours", [0, True, "3"], ids=["zero", "a bool", "a string"])
    def test_a_body_that_means_nothing_is_422_naming_hours(self, client, auth_headers, hours):
        # `true` once read as a 1 h payout: lax validation takes a bool for a number.
        project = _day_job(client, auth_headers)
        monday = self._last_monday().isoformat()
        resp = self._post(
            client, auth_headers, project["id"], date=monday, kind="delta", hours=hours
        )
        assert resp.status_code == 422, resp.text
        assert [f["path"] for f in resp.json()["fields"]] == ["hours"]

    def test_tz_is_required(self, client, auth_headers):
        project = _day_job(client, auth_headers)
        monday = self._last_monday().isoformat()
        resp = self._post(
            client, auth_headers, project["id"], tz=None, date=monday, kind="delta", hours=1
        )
        assert resp.status_code == 422, resp.text
        assert [f["path"] for f in resp.json()["fields"]] == ["tz"]

    def test_delete_is_204_then_404_and_scoped_to_the_project(
        self, client, auth_headers, other_auth_headers
    ):
        project = _day_job(client, auth_headers)
        other_job = _day_job(client, auth_headers)
        monday = self._last_monday().isoformat()
        created = self._record(
            client, auth_headers, project["id"], date=monday, kind="delta", hours=2
        )
        url = f"/api/projects/{project['id']}/adjustments"

        for headers, path in [
            (auth_headers, f"/api/projects/{other_job['id']}/adjustments/{created['id']}"),
            (other_auth_headers, f"{url}/{created['id']}"),
            (auth_headers, f"{url}/{'0' * 24}"),
            (auth_headers, f"{url}/not-an-id"),
        ]:
            resp = client.delete(path, headers=headers)
            assert resp.status_code == 404, (path, resp.text)

        resp = client.delete(f"{url}/{created['id']}", headers=auth_headers)
        assert resp.status_code == 204, resp.text
        assert self._ledger(client, auth_headers, project["id"])["weeks"][1]["adjustments"] == []
        resp = client.delete(f"{url}/{created['id']}", headers=auth_headers)
        assert resp.status_code == 404, resp.text
        assert resp.json()["code"] == "NOT_FOUND"

    def test_a_first_term_moved_past_an_adjustment_is_409(self, client, auth_headers):
        project = _day_job(client, auth_headers)
        self._record(client, auth_headers, project["id"], date="2026-02-02", kind="delta", hours=1)
        later = [{**FULL_TIME[0], "effective_from": "2026-02-09"}]

        resp = client.put(
            f"/api/projects/{project['id']}/contract", json={"terms": later}, headers=auth_headers
        )

        assert resp.status_code == 409, resp.text
        assert resp.json()["code"] == "ADJUSTMENT_BEFORE_START"

    def test_a_rename_keeps_them_and_a_kind_change_takes_them(self, client, auth_headers):
        project = _day_job(client, auth_headers)
        monday = self._last_monday().isoformat()
        self._record(client, auth_headers, project["id"], date=monday, kind="delta", hours=1)

        def put(**fields) -> None:
            resp = client.put(
                "/api/projects/",
                json={"id": project["id"], "name": "Renamed", **fields},
                headers=auth_headers,
            )
            assert resp.status_code == 200, resp.text

        # The drawer resends the whole contract on every edit.
        put(kind="day_job", contract={"terms": FULL_TIME})
        assert (
            len(self._ledger(client, auth_headers, project["id"])["weeks"][1]["adjustments"]) == 1
        )

        put(kind="side_project")
        put(kind="day_job", contract={"terms": FULL_TIME})
        ledger = self._ledger(client, auth_headers, project["id"])
        assert ledger["weeks"][1]["adjustments"] == []
        assert ledger["totals"]["adjusted"] == 0


class TestHolidayRegionsAPI:
    def test_regions_are_listed_and_cacheable(self, client, auth_headers):
        resp = client.get("/api/meta/holiday-regions", headers=auth_headers)
        assert resp.status_code == 200, resp.text
        # `public` is the decision — a shared cache may keep it despite the
        # Authorization header. The TTL is configuration and not restated.
        assert "public" in resp.headers["cache-control"]
        regions = resp.json()
        with_subdivisions = next(r for r in regions if r["subdivisions"])
        assert set(with_subdivisions) == {"code", "name", "subdivisions"}
        assert set(with_subdivisions["subdivisions"][0]) == {"code", "name"}

    def test_regions_need_a_session(self, client):
        assert client.get("/api/meta/holiday-regions").status_code == 401


class TestRegionHolidaysAPI:
    """The calendar of a region no contract names yet — what the settings
    form reads before a region change is saved."""

    @staticmethod
    def _holidays(client, headers, **params) -> list[dict]:
        resp = client.get("/api/meta/holidays", params=params, headers=headers)
        assert resp.status_code == 200, resp.text
        return resp.json()

    def test_a_region_is_listed_by_date_and_name_without_a_contract(self, client, auth_headers):
        resp = client.get(
            "/api/meta/holidays",
            params={"country": "GB", "subdivision": "ENG", "year": 2026},
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        assert "public" in resp.headers["cache-control"]
        holidays = resp.json()
        assert {"date": EASTER_MONDAY, "name": "Easter Monday"} in holidays
        assert all(set(h) == {"date", "name"} and h["date"].startswith("2026-") for h in holidays)
        assert [h["date"] for h in holidays] == sorted(h["date"] for h in holidays)

    def test_the_subdivision_is_part_of_the_region(self, client, auth_headers):
        # What the settings form compares: England and Scotland disagree on
        # Easter Monday and on Saint Andrew's Day.
        england = self._holidays(client, auth_headers, country="GB", subdivision="ENG", year=2026)
        scotland = self._holidays(client, auth_headers, country="GB", subdivision="SCT", year=2026)
        assert EASTER_MONDAY in {h["date"] for h in england}
        assert EASTER_MONDAY not in {h["date"] for h in scotland}
        assert "2026-11-30" in {h["date"] for h in scotland}
        assert "2026-11-30" not in {h["date"] for h in england}

    @pytest.mark.parametrize(
        "params", [{"country": "XX"}, {"country": "GB", "subdivision": "XX"}], ids=str
    )
    def test_an_unknown_region_is_400_with_code(self, client, auth_headers, params):
        resp = client.get(
            "/api/meta/holidays", params={**params, "year": 2026}, headers=auth_headers
        )
        assert resp.status_code == 400, resp.text
        assert resp.json()["code"] == "UNKNOWN_HOLIDAY_REGION"

    def test_the_year_is_required(self, client, auth_headers):
        resp = client.get("/api/meta/holidays", params={"country": "GB"}, headers=auth_headers)
        assert resp.status_code == 422, resp.text
        assert "year" in resp.json()["fields"][0]["path"]


# --- Billing: clients, project billing, billable overrides, the month ---

# March 2026 has ended whenever this runs, so its report is the whole month
# and fixed dates keep it independent of the day. The gate tests need "before
# this month" and "this month" instead, worked out from today in UTC, the
