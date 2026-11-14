"""The coach's memory: the store, and the rewrite.

Split out of `test_coach.py` at the size ceiling (CLAUDE.md § Conventions);
the shared fakes and factories are `coach_fakes.py`'s.
"""

import pytest

from beats.coach import memory_rewrite as memory_rewrite_module
from beats.coach.gateway import (
    GatewayResponse,
)
from beats.coach.memory import MemoryStore
from beats.coach.repos import (
    COACH_MEMORY_COLLECTION,
)
from beats.coach_fakes import (
    _async_db,
)
from beats.infrastructure.database import Database
from beats.settings import settings


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
            await client.close()

    async def test_read_returns_none_for_fresh_user(self):
        client, db = _async_db()
        try:
            store = MemoryStore(db, "user-fresh")
            assert await store.read() is None
        finally:
            await client.close()

    async def test_write_then_read_round_trips(self):
        client, db = _async_db()
        try:
            store = MemoryStore(db, "user-1")
            await store.write("# Coach memory\n\nUser ships at night.")
            got = await store.read()
            assert got == "# Coach memory\n\nUser ships at night."
        finally:
            await client.close()

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
            await client.close()

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
            await client.close()

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
            await client.close()

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
            await client.close()


class TestRewriteCoachMemory:
    """Nightly memory compaction. Reads the last 7 days, asks the LLM
    for a Markdown summary, persists via MemoryStore (which keeps the
    versioned history). The risk this guards against is silent loss
    of personality — a memory rewrite that succeeds-with-empty would
    overwrite the user's prior memory with a blank document."""

    @pytest.fixture(autouse=True)
    async def _setup(self, monkeypatch):
        await Database.connect(settings.db_dsn, settings.db_name)
        await Database.get_db()[COACH_MEMORY_COLLECTION].delete_many({})

        # Stub the heavy upstream — _recent_data_summary calls many
        # repos to build the per-day/intention/mood/review prompt
        # block. Tested independently at the IntelligenceService /
        # repo level; here we just need a deterministic stub.
        async def fake_summary(_user_id, _tz=None):
            return "## Recent\nfoo did things"

        monkeypatch.setattr(memory_rewrite_module, "_recent_data_summary", fake_summary)

        # Stub build_coach_messages: same shape as elsewhere.
        async def fake_build(_user_id, prompt, **_):
            return ("system", [{"role": "user", "content": prompt}], None)

        monkeypatch.setattr(memory_rewrite_module, "build_coach_messages", fake_build)

        yield
        await Database.disconnect()

    @pytest.fixture
    def patch_complete(self, monkeypatch):
        """Returns a setter for the canned LLM response + a captured-
        kwargs dict, identical pattern to the chat / brief / review
        fixtures."""
        captured: dict = {}

        async def factory(text: str = "# Coach memory\n\nUser ships at night."):
            async def fake_complete(**kwargs):
                captured["kwargs"] = kwargs
                from anthropic.types import TextBlock as _TB

                return GatewayResponse(
                    content=[_TB(type="text", text=text, citations=None)],
                    model="claude-opus-4-7",
                    input_tokens=2000,
                    output_tokens=500,
                    cache_creation_input_tokens=0,
                    cache_read_input_tokens=0,
                    cost_usd=0.04,
                    stop_reason="end_turn",
                )

            monkeypatch.setattr(memory_rewrite_module, "complete", fake_complete)

        return factory, captured

    async def test_persists_rewritten_memory_via_memory_store(self, patch_complete):
        """Happy path: LLM returns Markdown, rewrite_coach_memory
        strips and persists via MemoryStore. The next read sees the
        new content."""
        factory, _ = patch_complete
        await factory("# Coach memory\n\nNew personality.")

        result = await memory_rewrite_module.rewrite_coach_memory("user-1")
        assert result == "# Coach memory\n\nNew personality."

        # Read it back through the same store the API uses.
        client, db = _async_db()
        try:
            store = MemoryStore(db, "user-1")
            assert await store.read() == "# Coach memory\n\nNew personality."
        finally:
            await client.close()

    async def test_strips_whitespace_around_llm_output(self, patch_complete):
        """LLM may emit leading/trailing newlines (Anthropic models
        often do). Pin the strip — without it, the persisted memory
        starts with blank lines that render oddly in the
        UserContextBlock."""
        factory, _ = patch_complete
        await factory("\n\n  # Real content\n\n  ")

        result = await memory_rewrite_module.rewrite_coach_memory("user-1")
        assert result == "# Real content"

    async def test_passes_purpose_memory_rewrite_to_gateway(self, patch_complete):
        """Cost-bucket tag — the dashboard distinguishes memory_rewrite
        from chat/brief/review so a single weekly rewrite cost (a
        few cents per user) doesn't get hidden in the chat bucket."""
        factory, captured = patch_complete
        await factory()

        await memory_rewrite_module.rewrite_coach_memory("user-99")
        assert captured["kwargs"]["purpose"] == "memory_rewrite"
        assert captured["kwargs"]["user_id"] == "user-99"

    async def test_caps_output_tokens(self, patch_complete):
        """Memory rewrites get a tighter output cap than chat (2048 vs
        4096). Pin so a refactor that drops the kwargs to defaults
        doesn't quietly widen the per-rewrite cost.

        This test also used to pin temperature=0.3. Sampling parameters
        were removed from the API on every current-generation model —
        they now return HTTP 400 — so the gateway no longer sends one.
        `output_config.effort` is the replacement lever if the coach ever
        needs to trade thoroughness for cost per call site."""
        factory, captured = patch_complete
        await factory()

        await memory_rewrite_module.rewrite_coach_memory("user-1")
        assert "temperature" not in captured["kwargs"]
        assert captured["kwargs"]["max_tokens"] == 2048

    async def test_includes_recent_data_summary_in_prompt(self, patch_complete, monkeypatch):
        """The user prompt must contain the recent data block so the
        LLM has fresh context. Pin so a refactor that drops the
        summary or builds the prompt without it doesn't silently
        produce stale memory."""

        async def fake_summary(_user_id, _tz=None):
            return "## SENTINEL DATA\nproject X dominated"

        monkeypatch.setattr(memory_rewrite_module, "_recent_data_summary", fake_summary)

        factory, captured = patch_complete
        await factory()
        await memory_rewrite_module.rewrite_coach_memory("user-1")

        # The prompt that went to build_coach_messages includes the
        # sentinel + the rewrite directive.
        sent_messages = captured["kwargs"]["messages"]
        prompt_text = sent_messages[0]["content"]
        assert "## SENTINEL DATA" in prompt_text
        assert "project X dominated" in prompt_text

    async def test_overwrites_existing_memory_via_history(self, patch_complete):
        """Second rewrite shouldn't lose the first — MemoryStore's
        $push history machinery survives. The current memory after
        rewrite #2 is the new content; the previous (rewrite #1's
        output) lives in history. Locks the read-old-write-new flow
        end-to-end (chat.py never re-reads memory between rewrites,
        but a future "see what coach used to think" feature would)."""
        factory, _ = patch_complete

        await factory("# v1 memory")
        await memory_rewrite_module.rewrite_coach_memory("user-1")

        await factory("# v2 memory")
        await memory_rewrite_module.rewrite_coach_memory("user-1")

        client, db = _async_db()
        try:
            doc = await db[COACH_MEMORY_COLLECTION].find_one({"user_id": "user-1"})
            assert doc is not None
            assert doc["content"] == "# v2 memory"
            history = doc.get("history", [])
            # Two rewrites → two history entries (one with the
            # empty pre-state, one with v1).
            assert len(history) == 2
            assert [h["content"] for h in history] == ["", "# v1 memory"]
        finally:
            await client.close()

    async def test_isolates_users(self, patch_complete):
        """A rewrite for user A doesn't touch user B's memory."""
        factory, _ = patch_complete

        await factory("# A's memory")
        await memory_rewrite_module.rewrite_coach_memory("user-a")

        client, db = _async_db()
        try:
            store_a = MemoryStore(db, "user-a")
            store_b = MemoryStore(db, "user-b")
            assert await store_a.read() == "# A's memory"
            assert await store_b.read() is None
        finally:
            await client.close()


# Tool dispatch test scaffolding
