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
    return client.post("/api/organisations/join", headers={**headers, "X-Invite-Token": token})


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
        # The membership says whose it is, so a client finds its own row
        # without matching on the address the person joined under.
        assert mine["user_id"] == owner["user_id"]
        assert (
            client.get(f"/api/organisations/{org['id']}", headers=auth_headers).json()["user_id"]
            == owner["user_id"]
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
        preview = client.get(
            "/api/organisations/join",
            headers={**passerby, "X-Invite-Token": invite["token"]},
        )
        assert preview.status_code == 404
        assert preview.json()["code"] == "INVITE_NOT_FOUND"
        assert _join(client, passerby, invite["token"]).status_code == 404

        preview = client.get(
            "/api/organisations/join",
            headers={**invitee, "X-Invite-Token": invite["token"]},
        )
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

    def test_no_join_route_carries_the_token_in_its_path(self, client, auth_headers):
        """Cloud Run's request log keeps every request's full URL for 30
        days, so a token in the path is an unused invitation anyone who can
        read the project's logs can take (#376). Both join routes read it
        from X-Invite-Token and nowhere else."""
        org = _create_org(client, auth_headers)
        invite = _invite(client, auth_headers, org["id"])
        joiner = _new_user()

        in_path = client.get(f"/api/organisations/join/{invite['token']}", headers=joiner)
        assert in_path.status_code == 404
        posted_in_path = client.post(f"/api/organisations/join/{invite['token']}", headers=joiner)
        assert posted_in_path.status_code in (404, 405)
        # Missing header: malformed, not a token that failed to resolve.
        assert client.get("/api/organisations/join", headers=joiner).status_code == 422
        assert client.post("/api/organisations/join", headers=joiner).status_code == 422

        # And the header still works.
        assert _join(client, joiner, invite["token"]).status_code == 200

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
        # The request says what approving it grants: the invite's role.
        assert request["role"] == "member"
        decided = client.post(
            f"/api/organisations/{org['id']}/requests/{request['id']}",
            json={"decision": "approved"},
            headers=auth_headers,
        )
        assert decided.status_code == 200, decided.text
        assert decided.json()["role"] == "member"
        [mine] = client.get("/api/organisations/", headers=applicant).json()
        assert mine["organisation"]["id"] == org["id"]
        assert (
            client.get(f"/api/organisations/{org['id']}/requests", headers=auth_headers).json()
            == []
        )

        # A link that grants more than membership says so on its requests.
        admin_link = _invite(client, auth_headers, org["id"], requires_approval=True, role="admin")
        hopeful = _new_user()
        assert _join(client, hopeful, admin_link["token"]).json()["status"] == "pending"
        [asking] = client.get(
            f"/api/organisations/{org['id']}/requests", headers=auth_headers
        ).json()
        assert asking["role"] == "admin"
        client.post(
            f"/api/organisations/{org['id']}/requests/{asking['id']}",
            json={"decision": "declined"},
            headers=auth_headers,
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

    def test_the_month_is_the_organisations_timezone_whoever_asks(self, client, auth_headers):
        """#415: the lock and the freeze bucket by the organisation's
        timezone, and until this the reads bucket by the caller's — so two
        deciders downloaded two different legal records of one month, and
        the record could disagree with the month it was frozen from."""
        org = _create_org(client, auth_headers, timezone="Europe/Berlin")
        member = _new_user()
        member_id = _member_of(client, auth_headers, org["id"], member)
        project = _org_project(client, auth_headers, org["id"])
        _assign(client, auth_headers, org["id"], project["id"], member_id)
        # 23:30 UTC on 31 March is 01:30 on 1 April in Berlin, so the entry
        # is April's — in Lisbon, in Berlin, and for a caller sending UTC.
        _beat(client, member, project["id"], "2026-03-31T23:30:00", 30)

        for tz in ("UTC", "Europe/Lisbon", "Asia/Tokyo"):
            [march] = _members_of_record(
                _record(client, auth_headers, org["id"], month="2026-03", tz=tz), project["id"]
            )
            assert march["entries"] == []
            [april] = _members_of_record(
                _record(client, auth_headers, org["id"], month="2026-04", tz=tz), project["id"]
            )
            assert [e["day"] for e in april["entries"]] == ["2026-04-01"]

        # The member's own view of it is the same read, so it agrees.
        [seen] = _members_of_record(
            _visible(client, member, org["id"], month="2026-04", tz="UTC"), project["id"]
        )
        assert [e["day"] for e in seen["entries"]] == ["2026-04-01"]


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


class TestDeletingAnOrganisation:
    """#347: closing is notice, deletion is the hand-back. An owner starts
    a clock every member sees in-app; when it runs out, each member gets a
    personal copy of what connecting once took, and the organisation's
    record goes with the organisation."""

    def test_the_notice_has_a_floor_and_a_default(self, client, auth_headers):
        org = _create_org(client, auth_headers)
        soon = (datetime.now(UTC).date() + timedelta(days=10)).isoformat()
        refused = client.post(
            f"/api/organisations/{org['id']}/close",
            json={"closes_on": soon},
            headers=auth_headers,
        )
        assert refused.status_code == 409, refused.text
        assert refused.json()["code"] == "CLOSE_NOTICE_TOO_SHORT"

        started = client.post(
            f"/api/organisations/{org['id']}/close", json={}, headers=auth_headers
        )
        assert started.status_code == 200, started.text
        default = date.fromisoformat(started.json()["closes_on"])
        assert default >= datetime.now(UTC).date() + timedelta(days=59)

        # Every member reads the state; only an owner sets or clears it.
        member = _new_user()
        _member_of(client, auth_headers, org["id"], member)
        seen = client.get(f"/api/organisations/{org['id']}", headers=member)
        assert seen.json()["organisation"]["closes_on"] == started.json()["closes_on"]
        assert (
            client.post(
                f"/api/organisations/{org['id']}/close", json={}, headers=member
            ).status_code
            == 403
        )

        # Deletion waits for the day; cancel clears the clock.
        waiting = client.delete(f"/api/organisations/{org['id']}", headers=auth_headers)
        assert waiting.status_code == 409
        assert waiting.json()["code"] == "ORGANISATION_STILL_CLOSING"
        cancelled = client.delete(f"/api/organisations/{org['id']}/close", headers=auth_headers)
        assert cancelled.status_code == 200
        assert cancelled.json()["closes_on"] is None
        not_closing = client.delete(f"/api/organisations/{org['id']}", headers=auth_headers)
        assert not_closing.status_code == 409
        assert not_closing.json()["code"] == "ORGANISATION_NOT_CLOSING"

    def test_deletion_hands_every_member_back_their_own(self, client, auth_headers):
        org = _create_org(client, auth_headers)
        member = _new_user()
        member_id = _member_of(client, auth_headers, org["id"], member)
        project = _org_project(client, auth_headers, org["id"], kind="day_job")
        _assign(client, auth_headers, org["id"], project["id"], member_id)
        client.put(
            f"/api/projects/{project['id']}/contract", json={"terms": FULL_TIME}, headers=member
        )
        _beat(client, member, project["id"], "2026-03-03T09:00:00", 60)
        # A tombstoned ex-member's row: goes with the record's keeper.
        db = _db()
        stamped = db.timeLogs.find_one({"organisation_id": org["id"]})
        db.timeLogs.insert_one(
            {k: v for k, v in stamped.items() if k != "_id"} | {"user_id": "erased:gone"}
        )

        assert (
            client.post(
                f"/api/organisations/{org['id']}/close", json={}, headers=auth_headers
            ).status_code
            == 200
        )
        db.organisations.update_one(
            {"_id": ObjectId(org["id"])},
            {"$set": {"closes_on": (datetime.now(UTC).date() - timedelta(days=1)).isoformat()}},
        )
        gone = client.delete(f"/api/organisations/{org['id']}", headers=auth_headers)
        assert gone.status_code == 204, gone.text

        # The member keeps one timeline: a personal copy of the project,
        # same name and kind, the contract theirs again, the entry on it
        # and no longer anyone's record.
        [mine] = _projects(client, member)
        assert mine["name"] == project["name"]
        assert mine["kind"] == "day_job"
        assert mine["organisation"] is None
        assert mine["contract"] is not None
        week = client.get(
            f"/api/projects/{mine['id']}/contract/week", params={"tz": "UTC"}, headers=member
        )
        assert week.status_code == 200
        own = db.timeLogs.find_one({"user_id": member_id})
        assert own["project_id"] == mine["id"]
        assert "organisation_id" not in own

        # The organisation is gone whole: no membership, no rows, no stones.
        assert client.get(f"/api/organisations/{org['id']}", headers=member).status_code == 404
        assert db.org_members.count_documents({"organisation_id": org["id"]}) == 0
        assert db.org_audit.count_documents({"organisation_id": org["id"]}) == 0
        assert db.timeLogs.count_documents({"user_id": "erased:gone"}) == 0
        assert db.projects.count_documents({"organisation_id": org["id"]}) == 0


class TestRetention:
    """The retention setting over its statutory floor, and the purge pass
    (docs/organisations.md, stage 4 — retention). Expiry removes the
    organisation's record, never the person's data."""

    def _settings(self, client, headers, org: dict, **changes):
        body = {"name": org["name"], **changes}
        return client.put(f"/api/organisations/{org['id']}", json=body, headers=headers)

    @staticmethod
    def _purge(*, apply: bool = False, today: date | None = None):
        """One pass of the operator's purge over the test database."""
        from beats.infrastructure.retention import purge_expired_records

        async def run():
            from pymongo import AsyncMongoClient

            client_ = AsyncMongoClient(os.environ.get("DB_DSN", "mongodb://localhost:27017"))
            try:
                return await purge_expired_records(
                    client_[os.environ.get("DB_NAME", "beats_test")], today=today, apply=apply
                )
            finally:
                await client_.close()

        return asyncio.run(run())

    @staticmethod
    def _counts(report, org_id: str):
        [mine] = [o for o in report.organisations if o.organisation_id == org_id]
        return mine

    def test_the_floor_is_the_jurisdictions_not_ours(self, client, auth_headers):
        spain = _create_org(client, auth_headers, name="Madrid", holiday_country="ES")
        refused = self._settings(
            client, auth_headers, spain, holiday_country="ES", retention_years=3
        )
        assert refused.status_code == 409, refused.text
        assert refused.json()["code"] == "RETENTION_BELOW_FLOOR"
        assert "4 years" in refused.json()["detail"]
        kept = self._settings(client, auth_headers, spain, holiday_country="ES", retention_years=4)
        assert kept.status_code == 200, kept.text
        assert kept.json()["retention_years"] == 4

        berlin = _create_org(client, auth_headers, name="Berlin", holiday_country="DE")
        two = self._settings(client, auth_headers, berlin, holiday_country="DE", retention_years=2)
        assert two.status_code == 200, two.text

        # No country: the strictest common floor holds, so a gap in the
        # table can never allow deleting below a law not written down.
        nowhere = _create_org(client, auth_headers, name="Nowhere")
        assert self._settings(client, auth_headers, nowhere, retention_years=3).status_code == 409

    def test_an_unset_period_is_never_below_the_countrys_floor(self, client, auth_headers):
        """Poland keeps working-time records ten years. An organisation that
        never set a period reads as the four-year default, so purging on the
        stored field would take its record six years early."""
        org = _create_org(client, auth_headers, name="Kraków", holiday_country="PL")
        member = _new_user()
        member_id = _member_of(client, auth_headers, org["id"], member)
        project = _org_project(client, auth_headers, org["id"])
        _assign(client, auth_headers, org["id"], project["id"], member_id)
        _beat(client, member, project["id"], "2026-03-03T09:00:00", 60)

        kept = self._counts(self._purge(today=date(2031, 3, 4)), org["id"])
        assert kept.years == 10
        assert not any(kept.counts.values()), "a five-year-old Polish record is still owed"

    def test_expiry_unstamps_the_living_and_deletes_the_tombstoned(self, client, auth_headers):
        org = _create_org(client, auth_headers)
        member = _new_user()
        member_id = _member_of(client, auth_headers, org["id"], member)
        project = _org_project(client, auth_headers, org["id"])
        _assign(client, auth_headers, org["id"], project["id"], member_id)
        old = _beat(client, member, project["id"], "2020-01-10T09:00:00", 60)
        young = _beat(client, member, project["id"], "2026-03-03T09:00:00", 60)
        db = _db()
        # A tombstoned ex-member's old row, and records only the purge reads:
        # an expired timesheet and an audit event older than the cutoff.
        stone = dict(db.timeLogs.find_one({"_id": ObjectId(old["id"])}))
        stone.pop("_id")
        stone_id = db.timeLogs.insert_one({**stone, "user_id": "erased:m1"}).inserted_id
        # A tombstoned balance adjustment carries no stamp — the purge must
        # find it through the organisation's projects, as erasure left it.
        db.balance_adjustments.insert_one(
            {
                "user_id": "erased:m1",
                "project_id": project["id"],
                "date": "2020-01-12",
                "kind": "delta",
                "hours": 2.0,
            }
        )
        db.org_timesheets.insert_one(
            {
                "organisation_id": org["id"],
                "project_id": project["id"],
                "user_id": "erased:m1",
                "month": "2020-01-01",
                "status": "approved",
                "history": [],
            }
        )
        db.org_audit.insert_one(
            {
                "organisation_id": org["id"],
                "at": "2020-01-10T09:00:00",
                "event": "old",
                "details": {},
            }
        )

        mine = self._counts(self._purge(), org["id"])
        assert mine.counts["beats_unstamped"] == 1
        assert mine.counts["beats_deleted"] == 1
        assert mine.counts["adjustments_deleted"] == 1
        assert mine.counts["timesheets_deleted"] == 1
        assert mine.counts["audit_deleted"] == 1
        # Dry means dry: the stamp is still on the old row.
        assert db.timeLogs.find_one({"_id": ObjectId(old["id"])})["organisation_id"] == org["id"]

        self._purge(apply=True)
        survivor = db.timeLogs.find_one({"_id": ObjectId(old["id"])})
        assert survivor is not None, "a living member's row is theirs, not the record's"
        assert "organisation_id" not in survivor
        assert db.timeLogs.find_one({"_id": stone_id}) is None
        assert db.balance_adjustments.count_documents({"user_id": "erased:m1"}) == 0
        assert db.timeLogs.find_one({"_id": ObjectId(young["id"])})["organisation_id"] == org["id"]
        assert db.org_timesheets.count_documents({"organisation_id": org["id"]}) == 0
        assert db.org_audit.count_documents({"organisation_id": org["id"], "event": "old"}) == 0
        assert (
            db.org_audit.count_documents(
                {"organisation_id": org["id"], "event": "retention.purged"}
            )
            == 1
        )
        # The organisation's read agrees: only the young entry remains.
        [row] = _members_of_record(_record(client, auth_headers, org["id"]), project["id"])
        assert [e["day"] for e in row["entries"]] == ["2026-03-03"]


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


# --- Stage 3 and 4: employment (docs/organisations.md) ------------------------


def _employed(client, admin, member, *, managed: bool = True) -> tuple[dict, dict, str]:
    """Acme with `member` assigned to a day-job project; with `managed`, the
    contract taken under the organisation's hand with FULL_TIME terms."""
    org = _create_org(client, admin)
    member_id = _member_of(client, admin, org["id"], member)
    project = _org_project(client, admin, org["id"], kind="day_job")
    _assign(client, admin, org["id"], project["id"], member_id)
    if managed:
        resp = client.put(
            f"/api/organisations/{org['id']}/projects/{project['id']}/members/{member_id}/contract",
            json={"contract": {"terms": FULL_TIME, "opening_balance_hours": 2}, "managed": True},
            headers=admin,
        )
        assert resp.status_code == 200, resp.text
    return org, project, member_id


def _submit(client, headers, org_id: str, project_id: str, month: str):
    return client.post(
        f"/api/organisations/{org_id}/timesheets",
        json={"project_id": project_id, "month": f"{month}-01"},
        headers=headers,
    )


def _decide_sheet(client, headers, org_id: str, sheet_id: str, *, approve: bool, comment=None):
    return client.post(
        f"/api/organisations/{org_id}/timesheets/{sheet_id}/decision",
        json={"approve": approve, "comment": comment},
        headers=headers,
    )


class TestManagedContracts:
    """Stage 3: the contract belongs to the employer (decision in
    docs/organisations.md). Taking one under management starts from the terms
    the member recorded; from then on the member reads their week and balance
    as ever and writes none of the contract's inputs."""

    def test_management_starts_from_the_members_own_terms(self, client, auth_headers):
        org = _create_org(client, auth_headers)
        member = _new_user()
        member_id = _member_of(client, auth_headers, org["id"], member)
        project = _org_project(client, auth_headers, org["id"], kind="day_job")
        _assign(client, auth_headers, org["id"], project["id"], member_id)
        # The member recorded their own terms first.
        client.put(
            f"/api/projects/{project['id']}/contract",
            json={"terms": FULL_TIME, "opening_balance_hours": 7},
            headers=member,
        )
        taken = client.put(
            f"/api/organisations/{org['id']}/projects/{project['id']}/members/{member_id}/contract",
            json={"contract": None, "managed": True},
            headers=auth_headers,
        )
        assert taken.status_code == 200, taken.text
        assert taken.json()["managed"] is True
        # Nothing rewritten: the opening balance the member relied on stands.
        assert taken.json()["contract"]["opening_balance_hours"] == 7
        [mine] = _projects(client, member)
        assert mine["organisation"]["contract_managed"] is True
        assert mine["contract"]["opening_balance_hours"] == 7

    def test_the_members_own_writes_are_refused_while_managed(self, client, auth_headers):
        member = _new_user()
        _org, project, _member_id = _employed(client, auth_headers, member)
        for resp in (
            client.put(
                f"/api/projects/{project['id']}/contract",
                json={"terms": FULL_TIME, "opening_balance_hours": 99},
                headers=member,
            ),
            client.post(
                f"/api/projects/{project['id']}/absences",
                json={"date": "2026-03-06", "type": "vacation"},
                headers=member,
            ),
            client.post(
                f"/api/projects/{project['id']}/adjustments",
                params={"tz": "UTC"},
                json={"date": "2026-03-02", "kind": "delta", "hours": -8},
                headers=member,
            ),
        ):
            assert resp.status_code == 409, resp.text
            assert resp.json()["code"] == "CONTRACT_MANAGED"
        # Reading is untouched: the week and the ledger answer as ever.
        week = client.get(
            f"/api/projects/{project['id']}/contract/week", params={"tz": "UTC"}, headers=member
        )
        assert week.status_code == 200
        assert week.json()["balance"] is not None

    def test_the_employer_writes_terms_and_adjustments_and_can_hand_back(
        self, client, auth_headers
    ):
        member = _new_user()
        org, project, member_id = _employed(client, auth_headers, member)
        base = f"/api/organisations/{org['id']}/projects/{project['id']}/members/{member_id}"
        changed = client.put(
            f"{base}/contract",
            json={
                "contract": {
                    "terms": [
                        {
                            "effective_from": "2026-01-05",
                            "schedule_type": "part_time",
                            "full_time_hours": 40,
                            "percentage": 0.8,
                        }
                    ],
                    "opening_balance_hours": 2,
                },
                "managed": True,
            },
            headers=auth_headers,
        )
        assert changed.status_code == 200, changed.text
        [mine] = _projects(client, member)
        assert mine["contract"]["terms"][0]["percentage"] == 0.8
        payout = client.post(
            f"{base}/adjustments",
            json={"date": "2026-03-02", "kind": "delta", "hours": -8},
            headers=auth_headers,
        )
        assert payout.status_code == 201, payout.text
        # The ledger reaches back to the adjustment's week (March is further
        # than the default eight weeks from a later today).
        ledger = client.get(
            f"/api/projects/{project['id']}/ledger",
            params={"tz": "UTC", "weeks": 104},
            headers=member,
        ).json()
        assert any(a["hours"] == -8 for w in ledger["weeks"] for a in w["adjustments"])
        # Handed back, the member writes again.
        released = client.put(
            f"{base}/contract", json={"contract": None, "managed": False}, headers=auth_headers
        )
        assert released.status_code == 200
        own = client.post(
            f"/api/projects/{project['id']}/absences",
            json={"date": "2026-03-06", "type": "vacation"},
            headers=member,
        )
        assert own.status_code == 201, own.text

    def test_an_unmanaged_assignment_takes_no_employer_adjustment(self, client, auth_headers):
        member = _new_user()
        org, project, member_id = _employed(client, auth_headers, member, managed=False)
        resp = client.post(
            f"/api/organisations/{org['id']}/projects/{project['id']}"
            f"/members/{member_id}/adjustments",
            json={"date": "2026-03-02", "kind": "delta", "hours": -8},
            headers=auth_headers,
        )
        assert resp.status_code == 409
        assert resp.json()["code"] == "NOT_MANAGED"


class TestAbsenceRequests:
    """Stage 3: on a managed assignment the employee asks, a decider
    approves — which books the absence, stamped — or declines."""

    def test_the_request_flow(self, client, auth_headers):
        member = _new_user()
        org, project, _member_id = _employed(client, auth_headers, member)
        asked = client.post(
            f"/api/organisations/{org['id']}/absence-requests",
            json={
                "project_id": project["id"],
                "date": "2026-03-06",
                "type": "vacation",
                "note": "long weekend with family",
            },
            headers=member,
        )
        assert asked.status_code == 201, asked.text
        request = asked.json()
        assert request["status"] == "pending"

        # The decider sees it, note included: it is addressed to them.
        [pending] = client.get(
            f"/api/organisations/{org['id']}/absence-requests",
            params={"pending": True},
            headers=auth_headers,
        ).json()
        assert pending["note"] == "long weekend with family"

        approved = client.post(
            f"/api/organisations/{org['id']}/absence-requests/{request['id']}/decision",
            json={"approve": True, "comment": "enjoy"},
            headers=auth_headers,
        )
        assert approved.status_code == 200, approved.text
        assert approved.json()["status"] == "approved"
        # The absence is booked, stamped, on the member's own project —
        # and the organisation's record shows it without the note.
        [absence] = client.get(f"/api/projects/{project['id']}/absences", headers=member).json()
        assert (absence["date"], absence["organisation_id"]) == ("2026-03-06", org["id"])
        [row] = _members_of_record(_record(client, auth_headers, org["id"]), project["id"])
        assert [a["date"] for a in row["absences"]] == ["2026-03-06"]
        assert "long weekend" not in str(row)

        # Decided once: a second decision is a 409.
        again = client.post(
            f"/api/organisations/{org['id']}/absence-requests/{request['id']}/decision",
            json={"approve": False},
            headers=auth_headers,
        )
        assert again.status_code == 409
        assert again.json()["code"] == "REQUEST_DECIDED"

    def test_declined_books_nothing_and_a_pending_request_can_be_withdrawn(
        self, client, auth_headers
    ):
        member = _new_user()
        org, project, _member_id = _employed(client, auth_headers, member)
        url = f"/api/organisations/{org['id']}/absence-requests"
        first = client.post(
            url,
            json={"project_id": project["id"], "date": "2026-03-05", "type": "sick"},
            headers=member,
        ).json()
        declined = client.post(
            f"{url}/{first['id']}/decision",
            json={"approve": False, "comment": "come in, we'll see"},
            headers=auth_headers,
        )
        assert declined.status_code == 200
        assert client.get(f"/api/projects/{project['id']}/absences", headers=member).json() == []
        # The member sees the decision and its comment on their own list.
        mine = client.get(url, headers=member).json()
        assert [(r["status"], r["comment"]) for r in mine] == [("declined", "come in, we'll see")]

        second = client.post(
            url,
            json={"project_id": project["id"], "date": "2026-03-09", "type": "vacation"},
            headers=member,
        ).json()
        assert client.delete(f"{url}/{second['id']}", headers=member).status_code == 204
        # A decided one stays.
        assert client.delete(f"{url}/{first['id']}", headers=member).status_code == 404

    def test_an_unmanaged_assignment_needs_no_request(self, client, auth_headers):
        member = _new_user()
        org, project, _member_id = _employed(client, auth_headers, member, managed=False)
        resp = client.post(
            f"/api/organisations/{org['id']}/absence-requests",
            json={"project_id": project["id"], "date": "2026-03-06", "type": "vacation"},
            headers=member,
        )
        assert resp.status_code == 409
        assert resp.json()["code"] == "NOT_MANAGED"


class TestTimesheets:
    """Stage 3's one architectural change: approval freezes the month's
    figures — the first stored derived figure anywhere — and from then on a
    write dated inside the month is refused until a decider reopens it."""

    def test_submit_approve_freeze_and_lock(self, client, auth_headers):
        member = _new_user()
        org, project, member_id = _employed(client, auth_headers, member)
        _beat(client, member, project["id"], "2026-03-03T09:00:00", 90)
        kept = _beat(client, member, project["id"], "2026-03-04T09:00:00", 30)

        # The current month has not ended.
        this_month = date.today().strftime("%Y-%m")
        assert (
            _submit(client, member, org["id"], project["id"], this_month).json()["code"]
            == "MONTH_NOT_ENDED"
        )

        submitted = _submit(client, member, org["id"], project["id"], "2026-03")
        assert submitted.status_code == 201, submitted.text
        sheet = submitted.json()
        assert sheet["status"] == "submitted"
        assert sheet["frozen"] is None

        approved = _decide_sheet(
            client, auth_headers, org["id"], sheet["id"], approve=True, comment="looks right"
        )
        assert approved.status_code == 200, approved.text
        frozen = approved.json()["frozen"]
        assert frozen["worked"] == 2.0
        assert frozen["entries"] == 2
        # FULL_TIME expects 8 h per weekday of March 2026 (22 weekdays).
        assert frozen["expected"] == 176.0
        assert frozen["balance_end"] is not None

        # Every write dated inside the month is now refused, everywhere.
        for resp in (
            client.post(
                "/api/beats/",
                json={
                    "project_id": project["id"],
                    "start": "2026-03-10T09:00:00Z",
                    "end": "2026-03-10T10:00:00Z",
                },
                headers=member,
            ),
            client.put(
                "/api/beats/",
                json={
                    "id": kept["id"],
                    "project_id": project["id"],
                    "start": "2026-03-04T10:00:00Z",
                    "end": "2026-03-04T11:00:00Z",
                },
                headers=member,
            ),
            client.delete(f"/api/beats/{kept['id']}", headers=member),
            client.post(
                f"/api/projects/{project['id']}/start",
                json={"time": "2026-03-11T09:00:00Z"},
                headers=member,
            ),
            client.post(
                f"/api/organisations/{org['id']}/projects/{project['id']}"
                f"/members/{member_id}/entries",
                json={"start": "2026-03-12T09:00:00Z", "end": "2026-03-12T10:00:00Z"},
                headers=auth_headers,
            ),
        ):
            assert resp.status_code == 409, resp.text
            assert resp.json()["code"] == "PERIOD_APPROVED"
        # An entry outside the month still lands.
        _beat(client, member, project["id"], "2026-04-01T09:00:00", 30)

        # A member still reads everything; only a decider reopens.
        reopened = client.post(
            f"/api/organisations/{org['id']}/timesheets/{sheet['id']}/reopen",
            json={"reason": "a forgotten Friday"},
            headers=auth_headers,
        )
        assert reopened.status_code == 200, reopened.text
        assert reopened.json()["status"] == "reopened"
        assert reopened.json()["frozen"] is None
        _beat(client, member, project["id"], "2026-03-06T09:00:00", 60)

        # Resubmitted and re-approved, the freeze is fresh.
        sheet2 = _submit(client, member, org["id"], project["id"], "2026-03").json()
        refrozen = _decide_sheet(client, auth_headers, org["id"], sheet2["id"], approve=True)
        assert refrozen.json()["frozen"]["worked"] == 3.0
        history = [h["action"] for h in refrozen.json()["history"]]
        assert history == ["submitted", "approved", "reopened", "submitted", "approved"]

    def test_the_lock_holds_against_a_removal_and_a_backup(self, client, auth_headers):
        """A timesheet needs no managed contract, so an approved month can
        sit on an assignment the member still writes to. Three writes
        walked past the lock (#405): removing an absence, removing a
        balance adjustment, and restoring a backup's session over it."""
        member = _new_user()
        org, project, _member_id = _employed(client, auth_headers, member, managed=False)
        contract = client.put(
            f"/api/projects/{project['id']}/contract",
            json={"terms": FULL_TIME, "opening_balance_hours": 2},
            headers=member,
        )
        assert contract.status_code == 200, contract.text
        off = client.post(
            f"/api/projects/{project['id']}/absences",
            json={"date": "2026-03-10", "type": "vacation"},
            headers=member,
        )
        assert off.status_code in (200, 201), off.text
        payout = client.post(
            f"/api/projects/{project['id']}/adjustments",
            params={"tz": "UTC"},
            json={"date": "2026-03-11", "kind": "delta", "hours": -4},
            headers=member,
        )
        assert payout.status_code in (200, 201), payout.text
        kept = _beat(client, member, project["id"], "2026-03-04T09:00:00", 60)

        sheet = _submit(client, member, org["id"], project["id"], "2026-03").json()
        assert (
            _decide_sheet(client, auth_headers, org["id"], sheet["id"], approve=True).status_code
            == 200
        )

        for resp in (
            client.delete(
                f"/api/projects/{project['id']}/absences/{off.json()['id']}", headers=member
            ),
            client.delete(
                f"/api/projects/{project['id']}/adjustments/{payout.json()['id']}", headers=member
            ),
        ):
            assert resp.status_code == 409, resp.text
            assert resp.json()["code"] == "PERIOD_APPROVED"

        # A backup writes beats straight to storage, so it needs the check
        # of its own: the session inside the month is left out and said so,
        # and the one outside it lands.
        backup = {
            "version": "1.3",
            "exported_at": "2026-04-01T00:00:00Z",
            "projects": [],
            "beats": [
                {
                    "id": str(ObjectId()),
                    "project_id": project["id"],
                    "start": "2026-03-20T09:00:00Z",
                    "end": "2026-03-20T10:00:00Z",
                },
                {
                    "id": str(ObjectId()),
                    "project_id": project["id"],
                    "start": "2026-04-20T09:00:00Z",
                    "end": "2026-04-20T10:00:00Z",
                },
            ],
        }
        restored = client.post(
            "/api/export/import",
            files={"file": ("backup.json", json.dumps(backup), "application/json")},
            headers=member,
        )
        assert restored.status_code == 200, restored.text
        assert restored.json()["imported"]["beats"] == 1
        [skip] = restored.json()["skipped"]
        assert (skip["collection"], skip["code"], skip["date"]) == (
            "beats",
            "PERIOD_APPROVED",
            "2026-03-20",
        )
        # The approved month is as it was: the absence, the adjustment and
        # the one session it was frozen with.
        assert (
            len(client.get(f"/api/beats/?project_id={project['id']}", headers=member).json()) == 2
        )
        assert kept["id"] in [
            b["id"]
            for b in client.get(f"/api/beats/?project_id={project['id']}", headers=member).json()
        ]

    def test_changes_requested_and_resubmission(self, client, auth_headers):
        member = _new_user()
        org, project, _member_id = _employed(client, auth_headers, member)
        _beat(client, member, project["id"], "2026-03-03T09:00:00", 60)
        sheet = _submit(client, member, org["id"], project["id"], "2026-03").json()
        back = _decide_sheet(
            client,
            auth_headers,
            org["id"],
            sheet["id"],
            approve=False,
            comment="Tuesday looks short",
        )
        assert back.status_code == 200
        assert back.json()["status"] == "changes_requested"
        assert back.json()["comment"] == "Tuesday looks short"
        # Nothing is locked: the member fixes the day and resubmits.
        _beat(client, member, project["id"], "2026-03-03T14:00:00", 60)
        again = _submit(client, member, org["id"], project["id"], "2026-03")
        assert again.status_code == 201
        assert again.json()["status"] == "submitted"

    def test_approval_waits_for_a_running_timer_in_the_month(self, client, auth_headers):
        member = _new_user()
        org, project, _member_id = _employed(client, auth_headers, member)
        started = client.post(
            f"/api/projects/{project['id']}/start",
            json={"time": "2026-03-31T23:00:00Z"},
            headers=member,
        )
        assert started.status_code == 200, started.text
        sheet = _submit(client, member, org["id"], project["id"], "2026-03").json()
        refused = _decide_sheet(client, auth_headers, org["id"], sheet["id"], approve=True)
        assert refused.status_code == 409, refused.text
        assert refused.json()["code"] == "PERIOD_APPROVED"
        client.post("/api/projects/stop", json={}, headers=member)
        assert (
            _decide_sheet(client, auth_headers, org["id"], sheet["id"], approve=True).status_code
            == 200
        )

    def test_a_member_sees_their_own_sheets_and_cannot_decide(self, client, auth_headers):
        member = _new_user()
        org, project, _member_id = _employed(client, auth_headers, member)
        sheet = _submit(client, member, org["id"], project["id"], "2026-03").json()
        [own] = client.get(f"/api/organisations/{org['id']}/timesheets", headers=member).json()
        assert own["id"] == sheet["id"]
        refused = _decide_sheet(client, member, org["id"], sheet["id"], approve=True)
        assert refused.status_code == 403
        assert refused.json()["code"] == "ORGANISATION_ROLE_REQUIRED"


class TestTeamsAndRoles:
    """Stage 4: a manager decides and reads for the members of their teams;
    a viewer reads the whole record and changes nothing."""

    def _org_with_team(self, client, admin):
        manager = _new_user()
        inside = _new_user()
        outside = _new_user()
        org = _create_org(client, admin)
        manager_id = _member_of(client, admin, org["id"], manager, role="manager")
        inside_id = _member_of(client, admin, org["id"], inside)
        outside_id = _member_of(client, admin, org["id"], outside)
        project = _org_project(client, admin, org["id"], kind="day_job")
        for uid in (inside_id, outside_id):
            _assign(client, admin, org["id"], project["id"], uid)
        team = client.post(
            f"/api/organisations/{org['id']}/teams",
            json={"name": "Platform crew", "member_ids": [manager_id, inside_id]},
            headers=admin,
        )
        assert team.status_code == 201, team.text
        return org, project, (manager, manager_id), (inside, inside_id), (outside, outside_id)

    def test_a_manager_decides_inside_their_teams_and_nowhere_else(self, client, auth_headers):
        org, project, (manager, _), (inside, inside_id), (outside, outside_id) = (
            self._org_with_team(client, auth_headers)
        )
        base = f"/api/organisations/{org['id']}/projects/{project['id']}"
        ok = client.put(
            f"{base}/members/{inside_id}/contract",
            json={"contract": {"terms": FULL_TIME}, "managed": True},
            headers=manager,
        )
        assert ok.status_code == 200, ok.text
        refused = client.put(
            f"{base}/members/{outside_id}/contract",
            json={"contract": {"terms": FULL_TIME}, "managed": True},
            headers=manager,
        )
        assert refused.status_code == 403
        assert refused.json()["code"] == "OUTSIDE_MANAGER_SCOPE"

        # Their record is their teams': the outside member's row is not in it.
        _beat(client, inside, project["id"], "2026-03-03T09:00:00", 60)
        _beat(client, outside, project["id"], "2026-03-03T11:00:00", 60)
        rows = _members_of_record(_record(client, manager, org["id"]), project["id"])
        assert [r["user_id"] for r in rows] == [inside_id]
        # And a manager administers nothing.
        assert (
            client.post(
                f"/api/organisations/{org['id']}/invites", json={}, headers=manager
            ).status_code
            == 403
        )

    def test_a_decider_reads_the_names_without_the_admins_project_list(self, client, auth_headers):
        """A manager is shown the approvals but may not list the
        organisation's projects. The rows name themselves, so the decision
        does not have to be made against an id."""
        org, project, (manager, _), (inside, inside_id), _ = self._org_with_team(
            client, auth_headers
        )
        client.put(
            f"/api/organisations/{org['id']}/projects/{project['id']}/members/{inside_id}/contract",
            json={"contract": {"terms": FULL_TIME}, "managed": True},
            headers=manager,
        )
        assert (
            client.get(f"/api/organisations/{org['id']}/projects", headers=manager).status_code
            == 403
        )

        asked = client.post(
            f"/api/organisations/{org['id']}/absence-requests",
            json={"project_id": project["id"], "date": "2026-03-06", "type": "vacation"},
            headers=inside,
        )
        assert asked.status_code == 201, asked.text
        [pending] = client.get(
            f"/api/organisations/{org['id']}/absence-requests",
            params={"pending": True},
            headers=manager,
        ).json()
        name = _me(client, inside)["email"]
        assert (pending["project_name"], pending["member_name"]) == (project["name"], name)

        _submit(client, inside, org["id"], project["id"], "2026-03")
        [sheet] = client.get(f"/api/organisations/{org['id']}/timesheets", headers=manager).json()
        assert (sheet["project_name"], sheet["member_name"]) == (project["name"], name)

    def test_a_decided_row_still_names_a_member_who_left(self, client, auth_headers):
        """`/members` lists the active ones, so the name on a decision has to
        outlive the membership: the record is read long after someone goes."""
        member = _new_user()
        org, project, member_id = _employed(client, auth_headers, member)
        [listed] = [
            m
            for m in client.get(
                f"/api/organisations/{org['id']}/members", headers=auth_headers
            ).json()
            if m["user_id"] == member_id
        ]
        asked = client.post(
            f"/api/organisations/{org['id']}/absence-requests",
            json={"project_id": project["id"], "date": "2026-03-06", "type": "vacation"},
            headers=member,
        )
        request_id = asked.json()["id"]
        client.post(
            f"/api/organisations/{org['id']}/absence-requests/{request_id}/decision",
            json={"approve": True},
            headers=auth_headers,
        )
        _submit(client, member, org["id"], project["id"], "2026-03")
        assert (
            client.delete(
                f"/api/organisations/{org['id']}/members/{member_id}", headers=auth_headers
            ).status_code
            == 204
        )

        assert not [
            m
            for m in client.get(
                f"/api/organisations/{org['id']}/members", headers=auth_headers
            ).json()
            if m["user_id"] == member_id
        ]
        [gone] = client.get(
            f"/api/organisations/{org['id']}/absence-requests", headers=auth_headers
        ).json()
        assert gone["member_name"] == listed["name"]
        [sheet] = client.get(
            f"/api/organisations/{org['id']}/timesheets", headers=auth_headers
        ).json()
        assert sheet["member_name"] == listed["name"]

    def test_a_viewer_reads_everything_and_changes_nothing(self, client, auth_headers):
        org, project, _, (inside, inside_id), (outside, outside_id) = self._org_with_team(
            client, auth_headers
        )
        viewer = _new_user()
        _member_of(client, auth_headers, org["id"], viewer, role="viewer")
        _beat(client, inside, project["id"], "2026-03-03T09:00:00", 60)
        _beat(client, outside, project["id"], "2026-03-03T11:00:00", 60)

        rows = _members_of_record(_record(client, viewer, org["id"]), project["id"])
        assert {r["user_id"] for r in rows} == {inside_id, outside_id}
        sheet_csv = client.get(
            f"/api/organisations/{org['id']}/record.csv",
            params={"month": "2026-03", "tz": "UTC"},
            headers=viewer,
        )
        assert sheet_csv.status_code == 200
        assert sheet_csv.text.splitlines()[0] == "project,member,day,start,end,hours,note"
        assert len(sheet_csv.text.splitlines()) == 3

        compliance = client.get(
            f"/api/organisations/{org['id']}/compliance.csv",
            params={"month": "2026-03", "tz": "UTC"},
            headers=viewer,
        )
        assert compliance.status_code == 200
        header, *rows_csv = compliance.text.splitlines()
        assert header == (
            "member,project,day,first_start,last_end,break_minutes,worked_hours,warnings"
        )
        assert len(rows_csv) == 2

        # Changes nothing: no deciding, no administering, no audit.
        inside_sheet = _submit(client, inside, org["id"], project["id"], "2026-03").json()
        assert (
            _decide_sheet(client, viewer, org["id"], inside_sheet["id"], approve=True).status_code
            == 403
        )
        assert (
            client.get(f"/api/organisations/{org['id']}/audit", headers=viewer).status_code == 403
        )

    def test_a_member_takes_their_visible_month_away_as_csv(self, client, auth_headers):
        """The person can always take away exactly what is seen of them —
        their own rows, nobody else's, and no reader's role needed."""
        org, project, _, (inside, _inside_id), (outside, _outside_id) = self._org_with_team(
            client, auth_headers
        )
        _beat(client, inside, project["id"], "2026-03-03T09:00:00", 60)
        _beat(client, outside, project["id"], "2026-03-03T11:00:00", 60)

        mine = client.get(
            f"/api/organisations/{org['id']}/visible.csv",
            params={"month": "2026-03", "tz": "UTC"},
            headers=inside,
        )
        assert mine.status_code == 200, mine.text
        header, *rows = mine.text.splitlines()
        assert header == "project,member,day,start,end,hours,note"
        # One row: their own entry. The other member's is in no byte of it.
        assert len(rows) == 1
        outside_email = _me(client, outside)["email"]
        assert outside_email not in mine.text
        # The record's own CSV stays a reader's: a plain member is refused.
        refused = client.get(
            f"/api/organisations/{org['id']}/record.csv",
            params={"month": "2026-03", "tz": "UTC"},
            headers=inside,
        )
        assert refused.status_code == 403

    def test_compliance_counts_breaks_between_entries(self, client, auth_headers):
        member = _new_user()
        org, project, _member_id = _employed(client, auth_headers, member, managed=False)
        _beat(client, member, project["id"], "2026-03-03T09:00:00", 60)  # 09:00–10:00
        _beat(client, member, project["id"], "2026-03-03T10:30:00", 60)  # 10:30–11:30
        csv_text = client.get(
            f"/api/organisations/{org['id']}/compliance.csv",
            params={"month": "2026-03", "tz": "UTC"},
            headers=auth_headers,
        ).text
        [row] = csv_text.splitlines()[1:]
        # Two lawful hours: the breaks and total, and no warning raised.
        assert row.endswith(",30,2.00,")

    def test_compliance_warns_on_long_days_and_short_rests(self, client, auth_headers):
        """#350: the warnings are derived from the same rows on every read —
        an 11-hour day, then a start 8 hours after it ends."""
        member = _new_user()
        org, project, _member_id = _employed(client, auth_headers, member, managed=False)
        _beat(client, member, project["id"], "2026-03-03T08:00:00", 660)  # 08:00–19:00
        _beat(client, member, project["id"], "2026-03-04T03:00:00", 120)  # 8 h after
        csv_text = client.get(
            f"/api/organisations/{org['id']}/compliance.csv",
            params={"month": "2026-03", "tz": "UTC"},
            headers=auth_headers,
        ).text
        day_one, day_two = csv_text.splitlines()[1:]
        assert day_one.endswith(",day over 10 h (11.00 h)")
        assert day_two.endswith(",rest under 11 h (8.00 h after 2026-03-03)")

    def test_the_audit_log_reads_newest_first_for_admins(self, client, auth_headers):
        member = _new_user()
        org, _project, _member_id = _employed(client, auth_headers, member)
        events = client.get(f"/api/organisations/{org['id']}/audit", headers=auth_headers)
        assert events.status_code == 200
        names = [e["event"] for e in events.json()]
        assert names[0] == "contract.managed"
        assert "organisation.created" in names
        assert (
            client.get(f"/api/organisations/{org['id']}/audit", headers=member).status_code == 403
        )


class TestAdminEnteredTime:
    def test_an_entered_session_is_marked_and_on_the_members_timeline(self, client, auth_headers):
        member = _new_user()
        org, project, member_id = _employed(client, auth_headers, member)
        entered = client.post(
            f"/api/organisations/{org['id']}/projects/{project['id']}/members/{member_id}/entries",
            json={
                "start": "2026-03-03T09:00:00Z",
                "end": "2026-03-03T11:00:00Z",
                "note": "trade fair, logged for you",
            },
            headers=auth_headers,
        )
        assert entered.status_code == 201, entered.text
        beat = entered.json()
        assert beat["entered_by"] == _seeded_id(auth_headers)
        assert beat["organisation_id"] == org["id"]
        # On the member's own timeline, marked.
        [mine] = client.get(f"/api/beats/?project_id={project['id']}", headers=member).json()
        assert mine["entered_by"] == _seeded_id(auth_headers)
        assert mine["note"] == "trade fair, logged for you"
        # In the record, and in the audit log.
        [row] = _members_of_record(_record(client, auth_headers, org["id"]), project["id"])
        assert row["hours"] == 2.0
        names = [
            e["event"]
            for e in client.get(
                f"/api/organisations/{org['id']}/audit", headers=auth_headers
            ).json()
        ]
        assert "time.entered" in names

    def test_backwards_time_is_refused(self, client, auth_headers):
        member = _new_user()
        org, project, member_id = _employed(client, auth_headers, member)
        resp = client.post(
            f"/api/organisations/{org['id']}/projects/{project['id']}/members/{member_id}/entries",
            json={"start": "2026-03-03T11:00:00Z", "end": "2026-03-03T09:00:00Z"},
            headers=auth_headers,
        )
        assert resp.status_code == 400
