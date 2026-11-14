"""Helpers the organisation suites share — no tests of their own.

`test_organisations.py` grew past the size ceiling (CLAUDE.md § Conventions) and
split on the stage seam; both halves mint people, organisations, projects
and assignments the same way. Not `test_`-prefixed, so pytest does not
collect it.
"""

import os
from datetime import UTC, datetime, timedelta

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


def _beat_resp(client, headers, project_id: str, start: str, minutes: int):
    """As `_beat`, returning the response: for a write expected to be refused."""
    begun = datetime.fromisoformat(start).replace(tzinfo=UTC)
    return client.post(
        "/api/beats/",
        json={
            "project_id": project_id,
            "start": begun.isoformat(),
            "end": (begun + timedelta(minutes=minutes)).isoformat(),
        },
        headers=headers,
    )


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
