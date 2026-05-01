"""Coach domain tests.

Sibling of test_domain.py — covers the coach modules whose logic is
deterministic enough to test without making LLM calls. Some tests touch
Mongo via the testcontainers harness in conftest.py; others are pure.
Gateway streaming, the chat tool-use loop, and context builders use
hand-rolled fakes (added incrementally per the coach hardening
roadmap).

The test_api.py suite covers the HTTP layer; this file covers the
modules underneath.
"""

import os

import pytest
from motor.motor_asyncio import AsyncIOMotorClient

from beats.coach.memory import MemoryStore
from beats.coach.repos import COACH_MEMORY_COLLECTION, fmt_minutes


def _async_db():
    """Build a Motor handle for the test database. The conftest's
    testcontainer sets DB_DSN/DB_NAME; we connect directly so the
    coach modules can be exercised with their real (async) signature."""
    dsn = os.environ.get("DB_DSN", "mongodb://localhost:27017")
    db_name = os.environ.get("DB_NAME", "beats_test")
    client = AsyncIOMotorClient(dsn)
    return client, client[db_name]


class TestFmtMinutes:
    """fmt_minutes formats a minute count as 'Nh Mm' or 'Mm'.

    Used in the coach's session tables and the day/user context builders.
    Locks in the boundary cases — these are the inputs that matter for
    the coach's per-project hour summaries (a 60-minute session formatting
    as '60m' instead of '1h 0m' would surprise readers, and a fractional
    input formatting as '0h 0m' instead of '0m' would clutter the output).
    """

    def test_zero_minutes(self):
        assert fmt_minutes(0) == "0m"

    def test_under_one_hour(self):
        assert fmt_minutes(15) == "15m"
        assert fmt_minutes(45) == "45m"
        # Boundary — one minute under the hour.
        assert fmt_minutes(59) == "59m"

    def test_exactly_one_hour(self):
        # 60 → "1h 0m", not "60m" — the hour boundary kicks in at >= 60
        # because divmod(60, 60) == (1, 0) and the h>0 branch fires.
        assert fmt_minutes(60) == "1h 0m"

    def test_one_hour_with_remainder(self):
        assert fmt_minutes(61) == "1h 1m"
        assert fmt_minutes(75) == "1h 15m"
        assert fmt_minutes(90) == "1h 30m"

    def test_multiple_hours(self):
        assert fmt_minutes(120) == "2h 0m"
        assert fmt_minutes(125) == "2h 5m"
        assert fmt_minutes(480) == "8h 0m"

    def test_large_value(self):
        # 24h+ — the coach occasionally summarizes across multi-day
        # windows. No special handling for "1d", just keeps counting hours.
        assert fmt_minutes(1500) == "25h 0m"
        assert fmt_minutes(1543) == "25h 43m"

    def test_fractional_input_truncates(self):
        # int() truncates toward zero (per the implementation's
        # divmod(int(minutes), 60)). A 30.7-minute session reads as
        # "30m", not "31m" — pin so a future change to round() is
        # a deliberate decision, not an accident.
        assert fmt_minutes(30.7) == "30m"
        assert fmt_minutes(59.9) == "59m"
        # 60.5 → int → 60 → "1h 0m" (the hour kicks in only AT 60
        # post-truncation, not before).
        assert fmt_minutes(60.5) == "1h 0m"


class TestMemoryStore:
    """MemoryStore is the per-user Markdown document the coach rewrites
    weekly. It's read into the cached UserContextBlock, so a write that
    silently doesn't persist (or a read that misses for the user) is
    invisible at API-test level — it just degrades the coach's
    personality. These tests pin the contract end-to-end against real
    Mongo (via testcontainers).
    """

    @pytest.fixture(autouse=True)
    async def _clean_memory(self):
        client, db = _async_db()
        try:
            await db[COACH_MEMORY_COLLECTION].delete_many({})
            yield
        finally:
            client.close()

    async def test_read_returns_none_for_fresh_user(self):
        client, db = _async_db()
        try:
            store = MemoryStore(db, "user-fresh")
            assert await store.read() is None
        finally:
            client.close()

    async def test_write_then_read_round_trips(self):
        client, db = _async_db()
        try:
            store = MemoryStore(db, "user-1")
            await store.write("# Coach memory\n\nUser ships at night.")
            got = await store.read()
            assert got == "# Coach memory\n\nUser ships at night."
        finally:
            client.close()

    async def test_write_is_idempotent_on_user_id(self):
        """Two writes for the same user must not produce two rows —
        the coach's UserContextBlock reads exactly one document.
        Locks the upsert."""
        client, db = _async_db()
        try:
            store = MemoryStore(db, "user-1")
            await store.write("first")
            await store.write("second")
            count = await db[COACH_MEMORY_COLLECTION].count_documents({"user_id": "user-1"})
            assert count == 1
            assert await store.read() == "second"
        finally:
            client.close()

    async def test_write_pushes_previous_content_into_history(self):
        """The store keeps a versioned history so the coach's prior
        memory isn't lost when it's rewritten weekly. Pin that the
        $push happens (without this guarantee, a memory_rewrite
        regression that emitted bad content would silently overwrite
        the user's prior good memory)."""
        client, db = _async_db()
        try:
            store = MemoryStore(db, "user-1")
            await store.write("v1")
            await store.write("v2")
            await store.write("v3")
            doc = await db[COACH_MEMORY_COLLECTION].find_one({"user_id": "user-1"})
            assert doc is not None
            history = doc.get("history", [])
            # Three writes → three history entries (one for the
            # "previous content" of each write, including the empty
            # string that preceded v1).
            assert len(history) == 3
            assert [h["content"] for h in history] == ["", "v1", "v2"]
            # And the current content is v3.
            assert doc["content"] == "v3"
        finally:
            client.close()

    async def test_users_are_isolated(self):
        """A write for user A must not affect user B's read. Verifies
        the user_id query scoping — without this, the coach would
        pollute one user's memory into another's."""
        client, db = _async_db()
        try:
            store_a = MemoryStore(db, "user-a")
            store_b = MemoryStore(db, "user-b")

            await store_a.write("only A's notes")
            assert await store_b.read() is None

            await store_b.write("only B's notes")
            assert await store_a.read() == "only A's notes"
            assert await store_b.read() == "only B's notes"
        finally:
            client.close()

    async def test_first_write_initializes_metadata(self):
        """First write should set created_at, updated_at, and the
        history's "previous" entry to an empty string. These are the
        fields a future migration / introspection script would rely
        on; pin so a refactor that drops $setOnInsert breaks the
        test rather than silently shipping."""
        client, db = _async_db()
        try:
            store = MemoryStore(db, "user-1")
            await store.write("first")
            doc = await db[COACH_MEMORY_COLLECTION].find_one({"user_id": "user-1"})
            assert doc is not None
            assert "created_at" in doc
            assert "updated_at" in doc
            history = doc.get("history", [])
            assert len(history) == 1
            assert history[0]["content"] == ""  # the "previous" before first write
        finally:
            client.close()
