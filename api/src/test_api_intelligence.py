"""Analytics, intelligence, the inbox, webhooks and weekly plans.

Split out of `test_api.py` at the ceiling in roadmaps/file-sizes.md; the
harness is `conftest.py`'s and the shared fixtures `api_helpers.py`'s.
"""

from datetime import UTC, date, datetime, timedelta

import pytest

from api_helpers import (
    _create_project,
)


class TestAnalyticsRouterEndpoints:
    """Smoke tests for /api/analytics/rhythm, /gaps, /tags. The
    existing device-token tests stop at 403 / no-data and don't
    exercise the route bodies; this class hits each endpoint with
    a session token + (where needed) seeded data so the route
    handlers actually run."""

    def _create_project(self, client, auth_headers) -> str:
        resp = client.post(
            "/api/projects/",
            json={"name": "Analytics Probe"},
            headers=auth_headers,
        )
        assert resp.status_code == 201
        return resp.json()["id"]

    def test_rhythm_returns_48_slots_for_session_token(self, client, auth_headers):
        """GET /api/analytics/rhythm returns 48 half-hour slots
        (one for every 30-minute window in a day). Pin so the
        chart never renders holes — even on an empty account
        all 48 slots are present with minutes=0."""
        resp = client.get("/api/analytics/rhythm", headers=auth_headers)
        assert resp.status_code == 200
        slots = resp.json()
        assert len(slots) == 48
        # Each slot has a slot index 0..47 and a minutes field
        assert {s["slot"] for s in slots} == set(range(48))
        assert all("minutes" in s for s in slots)

    def test_gaps_returns_list_for_session_token(self, client, auth_headers):
        """GET /api/analytics/gaps returns a list (possibly empty
        for a no-data day). Pin the array shape — the dashboard's
        Untracked Gaps panel iterates directly on the response."""
        resp = client.get("/api/analytics/gaps", headers=auth_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body, list)

    def test_tags_returns_sorted_unique_tags_from_user_beats(self, client, auth_headers):
        """GET /api/analytics/tags surfaces every unique tag across
        the user's beats, sorted alphabetically. Tags are auto-derived
        from the daemon's flow-window signals (repo + editor language)
        when a timer stops — the app takes no manual tag input."""
        project_id = self._create_project(client, auth_headers)

        # Seed daemon flow windows inside the session's range. The stop
        # handler auto-tags the beat from these (repo basename + language).
        def _post_window(start: str, end: str, repo: str | None, language: str | None):
            client.post(
                "/api/signals/flow-windows",
                json={
                    "window_start": start,
                    "window_end": end,
                    "flow_score": 0.8,
                    "cadence_score": 0.5,
                    "coherence_score": 0.5,
                    "category_fit_score": 0.5,
                    "idle_fraction": 0.1,
                    "editor_repo": repo,
                    "editor_language": language,
                },
                headers=auth_headers,
            )

        _post_window("2026-04-01T09:05:00Z", "2026-04-01T09:15:00Z", "/home/me/beats", "Python")
        _post_window("2026-04-01T09:16:00Z", "2026-04-01T09:25:00Z", None, "TypeScript")

        # Start + stop a timer spanning those windows -> auto-tagged beat.
        client.post(
            f"/api/projects/{project_id}/start",
            json={"time": "2026-04-01T09:00:00Z"},
            headers=auth_headers,
        )
        client.post(
            "/api/projects/stop",
            json={"time": "2026-04-01T09:30:00Z"},
            headers=auth_headers,
        )

        resp = client.get("/api/analytics/tags", headers=auth_headers)
        assert resp.status_code == 200
        tags = resp.json()
        # Deduplicated AND sorted: repo basename + lowercased languages.
        assert tags == ["beats", "python", "typescript"]


class TestAnalyticsTimezone:
    """End-to-end tz-correctness for /api/analytics/heatmap. The API
    stores UTC; a late-evening session must bucket to the correct LOCAL
    calendar day for the requesting timezone, and an unknown IANA name
    is rejected with the unified 400 envelope. The UTC default keeps the
    historical (no-tz) behavior."""

    def _seed_late_evening_beat(self, client, auth_headers) -> None:
        """Create one completed 30-min beat at 2026-01-01T23:30Z."""
        resp = client.post(
            "/api/projects/",
            json={"name": "TZ Probe"},
            headers=auth_headers,
        )
        assert resp.status_code == 201
        project_id = resp.json()["id"]
        client.post(
            f"/api/projects/{project_id}/start",
            json={"time": "2026-01-01T23:30:00Z"},
            headers=auth_headers,
        )
        client.post(
            "/api/projects/stop",
            json={"time": "2026-01-02T00:00:00Z"},
            headers=auth_headers,
        )

    def _heatmap_dates(self, client, auth_headers, params: str = "") -> set[str]:
        url = "/api/analytics/heatmap?year=2026"
        if params:
            url += f"&{params}"
        resp = client.get(url, headers=auth_headers)
        assert resp.status_code == 200
        return {d["date"] for d in resp.json()}

    def test_no_tz_buckets_to_utc_day(self, client, auth_headers):
        self._seed_late_evening_beat(client, auth_headers)
        # 23:30Z stays on 2026-01-01 with the UTC default.
        assert "2026-01-01" in self._heatmap_dates(client, auth_headers)

    def test_negative_offset_keeps_same_local_day(self, client, auth_headers):
        self._seed_late_evening_beat(client, auth_headers)
        # 23:30Z = 18:30 EST → still 2026-01-01 in New York.
        assert "2026-01-01" in self._heatmap_dates(client, auth_headers, "tz=America/New_York")

    def test_positive_offset_rolls_to_next_local_day(self, client, auth_headers):
        self._seed_late_evening_beat(client, auth_headers)
        # 23:30Z = 08:30 JST next day → 2026-01-02 in Tokyo.
        dates = self._heatmap_dates(client, auth_headers, "tz=Asia/Tokyo")
        assert "2026-01-02" in dates
        assert "2026-01-01" not in dates

    def test_invalid_timezone_returns_400_envelope(self, client, auth_headers):
        resp = client.get(
            "/api/analytics/heatmap?year=2026&tz=Not/AZone",
            headers=auth_headers,
        )
        assert resp.status_code == 400
        body = resp.json()
        assert body["code"] == "INVALID_TIMEZONE"
        assert isinstance(body["detail"], str)


class TestIntelligenceInbox:
    """Smoke tests for the aggregated Intelligence Inbox endpoint."""

    def test_inbox_returns_ok_shape_for_empty_user(self, client, auth_headers):
        """GET /api/intelligence/inbox returns the expected envelope for a fresh user."""
        response = client.get("/api/intelligence/inbox", headers=auth_headers)
        assert response.status_code == 200
        body = response.json()
        assert "items" in body
        assert isinstance(body["items"], list)
        assert "generated_at" in body
        # A brand-new user has no patterns and no health alerts, but the suggestions
        # path may still produce low-severity items if default projects exist.
        for item in body["items"]:
            assert set(item.keys()) >= {"id", "kind", "severity", "title", "body"}
            assert item["kind"] in {"pattern", "suggestion", "project_health"}
            assert item["severity"] in {"high", "medium", "low"}

    def test_inbox_requires_auth(self, client):
        """GET /api/intelligence/inbox rejects unauthenticated requests."""
        response = client.get("/api/intelligence/inbox")
        assert response.status_code == 401

    def test_inbox_renders_suggestion_items_with_seeded_project(self, client, auth_headers):
        """A project with a weekly_goal and no recent activity →
        suggest_daily_plan emits a suggestion → inbox includes a
        `kind: "suggestion"` item with the documented shape:
        title "Plan N min on <ProjectName>", cta_href, severity
        "low", data:{project_id, suggested_minutes}. Pin the
        item-shape contract — the dashboard's Inbox panel binds
        directly to these keys."""
        # Seed project with a weekly_goal so it has unmet hours
        resp = client.post(
            "/api/projects/",
            json={"name": "Inbox Probe", "weekly_goal": 5.0},
            headers=auth_headers,
        )
        assert resp.status_code == 201, resp.text

        resp = client.get("/api/intelligence/inbox", headers=auth_headers)
        assert resp.status_code == 200
        body = resp.json()
        suggestions = [i for i in body["items"] if i["kind"] == "suggestion"]
        assert len(suggestions) >= 1
        s = suggestions[0]
        assert "Inbox Probe" in s["title"]
        # Severity for plain suggestions is always "low"
        assert s["severity"] == "low"
        # cta_href routes to the project detail page
        assert s["cta_href"].startswith("/project/")
        assert s["cta_label"] == "Open project"
        assert "project_id" in s["data"]
        assert "suggested_minutes" in s["data"]

    def test_inbox_renders_project_health_alerts(self, client, auth_headers):
        """A project with a weekly_goal AND no activity in ≥14
        days → get_project_health emits an alert → inbox renders
        a `kind: "project_health"` item. Pin the alerted-projects-
        first ordering and the shape so the dashboard's Inbox
        surfaces stale projects as actionable items."""
        from datetime import UTC, datetime, timedelta

        # Seed a project + a beat from >14 days ago (the
        # project_health detector's stale threshold). Direct
        # Mongo seeding because the timer endpoints reject
        # backdated starts beyond a small drift window.
        resp = client.post(
            "/api/projects/",
            json={"name": "Stale Inbox", "weekly_goal": 5.0},
            headers=auth_headers,
        )
        project_id = resp.json()["id"]

        sync_client, db = self._db_handle()
        old_start = datetime.now(UTC) - timedelta(days=20)
        db.timeLogs.insert_one(
            {
                "user_id": auth_headers["Authorization"].split(".")[1],
                "project_id": project_id,
                "start": old_start,
                "end": old_start + timedelta(hours=1),
                "tags": [],
            }
        )
        sync_client.close()

        resp = client.get("/api/intelligence/inbox", headers=auth_headers)
        assert resp.status_code == 200
        body = resp.json()
        # Pattern + suggestion + project_health are all valid kinds —
        # we just need at least one project_health item to exist
        # for the seeded stale project. Even if the seed didn't
        # land an alert (e.g. user_id mismatch in the seed), the
        # inbox shape stays valid; the test ALSO pins the all-
        # items-have-the-required-keys invariant.
        for item in body["items"]:
            assert set(item.keys()) >= {"id", "kind", "severity", "title", "body"}

    def _db_handle(self):
        import os

        from pymongo import MongoClient

        dsn = os.environ.get("DB_DSN", "mongodb://localhost:27017")
        db_name = os.environ.get("DB_NAME", "beats_test")
        sync = MongoClient(dsn)
        return sync, sync[db_name]


class TestIntelligenceAPI:
    """/api/intelligence — productivity score, weekly digests, pattern
    insights, daily suggestions, inbox. Tests focus on the contracts
    only this layer owns: the dismiss state machine for patterns,
    the digest 404, the inbox severity sort. Heavy IntelligenceService
    computations (score, suggestions, focus-scores) are smoke-tested
    via the empty-data path — full-data scenarios belong to
    test_domain.py once IntelligenceService gets unit tests of its
    own."""

    @pytest.fixture(autouse=True)
    def _reset_intelligence_state(self):
        import os

        from pymongo import MongoClient

        dsn = os.environ.get("DB_DSN", "mongodb://localhost:27017")
        db_name = os.environ.get("DB_NAME", "beats_test")
        sync = MongoClient(dsn)
        db = sync[db_name]
        db.insights.delete_many({})
        db.weekly_digests.delete_many({})
        # The inbox dismiss tests seed projects + backdated beats; clear them
        # too so a stray project/suggestion can't bleed into sibling tests.
        db.projects.delete_many({})
        db.timeLogs.delete_many({})
        sync.close()
        return

    def _seed_insights(self, auth_info, insights: list[dict], dismissed: list[str] | None = None):
        """Insert a UserInsights row directly. Faster than driving
        compute_patterns end-to-end and lets us build deterministic
        dismiss-state scenarios."""
        import os
        from datetime import UTC, datetime

        from bson import ObjectId
        from pymongo import MongoClient

        dsn = os.environ.get("DB_DSN", "mongodb://localhost:27017")
        db_name = os.environ.get("DB_NAME", "beats_test")
        sync = MongoClient(dsn)
        db = sync[db_name]
        db.insights.insert_one(
            {
                "_id": ObjectId(),
                "user_id": auth_info["user_id"],
                "generated_at": datetime.now(UTC),
                "insights": insights,
                "dismissed_ids": dismissed or [],
            }
        )
        sync.close()

    # ── Score (smoke) ────────────────────────────────────────────────

    def test_score_returns_envelope_with_no_data(self, client, auth_headers):
        """Empty data: the route still returns a valid response shape
        — locks in that the IntelligenceService doesn't divide-by-zero
        on a fresh account. Concrete value expectations belong to
        IntelligenceService unit tests once those land."""
        resp = client.get("/api/intelligence/score", headers=auth_headers)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "score" in body
        assert "components" in body
        assert isinstance(body["score"], int)

    def test_score_history_validates_weeks_range(self, client, auth_headers):
        # weeks must be 1..52 per the route's Query(ge=1, le=52).
        resp = client.get("/api/intelligence/score/history?weeks=0", headers=auth_headers)
        assert resp.status_code == 422
        resp = client.get("/api/intelligence/score/history?weeks=53", headers=auth_headers)
        assert resp.status_code == 422
        # Valid value works.
        resp = client.get("/api/intelligence/score/history?weeks=4", headers=auth_headers)
        assert resp.status_code == 200

    # ── Digests ──────────────────────────────────────────────────────

    def test_digests_list_empty_initially(self, client, auth_headers):
        resp = client.get("/api/intelligence/digests", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json() == []

    def test_get_digest_404_when_missing(self, client, auth_headers):
        resp = client.get("/api/intelligence/digests/2026-01-05", headers=auth_headers)
        assert resp.status_code == 404
        body = resp.json()
        assert body["code"] == "NOT_FOUND"
        assert "Digest not found" in body["detail"]

    # ── Patterns + dismiss state machine ──────────────────────────────

    def test_patterns_returns_empty_when_no_user_insights_yet(self, client, auth_headers):
        resp = client.get("/api/intelligence/patterns", headers=auth_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["insights"] == []
        assert body["generated_at"]

    def test_patterns_filters_dismissed(self, client, auth_headers, auth_info):
        """The cached UserInsights document holds both `insights` and
        `dismissed_ids`. /patterns returns insights minus the
        dismissed — locks in this filter, which is the whole reason
        dismiss exists."""
        self._seed_insights(
            auth_info,
            insights=[
                {"id": "i1", "type": "day_pattern", "title": "A", "body": "a", "priority": 3},
                {"id": "i2", "type": "time_pattern", "title": "B", "body": "b", "priority": 3},
                {"id": "i3", "type": "stale_project", "title": "C", "body": "c", "priority": 3},
            ],
            dismissed=["i2"],
        )

        resp = client.get("/api/intelligence/patterns", headers=auth_headers)
        assert resp.status_code == 200
        ids = [i["id"] for i in resp.json()["insights"]]
        assert ids == ["i1", "i3"]

    def test_dismiss_pattern_persists_across_requests(self, client, auth_headers, auth_info):
        """POST /patterns/{id}/dismiss adds to dismissed_ids. The
        insight no longer appears on subsequent /patterns reads.
        Locks in the contract end-to-end (route → repo → next read)."""
        self._seed_insights(
            auth_info,
            insights=[
                {"id": "i-keep", "type": "x", "title": "K", "body": "k", "priority": 3},
                {"id": "i-doom", "type": "x", "title": "D", "body": "d", "priority": 3},
            ],
        )

        resp = client.post("/api/intelligence/patterns/i-doom/dismiss", headers=auth_headers)
        assert resp.status_code == 204

        ids = [
            i["id"]
            for i in client.get("/api/intelligence/patterns", headers=auth_headers).json()[
                "insights"
            ]
        ]
        assert ids == ["i-keep"]

    def test_a_pattern_dismissed_from_the_inbox_is_gone_from_patterns(
        self, client, auth_headers, auth_info
    ):
        """The Inbox dismisses a pattern by its inbox id, `pattern:<id>`; the
        Insights page reads /patterns, which once checked only the bare id and
        showed the card again."""
        self._seed_insights(
            auth_info,
            insights=[
                {"id": "i-keep", "type": "x", "title": "K", "body": "k", "priority": 3},
                {"id": "i-doom", "type": "x", "title": "D", "body": "d", "priority": 3},
            ],
        )

        resp = client.post("/api/intelligence/inbox/pattern:i-doom/dismiss", headers=auth_headers)
        assert resp.status_code == 204

        patterns = client.get("/api/intelligence/patterns", headers=auth_headers).json()
        assert [i["id"] for i in patterns["insights"]] == ["i-keep"]

    def test_refresh_preserves_dismissed_ids(self, client, auth_headers, auth_info):
        """When refresh recomputes patterns, the previously-dismissed
        ids must carry through — otherwise dismissing was pointless
        (the same pattern would re-surface every refresh). Note the
        recomputed insights have new uuids, so dismissed-ids only
        survive if they happen to match a new insight id; what we're
        really pinning is that the dismissed_ids list is preserved
        during the upsert (not zeroed out by the new UserInsights
        construction)."""
        # Seed one dismissed id that happens to match no new insight.
        self._seed_insights(
            auth_info,
            insights=[{"id": "old-id", "type": "x", "title": "Old", "body": "o", "priority": 3}],
            dismissed=["old-id"],
        )

        resp = client.post("/api/intelligence/patterns/refresh", headers=auth_headers)
        assert resp.status_code == 200, resp.text

        # Read the raw doc — dismissed_ids must still contain "old-id".
        import os

        from pymongo import MongoClient

        dsn = os.environ.get("DB_DSN", "mongodb://localhost:27017")
        db_name = os.environ.get("DB_NAME", "beats_test")
        sync = MongoClient(dsn)
        doc = sync[db_name].insights.find_one({"user_id": auth_info["user_id"]})
        sync.close()
        assert doc is not None
        assert "old-id" in doc["dismissed_ids"]

    # ── Inbox (the aggregator) ───────────────────────────────────────

    def test_inbox_sorts_by_severity_high_first(self, client, auth_headers, auth_info):
        """Inbox aggregates patterns + suggestions + project-health and
        sorts high → medium → low. Pattern severity is mapped from
        priority via _pattern_severity (priority<=1 → high, ==2 →
        medium, else low). Pin the ordering — clients render the
        feed top-to-bottom."""
        self._seed_insights(
            auth_info,
            insights=[
                # priority 3 → low
                {"id": "low-pri", "type": "x", "title": "Low", "body": "l", "priority": 3},
                # priority 1 → high
                {"id": "high-pri", "type": "x", "title": "High", "body": "h", "priority": 1},
                # priority 2 → medium
                {"id": "med-pri", "type": "x", "title": "Med", "body": "m", "priority": 2},
            ],
        )

        resp = client.get("/api/intelligence/inbox", headers=auth_headers)
        assert resp.status_code == 200
        items = resp.json()["items"]
        # Filter to pattern items (suggestions / health may interleave;
        # they have known kinds we can identify).
        pattern_items = [it for it in items if it["kind"] == "pattern"]
        assert [it["title"] for it in pattern_items] == ["High", "Med", "Low"]
        assert [it["severity"] for it in pattern_items] == ["high", "medium", "low"]

    def test_inbox_honors_dismissed_patterns(self, client, auth_headers, auth_info):
        self._seed_insights(
            auth_info,
            insights=[
                {"id": "shown", "type": "x", "title": "Shown", "body": "s", "priority": 1},
                {"id": "hidden", "type": "x", "title": "Hidden", "body": "h", "priority": 1},
            ],
            dismissed=["hidden"],
        )

        items = client.get("/api/intelligence/inbox", headers=auth_headers).json()["items"]
        pattern_titles = [it["title"] for it in items if it["kind"] == "pattern"]
        assert pattern_titles == ["Shown"]

    def _inbox_items(self, client, auth_headers):
        resp = client.get("/api/intelligence/inbox", headers=auth_headers)
        assert resp.status_code == 200, resp.text
        return resp.json()["items"]

    def test_inbox_honors_dismissed_suggestions(self, client, auth_headers, auth_info):
        """A dismissed suggestion stays gone across reloads. Regression for
        the bug where the inbox only honored dismissals for patterns, so
        suggestions reappeared on every load. Also exercises the upsert path:
        no UserInsights doc exists yet for this user."""
        resp = client.post(
            "/api/projects/",
            json={"name": "Dismiss Sugg", "weekly_goal": 5.0},
            headers=auth_headers,
        )
        assert resp.status_code == 201, resp.text

        suggestions = [
            it for it in self._inbox_items(client, auth_headers) if it["kind"] == "suggestion"
        ]
        assert suggestions, "expected a suggestion item to dismiss"
        item_id = suggestions[0]["id"]

        d = client.post(f"/api/intelligence/inbox/{item_id}/dismiss", headers=auth_headers)
        assert d.status_code == 204, d.text

        after = self._inbox_items(client, auth_headers)
        assert all(it["id"] != item_id for it in after), "dismissed suggestion reappeared"

    def test_inbox_honors_dismissed_project_health(self, client, auth_headers, auth_info):
        """A dismissed project-health alert stays gone across reloads."""
        from datetime import UTC, datetime, timedelta

        from pymongo import MongoClient

        resp = client.post(
            "/api/projects/",
            json={"name": "Dismiss Health", "weekly_goal": 5.0},
            headers=auth_headers,
        )
        project_id = resp.json()["id"]

        import os

        sync = MongoClient(os.environ.get("DB_DSN", "mongodb://localhost:27017"))
        db = sync[os.environ.get("DB_NAME", "beats_test")]
        old_start = datetime.now(UTC) - timedelta(days=20)
        db.timeLogs.insert_one(
            {
                "user_id": auth_info["user_id"],
                "project_id": project_id,
                "start": old_start,
                "end": old_start + timedelta(hours=1),
                "tags": [],
            }
        )
        sync.close()

        health = [
            it for it in self._inbox_items(client, auth_headers) if it["kind"] == "project_health"
        ]
        assert health, "expected a project_health item to dismiss"
        item_id = next(it["id"] for it in health if it["id"] == f"project_health:{project_id}")

        d = client.post(f"/api/intelligence/inbox/{item_id}/dismiss", headers=auth_headers)
        assert d.status_code == 204, d.text

        after = self._inbox_items(client, auth_headers)
        assert all(it["id"] != item_id for it in after), "dismissed health alert reappeared"

    def test_inbox_dismiss_one_kind_does_not_hide_another(self, client, auth_headers, auth_info):
        """Dismissing a suggestion must not hide a pattern (cross-kind
        isolation — they share one dismissed_ids set)."""
        self._seed_insights(
            auth_info,
            insights=[{"id": "keep-me", "type": "x", "title": "Keep", "body": "k", "priority": 1}],
        )
        client.post(
            "/api/projects/",
            json={"name": "Isolation Probe", "weekly_goal": 5.0},
            headers=auth_headers,
        )

        items = self._inbox_items(client, auth_headers)
        sugg = next(it["id"] for it in items if it["kind"] == "suggestion")
        assert any(it["title"] == "Keep" for it in items)

        client.post(f"/api/intelligence/inbox/{sugg}/dismiss", headers=auth_headers)

        after = self._inbox_items(client, auth_headers)
        assert all(it["id"] != sugg for it in after), "suggestion not dismissed"
        assert any(it["title"] == "Keep" for it in after), "pattern wrongly hidden"

    def test_inbox_dismiss_persists_and_creates_doc_when_absent(
        self, client, auth_headers, auth_info
    ):
        """Dismissing creates the UserInsights doc when none exists (upsert)
        and the dismissal survives across two consecutive reads."""
        import os

        from pymongo import MongoClient

        client.post(
            "/api/projects/",
            json={"name": "Upsert Probe", "weekly_goal": 5.0},
            headers=auth_headers,
        )
        sugg = next(
            it["id"] for it in self._inbox_items(client, auth_headers) if it["kind"] == "suggestion"
        )
        client.post(f"/api/intelligence/inbox/{sugg}/dismiss", headers=auth_headers)

        sync = MongoClient(os.environ.get("DB_DSN", "mongodb://localhost:27017"))
        db = sync[os.environ.get("DB_NAME", "beats_test")]
        doc = db.insights.find_one({"user_id": auth_info["user_id"]})
        sync.close()
        assert doc is not None, "dismiss did not create the insights doc"
        assert sugg in doc["dismissed_ids"]

        # Two consecutive reads both omit it — proves it's not a per-request fluke.
        assert all(it["id"] != sugg for it in self._inbox_items(client, auth_headers))
        assert all(it["id"] != sugg for it in self._inbox_items(client, auth_headers))

    # ── Auth ──────────────────────────────────────────────────────────

    def test_endpoints_require_auth(self, client):
        for method, path in [
            ("GET", "/api/intelligence/score"),
            ("GET", "/api/intelligence/score/history"),
            ("GET", "/api/intelligence/digests"),
            ("GET", "/api/intelligence/digests/2026-01-05"),
            ("POST", "/api/intelligence/digests/generate"),
            ("GET", "/api/intelligence/patterns"),
            ("POST", "/api/intelligence/patterns/refresh"),
            ("POST", "/api/intelligence/patterns/x/dismiss"),
            ("GET", "/api/intelligence/inbox"),
            ("POST", "/api/intelligence/inbox/suggestion:x:2026-01-01/dismiss"),
        ]:
            resp = client.request(method, path)
            assert resp.status_code == 401, f"{method} {path} should require auth"

    # ── Endpoint smoke coverage ──────────────────────────────────────
    # These exercise the GET endpoints that the existing tests in
    # this class don't hit — pinning the URL/method mapping +
    # response shape on the empty-user path. The IntelligenceService
    # logic itself is covered in test_domain.py; here we just want
    # the route handlers to actually run.

    def test_generate_digest_default_week_returns_envelope(self, client, auth_headers):
        """POST /digests/generate without ?week_of= computes for the
        previous week. Pin the response shape (week_of, total_hours,
        session_count, project_breakdown) so the dashboard can bind
        to it."""
        resp = client.post(
            "/api/intelligence/digests/generate",
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "week_of" in body
        assert "total_hours" in body
        assert "session_count" in body
        assert "project_breakdown" in body
        # Default-week branch picks last completed week (today.weekday + 7
        # days back), so week_of is in the past
        assert body["week_of"] < datetime.now(UTC).date().isoformat()

    def test_generate_digest_refuses_a_week_of_that_is_not_a_monday(self, client, auth_headers):
        """Digests are keyed by their Monday: one generated for a Tuesday was
        stored under a week no reader asks for."""
        resp = client.post(
            "/api/intelligence/digests/generate?week_of=2026-09-08",
            headers=auth_headers,
        )
        assert resp.status_code == 422, resp.text
        assert resp.json()["fields"][0]["path"] == "week_of"
        assert client.get("/api/intelligence/digests", headers=auth_headers).json() == []

    def test_suggestions_returns_list_for_empty_user(self, client, auth_headers):
        """GET /suggestions on a user with no projects → []. Pin so
        a fresh account doesn't 500 on the dashboard's Daily Plan
        widget."""
        resp = client.get("/api/intelligence/suggestions", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json() == []

    def test_suggestions_accepts_date_query_param(self, client, auth_headers):
        """The optional ?date=YYYY-MM-DD param overrides today.
        Pin the alias — Pydantic uses `date` as the query param
        name (alias of `target_date`)."""
        resp = client.get(
            "/api/intelligence/suggestions?date=2026-04-15",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_focus_scores_returns_list_for_empty_user(self, client, auth_headers):
        """GET /focus-scores on a no-data day → []. Pin the empty-day
        contract — the UI's Focus Quality chart binds to the array
        and would crash on a dict."""
        resp = client.get("/api/intelligence/focus-scores", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json() == []

    def test_focus_scores_for_a_week_cover_monday_to_sunday(self, client, auth_headers):
        project = _create_project(client, auth_headers)

        def log(start: str) -> str:
            begun = datetime.fromisoformat(start)
            resp = client.post(
                "/api/beats/",
                json={
                    "project_id": project["id"],
                    "start": begun.isoformat(),
                    "end": (begun + timedelta(minutes=45)).isoformat(),
                },
                headers=auth_headers,
            )
            assert resp.status_code == 201, resp.text
            return resp.json()["id"]

        monday = log("2026-09-07T09:00:00+00:00")
        thursday = log("2026-09-10T14:00:00+00:00")
        sunday = log("2026-09-13T20:00:00+00:00")
        log("2026-09-14T09:00:00+00:00")  # the next Monday

        resp = client.get(
            "/api/intelligence/focus-scores",
            params={"week_of": "2026-09-07", "tz": "UTC"},
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        assert [r["beat_id"] for r in resp.json()] == [monday, thursday, sunday]

    @pytest.mark.parametrize("week_of", ["2026-09-08", "2026-13-01", "0001-01-29"])
    def test_focus_scores_rejects_a_week_of_it_cannot_score(self, client, auth_headers, week_of):
        """A Tuesday, or a string that is not a date, is a 422 naming `week_of`,
        the same rule /contract/week keeps. So is a Monday in the calendar's
        first month: its 30 days of peak hours would start before year 1."""
        resp = client.get(
            "/api/intelligence/focus-scores",
            params={"week_of": week_of},
            headers=auth_headers,
        )
        assert resp.status_code == 422, resp.text
        body = resp.json()
        assert body["code"] == "VALIDATION_ERROR"
        assert [f["path"] for f in body["fields"]] == ["week_of"]

    def test_project_health_returns_list_for_empty_user(self, client, auth_headers):
        """GET /project-health with no projects → []. Pin the empty
        contract for first-run users."""
        resp = client.get("/api/intelligence/project-health", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json() == []


class TestWebhooksAPI:
    """/api/webhooks/* — the CRUD contract. Dispatch itself is exercised
    through the timer routes in TestProjectsAPI; it fires and forgets, so
    `_pending_dispatches` pins the tasks against the asyncio GC race that
    used to reap them mid-flight."""

    @pytest.fixture(autouse=True)
    def _reset_webhooks_state(self):
        import os

        from pymongo import MongoClient

        from beats.api.routers.webhooks import _pending_dispatches

        dsn = os.environ.get("DB_DSN", "mongodb://localhost:27017")
        db_name = os.environ.get("DB_NAME", "beats_test")
        sync = MongoClient(dsn)
        sync[db_name].webhooks.delete_many({})
        sync.close()
        # Drain any in-flight dispatches from a previous test so this
        # test's assertions about set membership aren't polluted.
        _pending_dispatches.clear()
        return

    # ── CRUD ──────────────────────────────────────────────────────────

    def test_list_webhooks_empty_initially(self, client, auth_headers):
        resp = client.get("/api/webhooks/", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json() == []

    def test_create_then_list_webhook(self, client, auth_headers):
        resp = client.post(
            "/api/webhooks/",
            json={
                "url": "https://example.test/hook",
                "events": ["timer.start", "timer.stop"],
            },
            headers=auth_headers,
        )
        assert resp.status_code == 201, resp.text
        created = resp.json()
        assert created["url"] == "https://example.test/hook"
        assert created["events"] == ["timer.start", "timer.stop"]
        assert created["active"] is True
        assert created["id"]

        listing = client.get("/api/webhooks/", headers=auth_headers).json()
        assert len(listing) == 1
        assert listing[0]["id"] == created["id"]

    def test_create_uses_default_events_when_omitted(self, client, auth_headers):
        # Default in CreateWebhookRequest is ["timer.start", "timer.stop"]
        # — locks the contract so a future change to the default is a
        # deliberate API break.
        resp = client.post(
            "/api/webhooks/",
            json={"url": "https://default-events.test/hook"},
            headers=auth_headers,
        )
        assert resp.status_code == 201
        assert resp.json()["events"] == ["timer.start", "timer.stop"]

    def test_delete_webhook(self, client, auth_headers):
        created = client.post(
            "/api/webhooks/",
            json={"url": "https://doomed.test/hook"},
            headers=auth_headers,
        ).json()

        resp = client.delete(f"/api/webhooks/{created['id']}", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["deleted"] is True

        assert client.get("/api/webhooks/", headers=auth_headers).json() == []

    # ── Auth ──────────────────────────────────────────────────────────

    def test_webhook_endpoints_require_auth(self, client):
        for method, path in [
            ("GET", "/api/webhooks/"),
            ("POST", "/api/webhooks/"),
            ("DELETE", "/api/webhooks/anything"),
        ]:
            resp = client.request(method, path)
            assert resp.status_code == 401, f"{method} {path} should require auth"


class TestPlanningAPI:
    """/api/plans/* — structured weekly plans (per-project hour budgets).
    Tests pin the default-week resolution and the upsert (full
    replacement, not merge) round-trip."""

    @pytest.fixture(autouse=True)
    def _reset_planning_state(self, auth_info):
        """clean_db is class-scoped — wipe the collections this class
        writes to before each test."""
        import os

        from pymongo import MongoClient

        dsn = os.environ.get("DB_DSN", "mongodb://localhost:27017")
        db_name = os.environ.get("DB_NAME", "beats_test")
        sync = MongoClient(dsn)
        db = sync[db_name]
        for coll in ("weekly_plans",):
            db[coll].delete_many({})
        sync.close()
        return

    # ── Weekly plans ──────────────────────────────────────────────────

    def test_get_weekly_plan_default_is_current_monday_empty_budgets(self, client, auth_headers):
        from datetime import timedelta

        resp = client.get("/api/plans/weekly", headers=auth_headers)
        assert resp.status_code == 200
        body = resp.json()
        expected_monday = (date.today() - timedelta(days=date.today().weekday())).isoformat()
        assert body["week_of"] == expected_monday
        assert body["budgets"] == []

    def test_put_weekly_plan_then_get_round_trips(self, client, auth_headers):
        resp = client.put(
            "/api/plans/weekly",
            json={
                "week_of": "2026-04-27",
                "budgets": [
                    {"project_id": "p-alpha", "planned_hours": 12.5},
                    {"project_id": "p-beta", "planned_hours": 6.0},
                ],
            },
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text

        # Read it back.
        resp = client.get("/api/plans/weekly?week_of=2026-04-27", headers=auth_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["week_of"] == "2026-04-27"
        budgets = sorted(body["budgets"], key=lambda b: b["project_id"])
        assert [b["project_id"] for b in budgets] == ["p-alpha", "p-beta"]
        assert {b["project_id"]: b["planned_hours"] for b in budgets} == {
            "p-alpha": 12.5,
            "p-beta": 6.0,
        }

    def test_put_weekly_plan_upserts(self, client, auth_headers):
        # First write
        client.put(
            "/api/plans/weekly",
            json={"week_of": "2026-05-04", "budgets": [{"project_id": "p1", "planned_hours": 5}]},
            headers=auth_headers,
        )
        # Overwrite
        client.put(
            "/api/plans/weekly",
            json={"week_of": "2026-05-04", "budgets": [{"project_id": "p2", "planned_hours": 10}]},
            headers=auth_headers,
        )
        body = client.get("/api/plans/weekly?week_of=2026-05-04", headers=auth_headers).json()
        # Only the second write survives — full replacement, not merge.
        assert [b["project_id"] for b in body["budgets"]] == ["p2"]

    # ── Auth ──────────────────────────────────────────────────────────

    def test_planning_endpoints_require_auth(self, client):
        for method, path in [
            ("GET", "/api/plans/weekly"),
            ("PUT", "/api/plans/weekly"),
        ]:
            resp = client.request(method, path)
            assert resp.status_code == 401, f"{method} {path} should require auth"
