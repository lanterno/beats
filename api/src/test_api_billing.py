"""Clients, project billing, billable entries, the month report and the
billing budgets (docs/billing.md).

Split out of `test_api.py` at the ceiling in roadmaps/file-sizes.md; the
harness is `conftest.py`'s and the shared fixtures `api_helpers.py`'s.
"""

from datetime import UTC, datetime, timedelta

import pytest

from api_helpers import (
    BILLED_MONTH,
    KITE_RATE,
    _beat,
    _bill,
    _billable_from,
    _billing_budget_body,
    _billing_budgets,
    _client_body,
    _create_client,
    _create_project,
    _day_job,
    _entries,
    _freelance,
    _last_month,
    _month,
    _put_billing_budget,
    _put_client,
    _this_month,
)


class TestClientsAPI:
    """/api/clients — the write rules a client is held to beyond its model."""

    def test_create_then_read(self, client, auth_headers):
        created = _create_client(
            client,
            auth_headers,
            name="Studio Kite",
            contact_name="Mira Ott",
            contact_email="mira@kite.example",
            rates=KITE_RATE,
        )
        assert created["minor_units"] == 2
        assert created["currency_locked"] is True
        assert created["archived"] is False
        assert client.get(f"/api/clients/{created['id']}", headers=auth_headers).json() == created

        # The list is by name, whatever its case.
        _create_client(client, auth_headers, name="acme")
        names = [c["name"] for c in client.get("/api/clients/", headers=auth_headers).json()]
        assert names.index("acme") < names.index("Studio Kite")

    @pytest.mark.parametrize("rate", [85.5, True], ids=["a fraction", "a bool"])
    def test_a_rate_is_a_whole_number_of_minor_units(self, client, auth_headers, rate):
        resp = client.post(
            "/api/clients/",
            json=_client_body(rates=[{"effective_from": "2026-01-01", "rate_minor": rate}]),
            headers=auth_headers,
        )
        assert resp.status_code == 422, resp.text
        assert [f["path"] for f in resp.json()["fields"]] == ["rates.0.rate_minor"]

    def test_rates_out_of_order_are_refused_not_sorted(self, client, auth_headers):
        rates = [
            {"effective_from": "2026-03-01", "rate_minor": 9500},
            {"effective_from": "2026-01-01", "rate_minor": 8500},
        ]
        resp = client.post("/api/clients/", json=_client_body(rates=rates), headers=auth_headers)
        assert resp.status_code == 422, resp.text
        assert [f["path"] for f in resp.json()["fields"]] == ["rates"]

    def test_an_unknown_currency_is_400(self, client, auth_headers):
        resp = client.post("/api/clients/", json=_client_body(currency="EUX"), headers=auth_headers)
        assert resp.status_code == 400, resp.text
        assert resp.json()["code"] == "UNKNOWN_CURRENCY"

    def test_the_currency_changes_until_something_is_priced_in_it(self, client, auth_headers):
        # A typo made at creation is fixed before any rate exists.
        typo = _create_client(client, auth_headers, currency="USD")
        assert typo["currency_locked"] is False
        resp = _put_client(client, auth_headers, typo["id"], currency="EUR")
        assert resp.status_code == 200, resp.text
        assert resp.json()["currency"] == "EUR"

        # A rate of the client's own locks it...
        this_month = [{"effective_from": str(_this_month()), "rate_minor": 8500}]
        resp = _put_client(client, auth_headers, typo["id"], rates=this_month)
        assert resp.json()["currency_locked"] is True
        resp = _put_client(client, auth_headers, typo["id"], currency="GBP", rates=this_month)
        assert resp.status_code == 409, resp.text
        assert resp.json()["code"] == "CURRENCY_IN_USE"

        # ...and so does a rate on one of its projects.
        rateless = _create_client(client, auth_headers, name="Acme", currency="USD")
        project = _freelance(client, auth_headers)
        terms = _billable_from(_this_month(), rate_minor=12000)
        assert _bill(client, auth_headers, project["id"], rateless["id"], terms).status_code == 200
        got = client.get(f"/api/clients/{rateless['id']}", headers=auth_headers).json()
        assert got["currency_locked"] is True
        resp = _put_client(client, auth_headers, rateless["id"], name="Acme", currency="EUR")
        assert resp.status_code == 409, resp.text
        assert resp.json()["code"] == "CURRENCY_IN_USE"

    def test_a_client_with_a_billed_project_is_archived_not_deleted(self, client, auth_headers):
        kite = _create_client(client, auth_headers)
        project = _freelance(client, auth_headers)
        terms = _billable_from(_this_month())
        assert _bill(client, auth_headers, project["id"], kite["id"], terms).status_code == 200

        resp = client.delete(f"/api/clients/{kite['id']}", headers=auth_headers)
        assert resp.status_code == 409, resp.text
        assert resp.json()["code"] == "CLIENT_HAS_PROJECTS"

        resp = client.delete(
            f"/api/billing/projects/{project['id']}",
            params={"tz": "UTC", "rewrite_past": False, "remove_billing_budget": False},
            headers=auth_headers,
        )
        assert resp.status_code == 204, resp.text
        resp = client.delete(f"/api/clients/{kite['id']}", headers=auth_headers)
        assert resp.status_code == 204, resp.text
        resp = client.get(f"/api/clients/{kite['id']}", headers=auth_headers)
        assert resp.status_code == 404, resp.text
        assert resp.json()["code"] == "CLIENT_NOT_FOUND"

    def test_a_malformed_id_is_not_found(self, client, auth_headers):
        for resp in (
            client.get("/api/clients/not-an-id", headers=auth_headers),
            client.delete("/api/clients/not-an-id", headers=auth_headers),
            client.post("/api/clients/not-an-id/archive", headers=auth_headers),
        ):
            assert resp.status_code == 404, resp.text
            assert resp.json()["code"] == "CLIENT_NOT_FOUND"

    def test_a_past_rate_changes_only_with_consent(self, client, auth_headers):
        past = [{"effective_from": str(_last_month()), "rate_minor": 8500}]
        kite = _create_client(client, auth_headers, rates=past)

        raised = [{"effective_from": str(_last_month()), "rate_minor": 9000}]
        resp = _put_client(client, auth_headers, kite["id"], rates=raised)
        assert resp.status_code == 409, resp.text
        body = resp.json()
        assert body["code"] == "RETROACTIVE_CHANGE"
        assert f"{_last_month():%B %Y}" in body["detail"]
        stored = client.get(f"/api/clients/{kite['id']}", headers=auth_headers).json()
        assert stored["rates"] == past

        resp = _put_client(client, auth_headers, kite["id"], rates=raised, rewrite_past=True)
        assert resp.status_code == 200, resp.text
        assert resp.json()["rates"] == raised

        # A new rate from this month on has not been invoiced: no consent.
        then = [*raised, {"effective_from": str(_this_month()), "rate_minor": 9500}]
        resp = _put_client(client, auth_headers, kite["id"], rates=then)
        assert resp.status_code == 200, resp.text

    def test_rewrite_past_and_tz_are_required(self, client, auth_headers):
        kite = _create_client(client, auth_headers)
        resp = client.put(
            f"/api/clients/{kite['id']}",
            params={"tz": "UTC"},
            json=_client_body(),
            headers=auth_headers,
        )
        assert resp.status_code == 422, resp.text
        assert [f["path"] for f in resp.json()["fields"]] == ["rewrite_past"]
        resp = client.put(
            f"/api/clients/{kite['id']}",
            json={**_client_body(), "rewrite_past": False},
            headers=auth_headers,
        )
        assert resp.status_code == 422, resp.text
        assert [f["path"] for f in resp.json()["fields"]] == ["tz"]

    def test_an_archived_client_stays_in_the_months_it_has_hours_in(self, client, auth_headers):
        kite = _create_client(client, auth_headers, name="Archived Kite", rates=KITE_RATE)
        project = _freelance(client, auth_headers)
        terms = _billable_from("2026-03-01")
        assert _bill(client, auth_headers, project["id"], kite["id"], terms).status_code == 200
        _beat(client, auth_headers, project["id"], "2026-03-10T09:00:00", 60)

        resp = client.post(f"/api/clients/{kite['id']}/archive", headers=auth_headers)
        assert resp.status_code == 200, resp.text
        assert resp.json()["archived"] is True
        active = client.get("/api/clients/", headers=auth_headers).json()
        assert kite["id"] not in [c["id"] for c in active]
        archived = client.get("/api/clients/?archived=true", headers=auth_headers).json()
        assert kite["id"] in [c["id"] for c in archived]

        listed = {c["client_id"]: c for c in _month(client, auth_headers)["clients"]}
        assert listed[kite["id"]]["archived"] is True
        assert listed[kite["id"]]["amount_minor"] == 8500
        # A month it has no hours in does not list it.
        april = _month(client, auth_headers, "2026-04")["clients"]
        assert kite["id"] not in [c["client_id"] for c in april]


class TestProjectBillingAPI:
    """/api/billing/projects — which projects are billed, to whom, on what terms."""

    @pytest.mark.parametrize("kind", ["side_project", "day_job"])
    def test_only_a_freelance_project_is_billed(self, client, auth_headers, kind):
        kite = _create_client(client, auth_headers)
        project = (
            _day_job(client, auth_headers)
            if kind == "day_job"
            else _create_project(client, auth_headers)
        )
        resp = _bill(client, auth_headers, project["id"], kite["id"], [])
        assert resp.status_code == 409, resp.text
        assert resp.json()["code"] == "NOT_FREELANCE"

    def test_another_users_client_or_project_is_not_found(
        self, client, auth_headers, other_auth_headers
    ):
        theirs = _create_client(client, other_auth_headers)
        their_project = _freelance(client, other_auth_headers)
        mine = _create_client(client, auth_headers)
        project = _freelance(client, auth_headers)

        resp = _bill(client, auth_headers, project["id"], theirs["id"], [])
        assert resp.status_code == 404, resp.text
        assert resp.json()["code"] == "CLIENT_NOT_FOUND"
        resp = _bill(client, auth_headers, their_project["id"], mine["id"], [])
        assert resp.status_code == 404, resp.text

    def test_a_term_that_is_not_billable_takes_no_rate(self, client, auth_headers):
        kite = _create_client(client, auth_headers)
        project = _freelance(client, auth_headers)
        terms = [{"effective_from": "2026-03-01", "billable": False, "rate_minor": 9500}]
        resp = _bill(client, auth_headers, project["id"], kite["id"], terms)
        assert resp.status_code == 422, resp.text
        assert [f["path"] for f in resp.json()["fields"]] == ["terms.0.rate_minor"]

    def test_attaching_is_free_and_changing_the_past_needs_consent(self, client, auth_headers):
        kite = _create_client(client, auth_headers, rates=KITE_RATE)
        project = _freelance(client, auth_headers)

        # The first attach rewrites nothing: no figure existed before it.
        terms = _billable_from(_last_month())
        resp = _bill(client, auth_headers, project["id"], kite["id"], terms)
        assert resp.status_code == 200, resp.text
        assert resp.json() == {
            "project_id": project["id"],
            "client_id": kite["id"],
            "currency": "EUR",
            "minor_units": 2,
            "terms": [{**terms[0], "rate_minor": None}],
        }
        listed = client.get("/api/billing/projects", headers=auth_headers).json()
        assert resp.json() in listed

        # The same terms again, as a resend does, change nothing.
        assert _bill(client, auth_headers, project["id"], kite["id"], terms).status_code == 200

        own_rate = _billable_from(_last_month(), rate_minor=9500)
        resp = _bill(client, auth_headers, project["id"], kite["id"], own_rate)
        assert resp.status_code == 409, resp.text
        assert resp.json()["code"] == "RETROACTIVE_CHANGE"
        resp = _bill(client, auth_headers, project["id"], kite["id"], own_rate, rewrite_past=True)
        assert resp.status_code == 200, resp.text

        # Moving it to another client moves every past hour with it.
        other = _create_client(client, auth_headers, name="Acme", rates=KITE_RATE)
        resp = _bill(client, auth_headers, project["id"], other["id"], own_rate)
        assert resp.status_code == 409, resp.text
        assert resp.json()["code"] == "RETROACTIVE_CHANGE"

    def test_no_move_to_another_currency_once_past_hours_are_billed(self, client, auth_headers):
        euros = _create_client(client, auth_headers, rates=KITE_RATE)
        dollars = _create_client(client, auth_headers, name="Acme", currency="USD")
        project = _freelance(client, auth_headers)
        terms = _billable_from(_last_month())
        assert _bill(client, auth_headers, project["id"], euros["id"], terms).status_code == 200

        # Consent does not help: last month's euros would read as dollars.
        resp = _bill(client, auth_headers, project["id"], dollars["id"], terms, rewrite_past=True)
        assert resp.status_code == 409, resp.text
        assert resp.json()["code"] == "CURRENCY_MISMATCH"

        # Billed from this month on at the client's rate, nothing is re-denominated.
        recent = _freelance(client, auth_headers, "Recent")
        now = _billable_from(_this_month())
        assert _bill(client, auth_headers, recent["id"], euros["id"], now).status_code == 200
        resp = _bill(client, auth_headers, recent["id"], dollars["id"], now)
        assert resp.status_code == 200, resp.text
        assert resp.json()["currency"] == "USD"

        # A rate of the project's own is in its client's currency, whenever it starts.
        priced = _freelance(client, auth_headers, "Priced")
        own = _billable_from(_this_month(), rate_minor=9500)
        assert _bill(client, auth_headers, priced["id"], euros["id"], own).status_code == 200
        resp = _bill(client, auth_headers, priced["id"], dollars["id"], own)
        assert resp.status_code == 409, resp.text
        assert resp.json()["code"] == "CURRENCY_MISMATCH"

    def test_a_billed_project_keeps_its_kind(self, client, auth_headers):
        kite = _create_client(client, auth_headers)
        project = _freelance(client, auth_headers)
        terms = _billable_from(_last_month())
        assert _bill(client, auth_headers, project["id"], kite["id"], terms).status_code == 200

        edit = {"id": project["id"], "name": project["name"], "color": "#5B9CF6"}
        resp = client.put(
            "/api/projects/", json={**edit, "kind": "side_project"}, headers=auth_headers
        )
        assert resp.status_code == 409, resp.text
        assert resp.json()["code"] == "PROJECT_HAS_BILLING"
        # Any other edit goes through.
        resp = client.put("/api/projects/", json=edit, headers=auth_headers)
        assert resp.status_code == 200, resp.text
        assert resp.json()["kind"] == "freelance"

        resp = client.delete(
            f"/api/billing/projects/{project['id']}",
            params={"tz": "UTC", "rewrite_past": True, "remove_billing_budget": False},
            headers=auth_headers,
        )
        assert resp.status_code == 204, resp.text
        resp = client.put(
            "/api/projects/", json={**edit, "kind": "side_project"}, headers=auth_headers
        )
        assert resp.status_code == 200, resp.text

    def test_stopping_billing_with_past_terms_needs_consent(self, client, auth_headers):
        kite = _create_client(client, auth_headers)
        project = _freelance(client, auth_headers)
        terms = _billable_from(_last_month())
        assert _bill(client, auth_headers, project["id"], kite["id"], terms).status_code == 200
        url = f"/api/billing/projects/{project['id']}"
        params = {"tz": "UTC", "remove_billing_budget": False}

        resp = client.delete(url, params=params, headers=auth_headers)
        assert resp.status_code == 422, resp.text
        assert [f["path"] for f in resp.json()["fields"]] == ["rewrite_past"]
        resp = client.delete(url, params={**params, "rewrite_past": False}, headers=auth_headers)
        assert resp.status_code == 409, resp.text
        assert resp.json()["code"] == "RETROACTIVE_CHANGE"
        resp = client.delete(url, params={**params, "rewrite_past": True}, headers=auth_headers)
        assert resp.status_code == 204, resp.text
        listed = client.get("/api/billing/projects", headers=auth_headers).json()
        assert project["id"] not in [b["project_id"] for b in listed]
        resp = client.delete(url, params={**params, "rewrite_past": True}, headers=auth_headers)
        assert resp.status_code == 404, resp.text

    def test_a_past_entry_marked_billable_is_a_past_figure_too(self, client, auth_headers):
        # Billed from this month on, the project's one past figure is an
        # entry marked billable, at the client's rate: no term is dated
        # before this month, and moving or stopping the billing still
        # rewrites it.
        kite = _create_client(client, auth_headers, rates=KITE_RATE)
        other = _create_client(client, auth_headers, name="Other euros", rates=KITE_RATE)
        dollars = _create_client(
            client,
            auth_headers,
            name="Acme",
            currency="USD",
            rates=[{"effective_from": "2026-01-01", "rate_minor": 20000}],
        )
        project = _freelance(client, auth_headers)
        now = _billable_from(_this_month())
        assert _bill(client, auth_headers, project["id"], kite["id"], now).status_code == 200
        start = f"{_last_month() + timedelta(days=10)}T09:00:00"
        past = _beat(client, auth_headers, project["id"], start, 240)
        resp = client.put(
            f"/api/billing/entries/{past['id']}", json={"billable": True}, headers=auth_headers
        )
        assert resp.status_code == 200, resp.text
        last_month = f"{_last_month():%Y-%m}"
        before = _month(client, auth_headers, last_month)
        mine = {kite["id"], other["id"], dollars["id"]}
        assert [
            (c["name"], c["amount_minor"]) for c in before["clients"] if c["client_id"] in mine
        ] == [("Acme", 0), ("Other euros", 0), ("Studio Kite", 34000)]

        resp = _bill(client, auth_headers, project["id"], other["id"], now)
        assert resp.status_code == 409, resp.text
        assert resp.json()["code"] == "RETROACTIVE_CHANGE"
        resp = _bill(client, auth_headers, project["id"], dollars["id"], now, rewrite_past=True)
        assert resp.status_code == 409, resp.text
        assert resp.json()["code"] == "CURRENCY_MISMATCH"
        resp = client.delete(
            f"/api/billing/projects/{project['id']}",
            params={"tz": "UTC", "rewrite_past": False, "remove_billing_budget": False},
            headers=auth_headers,
        )
        assert resp.status_code == 409, resp.text
        assert resp.json()["code"] == "RETROACTIVE_CHANGE"
        assert _month(client, auth_headers, last_month) == before


class TestBillableEntriesAPI:
    """/api/billing/entries — one entry marked against its project's term,
    kept in its own collection, away from every write that replaces a beat."""

    def _billed_project(self, client, headers) -> dict:
        kite = _create_client(client, headers, rates=KITE_RATE)
        project = _freelance(client, headers)
        terms = _billable_from("2026-03-01")
        assert _bill(client, headers, project["id"], kite["id"], terms).status_code == 200
        return project

    def test_another_users_entry_is_not_found(self, client, auth_headers, other_auth_headers):
        project = self._billed_project(client, auth_headers)
        beat = _beat(client, auth_headers, project["id"], "2026-03-10T09:00:00", 60)
        for beat_id in (beat["id"], "not-an-id"):
            resp = client.put(
                f"/api/billing/entries/{beat_id}",
                json={"billable": False},
                headers=other_auth_headers,
            )
            assert resp.status_code == 404, resp.text
        assert client.get("/api/billing/entries", headers=auth_headers).json() == []

    def test_clearing_a_mark_returns_the_entry_to_its_projects_rule(self, client, auth_headers):
        project = self._billed_project(client, auth_headers)
        beat = _beat(client, auth_headers, project["id"], "2026-03-11T09:00:00", 60)
        url = f"/api/billing/entries/{beat['id']}"

        resp = client.put(url, json={"billable": False}, headers=auth_headers)
        assert resp.status_code == 200, resp.text
        assert resp.json() == {"beat_id": beat["id"], "billable": False}
        entry = _entries(_month(client, auth_headers))[beat["id"]]
        assert (entry["billable"], entry["overridden"], entry["rate_minor"]) == (False, True, None)

        assert client.delete(url, headers=auth_headers).status_code == 204
        entry = _entries(_month(client, auth_headers))[beat["id"]]
        assert (entry["billable"], entry["overridden"], entry["rate_minor"]) == (True, False, 8500)
        listed = client.get("/api/billing/entries", headers=auth_headers).json()
        assert beat["id"] not in [o["beat_id"] for o in listed]
        # Nothing left to clear is still a 204, and so is no entry at all.
        assert client.delete(url, headers=auth_headers).status_code == 204
        assert (
            client.delete("/api/billing/entries/not-an-id", headers=auth_headers).status_code == 204
        )

    def test_deleting_the_entry_deletes_its_mark(self, client, auth_headers):
        project = self._billed_project(client, auth_headers)
        beat = _beat(client, auth_headers, project["id"], "2026-03-12T09:00:00", 60)
        client.put(
            f"/api/billing/entries/{beat['id']}", json={"billable": False}, headers=auth_headers
        )

        assert client.delete(f"/api/beats/{beat['id']}", headers=auth_headers).status_code == 200
        listed = client.get("/api/billing/entries", headers=auth_headers).json()
        assert beat["id"] not in [o["beat_id"] for o in listed]

    def test_editing_or_stopping_the_entry_keeps_its_mark(self, client, auth_headers):
        project = self._billed_project(client, auth_headers)

        # PUT /api/beats/ rebuilds the beat and replaces it whole.
        beat = _beat(client, auth_headers, project["id"], "2026-03-13T09:00:00", 60)
        client.put(
            f"/api/billing/entries/{beat['id']}", json={"billable": False}, headers=auth_headers
        )
        resp = client.put(
            "/api/beats/",
            json={
                "id": beat["id"],
                "project_id": project["id"],
                "start": "2026-03-13T09:00:00+00:00",
                "end": "2026-03-13T11:00:00+00:00",
            },
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text

        # Stopping the timer replaces the running beat whole, too.
        started = client.post(
            f"/api/projects/{project['id']}/start",
            json={"time": datetime.now(UTC).isoformat()},
            headers=auth_headers,
        ).json()
        client.put(
            f"/api/billing/entries/{started['id']}", json={"billable": False}, headers=auth_headers
        )
        resp = client.post(
            "/api/projects/stop", json={"time": datetime.now(UTC).isoformat()}, headers=auth_headers
        )
        assert resp.status_code == 200, resp.text

        listed = client.get("/api/billing/entries", headers=auth_headers).json()
        marks = {o["beat_id"]: o["billable"] for o in listed}
        assert marks[beat["id"]] is False
        assert marks[started["id"]] is False


class TestBillingMonthAPI:
    """GET /api/billing/month — what each client is owed for a month."""

    def test_tz_is_required(self, client, auth_headers):
        resp = client.get(
            "/api/billing/month", params={"month": BILLED_MONTH}, headers=auth_headers
        )
        assert resp.status_code == 422, resp.text
        assert [f["path"] for f in resp.json()["fields"]] == ["tz"]

    def test_a_month_still_to_come_is_409(self, client, auth_headers):
        following = (_this_month() + timedelta(days=31)).replace(day=1)
        resp = client.get(
            "/api/billing/month",
            params={"month": f"{following:%Y-%m}", "tz": "UTC"},
            headers=auth_headers,
        )
        assert resp.status_code == 409, resp.text
        assert resp.json()["code"] == "MONTH_NOT_STARTED"

    def test_the_calendars_first_month_east_of_greenwich_is_empty(self, client, auth_headers):
        # Midnight on 1 January of year 1 in Berlin is before the first
        # instant UTC can hold; it was a 500.
        resp = client.get(
            "/api/billing/month",
            params={"month": "0001-01", "tz": "Europe/Berlin"},
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        assert (resp.json()["first"], resp.json()["clients"]) == ("0001-01-01", [])

    def test_a_month_end_to_end(self, client, auth_headers):
        kite = _create_client(client, auth_headers, rates=KITE_RATE)
        website = _freelance(client, auth_headers, "Website")
        terms = [
            {"effective_from": "2026-03-01", "billable": True},
            {"effective_from": "2026-03-16", "billable": True, "rate_minor": 9500},
        ]
        assert _bill(client, auth_headers, website["id"], kite["id"], terms).status_code == 200
        # 00:30 on 1 March in Berlin: March's, though it is February's in UTC.
        _beat(client, auth_headers, website["id"], "2026-02-28T23:30:00", 60)
        _beat(client, auth_headers, website["id"], "2026-03-10T09:00:00", 120)
        _beat(client, auth_headers, website["id"], "2026-03-20T09:00:00", 90)

        # An archived project's hours are still billed.
        old = _freelance(client, auth_headers, "Archive work")
        old_terms = _billable_from("2026-03-01")
        assert _bill(client, auth_headers, old["id"], kite["id"], old_terms).status_code == 200
        _beat(client, auth_headers, old["id"], "2026-03-05T09:00:00", 60)
        client.post(f"/api/projects/{old['id']}/archive", headers=auth_headers)

        # Freelance hours with no client, and a side project's, which billing ignores.
        logo = _freelance(client, auth_headers, "Logo refresh")
        _beat(client, auth_headers, logo["id"], "2026-03-12T09:00:00", 240)
        side = _create_project(client, auth_headers, name="Garden")
        _beat(client, auth_headers, side["id"], "2026-03-12T09:00:00", 60)

        # A timer left running on a billed project counts once it stops.
        running = _beat(client, auth_headers, website["id"], "2026-03-25T09:00:00", None)
        try:
            report = _month(client, auth_headers, tz="Europe/Berlin")
        finally:
            client.delete(f"/api/beats/{running['id']}", headers=auth_headers)

        assert (report["month"], report["first"], report["last"]) == (
            "2026-03",
            "2026-03-01",
            "2026-03-31",
        )
        [billed] = report["clients"]
        assert billed["client_id"] == kite["id"]
        assert billed["running"] is True
        keys = ("project_name", "rate_minor", "source", "first", "last", "hours", "amount_minor")
        assert [tuple(line[key] for key in keys) for line in billed["lines"]] == [
            ("Archive work", 8500, "client", "2026-03-01", "2026-03-31", 1.0, 8500),
            ("Website", 8500, "client", "2026-03-01", "2026-03-15", 3.0, 25500),
            ("Website", 9500, "project", "2026-03-16", "2026-03-31", 1.5, 14250),
        ]
        assert len(billed["entries"]) == 4
        assert (billed["billable_hours"], billed["amount_minor"]) == (5.5, 48250)
        assert report["totals"] == [
            {
                "currency": "EUR",
                "minor_units": 2,
                "billable_hours": 5.5,
                "unpriced_hours": 0.0,
                "amount_minor": 48250,
            }
        ]
        assert report["unattached"] == [
            {"project_id": logo["id"], "name": "Logo refresh", "hours": 4.0}
        ]


class TestBillingBudgetsAPI:
    """/api/billing/budgets — a limit on a client or a billed project, read
    as of today. "Today" is the real one in UTC, the timezone these send, as
    the gate tests above work it out; spent hours are logged last month, so
    a total budget from then counts them whatever the day."""

    @pytest.fixture(autouse=True)
    def _no_billing_budgets(self, mongo):
        # clean_db is class-scoped, and the read lists every budget.
        mongo.billing_budgets.delete_many({})

    def test_a_round_trip(self, client, auth_headers):
        assert _billing_budgets(client, auth_headers) == []
        kite = _create_client(client, auth_headers, rates=KITE_RATE)
        website = _freelance(client, auth_headers, "Website")
        assert (
            _bill(
                client, auth_headers, website["id"], kite["id"], _billable_from(_last_month())
            ).status_code
            == 200
        )
        _beat(client, auth_headers, website["id"], f"{_last_month()}T09:00:00", 120)

        resp = _put_billing_budget(
            client,
            auth_headers,
            "clients",
            kite["id"],
            unit="money",
            limit_hours=None,
            limit_minor=500000,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json() == {
            "scope": "client",
            "scope_id": kite["id"],
            "client_id": kite["id"],
            "currency": "EUR",
            "minor_units": 2,
            "unit": "money",
            "period": "monthly",
            "limit_hours": None,
            "limit_minor": 500000,
            "starts_on": None,
            "warn_at_percent": 80,
        }
        # A second write on the scope replaces the first, the money limit
        # included: it would be refused on every read beside a limit in hours.
        resp = _put_billing_budget(
            client, auth_headers, "clients", kite["id"], limit_hours=37.5, warn_at_percent=90
        )
        assert resp.status_code == 200, resp.text
        resp = _put_billing_budget(
            client,
            auth_headers,
            "projects",
            website["id"],
            unit="money",
            period="total",
            limit_hours=None,
            limit_minor=20000,
            starts_on=str(_last_month()),
        )
        assert resp.status_code == 200, resp.text
        assert (resp.json()["scope"], resp.json()["client_id"]) == ("project", kite["id"])
        # Another client sorts by its name, before Studio Kite.
        acme = _create_client(client, auth_headers, name="acme", currency="JPY")
        assert _put_billing_budget(client, auth_headers, "clients", acme["id"]).status_code == 200

        today = datetime.now(UTC).date()
        month_end = (_this_month() + timedelta(days=31)).replace(day=1) - timedelta(days=1)
        statuses = _billing_budgets(client, auth_headers)
        assert [(s["scope"], s["name"]) for s in statuses] == [
            ("client", "acme"),
            ("client", "Studio Kite"),
            ("project", "Website"),
        ]
        _, monthly, total = statuses
        assert {key: monthly[key] for key in monthly if key != "runs_out_on"} == {
            "scope": "client",
            "scope_id": kite["id"],
            "client_id": kite["id"],
            "name": "Studio Kite",
            "active": True,
            "currency": "EUR",
            "minor_units": 2,
            "unit": "hours",
            "period": "monthly",
            "limit_hours": 37.5,
            "limit_minor": None,
            "starts_on": None,
            "warn_at_percent": 90,
            "upcoming": False,
            "first": str(_this_month()),
            "last": str(month_end),
            "through": str(today),
            # Last month's two hours are not this month's.
            "billable_hours": 0.0,
            "unpriced_hours": 0.0,
            "amount_minor": 0,
            "remaining_hours": 37.5,
            "remaining_minor": None,
            "percent_used": 0,
            "state": "under",
            "running": None,
        }
        assert monthly["runs_out_on"] is None
        # Two hours at 85.00 EUR is 170.00 of 200.00: past the warning at 80 %.
        keys = ("first", "last", "through", "billable_hours", "amount_minor")
        assert {key: total[key] for key in keys} == {
            "first": str(_last_month()),
            "last": None,
            "through": str(today),
            "billable_hours": 2.0,
            "amount_minor": 17000,
        }
        keys = ("currency", "remaining_hours", "remaining_minor", "percent_used", "state")
        assert {key: total[key] for key in keys} == {
            "currency": "EUR",
            "remaining_hours": None,
            "remaining_minor": 3000,
            "percent_used": 85,
            "state": "near",
        }

    def test_tz_is_required(self, client, auth_headers):
        resp = client.get("/api/billing/budgets", headers=auth_headers)
        assert resp.status_code == 422, resp.text
        assert [f["path"] for f in resp.json()["fields"]] == ["tz"]

    @pytest.mark.parametrize(
        ("body", "field"),
        [
            (
                {key: value for key, value in _billing_budget_body().items() if key != "starts_on"},
                "starts_on",
            ),
            (_billing_budget_body(limit_hours=37.333), "limit_hours"),
        ],
        ids=["a key left out", "a third decimal"],
    )
    def test_a_write_is_refused_naming_its_key(self, client, auth_headers, body, field):
        kite = _create_client(client, auth_headers)
        resp = client.put(
            f"/api/billing/budgets/clients/{kite['id']}", json=body, headers=auth_headers
        )
        assert resp.status_code == 422, resp.text
        assert [f["path"] for f in resp.json()["fields"]] == [field]

    def test_another_users_scope_or_a_malformed_id_is_not_found(
        self, client, auth_headers, other_auth_headers
    ):
        theirs = _create_client(client, other_auth_headers)
        their_project = _freelance(client, other_auth_headers)
        billed = _bill(
            client,
            other_auth_headers,
            their_project["id"],
            theirs["id"],
            _billable_from(_this_month()),
        )
        assert billed.status_code == 200, billed.text

        resp = _put_billing_budget(client, auth_headers, "clients", theirs["id"])
        assert resp.status_code == 404, resp.text
        assert resp.json()["code"] == "CLIENT_NOT_FOUND"
        assert _put_billing_budget(client, auth_headers, "clients", "nope").status_code == 404
        for project_id in (their_project["id"], "nope"):
            resp = _put_billing_budget(client, auth_headers, "projects", project_id)
            assert resp.status_code == 404, resp.text
        assert _billing_budgets(client, other_auth_headers) == []

    def test_a_project_budget_needs_billing(self, client, auth_headers):
        unbilled = _freelance(client, auth_headers)
        resp = _put_billing_budget(client, auth_headers, "projects", unbilled["id"])
        assert resp.status_code == 409, resp.text
        assert resp.json()["code"] == "BILLING_BUDGET_NEEDS_BILLING"
        assert _billing_budgets(client, auth_headers) == []

    def test_a_delete_is_204_whether_or_not_there_was_one(self, client, auth_headers):
        kite = _create_client(client, auth_headers)
        website = _freelance(client, auth_headers)
        assert (
            _bill(
                client, auth_headers, website["id"], kite["id"], _billable_from(_this_month())
            ).status_code
            == 200
        )
        assert _put_billing_budget(client, auth_headers, "clients", kite["id"]).status_code == 200
        assert (
            _put_billing_budget(client, auth_headers, "projects", website["id"]).status_code == 200
        )

        for scope, scope_id in (("clients", kite["id"]), ("projects", website["id"])):
            for _ in range(2):
                resp = client.delete(
                    f"/api/billing/budgets/{scope}/{scope_id}", headers=auth_headers
                )
                assert resp.status_code == 204, resp.text
        assert _billing_budgets(client, auth_headers) == []

    def test_an_archived_scope_is_read_but_never_alerts(self, client, auth_headers):
        kite = _create_client(client, auth_headers)
        website = _freelance(client, auth_headers)
        assert (
            _bill(
                client, auth_headers, website["id"], kite["id"], _billable_from(_this_month())
            ).status_code
            == 200
        )
        assert _put_billing_budget(client, auth_headers, "clients", kite["id"]).status_code == 200
        assert (
            _put_billing_budget(client, auth_headers, "projects", website["id"]).status_code == 200
        )

        # An archived project: its own budget is quiet, its client's is not.
        client.post(f"/api/projects/{website['id']}/archive", headers=auth_headers)
        assert [s["active"] for s in _billing_budgets(client, auth_headers)] == [True, False]
        # An archived client quiets both, and a write on it is still taken.
        client.post(f"/api/clients/{kite['id']}/archive", headers=auth_headers)
        client.post(f"/api/projects/{website['id']}/unarchive", headers=auth_headers)
        assert [s["active"] for s in _billing_budgets(client, auth_headers)] == [False, False]
        resp = _put_billing_budget(client, auth_headers, "clients", kite["id"], limit_hours=10)
        assert resp.status_code == 200, resp.text

    def test_a_running_timer_is_answered_with_instants_not_figures(self, client, auth_headers):
        kite = _create_client(client, auth_headers, rates=KITE_RATE)
        website = _freelance(client, auth_headers)
        assert (
            _bill(
                client, auth_headers, website["id"], kite["id"], _billable_from(_this_month())
            ).status_code
            == 200
        )
        assert _put_billing_budget(client, auth_headers, "clients", kite["id"]).status_code == 200
        [before] = _billing_budgets(client, auth_headers)
        assert before["running"] is None

        # On the minute, so it started today in UTC whenever this runs.
        since = datetime.now(UTC).replace(second=0, microsecond=0, tzinfo=None)
        running = _beat(client, auth_headers, website["id"], since.isoformat(), None)
        try:
            [during] = _billing_budgets(client, auth_headers)
        finally:
            client.delete(f"/api/beats/{running['id']}", headers=auth_headers)

        # Nothing it has run so far is in a figure: only the instants move.
        assert {**during, "running": None} == before
        assert {key: during["running"][key] for key in ("project_id", "priced")} == {
            "project_id": website["id"],
            "priced": True,
        }
        instants = {
            key: datetime.fromisoformat(during["running"][key])
            for key in ("since", "near_at", "over_at")
        }
        # 40 h with a warning at 80 %, none of it spent: 32 h and 40 h from the start.
        begun = since.replace(tzinfo=UTC)
        assert instants == {
            "since": begun,
            "near_at": begun + timedelta(hours=32),
            "over_at": begun + timedelta(hours=40),
        }

    def test_a_money_budget_locks_its_clients_currency_where_hours_do_not(
        self, client, auth_headers
    ):
        # No rate anywhere, so only a budget could lock the currency.
        acme = _create_client(client, auth_headers, name="Acme", currency="USD")
        website = _freelance(client, auth_headers)
        terms = _billable_from(_this_month())
        assert _bill(client, auth_headers, website["id"], acme["id"], terms).status_code == 200

        def locked() -> bool:
            got = client.get(f"/api/clients/{acme['id']}", headers=auth_headers).json()
            listed = client.get("/api/clients/", headers=auth_headers).json()
            [same] = [c["currency_locked"] for c in listed if c["id"] == acme["id"]]
            assert same == got["currency_locked"]
            return got["currency_locked"]

        assert _put_billing_budget(client, auth_headers, "clients", acme["id"]).status_code == 200
        assert (
            _put_billing_budget(client, auth_headers, "projects", website["id"]).status_code == 200
        )
        assert locked() is False
        resp = _put_client(client, auth_headers, acme["id"], name="Acme", currency="EUR")
        assert resp.status_code == 200, resp.text

        money = {"unit": "money", "limit_hours": None, "limit_minor": 100000}
        for scope, scope_id in (("projects", website["id"]), ("clients", acme["id"])):
            resp = _put_billing_budget(client, auth_headers, scope, scope_id, **money)
            assert resp.status_code == 200, resp.text
            assert locked() is True
            resp = _put_client(client, auth_headers, acme["id"], name="Acme", currency="GBP")
            assert resp.status_code == 409, resp.text
            assert resp.json()["code"] == "CURRENCY_IN_USE"
            assert "billing budgets" in resp.json()["detail"]
            # Back to hours: nothing is in its currency again.
            assert _put_billing_budget(client, auth_headers, scope, scope_id).status_code == 200
            assert locked() is False

    def test_a_money_budget_keeps_its_project_in_its_currency(self, client, auth_headers):
        # Billed from this month on, at the client's rate: without a budget
        # the project moves to a client in any currency.
        kite = _create_client(client, auth_headers)
        euros = _create_client(client, auth_headers, name="Other euros")
        dollars = _create_client(client, auth_headers, name="Acme", currency="USD")
        website = _freelance(client, auth_headers)
        terms = _billable_from(_this_month())
        assert _bill(client, auth_headers, website["id"], kite["id"], terms).status_code == 200
        money = {"unit": "money", "limit_hours": None, "limit_minor": 100000}
        resp = _put_billing_budget(client, auth_headers, "projects", website["id"], **money)
        assert resp.status_code == 200, resp.text

        resp = _bill(client, auth_headers, website["id"], dollars["id"], terms, rewrite_past=True)
        assert resp.status_code == 409, resp.text
        assert resp.json()["code"] == "CURRENCY_MISMATCH"
        assert resp.json()["detail"].startswith("This project's billing budget is in EUR"), resp
        # To a client in the same currency it moves, budget and all.
        assert _bill(client, auth_headers, website["id"], euros["id"], terms).status_code == 200
        [status] = _billing_budgets(client, auth_headers)
        assert (status["client_id"], status["unit"]) == (euros["id"], "money")

        # An hours budget moves anywhere.
        resp = _put_billing_budget(client, auth_headers, "projects", website["id"])
        assert resp.status_code == 200, resp.text
        assert _bill(client, auth_headers, website["id"], dollars["id"], terms).status_code == 200
        [status] = _billing_budgets(client, auth_headers)
        assert (status["client_id"], status["currency"]) == (dollars["id"], "USD")

    def test_stopping_billing_names_the_billing_budget(self, client, auth_headers):
        kite = _create_client(client, auth_headers)
        website = _freelance(client, auth_headers, "Website")
        terms = _billable_from(_this_month())
        assert _bill(client, auth_headers, website["id"], kite["id"], terms).status_code == 200
        assert (
            _put_billing_budget(client, auth_headers, "projects", website["id"]).status_code == 200
        )
        url = f"/api/billing/projects/{website['id']}"
        params = {"tz": "UTC", "rewrite_past": False}

        def billed() -> bool:
            listed = client.get("/api/billing/projects", headers=auth_headers).json()
            return website["id"] in [b["project_id"] for b in listed]

        resp = client.delete(url, params=params, headers=auth_headers)
        assert resp.status_code == 422, resp.text
        assert [f["path"] for f in resp.json()["fields"]] == ["remove_billing_budget"]
        resp = client.delete(
            url, params={**params, "remove_billing_budget": False}, headers=auth_headers
        )
        assert resp.status_code == 409, resp.text
        assert resp.json()["code"] == "PROJECT_HAS_BILLING_BUDGET"
        assert resp.json()["detail"].startswith("Website has a billing budget"), resp.text
        assert billed()
        assert len(_billing_budgets(client, auth_headers)) == 1

        resp = client.delete(
            url, params={**params, "remove_billing_budget": True}, headers=auth_headers
        )
        assert resp.status_code == 204, resp.text
        assert not billed()
        assert _billing_budgets(client, auth_headers) == []

    def test_a_declined_past_change_keeps_the_billing_and_its_budget(
        self, client, auth_headers, mongo
    ):
        kite = _create_client(client, auth_headers)
        website = _freelance(client, auth_headers)
        terms = _billable_from(_last_month())
        assert _bill(client, auth_headers, website["id"], kite["id"], terms).status_code == 200
        assert (
            _put_billing_budget(client, auth_headers, "projects", website["id"]).status_code == 200
        )

        resp = client.delete(
            f"/api/billing/projects/{website['id']}",
            params={"tz": "UTC", "rewrite_past": False, "remove_billing_budget": True},
            headers=auth_headers,
        )

        assert resp.status_code == 409, resp.text
        assert resp.json()["code"] == "RETROACTIVE_CHANGE"
        listed = client.get("/api/billing/projects", headers=auth_headers).json()
        assert website["id"] in [b["project_id"] for b in listed]
        assert mongo.billing_budgets.count_documents({"scope_id": website["id"]}) == 1

    def test_deleting_a_client_takes_its_budget(self, client, auth_headers, mongo):
        # Read through the collection: a budget whose client is gone is
        # skipped on read, so the list could not tell.
        kite = _create_client(client, auth_headers)
        assert _put_billing_budget(client, auth_headers, "clients", kite["id"]).status_code == 200

        resp = client.delete(f"/api/clients/{kite['id']}", headers=auth_headers)

        assert resp.status_code == 204, resp.text
        assert mongo.billing_budgets.count_documents({"scope_id": kite["id"]}) == 0
