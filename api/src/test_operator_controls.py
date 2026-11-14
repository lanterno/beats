"""The operator's platform controls (docs/backoffice.md § Controls) and the
erasure request log (§ The pages, Privacy and compliance): the shape a pause
and a limit must have, the audit row each writes, what the Access page reads
back, and a request's state read off the job queue. Split from
test_operator_commands.py at the size ceiling (CLAUDE.md § Conventions); the
`operator_client` fixture is conftest.py's.
"""

from datetime import UTC, datetime, timedelta
from typing import ClassVar

import pytest
from bson import ObjectId

from conftest import OPERATOR_ORIGIN as ORIGIN
from conftest import OPERATOR_SUB


class TestControlCommands:
    """`control.set` and `control.clear` (docs/backoffice.md § Controls):
    the shape a pause and a limit must have, the audit row each writes, and
    what the Access page reads back."""

    OWN: ClassVar[dict[str, str]] = {"Origin": ORIGIN}

    @pytest.fixture(autouse=True)
    def _clean(self, mongo):
        yield
        mongo.platform_controls.delete_many({})
        mongo.operator_audit.delete_many({})

    def _run(self, operator_client, name, args):
        return operator_client.post(
            f"/api/operator/commands/{name}", json={"args": args}, headers=self.OWN
        )

    def test_a_pause_is_written_with_its_end_and_audited(self, operator_client, mongo):
        until = (datetime.now(UTC) + timedelta(hours=2)).isoformat()
        done = self._run(
            operator_client,
            "control.set",
            {"name": "coach", "until": until, "reason": "cost spike"},
        )
        assert done.status_code == 200, done.text
        entry = done.json()
        assert entry["subject_kind"] == "control"
        assert entry["subject_id"] == "coach"
        assert entry["before"] == {"set": False}
        assert entry["after"]["in_force"] is True
        assert entry["after"]["set_by"] == OPERATOR_SUB
        stored = mongo.platform_controls.find_one({"name": "coach"})
        assert stored["reason"] == "cost spike"
        assert "user_id" not in stored

        controls = operator_client.get("/api/operator/controls").json()
        assert [(c["name"], c["in_force"], c["reason"]) for c in controls] == [
            ("coach", True, "cost spike")
        ]

        cleared = self._run(operator_client, "control.clear", {"name": "coach"})
        assert cleared.status_code == 200
        assert cleared.json()["after"] == {"set": False}
        assert mongo.platform_controls.count_documents({}) == 0

    def test_a_pause_needs_an_end_inside_the_cap_and_a_reason(self, operator_client):
        from beats.platform_controls import MAX_PAUSE

        soon = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
        for args in (
            {"name": "imports", "reason": "r"},
            {"name": "imports", "until": soon},
            {
                "name": "imports",
                "until": (datetime.now(UTC) - timedelta(minutes=1)).isoformat(),
                "reason": "r",
            },
            {
                "name": "imports",
                "until": (datetime.now(UTC) + MAX_PAUSE + timedelta(hours=1)).isoformat(),
                "reason": "r",
            },
            {"name": "imports", "until": soon, "reason": "r", "value": 3},
        ):
            refused = self._run(operator_client, "control.set", args)
            assert refused.status_code == 422, (args, refused.text)
            assert refused.json()["code"] == "INVALID_COMMAND_ARGS"

    def test_a_limit_takes_a_value_and_nothing_else(self, operator_client, mongo):
        ok = self._run(operator_client, "control.set", {"name": "imports_per_hour", "value": 10})
        assert ok.status_code == 200, ok.text
        assert ok.json()["after"]["value"] == 10
        soon = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
        for args in (
            {"name": "imports_per_hour"},
            {"name": "imports_per_hour", "value": 10, "until": soon},
            {"name": "imports_per_hour", "value": 0},
        ):
            assert self._run(operator_client, "control.set", args).status_code == 422, args

    def test_a_network_is_slowed_never_blocked_and_only_until_midnight(self, operator_client):
        soon = (datetime.now(UTC) + timedelta(minutes=10)).isoformat()
        key = "0123456789abcdef0123456789abcdef"
        ok = self._run(
            operator_client,
            "control.set",
            {"name": "signups", "until": soon, "reason": "a wave", "value": 5, "network": key},
        )
        assert ok.status_code == 200, ok.text
        assert ok.json()["after"]["network"] == key
        tomorrow_noon = (datetime.now(UTC) + timedelta(days=1)).replace(hour=12).isoformat()
        for args in (
            {"name": "signups", "until": soon, "reason": "r", "network": key},
            {"name": "coach", "until": soon, "reason": "r", "network": key, "value": 5},
            {"name": "signups", "until": tomorrow_noon, "reason": "r", "value": 5, "network": key},
        ):
            assert self._run(operator_client, "control.set", args).status_code == 422, args

    def test_slowed_signups_carry_a_ceiling(self, operator_client):
        soon = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
        done = self._run(
            operator_client,
            "control.set",
            {"name": "signups", "until": soon, "reason": "a wave", "value": 20},
        )
        assert done.status_code == 200, done.text
        assert done.json()["after"]["value"] == 20

    def test_a_pause_in_force_is_a_queue_row_and_an_attention_count(self, operator_client, mongo):
        until = (datetime.now(UTC) + timedelta(hours=2)).isoformat()
        self._run(
            operator_client, "control.set", {"name": "webhooks", "until": until, "reason": "r"}
        )
        assert operator_client.get("/api/operator/attention").json()["controls_paused"] == 1
        rows = operator_client.get("/api/operator/queue").json()
        assert [(r["kind"], r["subject_id"]) for r in rows] == [("control_paused", "webhooks")]
        assert rows[0]["due"].startswith(until[:16])

    def test_access_lists_the_allowlist_and_nothing_else(self, operator_client):
        access = operator_client.get("/api/operator/access").json()
        assert {(a["email"], a["role"]) for a in access} == {
            ("op@example.test", "operator"),
            ("viewer@example.test", "viewer"),
        }
        assert all(set(a) == {"email", "role"} for a in access)


class TestErasureRequestLog:
    """The erasure request log (docs/backoffice.md § The pages, Compliance):
    a mail gets a date, the deadline is visible, the state is read off the
    job queue, and no address is ever in a row."""

    OWN: ClassVar[dict[str, str]] = {"Origin": ORIGIN}

    @pytest.fixture(autouse=True)
    def _clean(self, mongo):
        yield
        for name in ("erasure_requests", "operator_audit", "operator_jobs", "users"):
            mongo[name].delete_many({})

    def _run(self, operator_client, name, args):
        return operator_client.post(
            f"/api/operator/commands/{name}", json={"args": args}, headers=self.OWN
        )

    def _log(self, operator_client, days_ago: int, user_id=None, reference="mail-1"):
        received = (datetime.now(UTC) - timedelta(days=days_ago)).date().isoformat()
        done = self._run(
            operator_client,
            "erasure_request.log",
            {"reference": reference, "received_on": received, "user_id": user_id},
        )
        assert done.status_code == 200, done.text
        return done.json()["after"]["request_id"]

    def test_a_request_is_logged_dated_and_overdue_after_the_named_days(
        self, operator_client, mongo
    ):
        from beats.operator.reads import ERASURE_REQUEST_ATTENTION_DAYS

        fresh = self._log(operator_client, 1, reference="fresh")
        old = self._log(operator_client, ERASURE_REQUEST_ATTENTION_DAYS, reference="old")

        rows = operator_client.get("/api/operator/erasure-requests").json()
        assert {(r["id"], r["status"]) for r in rows} == {(fresh, "open"), (old, "open")}
        assert (
            operator_client.get("/api/operator/attention").json()["erasure_requests_overdue"] == 1
        )
        queue = operator_client.get("/api/operator/queue").json()
        kinds = [(r["kind"], r["subject_id"]) for r in queue]
        assert ("erasure_request_open", fresh) in kinds
        assert ("erasure_request_open", old) in kinds

    def test_a_reference_is_never_an_address(self, operator_client):
        refused = self._run(
            operator_client,
            "erasure_request.log",
            {"reference": "ana@example.test", "received_on": "2026-11-01"},
        )
        assert refused.status_code == 422
        assert refused.json()["code"] == "INVALID_COMMAND_ARGS"

    def test_the_state_is_read_off_the_job_queue(self, operator_client, mongo):
        user_id = str(ObjectId())
        mongo.users.insert_one({"_id": ObjectId(user_id), "email": "er@example.test"})
        request = self._log(operator_client, 3, user_id=user_id)

        queued = self._run(operator_client, "account.erase", {"user_id": user_id})
        assert queued.status_code == 409, "the email must be typed"
        queued = operator_client.post(
            "/api/operator/commands/account.erase",
            json={"args": {"user_id": user_id}, "confirmation": "er@example.test"},
            headers=self.OWN,
        )
        assert queued.status_code == 200, queued.text
        rows = operator_client.get("/api/operator/erasure-requests").json()
        assert rows[0]["status"] == "erasure_queued"
        assert (
            operator_client.get("/api/operator/attention").json()["erasure_requests_overdue"] == 0
        )
        assert "erasure_request_open" not in {
            r["kind"] for r in operator_client.get("/api/operator/queue").json()
        }

        mongo.operator_jobs.update_many({"subject_id": user_id}, {"$set": {"state": "done"}})
        assert (
            operator_client.get("/api/operator/erasure-requests").json()[0]["status"]
            == "erasure_ran"
        )

        closed = self._run(
            operator_client, "erasure_request.close", {"request_id": request, "reason": "erased"}
        )
        assert closed.status_code == 200, closed.text
        assert closed.json()["after"]["closed"] is True
        row = operator_client.get("/api/operator/erasure-requests").json()[0]
        assert row["status"] == "closed"
        stored = mongo.erasure_requests.find_one({"_id": ObjectId(request)})
        assert stored["expires_at"] is not None, "a closed request has a retention date"
        assert "user_id" not in stored
        assert "er@example.test" not in str(stored)

        again = self._run(
            operator_client, "erasure_request.close", {"request_id": request, "reason": "erased"}
        )
        assert again.status_code == 404
        assert again.json()["code"] == "ERASURE_REQUEST_NOT_FOUND"

    def test_a_request_naming_an_unknown_account_is_refused(self, operator_client):
        refused = self._run(
            operator_client,
            "erasure_request.log",
            {"reference": "r", "received_on": "2026-11-01", "user_id": str(ObjectId())},
        )
        assert refused.status_code == 404
