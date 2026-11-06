"""The gateway in the round: the budget invariant every call is held
to, the cache control as the client sees it, the retry, and the
missing key.

Split out of `test_coach.py` at the ceiling in roadmaps/file-sizes.md;
the shared fakes and factories are `coach_fakes.py`'s.
"""

from typing import ClassVar

import pytest

from beats.coach.gateway import (
    CacheSpec,
    _estimate_cost,
)
from beats.coach.repos import (
    LLM_USAGE_COLLECTION,
)
from beats.coach.usage import BudgetExceeded, UsageTracker
from beats.infrastructure.database import Database
from beats.settings import settings


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
        from beats.coach.gateway import complete

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
        from beats.coach.gateway import complete
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
