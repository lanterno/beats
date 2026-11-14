"""Closing and deleting an organisation (#347), the retention purge, and
the project index the list reads through.

Same harness as test_api.py (conftest.py): a TestClient over real Mongo
and one test user per class (`auth_headers`); every other person in a test
is minted by `_new_user`, since an organisation is about more than one.
Split at the size ceiling (CLAUDE.md § Conventions); the shared fixtures are
`organisation_helpers.py`'s.
"""

import asyncio
import os
from datetime import UTC, date, datetime, timedelta

import pytest
from bson import ObjectId

from organisation_helpers import (
    FULL_TIME,
    _assign,
    _beat,
    _create_org,
    _db,
    _employed,
    _member_of,
    _members_of_record,
    _new_user,
    _org_project,
    _projects,
    _record,
    _seeded_id,
)


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

    def test_a_crash_before_the_wipe_leaves_one_copy_on_the_re_run(
        self, client, auth_headers, monkeypatch
    ):
        """Decision 29 runs the hand-backs before the wipe so a crash
        midway strands nothing. Nothing was stranded — but the rows handed
        back belonged to the new copies, so `row_owner_ids` no longer found
        them and every contract holder was found again through their
        assignment and given a second copy, holding the contract and no
        rows (#414)."""
        from beats.infrastructure.organisations import MongoOrganisationStore

        org = _create_org(client, auth_headers)
        member = _new_user()
        member_id = _member_of(client, auth_headers, org["id"], member)
        project = _org_project(client, auth_headers, org["id"], kind="day_job")
        _assign(client, auth_headers, org["id"], project["id"], member_id)
        client.put(
            f"/api/projects/{project['id']}/contract", json={"terms": FULL_TIME}, headers=member
        )
        _beat(client, member, project["id"], "2026-03-03T09:00:00", 60)
        assert (
            client.post(
                f"/api/organisations/{org['id']}/close", json={}, headers=auth_headers
            ).status_code
            == 200
        )
        _db().organisations.update_one(
            {"_id": ObjectId(org["id"])},
            {"$set": {"closes_on": (datetime.now(UTC).date() - timedelta(days=1)).isoformat()}},
        )

        async def crash(self, organisation_id, project_ids):
            raise RuntimeError("the wipe never ran")

        monkeypatch.setattr(MongoOrganisationStore, "delete_organisation_rows", crash)
        with pytest.raises(RuntimeError):
            client.delete(f"/api/organisations/{org['id']}", headers=auth_headers)
        monkeypatch.undo()

        gone = client.delete(f"/api/organisations/{org['id']}", headers=auth_headers)
        assert gone.status_code == 204, gone.text
        [mine] = _projects(client, member)
        assert mine["contract"] is not None
        assert len(client.get(f"/api/beats/?project_id={mine['id']}", headers=member).json()) == 1

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

    def test_a_spent_tombstone_goes_and_an_owed_one_stays(self, client, auth_headers):
        """#408: erasure keeps a former member's name, address and contract
        under a tombstone so the record still groups their rows. The purge
        took the rows and left those behind for ever — the most personal
        data in the organisation, kept for a record that no longer exists.
        A tombstone with a row still inside the period keeps everything."""
        org = _create_org(client, auth_headers)
        project = _org_project(client, auth_headers, org["id"])
        db = _db()

        def _stone(name: str, day: str) -> str:
            """One erased member, their membership, assignment and one beat."""
            stone = f"erased:{name}"
            db.org_members.insert_one(
                {
                    "organisation_id": org["id"],
                    "user_id": stone,
                    "role": "member",
                    "name": "A Person",
                    "email": "person@example.com",
                    "left_reason": "erased",
                }
            )
            db.org_assignments.insert_one(
                {
                    "organisation_id": org["id"],
                    "project_id": project["id"],
                    "user_id": stone,
                    "shared_from": "2019-01-01T00:00:00+00:00",
                    "contract": {"terms": FULL_TIME},
                }
            )
            db.timeLogs.insert_one(
                {
                    "user_id": stone,
                    "project_id": project["id"],
                    "organisation_id": org["id"],
                    "start": datetime.fromisoformat(f"{day}T09:00:00").replace(tzinfo=UTC),
                    "end": datetime.fromisoformat(f"{day}T10:00:00").replace(tzinfo=UTC),
                    "tags": [],
                }
            )
            return stone

        spent = _stone("spent", "2020-01-10")
        owed = _stone("owed", "2026-03-03")

        counted = self._counts(self._purge(), org["id"])
        assert counted.counts["tombstones_deleted"] == 1, "a dry run counts what an apply takes"

        self._purge(apply=True)
        assert db.org_members.count_documents({"user_id": spent}) == 0
        assert db.org_assignments.count_documents({"user_id": spent}) == 0
        # The one still owed keeps its name, its address and its contract.
        assert db.org_members.count_documents({"user_id": owed}) == 1
        assert db.org_assignments.find_one({"user_id": owed})["contract"] is not None

    def test_a_decided_absence_request_expires_with_the_record(self, client, auth_headers):
        """Decision 30 does not list them; they expire on the same cutoff as
        the absence they asked for, which is the record itself."""
        org = _create_org(client, auth_headers)
        project = _org_project(client, auth_headers, org["id"])
        db = _db()
        for date_, decided in (("2020-01-10", True), ("2026-03-03", True), ("2020-02-10", False)):
            db.org_absence_requests.insert_one(
                {
                    "organisation_id": org["id"],
                    "project_id": project["id"],
                    "user_id": "someone",
                    "date": date_,
                    "type": "vacation",
                    "status": "approved" if decided else "pending",
                    "decided_at": "2020-01-11T00:00:00+00:00" if decided else None,
                }
            )

        self._purge(apply=True)
        left = sorted(
            r["date"] for r in db.org_absence_requests.find({"organisation_id": org["id"]})
        )
        # The old decided one goes; the young one and the one still waiting stay.
        assert left == ["2020-02-10", "2026-03-03"]

    def test_a_purge_does_not_take_the_balance_with_the_stamps(self, client, auth_headers):
        """A bug that happened (#409): the purge unstamps a living member's
        old rows, and `has_unshared` asked only whether an unstamped row
        existed — so after the first purge every long-standing member read
        as having unshared history, and the organisation lost the balance
        on its own record for good."""
        member = _new_user()
        org, project, _member_id = _employed(client, auth_headers, member, managed=False)
        contract = client.put(
            f"/api/projects/{project['id']}/contract",
            json={"terms": FULL_TIME, "opening_balance_hours": 2},
            headers=member,
        )
        assert contract.status_code == 200, contract.text
        _beat(client, member, project["id"], "2020-02-10T09:00:00", 60)  # past the cutoff
        _beat(client, member, project["id"], "2026-03-03T09:00:00", 60)

        [before] = _members_of_record(_record(client, auth_headers, org["id"]), project["id"])
        assert before["balance"] is not None

        self._purge(apply=True)
        db = _db()
        assert db.timeLogs.count_documents({"organisation_id": org["id"]}) == 1

        [after] = _members_of_record(_record(client, auth_headers, org["id"]), project["id"])
        assert after["balance"] is not None, "an expired row is not one the member kept back"

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
