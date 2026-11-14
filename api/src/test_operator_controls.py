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

    @staticmethod
    def _before_midnight() -> datetime:
        """An end before the key's midnight however near it is: ten minutes
        on, a network's slow-down would be refused between 23:50 and
        midnight UTC. Whole seconds, as a stored date keeps them."""
        now = datetime.now(UTC)
        midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        return (now + min(timedelta(minutes=10), (midnight - now) / 2)).replace(microsecond=0)

    def test_a_network_is_slowed_never_blocked_and_only_until_midnight(
        self, operator_client, mongo
    ):
        soon = self._before_midnight().isoformat()
        key = "0123456789abcdef0123456789abcdef"
        ok = self._run(
            operator_client,
            "control.set",
            {"name": "signups", "until": soon, "reason": "a wave", "value": 5, "network": key},
        )
        assert ok.status_code == 200, ok.text
        # The audit is kept four years: it says one network, never which.
        assert ok.json()["after"]["one_network"] is True
        assert key not in str(mongo.operator_audit.find_one({"command": "control.set"}))
        tomorrow_noon = (datetime.now(UTC) + timedelta(days=1)).replace(hour=12).isoformat()
        for args in (
            {"name": "signups", "until": soon, "reason": "r", "network": key},
            {"name": "coach", "until": soon, "reason": "r", "network": key, "value": 5},
            {"name": "signups", "until": tomorrow_noon, "reason": "r", "value": 5, "network": key},
        ):
            assert self._run(operator_client, "control.set", args).status_code == 422, args

    def test_the_control_for_everyone_and_each_networks_stand_side_by_side(
        self, operator_client, mongo
    ):
        """Slowing a network neither replaces the control for everyone nor
        releases another network, and lifting one leaves the rest — with
        the audit saying which kind was lifted and never which network."""
        until = self._before_midnight()
        a, b = "a" * 32, "b" * 32
        for args in (
            {"name": "signups", "until": until.isoformat(), "reason": "everyone"},
            {
                "name": "signups",
                "until": until.isoformat(),
                "reason": "a",
                "value": 5,
                "network": a,
            },
            {
                "name": "signups",
                "until": until.isoformat(),
                "reason": "b",
                "value": 3,
                "network": b,
            },
        ):
            done = self._run(operator_client, "control.set", args)
            assert done.status_code == 200, (args, done.text)
        stored = {d.get("network"): d for d in mongo.platform_controls.find({"name": "signups"})}
        assert set(stored) == {None, a, b}
        assert stored[None]["value"] is None, "the pause for everyone still stands"
        assert (stored[a]["value"], stored[b]["value"]) == (5, 3)
        # A network's key goes with its control: the TTL index reads this.
        assert stored[a]["expires_at"].replace(tzinfo=UTC) == until
        assert stored[None].get("expires_at") is None, "the one for everyone stays until cleared"

        lifted = self._run(operator_client, "control.clear", {"name": "signups", "network": a})
        assert lifted.status_code == 200, lifted.text
        assert lifted.json()["before"]["one_network"] is True
        assert lifted.json()["after"] == {"set": False, "one_network": True}
        assert {d.get("network") for d in mongo.platform_controls.find({})} == {None, b}

        lifted = self._run(operator_client, "control.clear", {"name": "signups"})
        assert lifted.status_code == 200, lifted.text
        assert lifted.json()["before"]["one_network"] is False
        assert lifted.json()["after"] == {"set": False}
        assert {d.get("network") for d in mongo.platform_controls.find({})} == {b}

        for entry in mongo.operator_audit.find({}):
            assert a not in str(entry), "a network's key is in no audit row"
            assert b not in str(entry), "a network's key is in no audit row"

    def test_the_access_page_reads_each_sign_up_control_with_its_network(self, operator_client):
        """What the page needs to show each and lift each: the network's key
        on its own row, none on the one for everyone, that one first."""
        until = self._before_midnight().isoformat()
        key = "d" * 32
        for args in (
            {"name": "signups", "until": until, "reason": "a wave", "value": 5, "network": key},
            {"name": "signups", "until": until, "reason": "everyone"},
        ):
            assert self._run(operator_client, "control.set", args).status_code == 200
        controls = operator_client.get("/api/operator/controls").json()
        assert [(c["name"], c["network"], c["value"], c["in_force"]) for c in controls] == [
            ("signups", None, None, True),
            ("signups", key, 5, True),
        ]

    def test_only_signups_are_slowed_for_one_network(self, operator_client):
        refused = self._run(
            operator_client, "control.clear", {"name": "coach", "network": "c" * 32}
        )
        assert refused.status_code == 422, refused.text
        assert refused.json()["code"] == "INVALID_COMMAND_ARGS"

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

    def test_the_queue_tells_a_pause_from_a_slow_down_and_everyone_from_a_network(
        self, operator_client
    ):
        until = self._before_midnight().isoformat()
        for args in (
            {"name": "coach", "until": until, "reason": "r"},
            {"name": "signups", "until": until, "reason": "r", "value": 20},
            {"name": "signups", "until": until, "reason": "r", "value": 5, "network": "e" * 32},
            {"name": "signups", "until": until, "reason": "r", "value": 5, "network": "f" * 32},
        ):
            assert self._run(operator_client, "control.set", args).status_code == 200, args
        rows = operator_client.get("/api/operator/queue").json()
        assert sorted((r["kind"], r["subject_id"], r["count"]) for r in rows) == [
            ("control_paused", "coach", 1),
            ("control_slowed", "signups", 1),
            ("control_slowed_network", "signups", 2),
        ]
        assert "e" * 32 not in str(rows), "the queue names no network"
        assert operator_client.get("/api/operator/attention").json()["controls_paused"] == 4

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

        fresh = self._log(operator_client, 1, reference="T-1")
        old = self._log(operator_client, ERASURE_REQUEST_ATTENTION_DAYS, reference="T-2")

        rows = operator_client.get("/api/operator/erasure-requests").json()
        assert {(r["id"], r["status"]) for r in rows} == {(fresh, "open"), (old, "open")}
        assert (
            operator_client.get("/api/operator/attention").json()["erasure_requests_overdue"] == 1
        )
        queue = operator_client.get("/api/operator/queue").json()
        kinds = [(r["kind"], r["subject_id"]) for r in queue]
        assert ("erasure_request_open", fresh) in kinds
        assert ("erasure_request_open", old) in kinds

    def test_the_audit_names_an_id_never_the_reference(self, operator_client, mongo):
        """operator_audit is kept four years and holds its subject as an id:
        the account's when the request names one, else the request's own. The
        reference the operator typed is in no audit row."""
        user_id = str(ObjectId())
        mongo.users.insert_one({"_id": ObjectId(user_id), "email": "named@example.test"})
        self._log(operator_client, 1, user_id=user_id, reference="T-4417")
        alone = self._log(operator_client, 1, reference="T-4418")

        audit = list(mongo.operator_audit.find({"command": "erasure_request.log"}))
        assert sorted(row["subject_id"] for row in audit) == sorted([user_id, alone])
        assert "T-441" not in str(audit)
        assert mongo.erasure_requests.find_one({"_id": ObjectId(alone)})["reference"] == "T-4418"

    def test_a_reference_is_a_ticket_or_a_date_never_a_name(self, operator_client, mongo):
        """The reference is kept a year after the request closes, so it is
        a ticket number or the mail's date and nothing a person is called."""
        for typed in ("Jane Doe mail", "JaneDoe", "jane.doe.2026", "ana@example.test"):
            refused = self._run(
                operator_client,
                "erasure_request.log",
                {"reference": typed, "received_on": "2026-11-01"},
            )
            assert refused.status_code == 422, typed
            assert refused.json()["code"] == "INVALID_COMMAND_ARGS"
            [field] = refused.json()["fields"]
            assert field["path"] == "reference"
            assert field["message"].startswith("a ticket number or the mail's date")
        assert mongo.erasure_requests.count_documents({}) == 0

        for typed in ("T-1234", "#42", "2026-11-14-2"):
            self._log(operator_client, 1, reference=typed)

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

    def test_an_account_id_naming_no_account_is_refused_on_its_box(self, operator_client):
        """The review keeps its form on a 422 and fails whole on anything
        else, so an unknown id, or a fragment of one, is refused as the
        argument it is: in the preview, before anything is logged, and in the
        act. A fragment once reached ObjectId() and answered 500."""
        for user_id in (str(ObjectId()), "6633f0a1"):
            args = {"reference": "mail-1", "received_on": "2026-11-01", "user_id": user_id}
            for path in ("erasure_request.log/preview", "erasure_request.log"):
                refused = operator_client.post(
                    f"/api/operator/commands/{path}", json={"args": args}, headers=self.OWN
                )
                assert refused.status_code == 422, (user_id, path, refused.text)
                assert refused.json()["code"] == "INVALID_COMMAND_ARGS"
                assert [f["path"] for f in refused.json()["fields"]] == ["user_id"]
