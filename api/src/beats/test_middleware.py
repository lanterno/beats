"""Idempotency middleware internals.

The HTTP-level contract (replay headers, failures not being cached) is covered
by ``TestIdempotentReplay`` in ``src/test_api.py``. These tests drive the
reservation helpers directly, because the behaviour that matters most —
two identical requests racing — cannot be produced through a single
``TestClient`` call.
"""

from datetime import UTC, datetime, timedelta

import pytest

from beats.api.middleware.idempotency import (
    _RESERVATION_STALE_SECONDS,
    _answer_from_reservation,
    _reserve,
    ensure_mutation_log_indexes,
)
from beats.infrastructure.database import Database


class TestIdempotencyReservation:
    """`_reserve` is the concurrency guard. It replaced a check-then-execute
    pass in which two simultaneous retries of the same client id both missed
    the lookup, both ran the mutation, and the loser's insert was swallowed by
    a broad `except` — a silent double-apply on exactly the traffic the offline
    queue generates when it drains on reconnect."""

    @pytest.fixture(autouse=True)
    async def _db(self):
        await Database.connect()
        await ensure_mutation_log_indexes()
        await Database.get_db().mutation_log.delete_many({})
        yield
        await Database.get_db().mutation_log.delete_many({})
        await Database.disconnect()

    @property
    def _collection(self):
        return Database.get_db().mutation_log

    @staticmethod
    def _key(client_id: str = "client-1") -> dict[str, str]:
        return {"user_id": "user-1", "client_id": client_id}

    async def test_first_caller_wins_the_reservation(self):
        assert await _reserve(self._collection, self._key()) is True

    async def test_second_concurrent_caller_is_refused(self):
        """The race: the winner has reserved but not yet recorded a response.
        The loser must not proceed to run the mutation."""
        key = self._key()
        assert await _reserve(self._collection, key) is True
        assert await _reserve(self._collection, key) is False

    async def test_different_client_ids_do_not_block_each_other(self):
        assert await _reserve(self._collection, self._key("a")) is True
        assert await _reserve(self._collection, self._key("b")) is True

    async def test_loser_gets_409_while_the_winner_is_still_running(self):
        key = self._key()
        await _reserve(self._collection, key)

        response = await _answer_from_reservation(self._collection, key, "/api/projects/x/start")

        assert response.status_code == 409
        assert b"IDEMPOTENT_IN_PROGRESS" in response.body
        assert response.headers.get("X-Idempotent-Replay") is None

    async def test_loser_gets_the_recorded_response_once_the_winner_finishes(self):
        key = self._key()
        await _reserve(self._collection, key)
        await self._collection.update_one(
            key,
            {
                "$set": {
                    "completed": True,
                    "status_code": 201,
                    "body": b'{"id":"beat-1"}',
                    "media_type": "application/json",
                }
            },
        )

        response = await _answer_from_reservation(self._collection, key, "/api/projects/x/start")

        assert response.status_code == 201
        assert response.body == b'{"id":"beat-1"}'
        assert response.headers["X-Idempotent-Replay"] == "true"

    async def test_completed_reservation_still_refuses_a_fresh_run(self):
        """A recorded response must be replayed, never re-executed."""
        key = self._key()
        await _reserve(self._collection, key)
        await self._collection.update_one(key, {"$set": {"completed": True, "status_code": 200}})

        assert await _reserve(self._collection, key) is False

    async def test_abandoned_reservation_is_claimable(self):
        """A process that died between reserving and recording would otherwise
        wedge that client id until the 72h TTL expired it, and every retry
        would be answered 409 — silently losing the mutation."""
        key = self._key()
        await _reserve(self._collection, key)
        await self._collection.update_one(
            key,
            {
                "$set": {
                    "created_at": datetime.now(UTC)
                    - timedelta(seconds=_RESERVATION_STALE_SECONDS + 5)
                }
            },
        )

        assert await _reserve(self._collection, key) is True

    async def test_recent_reservation_is_not_claimable(self):
        """The takeover window must not be so eager that a slow-but-live
        request gets its reservation stolen and its mutation double-applied."""
        key = self._key()
        await _reserve(self._collection, key)
        await self._collection.update_one(
            key,
            {
                "$set": {
                    "created_at": datetime.now(UTC)
                    - timedelta(seconds=_RESERVATION_STALE_SECONDS - 5)
                }
            },
        )

        assert await _reserve(self._collection, key) is False
