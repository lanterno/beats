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
from datetime import UTC, datetime, timedelta

import pytest
from motor.motor_asyncio import AsyncIOMotorClient

from beats.coach import brief as brief_module
from beats.coach import review as review_module
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
