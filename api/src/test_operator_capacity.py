"""The database's size over time (docs/backoffice.md § The pages, Capacity):
kept once a UTC day by the job runner, safe when two runs overlap, never in
the way of the queue the runner exists for, and read back by the capacity
route as a series and a pace; and the cluster's connections beside it. The
pace's arithmetic is beats/test_operator_growth.py's; the coach's cost on the
same route is test_operator.py's `TestCapacityRead`.

The runner is driven the way `_run_jobs` in test_operator_commands.py drives
it: a fresh client on a fresh loop, because in production it is its own
process.
"""

import asyncio
import logging
import os
from datetime import UTC, datetime, timedelta

import pytest
from bson import ObjectId
from pymongo import AsyncMongoClient
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import OperationFailure

from beats.infrastructure.database_sizes import COLLECTION, MongoDatabaseSizes
from beats.operator import jobs
from beats.operator.growth import DAYS_A_MONTH

MB = 1024 * 1024


def _on_a_fresh_client(work):
    async def go():
        client: AsyncMongoClient = AsyncMongoClient(
            os.environ.get("DB_DSN", "mongodb://localhost:27017")
        )
        try:
            return await work(client[os.environ.get("DB_NAME", "beats_test")])
        finally:
            await client.close()

    return asyncio.run(go())


@pytest.fixture(autouse=True)
def _no_sizes(mongo):
    mongo[COLLECTION].delete_many({})
    yield
    mongo[COLLECTION].delete_many({})


class TestKeepingTheSize:
    def test_a_day_is_kept_once_and_the_next_day_again(self, mongo):
        today = datetime.now(UTC)
        early, late = today.replace(hour=0, minute=5), today.replace(hour=23, minute=55)
        tomorrow = early + timedelta(days=1)

        assert _on_a_fresh_client(lambda db: MongoDatabaseSizes(db).keep(early)) is True
        assert _on_a_fresh_client(lambda db: MongoDatabaseSizes(db).keep(late)) is False
        assert _on_a_fresh_client(lambda db: MongoDatabaseSizes(db).keep(tomorrow)) is True

        days = sorted(d["_id"] for d in mongo[COLLECTION].find())
        assert days == [early.date().isoformat(), tomorrow.date().isoformat()]
        # The later run of the same day changed nothing: the day's size is
        # its first run's.
        first = mongo[COLLECTION].find_one({"_id": early.date().isoformat()})
        assert abs(first["taken_at"].replace(tzinfo=UTC) - early) < timedelta(seconds=1)

    def test_a_size_is_figures_and_names_only(self, mongo):
        mongo.operator_audit.insert_one({"at": datetime.now(UTC)})
        _on_a_fresh_client(lambda db: MongoDatabaseSizes(db).keep(datetime.now(UTC)))
        (doc,) = list(mongo[COLLECTION].find())
        audit = next(c for c in doc["collections"] if c["name"] == "operator_audit")
        assert set(audit) == {"name", "documents", "storage_bytes", "data_bytes", "index_bytes"}
        assert audit["documents"] >= 1
        assert audit["storage_bytes"] > 0

    def test_two_runs_at_once_keep_one_size(self, mongo):
        """Two ticks that overlap — a slow run and the next one — both find
        the day missing; one keeps it and the other changes nothing."""
        now = datetime.now(UTC)

        async def both(db: AsyncDatabase):
            return await asyncio.gather(
                MongoDatabaseSizes(db).keep(now), MongoDatabaseSizes(db).keep(now)
            )

        assert sorted(_on_a_fresh_client(both)) == [False, True]
        assert mongo[COLLECTION].count_documents({}) == 1


class TestTheRunnerKeepsIt:
    def test_a_run_keeps_todays_size_after_the_queue(self, mongo):
        assert _on_a_fresh_client(jobs.tick) == 0
        assert mongo[COLLECTION].find_one({"_id": datetime.now(UTC).date().isoformat()})

    def test_a_size_that_cannot_be_taken_fails_nothing_and_pages_nobody(
        self, mongo, monkeypatch, caplog
    ):
        """The grant missing on the job's database user is the likely way
        this fails. The queued work still runs, and the run logs a WARNING:
        an ERROR from this job pages somebody (terraform/operator.tf)."""
        user_id = str(ObjectId())
        mongo.users.insert_one({"_id": ObjectId(user_id), "email": "size-test@example.test"})
        job_id = mongo.operator_jobs.insert_one(
            {
                "command": "account.sign_out_everywhere",
                "args": {"user_id": user_id},
                "subject_kind": "account",
                "subject_id": user_id,
                "queued_by": {"sub": "test-operator", "email": "op@example.test"},
                "queued_at": datetime.now(UTC).isoformat(),
                "run_after": (datetime.now(UTC) - timedelta(minutes=1)).isoformat(),
                "state": "queued",
                "attempts": 0,
                "claimed_at": None,
                "finished_at": None,
                "error": None,
            }
        ).inserted_id

        async def refused(self, now):
            raise OperationFailure("not authorized on beats_test to execute command", code=13)

        monkeypatch.setattr(MongoDatabaseSizes, "keep", refused)
        try:
            with caplog.at_level(logging.INFO, logger="beats"):
                assert _on_a_fresh_client(jobs.tick) == 1
        finally:
            mongo.operator_jobs.delete_one({"_id": job_id})
            mongo.operator_audit.delete_many({"subject_id": user_id})

        assert mongo.users.find_one({"_id": ObjectId(user_id)}).get("sessions_valid_after")
        assert [r.levelname for r in caplog.records if "size" in r.getMessage()] == ["WARNING"]
        assert not [r for r in caplog.records if r.levelno >= logging.ERROR]
        assert mongo[COLLECTION].count_documents({}) == 0


def _plant(mongo, days_ago: int, collections: dict[str, int]) -> None:
    day = (datetime.now(UTC) - timedelta(days=days_ago)).date()
    mongo[COLLECTION].insert_one(
        {
            "_id": day.isoformat(),
            "taken_at": datetime.now(UTC),
            "expires_at": datetime.now(UTC) + timedelta(days=30),
            "collections": [
                {"name": n, "documents": 1, "storage_bytes": b, "data_bytes": b, "index_bytes": 0}
                for n, b in collections.items()
            ],
        }
    )


class TestCapacityGrowth:
    """What the route answers about the sizes kept, over HTTP."""

    def test_before_two_days_are_kept_there_is_no_pace(self, operator_client, mongo):
        body = operator_client.get("/api/operator/capacity").json()
        assert body["sizes"] == []
        assert body["growth"] is None

        _plant(mongo, 0, {"operator_audit": 4 * MB})
        body = operator_client.get("/api/operator/capacity").json()
        assert [s["storage_bytes"] for s in body["sizes"]] == [4 * MB]
        assert body["growth"] is None
        assert all(c["growth_bytes_a_month"] is None for c in body["collections"])

    def test_the_sizes_kept_read_back_as_a_series_and_a_pace(self, operator_client, mongo):
        mongo.operator_audit.insert_one({"at": datetime.now(UTC)})
        _plant(mongo, 10, {"operator_audit": 4 * MB, "timeLogs": 6 * MB})
        _plant(mongo, 3, {"operator_audit": 5 * MB, "timeLogs": 6 * MB})
        _plant(mongo, 0, {"operator_audit": 6 * MB, "timeLogs": 6 * MB, "flow_windows": 2 * MB})

        body = operator_client.get("/api/operator/capacity").json()
        assert [s["storage_bytes"] for s in body["sizes"]] == [10 * MB, 11 * MB, 14 * MB]
        assert body["sizes"][0]["day"] < body["sizes"][-1]["day"]

        growth = body["growth"]
        assert growth["since"] == body["sizes"][0]["day"]
        assert growth["until"] == body["sizes"][-1]["day"]
        assert growth["change_bytes"] == 4 * MB
        assert growth["bytes_a_month"] == pytest.approx(4 * MB * DAYS_A_MONTH / 10)

        audit = next(c for c in body["collections"] if c["name"] == "operator_audit")
        assert audit["growth_bytes_a_month"] == pytest.approx(2 * MB * DAYS_A_MONTH / 10)
        assert audit["growth_share_a_month"] == pytest.approx(0.5 * DAYS_A_MONTH / 10)


class TestConnections:
    def test_the_clusters_connections_are_read(self, operator_client):
        connections = operator_client.get("/api/operator/capacity").json()["connections"]
        assert connections["current"] >= 1
        assert connections["allowed"] > connections["current"]

    def test_a_refused_server_status_leaves_the_rest_of_the_page(
        self, operator_client, monkeypatch
    ):
        """A database user without the action — the grant not yet made — is
        a tile that says it cannot tell, not a page that fails."""
        original = AsyncDatabase.command

        async def refuse(self, command, *args, **kwargs):
            if command == "serverStatus":
                raise OperationFailure("not authorized on admin to execute command", code=13)
            return await original(self, command, *args, **kwargs)

        monkeypatch.setattr(AsyncDatabase, "command", refuse)
        resp = operator_client.get("/api/operator/capacity")
        assert resp.status_code == 200
        assert resp.json()["connections"] is None
        assert resp.json()["collections"]
