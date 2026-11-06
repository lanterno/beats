"""Organisations (docs/organisations.md, stage 2) — the HTTP contract
under /api/organisations, what an organisation's project is on a
member's own routes, and the wall: what the organisation's read
reaches and, more to the point, what it cannot.

Same harness as test_api.py (conftest.py): a TestClient over real Mongo
and one test user per class (`auth_headers`); every other person in a test
is minted by `_new_user`, since an organisation is about more than one.
Split at the ceiling in roadmaps/file-sizes.md; the shared fixtures are
`organisation_helpers.py`'s.
"""

from datetime import UTC, datetime, timedelta

from bson import ObjectId

from organisation_helpers import (
    FULL_TIME,
    MONTH,
    _assign,
    _beat,
    _create_org,
    _db,
    _invite,
    _join,
    _me,
    _member_of,
    _members_of_record,
    _new_user,
    _org_project,
    _projects,
    _record,
    _seeded_id,
    _visible,
)


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
