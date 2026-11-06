"""Coach gateway and usage: the usage tracker, the cost estimate, the
model pricing table, the cache-control placement and its integration,
the budget invariant, the retry and the missing key.

Split out of `test_coach.py` at the ceiling in roadmaps/file-sizes.md;
the shared fakes and factories are `coach_fakes.py`'s.
"""

from datetime import UTC, datetime, timedelta
from typing import ClassVar

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
        await Database.connect(settings.db_dsn, settings.db_name)
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

        await Database.connect(settings.db_dsn, settings.db_name)
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

    async def test_complete_does_not_send_temperature(self, fake_client):
        """Sampling parameters were removed from the API on every
        current-generation model — Sonnet 5, Opus 5, Opus 4.7/4.8 all
        return HTTP 400 for `temperature`. The gateway used to pass one
        unconditionally, so the coach would have broken outright the
        moment COACH_MODEL moved off Sonnet 4.6."""
        from beats.coach.gateway import complete

        await complete(
            user_id="user-1",
            system="sys",
            messages=[{"role": "user", "content": "hi"}],
            purpose="chat",
        )

        kwargs = fake_client["create_kwargs"]
        assert "temperature" not in kwargs
        assert "top_p" not in kwargs
        assert "top_k" not in kwargs

    async def test_cost_uses_the_responses_model_not_the_configured_one(
        self, fake_client, monkeypatch
    ):
        """The fake answers as claude-opus-4-7 ($5/$25) while settings
        name a Sonnet ($2/$10). The persisted row must be billed at the
        rate of the model that actually served the call — the gateway
        used to bill every model at a hardcoded Sonnet 4.6 rate, which
        under-reported Opus traffic by ~40% and quietly let the monthly
        budget ceiling overshoot."""
        from beats.coach.gateway import _estimate_cost, complete
        from beats.settings import settings

        monkeypatch.setattr(settings, "coach_model", "claude-sonnet-5")

        await complete(
            user_id="user-1",
            system="sys",
            messages=[{"role": "user", "content": "hi"}],
            purpose="chat",
        )

        doc = await Database.get_db()[LLM_USAGE_COLLECTION].find_one({"user_id": "user-1"})
        assert doc is not None
        assert doc["model"] == "claude-opus-4-7"
        # usage on the fake: 1500 input, 80 output, 400 write, 800 read
        assert doc["cost_usd"] == pytest.approx(
            _estimate_cost("claude-opus-4-7", 1500, 80, 400, 800)
        )
        assert doc["cost_usd"] != pytest.approx(
            _estimate_cost("claude-sonnet-5", 1500, 80, 400, 800)
        )

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


class TestGatewayRetryAndMissingKey:
    """gateway._get_client error path + gateway.complete retry logic.

    Why these matter: Anthropic returns 429 / 5xx semi-routinely
    under high concurrency or model-pool failover. The retry path
    is the difference between "the user sees a transient blip"
    and "the user sees a 502 every time the model pool warms".
    Pin both the retry-then-succeed path and the eventual-raise
    so a regression in MAX_RETRIES or the status-code list
    surfaces as a test failure, not a paged incident."""

    @pytest.fixture(autouse=True)
    async def _setup(self):
        await Database.connect(settings.db_dsn, settings.db_name)
        await Database.get_db()[LLM_USAGE_COLLECTION].delete_many({})
        yield
        await Database.disconnect()

    @staticmethod
    def _make_fake_response():
        """A _FakeMessage that mimics the Anthropic SDK's success
        shape — returned after retries succeed."""
        from anthropic.types import TextBlock as _TB

        class _FakeUsage:
            input_tokens = 100
            output_tokens = 50
            cache_creation_input_tokens = 0
            cache_read_input_tokens = 0

        class _FakeMessage:
            content: ClassVar = [_TB(type="text", text="ok", citations=None)]
            model = "claude-opus-4-7"
            usage = _FakeUsage()
            stop_reason = "end_turn"

        return _FakeMessage()

    @staticmethod
    def _make_api_error(status_code: int):
        """Build an anthropic.APIStatusError with the given code.
        The SDK requires a real response object (not a duck-typed stub) so we
        construct one. It must come from `httpx2` — the SDK moved its HTTP
        layer there in 1.0, and an `httpx.Response` is a different class to it.
        The gateway only branches on exc.status_code, so the body is
        irrelevant."""
        import anthropic
        import httpx2

        request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
        response = httpx2.Response(status_code=status_code, request=request)
        return anthropic.APIStatusError(
            message=f"err-{status_code}",
            response=response,
            body=None,
        )

    def test_get_client_raises_when_no_api_key(self, monkeypatch):
        """_get_client → CoachNotConfigured (503 on the wire) when
        ANTHROPIC_API_KEY isn't configured. Pin so a self-host that did not
        set the env var gets a plain answer rather than a 500 deep inside
        the Anthropic SDK, and `configured()` says so up front."""
        from beats import settings as settings_module
        from beats.coach import gateway
        from beats.domain.exceptions import CoachNotConfigured

        monkeypatch.setattr(settings_module.settings, "anthropic_api_key", "")
        assert gateway.configured() is False
        with pytest.raises(CoachNotConfigured, match="ANTHROPIC_API_KEY"):
            gateway._get_client()

    async def test_complete_retries_on_429_then_succeeds(self, monkeypatch):
        """First call → 429, second call → 200. The gateway
        should retry and return the second response without
        bubbling the 429 to the caller. Pin so a transient
        rate-limit blip doesn't surface to the user."""
        from beats import settings as settings_module
        from beats.coach import gateway

        # Avoid sleeping in tests — collapse the backoff to 0.
        monkeypatch.setattr(gateway, "BASE_DELAY_S", 0.0)
        # Settings need a fake API key so _get_client doesn't bail
        monkeypatch.setattr(settings_module.settings, "anthropic_api_key", "sk-test")

        call_count = {"n": 0}

        class _FakeMessages:
            async def create(self_inner, **_kwargs):
                call_count["n"] += 1
                if call_count["n"] == 1:
                    raise self.__class__._make_api_error(429)
                return self.__class__._make_fake_response()

        class _FakeClient:
            messages = _FakeMessages()

        monkeypatch.setattr(gateway, "_get_client", lambda: _FakeClient())

        result = await gateway.complete(
            user_id="user-1",
            system="sys",
            messages=[{"role": "user", "content": "hi"}],
            purpose="chat",
        )
        assert call_count["n"] == 2
        assert result.input_tokens == 100

    async def test_complete_retries_on_5xx_then_succeeds(self, monkeypatch):
        """503 should also trigger a retry. Pin the full retryable
        list (429/500/502/503/529) — the smaller test above pins
        429 specifically."""
        from beats import settings as settings_module
        from beats.coach import gateway

        monkeypatch.setattr(gateway, "BASE_DELAY_S", 0.0)
        monkeypatch.setattr(settings_module.settings, "anthropic_api_key", "sk-test")

        call_count = {"n": 0}

        class _FakeMessages:
            async def create(self_inner, **_kwargs):
                call_count["n"] += 1
                if call_count["n"] == 1:
                    raise self.__class__._make_api_error(503)
                return self.__class__._make_fake_response()

        class _FakeClient:
            messages = _FakeMessages()

        monkeypatch.setattr(gateway, "_get_client", lambda: _FakeClient())

        result = await gateway.complete(
            user_id="user-1",
            system="sys",
            messages=[{"role": "user", "content": "hi"}],
            purpose="chat",
        )
        assert call_count["n"] == 2
        assert result.output_tokens == 50

    async def test_complete_does_not_retry_on_401(self, monkeypatch):
        """A 401 (bad API key) is NOT in the retryable list — must
        raise immediately. Pin so a misconfigured deploy fails
        fast rather than wasting MAX_RETRIES round-trips on a
        guaranteed-failure call."""
        import anthropic

        from beats import settings as settings_module
        from beats.coach import gateway

        monkeypatch.setattr(gateway, "BASE_DELAY_S", 0.0)
        monkeypatch.setattr(settings_module.settings, "anthropic_api_key", "sk-test")

        call_count = {"n": 0}

        class _FakeMessages:
            async def create(self_inner, **_kwargs):
                call_count["n"] += 1
                raise self.__class__._make_api_error(401)

        class _FakeClient:
            messages = _FakeMessages()

        monkeypatch.setattr(gateway, "_get_client", lambda: _FakeClient())

        with pytest.raises(anthropic.APIStatusError):
            await gateway.complete(
                user_id="user-1",
                system="sys",
                messages=[{"role": "user", "content": "hi"}],
                purpose="chat",
            )
        # ONE attempt, no retries
        assert call_count["n"] == 1

    async def test_complete_eventually_raises_after_max_retries(self, monkeypatch):
        """Repeated 429s → after MAX_RETRIES attempts the gateway
        re-raises the last exception. Pin so a fully-saturated
        Anthropic backend doesn't loop forever and the caller can
        surface a 502 to the user."""
        import anthropic

        from beats import settings as settings_module
        from beats.coach import gateway

        monkeypatch.setattr(gateway, "BASE_DELAY_S", 0.0)
        monkeypatch.setattr(settings_module.settings, "anthropic_api_key", "sk-test")

        call_count = {"n": 0}

        class _FakeMessages:
            async def create(self_inner, **_kwargs):
                call_count["n"] += 1
                raise self.__class__._make_api_error(429)

        class _FakeClient:
            messages = _FakeMessages()

        monkeypatch.setattr(gateway, "_get_client", lambda: _FakeClient())

        with pytest.raises(anthropic.APIStatusError):
            await gateway.complete(
                user_id="user-1",
                system="sys",
                messages=[{"role": "user", "content": "hi"}],
                purpose="chat",
            )
        # Exactly MAX_RETRIES attempts (no more, no fewer)
        assert call_count["n"] == gateway.MAX_RETRIES
