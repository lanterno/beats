"""The GitHub and Google Calendar integrations: the auth URL, the code
exchange, the token refresh, the fetch and the disconnect.

Split out of `test_domain.py` at the ceiling in roadmaps/file-sizes.md;
the shared fakes and factories are `domain_fakes.py`'s.
"""

from datetime import UTC, date, datetime, timedelta

from beats.domain_fakes import (
    _calendar_settings,
    _FakeCalendarIntegrationRepo,
    _FakeGitHubIntegrationRepo,
    _FakeHTTPResponse,
    _github_settings,
    _no_op_raise_for_status,
    _patch_httpx,
    _patch_httpx_callable,
)


class TestGitHubAuthUrl:
    """get_auth_url builds the OAuth consent URL. Pin client_id +
    redirect_uri + scope — same risk profile as the Fitbit URL test
    (any missing param → silent rejection)."""

    def test_includes_client_id_redirect_and_scope(self, monkeypatch):
        from beats.domain.github import GitHubService

        svc = GitHubService(_github_settings(monkeypatch), _FakeGitHubIntegrationRepo())
        url = svc.get_auth_url()
        assert url.startswith("https://github.com/login/oauth/authorize?")
        assert "client_id=cid-gh" in url
        assert "redirect_uri=https%3A%2F%2Fbeats.test%2Foauth%2Fgithub" in url
        # scope = "repo:status read:user" — pin both tokens
        assert "repo" in url
        assert "user" in url


class TestGitHubExchangeCode:
    """exchange_code is a TWO-step flow: POST /access_token then
    GET /user. Both must succeed for the integration to land with
    the user's login. The user-info fetch is wrapped in try/except
    so a temporary GitHub outage on /user doesn't block the
    OAuth callback."""

    async def test_persists_token_and_username_on_happy_path(self, monkeypatch):
        from beats.domain.github import GitHubService

        def handler(method, url, params):
            if "access_token" in url:
                return _FakeHTTPResponse(200, {"access_token": "gho_abc123"})
            if "/user" in url:
                return _FakeHTTPResponse(200, {"login": "ahmed"})
            return _FakeHTTPResponse(404, {})

        _patch_httpx_callable(monkeypatch, handler)
        monkeypatch.setattr(
            _FakeHTTPResponse, "raise_for_status", _no_op_raise_for_status, raising=False
        )

        repo = _FakeGitHubIntegrationRepo()
        svc = GitHubService(_github_settings(monkeypatch), repo)
        integration = await svc.exchange_code("auth-code")
        assert integration.access_token == "gho_abc123"
        assert integration.github_username == "ahmed"
        assert (await repo.get()).github_username == "ahmed"

    async def test_user_endpoint_failure_still_persists_with_empty_username(self, monkeypatch):
        """A 5xx (or any exception) from /user should not block the
        OAuth callback — pin so a temporary GitHub outage during
        sign-in doesn't trap the user in an "auth failed" loop.
        We persist the token with empty username; subsequent calls
        can fill it in."""
        from beats.domain.github import GitHubService

        def handler(method, url, params):
            if "access_token" in url:
                return _FakeHTTPResponse(200, {"access_token": "gho_xyz"})
            if "/user" in url:
                # 500-style error wrapped via raise_for_status
                return _FakeHTTPResponse(500, {"message": "server error"})
            return _FakeHTTPResponse(404, {})

        _patch_httpx_callable(monkeypatch, handler)
        monkeypatch.setattr(
            _FakeHTTPResponse, "raise_for_status", _no_op_raise_for_status, raising=False
        )

        repo = _FakeGitHubIntegrationRepo()
        svc = GitHubService(_github_settings(monkeypatch), repo)
        integration = await svc.exchange_code("auth-code")
        assert integration.access_token == "gho_xyz"
        assert integration.github_username == ""


class TestGitHubFetchCommitCounts:
    """fetch_commit_counts paginates GitHub's /repos/:name/commits
    endpoint and aggregates by day. Three risks pinned:
      1. Returns [] (not None / not raises) when not connected
      2. Aggregation key is the YYYY-MM-DD prefix of the commit
         author date — drift would scatter commits across keys
      3. Pagination terminates: we stop on empty results or when a
         page has < 100 items. A regression that paginated forever
         would burn the user's GitHub rate limit on every dashboard
         load"""

    async def test_no_integration_returns_empty(self, monkeypatch):
        from beats.domain.github import GitHubService

        _patch_httpx_callable(
            monkeypatch,
            lambda *a, **kw: (_ for _ in ()).throw(
                RuntimeError("HTTP should not be called without integration")
            ),
        )
        svc = GitHubService(_github_settings(monkeypatch), _FakeGitHubIntegrationRepo(None))
        result = await svc.fetch_commit_counts("a/b", date(2026, 4, 1), date(2026, 4, 7))
        assert result == []

    async def test_empty_access_token_returns_empty(self, monkeypatch):
        """An integration row with an empty access_token (e.g.
        partial OAuth callback) is treated as "not connected".
        Pin so we don't fire requests with `Bearer ` (empty token)."""
        from beats.domain.github import GitHubService
        from beats.domain.models import GitHubIntegration

        _patch_httpx_callable(
            monkeypatch,
            lambda *a, **kw: (_ for _ in ()).throw(
                RuntimeError("HTTP should not be called for empty token")
            ),
        )
        svc = GitHubService(
            _github_settings(monkeypatch),
            _FakeGitHubIntegrationRepo(integration=GitHubIntegration(access_token="")),
        )
        result = await svc.fetch_commit_counts("a/b", date(2026, 4, 1), date(2026, 4, 7))
        assert result == []

    async def test_aggregates_commits_by_day_sorted(self, monkeypatch):
        """Three commits across two days → two output rows sorted
        ascending. Pin the YYYY-MM-DD prefix slice [:10]."""
        from beats.domain.github import GitHubService
        from beats.domain.models import GitHubIntegration

        commits = [
            {"commit": {"author": {"date": "2026-04-02T10:30:00Z"}}},
            {"commit": {"author": {"date": "2026-04-01T09:15:00Z"}}},
            {"commit": {"author": {"date": "2026-04-02T16:45:00Z"}}},
        ]

        def handler(method, url, params):
            if "/commits" in url:
                # Page 1 returns the commits, page 2 empty (terminates)
                if params.get("page", 1) == 1:
                    return _FakeHTTPResponse(200, commits)
                return _FakeHTTPResponse(200, [])
            return _FakeHTTPResponse(404, {})

        _patch_httpx_callable(monkeypatch, handler)
        monkeypatch.setattr(
            _FakeHTTPResponse, "raise_for_status", _no_op_raise_for_status, raising=False
        )

        svc = GitHubService(
            _github_settings(monkeypatch),
            _FakeGitHubIntegrationRepo(integration=GitHubIntegration(access_token="gho_x")),
        )
        result = await svc.fetch_commit_counts("ahmed/beats", date(2026, 4, 1), date(2026, 4, 7))
        assert result == [
            {"date": "2026-04-01", "commit_count": 1},
            {"date": "2026-04-02", "commit_count": 2},
        ]

    async def test_paginates_until_short_page(self, monkeypatch):
        """A first page with exactly 100 items triggers a follow-up
        request. The follow-up returning < 100 items terminates
        the loop. Pin both branches — without this, a user with
        100+ commits would silently lose every commit past page 1."""
        from beats.domain.github import GitHubService
        from beats.domain.models import GitHubIntegration

        # Page 1: 100 commits all on 2026-04-01
        page_1 = [{"commit": {"author": {"date": "2026-04-01T09:00:00Z"}}}] * 100
        # Page 2: 5 commits on 2026-04-02
        page_2 = [{"commit": {"author": {"date": "2026-04-02T10:00:00Z"}}}] * 5

        def handler(method, url, params):
            if "/commits" in url:
                p = params.get("page", 1)
                if p == 1:
                    return _FakeHTTPResponse(200, page_1)
                if p == 2:
                    return _FakeHTTPResponse(200, page_2)
                # Should not reach here
                return _FakeHTTPResponse(500, {})
            return _FakeHTTPResponse(404, {})

        _patch_httpx_callable(monkeypatch, handler)
        monkeypatch.setattr(
            _FakeHTTPResponse, "raise_for_status", _no_op_raise_for_status, raising=False
        )

        svc = GitHubService(
            _github_settings(monkeypatch),
            _FakeGitHubIntegrationRepo(integration=GitHubIntegration(access_token="gho_x")),
        )
        result = await svc.fetch_commit_counts("ahmed/beats", date(2026, 4, 1), date(2026, 4, 7))
        assert result == [
            {"date": "2026-04-01", "commit_count": 100},
            {"date": "2026-04-02", "commit_count": 5},
        ]

    async def test_exception_during_fetch_returns_partial(self, monkeypatch):
        """A network error during pagination breaks the loop
        cleanly and returns whatever was collected so far. Pin the
        partial-success contract — better to show the user some
        data than to 500 the whole dashboard."""
        from beats.domain.github import GitHubService
        from beats.domain.models import GitHubIntegration

        page_1 = [{"commit": {"author": {"date": "2026-04-01T09:00:00Z"}}}] * 100

        def handler(method, url, params):
            if "/commits" in url:
                p = params.get("page", 1)
                if p == 1:
                    return _FakeHTTPResponse(200, page_1)
                # Page 2 → error
                import httpx

                return httpx.ConnectError("network down")
            return _FakeHTTPResponse(404, {})

        _patch_httpx_callable(monkeypatch, handler)
        monkeypatch.setattr(
            _FakeHTTPResponse, "raise_for_status", _no_op_raise_for_status, raising=False
        )

        svc = GitHubService(
            _github_settings(monkeypatch),
            _FakeGitHubIntegrationRepo(integration=GitHubIntegration(access_token="gho_x")),
        )
        result = await svc.fetch_commit_counts("ahmed/beats", date(2026, 4, 1), date(2026, 4, 7))
        assert result == [{"date": "2026-04-01", "commit_count": 100}]


class TestGitHubDisconnect:
    async def test_disconnect_returns_bool(self, monkeypatch):
        from beats.domain.github import GitHubService
        from beats.domain.models import GitHubIntegration

        svc_full = GitHubService(
            _github_settings(monkeypatch),
            _FakeGitHubIntegrationRepo(integration=GitHubIntegration(access_token="gho")),
        )
        assert await svc_full.disconnect() is True

        svc_empty = GitHubService(_github_settings(monkeypatch), _FakeGitHubIntegrationRepo(None))
        assert await svc_empty.disconnect() is False


# Calendar Service — Google Calendar OAuth + event fetch


class TestCalendarAuthUrl:
    """get_auth_url builds the Google OAuth consent URL. Two
    parameters here are the load-bearing pieces: access_type=offline
    + prompt=consent. Without them, Google does NOT return a
    refresh_token, and the integration breaks the moment the access
    token expires (typically 1 hour later)."""

    def test_includes_offline_access_and_consent_prompt(self, monkeypatch):
        from beats.domain.calendar import CalendarService

        svc = CalendarService(_calendar_settings(monkeypatch), _FakeCalendarIntegrationRepo())
        url = svc.get_auth_url()
        assert url.startswith("https://accounts.google.com/o/oauth2/v2/auth?")
        assert "client_id=cid-g" in url
        assert "redirect_uri=https%3A%2F%2Fbeats.test%2Foauth%2Fgoogle" in url
        assert "response_type=code" in url
        # The two pieces that ensure a refresh_token comes back:
        assert "access_type=offline" in url
        assert "prompt=consent" in url
        # Calendar read-only scope
        assert "calendar.events.readonly" in url


class TestCalendarExchangeCode:
    """exchange_code POSTs the auth code → persists access_token,
    refresh_token, token_expiry."""

    async def test_persists_tokens_with_expiry(self, monkeypatch):
        from beats.domain.calendar import CalendarService

        _patch_httpx(
            monkeypatch,
            {
                "oauth2.googleapis.com/token": _FakeHTTPResponse(
                    200,
                    {
                        "access_token": "ya29-fresh",
                        "refresh_token": "1//rt-google",
                        "expires_in": 3600,
                    },
                )
            },
        )
        monkeypatch.setattr(
            _FakeHTTPResponse, "raise_for_status", _no_op_raise_for_status, raising=False
        )

        repo = _FakeCalendarIntegrationRepo()
        svc = CalendarService(_calendar_settings(monkeypatch), repo)
        before = datetime.now(UTC)
        integration = await svc.exchange_code("auth-code")
        after = datetime.now(UTC)

        assert integration.access_token == "ya29-fresh"
        assert integration.refresh_token == "1//rt-google"
        # token_expiry ≈ now + 3600 sec
        assert integration.token_expiry is not None
        expiry = integration.token_expiry
        assert before + timedelta(seconds=3599) <= expiry
        assert expiry <= after + timedelta(seconds=3601)
        assert (await repo.get()).access_token == "ya29-fresh"


class TestCalendarEnsureFreshToken:
    """_ensure_fresh_token has THREE branches:
      1. Token still valid → return as-is, no HTTP
      2. Expired but no refresh_token → return as-is (don't 401
         on a refresh attempt that's guaranteed to fail)
      3. Expired with refresh_token → POST refresh grant, persist

    Branch 2 is calendar-specific — Fitbit doesn't have it. Pin
    so a regression doesn't fire a refresh request that would burn
    a request slot for no purpose."""

    async def test_returns_same_when_not_expired(self, monkeypatch):
        from beats.domain.calendar import CalendarService
        from beats.domain.models import CalendarIntegration

        _patch_httpx(monkeypatch, {"": RuntimeError("should not refresh")})

        future = datetime.now(UTC) + timedelta(hours=1)
        existing = CalendarIntegration(
            access_token="ya29",
            refresh_token="1//rt",
            token_expiry=future,
        )
        svc = CalendarService(
            _calendar_settings(monkeypatch),
            _FakeCalendarIntegrationRepo(integration=existing),
        )
        result = await svc._ensure_fresh_token(existing)
        assert result.access_token == "ya29"

    async def test_returns_same_when_expired_but_no_refresh_token(self, monkeypatch):
        """No refresh_token → return integration unchanged, NO HTTP
        call. Pin so a regression doesn't fire `grant_type=
        refresh_token` with an empty refresh_token (Google would
        400; user has to re-auth anyway)."""
        from beats.domain.calendar import CalendarService
        from beats.domain.models import CalendarIntegration

        _patch_httpx(
            monkeypatch,
            {"": RuntimeError("must not refresh without a refresh_token")},
        )

        past = datetime.now(UTC) - timedelta(hours=2)
        no_refresh = CalendarIntegration(
            access_token="ya29-OLD",
            refresh_token="",
            token_expiry=past,
        )
        svc = CalendarService(
            _calendar_settings(monkeypatch),
            _FakeCalendarIntegrationRepo(integration=no_refresh),
        )
        result = await svc._ensure_fresh_token(no_refresh)
        assert result.access_token == "ya29-OLD"

    async def test_refreshes_when_expired_with_refresh_token(self, monkeypatch):
        from beats.domain.calendar import CalendarService
        from beats.domain.models import CalendarIntegration

        _patch_httpx(
            monkeypatch,
            {
                "oauth2.googleapis.com/token": _FakeHTTPResponse(
                    200,
                    {"access_token": "ya29-NEW", "expires_in": 3600},
                )
            },
        )
        monkeypatch.setattr(
            _FakeHTTPResponse, "raise_for_status", _no_op_raise_for_status, raising=False
        )

        past = datetime.now(UTC) - timedelta(hours=2)
        stale = CalendarIntegration(
            access_token="ya29-OLD",
            refresh_token="1//rt-keep",
            token_expiry=past,
        )
        repo = _FakeCalendarIntegrationRepo(integration=stale)
        svc = CalendarService(_calendar_settings(monkeypatch), repo)
        refreshed = await svc._ensure_fresh_token(stale)
        assert refreshed.access_token == "ya29-NEW"
        assert (await repo.get()).access_token == "ya29-NEW"


class TestCalendarFetchEvents:
    """fetch_events iterates calendar_ids (a user can have multiple
    calendars connected) and aggregates their events. Two distinct
    risks vs Fitbit/GitHub:
      1. all-day events use {"date": "YYYY-MM-DD"} not {"dateTime"} —
         pin the all_day boolean derivation
      2. one calendar's failure must not drop the others"""

    async def test_no_integration_returns_empty(self, monkeypatch):
        from beats.domain.calendar import CalendarService

        _patch_httpx(
            monkeypatch,
            {"": RuntimeError("must not fetch without integration")},
        )
        svc = CalendarService(
            _calendar_settings(monkeypatch),
            _FakeCalendarIntegrationRepo(None),
        )
        result = await svc.fetch_events(
            datetime(2026, 4, 1, tzinfo=UTC),
            datetime(2026, 4, 2, tzinfo=UTC),
        )
        assert result == []

    async def test_disabled_integration_returns_empty(self, monkeypatch):
        """integration.enabled=False → don't fetch. Pin so the
        Settings → "pause" toggle takes effect immediately rather
        than requiring a full disconnect."""
        from beats.domain.calendar import CalendarService
        from beats.domain.models import CalendarIntegration

        _patch_httpx(
            monkeypatch,
            {"": RuntimeError("must not fetch when disabled")},
        )
        future = datetime.now(UTC) + timedelta(hours=1)
        disabled = CalendarIntegration(
            access_token="ya29",
            refresh_token="rt",
            token_expiry=future,
            enabled=False,
        )
        svc = CalendarService(
            _calendar_settings(monkeypatch),
            _FakeCalendarIntegrationRepo(integration=disabled),
        )
        result = await svc.fetch_events(
            datetime(2026, 4, 1, tzinfo=UTC),
            datetime(2026, 4, 2, tzinfo=UTC),
        )
        assert result == []

    async def test_returns_timed_event_with_all_day_false(self, monkeypatch):
        """Event with `dateTime` → all_day=False, start/end use the
        dateTime value verbatim."""
        from beats.domain.calendar import CalendarService
        from beats.domain.models import CalendarIntegration

        _patch_httpx(
            monkeypatch,
            {
                "/events": _FakeHTTPResponse(
                    200,
                    {
                        "items": [
                            {
                                "summary": "Standup",
                                "start": {"dateTime": "2026-04-01T09:00:00Z"},
                                "end": {"dateTime": "2026-04-01T09:30:00Z"},
                            }
                        ]
                    },
                )
            },
        )
        monkeypatch.setattr(
            _FakeHTTPResponse, "raise_for_status", _no_op_raise_for_status, raising=False
        )

        future = datetime.now(UTC) + timedelta(hours=1)
        svc = CalendarService(
            _calendar_settings(monkeypatch),
            _FakeCalendarIntegrationRepo(
                integration=CalendarIntegration(
                    access_token="ya29",
                    refresh_token="rt",
                    token_expiry=future,
                )
            ),
        )
        events = await svc.fetch_events(
            datetime(2026, 4, 1, tzinfo=UTC),
            datetime(2026, 4, 2, tzinfo=UTC),
        )
        assert len(events) == 1
        e = events[0]
        assert e["summary"] == "Standup"
        assert e["start"] == "2026-04-01T09:00:00Z"
        assert e["end"] == "2026-04-01T09:30:00Z"
        assert e["all_day"] is False

    async def test_returns_all_day_event_correctly(self, monkeypatch):
        """Event with `date` (not `dateTime`) → all_day=True. Pin
        so the calendar view doesn't render an all-day event as
        "12:00 AM" (the timezone-zero artifact of treating
        "2026-04-01" as a datetime)."""
        from beats.domain.calendar import CalendarService
        from beats.domain.models import CalendarIntegration

        _patch_httpx(
            monkeypatch,
            {
                "/events": _FakeHTTPResponse(
                    200,
                    {
                        "items": [
                            {
                                "summary": "Holiday",
                                "start": {"date": "2026-04-01"},
                                "end": {"date": "2026-04-02"},
                            }
                        ]
                    },
                )
            },
        )
        monkeypatch.setattr(
            _FakeHTTPResponse, "raise_for_status", _no_op_raise_for_status, raising=False
        )

        future = datetime.now(UTC) + timedelta(hours=1)
        svc = CalendarService(
            _calendar_settings(monkeypatch),
            _FakeCalendarIntegrationRepo(
                integration=CalendarIntegration(
                    access_token="ya29",
                    refresh_token="rt",
                    token_expiry=future,
                )
            ),
        )
        events = await svc.fetch_events(
            datetime(2026, 4, 1, tzinfo=UTC),
            datetime(2026, 4, 2, tzinfo=UTC),
        )
        assert events == [
            {
                "summary": "Holiday",
                "start": "2026-04-01",
                "end": "2026-04-02",
                "all_day": True,
            }
        ]

    async def test_event_without_summary_falls_back_to_no_title(self, monkeypatch):
        """Calendar events sometimes have no title (busy blocks,
        declined invites). Pin the "(No title)" fallback so the
        UI doesn't render a literal empty string."""
        from beats.domain.calendar import CalendarService
        from beats.domain.models import CalendarIntegration

        _patch_httpx(
            monkeypatch,
            {
                "/events": _FakeHTTPResponse(
                    200,
                    {
                        "items": [
                            {
                                "start": {"dateTime": "2026-04-01T10:00:00Z"},
                                "end": {"dateTime": "2026-04-01T11:00:00Z"},
                            }
                        ]
                    },
                )
            },
        )
        monkeypatch.setattr(
            _FakeHTTPResponse, "raise_for_status", _no_op_raise_for_status, raising=False
        )

        future = datetime.now(UTC) + timedelta(hours=1)
        svc = CalendarService(
            _calendar_settings(monkeypatch),
            _FakeCalendarIntegrationRepo(
                integration=CalendarIntegration(
                    access_token="ya29",
                    refresh_token="rt",
                    token_expiry=future,
                )
            ),
        )
        events = await svc.fetch_events(
            datetime(2026, 4, 1, tzinfo=UTC),
            datetime(2026, 4, 2, tzinfo=UTC),
        )
        assert events[0]["summary"] == "(No title)"

    async def test_iterates_multiple_calendars(self, monkeypatch):
        """User has primary + a second calendar — both are queried
        and their events appended. Pin so a regression doesn't only
        fetch the first calendar in the list."""
        from beats.domain.calendar import CalendarService
        from beats.domain.models import CalendarIntegration

        call_log: list[str] = []

        def handler(method, url, params):
            call_log.append(url)
            if "primary" in url:
                return _FakeHTTPResponse(
                    200,
                    {
                        "items": [
                            {
                                "summary": "From primary",
                                "start": {"dateTime": "2026-04-01T09:00:00Z"},
                                "end": {"dateTime": "2026-04-01T10:00:00Z"},
                            }
                        ]
                    },
                )
            if "work" in url:
                return _FakeHTTPResponse(
                    200,
                    {
                        "items": [
                            {
                                "summary": "From work",
                                "start": {"dateTime": "2026-04-01T11:00:00Z"},
                                "end": {"dateTime": "2026-04-01T12:00:00Z"},
                            }
                        ]
                    },
                )
            return _FakeHTTPResponse(404, {})

        _patch_httpx_callable(monkeypatch, handler)
        monkeypatch.setattr(
            _FakeHTTPResponse, "raise_for_status", _no_op_raise_for_status, raising=False
        )

        future = datetime.now(UTC) + timedelta(hours=1)
        svc = CalendarService(
            _calendar_settings(monkeypatch),
            _FakeCalendarIntegrationRepo(
                integration=CalendarIntegration(
                    access_token="ya29",
                    refresh_token="rt",
                    token_expiry=future,
                    calendar_ids=["primary", "work@example.com"],
                )
            ),
        )
        events = await svc.fetch_events(
            datetime(2026, 4, 1, tzinfo=UTC),
            datetime(2026, 4, 2, tzinfo=UTC),
        )
        summaries = [e["summary"] for e in events]
        assert "From primary" in summaries
        assert "From work" in summaries
        assert len(call_log) == 2

    async def test_one_calendar_failure_does_not_drop_others(self, monkeypatch):
        """Calendar A errors, B succeeds → result has B's events.
        Pin per-calendar resilience so a single revoked calendar
        permission doesn't kill the whole event panel."""
        import httpx

        from beats.domain.calendar import CalendarService
        from beats.domain.models import CalendarIntegration

        def handler(method, url, params):
            if "primary" in url:
                return httpx.ConnectError("permission revoked")
            if "work" in url:
                return _FakeHTTPResponse(
                    200,
                    {
                        "items": [
                            {
                                "summary": "Survivor",
                                "start": {"dateTime": "2026-04-01T09:00:00Z"},
                                "end": {"dateTime": "2026-04-01T10:00:00Z"},
                            }
                        ]
                    },
                )
            return _FakeHTTPResponse(404, {})

        _patch_httpx_callable(monkeypatch, handler)
        monkeypatch.setattr(
            _FakeHTTPResponse, "raise_for_status", _no_op_raise_for_status, raising=False
        )

        future = datetime.now(UTC) + timedelta(hours=1)
        svc = CalendarService(
            _calendar_settings(monkeypatch),
            _FakeCalendarIntegrationRepo(
                integration=CalendarIntegration(
                    access_token="ya29",
                    refresh_token="rt",
                    token_expiry=future,
                    calendar_ids=["primary", "work@example.com"],
                )
            ),
        )
        events = await svc.fetch_events(
            datetime(2026, 4, 1, tzinfo=UTC),
            datetime(2026, 4, 2, tzinfo=UTC),
        )
        assert [e["summary"] for e in events] == ["Survivor"]


class TestCalendarDisconnect:
    async def test_disconnect_returns_bool(self, monkeypatch):
        from beats.domain.calendar import CalendarService
        from beats.domain.models import CalendarIntegration

        svc_full = CalendarService(
            _calendar_settings(monkeypatch),
            _FakeCalendarIntegrationRepo(integration=CalendarIntegration(access_token="ya29")),
        )
        assert await svc_full.disconnect() is True

        svc_empty = CalendarService(
            _calendar_settings(monkeypatch),
            _FakeCalendarIntegrationRepo(None),
        )
        assert await svc_empty.disconnect() is False


# Chronotype detector — Flow Score × time-of-day
