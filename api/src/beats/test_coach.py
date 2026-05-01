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

import json
import os
from datetime import UTC, date, datetime, timedelta

import pytest
from motor.motor_asyncio import AsyncIOMotorClient

from beats.coach import brief as brief_module
from beats.coach import chat as chat_module
from beats.coach import context as context_module
from beats.coach import memory_rewrite as memory_rewrite_module
from beats.coach import review as review_module
from beats.coach import tools as tools_module
from beats.coach.gateway import (
    SONNET_CACHE_READ_PER_MTOK,
    SONNET_CACHE_WRITE_PER_MTOK,
    SONNET_INPUT_COST_PER_MTOK,
    SONNET_OUTPUT_COST_PER_MTOK,
    CacheSpec,
    GatewayResponse,
    _apply_cache_control,
    _estimate_cost,
)
from beats.coach.memory import MemoryStore
from beats.coach.repos import (
    COACH_CONVERSATIONS_COLLECTION,
    COACH_MEMORY_COLLECTION,
    DAILY_BRIEFS_COLLECTION,
    LLM_USAGE_COLLECTION,
    REVIEW_ANSWERS_COLLECTION,
    fmt_minutes,
)
from beats.coach.usage import BudgetExceeded, UsageTracker
from beats.infrastructure.database import Database


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


class TestUsageTracker:
    """UsageTracker is the per-user LLM budget gate. Each Anthropic call
    records a row; enforce_budget sums the current month and raises
    BudgetExceeded if the cap is hit. Miscounting or mis-thresholding
    here means either silent overspend or unexpected 429s mid-session,
    both bad — these tests pin the math and the threshold semantics.

    UsageTracker uses Database.get_db() (the singleton). The class-
    scoped fixture connects the singleton to the testcontainer Mongo
    so the existing conftest pattern (sync pymongo) doesn't need to
    know about it.
    """

    @pytest.fixture(autouse=True)
    async def _setup(self):
        # Connect Database to the testcontainer's Mongo. The conftest
        # sets DB_DSN/DB_NAME; Database.connect() reads those by
        # default via beats.settings.
        await Database.connect()
        # Wipe any prior usage rows so each test starts deterministic.
        await Database.get_db()[LLM_USAGE_COLLECTION].delete_many({})
        yield
        await Database.disconnect()

    async def _record(
        self,
        tracker: UsageTracker,
        cost: float,
        *,
        purpose: str = "chat",
        ts_offset_days: int = 0,
    ) -> None:
        """Record a usage row with explicit cost; offset_days lets a
        test seed history outside the current month."""
        if ts_offset_days == 0:
            await tracker.record(
                model="claude-opus-4-7",
                input_tokens=1000,
                output_tokens=500,
                cache_creation=0,
                cache_read=0,
                cost_usd=cost,
                purpose=purpose,
            )
        else:
            # Backdate via direct insert (record() always uses now()).
            ts = datetime.now(UTC) + timedelta(days=ts_offset_days)
            await Database.get_db()[LLM_USAGE_COLLECTION].insert_one(
                {
                    "user_id": tracker._user_id,
                    "model": "claude-opus-4-7",
                    "input_tokens": 1000,
                    "output_tokens": 500,
                    "cache_creation_input_tokens": 0,
                    "cache_read_input_tokens": 0,
                    "cost_usd": cost,
                    "purpose": purpose,
                    "ts": ts,
                }
            )

    async def test_month_spend_zero_for_no_records(self):
        tracker = UsageTracker("user-fresh")
        assert await tracker.month_spend() == 0.0

    async def test_record_then_month_spend_sums(self):
        tracker = UsageTracker("user-1")
        await self._record(tracker, 1.50)
        await self._record(tracker, 2.75)
        await self._record(tracker, 0.25)
        # Float compare with tolerance — Mongo's $sum is exact for
        # values this small but Python float arithmetic on the
        # comparison side may differ in the last bit.
        assert abs(await tracker.month_spend() - 4.50) < 1e-9

    async def test_month_spend_only_includes_current_month(self):
        """A row from last month must not count toward this month's
        budget. Pin the $gte month_start filter — without it, the
        budget would never reset on the 1st."""
        tracker = UsageTracker("user-1")
        # Last month
        await self._record(tracker, 100.0, ts_offset_days=-45)
        # This month
        await self._record(tracker, 1.50)
        spent = await tracker.month_spend()
        assert abs(spent - 1.50) < 1e-9
        assert spent < 100.0  # last-month row was NOT counted

    async def test_month_spend_isolates_users(self):
        """Per-user filter must work — UserA's spend doesn't bleed
        into UserB's enforce_budget."""
        a = UsageTracker("user-a")
        b = UsageTracker("user-b")
        await self._record(a, 5.00)
        await self._record(b, 1.00)
        assert abs(await a.month_spend() - 5.00) < 1e-9
        assert abs(await b.month_spend() - 1.00) < 1e-9

    async def test_enforce_budget_under_limit_does_not_raise(self, monkeypatch):
        """Below the cap → no exception, no 429 to the user."""
        from beats import settings as settings_module

        monkeypatch.setattr(settings_module.settings, "coach_monthly_budget_usd", 10.0)
        tracker = UsageTracker("user-1")
        await self._record(tracker, 5.00)
        # Should not raise.
        await tracker.enforce_budget()

    async def test_enforce_budget_at_or_over_limit_raises(self, monkeypatch):
        """Threshold is `>=`, not strict `>`. A user who's spent
        exactly the cap is over for budgeting purposes — locks the
        boundary so a future refactor doesn't subtly let users go
        $0.01 past the cap before getting blocked."""
        from beats import settings as settings_module

        monkeypatch.setattr(settings_module.settings, "coach_monthly_budget_usd", 10.0)
        tracker = UsageTracker("user-1")
        await self._record(tracker, 10.0)
        with pytest.raises(BudgetExceeded) as exc_info:
            await tracker.enforce_budget()
        # Exception carries spent + limit so the API can surface them.
        assert abs(exc_info.value.spent - 10.0) < 1e-9
        assert exc_info.value.limit == 10.0

    async def test_enforce_budget_disabled_when_limit_is_zero(self, monkeypatch):
        """A zero/negative limit means budget enforcement is off — a
        deliberate "no cap" deploy mode. Pin so the BudgetExceeded
        path doesn't fire spuriously on a self-host that hasn't
        configured the cap."""
        from beats import settings as settings_module

        monkeypatch.setattr(settings_module.settings, "coach_monthly_budget_usd", 0.0)
        tracker = UsageTracker("user-1")
        await self._record(tracker, 99999.0)  # absurd spend
        # Must not raise.
        await tracker.enforce_budget()

    async def test_usage_summary_groups_by_day_and_sorts_ascending(self):
        """The /api/coach/usage cost dashboard renders these rows.
        Pin: one row per local-day, summed cost / tokens / calls,
        sorted oldest → newest."""
        tracker = UsageTracker("user-1")
        # Today
        await self._record(tracker, 1.00)
        await self._record(tracker, 2.00)
        # Yesterday
        await self._record(tracker, 0.50, ts_offset_days=-1)

        summary = await tracker.usage_summary(days=30)
        assert len(summary) == 2

        # Sorted ascending by date (the _id field).
        assert summary[0]["_id"] < summary[1]["_id"]

        # Today's totals (the second row by sort).
        today_row = summary[1]
        assert abs(today_row["cost_usd"] - 3.00) < 1e-9
        assert today_row["calls"] == 2

        # Yesterday's row sums correctly.
        yesterday_row = summary[0]
        assert abs(yesterday_row["cost_usd"] - 0.50) < 1e-9
        assert yesterday_row["calls"] == 1

    async def test_record_persists_all_fields(self):
        """Locks the document shape — the cost dashboard's $sum
        aggregations + the per-purpose filter rely on these field
        names. A refactor that renames `cost_usd` → `cost` would
        silently zero out the dashboard."""
        tracker = UsageTracker("user-1")
        await tracker.record(
            model="claude-opus-4-7",
            input_tokens=1234,
            output_tokens=567,
            cache_creation=100,
            cache_read=50,
            cost_usd=1.23,
            purpose="brief",
        )
        doc = await Database.get_db()[LLM_USAGE_COLLECTION].find_one({"user_id": "user-1"})
        assert doc is not None
        assert doc["model"] == "claude-opus-4-7"
        assert doc["input_tokens"] == 1234
        assert doc["output_tokens"] == 567
        assert doc["cache_creation_input_tokens"] == 100
        assert doc["cache_read_input_tokens"] == 50
        assert doc["cost_usd"] == 1.23
        assert doc["purpose"] == "brief"
        assert "ts" in doc


class _FakeTextBlock:
    """Stand-in for anthropic.types.TextBlock — brief.py extracts
    `.text` from each TextBlock instance via isinstance() so the
    fake must subclass the real type."""

    def __new__(cls, text: str):
        from anthropic.types import TextBlock

        # Use the real Pydantic constructor so isinstance(block, TextBlock)
        # in brief.py returns True.
        return TextBlock(type="text", text=text, citations=None)


def _fake_gateway_response(text: str = "Good morning. Two intentions today.") -> GatewayResponse:
    """Build a GatewayResponse the way `complete()` would — content is
    a list of TextBlocks, model + token + cost fields populated."""
    return GatewayResponse(
        content=[_FakeTextBlock(text)],
        model="claude-opus-4-7",
        input_tokens=1234,
        output_tokens=89,
        cache_creation_input_tokens=400,
        cache_read_input_tokens=800,
        cost_usd=0.012,
        stop_reason="end_turn",
    )


class TestGenerateBrief:
    """generate_brief composes context + calls the gateway + persists.
    Mocks build_coach_messages (the heavy upstream) and complete()
    (the LLM call). Pins what gets stored in daily_briefs and what
    the gateway is called with."""

    @pytest.fixture(autouse=True)
    async def _setup(self):
        await Database.connect()
        await Database.get_db()[DAILY_BRIEFS_COLLECTION].delete_many({})
        yield
        await Database.disconnect()

    @pytest.fixture
    def patched_gateway(self, monkeypatch):
        """Replace build_coach_messages and complete with deterministic
        fakes; capture the args the gateway was called with so tests
        can assert on prompt shape."""
        captured: dict = {}

        async def fake_build(user_id, prompt, target_date=None):
            captured["build_args"] = {
                "user_id": user_id,
                "prompt": prompt,
                "target_date": target_date,
            }
            return ("system text", [{"role": "user", "content": prompt}], None)

        async def fake_complete(**kwargs):
            captured["complete_kwargs"] = kwargs
            return _fake_gateway_response()

        monkeypatch.setattr(brief_module, "build_coach_messages", fake_build)
        monkeypatch.setattr(brief_module, "complete", fake_complete)
        return captured

    async def test_persists_brief_with_full_shape(self, patched_gateway):
        from datetime import date as date_type

        target = date_type(2026, 5, 1)
        doc = await brief_module.generate_brief("user-1", target_date=target)

        # Returned doc has all the fields the API exposes.
        assert doc["user_id"] == "user-1"
        assert doc["date"] == "2026-05-01"
        assert doc["body"] == "Good morning. Two intentions today."
        assert doc["model"] == "claude-opus-4-7"
        assert doc["cost_usd"] == 0.012
        assert doc["input_tokens"] == 1234
        assert doc["output_tokens"] == 89
        assert doc["cache_read"] == 800
        assert "created_at" in doc

        # Persisted to Mongo with the same shape.
        stored = await Database.get_db()[DAILY_BRIEFS_COLLECTION].find_one(
            {"user_id": "user-1", "date": "2026-05-01"}
        )
        assert stored is not None
        assert stored["body"] == "Good morning. Two intentions today."

    async def test_defaults_to_today_when_target_date_omitted(self, patched_gateway):
        await brief_module.generate_brief("user-1")
        today = datetime.now(UTC).date().isoformat()
        # build_coach_messages received today via target_date.
        assert patched_gateway["build_args"]["target_date"].isoformat() == today
        # And the persisted row's date is today.
        stored = await Database.get_db()[DAILY_BRIEFS_COLLECTION].find_one(
            {"user_id": "user-1", "date": today}
        )
        assert stored is not None

    async def test_passes_purpose_brief_to_gateway(self, patched_gateway):
        """Locks the purpose tag so per-purpose usage breakdowns
        keep separating brief from chat. Renaming this would skew
        the cost dashboard."""
        await brief_module.generate_brief("user-1")
        assert patched_gateway["complete_kwargs"]["purpose"] == "brief"

    async def test_passes_user_id_to_gateway(self, patched_gateway):
        """Without this, UsageTracker would count the brief against
        the wrong user."""
        await brief_module.generate_brief("user-99")
        assert patched_gateway["complete_kwargs"]["user_id"] == "user-99"

    async def test_concatenates_multiple_text_blocks(self, monkeypatch):
        """The LLM can return multiple TextBlocks (one per output
        chunk). brief.py concatenates and strips. Pin so a refactor
        that grabs only `content[0].text` doesn't truncate briefs."""

        async def fake_build(user_id, prompt, target_date=None):
            return ("sys", [], None)

        async def fake_complete(**_kwargs):
            return GatewayResponse(
                content=[
                    _FakeTextBlock("First sentence. "),
                    _FakeTextBlock("Second sentence."),
                ],
                model="claude-opus-4-7",
                input_tokens=10,
                output_tokens=20,
                cache_creation_input_tokens=0,
                cache_read_input_tokens=0,
                cost_usd=0.001,
                stop_reason="end_turn",
            )

        monkeypatch.setattr(brief_module, "build_coach_messages", fake_build)
        monkeypatch.setattr(brief_module, "complete", fake_complete)

        doc = await brief_module.generate_brief("user-1")
        assert doc["body"] == "First sentence. Second sentence."

    async def test_upserts_on_user_and_date(self, patched_gateway):
        """Generating a brief twice for the same date overwrites
        rather than duplicating. Locks the upsert filter — without
        it, get_brief() would non-deterministically return one of
        many rows."""
        from datetime import date as date_type

        target = date_type(2026, 5, 1)
        await brief_module.generate_brief("user-1", target_date=target)
        await brief_module.generate_brief("user-1", target_date=target)

        count = await Database.get_db()[DAILY_BRIEFS_COLLECTION].count_documents(
            {"user_id": "user-1", "date": "2026-05-01"}
        )
        assert count == 1


class TestGetAndListBriefs:
    """The read paths used by /api/coach/brief/today and
    /api/coach/brief/history. Pin: empty result for fresh users,
    descending-by-date for list, _id projection so the API doesn't
    leak ObjectIds."""

    @pytest.fixture(autouse=True)
    async def _setup(self):
        await Database.connect()
        await Database.get_db()[DAILY_BRIEFS_COLLECTION].delete_many({})
        yield
        await Database.disconnect()

    async def _seed_brief(self, user_id: str, date_str: str, body: str = "x") -> None:
        await Database.get_db()[DAILY_BRIEFS_COLLECTION].insert_one(
            {"user_id": user_id, "date": date_str, "body": body, "model": "x"}
        )

    async def test_get_brief_returns_none_when_missing(self):
        from datetime import date as date_type

        result = await brief_module.get_brief("user-1", target_date=date_type(2026, 5, 1))
        assert result is None

    async def test_get_brief_returns_doc_without_objectid(self):
        from datetime import date as date_type

        await self._seed_brief("user-1", "2026-05-01", "today's brief")
        result = await brief_module.get_brief("user-1", target_date=date_type(2026, 5, 1))
        assert result is not None
        assert result["body"] == "today's brief"
        # ObjectId stripped via the {"_id": 0} projection — important
        # because API responses don't serialize ObjectIds.
        assert "_id" not in result

    async def test_list_briefs_empty_for_fresh_user(self):
        result = await brief_module.list_briefs("user-1")
        assert result == []

    async def test_list_briefs_descending_by_date(self):
        await self._seed_brief("user-1", "2026-04-29", "older")
        await self._seed_brief("user-1", "2026-05-01", "newer")
        await self._seed_brief("user-1", "2026-04-30", "middle")

        result = await brief_module.list_briefs("user-1")
        # Newest first — important because the UI's "history" list
        # renders top-down.
        assert [b["date"] for b in result] == ["2026-05-01", "2026-04-30", "2026-04-29"]

    async def test_list_briefs_respects_limit(self):
        for d in ["2026-04-25", "2026-04-26", "2026-04-27", "2026-04-28", "2026-04-29"]:
            await self._seed_brief("user-1", d)

        result = await brief_module.list_briefs("user-1", limit=3)
        assert len(result) == 3
        # Most recent 3 (sort then truncate, not vice versa).
        assert [b["date"] for b in result] == ["2026-04-29", "2026-04-28", "2026-04-27"]

    async def test_list_briefs_isolates_users(self):
        await self._seed_brief("user-a", "2026-05-01", "A's brief")
        await self._seed_brief("user-b", "2026-05-01", "B's brief")

        a_briefs = await brief_module.list_briefs("user-a")
        assert len(a_briefs) == 1
        assert a_briefs[0]["body"] == "A's brief"


def _gateway_response_from_text(text: str) -> GatewayResponse:
    """Builds a GatewayResponse whose content[0] is the given text. Used
    by review tests to drive different LLM-output shapes through
    generate_review_questions's parser."""
    return GatewayResponse(
        content=[_FakeTextBlock(text)],
        model="claude-opus-4-7",
        input_tokens=100,
        output_tokens=50,
        cache_creation_input_tokens=0,
        cache_read_input_tokens=0,
        cost_usd=0.001,
        stop_reason="end_turn",
    )


class TestGenerateReviewQuestions:
    """generate_review_questions calls the LLM, parses JSON, persists.
    Pin: parse-success path persists what the LLM returned;
    parse-failure path falls back to 3 generic questions (so the EOD
    review never breaks the user's flow); upsert preserves prior
    answers when re-generating."""

    @pytest.fixture(autouse=True)
    async def _setup(self):
        await Database.connect()
        await Database.get_db()[REVIEW_ANSWERS_COLLECTION].delete_many({})
        yield
        await Database.disconnect()

    @pytest.fixture
    def patched_gateway(self, monkeypatch):
        captured: dict = {}

        async def fake_build(user_id, prompt, target_date=None):
            captured["build_args"] = {
                "user_id": user_id,
                "prompt": prompt,
                "target_date": target_date,
            }
            return ("system", [{"role": "user", "content": prompt}], None)

        monkeypatch.setattr(review_module, "build_coach_messages", fake_build)
        return captured

    async def test_parses_valid_json_array(self, monkeypatch, patched_gateway):
        """Happy path: LLM returns a JSON array of question dicts;
        each persists verbatim."""
        questions_json = json.dumps(
            [
                {"question": "Did the auth refactor land?", "derived_from": {"kind": "intention"}},
                {"question": "Why did the meeting overrun?", "derived_from": {"kind": "calendar"}},
                {
                    "question": "Mood is lower than last week — why?",
                    "derived_from": {"kind": "mood"},
                },
            ]
        )

        async def fake_complete(**_kwargs):
            return _gateway_response_from_text(questions_json)

        monkeypatch.setattr(review_module, "complete", fake_complete)

        from datetime import date as date_type

        result = await review_module.generate_review_questions(
            "user-1", target_date=date_type(2026, 5, 1)
        )

        assert len(result) == 3
        assert result[0]["question"] == "Did the auth refactor land?"
        assert result[2]["derived_from"]["kind"] == "mood"

        # And the persisted doc carries the same questions.
        stored = await Database.get_db()[REVIEW_ANSWERS_COLLECTION].find_one(
            {"user_id": "user-1", "date": "2026-05-01"}
        )
        assert stored is not None
        assert len(stored["questions"]) == 3
        assert stored["answers"] == [None, None, None]
        assert "created_at" in stored
        assert "updated_at" in stored

    async def test_falls_back_when_llm_returns_garbage(self, monkeypatch, patched_gateway):
        """If the LLM returns invalid JSON (model temperature spike,
        prompt drift, anything), the user must still get a usable
        review form. Pin the fallback — three generic questions
        rather than a 500 or empty list."""

        async def fake_complete(**_kwargs):
            return _gateway_response_from_text("here are some questions: 1) why...")

        monkeypatch.setattr(review_module, "complete", fake_complete)

        result = await review_module.generate_review_questions("user-1")
        assert len(result) == 3
        # All fallback questions tagged so callers can tell the
        # difference between AI-generated and stock prompts.
        assert all(q["derived_from"]["kind"] == "fallback" for q in result)
        # They're real strings, not empty placeholders.
        assert all(q["question"] for q in result)

    async def test_falls_back_when_llm_returns_non_array_json(self, monkeypatch, patched_gateway):
        """Valid JSON but wrong shape (e.g. dict instead of list) →
        same fallback. Pin so a future prompt change that produces
        valid-but-wrong-shape output doesn't crash."""

        async def fake_complete(**_kwargs):
            return _gateway_response_from_text(json.dumps({"questions": []}))

        monkeypatch.setattr(review_module, "complete", fake_complete)

        result = await review_module.generate_review_questions("user-1")
        assert len(result) == 3
        assert all(q["derived_from"]["kind"] == "fallback" for q in result)

    async def test_passes_purpose_review_to_gateway(self, monkeypatch, patched_gateway):
        """purpose="review" tag separates review LLM spend from chat
        and brief in the cost dashboard's per-purpose breakdown."""
        captured = {}

        async def fake_complete(**kwargs):
            captured.update(kwargs)
            return _gateway_response_from_text(json.dumps([]))

        monkeypatch.setattr(review_module, "complete", fake_complete)

        await review_module.generate_review_questions("user-99")
        assert captured["purpose"] == "review"
        assert captured["user_id"] == "user-99"

    async def test_upsert_preserves_answers_on_regenerate(self, monkeypatch, patched_gateway):
        """Locks $setOnInsert vs $set: a regenerate replaces questions
        but does NOT reset answers. Without this, a user who answered
        Q1 then triggered a regenerate would lose their progress."""
        from datetime import date as date_type

        target = date_type(2026, 5, 1)

        async def fake_first(**_kwargs):
            return _gateway_response_from_text(
                json.dumps([{"question": "v1-q1", "derived_from": {"kind": "x"}}])
            )

        monkeypatch.setattr(review_module, "complete", fake_first)
        await review_module.generate_review_questions("user-1", target_date=target)

        # User answers Q1.
        await review_module.save_answer("user-1", target, 0, "answered")

        # Regenerate — different questions.
        async def fake_second(**_kwargs):
            return _gateway_response_from_text(
                json.dumps([{"question": "v2-q1", "derived_from": {"kind": "y"}}])
            )

        monkeypatch.setattr(review_module, "complete", fake_second)
        await review_module.generate_review_questions("user-1", target_date=target)

        stored = await Database.get_db()[REVIEW_ANSWERS_COLLECTION].find_one(
            {"user_id": "user-1", "date": "2026-05-01"}
        )
        assert stored is not None
        assert stored["questions"][0]["question"] == "v2-q1"
        # Answer survived the regenerate (the $set updates questions
        # but $setOnInsert wouldn't re-write answers).
        assert stored["answers"][0]["text"] == "answered"


class TestSaveAnswerAndReadbacks:
    """save_answer is the per-question persist path the EOD modal
    calls; get_review / list_reviews are the read paths the API
    exposes. Pin atomicity, indexing, and the empty-state shapes."""

    @pytest.fixture(autouse=True)
    async def _setup(self):
        await Database.connect()
        await Database.get_db()[REVIEW_ANSWERS_COLLECTION].delete_many({})
        yield
        await Database.disconnect()

    async def _seed_review(self, user_id: str, date_str: str, n_questions: int = 3) -> None:
        await Database.get_db()[REVIEW_ANSWERS_COLLECTION].insert_one(
            {
                "user_id": user_id,
                "date": date_str,
                "questions": [{"question": f"Q{i}"} for i in range(n_questions)],
                "answers": [None] * n_questions,
            }
        )

    async def test_save_answer_writes_to_specific_index(self):
        """Locks the $set on `answers.{i}` — atomically writes one
        slot without touching the others. A user who has Q0 and Q2
        answered must still see Q0 and Q2 after a Q1 update."""
        from datetime import date as date_type

        target = date_type(2026, 5, 1)
        await self._seed_review("user-1", "2026-05-01")
        await review_module.save_answer("user-1", target, 0, "first answer")
        await review_module.save_answer("user-1", target, 2, "third answer")

        stored = await Database.get_db()[REVIEW_ANSWERS_COLLECTION].find_one(
            {"user_id": "user-1", "date": "2026-05-01"}
        )
        assert stored is not None
        assert stored["answers"][0]["text"] == "first answer"
        assert stored["answers"][1] is None  # untouched
        assert stored["answers"][2]["text"] == "third answer"
        # Each answered slot carries an answered_at timestamp.
        assert "answered_at" in stored["answers"][0]

    async def test_save_answer_overwrites_same_index(self):
        """Re-answering Q0 replaces, doesn't append. Pin so a refactor
        to $push doesn't accumulate answers per slot."""
        from datetime import date as date_type

        target = date_type(2026, 5, 1)
        await self._seed_review("user-1", "2026-05-01")
        await review_module.save_answer("user-1", target, 0, "first")
        await review_module.save_answer("user-1", target, 0, "revised")

        stored = await Database.get_db()[REVIEW_ANSWERS_COLLECTION].find_one(
            {"user_id": "user-1", "date": "2026-05-01"}
        )
        assert stored is not None
        assert stored["answers"][0]["text"] == "revised"

    async def test_get_review_returns_none_for_missing(self):
        from datetime import date as date_type

        result = await review_module.get_review("user-1", target_date=date_type(2026, 5, 1))
        assert result is None

    async def test_get_review_strips_objectid(self):
        from datetime import date as date_type

        await self._seed_review("user-1", "2026-05-01")
        result = await review_module.get_review("user-1", target_date=date_type(2026, 5, 1))
        assert result is not None
        assert "_id" not in result

    async def test_list_reviews_descending_by_date(self):
        await self._seed_review("user-1", "2026-04-29")
        await self._seed_review("user-1", "2026-05-01")
        await self._seed_review("user-1", "2026-04-30")

        result = await review_module.list_reviews("user-1")
        assert [r["date"] for r in result] == ["2026-05-01", "2026-04-30", "2026-04-29"]

    async def test_list_reviews_isolates_users(self):
        await self._seed_review("user-a", "2026-05-01")
        await self._seed_review("user-b", "2026-05-01")

        a = await review_module.list_reviews("user-a")
        assert len(a) == 1
        # The seeded shape distinguishes via the user_id (which is in
        # the doc) — we just verify count to confirm the user_id
        # filter excluded user-b's row.


class TestEstimateCost:
    """The deterministic cost math the gateway uses to bill users.
    Wrong here = wrong dashboard + wrong budget enforcement.

    The model: cost = base_input·rate + output·rate +
    cache_creation·write_rate + cache_read·read_rate, where
    base_input = total_input − cache_creation − cache_read.
    """

    def test_zero_tokens_zero_cost(self):
        assert _estimate_cost(0, 0, 0, 0) == 0.0

    def test_pure_input_no_cache_uses_input_rate(self):
        # 1M input tokens, no output, no cache → 1 × $3 = $3
        assert _estimate_cost(1_000_000, 0, 0, 0) == 3.0

    def test_pure_output_uses_output_rate(self):
        # 1M output tokens → 1 × $15 = $15
        assert _estimate_cost(0, 1_000_000, 0, 0) == 15.0

    def test_input_minus_cache_is_billed_at_input_rate(self):
        """If 1M input tokens were ALL cache reads, only the cache-read
        rate applies — the "base input" billed at $3/Mtok is zero.
        Locks the subtraction at line 64; without it a refactor that
        bills cache_read AS input would charge $3 + $0.30 instead of
        just $0.30 — a 10× over-bill on heavy-cache calls."""
        # 1M cache reads, no other input
        cost = _estimate_cost(1_000_000, 0, 0, 1_000_000)
        # base_input = 1M - 0 - 1M = 0, so only the cache-read rate.
        assert cost == pytest.approx(0.30, rel=1e-9)

    def test_input_minus_cache_with_cache_creation(self):
        """Same logic for cache writes — they're a separate line item."""
        cost = _estimate_cost(1_000_000, 0, 1_000_000, 0)
        # base_input = 0, cache_creation = 1M × $3.75 = $3.75
        assert cost == pytest.approx(3.75, rel=1e-9)

    def test_mixed_realistic_call(self):
        """A realistic chat turn: 5K input including 2K cache-read
        (system prompt) + 1K cache-creation (turn boundary) + 1K
        output. Computes the line-by-line bill so a refactor that
        merges any of the rates is caught."""
        cost = _estimate_cost(
            input_tokens=5_000,
            output_tokens=1_000,
            cache_creation=1_000,
            cache_read=2_000,
        )
        # base_input = 5000 - 1000 - 2000 = 2000
        # 2000 * 3 / 1M + 1000 * 15 / 1M + 1000 * 3.75 / 1M + 2000 * 0.30 / 1M
        expected = (
            2000 * SONNET_INPUT_COST_PER_MTOK / 1_000_000
            + 1000 * SONNET_OUTPUT_COST_PER_MTOK / 1_000_000
            + 1000 * SONNET_CACHE_WRITE_PER_MTOK / 1_000_000
            + 2000 * SONNET_CACHE_READ_PER_MTOK / 1_000_000
        )
        assert cost == pytest.approx(expected, rel=1e-9)

    def test_negative_base_input_clamps_to_zero(self):
        """If reported cache_creation+cache_read exceeds total input
        (Anthropic API quirk on certain edge cases), base_input
        clamps at 0 — we never bill negative dollars. Without this
        guard, a 10K cache_read against 9K input_tokens would
        produce a negative input charge that subtracts from the
        bill — under-collecting in a way the dashboard wouldn't
        catch."""
        cost = _estimate_cost(
            input_tokens=9_000,
            output_tokens=0,
            cache_creation=0,
            cache_read=10_000,  # exceeds input
        )
        # max(0, 9000 - 0 - 10000) = 0, so just cache_read at $0.30/M
        expected = 10_000 * SONNET_CACHE_READ_PER_MTOK / 1_000_000
        assert cost == pytest.approx(expected, rel=1e-9)


class TestApplyCacheControl:
    """_apply_cache_control injects cache_control={"type": "ephemeral"}
    breakpoints per the CacheSpec. Wrong placement = silently higher
    coach spend (cache misses) or breaking the request format. Pin
    every shape combination."""

    def test_string_system_becomes_block_with_cache_marker(self):
        """The default CacheSpec marks the system prompt as cached.
        Locks the conversion: str -> [{type, text, cache_control}]."""
        spec = CacheSpec(system_cached=True, cached_turn_indices=[])
        sys_blocks, msgs = _apply_cache_control("you are a coach", [], spec)

        assert len(sys_blocks) == 1
        assert sys_blocks[0]["type"] == "text"
        assert sys_blocks[0]["text"] == "you are a coach"
        assert sys_blocks[0]["cache_control"] == {"type": "ephemeral"}
        assert msgs == []

    def test_system_cached_false_skips_cache_marker(self):
        """A caller that opts out of system caching (e.g. a one-off
        non-cacheable system prompt) gets back the converted blocks
        WITHOUT cache_control. Pin the off-path so a future default
        flip doesn't silently start charging cache writes for
        opt-out callers."""
        spec = CacheSpec(system_cached=False, cached_turn_indices=[])
        sys_blocks, _ = _apply_cache_control("you are a coach", [], spec)

        assert len(sys_blocks) == 1
        assert "cache_control" not in sys_blocks[0]

    def test_list_system_marks_only_last_block(self):
        """If the caller passes pre-built system blocks, only the LAST
        one gets the cache marker. This is by design — Anthropic's
        prompt-caching uses the last cached block as the read pointer,
        so multi-block systems should mark just the final boundary."""
        spec = CacheSpec(system_cached=True, cached_turn_indices=[])
        system_in = [
            {"type": "text", "text": "first"},
            {"type": "text", "text": "second"},
        ]
        sys_blocks, _ = _apply_cache_control(system_in, [], spec)
        assert len(sys_blocks) == 2
        assert "cache_control" not in sys_blocks[0]
        assert sys_blocks[1]["cache_control"] == {"type": "ephemeral"}

    def test_does_not_mutate_input_system_blocks(self):
        """The function must return new dicts — mutating caller-owned
        lists would surprise on a retry where the same `system` is
        passed in again."""
        spec = CacheSpec(system_cached=True, cached_turn_indices=[])
        system_in = [{"type": "text", "text": "first"}]
        _apply_cache_control(system_in, [], spec)
        assert "cache_control" not in system_in[0]

    def test_string_message_at_cached_index_gets_block_form(self):
        """A bare-string message content at a cached index gets
        converted into the block form so cache_control can attach
        to it. Locks the shape Anthropic's API expects."""
        spec = CacheSpec(system_cached=False, cached_turn_indices=[0])
        msgs_in = [{"role": "user", "content": "hello"}]
        _, msgs_out = _apply_cache_control("sys", msgs_in, spec)

        assert msgs_out[0]["content"] == [
            {"type": "text", "text": "hello", "cache_control": {"type": "ephemeral"}}
        ]

    def test_list_message_marks_last_content_block(self):
        """Same single-cache-marker rule as system: when the message
        content is already a list of blocks, mark only the last."""
        spec = CacheSpec(system_cached=False, cached_turn_indices=[0])
        msgs_in = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "first"},
                    {"type": "text", "text": "second"},
                ],
            }
        ]
        _, msgs_out = _apply_cache_control("sys", msgs_in, spec)
        content = msgs_out[0]["content"]
        assert "cache_control" not in content[0]
        assert content[1]["cache_control"] == {"type": "ephemeral"}

    def test_only_indexed_turns_get_cached(self):
        """Indices outside cached_turn_indices stay unmarked. Pin
        so a refactor that broadens the cache to all turns (=
        unsupported by the API + every turn pays write cost)
        breaks the test."""
        spec = CacheSpec(system_cached=False, cached_turn_indices=[0])
        msgs_in = [
            {"role": "user", "content": "first"},
            {"role": "assistant", "content": "ack"},
            {"role": "user", "content": "third"},
        ]
        _, msgs_out = _apply_cache_control("sys", msgs_in, spec)
        # First turn cached.
        assert msgs_out[0]["content"][0]["cache_control"] == {"type": "ephemeral"}
        # Other turns left as bare strings.
        assert msgs_out[1]["content"] == "ack"
        assert msgs_out[2]["content"] == "third"

    def test_out_of_range_index_is_ignored(self):
        """A spec referring to an index past the message list is a
        no-op (rather than IndexError). Defensive — if the caller
        builds the spec from stale assumptions about message count,
        we don't 500."""
        spec = CacheSpec(system_cached=False, cached_turn_indices=[5])
        msgs_in = [{"role": "user", "content": "only one"}]
        _, msgs_out = _apply_cache_control("sys", msgs_in, spec)
        # Untouched; still a bare string.
        assert msgs_out[0]["content"] == "only one"

    def test_does_not_mutate_input_messages(self):
        """Same defensive copy guarantee as system blocks — important
        for retries where the same messages list is passed in twice."""
        spec = CacheSpec(system_cached=False, cached_turn_indices=[0])
        msgs_in = [{"role": "user", "content": "hello"}]
        _apply_cache_control("sys", msgs_in, spec)
        # Caller's input is still a bare-string content.
        assert msgs_in[0]["content"] == "hello"

    def test_default_cache_spec_caches_system_only(self):
        """The CacheSpec() default — system_cached=True, no turns —
        is what brief.py and review.py use. Pin so a default change
        is deliberate."""
        spec = CacheSpec()
        sys_blocks, msgs = _apply_cache_control("sys", [{"role": "user", "content": "hi"}], spec)
        assert sys_blocks[0]["cache_control"] == {"type": "ephemeral"}
        # No turn cached.
        assert msgs[0]["content"] == "hi"


def _fake_tool_use(name: str, tool_input: dict, block_id: str = "tu_1"):
    """Build an anthropic.types.ToolUseBlock so isinstance() in chat.py
    narrows it correctly."""
    from anthropic.types import ToolUseBlock

    return ToolUseBlock(type="tool_use", id=block_id, name=name, input=tool_input)


def _resp(content_blocks, **overrides) -> GatewayResponse:
    """Wrap a list of content blocks into a GatewayResponse with
    sensible defaults for the fields chat.py doesn't read."""
    return GatewayResponse(
        content=content_blocks,
        model="claude-opus-4-7",
        input_tokens=overrides.get("input_tokens", 100),
        output_tokens=overrides.get("output_tokens", 50),
        cache_creation_input_tokens=0,
        cache_read_input_tokens=0,
        cost_usd=overrides.get("cost_usd", 0.001),
        stop_reason=overrides.get("stop_reason", "end_turn"),
    )


class _FakeRepos:
    """Stand-in for the CoachRepos dataclass — chat.py only calls
    `.project.list()` to seed the tool dispatch context."""

    class _ProjectRepo:
        async def list(self):
            return []

    project = _ProjectRepo()


class TestHandleChatTurn:
    """The streaming chat turn — runs an LLM round, optionally executes
    tools, optionally loops, and yields SSE events. Tested by replacing
    `complete()` with a sequence of canned GatewayResponses and
    `execute_tool` with a deterministic stub."""

    @pytest.fixture(autouse=True)
    async def _setup(self, monkeypatch):
        await Database.connect()
        await Database.get_db()[COACH_CONVERSATIONS_COLLECTION].delete_many({})

        # Replace the upstream context builder so we don't need to
        # seed a fake user with full beats/projects history.
        async def fake_build(user_id, message, history=None, **_):
            messages = list(history or [])
            messages.append({"role": "user", "content": message})
            return ("system", messages, None)

        monkeypatch.setattr(chat_module, "build_coach_messages", fake_build)

        # Stub build_repos so we don't hit the project repo for real.
        async def fake_build_repos(_user_id):
            return _FakeRepos()

        monkeypatch.setattr(chat_module, "build_repos", fake_build_repos)

        yield
        await Database.disconnect()

    @pytest.fixture
    def patch_complete(self, monkeypatch):
        """Returns a setter that lets a test queue a sequence of
        GatewayResponses; chat.py's tool-loop pulls one per round."""
        responses: list[GatewayResponse] = []
        captured_calls: list[dict] = []

        async def fake_complete(**kwargs):
            captured_calls.append(kwargs)
            if not responses:
                raise AssertionError("complete() called more times than expected")
            return responses.pop(0)

        monkeypatch.setattr(chat_module, "complete", fake_complete)
        return responses, captured_calls

    @pytest.fixture
    def patch_execute_tool(self, monkeypatch):
        """Records every tool call and returns a deterministic string."""
        calls: list[tuple] = []

        async def fake_execute(_user_id, name, tool_input, *, repos, projects):
            calls.append((name, tool_input))
            return f"<{name} result>"

        monkeypatch.setattr(chat_module, "execute_tool", fake_execute)
        return calls

    async def _drain(self, gen):
        events = []
        async for ev in gen:
            events.append(ev)
        return events

    async def test_text_only_response_emits_text_then_done(self, patch_complete):
        """Happy path with no tool use — single LLM round, single text
        block, terminates with the done event."""
        from anthropic.types import TextBlock

        responses, _calls = patch_complete
        responses.append(_resp([TextBlock(type="text", text="hello there", citations=None)]))

        events = await self._drain(
            chat_module.handle_chat_turn(user_id="user-1", message="hi", conversation_id="c-1")
        )

        assert events[0] == {"type": "text", "text": "hello there"}
        assert events[-1] == {"type": "done", "conversation_id": "c-1"}

    async def test_persists_user_and_assistant_messages(self, patch_complete):
        from anthropic.types import TextBlock

        responses, _ = patch_complete
        responses.append(_resp([TextBlock(type="text", text="reply", citations=None)]))

        await self._drain(
            chat_module.handle_chat_turn(user_id="user-1", message="hi", conversation_id="c-1")
        )

        rows = (
            await Database.get_db()[COACH_CONVERSATIONS_COLLECTION]
            .find({"conversation_id": "c-1"})
            .to_list(10)
        )
        roles = sorted([r["role"] for r in rows])
        # The user message and the assistant message both persist.
        assert roles == ["assistant", "user"]
        assistant = next(r for r in rows if r["role"] == "assistant")
        assert assistant["content"] == "reply"

    async def test_auto_generates_conversation_id_when_omitted(self, patch_complete):
        """Locks the conversation_id contract — caller can pass None
        and chat.py mints a uuid that flows through to the done event
        and to every persisted row."""
        from anthropic.types import TextBlock

        responses, _ = patch_complete
        responses.append(_resp([TextBlock(type="text", text="ok", citations=None)]))

        events = await self._drain(chat_module.handle_chat_turn(user_id="user-1", message="hi"))

        done = next(ev for ev in events if ev["type"] == "done")
        cid = done["conversation_id"]
        assert cid  # not empty
        # And the persisted user message carries the same id.
        row = await Database.get_db()[COACH_CONVERSATIONS_COLLECTION].find_one({"role": "user"})
        assert row is not None
        assert row["conversation_id"] == cid

    async def test_tool_use_round_then_text_round(self, patch_complete, patch_execute_tool):
        """Round 1: LLM emits tool_use → chat.py runs the tool, yields
        tool_use + tool_result events. Round 2: LLM emits text → done.
        Locks the loop's two-round happy path."""
        from anthropic.types import TextBlock

        responses, calls = patch_complete
        responses.append(
            _resp(
                [
                    TextBlock(type="text", text="let me check", citations=None),
                    _fake_tool_use("get_score", {}, "tu_1"),
                ]
            )
        )
        responses.append(_resp([TextBlock(type="text", text="your score is X", citations=None)]))

        events = await self._drain(
            chat_module.handle_chat_turn(
                user_id="user-1", message="how am I doing?", conversation_id="c-1"
            )
        )

        # Sequence: round 1 text, tool_use, tool_result, round 2 text, done.
        types = [ev["type"] for ev in events]
        assert types == ["text", "tool_use", "tool_result", "text", "done"]

        # Tool was actually invoked.
        assert patch_execute_tool == [("get_score", {})]

        # Round 2 received the tool_result in messages.
        assert len(calls) == 2
        round2_messages = calls[1]["messages"]
        # Last user-role message in round 2 carries the tool_result block.
        last = round2_messages[-1]
        assert last["role"] == "user"
        assert last["content"][0]["type"] == "tool_result"
        assert last["content"][0]["content"] == "<get_score result>"

    async def test_tool_execution_error_becomes_error_text(self, patch_complete, monkeypatch):
        """A tool that raises an exception must NOT 500 the chat
        stream — chat.py catches and surfaces "Error: ..." in the
        tool_result so the LLM can recover and the user sees the
        failure."""
        from anthropic.types import TextBlock

        async def failing_execute(*_args, **_kwargs):
            raise RuntimeError("tool blew up")

        monkeypatch.setattr(chat_module, "execute_tool", failing_execute)

        responses, _ = patch_complete
        responses.append(_resp([_fake_tool_use("get_score", {}, "tu_1")]))
        responses.append(
            _resp([TextBlock(type="text", text="couldn't fetch your score", citations=None)])
        )

        events = await self._drain(
            chat_module.handle_chat_turn(user_id="user-1", message="score?", conversation_id="c-1")
        )

        tool_result = next(ev for ev in events if ev["type"] == "tool_result")
        assert "Error: tool blew up" in tool_result["result"]

    async def test_tool_result_truncated_in_sse_event_only(self, patch_complete, monkeypatch):
        """The SSE event truncates the tool result to
        TOOL_RESULT_DISPLAY_LIMIT chars (so the UI doesn't render a
        novel), but the FULL text goes back to the LLM in the next
        round's messages. Pin both halves — without the LLM-side
        full-content guarantee, large tool outputs would silently
        get truncated mid-thought."""
        from anthropic.types import TextBlock

        big_payload = "x" * 5000  # well over the 500-char display cap

        async def big_execute(*_args, **_kwargs):
            return big_payload

        monkeypatch.setattr(chat_module, "execute_tool", big_execute)

        responses, calls = patch_complete
        responses.append(_resp([_fake_tool_use("search_beats", {}, "tu_1")]))
        responses.append(_resp([TextBlock(type="text", text="ok", citations=None)]))

        events = await self._drain(
            chat_module.handle_chat_turn(user_id="user-1", message="search", conversation_id="c-1")
        )

        # SSE event truncated to display limit.
        tool_result_event = next(ev for ev in events if ev["type"] == "tool_result")
        assert len(tool_result_event["result"]) == chat_module.TOOL_RESULT_DISPLAY_LIMIT

        # But the LLM message in round 2 has the FULL payload — locks
        # the contract that the LLM gets to see what really came back.
        round2_messages = calls[1]["messages"]
        last = round2_messages[-1]
        assert last["content"][0]["content"] == big_payload  # full size

    async def test_max_tool_turns_constant_value(self):
        """Locks the constant value at 8. Changing this is a pricing
        decision (each round = one full LLM call) so should be
        deliberate. Bumping from 5 (the previous inline cap) gives
        legitimate research-style turns headroom for a 4-5 tool
        chain plus a clarifying follow-up."""
        assert chat_module.MAX_TOOL_TURNS == 8

    async def test_tool_loop_exhaustion_emits_typed_error_event(
        self, patch_complete, patch_execute_tool
    ):
        """When the LLM can't produce text within MAX_TOOL_TURNS rounds,
        the handler emits a typed `error` event (NOT a faked text
        event) followed by `done`. Pin the event shape — the UI's
        error-branch handler reads `event.error` and renders it
        distinctly from a model-authored text turn. Without the typed
        event, a "the coach kept failing tool calls" outcome would
        look identical to a normal coach reply."""
        responses, _ = patch_complete

        # Queue MAX_TOOL_TURNS rounds of pure tool_use (no text), so
        # the loop never finds a non-tool response and falls through.
        for i in range(chat_module.MAX_TOOL_TURNS):
            responses.append(_resp([_fake_tool_use("get_score", {}, f"tu_{i}")]))

        events = await self._drain(
            chat_module.handle_chat_turn(user_id="user-1", message="loop", conversation_id="c-1")
        )

        # No text events should appear — we queued only tool_use.
        assert not any(ev["type"] == "text" for ev in events)

        # Final two events: typed error + done. Same shape the /chat
        # router uses for budget-exceeded so the UI's existing error
        # handler renders it without changes.
        error_events = [ev for ev in events if ev["type"] == "error"]
        assert len(error_events) == 1
        assert "tool-call limit" in error_events[0]["error"].lower()
        assert error_events[0]["code"] == 502
        assert events[-1] == {"type": "done", "conversation_id": "c-1"}

    async def test_loop_does_not_call_complete_more_than_max_turns(
        self, patch_complete, patch_execute_tool
    ):
        """Hard upper bound on LLM calls per chat turn. Pin so a
        future refactor that changes the loop structure can't
        accidentally let the cap leak."""
        responses, calls = patch_complete

        # Queue more responses than the cap; the loop must stop early.
        for i in range(chat_module.MAX_TOOL_TURNS + 5):
            responses.append(_resp([_fake_tool_use("get_score", {}, f"tu_{i}")]))

        await self._drain(
            chat_module.handle_chat_turn(user_id="user-1", message="loop", conversation_id="c-1")
        )

        # complete() called exactly MAX_TOOL_TURNS times — no more,
        # no fewer. Locks the per-turn LLM cost ceiling.
        assert len(calls) == chat_module.MAX_TOOL_TURNS

    async def test_history_is_loaded_in_chronological_order(self, patch_complete):
        """Messages persist with descending sort by created_at, but
        chat.py reverses to chronological for the LLM. Pin so a
        refactor that drops the reverse() doesn't feed the LLM
        history backwards."""
        from anthropic.types import TextBlock

        _td = timedelta
        now = datetime.now(UTC)
        await Database.get_db()[COACH_CONVERSATIONS_COLLECTION].insert_many(
            [
                {
                    "user_id": "user-1",
                    "conversation_id": "c-1",
                    "role": "user",
                    "content": "FIRST",
                    "created_at": now - _td(minutes=10),
                },
                {
                    "user_id": "user-1",
                    "conversation_id": "c-1",
                    "role": "assistant",
                    "content": "SECOND",
                    "created_at": now - _td(minutes=5),
                },
            ]
        )

        responses, calls = patch_complete
        responses.append(_resp([TextBlock(type="text", text="ok", citations=None)]))

        await self._drain(
            chat_module.handle_chat_turn(user_id="user-1", message="THIRD", conversation_id="c-1")
        )

        # The fake build_coach_messages preserves history order; the
        # call to complete() should see FIRST → SECOND → THIRD.
        sent = calls[0]["messages"]
        contents = [m["content"] for m in sent if isinstance(m.get("content"), str)]
        # Should be [FIRST, SECOND, THIRD] in order.
        assert contents == ["FIRST", "SECOND", "THIRD"]

    async def test_passes_purpose_chat_to_gateway(self, patch_complete):
        """The cost dashboard distinguishes chat from brief/review.
        Pin so a refactor doesn't leak chat spend into the wrong
        bucket."""
        from anthropic.types import TextBlock

        responses, calls = patch_complete
        responses.append(_resp([TextBlock(type="text", text="ok", citations=None)]))

        await self._drain(
            chat_module.handle_chat_turn(user_id="user-99", message="hi", conversation_id="c-1")
        )

        assert calls[0]["purpose"] == "chat"
        assert calls[0]["user_id"] == "user-99"
        assert calls[0]["tools"] is not None  # tools registered every call


class TestRecentDataSummary:
    """_recent_data_summary builds the human-readable context block
    that's prepended to the memory-rewrite LLM prompt. It walks
    7 days of beats / intentions / mood / reviews and renders
    Markdown.

    Why test directly: the existing TestRewriteCoachMemory stubs
    this whole helper out, so a regression in the rendering would
    silently degrade the LLM's input quality without any test
    failure. Pin each of the four sections (sessions, intentions,
    mood, reviews) plus the empty-state fallback."""

    @pytest.fixture
    def stub_reviews_empty(self, monkeypatch):
        """list_reviews defaults to empty unless a test opts in."""

        async def fake_list_reviews(_user_id, limit=7):
            return []

        monkeypatch.setattr(memory_rewrite_module, "list_reviews", fake_list_reviews)

    @pytest.fixture
    def patch_repos(self, monkeypatch):
        """Returns a setter that monkeypatches build_repos to return
        the supplied _FakeCoachRepos instance."""

        def setter(repos):
            async def fake_build_repos(_user_id):
                return repos

            monkeypatch.setattr(memory_rewrite_module, "build_repos", fake_build_repos)

        return setter

    async def test_empty_data_renders_no_sessions_line(self, patch_repos, stub_reviews_empty):
        """No beats / intentions / notes / reviews → output still
        renders the section headers with the documented empty-state
        line. Pin so the LLM gets a stable structure even on a
        first-week user."""
        patch_repos(_FakeCoachRepos())
        out = await memory_rewrite_module._recent_data_summary("user-1")
        assert "## Last 7 days of sessions" in out
        assert "(No sessions in the last 7 days)" in out
        assert "## Recent intentions" in out
        assert "## Mood" in out
        # Reviews section is OMITTED when empty (only renders if
        # at least one review has answers)
        assert "## Review answers" not in out

    async def test_recent_beats_render_with_project_name_and_duration(
        self, patch_repos, stub_reviews_empty
    ):
        """A beat in the last 7 days renders as
        `**YYYY-MM-DD** (Xh): ProjectName (45m)`. Pin the
        project name resolution + the fmt_minutes formatting."""
        recent_iso = (
            (datetime.now(UTC) - timedelta(days=2))
            .replace(hour=10, minute=0, second=0, microsecond=0)
            .isoformat()
        )
        recent_iso = recent_iso[:19]  # strip tz suffix for the helper
        beats = [_completed_beat(recent_iso, 45, project_id="p1")]
        repos = _FakeCoachRepos(
            projects=[_project("p1", "Alpha")],
            beats=beats,
        )
        patch_repos(repos)
        out = await memory_rewrite_module._recent_data_summary("user-1")
        # Project name must resolve (not "?") and the duration
        # uses fmt_minutes (45m, not "0:45:00")
        assert "Alpha (45m)" in out
        # The empty-state line must NOT appear
        assert "(No sessions in the last 7 days)" not in out

    async def test_old_beats_excluded_from_session_summary(self, patch_repos, stub_reviews_empty):
        """A beat from 10 days ago must not appear in the
        last-7-days section. Pin so the rewrite prompt isn't
        polluted with stale activity."""
        old_iso = (
            (datetime.now(UTC) - timedelta(days=10))
            .replace(hour=10, minute=0, second=0, microsecond=0)
            .isoformat()[:19]
        )
        beats = [_completed_beat(old_iso, 60, project_id="p1")]
        repos = _FakeCoachRepos(
            projects=[_project("p1", "Alpha")],
            beats=beats,
        )
        patch_repos(repos)
        out = await memory_rewrite_module._recent_data_summary("user-1")
        # The beat IS in beats but should be filtered out by the >= week_ago check
        assert "(No sessions in the last 7 days)" in out
        assert "Alpha" not in out.split("## Recent intentions")[0]

    async def test_intentions_render_with_done_and_missed_status(
        self, patch_repos, stub_reviews_empty
    ):
        """Each intention renders as `ProjectName Nm [done|missed]`.
        Pin both status branches so a regression doesn't silently
        flip the meaning."""
        from beats.domain.models import Intention

        today = datetime.now(UTC).date()
        yesterday = today - timedelta(days=1)
        intentions_by_date = {
            today: [
                Intention(project_id="p1", date=today, planned_minutes=60, completed=True),
            ],
            yesterday: [
                Intention(
                    project_id="p1",
                    date=yesterday,
                    planned_minutes=30,
                    completed=False,
                ),
            ],
        }
        repos = _FakeCoachRepos(
            projects=[_project("p1", "Alpha")],
            intentions_by_date=intentions_by_date,
        )
        patch_repos(repos)
        out = await memory_rewrite_module._recent_data_summary("user-1")
        # Done intention from today
        assert "Alpha 60m [done]" in out
        # Missed intention from yesterday
        assert "Alpha 30m [missed]" in out

    async def test_mood_section_renders_when_notes_have_mood(self, patch_repos, stub_reviews_empty):
        """Daily notes with mood render as
        `**YYYY-MM-DD**: M/5 — "<text>"`. Pin so a refactor of
        DailyNote can't drop the mood line."""
        from beats.domain.models import DailyNote

        target_dates = {
            datetime.now(UTC).date() - timedelta(days=1): DailyNote(
                date=datetime.now(UTC).date() - timedelta(days=1),
                mood=4,
                note="Felt focused in the morning",
            ),
        }

        class _MoodFakeNoteRepo:
            async def get_by_date(self, d):
                return target_dates.get(d)

        repos = _FakeCoachRepos()
        repos.note = _MoodFakeNoteRepo()
        patch_repos(repos)
        out = await memory_rewrite_module._recent_data_summary("user-1")
        assert "4/5" in out
        assert "Felt focused in the morning" in out

    async def test_mood_section_skips_notes_without_mood(self, patch_repos, stub_reviews_empty):
        """A note that exists but has mood=None → no line under
        the Mood header. Pin so empty mood doesn't render as
        "None/5"."""
        from beats.domain.models import DailyNote

        d = datetime.now(UTC).date() - timedelta(days=1)

        class _NoMoodNoteRepo:
            async def get_by_date(self, dd):
                if dd == d:
                    return DailyNote(date=d, mood=None, note="just a journal entry")
                return None

        repos = _FakeCoachRepos()
        repos.note = _NoMoodNoteRepo()
        patch_repos(repos)
        out = await memory_rewrite_module._recent_data_summary("user-1")
        assert "/5" not in out
        assert "just a journal entry" not in out

    async def test_reviews_section_renders_when_answers_present(self, patch_repos, monkeypatch):
        """A review with at least one answered question renders
        under "## Review answers". Pin so the rewrite prompt
        carries the user's most recent reflections."""

        async def fake_list_reviews(_user_id, limit=7):
            return [
                {
                    "date": "2026-04-30",
                    "answers": [
                        {"text": "I shipped the auth roadmap"},
                        {"text": ""},
                    ],
                }
            ]

        monkeypatch.setattr(memory_rewrite_module, "list_reviews", fake_list_reviews)
        patch_repos(_FakeCoachRepos())
        out = await memory_rewrite_module._recent_data_summary("user-1")
        assert "## Review answers" in out
        assert "2026-04-30" in out
        assert "I shipped the auth roadmap" in out

    async def test_unknown_project_id_renders_as_question_mark(
        self, patch_repos, stub_reviews_empty
    ):
        """Beat references a project_id not in the project map
        (project deleted between session creation and rewrite)
        → renders as "? (45m)" rather than crashing on KeyError.
        Pin so a deleted project doesn't kill the weekly rewrite."""
        recent_iso = (
            (datetime.now(UTC) - timedelta(days=1))
            .replace(hour=10, minute=0, second=0, microsecond=0)
            .isoformat()[:19]
        )
        beats = [_completed_beat(recent_iso, 45, project_id="ghost")]
        repos = _FakeCoachRepos(
            projects=[],  # project map is empty
            beats=beats,
        )
        patch_repos(repos)
        out = await memory_rewrite_module._recent_data_summary("user-1")
        assert "? (45m)" in out


class TestRewriteCoachMemory:
    """Nightly memory compaction. Reads the last 7 days, asks the LLM
    for a Markdown summary, persists via MemoryStore (which keeps the
    versioned history). The risk this guards against is silent loss
    of personality — a memory rewrite that succeeds-with-empty would
    overwrite the user's prior memory with a blank document."""

    @pytest.fixture(autouse=True)
    async def _setup(self, monkeypatch):
        await Database.connect()
        await Database.get_db()[COACH_MEMORY_COLLECTION].delete_many({})

        # Stub the heavy upstream — _recent_data_summary calls many
        # repos to build the per-day/intention/mood/review prompt
        # block. Tested independently at the IntelligenceService /
        # repo level; here we just need a deterministic stub.
        async def fake_summary(_user_id):
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
            client.close()

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

    async def test_uses_low_temperature_for_consistency(self, patch_complete):
        """Memory rewrites should be more conservative than chat
        (temperature=0.3 vs 0.7). Pin so a refactor that drops the
        kwargs to defaults doesn't make memory rewrites stylistically
        unstable across weeks."""
        factory, captured = patch_complete
        await factory()

        await memory_rewrite_module.rewrite_coach_memory("user-1")
        assert captured["kwargs"]["temperature"] == 0.3
        assert captured["kwargs"]["max_tokens"] == 2048

    async def test_includes_recent_data_summary_in_prompt(self, patch_complete, monkeypatch):
        """The user prompt must contain the recent data block so the
        LLM has fresh context. Pin so a refactor that drops the
        summary or builds the prompt without it doesn't silently
        produce stale memory."""

        async def fake_summary(_user_id):
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
            client.close()

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
            client.close()


# Tool dispatch test scaffolding
# ---------------------------------------------------------------------


class _FakeIntentionRepo:
    def __init__(self, by_date: dict | None = None):
        self._by_date = by_date or {}

    async def list_by_date(self, d):
        return list(self._by_date.get(d, []))


class _FakeNoteRepo:
    async def get_by_date(self, _d):
        return None


class _FakeProjectRepoForTools:
    """Returns a fixed list of project objects."""

    def __init__(self, projects):
        self._projects = projects

    async def list(self, archived: bool = False):
        if archived:
            return list(self._projects)
        return [p for p in self._projects if not p.archived]


class _FakeBeatRepoForTools:
    """Returns a fixed list of beats — both list_all_completed and the
    other methods AnalyticsService might invoke (we don't expect those
    here since IntelligenceService is stubbed)."""

    def __init__(self, beats):
        self._beats = beats

    async def list_all_completed(self):
        return [b for b in self._beats if b.end is not None]


class _FakeCoachRepos:
    """Mirrors the CoachRepos dataclass shape for tests."""

    def __init__(self, *, projects=None, beats=None, intentions_by_date=None):
        self.project = _FakeProjectRepoForTools(projects or [])
        self.beat = _FakeBeatRepoForTools(beats or [])
        self.intention = _FakeIntentionRepo(intentions_by_date or {})
        self.note = _FakeNoteRepo()
        self.digest = None  # not used by tools.py


def _project(id_: str, name: str, *, weekly_goal=None, goal_type="target", archived=False):
    """Quick project factory."""
    from beats.domain.models import GoalType, Project

    return Project(
        id=id_,
        name=name,
        weekly_goal=weekly_goal,
        goal_type=GoalType(goal_type) if goal_type else GoalType.TARGET,
        archived=archived,
    )


def _completed_beat(start_iso: str, minutes: int, project_id: str, *, note=None, tags=None):
    from beats.domain.models import Beat

    s = datetime.fromisoformat(start_iso).replace(tzinfo=UTC)
    return Beat(
        id="b-" + start_iso,
        project_id=project_id,
        start=s,
        end=s + timedelta(minutes=minutes),
        note=note,
        tags=list(tags or []),
    )


class TestToolsDispatch:
    """Each coach tool is an async function over the repos. The chat
    loop calls execute_tool(name, input). Wrong dispatch = the LLM
    gets useless text + the user perceives a confused coach.

    Tests cover every tool's happy path + the most consequential
    edge cases (filters, dates, empty data)."""

    async def test_unknown_tool_name_returns_error_string(self):
        """The LLM occasionally hallucinates tool names. The dispatcher
        must NOT raise — the chat loop's exception handler would turn
        a raise into an "Error: ..." tool_result, but a string
        return is more graceful (the LLM can recover)."""
        repos = _FakeCoachRepos()
        result = await tools_module.execute_tool(
            "user-1",
            "non_existent_tool",
            {},
            repos=repos,
            projects=[],
        )
        assert "Unknown tool" in result
        assert "non_existent_tool" in result

    # -- get_projects --

    async def test_get_projects_lists_active_with_goal_lines(self):
        projects = [
            _project("p1", "Alpha", weekly_goal=10, goal_type="target"),
            _project("p2", "Beta"),
        ]
        repos = _FakeCoachRepos(projects=projects)
        result = await tools_module.execute_tool(
            "user-1", "get_projects", {}, repos=repos, projects=projects
        )
        assert "Alpha" in result
        assert "Beta" in result
        # weekly_goal renders as a float; the LLM-facing format is
        # "(goal: 10.0h/wk target)".
        assert "10.0h/wk target" in result
        # No archived suffix on either.
        assert "archived" not in result

    async def test_get_projects_excludes_archived_by_default(self):
        projects = [
            _project("p1", "Active"),
            _project("p2", "Stale", archived=True),
        ]
        repos = _FakeCoachRepos(projects=projects)
        result = await tools_module.execute_tool(
            "user-1", "get_projects", {}, repos=repos, projects=projects
        )
        assert "Active" in result
        assert "Stale" not in result

    async def test_get_projects_includes_archived_when_requested(self):
        projects = [
            _project("p1", "Active"),
            _project("p2", "Stale", archived=True),
        ]
        repos = _FakeCoachRepos(projects=projects)
        result = await tools_module.execute_tool(
            "user-1",
            "get_projects",
            {"include_archived": True},
            repos=repos,
            projects=projects,
        )
        assert "Active" in result
        assert "Stale" in result
        assert "archived" in result

    async def test_get_projects_empty_returns_friendly_text(self):
        repos = _FakeCoachRepos(projects=[])
        result = await tools_module.execute_tool(
            "user-1", "get_projects", {}, repos=repos, projects=[]
        )
        assert "No projects found" in result

    # -- get_beats --

    async def test_get_beats_default_window_summarizes_total(self):
        """Default window is the last 7 days. The summary line counts
        sessions and sums hours — pin the format the LLM relies on."""
        today = datetime.now(UTC).date()
        recent_iso = (datetime.combine(today, datetime.min.time()).replace(tzinfo=UTC)).isoformat()

        projects = [_project("p1", "Alpha")]
        beats = [_completed_beat(recent_iso[:-6], 60, "p1", note="planning")]
        repos = _FakeCoachRepos(projects=projects, beats=beats)

        result = await tools_module.execute_tool(
            "user-1", "get_beats", {}, repos=repos, projects=projects
        )
        # The session line + the summary footer.
        assert "Alpha" in result
        assert "1h 0m" in result or "60m" in result
        assert "1 sessions, 1.0h total" in result or "1 sessions, 1.0" in result

    async def test_get_beats_filters_by_project_name_case_insensitive(self):
        projects = [
            _project("p1", "Alpha"),
            _project("p2", "Beta"),
        ]
        today_str = datetime.now(UTC).date().isoformat()
        beats = [
            _completed_beat(f"{today_str}T09:00:00", 30, "p1"),
            _completed_beat(f"{today_str}T10:00:00", 45, "p2"),
        ]
        repos = _FakeCoachRepos(projects=projects, beats=beats)

        result = await tools_module.execute_tool(
            "user-1",
            "get_beats",
            {"project_name": "alpha"},  # lowercase — pin case-insensitivity
            repos=repos,
            projects=projects,
        )
        assert "Alpha" in result
        assert "Beta" not in result
        assert "1 sessions" in result

    async def test_get_beats_empty_returns_friendly_text(self):
        repos = _FakeCoachRepos(projects=[], beats=[])
        result = await tools_module.execute_tool(
            "user-1", "get_beats", {}, repos=repos, projects=[]
        )
        assert "No sessions found" in result

    # -- get_intentions --

    async def test_get_intentions_lists_status(self):
        from beats.domain.models import Intention

        today = datetime.now(UTC).date()
        intentions_by_date = {
            today: [
                Intention(project_id="p1", date=today, planned_minutes=60, completed=True),
                Intention(project_id="p2", date=today, planned_minutes=30, completed=False),
            ]
        }
        projects = [_project("p1", "Alpha"), _project("p2", "Beta")]
        repos = _FakeCoachRepos(projects=projects, intentions_by_date=intentions_by_date)

        result = await tools_module.execute_tool(
            "user-1", "get_intentions", {}, repos=repos, projects=projects
        )
        assert "Alpha: 60min [done]" in result
        assert "Beta: 30min [pending]" in result

    async def test_get_intentions_explicit_date_uses_that_day(self):
        from beats.domain.models import Intention

        target = date(2026, 5, 1)
        intentions_by_date = {target: [Intention(project_id="p1", date=target, planned_minutes=45)]}
        projects = [_project("p1", "Alpha")]
        repos = _FakeCoachRepos(projects=projects, intentions_by_date=intentions_by_date)

        result = await tools_module.execute_tool(
            "user-1",
            "get_intentions",
            {"date": "2026-05-01"},
            repos=repos,
            projects=projects,
        )
        assert "Alpha: 45min" in result

    async def test_get_intentions_empty_day_returns_friendly_text(self):
        projects = [_project("p1", "Alpha")]
        repos = _FakeCoachRepos(projects=projects, intentions_by_date={})
        result = await tools_module.execute_tool(
            "user-1", "get_intentions", {}, repos=repos, projects=projects
        )
        assert "No intentions set" in result

    # -- get_productivity_score --

    async def test_get_productivity_score_formats_components(self, monkeypatch):
        async def fake_score(_self):
            return {
                "score": 67,
                "components": {
                    "consistency": 80,
                    "intentions": 50,
                    "goals": 70,
                    "quality": 65,
                },
            }

        from beats.domain.intelligence import IntelligenceService

        monkeypatch.setattr(IntelligenceService, "compute_productivity_score", fake_score)

        projects = [_project("p1", "Alpha")]
        repos = _FakeCoachRepos(projects=projects)
        result = await tools_module.execute_tool(
            "user-1", "get_productivity_score", {}, repos=repos, projects=projects
        )
        assert "Score: 67/100" in result
        assert "Consistency: 80" in result
        assert "Intentions: 50" in result

    async def test_get_productivity_score_swallows_exception(self, monkeypatch):
        """If IntelligenceService raises (e.g. divide-by-zero on fresh
        account), the tool returns an error message instead of
        crashing the chat stream. The LLM can describe the outcome
        to the user instead of seeing a 500."""
        from beats.domain.intelligence import IntelligenceService

        async def boom(_self):
            raise ValueError("score broke")

        monkeypatch.setattr(IntelligenceService, "compute_productivity_score", boom)

        projects = [_project("p1", "Alpha")]
        repos = _FakeCoachRepos(projects=projects)
        result = await tools_module.execute_tool(
            "user-1", "get_productivity_score", {}, repos=repos, projects=projects
        )
        assert "Could not compute score" in result
        assert "score broke" in result

    # -- get_patterns --

    async def test_get_patterns_lists_first_ten(self, monkeypatch):
        from beats.domain.intelligence import IntelligenceService
        from beats.domain.models import InsightCard

        async def fake_detect(_self):
            return [
                InsightCard(
                    id="i1", type="day_pattern", title="Tuesdays peak", body="b1", priority=1
                ),
                InsightCard(id="i2", type="time_pattern", title="9am peak", body="b2", priority=2),
            ]

        monkeypatch.setattr(IntelligenceService, "detect_patterns", fake_detect)
        repos = _FakeCoachRepos(projects=[])
        result = await tools_module.execute_tool(
            "user-1", "get_patterns", {}, repos=repos, projects=[]
        )
        assert "Tuesdays peak" in result
        assert "9am peak" in result
        assert "(day_pattern)" in result

    async def test_get_patterns_empty_returns_friendly_text(self, monkeypatch):
        from beats.domain.intelligence import IntelligenceService

        async def fake_detect(_self):
            return []

        monkeypatch.setattr(IntelligenceService, "detect_patterns", fake_detect)
        repos = _FakeCoachRepos(projects=[])
        result = await tools_module.execute_tool(
            "user-1", "get_patterns", {}, repos=repos, projects=[]
        )
        assert "No patterns" in result

    # -- search_beats --

    async def test_search_beats_matches_note_text(self):
        projects = [_project("p1", "Alpha")]
        beats = [
            _completed_beat("2026-05-01T09:00:00", 30, "p1", note="auth refactor planning"),
            _completed_beat("2026-05-02T09:00:00", 45, "p1", note="meeting prep"),
        ]
        repos = _FakeCoachRepos(projects=projects, beats=beats)

        result = await tools_module.execute_tool(
            "user-1", "search_beats", {"query": "REFACTOR"}, repos=repos, projects=projects
        )
        # Case-insensitive match on the note text.
        assert "auth refactor planning" in result
        assert "meeting prep" not in result

    async def test_search_beats_matches_tags(self):
        projects = [_project("p1", "Alpha")]
        beats = [
            _completed_beat("2026-05-01T09:00:00", 30, "p1", tags=["focus", "deep-work"]),
            _completed_beat("2026-05-02T09:00:00", 45, "p1", tags=["meeting"]),
        ]
        repos = _FakeCoachRepos(projects=projects, beats=beats)

        result = await tools_module.execute_tool(
            "user-1", "search_beats", {"query": "deep"}, repos=repos, projects=projects
        )
        assert "2026-05-01" in result
        assert "2026-05-02" not in result

    async def test_search_beats_empty_query_short_circuits(self):
        repos = _FakeCoachRepos(projects=[], beats=[])
        result = await tools_module.execute_tool(
            "user-1", "search_beats", {"query": ""}, repos=repos, projects=[]
        )
        assert "No search query" in result

    async def test_search_beats_no_matches_returns_query_in_message(self):
        projects = [_project("p1", "Alpha")]
        beats = [_completed_beat("2026-05-01T09:00:00", 30, "p1", note="something")]
        repos = _FakeCoachRepos(projects=projects, beats=beats)
        result = await tools_module.execute_tool(
            "user-1", "search_beats", {"query": "nonsense"}, repos=repos, projects=projects
        )
        assert "nonsense" in result
        assert "No sessions matching" in result


class TestBuildSystemBlock:
    """Pure function — returns COACH_PERSONA. Locked here so a
    refactor that quietly changes the persona text is visible."""

    def test_returns_non_empty_string(self):
        result = context_module.build_system_block()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_returns_the_coach_persona(self):
        from beats.coach.prompts import COACH_PERSONA

        assert context_module.build_system_block() == COACH_PERSONA


class TestBuildCoachMessages:
    """build_coach_messages composes the (system, messages, spec) tuple
    every coach call uses. The structure is load-bearing for prompt
    caching (the cache_spec marks index 0 of messages as cached, which
    is the user_ctx block — a refactor that re-orders the preamble
    without updating the spec would silently miss the cache)."""

    @pytest.fixture
    def patched_context(self, monkeypatch):
        """Stub build_repos / build_user_context / build_day_context so
        we can drive the composition without real Mongo data."""

        async def fake_build_repos(_user_id):
            return _FakeCoachRepos()

        async def fake_user_ctx(_user_id, _repos):
            return "USER_CTX_BLOCK"

        async def fake_day_ctx(_user_id, _repos, _target_date):
            return "DAY_CTX_BLOCK"

        monkeypatch.setattr(context_module, "build_repos", fake_build_repos)
        monkeypatch.setattr(context_module, "build_user_context", fake_user_ctx)
        monkeypatch.setattr(context_module, "build_day_context", fake_day_ctx)

    async def test_returns_system_messages_and_spec(self, patched_context):
        system, messages, spec = await context_module.build_coach_messages(
            "user-1", "what should I do today?"
        )
        # System is the persona string.
        assert isinstance(system, str)
        assert len(system) > 0
        # Spec marks system + first message index for caching.
        assert spec.system_cached is True
        assert spec.cached_turn_indices == [0]

    async def test_preamble_is_user_assistant_user_assistant_user(self, patched_context):
        """The preamble alternates user/assistant/user/assistant before
        the actual user message — Anthropic's API requires user/assistant
        alternation, and the fake "Context loaded." / "Ready." assistant
        turns are how we keep the shape valid while loading large
        cacheable context blocks. Pin the role sequence — a refactor
        that drops one of the assistant acks would break the API call."""
        _, messages, _ = await context_module.build_coach_messages("user-1", "hello")
        roles = [m["role"] for m in messages]
        # First 4 are the preamble, then the trailing user message.
        assert roles[:5] == ["user", "assistant", "user", "assistant", "user"]

    async def test_user_ctx_is_message_index_0(self, patched_context):
        """Cache spec marks index 0 — that index MUST be the user
        context block (the heavy 30-day aggregate that's cheap to cache).
        A refactor that swapped index 0 for the day_ctx would silently
        cache the wrong (volatile) content."""
        _, messages, spec = await context_module.build_coach_messages("user-1", "hi")
        assert spec.cached_turn_indices == [0]
        assert messages[0]["content"] == "USER_CTX_BLOCK"

    async def test_day_ctx_is_message_index_2(self, patched_context):
        """Day context follows the user_ctx ack at index 1, lands at
        index 2. NOT cached — it changes every day."""
        _, messages, _ = await context_module.build_coach_messages("user-1", "hi")
        assert messages[2]["content"] == "DAY_CTX_BLOCK"

    async def test_user_message_is_last(self, patched_context):
        _, messages, _ = await context_module.build_coach_messages("user-1", "what's my best week?")
        assert messages[-1]["role"] == "user"
        assert messages[-1]["content"] == "what's my best week?"

    async def test_history_inserted_between_preamble_and_user_message(self, patched_context):
        """History from prior turns goes after the preamble (index 4)
        and before the new user message. Pin so a refactor doesn't put
        history INSIDE the preamble (would break cache index 0) or
        after the user message (would mean the LLM sees the new
        question before the conversation it's responding to)."""
        history = [
            {"role": "user", "content": "earlier question"},
            {"role": "assistant", "content": "earlier answer"},
        ]
        _, messages, _ = await context_module.build_coach_messages(
            "user-1", "follow up", history=history
        )
        # Preamble (4) + history (2) + user message (1) = 7
        assert len(messages) == 7
        assert messages[4]["content"] == "earlier question"
        assert messages[5]["content"] == "earlier answer"
        assert messages[6]["content"] == "follow up"

    async def test_no_history_omits_history_section(self, patched_context):
        _, messages, _ = await context_module.build_coach_messages("user-1", "hi")
        # Preamble (4) + user message (1) = 5
        assert len(messages) == 5

    async def test_target_date_threads_to_day_ctx(self, monkeypatch):
        """Locks that target_date is passed through. Without this, a
        brief generated for a past date would silently use today's
        signals — confusing if a user asks the coach to brief
        yesterday."""
        captured = {}

        async def fake_build_repos(_user_id):
            return _FakeCoachRepos()

        async def fake_user_ctx(_user_id, _repos):
            return "USER"

        async def fake_day_ctx(_user_id, _repos, target_date):
            captured["target_date"] = target_date
            return "DAY"

        monkeypatch.setattr(context_module, "build_repos", fake_build_repos)
        monkeypatch.setattr(context_module, "build_user_context", fake_user_ctx)
        monkeypatch.setattr(context_module, "build_day_context", fake_day_ctx)

        target = date(2026, 5, 1)
        await context_module.build_coach_messages("user-1", "yesterday's brief", target_date=target)
        assert captured["target_date"] == target


class TestBuildUserContext:
    """build_user_context is the heavy 30-day aggregate. Tests cover
    the structural composition (header lines, sections) and the
    productivity-score-unavailable fallback. Repo data uses small
    in-memory fakes."""

    @pytest.fixture(autouse=True)
    async def _setup_db(self):
        """build_user_context reads from MemoryStore which uses
        Database.get_db(). Connect for the duration of the test."""
        await Database.connect()
        await Database.get_db()[COACH_MEMORY_COLLECTION].delete_many({})
        yield
        await Database.disconnect()

    async def test_renders_section_headers_in_expected_order(self, monkeypatch):
        """Pin the markdown structure the LLM consumes — section
        order matters because the model gives early sections more
        attention. A refactor that re-orders these would silently
        change coach behavior."""
        from beats.domain.intelligence import IntelligenceService

        async def fake_score(_self):
            return {
                "score": 75,
                "components": {
                    "consistency": 80,
                    "intentions": 70,
                    "goals": 75,
                    "quality": 75,
                },
            }

        monkeypatch.setattr(IntelligenceService, "compute_productivity_score", fake_score)

        repos = _FakeCoachRepos(projects=[_project("p1", "Alpha", weekly_goal=10)])
        result = await context_module.build_user_context("user-1", repos)

        # Expected sections in order.
        sections = [
            "## User profile (30-day window)",
            "Active projects: Alpha",
            "### Hours by project (last 30 days)",
            "### Weekly totals",
            "Productivity score: 75/100",
            "### Weekly goals",
            "## Coach memory",
        ]
        last_pos = -1
        for s in sections:
            pos = result.find(s)
            assert pos > last_pos, f"section {s!r} out of order in:\n{result}"
            last_pos = pos

    async def test_score_unavailable_renders_fallback(self, monkeypatch):
        """When IntelligenceService raises (fresh account, divide-by-
        zero), the context should still render — with "Productivity
        score: unavailable" instead of a Python traceback. Pin so a
        refactor of the except-Exception swallow doesn't quietly
        break the coach for new users."""
        from beats.domain.intelligence import IntelligenceService

        async def boom(_self):
            raise ValueError("fresh user")

        monkeypatch.setattr(IntelligenceService, "compute_productivity_score", boom)

        repos = _FakeCoachRepos(projects=[_project("p1", "Alpha")])
        result = await context_module.build_user_context("user-1", repos)
        assert "Productivity score: unavailable" in result

    async def test_no_memory_renders_empty_marker(self, monkeypatch):
        """First-run users have no coach_memory document. The context
        should render the placeholder so the LLM doesn't see "None"
        or an unterminated section. Pin the exact phrasing the cached
        context expects."""
        from beats.domain.intelligence import IntelligenceService

        async def fake_score(_self):
            return {
                "score": 50,
                "components": {
                    "consistency": 50,
                    "intentions": 50,
                    "goals": 50,
                    "quality": 50,
                },
            }

        monkeypatch.setattr(IntelligenceService, "compute_productivity_score", fake_score)

        repos = _FakeCoachRepos(projects=[_project("p1", "Alpha")])
        result = await context_module.build_user_context("user-1", repos)
        assert "(No coach memory yet" in result

    async def test_existing_memory_is_inlined(self, monkeypatch):
        """When MemoryStore has content, that content appears verbatim
        under the ## Coach memory section. Pin so a refactor of the
        MemoryStore.read() call doesn't drop the user's persisted
        personality from the cache."""
        from beats.domain.intelligence import IntelligenceService

        async def fake_score(_self):
            return {
                "score": 60,
                "components": {
                    "consistency": 60,
                    "intentions": 60,
                    "goals": 60,
                    "quality": 60,
                },
            }

        monkeypatch.setattr(IntelligenceService, "compute_productivity_score", fake_score)

        # Seed memory directly via MemoryStore.
        client, db = _async_db()
        try:
            store = MemoryStore(db, "user-1")
            await store.write("# Memory\n\nUser ships at night.")
        finally:
            client.close()

        repos = _FakeCoachRepos(projects=[_project("p1", "Alpha")])
        result = await context_module.build_user_context("user-1", repos)
        assert "User ships at night." in result

    async def test_no_goals_renders_no_goals_set(self, monkeypatch):
        from beats.domain.intelligence import IntelligenceService

        async def fake_score(_self):
            return {
                "score": 50,
                "components": {
                    "consistency": 50,
                    "intentions": 50,
                    "goals": 50,
                    "quality": 50,
                },
            }

        monkeypatch.setattr(IntelligenceService, "compute_productivity_score", fake_score)

        # Project with no weekly_goal.
        repos = _FakeCoachRepos(projects=[_project("p1", "Alpha", weekly_goal=None)])
        result = await context_module.build_user_context("user-1", repos)
        assert "(No goals set)" in result


class TestGatewayBudgetInvariant:
    """Critical invariant: enforce_budget() must fire BEFORE any
    client.messages.* call. If a user is over their monthly cap, the
    next request must NOT spend more tokens. A regression here = the
    cap exists in name only — every chat / brief / review still hits
    Anthropic, the cost dashboard climbs forever, and the only signal
    is the eventual response that the system surfaces.

    The test pattern: seed an over-budget usage row, install a fake
    Anthropic client that records every call, attempt complete() /
    stream(), assert BudgetExceeded was raised AND the client
    recorded zero calls."""

    @pytest.fixture(autouse=True)
    async def _setup(self):
        await Database.connect()
        await Database.get_db()[LLM_USAGE_COLLECTION].delete_many({})
        yield
        await Database.disconnect()

    @pytest.fixture
    def fake_client(self, monkeypatch):
        """Replace _get_client() with a fake that records every call.
        Returns the call list so tests can assert 'zero LLM calls
        when over budget'."""
        from beats.coach import gateway

        calls: list[str] = []

        class _FakeMessages:
            async def create(self, **_kwargs):
                calls.append("create")
                raise AssertionError(
                    "client.messages.create was called despite over-budget — "
                    "enforce_budget() did NOT fire before spend"
                )

            def stream(self, **_kwargs):
                calls.append("stream")
                raise AssertionError(
                    "client.messages.stream was called despite over-budget — "
                    "enforce_budget() did NOT fire before spend"
                )

        class _FakeAnthropicClient:
            messages = _FakeMessages()

        def fake_get_client():
            return _FakeAnthropicClient()

        monkeypatch.setattr(gateway, "_get_client", fake_get_client)
        return calls

    async def _seed_over_budget(self, user_id: str, monkeypatch):
        """Set a low monthly limit and seed a usage row over it.
        Returns nothing; the next enforce_budget call will raise."""
        from beats import settings as settings_module

        # Force a low cap.
        monkeypatch.setattr(settings_module.settings, "coach_monthly_budget_usd", 1.0)

        tracker = UsageTracker(user_id)
        await tracker.record(
            model="claude-opus-4-7",
            input_tokens=1000,
            output_tokens=500,
            cache_creation=0,
            cache_read=0,
            cost_usd=2.0,  # over the $1 cap
            purpose="chat",
        )

    async def test_complete_does_not_call_anthropic_when_over_budget(
        self, fake_client, monkeypatch
    ):
        """The cost-cap invariant: if the user is over budget,
        gateway.complete() raises BudgetExceeded BEFORE any
        client.messages.create(). The fake client's create() raises
        AssertionError if it's ever called — the test fails LOUDLY
        on a regression rather than silently overspending."""
        from beats.coach.gateway import complete

        await self._seed_over_budget("user-1", monkeypatch)

        with pytest.raises(BudgetExceeded):
            await complete(
                user_id="user-1",
                system="sys",
                messages=[{"role": "user", "content": "hi"}],
                purpose="chat",
            )

        # Zero recorded LLM calls — the invariant holds.
        assert fake_client == []

    async def test_stream_does_not_call_anthropic_when_over_budget(self, fake_client, monkeypatch):
        """Same invariant for the streaming path. gateway.stream() is
        an async generator — `iterating` it (via async for) is what
        triggers enforce_budget. Pin both halves: BudgetExceeded
        raises and the client records no stream() call."""
        from beats.coach.gateway import stream

        await self._seed_over_budget("user-1", monkeypatch)

        async def _drain():
            async for _ev in stream(
                user_id="user-1",
                system="sys",
                messages=[{"role": "user", "content": "hi"}],
                purpose="chat",
            ):
                pass  # pragma: no cover — should never reach

        with pytest.raises(BudgetExceeded):
            await _drain()

        assert fake_client == []

    async def test_complete_calls_anthropic_when_under_budget(self, fake_client, monkeypatch):
        """Negative control: when under budget, the LLM call IS made.
        Ensures the test scaffolding above doesn't accidentally pass
        because complete() never reaches the LLM (which would make
        the invariant test a tautology)."""
        from beats import settings as settings_module
        from beats.coach.gateway import complete

        # High cap + no spend → enforce_budget passes.
        monkeypatch.setattr(settings_module.settings, "coach_monthly_budget_usd", 100.0)

        # The fake client raises AssertionError if called — that's
        # exactly what we want to see now (it proves the call site
        # IS reached when budget is fine). Catch the AssertionError
        # to confirm the path executed, rather than the test failing.
        with pytest.raises(AssertionError, match="enforce_budget"):
            await complete(
                user_id="user-1",
                system="sys",
                messages=[{"role": "user", "content": "hi"}],
                purpose="chat",
            )

        # The fake recorded the create() attempt.
        assert fake_client == ["create"]

    async def test_zero_limit_disables_enforcement_so_call_proceeds(self, fake_client, monkeypatch):
        """When coach_monthly_budget_usd <= 0, budget enforcement is
        off (the documented "no cap" deploy mode from T1 #19). Even
        with massive spend recorded, the LLM call must proceed. Pin
        the bypass — without it, a self-host that hasn't configured
        the cap would still get spuriously blocked."""
        from beats import settings as settings_module
        from beats.coach.gateway import complete

        monkeypatch.setattr(settings_module.settings, "coach_monthly_budget_usd", 0.0)

        # Big spend that WOULD trigger BudgetExceeded if the cap
        # were active. With limit=0 it's a no-op.
        tracker = UsageTracker("user-1")
        await tracker.record(
            model="claude-opus-4-7",
            input_tokens=1000,
            output_tokens=500,
            cache_creation=0,
            cache_read=0,
            cost_usd=999.0,
            purpose="chat",
        )

        # Should proceed past enforce_budget — the fake client's
        # create() raises to confirm the path executes.
        with pytest.raises(AssertionError, match="enforce_budget"):
            await complete(
                user_id="user-1",
                system="sys",
                messages=[{"role": "user", "content": "hi"}],
                purpose="chat",
            )
        assert fake_client == ["create"]


class TestGatewayCacheControlIntegration:
    """The _apply_cache_control helper has unit-level tests in
    TestApplyCacheControl. This class pins the *integration*: that
    gateway.complete() actually feeds the cache-marked output to
    client.messages.create() and that the response's cache fields
    flow back into UsageTracker.record(). A regression that
    bypassed _apply_cache_control would silently disable prompt
    caching across the entire coach surface — ~10× cost increase
    on cached calls with no error to surface it."""

    @pytest.fixture(autouse=True)
    async def _setup(self, monkeypatch):
        from beats import settings as settings_module

        await Database.connect()
        await Database.get_db()[LLM_USAGE_COLLECTION].delete_many({})
        # Disable budget enforcement so the tests focus on the
        # cache-control integration.
        monkeypatch.setattr(settings_module.settings, "coach_monthly_budget_usd", 0.0)
        yield
        await Database.disconnect()

    @pytest.fixture
    def fake_client(self, monkeypatch):
        """Replace _get_client() with a fake whose .messages.create
        records the kwargs and returns a deterministic Anthropic-
        shaped response."""
        from beats.coach import gateway

        captured: dict = {"create_kwargs": None}

        class _FakeUsage:
            def __init__(self, input_tokens, output_tokens, cache_creation, cache_read):
                self.input_tokens = input_tokens
                self.output_tokens = output_tokens
                self.cache_creation_input_tokens = cache_creation
                self.cache_read_input_tokens = cache_read

        class _FakeMessage:
            def __init__(self):
                from anthropic.types import TextBlock as _TB

                self.content = [_TB(type="text", text="ok", citations=None)]
                self.model = "claude-opus-4-7"
                self.usage = _FakeUsage(1500, 80, 400, 800)
                self.stop_reason = "end_turn"

        class _FakeMessages:
            async def create(self, **kwargs):
                captured["create_kwargs"] = kwargs
                return _FakeMessage()

        class _FakeAnthropicClient:
            messages = _FakeMessages()

        def fake_get_client():
            return _FakeAnthropicClient()

        monkeypatch.setattr(gateway, "_get_client", fake_get_client)
        return captured

    async def test_complete_marks_system_block_with_cache_control(self, fake_client):
        """Default CacheSpec → system block forwarded with the
        ephemeral cache marker. A refactor that bypassed
        _apply_cache_control (e.g. passed `system=system` directly)
        would silently disable system caching — ~3× cost on every
        cached call with no error."""
        from beats.coach.gateway import complete

        await complete(
            user_id="user-1",
            system="you are the coach",
            messages=[{"role": "user", "content": "hi"}],
            purpose="chat",
        )

        kwargs = fake_client["create_kwargs"]
        assert kwargs is not None
        sys_blocks = kwargs["system"]
        assert isinstance(sys_blocks, list)
        assert sys_blocks[0]["cache_control"] == {"type": "ephemeral"}
        assert sys_blocks[0]["text"] == "you are the coach"

    async def test_complete_marks_indexed_messages_with_cache_control(self, fake_client):
        """When the spec marks an index, that message's content gets
        a cache_control breakpoint in the API call. brief.py and
        review.py rely on this — their build_coach_messages produces
        CacheSpec(cached_turn_indices=[0])."""
        from beats.coach.gateway import CacheSpec, complete

        await complete(
            user_id="user-1",
            system="sys",
            messages=[
                {"role": "user", "content": "cacheable user-context block"},
                {"role": "assistant", "content": "ack"},
                {"role": "user", "content": "hi"},
            ],
            cache_spec=CacheSpec(system_cached=True, cached_turn_indices=[0]),
            purpose="chat",
        )

        kwargs = fake_client["create_kwargs"]
        msgs = kwargs["messages"]
        assert msgs[0]["content"] == [
            {
                "type": "text",
                "text": "cacheable user-context block",
                "cache_control": {"type": "ephemeral"},
            }
        ]
        # Message 1 (assistant ack) NOT converted — still bare string.
        assert msgs[1]["content"] == "ack"

    async def test_complete_routes_response_cache_fields_into_usage_record(self, fake_client):
        """Round-trip: the fake returns usage with cache_creation=400,
        cache_read=800. Those values must land in the persisted
        llm_usage row. Without this, the cost dashboard's cache
        breakdown would always show zero."""
        from beats.coach.gateway import complete

        await complete(
            user_id="user-1",
            system="sys",
            messages=[{"role": "user", "content": "hi"}],
            purpose="chat",
        )

        doc = await Database.get_db()[LLM_USAGE_COLLECTION].find_one({"user_id": "user-1"})
        assert doc is not None
        assert doc["cache_creation_input_tokens"] == 400
        assert doc["cache_read_input_tokens"] == 800

    async def test_gateway_response_carries_cache_fields_to_caller(self, fake_client):
        """The GatewayResponse the caller receives carries the cache
        fields. brief.py and review.py persist these into the
        daily_briefs / review documents."""
        from beats.coach.gateway import complete

        result = await complete(
            user_id="user-1",
            system="sys",
            messages=[{"role": "user", "content": "hi"}],
            purpose="chat",
        )

        assert result.cache_creation_input_tokens == 400
        assert result.cache_read_input_tokens == 800

    async def test_complete_handles_response_without_cache_fields(self, monkeypatch):
        """A non-cached response may not include cache_creation /
        cache_read on the usage object. gateway.py:157-158 defends
        with getattr(..., 0) or 0. Pin so a refactor that drops the
        default doesn't AttributeError."""
        from beats import settings as settings_module
        from beats.coach import gateway
        from beats.coach.gateway import complete

        monkeypatch.setattr(settings_module.settings, "coach_monthly_budget_usd", 0.0)

        class _BareUsage:
            input_tokens = 100
            output_tokens = 50
            # NO cache_creation_input_tokens / cache_read_input_tokens.

        class _BareMessage:
            def __init__(self):
                from anthropic.types import TextBlock as _TB

                self.content = [_TB(type="text", text="ok", citations=None)]
                self.model = "claude-opus-4-7"
                self.usage = _BareUsage()
                self.stop_reason = "end_turn"

        class _BareMessages:
            async def create(self, **_kwargs):
                return _BareMessage()

        class _BareClient:
            messages = _BareMessages()

        monkeypatch.setattr(gateway, "_get_client", lambda: _BareClient())

        result = await complete(
            user_id="user-1",
            system="sys",
            messages=[{"role": "user", "content": "hi"}],
            purpose="chat",
        )
        assert result.cache_creation_input_tokens == 0
        assert result.cache_read_input_tokens == 0


class TestBuildDayContext:
    """build_day_context renders today's signals (beats, intentions,
    mood, calendar, biometrics) into the small per-turn context
    block that's prepended to chat / brief / review prompts.

    Why test directly: existing tests stub this whole function out,
    leaving 130+ lines (38% of context.py) uncovered. A regression
    in any branch would silently degrade the LLM's per-turn input
    and the chat coach would drift further from the user's actual
    state without any test failure.

    Most assertions use `target_date` to avoid wall-clock dependency.
    Database is needed because the calendar + biometric blocks
    query Mongo directly; both are wrapped in try/except so a
    missing testcontainer would degrade gracefully — but we
    connect anyway to exercise the bio block on success."""

    @pytest.fixture(autouse=True)
    async def _setup(self):
        await Database.connect()
        # Clean any stale biometric / calendar docs from prior tests
        db = Database.get_db()
        await db.biometric_days.delete_many({})
        await db.calendar_integrations.delete_many({})
        yield
        await Database.disconnect()

    async def test_empty_data_renders_headers_with_empty_state(self):
        """No beats / intentions / notes / calendar / biometrics →
        the four section headers still render with documented
        empty-state lines. Pin so a coach turn on a first-day
        account doesn't crash on missing keys."""
        target = datetime.now(UTC).date()
        repos = _FakeCoachRepos()
        out = await context_module.build_day_context("user-1", repos, target_date=target)
        assert f"## Today: {target.isoformat()}" in out
        assert "### Yesterday's sessions" in out
        assert "No sessions yesterday." in out
        assert "### Today's sessions so far" in out
        assert "No sessions today." in out
        assert "### Today's intentions" in out
        assert "No intentions set for today." in out
        # Calendar + biometric sections are omitted when empty
        assert "### Calendar today" not in out
        assert "### Last night's biometrics" not in out

    async def test_today_beats_render_with_time_project_and_duration(self):
        """A beat that started today renders as
        `  HH:MM — ProjectName (Xm)` with a totals line.
        Pin the format so the coach's "today so far" prompt
        block is stable."""
        from beats.domain.models import Beat

        target = datetime.now(UTC).date()
        s = datetime.combine(target, datetime.min.time(), tzinfo=UTC).replace(hour=9)
        beat = Beat(
            id="b1",
            project_id="p1",
            start=s,
            end=s + timedelta(minutes=45),
        )
        repos = _FakeCoachRepos(
            projects=[_project("p1", "Alpha")],
            beats=[beat],
        )
        out = await context_module.build_day_context("user-1", repos, target_date=target)
        assert "09:00 — Alpha (45m)" in out
        # Totals line: 45/60 = 0.75h, rounded to 0.8h via :.1f
        assert "Total: 0.8h across 1 sessions" in out

    async def test_yesterday_beats_render_separately_from_today(self):
        """Yesterday's beats land under "### Yesterday's sessions"
        — pin so the coach can compare day-to-day rather than
        confuse them. A beat from yesterday must not appear in
        the today section."""
        from beats.domain.models import Beat

        target = datetime.now(UTC).date()
        yesterday = target - timedelta(days=1)
        s = datetime.combine(yesterday, datetime.min.time(), tzinfo=UTC).replace(hour=14)
        beat = Beat(
            id="b1",
            project_id="p1",
            start=s,
            end=s + timedelta(minutes=60),
        )
        repos = _FakeCoachRepos(
            projects=[_project("p1", "Alpha")],
            beats=[beat],
        )
        out = await context_module.build_day_context("user-1", repos, target_date=target)
        # Split on the today header to verify the beat is in
        # yesterday's section, not today's
        yesterday_block, _, today_block = out.partition("### Today's sessions so far")
        assert "14:00 — Alpha (1h 0m)" in yesterday_block
        assert "Alpha" not in today_block.split("### Today's intentions")[0]

    async def test_beat_with_note_renders_note_suffix(self):
        """A beat with .note set renders as `... [note: <note>]`.
        Pin so the LLM sees per-session annotations the user wrote."""
        from beats.domain.models import Beat

        target = datetime.now(UTC).date()
        s = datetime.combine(target, datetime.min.time(), tzinfo=UTC).replace(hour=10)
        beat = Beat(
            id="b1",
            project_id="p1",
            start=s,
            end=s + timedelta(minutes=30),
            note="deep work",
        )
        repos = _FakeCoachRepos(
            projects=[_project("p1", "Alpha")],
            beats=[beat],
        )
        out = await context_module.build_day_context("user-1", repos, target_date=target)
        assert "[note: deep work]" in out

    async def test_intentions_render_with_done_and_pending_status(self):
        """Today's intentions render with done|pending status.
        Pin both branches so a regression doesn't silently flip
        the coach's view of what's complete."""
        from beats.domain.models import Intention

        target = datetime.now(UTC).date()
        intentions_by_date = {
            target: [
                Intention(
                    project_id="p1",
                    date=target,
                    planned_minutes=60,
                    completed=True,
                ),
                Intention(
                    project_id="p1",
                    date=target,
                    planned_minutes=30,
                    completed=False,
                ),
            ]
        }
        repos = _FakeCoachRepos(
            projects=[_project("p1", "Alpha")],
            intentions_by_date=intentions_by_date,
        )
        out = await context_module.build_day_context("user-1", repos, target_date=target)
        assert "Alpha: 60min [done]" in out
        assert "Alpha: 30min [pending]" in out

    async def test_yesterday_mood_line_renders_with_truncated_note(self):
        """Yesterday's note with mood + text → renders as
        `Yesterday's mood: M/5 — "<truncated note>"`. Pin so
        the coach can pick up on emotional context day-over-day."""
        from beats.domain.models import DailyNote

        target = datetime.now(UTC).date()
        yesterday = target - timedelta(days=1)
        long_note = "Felt great. " * 20  # > 100 chars

        class _MoodNoteRepo:
            async def get_by_date(self, d):
                if d == yesterday:
                    return DailyNote(date=yesterday, mood=4, note=long_note)
                return None

        repos = _FakeCoachRepos()
        repos.note = _MoodNoteRepo()
        out = await context_module.build_day_context("user-1", repos, target_date=target)
        assert "Yesterday's mood: 4/5" in out
        # Note is truncated to 100 chars
        assert long_note[:100] in out
        assert long_note[:101] not in out

    async def test_biometric_block_renders_when_doc_exists(self):
        """A biometric_days doc for yesterday → renders the
        sleep/HRV/HR/readiness block. Pin all four field
        formatters so a regression doesn't drop one. The block
        is hidden entirely if no fields are populated."""
        target = datetime.now(UTC).date()
        yesterday = target - timedelta(days=1)
        db = Database.get_db()
        await db.biometric_days.insert_one(
            {
                "user_id": "user-1",
                "date": yesterday.isoformat(),
                "sleep_minutes": 480,
                "sleep_efficiency": 0.92,
                "hrv_ms": 45,
                "resting_hr_bpm": 58,
                "readiness_score": 88,
                "created_at": datetime.now(UTC),
            }
        )
        repos = _FakeCoachRepos()
        out = await context_module.build_day_context("user-1", repos, target_date=target)
        assert "### Last night's biometrics" in out
        # 480 min / 60 = 8.0h
        assert "Sleep: 8.0h (efficiency 92%)" in out
        assert "HRV: 45ms" in out
        assert "Resting HR: 58 bpm" in out
        assert "Readiness: 88/100" in out

    async def test_biometric_block_omitted_when_no_fields_populated(self):
        """A biometric_days doc with all biometric fields None
        (e.g. a placeholder row) → block is omitted, NOT rendered
        with empty values. Pin so a coach turn doesn't include
        a half-empty biometric section."""
        target = datetime.now(UTC).date()
        yesterday = target - timedelta(days=1)
        db = Database.get_db()
        await db.biometric_days.insert_one(
            {
                "user_id": "user-1",
                "date": yesterday.isoformat(),
                "sleep_minutes": None,
                "hrv_ms": None,
                "resting_hr_bpm": None,
                "readiness_score": None,
                "created_at": datetime.now(UTC),
            }
        )
        repos = _FakeCoachRepos()
        out = await context_module.build_day_context("user-1", repos, target_date=target)
        assert "### Last night's biometrics" not in out

    async def test_biometric_block_partial_fields_only_renders_present(self):
        """Only sleep_minutes set → biometric block renders just
        the Sleep line. Pin so a partial day's data still surfaces
        what's available."""
        target = datetime.now(UTC).date()
        yesterday = target - timedelta(days=1)
        db = Database.get_db()
        await db.biometric_days.insert_one(
            {
                "user_id": "user-1",
                "date": yesterday.isoformat(),
                "sleep_minutes": 420,
                "sleep_efficiency": None,  # no efficiency suffix
                "created_at": datetime.now(UTC),
            }
        )
        repos = _FakeCoachRepos()
        out = await context_module.build_day_context("user-1", repos, target_date=target)
        assert "Sleep: 7.0h" in out
        # No efficiency suffix
        assert "(efficiency" not in out
        # Other lines absent
        assert "HRV:" not in out
        assert "Resting HR:" not in out
        assert "Readiness:" not in out

    async def test_unknown_project_resolves_to_question_mark(self):
        """Beat references a project_id not in the project list
        (project deleted between session and prompt build) →
        renders as "? (Xm)" rather than crashing on KeyError."""
        from beats.domain.models import Beat

        target = datetime.now(UTC).date()
        s = datetime.combine(target, datetime.min.time(), tzinfo=UTC).replace(hour=11)
        beat = Beat(
            id="b1",
            project_id="ghost",
            start=s,
            end=s + timedelta(minutes=30),
        )
        repos = _FakeCoachRepos(projects=[], beats=[beat])
        out = await context_module.build_day_context("user-1", repos, target_date=target)
        assert "11:00 — ? (30m)" in out
