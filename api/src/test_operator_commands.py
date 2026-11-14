"""The operator's commands and the job queue (docs/backoffice.md § Commands,
§ Jobs): the runner's gates, the organisation acts, and the window the
irreversible work waits out. The reads, the wall and the IAP checks are
test_operator.py; the operator env and the `operator_client` fixture are
conftest.py's.
"""

import os
from datetime import UTC, datetime, timedelta
from typing import Any, ClassVar

import pytest
from bson import ObjectId

from beats.domain.accounts import ERASURE_WINDOW_DAYS
from conftest import OPERATOR_ORIGIN as ORIGIN
from conftest import OPERATOR_SUB, VIEWER_SUB


class TestOperatorCommands:
    """POST /commands/{name}: the one path a mutation takes. The runner's
    gates (confirmation, role, unknown command), the delegation to the
    services that own each rule, and the audit that cannot be forgotten."""

    OWN: ClassVar[dict[str, str]] = {"Origin": ORIGIN}

    @pytest.fixture(autouse=True)
    def _clean(self, mongo):
        yield
        mongo.operator_audit.delete_many({})
        mongo.account_limits.delete_many({})

    def _user(self, mongo, email="cmd@example.test") -> str:
        user_id = str(ObjectId())
        mongo.users.insert_one(
            {"_id": ObjectId(user_id), "email": email, "created_at": datetime.now(UTC)}
        )
        return user_id

    def _run(self, operator_client, name, args, confirmation=None):
        return operator_client.post(
            f"/api/operator/commands/{name}",
            json={"args": args, "confirmation": confirmation},
            headers=self.OWN,
        )

    def test_suspend_needs_the_accounts_email_typed_back(self, operator_client, mongo):
        user_id = self._user(mongo)
        wrong = self._run(
            operator_client,
            "account.suspend",
            {"user_id": user_id, "reason": "scraping"},
            confirmation="someone-else@example.test",
        )
        assert wrong.status_code == 409
        assert wrong.json()["code"] == "CONFIRMATION_MISMATCH"
        assert mongo.users.find_one({"_id": ObjectId(user_id)}).get("suspended_at") is None

        right = self._run(
            operator_client,
            "account.suspend",
            {"user_id": user_id, "reason": "scraping"},
            confirmation="cmd@example.test",
        )
        assert right.status_code == 200, right.text
        assert mongo.users.find_one({"_id": ObjectId(user_id)})["suspended_at"] is not None

        # The audit cannot be forgotten: the runner is the only path, and the
        # entry carries before and after, the subject as subject_id (never
        # user_id, which erasure's sweep would take), and no address.
        entry = right.json()
        assert entry["command"] == "account.suspend"
        assert entry["subject_id"] == user_id
        assert entry["before"]["suspended"] is False
        assert entry["after"]["suspended"] is True
        stored = mongo.operator_audit.find_one({"subject_id": user_id})
        assert stored is not None
        assert "user_id" not in stored
        assert "cmd@example.test" not in str(stored)

    def test_unsuspend_set_limits_and_revoke_delegate(
        self, operator_client, mongo, auth_info, client
    ):
        user_id = self._user(mongo, "acts@example.test")
        self._run(
            operator_client,
            "account.suspend",
            {"user_id": user_id, "reason": "r"},
            confirmation="acts@example.test",
        )
        assert (
            self._run(operator_client, "account.unsuspend", {"user_id": user_id}).status_code == 200
        )
        assert mongo.users.find_one({"_id": ObjectId(user_id)})["suspended_at"] is None

        limits = self._run(
            operator_client,
            "account.set_limits",
            {"user_id": user_id, "writes_per_minute_beats": 5, "webhooks_disabled": True},
        )
        assert limits.status_code == 200, limits.text
        doc = mongo.account_limits.find_one({"user_id": user_id})
        assert doc["writes_per_minute_beats"] == 5
        assert doc["webhooks_disabled"] is True
        assert doc["set_by"] == OPERATOR_SUB
        assert (
            self._run(operator_client, "account.clear_limits", {"user_id": user_id}).status_code
            == 200
        )
        assert mongo.account_limits.find_one({"user_id": user_id}) is None

        # device.revoke: the narrow answer to one broken daemon.
        code = client.post("/api/device/pair/code", headers=auth_info["headers"]).json()["code"]
        device_id = client.post("/api/device/pair/exchange", json={"code": code}).json()[
            "device_id"
        ]
        revoked = self._run(
            operator_client,
            "device.revoke",
            {"user_id": auth_info["user_id"], "device_id": device_id},
        )
        assert revoked.status_code == 200, revoked.text
        assert mongo.device_registrations.find_one({"device_id": device_id})["revoked"] is True

    def test_sign_out_everywhere_sets_the_cut(self, operator_client, mongo):
        user_id = self._user(mongo, "cut@example.test")
        resp = self._run(operator_client, "account.sign_out_everywhere", {"user_id": user_id})
        assert resp.status_code == 200
        assert mongo.users.find_one({"_id": ObjectId(user_id)})["sessions_valid_after"]

    def test_suspend_refuses_the_erasure_kind(self, operator_client, mongo):
        """An erasure-kind suspension minted here would falsely promise a
        deletion date with no job behind it; that kind belongs to the
        erasure's own queueing."""
        user_id = self._user(mongo, "no-fake-erasure@example.test")
        resp = self._run(
            operator_client,
            "account.suspend",
            {"user_id": user_id, "kind": "erasure", "reason": "r"},
            confirmation="no-fake-erasure@example.test",
        )
        assert resp.status_code == 422
        assert resp.json()["code"] == "INVALID_COMMAND_ARGS"

    def test_an_unknown_command_is_404_and_bad_args_422(self, operator_client):
        assert self._run(operator_client, "account.explode", {"user_id": "x"}).status_code == 404
        bad = self._run(operator_client, "account.suspend", {"user_id": ""})
        assert bad.status_code == 422
        assert bad.json()["code"] == "INVALID_COMMAND_ARGS"

    async def test_a_viewer_runs_no_command(self):
        """The role gate is the runner's, so it holds for every command at
        once — pinned at the runner, since the dev stand-in fixes one
        identity per process."""
        from typing import cast

        from beats.operator.commands import CommandContext
        from beats.operator.runner import ViewerCannotAct, run_command
        from beats.operator.settings import OperatorIdentity

        # None stands in for everything after the role gate, which refuses
        # before any of it is touched.
        absent = cast("Any", None)
        ctx = CommandContext(
            operator=OperatorIdentity(sub=VIEWER_SUB, email="v@example.test", role="viewer"),
            db=absent,
            accounts=absent,
            organisations=absent,
            devices=absent,
        )
        with pytest.raises(ViewerCannotAct):
            await run_command(ctx, "account.unsuspend", {"user_id": "u"}, None)


class TestOperatorOrganisationActs:
    """The operator acts only for an organisation with no owner, and only
    when asked — and each act lands in the organisation's own audit log
    under actor_kind operator, with no operator id in it."""

    OWN: ClassVar[dict[str, str]] = {"Origin": ORIGIN}

    def _org(self, mongo, *, name="Orphaned Org", owner=False, closes_on=None) -> dict:
        org_id = str(ObjectId())
        mongo.organisations.insert_one(
            {
                "_id": ObjectId(org_id),
                "name": name,
                "created_by": "nobody",
                "created_at": datetime.now(UTC).isoformat(),
                "timezone": "UTC",
                "closes_on": closes_on,
            }
        )
        member_id = str(ObjectId())
        mongo.users.insert_one({"_id": ObjectId(member_id), "email": f"m-{member_id}@x.test"})
        mongo.org_members.insert_one(
            {
                "organisation_id": org_id,
                "user_id": member_id,
                "role": "owner" if owner else "admin",
                "name": "M",
                "email": f"m-{member_id}@x.test",
                "joined_at": datetime.now(UTC).isoformat(),
                "left_at": None,
            }
        )
        return {"org_id": org_id, "member_id": member_id}

    def _run(self, operator_client, name, args, confirmation=None):
        return operator_client.post(
            f"/api/operator/commands/{name}",
            json={"args": args, "confirmation": confirmation},
            headers=self.OWN,
        )

    def test_nothing_while_an_owner_exists(self, operator_client, mongo):
        planted = self._org(mongo, name="Owned Org", owner=True)
        resp = self._run(
            operator_client,
            "organisation.grant_owner",
            {"organisation_id": planted["org_id"], "user_id": planted["member_id"]},
            confirmation="Owned Org",
        )
        assert resp.status_code == 409, resp.text
        assert resp.json()["code"] == "ORGANISATION_HAS_OWNER"

    def test_grant_owner_to_the_requester_with_the_organisations_name_typed(
        self, operator_client, mongo
    ):
        planted = self._org(mongo)
        args = {"organisation_id": planted["org_id"], "user_id": planted["member_id"]}

        unconfirmed = self._run(operator_client, "organisation.grant_owner", args)
        assert unconfirmed.status_code == 409
        assert unconfirmed.json()["code"] == "CONFIRMATION_MISMATCH"

        granted = self._run(
            operator_client, "organisation.grant_owner", args, confirmation="Orphaned Org"
        )
        assert granted.status_code == 200, granted.text
        member = mongo.org_members.find_one({"user_id": planted["member_id"]})
        assert member["role"] == "owner"

        # In the organisation's own log, as the operator and as nobody:
        # actor_kind says whose act it was, and no operator id is in it.
        row = mongo.org_audit.find_one(
            {"organisation_id": planted["org_id"], "event": "member.role_changed"}
        )
        assert row["actor_kind"] == "operator"
        assert row.get("actor_user_id") is None
        assert OPERATOR_SUB not in str(row)

    def test_the_requester_must_hold_the_highest_active_role(self, operator_client, mongo):
        planted = self._org(mongo)  # the candidate is an admin
        lower_id = str(ObjectId())
        mongo.org_members.insert_one(
            {
                "organisation_id": planted["org_id"],
                "user_id": lower_id,
                "role": "member",
                "name": "L",
                "email": "l@x.test",
                "joined_at": datetime.now(UTC).isoformat(),
                "left_at": None,
            }
        )
        refused = self._run(
            operator_client,
            "organisation.grant_owner",
            {"organisation_id": planted["org_id"], "user_id": lower_id},
            confirmation="Orphaned Org",
        )
        assert refused.status_code == 409
        assert refused.json()["code"] == "REQUESTER_NOT_HIGHEST"

    def test_a_closing_notice_may_always_move_later(self, operator_client, mongo):
        """Amends decision 29: a notice with five days left can be extended
        by a week, while a fresh short notice is still refused."""
        soon = (datetime.now(UTC).date() + timedelta(days=5)).isoformat()
        planted = self._org(mongo, name="Closing Org", closes_on=soon)

        later = (datetime.now(UTC).date() + timedelta(days=12)).isoformat()
        moved = self._run(
            operator_client,
            "organisation.begin_closing",
            {"organisation_id": planted["org_id"], "closes_on": later},
            confirmation="Closing Org",
        )
        assert moved.status_code == 200, moved.text
        assert (
            mongo.organisations.find_one({"_id": ObjectId(planted["org_id"])})["closes_on"] == later
        )

        earlier = (datetime.now(UTC).date() + timedelta(days=3)).isoformat()
        refused = self._run(
            operator_client,
            "organisation.begin_closing",
            {"organisation_id": planted["org_id"], "closes_on": earlier},
            confirmation="Closing Org",
        )
        assert refused.status_code == 409
        assert refused.json()["code"] == "CLOSE_NOTICE_TOO_SHORT"

        cancelled = self._run(
            operator_client,
            "organisation.cancel_closing",
            {"organisation_id": planted["org_id"]},
        )
        assert cancelled.status_code == 200
        assert (
            mongo.organisations.find_one({"_id": ObjectId(planted["org_id"])}).get("closes_on")
            is None
        )


def _run_jobs() -> int:
    """Drain the queue the way the Cloud Run Job does: a fresh client on a
    fresh loop, because the job runner is its own process in production."""
    import asyncio

    from pymongo import AsyncMongoClient

    from beats.operator.jobs import run_due_jobs

    async def go() -> int:
        client = AsyncMongoClient(os.environ.get("DB_DSN", "mongodb://localhost:27017"))
        try:
            return await run_due_jobs(client[os.environ.get("DB_NAME", "beats_test")])
        finally:
            await client.close()

    return asyncio.run(go())


class TestOperatorJobs:
    """The window, the queue, and the sweep that must not eat its own record."""

    OWN: ClassVar[dict[str, str]] = {"Origin": ORIGIN}

    @pytest.fixture(autouse=True)
    def _clean(self, mongo):
        mongo.operator_jobs.delete_many({})
        mongo.operator_audit.delete_many({})
        yield
        mongo.operator_jobs.delete_many({})
        mongo.operator_audit.delete_many({})

    def _user(self, mongo, email: str) -> str:
        user_id = str(ObjectId())
        mongo.users.insert_one(
            {"_id": ObjectId(user_id), "email": email, "created_at": datetime.now(UTC)}
        )
        return user_id

    def _run(self, operator_client, name, args, confirmation=None):
        return operator_client.post(
            f"/api/operator/commands/{name}",
            json={"args": args, "confirmation": confirmation},
            headers=self.OWN,
        )

    def _due_now(self, mongo, job_id: str):
        mongo.operator_jobs.update_one(
            {"_id": ObjectId(job_id)},
            {"$set": {"run_after": (datetime.now(UTC) - timedelta(minutes=1)).isoformat()}},
        )

    def test_an_erasure_waits_out_its_window_suspended(self, operator_client, mongo):
        user_id = self._user(mongo, "erase-me@example.test")
        resp = self._run(
            operator_client,
            "account.erase",
            {"user_id": user_id},
            confirmation="erase-me@example.test",
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["queued"] is True
        job = body["job"]
        assert job["state"] == "queued"
        assert job["subject_id"] == user_id
        assert "user_id" not in job

        # Queueing suspended the account with the erasure's own wording — the
        # refusal names the day the window ends, inside the week there is to
        # stop it. Nothing is deleted yet.
        user = mongo.users.find_one({"_id": ObjectId(user_id)})
        assert user["suspended_kind"] == "erasure"
        run_after = datetime.fromisoformat(job["run_after"])
        assert run_after - datetime.now(UTC) > timedelta(days=6)

        # Second thoughts: job.cancel lifts that suspension — it was the
        # erasure's.
        cancelled = self._run(operator_client, "job.cancel", {"job_id": job["id"]})
        assert cancelled.status_code == 200, cancelled.text
        assert mongo.operator_jobs.find_one({"_id": ObjectId(job["id"])})["state"] == "cancelled"
        assert mongo.users.find_one({"_id": ObjectId(user_id)}).get("suspended_at") is None

    def test_cancelling_an_erasure_never_lifts_an_abuse_suspension(self, operator_client, mongo):
        user_id = self._user(mongo, "abusive@example.test")
        # Suspended for abuse first; the erasure queued on top keeps its own
        # wording, but cancelling it must not open the abuse door.
        self._run(
            operator_client,
            "account.suspend",
            {"user_id": user_id, "reason": "scraping"},
            confirmation="abusive@example.test",
        )
        job = self._run(
            operator_client,
            "account.erase",
            {"user_id": user_id},
            confirmation="abusive@example.test",
        ).json()["job"]
        # Put the abuse suspension back the way the operator would after a
        # mistaken queue-on-top: the kind decides what cancel may lift.
        mongo.users.update_one({"_id": ObjectId(user_id)}, {"$set": {"suspended_kind": "abuse"}})

        self._run(operator_client, "job.cancel", {"job_id": job["id"]})

        assert mongo.users.find_one({"_id": ObjectId(user_id)})["suspended_at"] is not None

    def test_the_job_runs_the_erasure_and_the_sweep_spares_its_own_record(
        self, operator_client, mongo
    ):
        user_id = self._user(mongo, "gone@example.test")
        mongo.projects.insert_one({"user_id": user_id, "name": "P"})
        mongo.account_limits.insert_one({"user_id": user_id, "webhooks_disabled": True})

        job = self._run(
            operator_client,
            "account.erase",
            {"user_id": user_id},
            confirmation="gone@example.test",
        ).json()["job"]
        self._due_now(mongo, job["id"])

        assert _run_jobs() == 1

        # The account and everything keyed on it went — account_limits keyed
        # on user_id deliberately, so the sweep takes it — while the job's
        # own entry and the audit of the act survive: their subject is
        # subject_id, which the sweep never matches.
        assert mongo.users.find_one({"_id": ObjectId(user_id)}) is None
        assert mongo.projects.find_one({"user_id": user_id}) is None
        assert mongo.account_limits.find_one({"user_id": user_id}) is None
        job_row = mongo.operator_jobs.find_one({"_id": ObjectId(job["id"])})
        assert job_row["state"] == "done"
        audit = mongo.operator_audit.find_one({"subject_id": user_id})
        assert audit is not None
        assert audit["command"] == "account.erase"
        assert audit["operator_sub"] == OPERATOR_SUB
        assert "gone@example.test" not in str(audit)

    def test_a_deletion_queued_then_outranked_by_a_new_owner_fails_its_job(
        self, operator_client, mongo
    ):
        """A command's rules are checked when it runs, not when it was
        queued; and after three attempts the entry is failed, for the alert
        to see."""
        org_id = str(ObjectId())
        yesterday = (datetime.now(UTC).date() - timedelta(days=1)).isoformat()
        mongo.organisations.insert_one(
            {
                "_id": ObjectId(org_id),
                "name": "Doomed Org",
                "created_by": "x",
                "created_at": datetime.now(UTC).isoformat(),
                "timezone": "UTC",
                "closes_on": yesterday,
            }
        )
        job = self._run(
            operator_client,
            "organisation.delete",
            {"organisation_id": org_id},
            confirmation="Doomed Org",
        ).json()["job"]

        # An owner appears while the job waits.
        mongo.org_members.insert_one(
            {
                "organisation_id": org_id,
                "user_id": str(ObjectId()),
                "role": "owner",
                "name": "O",
                "email": "o@x.test",
                "joined_at": datetime.now(UTC).isoformat(),
                "left_at": None,
            }
        )

        self._due_now(mongo, job["id"])
        # One drain retries a due, failing entry up to its attempt cap —
        # three claims — and then marks it failed, for the alert to see.
        assert _run_jobs() == 3
        row = mongo.operator_jobs.find_one({"_id": ObjectId(job["id"])})
        assert row["state"] == "failed"
        assert row["attempts"] == 3
        assert "owner" in row["error"].lower()
        assert mongo.organisations.find_one({"_id": ObjectId(org_id)}) is not None

    def test_an_ownerless_organisations_deletion_runs_once_due(self, operator_client, mongo):
        org_id = str(ObjectId())
        yesterday = (datetime.now(UTC).date() - timedelta(days=1)).isoformat()
        mongo.organisations.insert_one(
            {
                "_id": ObjectId(org_id),
                "name": "Ends Now",
                "created_by": "x",
                "created_at": datetime.now(UTC).isoformat(),
                "timezone": "UTC",
                "closes_on": yesterday,
            }
        )
        job = self._run(
            operator_client,
            "organisation.delete",
            {"organisation_id": org_id},
            confirmation="Ends Now",
        ).json()["job"]
        self._due_now(mongo, job["id"])

        assert _run_jobs() == 1

        assert mongo.organisations.find_one({"_id": ObjectId(org_id)}) is None
        assert mongo.operator_jobs.find_one({"_id": ObjectId(job["id"])})["state"] == "done"

    def test_the_purge_trims_the_operator_audit_at_four_years(self, mongo):
        import asyncio

        from pymongo import AsyncMongoClient

        from beats.infrastructure.retention import purge_expired_records

        old = (datetime.now(UTC) - timedelta(days=5 * 365)).isoformat()
        fresh = datetime.now(UTC).isoformat()
        mongo.operator_audit.insert_many(
            [
                {"at": old, "command": "account.suspend", "subject_id": "s1"},
                {"at": fresh, "command": "account.suspend", "subject_id": "s2"},
            ]
        )

        async def go():
            client = AsyncMongoClient(os.environ.get("DB_DSN", "mongodb://localhost:27017"))
            try:
                await purge_expired_records(
                    client[os.environ.get("DB_NAME", "beats_test")], apply=True
                )
            finally:
                await client.close()

        asyncio.run(go())

        remaining = list(mongo.operator_audit.find({}))
        assert [r["subject_id"] for r in remaining] == ["s2"]

    def test_one_queued_erasure_per_account_and_no_unsuspend_around_it(
        self, operator_client, mongo
    ):
        """The window must stay visible and cancellable as one thing: a
        second queued erasure would let a cancel lift the suspension while
        the other ran on schedule, and an unsuspend around a queued erasure
        would leave the account working normally — showing none of the
        warning — and still erased in seven days. job.cancel is the one way
        out, and it lifts the suspension itself."""
        user_id = self._user(mongo, "once@example.test")
        first = self._run(
            operator_client, "account.erase", {"user_id": user_id}, "once@example.test"
        )
        assert first.status_code == 200, first.text

        again = self._run(
            operator_client, "account.erase", {"user_id": user_id}, "once@example.test"
        )
        assert again.status_code == 409
        assert again.json()["code"] == "JOB_ALREADY_QUEUED"

        unsuspend = self._run(operator_client, "account.unsuspend", {"user_id": user_id})
        assert unsuspend.status_code == 409
        assert unsuspend.json()["code"] == "ERASURE_QUEUED"

        job_id = first.json()["job"]["id"]
        assert self._run(operator_client, "job.cancel", {"job_id": job_id}).status_code == 200
        assert mongo.users.find_one({"_id": ObjectId(user_id)}).get("suspended_at") is None

    def test_a_mistyped_subject_is_refused_at_queue_time_not_waived(self, operator_client, mongo):
        """A subject that doesn't resolve must never read as 'no confirmation
        required': the typed confirmation exists precisely for the mistyped
        id."""
        resp = self._run(operator_client, "account.erase", {"user_id": str(ObjectId())})
        assert resp.status_code == 404
        assert resp.json()["code"] == "ACCOUNT_NOT_FOUND"
        assert mongo.operator_jobs.count_documents({}) == 0

    def test_a_failed_queue_side_effect_leaves_no_job_standing(self, operator_client, mongo):
        """If queueing's suspension fails, the job is cancelled and the error
        surfaces: a job with no suspension would wait out an invisible window
        while the operator, who saw an error, believes nothing was queued.
        Driven at the runner with the real context, its suspend replaced by
        the transient failure a Mongo hiccup would be."""
        import asyncio

        from pymongo import AsyncMongoClient

        from beats.operator.context import build_command_context
        from beats.operator.runner import run_command
        from beats.operator.settings import OperatorIdentity

        user_id = self._user(mongo, "half@example.test")

        async def queue_with_failing_suspend() -> bool:
            client = AsyncMongoClient(os.environ.get("DB_DSN", "mongodb://localhost:27017"))
            try:
                db = client[os.environ.get("DB_NAME", "beats_test")]
                ctx = build_command_context(
                    db,
                    OperatorIdentity(sub=OPERATOR_SUB, email="op@example.test", role="operator"),
                )

                async def failing_suspend(*args, **kwargs):
                    raise RuntimeError("transient write failure")

                # ty flags replacing a bound method; a cast keeps the patch
                # explicit without widening the service's own type.
                from typing import cast

                cast("Any", ctx.accounts).suspend = failing_suspend
                try:
                    await run_command(
                        ctx, "account.erase", {"user_id": user_id}, "half@example.test"
                    )
                except RuntimeError:
                    return True
                return False
            finally:
                await client.close()

        assert asyncio.run(queue_with_failing_suspend()) is True
        job = mongo.operator_jobs.find_one({"subject_id": user_id})
        assert job is not None
        assert job["state"] == "cancelled"


class TestCommandPreview:
    """POST /commands/{name}/preview: what the act would do, answered
    without doing any of it. The review a page shows comes from here, so it
    has to pass the same gates as the act and change nothing on the way."""

    OWN: ClassVar[dict[str, str]] = {"Origin": ORIGIN}

    @pytest.fixture(autouse=True)
    def _clean(self, mongo):
        yield
        mongo.operator_audit.delete_many({})
        mongo.operator_jobs.delete_many({})
        mongo.users.delete_many({})

    def _user(self, mongo, email="preview@example.test") -> str:
        user_id = str(ObjectId())
        mongo.users.insert_one(
            {"_id": ObjectId(user_id), "email": email, "created_at": datetime.now(UTC)}
        )
        return user_id

    def _preview(self, operator_client, name, args):
        return operator_client.post(
            f"/api/operator/commands/{name}/preview", json={"args": args}, headers=self.OWN
        )

    def test_an_inline_command_answers_its_subject_and_no_window(self, operator_client, mongo):
        user_id = self._user(mongo)
        body = self._preview(
            operator_client, "account.sign_out_everywhere", {"user_id": user_id}
        ).json()
        assert body["command"] == "account.sign_out_everywhere"
        assert body["subject_kind"] == "account"
        assert body["subject_id"] == user_id
        assert body["confirmation_required"] is False
        assert body["window_days"] is None
        assert body["runs_after"] is None
        assert body["already_queued"] is False
        # describe()'s own answer, which the audit will keep as `before`.
        assert body["before"]["suspended"] is False

    def test_a_command_that_asks_for_the_subject_says_so_without_naming_it(
        self, operator_client, mongo
    ):
        """The operator types the address because they know it. A preview
        that handed it back could be autofilled, and the typing would stop
        proving anything."""
        user_id = self._user(mongo, email="typed@example.test")
        response = self._preview(
            operator_client, "account.suspend", {"user_id": user_id, "reason": "scraping"}
        )
        assert response.json()["confirmation_required"] is True
        assert "typed@example.test" not in response.text

    def test_a_windowed_command_says_when_it_would_run(self, operator_client, mongo):
        user_id = self._user(mongo)
        body = self._preview(operator_client, "account.erase", {"user_id": user_id}).json()
        assert body["window_days"] == ERASURE_WINDOW_DAYS
        runs_after = datetime.fromisoformat(body["runs_after"])
        expected = datetime.now(UTC) + timedelta(days=ERASURE_WINDOW_DAYS)
        assert abs((runs_after - expected).total_seconds()) < 60

    def test_previewing_changes_nothing(self, operator_client, mongo):
        """The whole point: it is a read of what the act would do. Every
        command is previewed, including the ones that suspend, erase and
        delete, and nothing moves."""
        user_id = self._user(mongo)
        before = mongo.users.find_one({"_id": ObjectId(user_id)})
        for name, args in (
            ("account.suspend", {"user_id": user_id, "reason": "scraping"}),
            ("account.unsuspend", {"user_id": user_id}),
            ("account.sign_out_everywhere", {"user_id": user_id}),
            ("account.clear_limits", {"user_id": user_id}),
            ("account.erase", {"user_id": user_id}),
        ):
            assert self._preview(operator_client, name, args).status_code == 200

        assert mongo.users.find_one({"_id": ObjectId(user_id)}) == before
        assert mongo.operator_audit.count_documents({}) == 0
        assert mongo.operator_jobs.count_documents({}) == 0

    def test_an_unknown_command_and_bad_arguments_refuse_as_the_act_does(
        self, operator_client, mongo
    ):
        unknown = self._preview(operator_client, "account.explode", {"user_id": "x"})
        assert unknown.status_code == 404
        bad = self._preview(operator_client, "account.suspend", {"user_id": ""})
        assert bad.status_code == 422
        assert bad.json()["code"] == "INVALID_COMMAND_ARGS"

    def test_a_subject_that_does_not_resolve_refuses_before_anything_is_typed(
        self, operator_client, mongo
    ):
        """A mistyped id is the case the typed confirmation exists for, and
        the review is where the operator should learn of it."""
        missing = self._preview(
            operator_client, "account.suspend", {"user_id": str(ObjectId()), "reason": "x"}
        )
        assert missing.status_code == 404

    def test_a_queued_window_is_named_before_the_second_attempt(self, operator_client, mongo):
        user_id = self._user(mongo, email="queued@example.test")
        assert (
            self._preview(operator_client, "account.erase", {"user_id": user_id}).json()[
                "already_queued"
            ]
            is False
        )

        queued = operator_client.post(
            "/api/operator/commands/account.erase",
            json={"args": {"user_id": user_id}, "confirmation": "queued@example.test"},
            headers=self.OWN,
        )
        assert queued.status_code == 200

        assert (
            self._preview(operator_client, "account.erase", {"user_id": user_id}).json()[
                "already_queued"
            ]
            is True
        )

    async def test_a_viewer_previews_nothing(self):
        """Same gate as the act, at the runner for the same reason: a
        preview a viewer could read would say whether an id exists."""
        from typing import cast

        from beats.operator.commands import CommandContext
        from beats.operator.runner import ViewerCannotAct, preview_command
        from beats.operator.settings import OperatorIdentity

        absent = cast("Any", None)
        ctx = CommandContext(
            operator=OperatorIdentity(sub=VIEWER_SUB, email="v@example.test", role="viewer"),
            db=absent,
            accounts=absent,
            organisations=absent,
            devices=absent,
        )
        with pytest.raises(ViewerCannotAct):
            await preview_command(ctx, "account.unsuspend", {"user_id": "u"})


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
