"""A day job's work contract over HTTP: the contract itself and the week
(docs/work-contracts.md).

Split out of `test_api.py` at the ceiling in roadmaps/file-sizes.md; the
harness is `conftest.py`'s and the shared fixtures `api_helpers.py`'s.
"""

from datetime import UTC, date, datetime, timedelta

import pytest

from api_helpers import (
    COMPANY_DAY,
    CONTRACT_START,
    EASTER_MONDAY,
    FULL_TIME,
    VACATION,
    WEEK,
    _create_project,
    _day_job,
    _log,
    _put_contract,
)


class TestContractAPI:
    """`kind` and `contract` on the project routes, and the contract replace."""

    def test_invalid_term_is_422_naming_the_term(self, client, auth_headers):
        # A custom term without weekly_hours: the domain validator's message,
        # at the term's path, in the envelope's `fields`.
        resp = client.post(
            "/api/projects/",
            json={
                "name": "bad term",
                "kind": "day_job",
                "contract": {
                    "terms": [{"effective_from": CONTRACT_START, "schedule_type": "custom"}]
                },
            },
            headers=auth_headers,
        )
        assert resp.status_code == 422, resp.text
        body = resp.json()
        assert body["code"] == "VALIDATION_ERROR"
        assert [f["path"] for f in body["fields"]] == ["contract.terms.0"]
        message = body["fields"][0]["message"]
        assert "weekly_hours" in message
        # The UI shows this sentence as is; Pydantic's "Value error, " comes off.
        assert not message.startswith("Value error")

    def test_put_without_contract_keeps_the_stored_one(self, client, auth_headers):
        # An older client that does not know `kind` or `contract` edits the
        # colour; the day job must come back a day job with its contract —
        # which is also what keeps the startup migration from being undone by
        # the first ordinary edit.
        project = _day_job(client, auth_headers)
        resp = client.put(
            "/api/projects/",
            json={"id": project["id"], "name": project["name"], "color": "#abcdef"},
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["kind"] == "day_job"
        assert resp.json()["contract"] == project["contract"]

    def test_put_with_null_contract_clears_it(self, client, auth_headers):
        project = _day_job(client, auth_headers)
        resp = client.put(
            "/api/projects/",
            json={"id": project["id"], "name": project["name"], "contract": None},
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["contract"] is None
        assert resp.json()["kind"] == "day_job"
        listed = client.get("/api/projects/", headers=auth_headers).json()
        assert next(p for p in listed if p["id"] == project["id"])["contract"] is None

    def test_contract_with_another_kind_is_409(self, client, auth_headers):
        # A contract lives only on a day job: refused on the project routes
        # as on PUT /contract, rather than stored where nothing can read it.
        resp = client.post(
            "/api/projects/",
            json={"name": "freelance", "kind": "freelance", "contract": {"terms": FULL_TIME}},
            headers=auth_headers,
        )
        assert resp.status_code == 409, resp.text
        assert resp.json()["code"] == "NOT_A_DAY_JOB"

    def test_changing_the_kind_takes_the_contract_with_it(self, client, auth_headers):
        project = _day_job(client, auth_headers)
        resp = client.put(
            "/api/projects/",
            json={"id": project["id"], "name": project["name"], "kind": "side_project"},
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["kind"] == "side_project"
        assert resp.json()["contract"] is None
        # Back to a day job it comes with nothing: no dormant contract kept.
        resp = client.put(
            "/api/projects/",
            json={"id": project["id"], "name": project["name"], "kind": "day_job"},
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["contract"] is None

    def test_replace_contract_replaces_the_whole_thing(self, client, auth_headers):
        project = _day_job(client, auth_headers)
        replacement = {
            "terms": [
                {"effective_from": CONTRACT_START, "schedule_type": "custom", "weekly_hours": 20},
                {
                    "effective_from": WEEK,
                    "schedule_type": "part_time",
                    "full_time_hours": 42,
                    "percentage": 0.8,
                },
            ],
            "holiday_country": "CH",
            "holiday_subdivision": "ZH",
            "opening_balance_hours": 12.5,
            "ended_on": None,
        }
        resp = client.put(
            f"/api/projects/{project['id']}/contract", json=replacement, headers=auth_headers
        )
        assert resp.status_code == 200, resp.text
        contract = resp.json()["contract"]
        assert contract["holiday_subdivision"] == "ZH"
        assert contract["opening_balance_hours"] == 12.5
        assert [t["effective_from"] for t in contract["terms"]] == [CONTRACT_START, WEEK]
        assert resp.json()["kind"] == "day_job"

    @pytest.mark.parametrize("opening", [-10_001, 10_001], ids=["owed", "banked"])
    def test_an_opening_past_the_bound_is_422_at_the_opening(self, client, auth_headers, opening):
        project = _day_job(client, auth_headers)
        resp = client.put(
            f"/api/projects/{project['id']}/contract",
            json={"terms": FULL_TIME, "opening_balance_hours": opening},
            headers=auth_headers,
        )
        assert resp.status_code == 422, resp.text
        body = resp.json()
        assert body["code"] == "VALIDATION_ERROR"
        assert [f["path"] for f in body["fields"]] == ["opening_balance_hours"]

    def test_replace_contract_on_a_side_project_is_409(self, client, auth_headers):
        project = _create_project(client, auth_headers)
        resp = client.put(
            f"/api/projects/{project['id']}/contract",
            json={"terms": FULL_TIME},
            headers=auth_headers,
        )
        assert resp.status_code == 409, resp.text
        assert resp.json()["code"] == "NOT_A_DAY_JOB"

    def test_unknown_region_is_400_with_code(self, client, auth_headers):
        project = _day_job(client, auth_headers)
        resp = client.put(
            f"/api/projects/{project['id']}/contract",
            json={"terms": FULL_TIME, "holiday_country": "XX"},
            headers=auth_headers,
        )
        assert resp.status_code == 400, resp.text
        assert resp.json()["code"] == "UNKNOWN_HOLIDAY_REGION"
        assert "XX" in resp.json()["detail"]

    @staticmethod
    def _send_contract(client, headers, route: str, project: dict, contract: dict) -> dict:
        """One contract write, through PUT /{id}/contract or PUT /api/projects."""
        if route == "contract":
            resp = client.put(
                f"/api/projects/{project['id']}/contract", json=contract, headers=headers
            )
        else:
            resp = client.put(
                "/api/projects/",
                json={
                    "id": project["id"],
                    "name": project["name"],
                    "kind": "day_job",
                    "contract": contract,
                },
                headers=headers,
            )
        assert resp.status_code == 200, resp.text
        return resp.json()["contract"]

    @pytest.mark.parametrize("route", ["contract", "project"])
    def test_a_contract_without_the_holiday_lists_keeps_them(self, client, auth_headers, route):
        # An SPA that predates the lists rebuilds the whole contract on every
        # term edit and sends neither: they must survive it. `[]` clears.
        project = _day_job(client, auth_headers)
        _put_contract(
            client,
            auth_headers,
            project["id"],
            holiday_country="GB",
            company_holidays=[COMPANY_DAY],
            holidays_not_given=[EASTER_MONDAY],
        )
        old_spa_body = {"terms": FULL_TIME, "holiday_country": "GB", "opening_balance_hours": 3}

        kept = self._send_contract(client, auth_headers, route, project, old_spa_body)
        assert kept["opening_balance_hours"] == 3
        assert kept["company_holidays"] == [COMPANY_DAY]
        assert kept["holidays_not_given"] == [EASTER_MONDAY]

        cleared = self._send_contract(
            client,
            auth_headers,
            route,
            project,
            {**old_spa_body, "company_holidays": [], "holidays_not_given": []},
        )
        assert (cleared["company_holidays"], cleared["holidays_not_given"]) == ([], [])

    @pytest.mark.parametrize("route", ["contract", "project"])
    def test_an_old_spa_clearing_the_region_keeps_the_project_readable(
        self, client, auth_headers, route
    ):
        # The not-given list stays behind with no region to take from: inert,
        # not invalid — every project of the user is re-validated on read.
        project = _day_job(client, auth_headers)
        _put_contract(
            client,
            auth_headers,
            project["id"],
            holiday_country="GB",
            holiday_subdivision="ENG",
            holidays_not_given=[EASTER_MONDAY],
        )

        contract = self._send_contract(
            client, auth_headers, route, project, {"terms": FULL_TIME, "holiday_country": None}
        )
        assert contract["holiday_country"] is None
        assert contract["holidays_not_given"] == [EASTER_MONDAY]

        listed = client.get("/api/projects/", headers=auth_headers)
        assert listed.status_code == 200, listed.text
        assert any(p["id"] == project["id"] for p in listed.json())
        resp = client.get(
            f"/api/projects/{project['id']}/contract/week",
            params={"week_of": EASTER_MONDAY},
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["expected"] == 40  # no region: nothing to take away

    @pytest.mark.parametrize(
        ("route", "prefix"),
        [("contract", ""), ("project", "contract.")],
        ids=["contract", "project"],
    )
    def test_a_blank_company_holiday_name_is_422_at_its_row(
        self, client, auth_headers, route, prefix
    ):
        project = _day_job(client, auth_headers)
        contract = {"terms": FULL_TIME, "company_holidays": [{"date": "2026-12-24", "name": " "}]}
        if route == "contract":
            resp = client.put(
                f"/api/projects/{project['id']}/contract", json=contract, headers=auth_headers
            )
        else:
            resp = client.put(
                "/api/projects/",
                json={"id": project["id"], "name": project["name"], "contract": contract},
                headers=auth_headers,
            )
        assert resp.status_code == 422, resp.text
        body = resp.json()
        assert body["code"] == "VALIDATION_ERROR"
        assert [f["path"] for f in body["fields"]] == [f"{prefix}company_holidays.0.name"]

    @pytest.mark.parametrize("route", ["contract", "project"])
    def test_a_contract_without_vacation_keeps_the_entitlement(self, client, auth_headers, route):
        # The SPA on lifepete.com can be older than the API: its contract
        # writes rebuild the contract field by field and never send
        # `vacation`. That must not wipe the entitlement; `null` clears it.
        project = _day_job(client, auth_headers)
        stored = _put_contract(client, auth_headers, project["id"], vacation=VACATION)
        assert stored["vacation"] == VACATION

        old_spa_body = {"terms": FULL_TIME, "opening_balance_hours": 3}
        kept = self._send_contract(client, auth_headers, route, project, old_spa_body)
        assert kept["opening_balance_hours"] == 3
        assert kept["vacation"] == VACATION

        cleared = self._send_contract(
            client, auth_headers, route, project, {**old_spa_body, "vacation": None}
        )
        assert cleared["vacation"] is None

    @pytest.mark.parametrize("route", ["contract", "project"])
    def test_moving_the_start_past_the_vacation_opening_is_409(self, client, auth_headers, route):
        # An old SPA removes the first term. The entitlement it did not send
        # is kept, so its opening would now fall before the contract starts:
        # refused, and nothing stored changes.
        project = _day_job(client, auth_headers)
        two_terms = [
            *FULL_TIME,
            {
                "effective_from": WEEK,
                "schedule_type": "part_time",
                "full_time_hours": 40,
                "percentage": 0.8,
            },
        ]
        before = _put_contract(
            client,
            auth_headers,
            project["id"],
            terms=two_terms,
            vacation={**VACATION, "opening_on": "2026-02-02"},
        )
        body = {"terms": two_terms[1:]}
        if route == "contract":
            resp = client.put(
                f"/api/projects/{project['id']}/contract", json=body, headers=auth_headers
            )
        else:
            resp = client.put(
                "/api/projects/",
                json={"id": project["id"], "name": project["name"], "contract": body},
                headers=auth_headers,
            )
        assert resp.status_code == 409, resp.text
        assert resp.json()["code"] == "VACATION_OPENING_OUTSIDE_CONTRACT"
        assert "Feb 2, 2026" in resp.json()["detail"]
        listed = client.get("/api/projects/", headers=auth_headers).json()
        assert next(p for p in listed if p["id"] == project["id"])["contract"] == before

    def test_a_vacation_figure_off_the_half_day_is_422_at_its_leaf(self, client, auth_headers):
        project = _day_job(client, auth_headers)
        resp = client.put(
            "/api/projects/",
            json={
                "id": project["id"],
                "name": project["name"],
                "contract": {"terms": FULL_TIME, "vacation": {**VACATION, "days_per_year": 25.3}},
            },
            headers=auth_headers,
        )
        assert resp.status_code == 422, resp.text
        assert [f["path"] for f in resp.json()["fields"]] == ["contract.vacation.days_per_year"]

    def test_a_capped_carry_over_without_a_cap_is_422_at_the_cap(self, client, auth_headers):
        project = _day_job(client, auth_headers)
        resp = client.put(
            f"/api/projects/{project['id']}/contract",
            json={"terms": FULL_TIME, "vacation": {**VACATION, "carry_over": "capped"}},
            headers=auth_headers,
        )
        assert resp.status_code == 422, resp.text
        assert [f["path"] for f in resp.json()["fields"]] == ["vacation.carry_over_max_days"]

    @pytest.mark.parametrize("carry_over", ["all", "none"])
    def test_a_cap_on_an_uncapped_carry_over_is_422_at_the_cap(
        self, client, auth_headers, carry_over
    ):
        # Kept, it would be a stored cap that nothing reads.
        project = _day_job(client, auth_headers)
        resp = client.put(
            f"/api/projects/{project['id']}/contract",
            json={
                "terms": FULL_TIME,
                "vacation": {**VACATION, "carry_over": carry_over, "carry_over_max_days": 5},
            },
            headers=auth_headers,
        )
        assert resp.status_code == 422, resp.text
        assert [f["path"] for f in resp.json()["fields"]] == ["vacation.carry_over_max_days"]


class TestContractWeekAPI:
    """GET /api/projects/{id}/contract/week, /holidays, and the index's this_week."""

    def _week(self, client, headers, project_id: str, **params) -> dict:
        resp = client.get(
            f"/api/projects/{project_id}/contract/week",
            params={"week_of": WEEK, **params},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        return resp.json()

    def test_week_on_a_side_project_is_409(self, client, auth_headers):
        project = _create_project(client, auth_headers)
        resp = client.get(f"/api/projects/{project['id']}/contract/week", headers=auth_headers)
        assert resp.status_code == 409, resp.text
        assert resp.json()["code"] == "NOT_A_DAY_JOB"

    def test_malformed_project_id_is_404_in_the_envelope(self, client, auth_headers):
        # Not an ObjectId at all, as opposed to a valid one nobody owns: the
        # same answer, in the same envelope, rather than a bare 500.
        resp = client.get("/api/projects/not-an-id/contract/week", headers=auth_headers)
        assert resp.status_code == 404, resp.text
        assert resp.json()["code"] == "NOT_FOUND"

    def test_week_on_a_day_job_without_a_contract_is_409(self, client, auth_headers):
        project = _create_project(client, auth_headers, kind="day_job")
        resp = client.get(f"/api/projects/{project['id']}/contract/week", headers=auth_headers)
        assert resp.status_code == 409, resp.text
        assert resp.json()["code"] == "NO_CONTRACT"

    def test_week_of_must_be_a_monday(self, client, auth_headers):
        project = _day_job(client, auth_headers)
        resp = client.get(
            f"/api/projects/{project['id']}/contract/week",
            params={"week_of": "2026-03-03"},
            headers=auth_headers,
        )
        assert resp.status_code == 422, resp.text
        body = resp.json()
        assert body["code"] == "VALIDATION_ERROR"
        assert [f["path"] for f in body["fields"]] == ["week_of"]

    def test_week_reports_seven_days_with_worked_by_day(self, client, auth_headers):
        project = _day_job(client, auth_headers)
        _log(client, auth_headers, project["id"], "2026-03-03T09:00:00+00:00", 120)
        _log(client, auth_headers, project["id"], "2026-03-04T09:00:00+00:00", 90)

        week = self._week(client, auth_headers, project["id"])

        assert week["week_of"] == WEEK
        assert [d["date"] for d in week["days"]] == [
            "2026-03-02",
            "2026-03-03",
            "2026-03-04",
            "2026-03-05",
            "2026-03-06",
            "2026-03-07",
            "2026-03-08",
        ]
        assert week["expected"] == 40
        assert week["worked"] == 3.5
        assert week["remaining"] == 36.5
        assert [d["worked"] for d in week["days"]] == [0, 2, 1.5, 0, 0, 0, 0]
        assert [d["expected"] for d in week["days"]] == [8, 8, 8, 8, 8, 0, 0]
        assert all(d["holiday"] is None and d["absence"] is None for d in week["days"])
        # Since the contract started, 3.5 h were worked against months owed.
        assert isinstance(week["balance"], float)
        assert week["balance"] < 0

    def test_remaining_ignores_hours_before_a_midweek_start(self, client, auth_headers):
        # The balance counts work from starts_on; Remaining used to subtract
        # Monday's two hours too, so the two disagreed on the first week.
        project = _day_job(
            client,
            auth_headers,
            terms=[
                {
                    "effective_from": "2026-03-04",  # the Wednesday
                    "schedule_type": "full_time",
                    "full_time_hours": 40,
                }
            ],
        )
        _log(client, auth_headers, project["id"], "2026-03-02T09:00:00+00:00", 120)
        _log(client, auth_headers, project["id"], "2026-03-05T09:00:00+00:00", 180)

        week = self._week(client, auth_headers, project["id"])

        assert week["expected"] == 24
        assert week["worked"] == 5
        assert week["remaining"] == 21
        assert week["balance_worked"] == 3

    def test_remaining_ignores_hours_after_a_midweek_end(self, client, auth_headers):
        project = _day_job(client, auth_headers, ended_on="2026-03-04")
        _log(client, auth_headers, project["id"], "2026-03-03T09:00:00+00:00", 120)
        _log(client, auth_headers, project["id"], "2026-03-05T09:00:00+00:00", 180)

        week = self._week(client, auth_headers, project["id"])

        assert week["expected"] == 24
        assert week["worked"] == 5
        assert week["remaining"] == 22

    def test_hours_under_an_objective_term_count_toward_neither_remaining_nor_balance(
        self, client, auth_headers
    ):
        # AHM-82. Full time Monday and Tuesday, objective from Wednesday,
        # full time again the Monday after, so today has a balance. Thursday's
        # 3 h were worked under a term that expects nothing: shown in
        # `worked`, subtracted from neither Remaining nor counted as overtime.
        full_time = {"schedule_type": "full_time", "full_time_hours": 40}
        project = _day_job(
            client,
            auth_headers,
            terms=[
                {"effective_from": WEEK, **full_time},
                {"effective_from": "2026-03-04", "schedule_type": "objective"},
                {"effective_from": "2026-03-09", **full_time},
            ],
        )
        _log(client, auth_headers, project["id"], "2026-03-03T09:00:00+00:00", 120)
        _log(client, auth_headers, project["id"], "2026-03-05T09:00:00+00:00", 180)

        week = self._week(client, auth_headers, project["id"])

        assert (week["expected"], week["worked"], week["remaining"]) == (16, 5, 14)
        assert week["balance_worked"] == 2

    def test_percentage_change_midweek_shows_in_days(self, client, auth_headers):
        project = _day_job(
            client,
            auth_headers,
            terms=[
                *FULL_TIME,
                {
                    "effective_from": "2026-03-04",  # the Wednesday
                    "schedule_type": "part_time",
                    "full_time_hours": 40,
                    "percentage": 0.5,
                },
            ],
        )
        week = self._week(client, auth_headers, project["id"])
        assert [d["expected"] for d in week["days"]] == [8, 8, 4, 4, 4, 0, 0]
        assert week["expected"] == 28

    def test_zero_hour_term_week_has_no_expectation(self, client, auth_headers):
        # A term of 0 hours governs — the personal goal must not resurface
        # under a sabbatical — but expects nothing by nature: null, as
        # `effective_goal` already reads it, not "Expected 0.0 h" on the card
        # and "12.0/0.0h" in the header. The balance is null on the same rule.
        project = _day_job(
            client,
            auth_headers,
            terms=[
                {"effective_from": CONTRACT_START, "schedule_type": "custom", "weekly_hours": 0}
            ],
        )
        _log(client, auth_headers, project["id"], "2026-03-03T09:00:00+00:00", 120)

        week = self._week(client, auth_headers, project["id"])

        assert (week["expected"], week["remaining"], week["balance"]) == (None, None, None)
        assert week["worked"] == 2
        assert all(d["expected"] == 0 for d in week["days"])

    def test_absence_round_trip_reduces_expected(self, client, auth_headers):
        project = _day_job(client, auth_headers)
        resp = client.post(
            f"/api/projects/{project['id']}/absences",
            json={"date": "2026-03-04", "type": "vacation", "note": "skiing"},
            headers=auth_headers,
        )
        assert resp.status_code == 201, resp.text

        week = self._week(client, auth_headers, project["id"])
        assert week["expected"] == 32
        wednesday = week["days"][2]
        assert wednesday["expected"] == 0
        assert wednesday["absence"] == {"type": "vacation", "half_day": False, "note": "skiing"}

        # Posting the same date again replaces: a full day becomes a half.
        resp = client.post(
            f"/api/projects/{project['id']}/absences",
            json={"date": "2026-03-04", "type": "sick", "half_day": True},
            headers=auth_headers,
        )
        assert resp.status_code == 201, resp.text
        week = self._week(client, auth_headers, project["id"])
        assert week["expected"] == 36
        assert week["days"][2]["absence"] == {"type": "sick", "half_day": True, "note": None}

    def test_running_timer_counts_toward_worked(self, client, auth_headers):
        project = _day_job(client, auth_headers)
        started = datetime.now(UTC) - timedelta(minutes=30)
        resp = client.post(
            f"/api/projects/{project['id']}/start",
            json={"time": started.isoformat()},
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        try:
            # The week the timer started in, so a run across the Monday
            # boundary still finds the beat where it began.
            monday = (started - timedelta(days=started.weekday())).date().isoformat()
            week = self._week(client, auth_headers, project["id"], week_of=monday)
            assert week["worked"] >= 0.5
            assert week["days"][started.weekday()]["worked"] >= 0.5
        finally:
            client.post(
                "/api/projects/stop",
                json={"time": datetime.now(UTC).isoformat()},
                headers=auth_headers,
            )

    def test_beat_crossing_midnight_belongs_to_the_local_day_it_started(self, client, auth_headers):
        project = _day_job(client, auth_headers)
        # 23:30 UTC on the Wednesday, running an hour into Thursday UTC —
        # which in Tokyo is 08:30 on the Thursday.
        _log(client, auth_headers, project["id"], "2026-03-04T23:30:00+00:00", 60)

        in_utc = self._week(client, auth_headers, project["id"])
        assert [d["worked"] for d in in_utc["days"][2:4]] == [1, 0]

        in_tokyo = self._week(client, auth_headers, project["id"], tz="Asia/Tokyo")
        assert [d["worked"] for d in in_tokyo["days"][2:4]] == [0, 1]

    def test_objective_term_has_no_expectation_and_no_balance(self, client, auth_headers):
        project = _day_job(
            client,
            auth_headers,
            terms=[{"effective_from": CONTRACT_START, "schedule_type": "objective"}],
        )
        _log(client, auth_headers, project["id"], "2026-03-03T09:00:00+00:00", 60)
        week = self._week(client, auth_headers, project["id"])
        assert week["expected"] is None
        assert week["remaining"] is None
        assert week["balance"] is None
        assert week["worked"] == 1
        assert [d["expected"] for d in week["days"]] == [0] * 7
        # No balance, no proof under it.
        assert all(
            week[field] is None
            for field in (
                "balance_as_of",
                "balance_opening",
                "balance_worked",
                "balance_expected_through",
                "balance_adjusted",
            )
        )

    def test_week_carries_the_proof_under_the_balance(self, client, auth_headers):
        # The four terms beside the balance are what the standing shows
        # under the figure; each and the balance are rounded on their own,
        # so the sum lands within 0.025 of it. Odd minutes, so the rounding
        # is exercised.
        project = _day_job(client, auth_headers, opening_balance_hours=2.25)
        _log(client, auth_headers, project["id"], "2026-03-03T09:00:00+00:00", 47)
        _log(client, auth_headers, project["id"], "2026-03-04T09:00:00+00:00", 323)

        week = self._week(client, auth_headers, project["id"])

        assert week["balance_as_of"] == datetime.now(UTC).date().isoformat()
        assert week["balance_opening"] == 2.25
        assert week["balance_worked"] == pytest.approx(round((47 + 323) / 60, 2))
        assert week["balance_expected_through"] > 0
        assert week["balance_adjusted"] == 0
        proof = (
            week["balance_opening"]
            + week["balance_worked"]
            - week["balance_expected_through"]
            + week["balance_adjusted"]
        )
        assert proof == pytest.approx(week["balance"], abs=0.025)

    def test_holidays_are_empty_without_a_region(self, client, auth_headers):
        project = _day_job(client, auth_headers)
        resp = client.get(
            f"/api/projects/{project['id']}/holidays",
            params={"year": 2026},
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json() == []

    def test_region_holidays_are_named_and_zero_their_day(self, client, auth_headers):
        # Which days GB observes is the library's business; that a listed
        # weekday holiday comes back by name in the week and costs its day
        # is ours.
        project = _day_job(client, auth_headers, holiday_country="GB", holiday_subdivision="ENG")
        resp = client.get(
            f"/api/projects/{project['id']}/holidays",
            params={"year": 2026},
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        holidays = resp.json()
        assert holidays, "a region with no holidays at all would be a wiring bug"
        assert all(h["date"].startswith("2026-") and h["name"] for h in holidays)

        # The first weekday holiday once the contract is in force: one before
        # it would cost nothing for another reason (no term yet), and the
        # holiday rule would go unexercised.
        weekday = next(
            h
            for h in holidays
            if h["date"] >= CONTRACT_START and date.fromisoformat(h["date"]).weekday() < 5
        )
        day = date.fromisoformat(weekday["date"])
        monday = (day - timedelta(days=day.weekday())).isoformat()
        week = self._week(client, auth_headers, project["id"], week_of=monday)
        reported = week["days"][day.weekday()]
        assert reported["holiday"] == weekday["name"]
        assert reported["expected"] == 0
        # Every weekday holiday in that week costs its 8 h off the 40.
        off = sum(1 for d in week["days"][:5] if d["holiday"])
        assert off >= 1
        assert week["expected"] == 40 - 8 * off

    def test_a_company_holiday_is_named_and_zeroes_its_day(self, client, auth_headers):
        project = _day_job(client, auth_headers)
        _put_contract(client, auth_headers, project["id"], company_holidays=[COMPANY_DAY])

        week = self._week(client, auth_headers, project["id"])

        wednesday = week["days"][2]
        assert (wednesday["holiday"], wednesday["expected"]) == ("Founders' Day", 0)
        assert week["expected"] == 32

    def test_a_region_holiday_not_given_is_owed_and_moves_the_balance(self, client, auth_headers):
        project = _day_job(client, auth_headers, holiday_country="GB", holiday_subdivision="ENG")
        given = self._week(client, auth_headers, project["id"], week_of=EASTER_MONDAY)
        assert given["days"][0]["holiday"] == "Easter Monday"

        _put_contract(
            client,
            auth_headers,
            project["id"],
            holiday_country="GB",
            holiday_subdivision="ENG",
            holidays_not_given=[EASTER_MONDAY],
        )
        worked = self._week(client, auth_headers, project["id"], week_of=EASTER_MONDAY)

        assert (worked["days"][0]["holiday"], worked["days"][0]["expected"]) == (None, 8)
        assert worked["expected"] == given["expected"] + 8
        assert worked["balance"] == pytest.approx(given["balance"] - 8)

    def test_holidays_list_company_days_without_a_region(self, client, auth_headers):
        project = _day_job(client, auth_headers)
        _put_contract(client, auth_headers, project["id"], company_holidays=[COMPANY_DAY])
        resp = client.get(
            f"/api/projects/{project['id']}/holidays",
            params={"year": 2026},
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json() == [{**COMPANY_DAY, "source": "company", "given": True}]

    def test_holidays_leave_out_days_not_given_unless_asked(self, client, auth_headers):
        project = _day_job(client, auth_headers)
        _put_contract(
            client,
            auth_headers,
            project["id"],
            holiday_country="GB",
            holiday_subdivision="ENG",
            company_holidays=[COMPANY_DAY],
            holidays_not_given=[EASTER_MONDAY],
        )
        url = f"/api/projects/{project['id']}/holidays"

        default = client.get(url, params={"year": 2026}, headers=auth_headers).json()
        assert EASTER_MONDAY not in {h["date"] for h in default}
        assert all(h["given"] for h in default)
        by_date = {h["date"]: h for h in default}
        assert by_date[COMPANY_DAY["date"]]["source"] == "company"
        assert by_date["2026-12-25"]["source"] == "region"

        resp = client.get(url, params={"year": 2026, "include": "not_given"}, headers=auth_headers)
        assert resp.status_code == 200, resp.text
        removed = next(h for h in resp.json() if h["date"] == EASTER_MONDAY)
        assert (removed["name"], removed["source"], removed["given"]) == (
            "Easter Monday",
            "region",
            False,
        )

        resp = client.get(url, params={"year": 2026, "include": "bogus"}, headers=auth_headers)
        assert resp.status_code == 422, resp.text
        assert [f["path"] for f in resp.json()["fields"]] == ["include"]

    def test_this_week_include_carries_contract_fields_for_day_jobs(self, client, auth_headers):
        # Both day jobs also carry a personal goal, and the governed one an
        # override on this very week; on the wire the contract must win.
        day_job = _create_project(
            client, auth_headers, kind="day_job", weekly_goal=5, contract={"terms": FULL_TIME}
        )
        this_monday = date.today() - timedelta(days=date.today().weekday())
        resp = client.put(
            f"/api/projects/{day_job['id']}/goal-overrides",
            json=[{"week_of": this_monday.isoformat(), "weekly_goal": 3}],
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        objective = _create_project(
            client,
            auth_headers,
            kind="day_job",
            weekly_goal=5,
            contract={"terms": [{"effective_from": CONTRACT_START, "schedule_type": "objective"}]},
        )
        side = _create_project(client, auth_headers, weekly_goal=5)

        listed = client.get("/api/projects/?include=this_week", headers=auth_headers).json()
        by_id = {p["id"]: p for p in listed}

        mine = by_id[day_job["id"]]
        assert mine["contract_expected"] == 40
        # The effective goal trio is the contract's too: its nominal hours, a
        # target, and no override in effect however many are stored.
        assert (mine["effective_goal"], mine["effective_goal_type"]) == (40, "target")
        assert mine["effective_goal_overridden"] is False
        # Under an objective term the personal goal is the goal, as always.
        assert by_id[objective["id"]]["effective_goal"] == 5
        assert isinstance(mine["balance"], float)
        # The trio is the contract's own and adds up among itself; it does not
        # share `weekly_minutes`' bucketing (see ProjectsListItemResponse).
        assert mine["contract_expected"] - mine["contract_worked"] == pytest.approx(
            mine["contract_remaining"]
        )
        for project in (objective, side):
            item = by_id[project["id"]]
            assert (item["contract_expected"], item["contract_remaining"], item["balance"]) == (
                None,
                None,
                None,
            )
        # Work is reported under an objective term too, as the week route does;
        # only a project of another kind has no contract figure at all.
        assert by_id[objective["id"]]["contract_worked"] == 0
        assert by_id[side["id"]]["contract_worked"] is None
        # The personal goal is untouched by the contract fields.
        assert by_id[side["id"]]["effective_goal"] == 5
