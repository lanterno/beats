"""Coach gateway and usage: the usage tracker, the cost estimate, the
model pricing table, the cache-control placement.

Split out of `test_coach.py` at the size ceiling (CLAUDE.md § Conventions);
the shared fakes and factories are `coach_fakes.py`'s.
"""

from datetime import UTC, datetime, timedelta

import pytest

from beats.coach.gateway import (
    MODEL_PRICING,
    UNKNOWN_MODEL_PRICING,
    CacheSpec,
    _apply_cache_control,
    _estimate_cost,
    pricing_for,
)
from beats.coach.repos import (
    LLM_USAGE_COLLECTION,
)
from beats.coach.usage import BudgetExceeded, UsageTracker
from beats.coach_fakes import (
    _S46,
    SONNET_46,
)
from beats.infrastructure.database import Database
from beats.settings import settings


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
        # sets DB_DSN/DB_NAME, which beats.settings reads; connect()
        # itself no longer touches the settings.
        await Database.connect(settings.db_dsn, settings.db_name)
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


class TestEstimateCost:
    """The deterministic cost math the gateway uses to bill users.
    Wrong here = wrong dashboard + wrong budget enforcement.

    The model: cost = base_input·rate + output·rate +
    cache_creation·write_rate + cache_read·read_rate, where
    base_input = total_input − cache_creation − cache_read.
    """

    def test_zero_tokens_zero_cost(self):
        assert _estimate_cost(SONNET_46, 0, 0, 0, 0) == 0.0

    def test_pure_input_no_cache_uses_input_rate(self):
        # 1M input tokens, no output, no cache → 1 × $3 = $3
        assert _estimate_cost(SONNET_46, 1_000_000, 0, 0, 0) == 3.0

    def test_pure_output_uses_output_rate(self):
        # 1M output tokens → 1 × $15 = $15
        assert _estimate_cost(SONNET_46, 0, 1_000_000, 0, 0) == 15.0

    def test_input_minus_cache_is_billed_at_input_rate(self):
        """If 1M input tokens were ALL cache reads, only the cache-read
        rate applies — the "base input" billed at $3/Mtok is zero.
        Locks the subtraction; without it a refactor that bills
        cache_read AS input would charge $3 + $0.30 instead of just
        $0.30 — a 10× over-bill on heavy-cache calls."""
        # 1M cache reads, no other input
        cost = _estimate_cost(SONNET_46, 1_000_000, 0, 0, 1_000_000)
        # base_input = 1M - 0 - 1M = 0, so only the cache-read rate.
        assert cost == pytest.approx(0.30, rel=1e-9)

    def test_input_minus_cache_with_cache_creation(self):
        """Same logic for cache writes — they're a separate line item."""
        cost = _estimate_cost(SONNET_46, 1_000_000, 0, 1_000_000, 0)
        # base_input = 0, cache_creation = 1M × $3.75 = $3.75
        assert cost == pytest.approx(3.75, rel=1e-9)

    def test_mixed_realistic_call(self):
        """A realistic chat turn: 5K input including 2K cache-read
        (system prompt) + 1K cache-creation (turn boundary) + 1K
        output. Computes the line-by-line bill so a refactor that
        merges any of the rates is caught."""
        cost = _estimate_cost(
            SONNET_46,
            input_tokens=5_000,
            output_tokens=1_000,
            cache_creation=1_000,
            cache_read=2_000,
        )
        # base_input = 5000 - 1000 - 2000 = 2000
        expected = (
            2000 * _S46.input / 1_000_000
            + 1000 * _S46.output / 1_000_000
            + 1000 * _S46.cache_write / 1_000_000
            + 2000 * _S46.cache_read / 1_000_000
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
            SONNET_46,
            input_tokens=9_000,
            output_tokens=0,
            cache_creation=0,
            cache_read=10_000,  # exceeds input
        )
        # max(0, 9000 - 0 - 10000) = 0, so just cache_read at $0.30/M
        expected = 10_000 * _S46.cache_read / 1_000_000
        assert cost == pytest.approx(expected, rel=1e-9)


class TestModelPricing:
    """Rates are per-model. The gateway used to hardcode Sonnet 4.6's
    prices and apply them to whatever COACH_MODEL named, so pointing the
    coach at Opus under-reported every row by 40% — and the monthly budget
    ceiling under-counted with it."""

    def test_opus_costs_more_than_sonnet_for_identical_usage(self):
        """The regression this class exists for: same tokens, different
        model, different bill."""
        args = (1_000_000, 1_000_000, 0, 0)
        sonnet = _estimate_cost("claude-sonnet-5", *args)
        opus = _estimate_cost("claude-opus-5", *args)
        assert sonnet == pytest.approx(2.0 + 10.0)
        assert opus == pytest.approx(5.0 + 25.0)

    def test_configured_default_model_is_priced(self):
        """The default in settings must be a model we can bill, or every
        call silently falls back to the unknown-model rate."""
        from beats.settings import settings

        assert pricing_for(settings.coach_model) is MODEL_PRICING[settings.coach_model]

    def test_dated_suffix_resolves_to_base_model(self):
        """A response naming a dated snapshot bills at its base rate."""
        assert pricing_for("claude-sonnet-5-20260101") is MODEL_PRICING["claude-sonnet-5"]

    def test_dated_suffix_takes_the_longest_known_prefix(self):
        """`claude-opus-5` is a prefix of `claude-opus-5-5`, and bills more:
        a dated Opus 5.5 must not be charged as Opus 5."""
        assert pricing_for("claude-opus-5-5-20261001") is MODEL_PRICING["claude-opus-5-5"]
        assert pricing_for("claude-opus-5-20260101") is MODEL_PRICING["claude-opus-5"]

    def test_unknown_model_bills_at_the_highest_known_rate(self):
        """Fail expensive, not cheap: over-estimating stops the coach at
        the budget ceiling, under-estimating spends past it unnoticed."""
        pricing = pricing_for("claude-something-unreleased")
        assert pricing is UNKNOWN_MODEL_PRICING
        assert pricing.input >= max(p.input for p in MODEL_PRICING.values())
        assert pricing.output >= max(p.output for p in MODEL_PRICING.values())

    def test_cache_rates_follow_the_standard_multipliers(self):
        for name, pricing in MODEL_PRICING.items():
            assert pricing.cache_write == pytest.approx(pricing.input * 1.25), name
            assert pricing.cache_read == pytest.approx(pricing.input * 0.10), name


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
