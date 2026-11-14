"""An organisation's projects over their life: connecting one already
tracked personally, merging, leaving and removal, erasure, and what a
backup carries.

Same harness as test_api.py (conftest.py): a TestClient over real Mongo
and one test user per class (`auth_headers`); every other person in a test
is minted by `_new_user`, since an organisation is about more than one.
Split at the size ceiling (CLAUDE.md § Conventions); the shared fixtures are
`organisation_helpers.py`'s.
"""

import asyncio
import csv
import io
import json
import os
from datetime import date, timedelta

from bson import ObjectId

from organisation_helpers import (
    FULL_TIME,
    MONTH,
    _assign,
    _beat,
    _create_org,
    _db,
    _decide_sheet,
    _employed,
    _member_of,
    _members_of_record,
    _new_user,
    _org_project,
    _projects,
    _record,
    _seeded_id,
    _submit,
    _visible,
)


class TestConnectingAProject:
    """Rule 4: a project already tracked personally is connected from a day
    the person chooses, and nothing before that day is shared."""

    def _tracked_day_job(self, client, headers) -> dict:
        project = client.post(
            "/api/projects/",
            json={
                "name": "Day job",
                "kind": "day_job",
                "weekly_goal": 32,
                "autostart_repos": ["/Users/me/work"],
                "contract": {"terms": FULL_TIME, "opening_balance_hours": 12},
            },
            headers=headers,
        ).json()
        _beat(client, headers, project["id"], "2026-03-02T09:00:00", 60)  # Monday, before
        _beat(client, headers, project["id"], "2026-03-03T09:00:00", 60)  # Tuesday, before
        _beat(client, headers, project["id"], "2026-03-04T09:00:00", 120)  # Wednesday, from here
        _beat(client, headers, project["id"], "2026-03-05T09:00:00", 60)  # Thursday
        for day in ("2026-03-03", "2026-03-06"):
            client.post(
                f"/api/projects/{project['id']}/absences",
                json={"date": day, "type": "vacation"},
                headers=headers,
            )
        return project

    def _connect(
        self, client, headers, org_id: str, project_id: str, share_from, tz="Europe/Zurich"
    ):
        return client.post(
            f"/api/organisations/{org_id}/connect",
            params={"tz": tz},
            json={"project_id": project_id, "share_from": share_from},
            headers=headers,
        )

    def test_history_is_shared_from_the_chosen_day_only(self, client, auth_headers):
        org = _create_org(client, auth_headers)
        member = _new_user()
        member_id = _member_of(client, auth_headers, org["id"], member)
        project = self._tracked_day_job(client, member)

        connected = self._connect(client, member, org["id"], project["id"], "2026-03-04")
        assert connected.status_code == 200, connected.text
        assert connected.json()["user_id"] == member_id
        # Local midnight in Zurich, in UTC.
        assert connected.json()["shared_from"] == "2026-03-03T23:00:00Z"
        assert connected.json()["has_contract"] is True

        # The organisation sees Wednesday on, and Friday's absence, not Tuesday's.
        [row] = _members_of_record(_record(client, auth_headers, org["id"]), project["id"])
        assert [e["day"] for e in row["entries"]] == ["2026-03-04", "2026-03-05"]
        assert row["hours"] == 3.0
        assert [a["date"] for a in row["absences"]] == ["2026-03-06"]
        assert row["totals"]["entries"] == 2
        assert row["has_contract"] is True
        # The balance sums every hour since the contract began, Monday and
        # Tuesday among them, so it is withheld rather than carry what the
        # member kept back (rule 4) — and the member's own figure is theirs.
        assert row["balance"] is None
        mine_week = client.get(
            f"/api/projects/{project['id']}/contract/week", params={"tz": "UTC"}, headers=member
        ).json()
        assert mine_week["balance"] is not None

        # The member keeps everything: all four entries, the goal, the paths,
        # the contract — and the project is now marked as Acme's.
        [mine] = _projects(client, member)
        assert mine["organisation"]["name"] == "Acme"
        assert mine["organisation"]["shared_from"] == "2026-03-03T23:00:00Z"
        assert (mine["weekly_goal"], mine["autostart_repos"]) == (32, ["/Users/me/work"])
        assert mine["contract"]["opening_balance_hours"] == 12
        assert (
            len(client.get(f"/api/beats/?project_id={project['id']}", headers=member).json()) == 4
        )
        ledger = client.get(f"/api/projects/{project['id']}/ledger", headers=member)
        assert ledger.status_code == 200
        # The organisation has one project it did not create, named as it was.
        [theirs] = client.get(
            f"/api/organisations/{org['id']}/projects", headers=auth_headers
        ).json()
        assert (theirs["id"], theirs["name"], theirs["kind"]) == (
            project["id"],
            "Day job",
            "day_job",
        )

    def test_starting_fresh_shares_nothing_before_now(self, client, auth_headers):
        org = _create_org(client, auth_headers)
        member = _new_user()
        _member_of(client, auth_headers, org["id"], member)
        project = self._tracked_day_job(client, member)
        # A day off already booked for a day to come is the record's from here.
        future = (date.today() + timedelta(days=30)).isoformat()
        client.post(
            f"/api/projects/{project['id']}/absences",
            json={"date": future, "type": "vacation"},
            headers=member,
        )
        connected = self._connect(client, member, org["id"], project["id"], None)
        assert connected.status_code == 200, connected.text
        [row] = _members_of_record(_record(client, auth_headers, org["id"]), project["id"])
        assert row["entries"] == []
        assert row["absences"] == []
        assert row["totals"]["entries"] == 0
        assert row["balance"] is None
        this_month = date.today().strftime("%Y-%m")
        future_month = (date.today() + timedelta(days=30)).strftime("%Y-%m")
        if future_month != this_month:
            [later] = _members_of_record(
                _record(client, auth_headers, org["id"], month=future_month), project["id"]
            )
            assert [a["date"] for a in later["absences"]] == [future]
        # From now on, tracking is the organisation's.
        started = client.post(f"/api/projects/{project['id']}/start", json={}, headers=member)
        assert started.json()["organisation_id"] == org["id"]

    def test_what_cannot_be_connected(self, client, auth_headers):
        org = _create_org(client, auth_headers)
        member = _new_user()
        _member_of(client, auth_headers, org["id"], member)
        project = self._tracked_day_job(client, member)

        future = self._connect(client, member, org["id"], project["id"], "2099-01-01")
        assert future.status_code == 409
        assert future.json()["code"] == "SHARE_FROM_IN_FUTURE"
        no_tz = client.post(
            f"/api/organisations/{org['id']}/connect",
            json={"project_id": project["id"], "share_from": None},
            headers=member,
        )
        assert no_tz.status_code == 422

        billed = client.post(
            "/api/projects/", json={"name": "Site", "kind": "freelance"}, headers=member
        ).json()
        kite = client.post(
            "/api/clients/",
            json={
                "name": "Kite",
                "currency": "EUR",
                "rates": [],
                "contact_name": None,
                "contact_email": None,
            },
            headers=member,
        ).json()
        assert (
            client.put(
                f"/api/billing/projects/{billed['id']}",
                params={"tz": "UTC"},
                json={
                    "client_id": kite["id"],
                    "rewrite_past": False,
                    "terms": [{"effective_from": "2026-03-01", "billable": True}],
                },
                headers=member,
            ).status_code
            == 200
        )
        refused = self._connect(client, member, org["id"], billed["id"], None)
        assert refused.status_code == 409
        assert refused.json()["code"] == "PROJECT_HAS_BILLING"

        # Someone else's project is not found; a connected one is the organisation's already.
        stranger = _new_user()
        _member_of(client, auth_headers, org["id"], stranger)
        assert self._connect(client, stranger, org["id"], project["id"], None).status_code == 404
        assert self._connect(client, member, org["id"], project["id"], None).status_code == 200
        twice = self._connect(client, member, org["id"], project["id"], None)
        assert twice.status_code == 409
        assert twice.json()["code"] == "ORGANISATION_PROJECT"
        # And a non-member cannot connect anything to an organisation.
        outsider = _new_user()
        theirs = client.post("/api/projects/", json={"name": "Mine"}, headers=outsider).json()
        assert self._connect(client, outsider, org["id"], theirs["id"], None).status_code == 404

    def test_no_later_write_hands_over_what_the_connect_kept_back(self, client, auth_headers):
        """A bug that happened (#404): every write stamped a row from the
        project alone, so touching a pre-share row handed it to the
        organisation — the plainest possible break of rule 4, since the
        member changed a note and gave away a day."""
        org = _create_org(client, auth_headers)
        member = _new_user()
        _member_of(client, auth_headers, org["id"], member)
        project = self._tracked_day_job(client, member)
        kept = next(
            b
            for b in client.get(f"/api/beats/?project_id={project['id']}", headers=member).json()
            if b["start"].startswith("2026-03-03")
        )
        assert self._connect(client, member, org["id"], project["id"], "2026-03-04").status_code

        # An edit to a pre-share session: the note is the member's, and so
        # is the session it is on.
        edited = client.put(
            "/api/beats/",
            json={
                "id": kept["id"],
                "project_id": project["id"],
                "start": kept["start"],
                "end": kept["end"],
                "note": "the dentist, actually",
            },
            headers=member,
        )
        assert edited.status_code == 200, edited.text
        assert edited.json()["organisation_id"] is None

        # A session back-dated into the kept-back week, by either door.
        assert (
            _beat(client, member, project["id"], "2026-03-02T14:00:00", 30)["organisation_id"]
            is None
        )
        started = client.post(
            f"/api/projects/{project['id']}/start",
            json={"time": "2026-03-02T16:00:00Z"},
            headers=member,
        )
        assert started.status_code == 200, started.text
        assert started.json()["organisation_id"] is None
        client.post("/api/projects/stop", json={"time": "2026-03-02T17:00:00Z"}, headers=member)

        # And a day booked off before the share day. An absence is dated,
        # not timed, so it is the chosen *day* it is judged against.
        booked = client.post(
            f"/api/projects/{project['id']}/absences",
            json={"date": "2026-03-02", "type": "vacation"},
            headers=member,
        )
        assert booked.status_code in (200, 201), booked.text

        # The organisation's record is exactly what it was.
        [row] = _members_of_record(_record(client, auth_headers, org["id"]), project["id"])
        assert [e["day"] for e in row["entries"]] == ["2026-03-04", "2026-03-05"]
        assert [a["date"] for a in row["absences"]] == ["2026-03-06"]
        assert all(e["note"] != "the dentist, actually" for e in row["entries"])
        # And the member's own view of it agrees, since it is the same read.
        [seen] = _members_of_record(_visible(client, member, org["id"]), project["id"])
        assert [e["day"] for e in seen["entries"]] == ["2026-03-04", "2026-03-05"]

    def test_being_reassigned_does_not_reopen_the_history(self, client, auth_headers):
        """`shared_from` moves to the day of a new assignment, so it cannot
        be what a stamp is judged against: what the member kept back at the
        connect stays kept back through an unassign and a reassign."""
        org = _create_org(client, auth_headers)
        member = _new_user()
        member_id = _member_of(client, auth_headers, org["id"], member)
        project = self._tracked_day_job(client, member)
        self._connect(client, member, org["id"], project["id"], "2026-03-04")

        path = f"/api/organisations/{org['id']}/projects/{project['id']}/members/{member_id}"
        assert client.delete(path, headers=auth_headers).status_code == 204
        assert client.put(path, headers=auth_headers).status_code == 200

        assert (
            _beat(client, member, project["id"], "2026-03-02T14:00:00", 30)["organisation_id"]
            is None
        )
        [row] = _members_of_record(_record(client, auth_headers, org["id"]), project["id"])
        assert [e["day"] for e in row["entries"]] == ["2026-03-04", "2026-03-05"]


class TestMergingAProject:
    """#346: a connect leaves a duplicate when the organisation already had
    a project for the same work; the merge folds it in, rule 4 kept — every
    row moves with its stamp untouched, so what was shared stays shared
    from the chosen instant and what was private stays private."""

    def _tracked(self, client, headers, name="Day job") -> dict:
        project = client.post(
            "/api/projects/",
            json={
                "name": name,
                "kind": "day_job",
                "contract": {"terms": FULL_TIME, "opening_balance_hours": 12},
            },
            headers=headers,
        ).json()
        _beat(client, headers, project["id"], "2026-03-02T09:00:00", 60)  # before the share
        _beat(client, headers, project["id"], "2026-03-04T09:00:00", 120)  # from here
        return project

    def _connect(self, client, headers, org_id: str, project_id: str, share_from):
        resp = client.post(
            f"/api/organisations/{org_id}/connect",
            params={"tz": "UTC"},
            json={"project_id": project_id, "share_from": share_from},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        return resp.json()

    def _merge(self, client, headers, org_id: str, source_id: str, target_id: str):
        return client.post(
            f"/api/organisations/{org_id}/projects/{source_id}/merge",
            json={"into": target_id},
            headers=headers,
        )

    def test_the_duplicate_folds_in_and_the_stamps_decide_what_crosses(self, client, auth_headers):
        org = _create_org(client, auth_headers)
        platform = _org_project(client, auth_headers, org["id"], name="Platform")
        member = _new_user()
        member_id = _member_of(client, auth_headers, org["id"], member)
        mine = self._tracked(client, member)
        self._connect(client, member, org["id"], mine["id"], "2026-03-04")

        merged = self._merge(client, auth_headers, org["id"], mine["id"], platform["id"])
        assert merged.status_code == 200, merged.text
        assert merged.json()["id"] == platform["id"]
        assert [m["user_id"] for m in merged.json()["members"]] == [member_id]

        # One project remains, and the organisation reads under it exactly
        # what the member shared: Wednesday's hours, never Monday's.
        assert [
            p["id"]
            for p in client.get(
                f"/api/organisations/{org['id']}/projects", headers=auth_headers
            ).json()
        ] == [platform["id"]]
        [row] = _members_of_record(_record(client, auth_headers, org["id"]), platform["id"])
        assert [e["day"] for e in row["entries"]] == ["2026-03-04"]
        assert row["has_contract"] is True  # the connect's contract moved with the assignment
        assert row["shared_from"] == "2026-03-04T00:00:00Z"

        # The member keeps one timeline: both entries, now under Platform.
        [own] = _projects(client, member)
        assert own["id"] == platform["id"]
        assert own["organisation"]["name"] == "Acme"
        total = client.get(
            f"/api/projects/{platform['id']}/total/", params={"tz": "UTC"}, headers=member
        ).json()
        assert total["total_minutes"] == 180  # Monday's hour too, theirs as ever

        events = [
            e["event"]
            for e in client.get(
                f"/api/organisations/{org['id']}/audit", headers=auth_headers
            ).json()
        ]
        assert "project.merged" in events

    def test_an_existing_assignment_survives_and_gains_only_what_it_lacked(
        self, client, auth_headers
    ):
        org = _create_org(client, auth_headers)
        platform = _org_project(client, auth_headers, org["id"], name="Platform")
        member = _new_user()
        member_id = _member_of(client, auth_headers, org["id"], member)
        _assign(client, auth_headers, org["id"], platform["id"], member_id)
        _beat(client, member, platform["id"], "2026-03-10T09:00:00", 60)
        mine = self._tracked(client, member)
        self._connect(client, member, org["id"], mine["id"], "2026-03-04")

        merged = self._merge(client, auth_headers, org["id"], mine["id"], platform["id"])
        assert merged.status_code == 200, merged.text

        [row] = _members_of_record(_record(client, auth_headers, org["id"]), platform["id"])
        # Both stamped histories under one project, shared from the earlier
        # instant; the target's assignment stood and took the contract it lacked.
        assert [e["day"] for e in row["entries"]] == ["2026-03-04", "2026-03-10"]
        assert row["shared_from"] == "2026-03-04T00:00:00Z"
        assert row["has_contract"] is True

    def test_a_former_member_stays_in_the_merged_projects_record(self, client, auth_headers):
        """A bug that happened (#406): the fold took the active assignments
        and the delete took them all, so a member who had left kept their
        rows under the target with nothing to list them by — and dropped out
        of a record an employer may be bound to keep."""
        org = _create_org(client, auth_headers)
        platform = _org_project(client, auth_headers, org["id"], name="Platform")
        gone = _new_user()
        gone_id = _member_of(client, auth_headers, org["id"], gone)
        source = _org_project(client, auth_headers, org["id"], name="Duplicate")
        _assign(client, auth_headers, org["id"], source["id"], gone_id)
        _beat(client, gone, source["id"], "2026-03-04T09:00:00", 60)
        assert (
            client.delete(
                f"/api/organisations/{org['id']}/projects/{source['id']}/members/{gone_id}",
                headers=auth_headers,
            ).status_code
            == 204
        )

        merged = self._merge(client, auth_headers, org["id"], source["id"], platform["id"])
        assert merged.status_code == 200, merged.text

        [row] = _members_of_record(_record(client, auth_headers, org["id"]), platform["id"])
        assert row["user_id"] == gone_id
        assert [e["day"] for e in row["entries"]] == ["2026-03-04"]
        # And they are still off the project: folding moves their half, it
        # does not put them back on it.
        assert row["active"] is False

    def test_a_members_plan_and_flow_windows_follow_the_merge(self, client, auth_headers):
        """The two places a member names a project that is not a row of
        theirs. Left behind they point at the document the merge deletes."""
        org = _create_org(client, auth_headers)
        platform = _org_project(client, auth_headers, org["id"], name="Platform")
        member = _new_user()
        _member_of(client, auth_headers, org["id"], member)
        mine = self._tracked(client, member)
        planned = client.put(
            "/api/plans/weekly",
            json={
                "week_of": "2026-03-02",
                "budgets": [{"project_id": mine["id"], "planned_hours": 8}],
            },
            headers=member,
        )
        assert planned.status_code == 200, planned.text
        self._connect(client, member, org["id"], mine["id"], "2026-03-04")

        merged = self._merge(client, auth_headers, org["id"], mine["id"], platform["id"])
        assert merged.status_code == 200, merged.text

        plan = client.get(
            "/api/plans/weekly", params={"week_of": "2026-03-02"}, headers=member
        ).json()
        assert [b["project_id"] for b in plan["budgets"]] == [platform["id"]]

    def test_a_frozen_month_refuses_the_merge(self, client, auth_headers):
        member = _new_user()
        org, employed, _member_id = _employed(client, auth_headers, member)
        _beat(client, member, employed["id"], "2026-03-03T09:00:00", 60)
        sheet = _submit(client, member, org["id"], employed["id"], MONTH).json()
        assert (
            _decide_sheet(client, auth_headers, org["id"], sheet["id"], approve=True).status_code
            == 200
        )
        other = _org_project(client, auth_headers, org["id"], name="Other")

        for source, target in ((employed, other), (other, employed)):
            refused = self._merge(client, auth_headers, org["id"], source["id"], target["id"])
            assert refused.status_code == 409, refused.text
            assert refused.json()["code"] == "PERIOD_APPROVED"

    def test_only_an_admin_merges_and_only_into_another_project(self, client, auth_headers):
        org = _create_org(client, auth_headers)
        platform = _org_project(client, auth_headers, org["id"], name="Platform")
        other = _org_project(client, auth_headers, org["id"], name="Other")
        member = _new_user()
        _member_of(client, auth_headers, org["id"], member)

        as_member = self._merge(client, member, org["id"], other["id"], platform["id"])
        assert as_member.status_code == 403
        itself = self._merge(client, auth_headers, org["id"], other["id"], other["id"])
        assert itself.status_code == 409
        assert itself.json()["code"] == "MERGE_INTO_ITSELF"
        assert (
            self._merge(client, auth_headers, org["id"], other["id"], "0" * 24).status_code == 404
        )


class TestLeavingAndRemoval:
    def _acme(self, client, admin, member) -> tuple[dict, dict, str]:
        org = _create_org(client, admin)
        member_id = _member_of(client, admin, org["id"], member)
        project = _org_project(client, admin, org["id"])
        _assign(client, admin, org["id"], project["id"], member_id)
        _beat(client, member, project["id"], "2026-03-03T09:00:00", 60)
        _beat(client, member, project["id"], "2026-03-04T09:00:00", 30)
        return org, project, member_id

    def test_leaving_stops_tracking_keeps_the_record_and_leaves_an_archive(
        self, client, auth_headers
    ):
        member = _new_user()
        org, project, _member_id = self._acme(client, auth_headers, member)
        personal = client.post("/api/projects/", json={"name": "Garden"}, headers=member).json()

        left = client.post(f"/api/organisations/{org['id']}/leave", headers=member)
        assert left.status_code == 200, left.text
        assert left.json()["left_reason"] == "left"

        # Tracking stops: the project is gone from the list and not found.
        assert [p["id"] for p in _projects(client, member)] == [personal["id"]]
        assert (
            client.post(f"/api/projects/{project['id']}/start", json={}, headers=member).status_code
            == 404
        )
        assert (
            client.get(f"/api/projects/{project['id']}/ledger", headers=member).status_code == 404
        )
        # The membership is listed as left, and the organisation's routes are closed.
        [mine] = client.get("/api/organisations/", headers=member).json()
        assert mine["left_at"] is not None
        assert client.get(f"/api/organisations/{org['id']}", headers=member).status_code == 404

        # The organisation keeps its record.
        [row] = _members_of_record(_record(client, auth_headers, org["id"]), project["id"])
        assert (row["active"], row["hours"]) == (False, 1.5)
        [m] = client.get(f"/api/organisations/{org['id']}/members", headers=auth_headers).json()
        assert m["user_id"] == _seeded_id(auth_headers)

        # The person keeps a read-only archive of their own hours, and can export it.
        archive = client.get(
            f"/api/organisations/{org['id']}/archive", params={"tz": "UTC"}, headers=member
        )
        assert archive.status_code == 200, archive.text
        body = archive.json()
        assert body["organisation"]["name"] == "Acme"
        assert body["left_at"] is not None
        assert body["hours"] == 1.5
        [archived] = body["projects"]
        assert (archived["name"], archived["hours"], len(archived["entries"])) == (
            "Platform",
            1.5,
            2,
        )
        assert archived["absences"] == []
        sheet = client.get(f"/api/organisations/{org['id']}/archive.csv", headers=member)
        assert sheet.status_code == 200
        assert sheet.headers["content-type"].startswith("text/csv")
        rows = list(csv.reader(io.StringIO(sheet.text)))
        assert rows[0] == ["project", "day", "kind", "start", "end", "hours", "note"]
        assert [(r[2], r[5]) for r in rows[1:]] == [("entry", "1.00"), ("entry", "0.50")]
        # And still sees what the organisation sees of them.
        [visible] = _members_of_record(_visible(client, member, org["id"]), project["id"])
        assert visible["hours"] == 1.5

    def test_removal_is_leaving_done_by_an_admin(self, client, auth_headers):
        member = _new_user()
        org, project, member_id = self._acme(client, auth_headers, member)
        removed = client.delete(
            f"/api/organisations/{org['id']}/members/{member_id}", headers=auth_headers
        )
        assert removed.status_code == 204
        [mine] = client.get("/api/organisations/", headers=member).json()
        assert mine["left_reason"] == "removed"
        assert _projects(client, member) == []
        assert (
            client.get(f"/api/organisations/{org['id']}/archive", headers=member).json()["hours"]
            == 1.5
        )
        # Invited back, the membership reopens and the project must be assigned again.
        _member_of(client, auth_headers, org["id"], member)
        [mine] = client.get("/api/organisations/", headers=member).json()
        assert mine["left_at"] is None
        assert _projects(client, member) == []
        _assign(client, auth_headers, org["id"], project["id"], member_id)
        assert [p["id"] for p in _projects(client, member)] == [project["id"]]


class TestErasure:
    """Decision 3: an erased account leaves the organisation its working-time
    rows under a tombstone, with the name it knew the person by, and nothing
    else."""

    def test_the_record_survives_the_account(self, client, auth_headers):
        from beats.infrastructure.erasure import erase_account

        org = _create_org(client, auth_headers)
        member = _new_user()
        member_id = _member_of(client, auth_headers, org["id"], member)
        project = _org_project(client, auth_headers, org["id"], kind="day_job")
        _assign(client, auth_headers, org["id"], project["id"], member_id)
        client.put(
            f"/api/projects/{project['id']}/contract", json={"terms": FULL_TIME}, headers=member
        )
        _beat(client, member, project["id"], "2026-03-03T09:00:00", 60)
        client.post(
            f"/api/projects/{project['id']}/absences",
            json={"date": "2026-03-06", "type": "sick", "note": "private"},
            headers=member,
        )
        personal = client.post("/api/projects/", json={"name": "Garden"}, headers=member).json()
        _beat(client, member, personal["id"], "2026-03-03T19:00:00", 60)
        db = _db()
        db.timeLogs.update_many({"user_id": member_id}, {"$set": {"tags": ["private-tag"]}})
        before = _record(client, auth_headers, org["id"])

        async def run():
            from pymongo import AsyncMongoClient

            client_ = AsyncMongoClient(os.environ.get("DB_DSN", "mongodb://localhost:27017"))
            try:
                return await erase_account(
                    client_[os.environ.get("DB_NAME", "beats_test")], member_id
                )
            finally:
                await client_.close()

        report = asyncio.run(run())
        assert report.organisations == [org["id"]]
        assert report.retained["timeLogs"] == 1
        assert report.retained["absences"] == 1
        assert report.deleted["timeLogs"] == 1
        assert report.deleted["projects"] == 1
        assert report.deleted["users"] == 1

        # Nothing of the person is left under their id, and the account is gone.
        assert db.users.find_one({"_id": ObjectId(member_id)}) is None
        for name in db.list_collection_names():
            assert db[name].count_documents({"user_id": member_id}) == 0, name
        assert client.get("/api/projects/", headers=member).json() == []

        # The organisation's record is as it was, under the name it knew.
        after = _record(client, auth_headers, org["id"])
        [row] = _members_of_record(after, project["id"])
        [was] = _members_of_record(before, project["id"])
        assert row["user_id"].startswith("erased:")
        assert row["name"] == was["name"]
        assert row["entries"] == was["entries"]
        assert row["absences"] == was["absences"]
        assert row["has_contract"] is True
        assert row["active"] is False
        [m] = list(db.org_members.find({"organisation_id": org["id"], "role": "member"}))
        assert (m["left_reason"], m["name"]) == ("erased", was["name"])
        kept = db.timeLogs.find_one({"organisation_id": org["id"]})
        assert "tags" not in kept
        assert kept["user_id"] == row["user_id"]
        assert "note" not in db.absences.find_one({"organisation_id": org["id"]})
        assert db.org_audit.find_one({"event": "account.erased", "subject_user_id": row["user_id"]})

    def test_a_deciders_erasure_leaves_no_raw_id_anywhere(self, client, auth_headers):
        """The module promises every column in the organisation naming the
        person gets the tombstone. Two were missed (#410): `entered_by` on
        a session a decider logged for a member, and the `by` of each step
        of a timesheet's history."""
        from beats.infrastructure.erasure import erase_account

        decider = _new_user()
        decider_id = _seeded_id(decider)
        member = _new_user()
        org, project, member_id = _employed(client, auth_headers, member, managed=False)
        _member_of(client, auth_headers, org["id"], decider, role="admin")
        entered = client.post(
            f"/api/organisations/{org['id']}/projects/{project['id']}/members/{member_id}/entries",
            json={"start": "2026-03-04T09:00:00Z", "end": "2026-03-04T10:00:00Z"},
            headers=decider,
        )
        assert entered.status_code == 201, entered.text
        sheet = _submit(client, member, org["id"], project["id"], MONTH).json()
        assert (
            _decide_sheet(client, decider, org["id"], sheet["id"], approve=False).status_code == 200
        )
        # A session they entered that the member has since moved to a
        # personal project of their own: no stamp, so no tombstone fits it.
        mine = client.post("/api/projects/", json={"name": "Garden"}, headers=member).json()
        moved = client.post(
            f"/api/organisations/{org['id']}/projects/{project['id']}/members/{member_id}/entries",
            json={"start": "2026-03-05T09:00:00Z", "end": "2026-03-05T10:00:00Z"},
            headers=decider,
        ).json()
        assert (
            client.put(
                "/api/beats/",
                json={
                    "id": moved["id"],
                    "project_id": mine["id"],
                    "start": moved["start"],
                    "end": moved["end"],
                },
                headers=member,
            ).status_code
            == 200
        )

        async def run():
            from pymongo import AsyncMongoClient

            client_ = AsyncMongoClient(os.environ.get("DB_DSN", "mongodb://localhost:27017"))
            try:
                return await erase_account(
                    client_[os.environ.get("DB_NAME", "beats_test")], decider_id
                )
            finally:
                await client_.close()

        asyncio.run(run())

        db = _db()
        # Every column in the organisation that names a person. (The
        # membership's name and email are kept by decision 3, and the test
        # fixture happens to build an address out of the id, so this names
        # the id-bearing fields rather than sweeping the raw documents.)
        for name in db.list_collection_names():
            for field in (
                "user_id",
                "entered_by",
                "decided_by",
                "assigned_by",
                "created_by",
                "accepted_by",
                "actor_user_id",
                "subject_user_id",
                "history.by",
                "member_ids",
            ):
                assert db[name].count_documents({field: decider_id}) == 0, f"{name}.{field}"
        stamped = db.timeLogs.find_one({"_id": ObjectId(entered.json()["id"])})
        assert stamped["entered_by"].startswith("erased:")
        assert db.timeLogs.find_one({"_id": ObjectId(moved["id"])})["entered_by"] == "erased"
        # The submit is the member's and the decision was the decider's;
        # only the latter is tombstoned.
        history = db.org_timesheets.find_one({})["history"]
        assert any(h.get("by", "").startswith("erased:") for h in history)


class TestBackupsAndOrganisations:
    """What a personal backup does with an organisation's project."""

    @staticmethod
    def _import(client, headers, backup: dict):
        import json

        return client.post(
            "/api/export/import",
            params={"tz": "UTC"},
            files={"file": ("backup.json", json.dumps(backup), "application/json")},
            headers=headers,
        )

    def test_a_backup_carries_it_and_restores_only_the_personal_half(self, client, auth_headers):
        org = _create_org(client, auth_headers)
        member = _new_user()
        member_id = _member_of(client, auth_headers, org["id"], member)
        project = _org_project(client, auth_headers, org["id"], kind="day_job")
        _assign(client, auth_headers, org["id"], project["id"], member_id)
        client.put(
            "/api/projects/",
            json={"id": project["id"], "name": "Platform", "weekly_goal": 30},
            headers=member,
        )
        beat = _beat(client, member, project["id"], "2026-03-03T09:00:00", 60)

        backup = client.get("/api/export/full", headers=member).json()
        [exported] = backup["projects"]
        assert exported["organisation"]["id"] == org["id"]
        assert backup["beats"][0]["organisation_id"] == org["id"]

        # The organisation renames and the member changes their goal; the
        # import puts the goal back and leaves the name to the organisation.
        client.put(
            f"/api/organisations/{org['id']}/projects/{project['id']}",
            json={"name": "Platform Team"},
            headers=auth_headers,
        )
        client.put(
            "/api/projects/",
            json={"id": project["id"], "name": "Platform Team", "weekly_goal": 10},
            headers=member,
        )
        restored = self._import(client, member, backup)
        assert restored.status_code == 200, restored.text
        assert restored.json()["imported"]["projects"] == 1
        assert restored.json()["imported"]["beats"] == 1
        assert restored.json()["skipped"] == []
        [mine] = _projects(client, member)
        assert (mine["name"], mine["weekly_goal"]) == ("Platform Team", 30)
        assert (
            client.get(f"/api/beats/{beat['id']}", headers=member).json()["organisation_id"]
            == org["id"]
        )

        # The stamp is never the file's. One stripped from the file comes
        # back from the project as it stands; one planted on an entry dated
        # before the member shares from is not written.
        tampered = json.loads(json.dumps(backup))
        tampered["beats"][0]["organisation_id"] = None
        early = {
            **tampered["beats"][0],
            "id": str(ObjectId()),
            "start": "2020-01-01T09:00:00Z",
            "end": "2020-01-01T10:00:00Z",
            "organisation_id": org["id"],
        }
        tampered["beats"].append(early)
        assert self._import(client, member, tampered).status_code == 200
        stamps = {
            b["id"]: b["organisation_id"]
            for b in client.get(f"/api/beats/?project_id={project['id']}", headers=member).json()
        }
        assert stamps[beat["id"]] == org["id"]
        assert stamps[early["id"]] is None

        # Into an account that is not assigned to it, the project and what is
        # on it are left out and said so, and the rest imports.
        other = _new_user()
        backup["projects"].append({"id": str(ObjectId()), "name": "Garden"})
        elsewhere = self._import(client, other, backup)
        assert elsewhere.status_code == 200, elsewhere.text
        assert elsewhere.json()["imported"]["projects"] == 1
        assert elsewhere.json()["imported"]["beats"] == 0
        skipped = elsewhere.json()["skipped"]
        assert [(s["collection"], s["code"]) for s in skipped] == [
            ("projects", "ORGANISATION_PROJECT"),
            ("beats", "ORGANISATION_PROJECT"),
        ]
        assert [p["name"] for p in _projects(client, other)] == ["Garden"]
