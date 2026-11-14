"""The Oura and Fitbit integrations: the connect, the token refresh, the
daily fetch and the disconnect.

Split out of `test_domain.py` at the size ceiling (CLAUDE.md § Conventions);
the shared fakes and factories are `domain_fakes.py`'s.
"""

from datetime import UTC, date, datetime, timedelta

import pytest

from beats.domain.exceptions import (
    DomainException,
)
from beats.domain_fakes import (
    _FakeFitbitIntegrationRepo,
    _FakeHTTPResponse,
    _FakeOuraIntegrationRepo,
    _fitbit_settings,
    _no_op_raise_for_status,
    _patch_httpx,
)


class TestOuraServiceConnect:
    """OuraService.connect validates a PAT against Oura's API
    before persisting it. Pin the validate-then-persist sequence
    so a bad token can't be silently saved."""

    async def test_valid_pat_persists_integration(self, monkeypatch):
        from beats.domain.oura import OuraService

        _patch_httpx(
            monkeypatch,
            {"personal_info": _FakeHTTPResponse(200, {"id": "oura-user-42"})},
        )
        repo = _FakeOuraIntegrationRepo()
        svc = OuraService(repo)
        integration = await svc.connect("pat-good")
        assert integration.access_token == "pat-good"
        assert integration.oura_user_id == "oura-user-42"
        # Pinned: actually upserted into the repo, not just returned
        assert (await repo.get()).access_token == "pat-good"

    async def test_invalid_pat_raises_and_does_not_persist(self, monkeypatch):
        """A 401 from /personal_info → DomainException, AND the
        repo stays empty. Pin the no-side-effects-on-failure
        invariant — the user shouldn't see a "connected" badge if
        the token never validated."""
        from beats.domain.oura import OuraService

        _patch_httpx(
            monkeypatch,
            {"personal_info": _FakeHTTPResponse(401, {"error": "unauthorized"})},
        )
        repo = _FakeOuraIntegrationRepo()
        svc = OuraService(repo)
        with pytest.raises(DomainException):
            await svc.connect("pat-bad")
        assert await repo.get() is None


class TestOuraServiceFetchDaily:
    """fetch_daily aggregates sleep/readiness/HRV from three Oura
    endpoints. Each call is wrapped in its own try/except so a
    5xx on readiness shouldn't drop sleep data.

    Risk: a regression that surfaces an HTTP exception from one
    endpoint would silently zero out the entire day's biometrics.
    Pin per-endpoint resilience."""

    async def test_no_integration_returns_empty(self, monkeypatch):
        """When the user hasn't connected Oura, fetch_daily must
        return {} without making any HTTP calls. Pin so a
        regression doesn't fire requests for not-connected users."""
        from beats.domain.oura import OuraService

        _patch_httpx(
            monkeypatch,
            {"": RuntimeError("should not have called HTTP without integration")},
        )
        repo = _FakeOuraIntegrationRepo(integration=None)
        svc = OuraService(repo)
        result = await svc.fetch_daily(date(2026, 4, 1))
        assert result == {}

    async def test_aggregates_sleep_readiness_and_hrv(self, monkeypatch):
        """Happy path: all three endpoints return data → result
        contains sleep_minutes, sleep_efficiency, readiness_score,
        hrv_ms, resting_hr_bpm. Pin the field names — the
        biometrics ingest pipeline binds to these keys."""
        from beats.domain.models import OuraIntegration
        from beats.domain.oura import OuraService

        _patch_httpx(
            monkeypatch,
            {
                "daily_sleep": _FakeHTTPResponse(
                    200,
                    {
                        "data": [
                            {
                                "score": 85,
                                "contributors": {"total_sleep": 27000},
                            }
                        ]
                    },
                ),
                "daily_readiness": _FakeHTTPResponse(200, {"data": [{"score": 78}]}),
                "/sleep": _FakeHTTPResponse(
                    200,
                    {"data": [{"average_hrv": 45.5, "lowest_heart_rate": 52}]},
                ),
            },
        )
        repo = _FakeOuraIntegrationRepo(
            integration=OuraIntegration(access_token="pat", oura_user_id="u1")
        )
        svc = OuraService(repo)
        result = await svc.fetch_daily(date(2026, 4, 1))
        assert result["source"] == "oura"
        assert result["sleep_minutes"] == 450  # 27000 / 60
        assert result["sleep_efficiency"] == 0.85
        assert result["readiness_score"] == 78
        assert result["hrv_ms"] == 45.5
        assert result["resting_hr_bpm"] == 52

    async def test_readiness_failure_does_not_drop_sleep(self, monkeypatch):
        """Readiness endpoint raises httpx.HTTPError → sleep data
        still lands. Pin per-endpoint try/except so a flaky Oura
        backend can't zero out the user's whole day."""
        import httpx

        from beats.domain.models import OuraIntegration
        from beats.domain.oura import OuraService

        _patch_httpx(
            monkeypatch,
            {
                "daily_sleep": _FakeHTTPResponse(
                    200,
                    {
                        "data": [
                            {
                                "score": 90,
                                "contributors": {"total_sleep": 28800},
                            }
                        ]
                    },
                ),
                "daily_readiness": httpx.ConnectError("network down"),
                "/sleep": _FakeHTTPResponse(200, {"data": []}),
            },
        )
        repo = _FakeOuraIntegrationRepo(integration=OuraIntegration(access_token="pat"))
        svc = OuraService(repo)
        result = await svc.fetch_daily(date(2026, 4, 1))
        assert result["sleep_minutes"] == 480
        assert "readiness_score" not in result

    async def test_empty_response_arrays_yield_no_keys(self, monkeypatch):
        """Each endpoint returns {"data": []} (no record for the
        date) — result has only `source` and `date`. Pin so a
        no-data day doesn't produce phantom zero values that
        masquerade as real measurements."""
        from beats.domain.models import OuraIntegration
        from beats.domain.oura import OuraService

        _patch_httpx(
            monkeypatch,
            {
                "daily_sleep": _FakeHTTPResponse(200, {"data": []}),
                "daily_readiness": _FakeHTTPResponse(200, {"data": []}),
                "/sleep": _FakeHTTPResponse(200, {"data": []}),
            },
        )
        repo = _FakeOuraIntegrationRepo(integration=OuraIntegration(access_token="pat"))
        svc = OuraService(repo)
        target = date(2026, 4, 1)
        result = await svc.fetch_daily(target)
        assert result == {"source": "oura", "date": target}


class TestOuraServiceDisconnect:
    """disconnect drops the stored integration. Pin the bool
    contract — the API route maps True/False to 200/404."""

    async def test_disconnect_returns_true_when_present(self):
        from beats.domain.models import OuraIntegration
        from beats.domain.oura import OuraService

        repo = _FakeOuraIntegrationRepo(integration=OuraIntegration(access_token="pat"))
        svc = OuraService(repo)
        assert await svc.disconnect() is True
        assert await repo.get() is None

    async def test_disconnect_returns_false_when_absent(self):
        from beats.domain.oura import OuraService

        svc = OuraService(_FakeOuraIntegrationRepo(integration=None))
        assert await svc.disconnect() is False


# Fitbit Service — OAuth flow + biometric fetch with token refresh


class TestFitbitAuthUrl:
    """get_auth_url builds the OAuth consent URL deterministically.
    Pin every required parameter — Fitbit will reject the redirect
    silently if any are missing or misnamed, leaving the user on
    a "loading…" screen with no error."""

    def test_includes_client_id_redirect_response_type_and_scope(self, monkeypatch):
        from beats.domain.fitbit import FitbitService

        svc = FitbitService(_fitbit_settings(monkeypatch), _FakeFitbitIntegrationRepo())
        url = svc.get_auth_url()
        assert url.startswith("https://www.fitbit.com/oauth2/authorize?")
        assert "client_id=cid-fb" in url
        # redirect_uri is URL-encoded (colons + slashes escaped)
        assert "redirect_uri=https%3A%2F%2Fbeats.test%2Foauth%2Ffitbit" in url
        assert "response_type=code" in url
        # scope = "activity heartrate sleep" — pin the three tokens
        assert "activity" in url
        assert "heartrate" in url
        assert "sleep" in url


class TestFitbitExchangeCode:
    """exchange_code POSTs the auth code + creds to Fitbit's token
    endpoint and persists the tokens. Pin both the four-field
    persisted shape and the token_expiry math (now + expires_in)."""

    async def test_happy_path_persists_all_four_fields(self, monkeypatch):
        from beats.domain.fitbit import FitbitService

        _patch_httpx(
            monkeypatch,
            {
                "oauth2/token": _FakeHTTPResponse(
                    200,
                    {
                        "access_token": "at-fb",
                        "refresh_token": "rt-fb",
                        "expires_in": 28800,
                        "user_id": "fb-user-1",
                    },
                )
            },
        )
        monkeypatch.setattr(
            _FakeHTTPResponse, "raise_for_status", _no_op_raise_for_status, raising=False
        )

        repo = _FakeFitbitIntegrationRepo()
        svc = FitbitService(_fitbit_settings(monkeypatch), repo)
        before = datetime.now(UTC)
        integration = await svc.exchange_code("auth-code")
        after = datetime.now(UTC)

        assert integration.access_token == "at-fb"
        assert integration.refresh_token == "rt-fb"
        assert integration.fitbit_user_id == "fb-user-1"
        # token_expiry ≈ now + 28800 sec
        assert integration.token_expiry is not None
        expiry = integration.token_expiry
        assert before + timedelta(seconds=28799) <= expiry
        assert expiry <= after + timedelta(seconds=28801)
        # Persisted, not just returned
        assert (await repo.get()).access_token == "at-fb"


class TestFitbitEnsureFreshToken:
    """_ensure_fresh_token returns the integration as-is when the
    token is still valid; otherwise it refreshes via the
    refresh_token grant and persists.

    Risk: a regression here would either (a) fire a refresh on
    every request (rate-limit) or (b) skip refreshing on an
    expired token (every fetch fails)."""

    async def test_returns_same_when_not_expired(self, monkeypatch):
        """token_expiry > now → return integration unchanged, no
        HTTP call. Patched httpx raises if invoked — the test
        would fail loudly if a regression started spamming
        refreshes."""
        from beats.domain.fitbit import FitbitService
        from beats.domain.models import FitbitIntegration

        _patch_httpx(
            monkeypatch,
            {"": RuntimeError("should not refresh when token still valid")},
        )

        future = datetime.now(UTC) + timedelta(hours=2)
        existing = FitbitIntegration(
            access_token="at-current",
            refresh_token="rt",
            token_expiry=future,
        )
        repo = _FakeFitbitIntegrationRepo(integration=existing)
        svc = FitbitService(_fitbit_settings(monkeypatch), repo)
        result = await svc._ensure_fresh_token(existing)
        assert result.access_token == "at-current"

    async def test_refreshes_when_expired(self, monkeypatch):
        """token_expiry in the past → POST refresh_token grant,
        persist new access_token + token_expiry. Pin so an expired
        token doesn't silently leak through to the API call."""
        from beats.domain.fitbit import FitbitService
        from beats.domain.models import FitbitIntegration

        _patch_httpx(
            monkeypatch,
            {
                "oauth2/token": _FakeHTTPResponse(
                    200,
                    {
                        "access_token": "at-NEW",
                        "refresh_token": "rt-NEW",
                        "expires_in": 28800,
                    },
                )
            },
        )
        monkeypatch.setattr(
            _FakeHTTPResponse, "raise_for_status", _no_op_raise_for_status, raising=False
        )

        past = datetime.now(UTC) - timedelta(hours=1)
        stale = FitbitIntegration(
            access_token="at-OLD",
            refresh_token="rt-OLD",
            token_expiry=past,
        )
        repo = _FakeFitbitIntegrationRepo(integration=stale)
        svc = FitbitService(_fitbit_settings(monkeypatch), repo)
        refreshed = await svc._ensure_fresh_token(stale)
        assert refreshed.access_token == "at-NEW"
        assert refreshed.refresh_token == "rt-NEW"
        # Persisted, not just returned
        assert (await repo.get()).access_token == "at-NEW"

    async def test_refresh_preserves_existing_refresh_token_when_omitted(self, monkeypatch):
        """Fitbit sometimes omits refresh_token from the refresh
        response (when the existing one is still valid). Pin that
        we keep the existing refresh_token rather than blanking it
        — losing the refresh token would force a full re-auth."""
        from beats.domain.fitbit import FitbitService
        from beats.domain.models import FitbitIntegration

        _patch_httpx(
            monkeypatch,
            {
                "oauth2/token": _FakeHTTPResponse(
                    200,
                    {
                        "access_token": "at-NEW",
                        # No refresh_token in response
                        "expires_in": 28800,
                    },
                )
            },
        )
        monkeypatch.setattr(
            _FakeHTTPResponse, "raise_for_status", _no_op_raise_for_status, raising=False
        )

        past = datetime.now(UTC) - timedelta(hours=1)
        stale = FitbitIntegration(
            access_token="at-OLD",
            refresh_token="rt-keep",
            token_expiry=past,
        )
        repo = _FakeFitbitIntegrationRepo(integration=stale)
        svc = FitbitService(_fitbit_settings(monkeypatch), repo)
        refreshed = await svc._ensure_fresh_token(stale)
        assert refreshed.refresh_token == "rt-keep"


class TestFitbitFetchDaily:
    """fetch_daily aggregates sleep + heart rate + steps. Mirrors
    the Oura per-endpoint resilience pattern — one endpoint's
    failure must not drop another's data."""

    async def test_no_integration_returns_empty(self, monkeypatch):
        from beats.domain.fitbit import FitbitService

        _patch_httpx(
            monkeypatch,
            {"": RuntimeError("should not have called HTTP without integration")},
        )
        svc = FitbitService(_fitbit_settings(monkeypatch), _FakeFitbitIntegrationRepo(None))
        assert await svc.fetch_daily(date(2026, 4, 1)) == {}

    async def test_aggregates_sleep_hr_and_steps(self, monkeypatch):
        from beats.domain.fitbit import FitbitService
        from beats.domain.models import FitbitIntegration

        _patch_httpx(
            monkeypatch,
            {
                # Substring matches; first-match-wins. Order so the
                # most-specific routes match first.
                "/sleep/": _FakeHTTPResponse(
                    200,
                    {
                        "summary": {
                            "totalMinutesAsleep": 420,
                            "totalTimeInBed": 480,
                        }
                    },
                ),
                "/heart/": _FakeHTTPResponse(
                    200, {"activities-heart": [{"value": {"restingHeartRate": 58}}]}
                ),
                "/activities/date/": _FakeHTTPResponse(200, {"summary": {"steps": 9876}}),
            },
        )
        future = datetime.now(UTC) + timedelta(hours=2)
        repo = _FakeFitbitIntegrationRepo(
            integration=FitbitIntegration(
                access_token="at", refresh_token="rt", token_expiry=future
            )
        )
        svc = FitbitService(_fitbit_settings(monkeypatch), repo)
        result = await svc.fetch_daily(date(2026, 4, 1))
        assert result["source"] == "fitbit"
        assert result["sleep_minutes"] == 420
        assert result["sleep_efficiency"] == 420 / 480
        assert result["resting_hr_bpm"] == 58
        assert result["steps"] == 9876

    async def test_hr_failure_does_not_drop_sleep_or_steps(self, monkeypatch):
        """HR endpoint raises → sleep + steps still land. Pin
        per-endpoint resilience — a flaky Fitbit backend can't
        zero out the user's whole day."""
        import httpx

        from beats.domain.fitbit import FitbitService
        from beats.domain.models import FitbitIntegration

        _patch_httpx(
            monkeypatch,
            {
                "/sleep/": _FakeHTTPResponse(
                    200,
                    {
                        "summary": {
                            "totalMinutesAsleep": 400,
                            "totalTimeInBed": 460,
                        }
                    },
                ),
                "/heart/": httpx.ConnectError("hr down"),
                "/activities/date/": _FakeHTTPResponse(200, {"summary": {"steps": 5000}}),
            },
        )
        future = datetime.now(UTC) + timedelta(hours=2)
        repo = _FakeFitbitIntegrationRepo(
            integration=FitbitIntegration(
                access_token="at", refresh_token="rt", token_expiry=future
            )
        )
        svc = FitbitService(_fitbit_settings(monkeypatch), repo)
        result = await svc.fetch_daily(date(2026, 4, 1))
        assert result["sleep_minutes"] == 400
        assert result["steps"] == 5000
        assert "resting_hr_bpm" not in result


class TestFitbitDisconnect:
    async def test_disconnect_returns_bool(self, monkeypatch):
        from beats.domain.fitbit import FitbitService
        from beats.domain.models import FitbitIntegration

        svc_full = FitbitService(
            _fitbit_settings(monkeypatch),
            _FakeFitbitIntegrationRepo(integration=FitbitIntegration(access_token="at")),
        )
        assert await svc_full.disconnect() is True

        svc_empty = FitbitService(_fitbit_settings(monkeypatch), _FakeFitbitIntegrationRepo(None))
        assert await svc_empty.disconnect() is False


# GitHub Service — OAuth flow + commit-activity fetch with pagination
