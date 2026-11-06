"""Employment (docs/organisations.md, stages 3 and 4): managed
contracts, absence requests, timesheets with the frozen month and its
lock, teams and manager scope, and admin-entered time.

Same harness as test_api.py (conftest.py): a TestClient over real Mongo
and one test user per class (`auth_headers`); every other person in a test
is minted by `_new_user`, since an organisation is about more than one.
Split at the ceiling in roadmaps/file-sizes.md; the shared fixtures are
`organisation_helpers.py`'s.
"""

import json
from datetime import date

from bson import ObjectId

from organisation_helpers import (
    FULL_TIME,
    _assign,
    _beat,
    _beat_resp,
    _create_org,
    _decide_sheet,
    _employed,
    _me,
    _member_of,
    _members_of_record,
    _new_user,
    _org_project,
    _projects,
    _record,
    _seeded_id,
    _submit,
)


class TestManagedContracts:
    """Stage 3: the contract belongs to the employer (decision in
    docs/organisations.md). Taking one under management starts from the terms
    the member recorded; from then on the member reads their week and balance
    as ever and writes none of the contract's inputs."""

    def test_the_employers_write_keeps_the_members_own_rules(self, client, auth_headers):
        """Decision 21: one set of rules validates a contract whoever
        writes it. The employer's write skipped two of them (#412) — the
        day-job check, so it could put a contract on a freelance project,
        and the adjustment reconcile, so it could move the first day past
        one of the member's balance adjustments."""
        member = _new_user()
        org, project, member_id = _employed(client, auth_headers, member)
        url = f"/api/organisations/{org['id']}/projects/{{pid}}/members/{member_id}/contract"

        freelance = _org_project(client, auth_headers, org["id"], name="Gig", kind="freelance")
        _assign(client, auth_headers, org["id"], freelance["id"], member_id)
        refused = client.put(
            url.format(pid=freelance["id"]),
            json={"contract": {"terms": FULL_TIME}, "managed": True},
            headers=auth_headers,
        )
        assert refused.status_code == 409, refused.text
        assert refused.json()["code"] == "NOT_A_DAY_JOB"

        # A payout the employer entered, and then a first day moved past it.
        paid = client.post(
            f"/api/organisations/{org['id']}/projects/{project['id']}"
            f"/members/{member_id}/adjustments",
            json={"date": "2026-01-20", "kind": "delta", "hours": -4},
            headers=auth_headers,
        )
        assert paid.status_code == 201, paid.text
        later = client.put(
            url.format(pid=project["id"]),
            json={
                "contract": {
                    "terms": [{**FULL_TIME[0], "effective_from": "2026-02-02"}],
                    "opening_balance_hours": 2,
                },
                "managed": True,
            },
            headers=auth_headers,
        )
        assert later.status_code == 409, later.text
        assert later.json()["code"] == "ADJUSTMENT_BEFORE_START"

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

    def test_a_contract_write_marks_the_approvals_it_moves_and_never_refuses(
        self, client, auth_headers
    ):
        """Decision 23, the half decided on 2026-10-31: a contract write is
        not dated inside a month, so the lock has nothing to catch and it is
        not refused. The approved months whose figures it moves are marked
        instead — still approved, still locked, `frozen` still the record,
        and a `terms_changed` step in the history — from the day the two
        contracts diverge, so a term added for next year marks nothing."""
        member = _new_user()
        org, project, member_id = _employed(client, auth_headers, member)
        _beat(client, member, project["id"], "2026-03-03T09:00:00", 60)
        sheet = _submit(client, member, org["id"], project["id"], "2026-03").json()
        approved = _decide_sheet(client, auth_headers, org["id"], sheet["id"], approve=True)
        assert approved.status_code == 200, approved.text
        assert approved.json()["superseded_at"] is None
        frozen = approved.json()["frozen"]
        url = (
            f"/api/organisations/{org['id']}/projects/{project['id']}/members/{member_id}/contract"
        )

        def listed() -> dict:
            [one] = client.get(
                f"/api/organisations/{org['id']}/timesheets", headers=auth_headers
            ).json()
            return one

        # A term for next year: taken, and March is untouched.
        future = client.put(
            url,
            json={
                "contract": {
                    "terms": [
                        *FULL_TIME,
                        {**FULL_TIME[0], "effective_from": "2027-01-04", "full_time_hours": 32},
                    ],
                    "opening_balance_hours": 2,
                },
                "managed": True,
            },
            headers=auth_headers,
        )
        assert future.status_code == 200, future.text
        assert listed()["superseded_at"] is None

        # A term changed from February: taken too — never refused — and March
        # is marked, with the frozen figures exactly as they were.
        moved = client.put(
            url,
            json={
                "contract": {
                    "terms": [
                        {**FULL_TIME[0], "effective_from": "2026-02-02", "full_time_hours": 32}
                    ],
                    "opening_balance_hours": 2,
                },
                "managed": True,
            },
            headers=auth_headers,
        )
        assert moved.status_code == 200, moved.text
        marked = listed()
        assert marked["status"] == "approved"
        assert marked["frozen"] == frozen
        assert marked["superseded_at"] is not None
        assert marked["superseded_by"] == _seeded_id(auth_headers)
        assert [h["action"] for h in marked["history"]] == [
            "submitted",
            "approved",
            "terms_changed",
        ]
        # Still locked: the mark is not an unlock.
        refused = _beat_resp(client, member, project["id"], "2026-03-10T09:00:00", 60)
        assert refused.status_code == 409, refused.text
        assert refused.json()["code"] == "PERIOD_APPROVED"
        # And the act is in the audit log with its count.
        [event] = [
            e
            for e in client.get(
                f"/api/organisations/{org['id']}/audit", headers=auth_headers
            ).json()
            if e["event"] == "contract.managed" and e["details"].get("superseded_timesheets")
        ]
        assert event["details"]["superseded_timesheets"] == 1

        # A reopen is the recorded way back: the mark goes with the freeze,
        # and the re-approval freezes against the terms now in force.
        reopened = client.post(
            f"/api/organisations/{org['id']}/timesheets/{sheet['id']}/reopen",
            json={"reason": "the February term was wrong"},
            headers=auth_headers,
        )
        assert reopened.status_code == 200, reopened.text
        assert reopened.json()["superseded_at"] is None
        again = _submit(client, member, org["id"], project["id"], "2026-03").json()
        refrozen = _decide_sheet(client, auth_headers, org["id"], again["id"], approve=True).json()
        assert refrozen["superseded_at"] is None
        assert refrozen["frozen"]["expected"] != frozen["expected"]

    def test_the_members_own_contract_write_marks_the_employers_approval(
        self, client, auth_headers
    ):
        """The member's write on an unmanaged assignment goes through the
        same rule — that is the point: it turns a silent divergence into a
        visible one, and the mark names the member."""
        member = _new_user()
        org, project, member_id = _employed(client, auth_headers, member, managed=False)
        assert (
            client.put(
                f"/api/projects/{project['id']}/contract",
                json={"terms": FULL_TIME, "opening_balance_hours": 2},
                headers=member,
            ).status_code
            == 200
        )
        _beat(client, member, project["id"], "2026-03-03T09:00:00", 60)
        sheet = _submit(client, member, org["id"], project["id"], "2026-03").json()
        assert (
            _decide_sheet(client, auth_headers, org["id"], sheet["id"], approve=True).status_code
            == 200
        )

        changed = client.put(
            f"/api/projects/{project['id']}/contract",
            json={"terms": FULL_TIME, "opening_balance_hours": 10},
            headers=member,
        )
        assert changed.status_code == 200, changed.text
        [one] = client.get(f"/api/organisations/{org['id']}/timesheets", headers=member).json()
        assert one["status"] == "approved"
        assert one["superseded_by"] == member_id
        assert one["history"][-1]["action"] == "terms_changed"

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
        # And the answered complaint goes with the answer (#413): `_dump`
        # excludes None, so the sheet used to read as submitted and still
        # carry the decider, the instant and the comment it was answering.
        assert again.json()["comment"] is None
        assert again.json()["decided_by"] is None
        assert again.json()["decided_at"] is None
        [listed] = client.get(f"/api/organisations/{org['id']}/timesheets", headers=member).json()
        assert (listed["comment"], listed["decided_by"]) == (None, None)
        # The history is the record of what happened and keeps both steps.
        assert [h["action"] for h in listed["history"]] == [
            "submitted",
            "changes_requested",
            "submitted",
        ]

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

    def test_leaving_takes_the_person_out_of_every_team(self, client, auth_headers):
        """#411: `remove_from_teams` existed and nothing called it, so a
        person who rejoined was silently back in their old team — and a
        former manager re-invited as one got their old scope back with
        nobody assigning it."""
        org, _project, _mgr, (inside, inside_id), _out = self._org_with_team(client, auth_headers)
        teams_url = f"/api/organisations/{org['id']}/teams"
        [team] = client.get(teams_url, headers=auth_headers).json()
        assert inside_id in team["member_ids"]

        assert client.post(f"/api/organisations/{org['id']}/leave", headers=inside).status_code

        [team] = client.get(teams_url, headers=auth_headers).json()
        assert inside_id not in team["member_ids"]
        # Rejoining is a fresh start: the scope is an admin's to give again.
        _member_of(client, auth_headers, org["id"], inside)
        [team] = client.get(teams_url, headers=auth_headers).json()
        assert inside_id not in team["member_ids"]

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
