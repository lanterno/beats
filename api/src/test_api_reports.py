"""The public report links: the read with no Authorization header, and
what a link cannot reach (docs/billing.md, phase 1c).

Split out of `test_api.py` at the size ceiling (CLAUDE.md § Conventions); the
harness is `conftest.py`'s and the shared fixtures `api_helpers.py`'s.
"""

import pytest

from api_helpers import (
    _beat,
    _billed_march,
    _create_client,
    _create_project,
    _link_body,
    _mint_link,
    _month,
    _read_report,
)


class TestReportLinksAPI:
    """Report links (docs/billing.md, phase 1c) — the owner's writes under
    /api/clients/{id}/links, and the public read under /api/reports that a
    client opens with no account at all, its token in X-Report-Token.

    The range is March 2026, in the past and so fully closed, which is what
    lets these assert exact figures.
    """

    def test_a_client_reads_its_hours_with_no_login(self, client, auth_headers):
        billed = _billed_march(client, auth_headers)
        link = _mint_link(client, auth_headers, billed["client"]["id"])

        resp = _read_report(client, link["token"])

        assert resp.status_code == 200, resp.text
        report = resp.json()
        assert report["client_name"] == "Studio Kite"
        assert (report["first"], report["last"]) == ("2026-03-01", "2026-03-31")
        # Three hours at 85.00/h, and the figures are the assembler's.
        assert report["billable_hours"] == 3.0
        assert report["amount_minor"] == 25500
        assert report["currency"] == "EUR"
        assert report["minor_units"] == 2
        assert [line["project_name"] for line in report["lines"]] == ["Website"]
        assert len(report["entries"]) == 2

    def test_the_figures_are_the_owners(self, client, auth_headers):
        """One arithmetic serves both pages: what the client is shown and
        what the owner is shown for the same range agree to the hundredth."""
        billed = _billed_march(client, auth_headers)
        link = _mint_link(client, auth_headers, billed["client"]["id"])

        report = _read_report(client, link["token"]).json()
        mine = next(
            c
            for c in _month(client, auth_headers)["clients"]
            if c["client_id"] == billed["client"]["id"]
        )

        assert report["billable_hours"] == mine["billable_hours"]
        assert report["amount_minor"] == mine["amount_minor"]

    def test_hiding_amounts_keeps_the_hours(self, client, auth_headers):
        """A link without amounts is a proof of time with the price left
        out: every money field is null and no hour moves."""
        billed = _billed_march(client, auth_headers)
        priced = _mint_link(client, auth_headers, billed["client"]["id"])
        free = _mint_link(client, auth_headers, billed["client"]["id"], show_amounts=False)

        report = _read_report(client, free["token"]).json()

        assert report["currency"] is None
        assert report["minor_units"] is None
        assert report["amount_minor"] is None
        assert report["unpriced_hours"] is None
        assert [line["rate_minor"] for line in report["lines"]] == [None]
        assert [line["amount_minor"] for line in report["lines"]] == [None]
        assert (
            report["billable_hours"]
            == _read_report(client, priced["token"]).json()["billable_hours"]
        )

    def test_hiding_entries_keeps_the_lines(self, client, auth_headers):
        billed = _billed_march(client, auth_headers)
        link = _mint_link(client, auth_headers, billed["client"]["id"], show_entries=False)

        report = _read_report(client, link["token"]).json()

        assert report["entries"] == []
        assert len(report["lines"]) == 1
        assert report["billable_hours"] == 3.0

    def test_only_billable_entries_are_listed(self, client, auth_headers):
        """A client sees what they are being asked to pay for. An entry
        marked not billable is in no line and in no row."""
        billed = _billed_march(client, auth_headers)
        unbilled = _beat(client, auth_headers, billed["project"]["id"], "2026-03-04T09:00:00", 90)
        assert (
            client.put(
                f"/api/billing/entries/{unbilled['id']}",
                json={"billable": False},
                headers=auth_headers,
            ).status_code
            == 200
        )
        link = _mint_link(client, auth_headers, billed["client"]["id"])

        report = _read_report(client, link["token"]).json()

        assert len(report["entries"]) == 2
        assert report["billable_hours"] == 3.0

    def test_a_link_cannot_reach_another_client(self, client, auth_headers):
        """The wall of 1c decision 3. Two clients of one account, each with
        its own billed project: a link on one names neither the other's
        project nor its hours, because the query for them is never made."""
        kite = _billed_march(client, auth_headers, name="Studio Kite", project="Website")
        _billed_march(client, auth_headers, name="Acme", project="Acme Intranet")
        link = _mint_link(client, auth_headers, kite["client"]["id"])

        body = _read_report(client, link["token"]).text

        assert "Acme" not in body
        report = _read_report(client, link["token"]).json()
        assert [line["project_name"] for line in report["lines"]] == ["Website"]
        assert report["billable_hours"] == 3.0

    def test_a_personal_project_is_never_in_reach(self, client, auth_headers):
        """A day job and a side project of the same account are not billed
        to anyone, so they are not among the link's inputs at all."""
        billed = _billed_march(client, auth_headers)
        _create_project(client, auth_headers, name="Novel", kind="side_project")
        _create_project(client, auth_headers, name="Day Job", kind="day_job")
        link = _mint_link(client, auth_headers, billed["client"]["id"])

        body = _read_report(client, link["token"]).text

        assert "Novel" not in body
        assert "Day Job" not in body

    def test_the_report_carries_no_internal_ids_and_no_marks(self, client, auth_headers):
        """1c decisions 4, 5 and 7: the public schema is written field by
        field, so it cannot grow by inheriting from the private one. A
        response that started carrying these would mean someone made
        `ReportResponse` a subclass."""
        billed = _billed_march(client, auth_headers)
        link = _mint_link(client, auth_headers, billed["client"]["id"])

        report = _read_report(client, link["token"]).json()

        for absent in ("client_id", "running", "non_billable_hours"):
            assert absent not in report
        assert "project_id" not in report["lines"][0]
        assert "source" not in report["lines"][0]
        for absent in ("beat_id", "project_id", "overridden", "rate_minor", "note"):
            assert absent not in report["entries"][0]

    def test_a_running_timer_is_in_no_figure(self, client, auth_headers):
        """A report must read the same twice. A running beat is not billed
        (1a decision 9), and the link does not say one is running either."""
        billed = _billed_march(client, auth_headers)
        _beat(client, auth_headers, billed["project"]["id"], "2026-03-05T09:00:00", None)
        link = _mint_link(client, auth_headers, billed["client"]["id"])

        report = _read_report(client, link["token"]).json()

        assert report["billable_hours"] == 3.0
        assert len(report["entries"]) == 2
        assert "running" not in report

    def test_an_unknown_token_is_404(self, client):
        resp = _read_report(client, "nosuchtoken")
        assert resp.status_code == 404, resp.text
        assert resp.json()["code"] == "REPORT_NOT_FOUND"

    def test_no_route_carries_the_token_in_its_path(self, client, auth_headers):
        """Cloud Run's request log keeps every request's full URL for 30
        days, so a token in the path is a live report link anyone who can
        read the project's logs can open (#376). The token is read from
        X-Report-Token and from nowhere else — not the path it used to be
        in, and not a query parameter either."""
        billed = _billed_march(client, auth_headers)
        link = _mint_link(client, auth_headers, billed["client"]["id"])
        assert _read_report(client, link["token"]).status_code == 200

        assert client.get(f"/api/reports/{link['token']}").status_code == 404
        in_query = client.get(f"/api/reports?token={link['token']}")
        assert in_query.status_code == 422, in_query.text

    def test_the_header_is_required(self, client):
        """No token at all is a 422 — the request is malformed, which is a
        different answer from a token that did not resolve, and tells a
        reader nothing the absent token did not already."""
        resp = client.get("/api/reports")
        assert resp.status_code == 422, resp.text

    def test_a_revoked_link_is_dead(self, client, auth_headers):
        billed = _billed_march(client, auth_headers)
        link = _mint_link(client, auth_headers, billed["client"]["id"])
        assert _read_report(client, link["token"]).status_code == 200

        resp = client.delete(
            f"/api/clients/{billed['client']['id']}/links/{link['id']}", headers=auth_headers
        )

        assert resp.status_code == 204, resp.text
        gone = _read_report(client, link["token"])
        assert gone.status_code == 404, gone.text
        assert gone.json()["code"] == "REPORT_NOT_FOUND"
        # And it answers exactly as an unknown token does: a reader with no
        # session must not learn that the link once existed.
        assert gone.json()["detail"] == _read_report(client, "nosuchtoken").json()["detail"]

    def test_deleting_a_client_takes_its_links(self, client, auth_headers):
        kite = _create_client(client, auth_headers)
        link = _mint_link(client, auth_headers, kite["id"])

        assert client.delete(f"/api/clients/{kite['id']}", headers=auth_headers).status_code == 204

        gone = _read_report(client, link["token"])
        assert gone.status_code == 404, gone.text
        assert gone.json()["code"] == "REPORT_NOT_FOUND"

    def test_revoking_is_idempotent_and_scoped_to_its_client(self, client, auth_headers):
        """204 with no such link, and a link cannot be revoked through
        another client's path."""
        kite = _create_client(client, auth_headers, name="Studio Kite")
        acme = _create_client(client, auth_headers, name="Acme")
        link = _mint_link(client, auth_headers, kite["id"])

        missing = client.delete(f"/api/clients/{kite['id']}/links/xyz", headers=auth_headers)
        wrong = client.delete(f"/api/clients/{acme['id']}/links/{link['id']}", headers=auth_headers)

        assert (missing.status_code, wrong.status_code) == (204, 204)
        assert _read_report(client, link["token"]).status_code == 200

    def test_links_are_listed_newest_first_with_their_tokens(self, client, auth_headers):
        """The owner has to be able to re-copy a link they already sent."""
        kite = _create_client(client, auth_headers)
        older = _mint_link(client, auth_headers, kite["id"], first="2026-01-01", last="2026-01-31")
        newer = _mint_link(client, auth_headers, kite["id"])

        listed = client.get(f"/api/clients/{kite['id']}/links", headers=auth_headers).json()

        assert [link["id"] for link in listed] == [newer["id"], older["id"]]
        assert [link["token"] for link in listed] == [newer["token"], older["token"]]

    @pytest.mark.parametrize(
        "fields",
        [
            {"first": "2026-03-31", "last": "2026-03-01"},
            {"first": "2026-01-01", "last": "2027-01-02"},
        ],
        ids=["backwards", "over 366 days"],
    )
    def test_a_range_must_run_forward_and_be_bounded(self, client, auth_headers, fields):
        kite = _create_client(client, auth_headers)

        resp = client.post(
            f"/api/clients/{kite['id']}/links", json=_link_body(**fields), headers=auth_headers
        )

        assert resp.status_code == 422, resp.text
        assert [f["path"] for f in resp.json()["fields"]] == ["last"]

    def test_an_unknown_timezone_is_400(self, client, auth_headers):
        kite = _create_client(client, auth_headers)

        resp = client.post(
            f"/api/clients/{kite['id']}/links",
            json=_link_body(tz="Mars/Olympus"),
            headers=auth_headers,
        )

        assert resp.status_code == 400, resp.text
        assert resp.json()["code"] == "INVALID_TIMEZONE"

    @pytest.mark.parametrize("flag", ["show_amounts", "show_entries"])
    def test_the_flags_are_strict_and_required(self, client, auth_headers, flag):
        """Showing a client money by accident is the one mistake to rule
        out, so 1 does not read as true and a missing key is not off."""
        kite = _create_client(client, auth_headers)

        loose = client.post(
            f"/api/clients/{kite['id']}/links",
            json=_link_body(**{flag: 1}),
            headers=auth_headers,
        )
        missing = _link_body()
        del missing[flag]
        absent = client.post(f"/api/clients/{kite['id']}/links", json=missing, headers=auth_headers)

        assert (loose.status_code, absent.status_code) == (422, 422)

    def test_the_link_routes_are_the_owners(self, client, auth_headers):
        """Someone else's client is not found, and minting needs a session."""
        kite = _create_client(client, auth_headers)

        assert client.get(f"/api/clients/{kite['id']}/links").status_code == 401
        assert client.post(f"/api/clients/{kite['id']}/links", json=_link_body()).status_code == 401
        missing = client.get("/api/clients/nosuchclient/links", headers=auth_headers)
        assert missing.status_code == 404, missing.text
        assert missing.json()["code"] == "CLIENT_NOT_FOUND"

    def test_the_public_read_is_uncached_and_unindexed(self, client, auth_headers):
        billed = _billed_march(client, auth_headers)
        link = _mint_link(client, auth_headers, billed["client"]["id"])

        resp = _read_report(client, link["token"])

        assert resp.headers["cache-control"] == "no-store"
        assert "noindex" in resp.headers["x-robots-tag"]

    def test_the_range_is_frozen_at_the_links_own_days(self, client, auth_headers):
        """The link's range decides what is counted, not the data's: hours
        outside it are in no figure, however recent."""
        billed = _billed_march(client, auth_headers)
        _beat(client, auth_headers, billed["project"]["id"], "2026-04-01T09:00:00", 600)
        link = _mint_link(client, auth_headers, billed["client"]["id"])

        report = _read_report(client, link["token"]).json()

        assert report["billable_hours"] == 3.0
