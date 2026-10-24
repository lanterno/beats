"""Organisations (docs/organisations.md, stage 2) — the HTTP contract under
/api/organisations, what an organisation's project is on a member's own
routes, and the wall: what the organisation's read reaches and, more to the
point, what it cannot.

Same harness as test_api.py (conftest.py): a TestClient over real Mongo and
one test user per class (`auth_headers`); every other person in a test is
minted by `_new_user`, since an organisation is about more than one.
"""

import asyncio
import csv
import io
import json
import os
from datetime import UTC, date, datetime, timedelta

import pytest
from bson import ObjectId

# March 2026 is closed, so the record's figures are exact.
MONTH = "2026-03"
FULL_TIME = [{"effective_from": "2026-01-05", "schedule_type": "full_time", "full_time_hours": 40}]


def _me(client, headers) -> dict:
    resp = client.get("/api/account/me", headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _user_id(client, headers) -> str:
    """The caller's id, read off a project they own."""
    me = _me(client, headers)
    return me["id"] if "id" in me else _seeded_id(headers)


def _seeded_id(headers) -> str:
    from beats.auth.session import SessionManager
    from beats.settings import settings

    token = headers["Authorization"].removeprefix("Bearer ")
    payload = SessionManager(settings.jwt_secret).validate_session_token(token)
    assert payload is not None
    return payload["sub"]


def _new_user() -> dict[str, str]:
    """Bearer header for a fresh account, minted as conftest mints its second user."""
    from beats.auth.session import SessionManager
    from beats.settings import settings

    user_id = str(ObjectId())
    email = f"person-{user_id}@example.com"
    _db().users.insert_one({"_id": ObjectId(user_id), "email": email, "display_name": None})
    token = SessionManager(settings.jwt_secret).create_session_token(user_id, email)
    return {"Authorization": f"Bearer {token}"}


def _create_org(client, headers, name: str = "Acme", **fields) -> dict:
    resp = client.post("/api/organisations/", json={"name": name, **fields}, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()["organisation"]


def _invite(client, headers, org_id: str, **fields) -> dict:
    resp = client.post(f"/api/organisations/{org_id}/invites", json=fields, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


def _join(client, headers, token: str):
    return client.post(f"/api/organisations/join/{token}", headers=headers)


def _member_of(client, admin, org_id: str, headers, role: str = "member") -> str:
    """Make `headers`' user a member through an email invite; their id."""
    email = _me(client, headers)["email"]
    invite = _invite(client, admin, org_id, email=email, role=role)
    resp = _join(client, headers, invite["token"])
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "joined"
    return _seeded_id(headers)


def _org_project(client, headers, org_id: str, name: str = "Platform", **fields) -> dict:
    resp = client.post(
        f"/api/organisations/{org_id}/projects", json={"name": name, **fields}, headers=headers
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _assign(client, headers, org_id: str, project_id: str, user_id: str) -> dict:
    resp = client.put(
        f"/api/organisations/{org_id}/projects/{project_id}/members/{user_id}", headers=headers
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _beat(client, headers, project_id: str, start: str, minutes: int | None, **extra) -> dict:
    begun = datetime.fromisoformat(start).replace(tzinfo=UTC)
    end = None if minutes is None else (begun + timedelta(minutes=minutes)).isoformat()
    resp = client.post(
        "/api/beats/",
        json={"project_id": project_id, "start": begun.isoformat(), "end": end, **extra},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _record(client, headers, org_id: str, month: str = MONTH, tz: str = "UTC") -> dict:
    resp = client.get(
        f"/api/organisations/{org_id}/record", params={"month": month, "tz": tz}, headers=headers
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _visible(client, headers, org_id: str, month: str = MONTH, tz: str = "UTC") -> dict:
    resp = client.get(
        f"/api/organisations/{org_id}/visible", params={"month": month, "tz": tz}, headers=headers
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _projects(client, headers, **params) -> list[dict]:
    resp = client.get("/api/projects/", params=params, headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _members_of_record(record: dict, project_id: str) -> list[dict]:
    [project] = [p for p in record["projects"] if p["project"]["id"] == project_id]
    return project["members"]


def _db():
    from pymongo import MongoClient

    return MongoClient(os.environ.get("DB_DSN", "mongodb://localhost:27017"))[
        os.environ.get("DB_NAME", "beats_test")
    ]


class TestOrganisationLifecycle:
    """Creating, joining, roles, leaving and removal."""

    def test_creating_makes_the_creator_its_owner(self, client, auth_headers):
        org = _create_org(client, auth_headers, timezone="Europe/Zurich", holiday_country="CH")
        [mine] = client.get("/api/organisations/", headers=auth_headers).json()
        assert mine["organisation"]["id"] == org["id"]
        assert mine["role"] == "owner"
        assert mine["left_at"] is None
        [owner] = client.get(f"/api/organisations/{org['id']}/members", headers=auth_headers).json()
        assert (owner["name"], owner["email"], owner["role"]) == (
            "Test User",
            "test@example.com",
            "owner",
        )

    def test_settings_are_checked_like_a_contracts(self, client, auth_headers):
        bad_region = client.post(
            "/api/organisations/",
            json={"name": "Acme", "holiday_country": "ZZ"},
            headers=auth_headers,
        )
        assert bad_region.status_code == 400
        assert bad_region.json()["code"] == "UNKNOWN_HOLIDAY_REGION"
        bad_zone = client.post(
            "/api/organisations/",
            json={"name": "Acme", "timezone": "Mars/Olympus"},
            headers=auth_headers,
        )
        assert bad_zone.status_code == 400
        assert bad_zone.json()["code"] == "INVALID_TIMEZONE"

    def test_a_non_member_finds_nothing_and_a_member_without_the_role_is_refused(
        self, client, auth_headers
    ):
        org = _create_org(client, auth_headers)
        stranger = _new_user()
        for resp in (
            client.get(f"/api/organisations/{org['id']}", headers=stranger),
            client.get(f"/api/organisations/{org['id']}/members", headers=stranger),
            client.get(f"/api/organisations/{org['id']}/record?month={MONTH}", headers=stranger),
            client.get("/api/organisations/not-an-id", headers=stranger),
        ):
            assert resp.status_code == 404, resp.text
            assert resp.json()["code"] == "ORGANISATION_NOT_FOUND"

        _member_of(client, auth_headers, org["id"], stranger)
        assert client.get(f"/api/organisations/{org['id']}", headers=stranger).status_code == 200
        forbidden = client.get(f"/api/organisations/{org['id']}/projects", headers=stranger)
        assert forbidden.status_code == 403
        assert forbidden.json()["code"] == "ORGANISATION_ROLE_REQUIRED"
        assert (
            client.put(
                f"/api/organisations/{org['id']}", json={"name": "Mine now"}, headers=stranger
            ).status_code
            == 403
        )

    def test_an_email_invitation_waits_for_its_address_and_is_taken_once(
        self, client, auth_headers
    ):
        org = _create_org(client, auth_headers)
        invitee = _new_user()
        email = _me(client, invitee)["email"]
        invite = _invite(client, auth_headers, org["id"], email=email.upper())

        # Found at sign-in by the address, not sent anywhere — who and as
        # what, but not the way in: an address is not verified at sign-up,
        # so whoever registered it first is not handed the token.
        [waiting] = client.get("/api/organisations/invitations", headers=invitee).json()
        assert waiting["organisation"]["name"] == "Acme"
        assert waiting["role"] == "member"
        assert "token" not in waiting

        # Someone else holding the token learns nothing from it.
        passerby = _new_user()
        preview = client.get(f"/api/organisations/join/{invite['token']}", headers=passerby)
        assert preview.status_code == 404
        assert preview.json()["code"] == "INVITE_NOT_FOUND"
        assert _join(client, passerby, invite["token"]).status_code == 404

        preview = client.get(f"/api/organisations/join/{invite['token']}", headers=invitee)
        assert preview.status_code == 200
        assert preview.json()["addressed"] is True
        assert preview.json()["already_member"] is False
        joined = _join(client, invitee, invite["token"])
        assert joined.status_code == 200, joined.text
        assert joined.json()["membership"]["role"] == "member"
        # No second account, no moved data: one membership.
        assert len(client.get("/api/organisations/", headers=invitee).json()) == 1
        # Taken once.
        again = _join(client, invitee, invite["token"])
        assert again.status_code == 410
        assert again.json()["code"] == "INVITE_EXPIRED"
        assert client.get("/api/organisations/invitations", headers=invitee).json() == []

    def test_a_link_with_an_approval_step_leaves_a_request(self, client, auth_headers):
        org = _create_org(client, auth_headers)
        link = _invite(client, auth_headers, org["id"], requires_approval=True)
        assert link["email"] is None
        applicant = _new_user()

        pending = _join(client, applicant, link["token"])
        assert pending.status_code == 200
        assert pending.json() == {"status": "pending", "membership": None}
        assert _join(client, applicant, link["token"]).json()["code"] == "JOIN_REQUEST_PENDING"
        assert client.get("/api/organisations/", headers=applicant).json() == []

        [request] = client.get(
            f"/api/organisations/{org['id']}/requests", headers=auth_headers
        ).json()
        assert request["email"] == _me(client, applicant)["email"]
        decided = client.post(
            f"/api/organisations/{org['id']}/requests/{request['id']}",
            json={"decision": "approved"},
            headers=auth_headers,
        )
        assert decided.status_code == 200, decided.text
        [mine] = client.get("/api/organisations/", headers=applicant).json()
        assert mine["organisation"]["id"] == org["id"]
        assert (
            client.get(f"/api/organisations/{org['id']}/requests", headers=auth_headers).json()
            == []
        )

        # The link is reusable until revoked.
        another = _new_user()
        assert _join(client, another, link["token"]).json()["status"] == "pending"
        revoked = client.delete(
            f"/api/organisations/{org['id']}/invites/{link['id']}", headers=auth_headers
        )
        assert revoked.status_code == 204
        third = _new_user()
        assert _join(client, third, link["token"]).status_code == 410

    def test_roles_owner_is_reserved_and_the_last_owner_stays(self, client, auth_headers):
        org = _create_org(client, auth_headers)
        me = _seeded_id(auth_headers)
        admin = _new_user()
        admin_id = _member_of(client, auth_headers, org["id"], admin, role="admin")
        member = _new_user()
        member_id = _member_of(client, auth_headers, org["id"], member)

        # No invite carries the owner role.
        resp = client.post(
            f"/api/organisations/{org['id']}/invites", json={"role": "owner"}, headers=auth_headers
        )
        assert resp.status_code == 403
        assert resp.json()["code"] == "OWNER_ROLE_RESERVED"

        # An admin changes roles below owner, and no higher.
        promoted = client.patch(
            f"/api/organisations/{org['id']}/members/{member_id}",
            json={"role": "admin"},
            headers=admin,
        )
        assert promoted.status_code == 200, promoted.text
        assert promoted.json()["role"] == "admin"
        assert (
            client.patch(
                f"/api/organisations/{org['id']}/members/{member_id}",
                json={"role": "owner"},
                headers=admin,
            ).json()["code"]
            == "OWNER_ROLE_RESERVED"
        )
        assert (
            client.delete(f"/api/organisations/{org['id']}/members/{me}", headers=admin).json()[
                "code"
            ]
            == "OWNER_ROLE_RESERVED"
        )

        # The last owner can neither step down nor leave.
        for resp in (
            client.patch(
                f"/api/organisations/{org['id']}/members/{me}",
                json={"role": "member"},
                headers=auth_headers,
            ),
            client.post(f"/api/organisations/{org['id']}/leave", headers=auth_headers),
        ):
            assert resp.status_code == 409, resp.text
            assert resp.json()["code"] == "LAST_OWNER"

        # Named a second owner, the first may go.
        made_owner = client.patch(
            f"/api/organisations/{org['id']}/members/{admin_id}",
            json={"role": "owner"},
            headers=auth_headers,
        )
        assert made_owner.status_code == 200
        left = client.post(f"/api/organisations/{org['id']}/leave", headers=auth_headers)
        assert left.status_code == 200, left.text
        assert left.json()["left_reason"] == "left"
        assert left.json()["left_at"] is not None

    def test_device_tokens_cannot_reach_organisations(self, client, auth_headers):
        org = _create_org(client, auth_headers)
        code = client.post("/api/device/pair/code", headers=auth_headers).json()["code"]
        token = client.post("/api/device/pair/exchange", json={"code": code}).json()["device_token"]
        device = {"Authorization": f"Bearer {token}"}
        for resp in (
            client.get("/api/organisations/", headers=device),
            client.get(f"/api/organisations/{org['id']}/record?month={MONTH}", headers=device),
            client.post(
                f"/api/organisations/{org['id']}/connect?tz=UTC",
                json={"project_id": str(ObjectId())},
                headers=device,
            ),
        ):
            assert resp.status_code == 403, resp.text
            assert resp.json()["code"] == "DEVICE_PATH_FORBIDDEN"


class TestOrganisationProjects:
    """An organisation's project on a member's own routes: listed beside
    their own, tracked on unchanged, and theirs only in its personal half."""

    def test_an_assigned_project_appears_on_the_members_list_marked(self, client, auth_headers):
        org = _create_org(client, auth_headers, logo_url="https://acme.example/logo.svg")
        member = _new_user()
        member_id = _member_of(client, auth_headers, org["id"], member)
        project = _org_project(client, auth_headers, org["id"], color="#5B9CF6", kind="day_job")

        # Not on the list until assigned, and never on an admin's for being admin.
        assert _projects(client, member) == []
        assert _projects(client, auth_headers) == []

        assignment = _assign(client, auth_headers, org["id"], project["id"], member_id)
        assert assignment["ended_at"] is None
        [listed] = _projects(client, member)
        assert listed["id"] == project["id"]
        assert listed["name"] == "Platform"
        assert listed["kind"] == "day_job"
        assert listed["organisation"]["name"] == "Acme"
        assert listed["organisation"]["logo_url"] == "https://acme.example/logo.svg"
        assert listed["organisation"]["shared_from"] == assignment["shared_from"]
        # Through the aggregating list too, and by id.
        [with_totals] = _projects(client, member, include="totals,this_week,last_tracked")
        assert with_totals["organisation"]["id"] == org["id"]
        one = client.get(f"/api/projects/{project['id']}/ledger", headers=member)
        assert one.status_code == 200
        # A member who is not assigned does not find it.
        bystander = _new_user()
        _member_of(client, auth_headers, org["id"], bystander)
        assert (
            client.get(f"/api/projects/{project['id']}/ledger", headers=bystander).status_code
            == 404
        )
        [org_view] = client.get(
            f"/api/organisations/{org['id']}/projects", headers=auth_headers
        ).json()
        assert [m["user_id"] for m in org_view["members"]] == [member_id]

    def test_tracking_on_it_stamps_the_entry_as_the_organisations(self, client, auth_headers):
        org = _create_org(client, auth_headers)
        member = _new_user()
        member_id = _member_of(client, auth_headers, org["id"], member)
        project = _org_project(client, auth_headers, org["id"])
        _assign(client, auth_headers, org["id"], project["id"], member_id)
        personal = client.post("/api/projects/", json={"name": "Garden"}, headers=member).json()

        started = client.post(f"/api/projects/{project['id']}/start", json={}, headers=member)
        assert started.status_code == 200, started.text
        assert started.json()["organisation_id"] == org["id"]
        status = client.get("/api/timer/status", headers=member).json()
        assert status["project"]["organisation"]["name"] == "Acme"
        stopped = client.post("/api/projects/stop", json={}, headers=member)
        assert stopped.json()["organisation_id"] == org["id"]

        logged = _beat(client, member, project["id"], "2026-03-03T09:00:00", 60)
        assert logged["organisation_id"] == org["id"]
        # Moved to a personal project, the entry is nobody's record but theirs.
        moved = client.put(
            "/api/beats/",
            json={
                "id": logged["id"],
                "project_id": personal["id"],
                "start": logged["start"],
                "end": logged["end"],
            },
            headers=member,
        )
        assert moved.status_code == 200, moved.text
        assert moved.json()["organisation_id"] is None
        assert (
            client.get(f"/api/beats/{logged['id']}", headers=member).json()["organisation_id"]
            is None
        )

    def test_the_organisations_fields_are_not_the_members_to_write(self, client, auth_headers):
        org = _create_org(client, auth_headers)
        member = _new_user()
        member_id = _member_of(client, auth_headers, org["id"], member)
        project = _org_project(client, auth_headers, org["id"], kind="day_job", color="#5B9CF6")
        _assign(client, auth_headers, org["id"], project["id"], member_id)

        rename = client.put(
            "/api/projects/", json={"id": project["id"], "name": "Mine"}, headers=member
        )
        assert rename.status_code == 409, rename.text
        assert rename.json()["code"] == "ORGANISATION_PROJECT"
        assert "name" in rename.json()["detail"]
        recolour = client.put(
            "/api/projects/",
            json={"id": project["id"], "name": "Platform", "color": "#F87171"},
            headers=member,
        )
        assert recolour.json()["code"] == "ORGANISATION_PROJECT"
        for resp in (
            client.post(f"/api/projects/{project['id']}/archive", headers=member),
            client.post(f"/api/projects/{project['id']}/unarchive", headers=member),
        ):
            assert resp.status_code == 409
            assert resp.json()["code"] == "ORGANISATION_PROJECT"

        # The personal half is theirs: the goal, the local repo paths and,
        # in this stage, the contract.
        goal = client.put(
            "/api/projects/",
            json={
                "id": project["id"],
                "name": "Platform",
                "weekly_goal": 30,
                "autostart_repos": ["/Users/me/platform"],
            },
            headers=member,
        )
        assert goal.status_code == 200, goal.text
        assert goal.json()["weekly_goal"] == 30
        assert goal.json()["autostart_repos"] == ["/Users/me/platform"]
        contract = client.put(
            f"/api/projects/{project['id']}/contract", json={"terms": FULL_TIME}, headers=member
        )
        assert contract.status_code == 200, contract.text
        assert contract.json()["contract"]["terms"][0]["full_time_hours"] == 40
        week = client.get(f"/api/projects/{project['id']}/contract/week", headers=member)
        assert week.status_code == 200

        # Another member on the same project keeps their own half.
        second = _new_user()
        second_id = _member_of(client, auth_headers, org["id"], second)
        _assign(client, auth_headers, org["id"], project["id"], second_id)
        [theirs] = _projects(client, second)
        assert theirs["weekly_goal"] is None
        assert theirs["autostart_repos"] == []
        assert theirs["contract"] is None
        # And the organisation's document carries none of it.
        doc = _db().projects.find_one({"_id": ObjectId(project["id"])})
        assert "user_id" not in doc
        assert "contract" not in doc
        assert "autostart_repos" not in doc
        assert "weekly_goal" not in doc

        # The organisation renames; both see it.
        renamed = client.put(
            f"/api/organisations/{org['id']}/projects/{project['id']}",
            json={"name": "Platform Team"},
            headers=auth_headers,
        )
        assert renamed.status_code == 200, renamed.text
        assert _projects(client, member)[0]["name"] == "Platform Team"
        assert _projects(client, second)[0]["name"] == "Platform Team"

    def test_billing_stays_personal(self, client, auth_headers):
        org = _create_org(client, auth_headers)
        member = _new_user()
        member_id = _member_of(client, auth_headers, org["id"], member)
        project = _org_project(client, auth_headers, org["id"], kind="freelance")
        _assign(client, auth_headers, org["id"], project["id"], member_id)
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
        billed = client.put(
            f"/api/billing/projects/{project['id']}",
            params={"tz": "UTC"},
            json={
                "client_id": kite["id"],
                "rewrite_past": False,
                "terms": [{"effective_from": "2026-03-01", "billable": True}],
            },
            headers=member,
        )
        assert billed.status_code == 409, billed.text
        assert billed.json()["code"] == "ORGANISATION_PROJECT"

    def test_unassigning_takes_the_project_off_the_list_and_keeps_the_hours(
        self, client, auth_headers
    ):
        org = _create_org(client, auth_headers)
        member = _new_user()
        member_id = _member_of(client, auth_headers, org["id"], member)
        project = _org_project(client, auth_headers, org["id"])
        _assign(client, auth_headers, org["id"], project["id"], member_id)
        _beat(client, member, project["id"], "2026-03-03T09:00:00", 60)

        gone = client.delete(
            f"/api/organisations/{org['id']}/projects/{project['id']}/members/{member_id}",
            headers=auth_headers,
        )
        assert gone.status_code == 204
        assert _projects(client, member) == []
        assert (
            client.post(f"/api/projects/{project['id']}/start", json={}, headers=member).status_code
            == 404
        )
        [row] = _members_of_record(_record(client, auth_headers, org["id"]), project["id"])
        assert (row["active"], row["hours"]) == (False, 1.0)
        again = client.delete(
            f"/api/organisations/{org['id']}/projects/{project['id']}/members/{member_id}",
            headers=auth_headers,
        )
        assert again.status_code == 404
        assert again.json()["code"] == "NOT_ASSIGNED"

    def test_reassigning_keeps_the_members_own_half(self, client, auth_headers):
        """Taken off by mistake and put back, a member keeps their goal, repo
        paths and contract — the contract is behind a balance the
        organisation already read."""
        org = _create_org(client, auth_headers)
        member = _new_user()
        member_id = _member_of(client, auth_headers, org["id"], member)
        project = _org_project(client, auth_headers, org["id"], kind="day_job")
        _assign(client, auth_headers, org["id"], project["id"], member_id)
        client.put(
            "/api/projects/",
            json={
                "id": project["id"],
                "name": "Platform",
                "weekly_goal": 30,
                "autostart_repos": ["/Users/me/platform"],
            },
            headers=member,
        )
        client.put(
            f"/api/projects/{project['id']}/contract",
            json={"terms": FULL_TIME, "opening_balance_hours": 5},
            headers=member,
        )
        client.delete(
            f"/api/organisations/{org['id']}/projects/{project['id']}/members/{member_id}",
            headers=auth_headers,
        )
        _assign(client, auth_headers, org["id"], project["id"], member_id)

        [mine] = _projects(client, member)
        assert (mine["weekly_goal"], mine["autostart_repos"]) == (30, ["/Users/me/platform"])
        assert mine["contract"]["opening_balance_hours"] == 5


class TestOrganisationRecord:
    """What the organisation reads, and what the member sees it reading."""

    def _acme_with_hours(self, client, admin, member) -> tuple[dict, dict, str]:
        org = _create_org(client, admin)
        member_id = _member_of(client, admin, org["id"], member)
        project = _org_project(client, admin, org["id"], kind="day_job")
        _assign(client, admin, org["id"], project["id"], member_id)
        _beat(client, member, project["id"], "2026-03-03T09:00:00", 90)
        _beat(client, member, project["id"], "2026-03-04T13:30:00", 30)
        return org, project, member_id

    def test_the_record_is_hours_not_the_person(self, client, auth_headers):
        member = _new_user()
        org, project, member_id = self._acme_with_hours(client, auth_headers, member)
        # A running timer, which the record must not know about.
        client.post(f"/api/projects/{project['id']}/start", json={}, headers=member)
        # A note, which crosses (decision 1), planted as an import would.
        _db().timeLogs.update_one(
            {"user_id": member_id, "project_id": project["id"], "start": datetime(2026, 3, 3, 9)},
            {"$set": {"note": "deploy day", "tags": ["beats", "python"]}},
        )
        absence = client.post(
            f"/api/projects/{project['id']}/absences",
            json={"date": "2026-03-06", "type": "sick", "half_day": True, "note": "migraine"},
            headers=member,
        )
        assert absence.status_code == 201, absence.text
        assert absence.json()["organisation_id"] == org["id"]

        record = _record(client, auth_headers, org["id"])
        assert record["month"] == MONTH
        assert record["organisation"]["name"] == "Acme"
        [row] = _members_of_record(record, project["id"])
        assert row["user_id"] == member_id
        assert row["hours"] == 2.0
        assert [e["hours"] for e in row["entries"]] == [1.5, 0.5]
        assert row["entries"][0]["note"] == "deploy day"
        assert row["entries"][0]["day"] == "2026-03-03"
        assert row["absences"] == [{"date": "2026-03-06", "type": "sick", "half_day": True}]
        assert row["totals"]["entries"] == 2
        assert row["totals"]["hours"] == 2.0
        # Nothing about now, no tags, no absence note, and no key for any of them.
        text = str(record)
        assert "running" not in text
        assert "is_active" not in text
        assert "tags" not in text
        assert "beats" not in text
        assert "python" not in text
        assert "migraine" not in text
        assert row["has_contract"] is False
        assert row["balance"] is None

    def test_a_contract_shows_its_balance(self, client, auth_headers):
        member = _new_user()
        org, project, _member_id = self._acme_with_hours(client, auth_headers, member)
        contract = client.put(
            f"/api/projects/{project['id']}/contract",
            json={"terms": FULL_TIME, "opening_balance_hours": 12, "ended_on": "2026-03-04"},
            headers=member,
        )
        assert contract.status_code == 200, contract.text
        # 12 h opening, 2 h worked, 8 h a day expected over the 43 weekdays
        # of 2026-01-05..2026-03-04 — the figure the member's own week route
        # shows, to the hundredth.
        mine = client.get(
            f"/api/projects/{project['id']}/contract/week", params={"tz": "UTC"}, headers=member
        ).json()
        [row] = _members_of_record(_record(client, auth_headers, org["id"]), project["id"])
        assert row["has_contract"] is True
        assert row["balance"]["balance"] == mine["balance"]
        assert row["balance"]["opening"] == 12.0
        assert row["balance"]["worked"] == 2.0

    def test_what_a_member_sees_is_the_organisations_read_of_them(self, client, auth_headers):
        member = _new_user()
        org, project, member_id = self._acme_with_hours(client, auth_headers, member)
        second = _new_user()
        second_id = _member_of(client, auth_headers, org["id"], second)
        _assign(client, auth_headers, org["id"], project["id"], second_id)
        _beat(client, second, project["id"], "2026-03-05T09:00:00", 120)

        record = _record(client, auth_headers, org["id"])
        visible = _visible(client, member, org["id"])
        # The same read, narrowed to one person: their row is identical, and
        # the other member is not in it.
        [mine_in_record] = [
            r for r in _members_of_record(record, project["id"]) if r["user_id"] == member_id
        ]
        [mine] = _members_of_record(visible, project["id"])
        assert mine == mine_in_record
        assert second_id not in str(visible)
        # A member reads it, an admin reads the record; neither crosses.
        assert (
            client.get(
                f"/api/organisations/{org['id']}/record?month={MONTH}", headers=member
            ).status_code
            == 403
        )


class TestOrganisationWall:
    """Rule 3, in the shape of 1c's tests: another member's personal project,
    a tag, a flow score and a biometric are each unreachable because the
    query is never made — and so, from the outside, are absent from every
    byte the organisation can read."""

    def test_nothing_personal_crosses(self, client, auth_headers):
        org = _create_org(client, auth_headers)
        member = _new_user()
        member_id = _member_of(client, auth_headers, org["id"], member)
        project = _org_project(client, auth_headers, org["id"])
        _assign(client, auth_headers, org["id"], project["id"], member_id)
        _beat(client, member, project["id"], "2026-03-03T09:00:00", 60)

        # The member's personal life, each with a sentinel.
        secret = client.post(
            "/api/projects/", json={"name": "Secret Novel 7b3c"}, headers=member
        ).json()
        _beat(client, member, secret["id"], "2026-03-03T19:00:00", 60)
        _db().timeLogs.update_many(
            {"user_id": member_id}, {"$set": {"tags": ["sentinel-tag-9f1e"]}}
        )
        code = client.post("/api/device/pair/code", headers=member).json()["code"]
        device_token = client.post("/api/device/pair/exchange", json={"code": code}).json()[
            "device_token"
        ]
        device = {"Authorization": f"Bearer {device_token}"}
        now = datetime(2026, 3, 3, 9, 30, tzinfo=UTC)
        flow = client.post(
            "/api/signals/flow-windows",
            json={
                "window_start": now.isoformat(),
                "window_end": (now + timedelta(minutes=5)).isoformat(),
                "flow_score": 0.4242,
                "cadence_score": 0.5,
                "coherence_score": 0.5,
                "category_fit_score": 0.0,
                "idle_fraction": 0.0,
                "dominant_bundle_id": "com.sentinel.editor",
                "dominant_category": "coding",
                "editor_repo": "/tmp/sentinel-repo",
                "active_project_id": project["id"],
            },
            headers=device,
        )
        assert flow.status_code == 201, flow.text
        bio = client.post(
            "/api/biometrics/daily",
            json={"date": "2026-03-03", "source": "oura", "sleep_minutes": 4242, "hrv_ms": 42.42},
            headers=device,
        )
        assert bio.status_code in (200, 201), bio.text

        everything = [
            _record(client, auth_headers, org["id"]),
            client.get(f"/api/organisations/{org['id']}/projects", headers=auth_headers).json(),
            client.get(f"/api/organisations/{org['id']}/members", headers=auth_headers).json(),
        ]
        text = str(everything)
        for sentinel in (
            "Secret Novel",
            "7b3c",
            secret["id"],
            "sentinel-tag-9f1e",
            "0.4242",
            "com.sentinel.editor",
            "sentinel-repo",
            "4242",
            "42.42",
            "flow",
            "biometric",
        ):
            assert sentinel not in text, sentinel
        # And the one entry it does see is the one on its own project.
        [row] = _members_of_record(everything[0], project["id"])
        assert row["totals"]["entries"] == 1

    def test_the_organisations_read_is_keyed_on_its_own_stamp(self, client, auth_headers):
        """The query itself: a beat on the organisation's project but without
        the stamp — one a member moved there by hand in the database, or one
        before `shared_from` on a connected project — is not read, because
        the read asks for the stamp, not the project."""
        org = _create_org(client, auth_headers)
        member = _new_user()
        member_id = _member_of(client, auth_headers, org["id"], member)
        project = _org_project(client, auth_headers, org["id"])
        _assign(client, auth_headers, org["id"], project["id"], member_id)
        stamped = _beat(client, member, project["id"], "2026-03-03T09:00:00", 60)
        _db().timeLogs.insert_one(
            {
                "user_id": member_id,
                "project_id": project["id"],
                "start": datetime(2026, 3, 3, 11),
                "end": datetime(2026, 3, 3, 12),
                "tags": [],
            }
        )
        [row] = _members_of_record(_record(client, auth_headers, org["id"]), project["id"])
        assert [e["id"] for e in row["entries"]] == [stamped["id"]]


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


class TestProjectsIndex:
    """The roadmap's fourth prerequisite: the project list reads through an
    index. Measured on the plan rather than assumed."""

    def test_the_list_is_an_index_scan(self, client, auth_headers):
        client.post("/api/projects/", json={"name": "One"}, headers=auth_headers)
        db = _db()
        plan = db.command(
            "explain",
            {
                "find": "projects",
                "filter": {"user_id": _seeded_id(auth_headers), "archived": False},
            },
            verbosity="queryPlanner",
        )
        winning = str(plan["queryPlanner"]["winningPlan"])
        assert "IXSCAN" in winning, winning
        assert "COLLSCAN" not in winning, winning
        assert "user_id" in winning
        assert "archived" in winning


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    from beats.api.routers.auth import limiter

    limiter.reset()
