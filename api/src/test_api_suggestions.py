"""What the daemon asks of the API: the timer suggestion and its
pending poll, the fields a project write must keep for the auto-timer,
the timer context, and drift.

Split out of `test_api.py` at the ceiling in roadmaps/file-sizes.md; the
harness is `conftest.py`'s and the shared fixtures `api_helpers.py`'s.
"""

from datetime import UTC, datetime, timedelta

from api_helpers import _pair_device


class TestTimerSuggestionsAPI:
    """`/api/signals/suggest-timer` and what the companion polls, plus the
    project-write fields and the timer context the daemon reads."""

    def test_suggest_timer_matches_editor_repo_against_autostart_repos(self, client, auth_headers):
        """The /suggest-timer endpoint disambiguates same-category
        projects by matching the daemon's editor_repo against each
        project's autostart_repos. Without this, two "coding"
        projects always returned the same one (whichever came first
        in the project list).
        """
        # Two coding projects, only one of which claims the editor's repo.
        resp = client.post(
            "/api/projects/",
            json={"name": "Project A", "category": "coding"},
            headers=auth_headers,
        )
        proj_a = resp.json()["id"]
        resp = client.post(
            "/api/projects/",
            json={"name": "Project B", "category": "coding"},
            headers=auth_headers,
        )
        proj_b = resp.json()["id"]
        # B claims the workspace via autostart_repos.
        client.put(
            "/api/projects/",
            json={
                "id": proj_b,
                "name": "Project B",
                "category": "coding",
                "autostart_repos": ["/Users/me/code/projB"],
            },
            headers=auth_headers,
        )

        _, device_headers = _pair_device(client, auth_headers)
        resp = client.post(
            "/api/signals/suggest-timer",
            json={
                "window_start": (datetime.now(UTC) - timedelta(minutes=1)).isoformat(),
                "window_end": datetime.now(UTC).isoformat(),
                "flow_score": 0.85,
                "cadence_score": 0.5,
                "coherence_score": 0.5,
                "category_fit_score": 0.0,
                "idle_fraction": 0.1,
                "dominant_bundle_id": "com.microsoft.VSCode",
                "dominant_category": "coding",
                "editor_repo": "/Users/me/code/projB",
            },
            headers=device_headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["should_suggest"] is True
        # B should win even though A also matches by category, because
        # editor_repo matches B's autostart_repos.
        assert body["project_id"] == proj_b, body
        assert body["project_name"] == "Project B"
        # Make sure A wasn't picked accidentally.
        assert body["project_id"] != proj_a

    def test_suggest_timer_falls_back_to_category_when_no_editor_repo_match(
        self, client, auth_headers
    ):
        """When the editor_repo doesn't match any project's
        autostart_repos (or is empty), fall back to category match.
        Locks in the second-priority path.
        """
        resp = client.post(
            "/api/projects/",
            json={"name": "Cat Fallback", "category": "design"},
            headers=auth_headers,
        )
        proj_id = resp.json()["id"]

        _, device_headers = _pair_device(client, auth_headers)
        # Send a window with no editor_repo at all.
        resp = client.post(
            "/api/signals/suggest-timer",
            json={
                "window_start": (datetime.now(UTC) - timedelta(minutes=1)).isoformat(),
                "window_end": datetime.now(UTC).isoformat(),
                "flow_score": 0.85,
                "cadence_score": 0.5,
                "coherence_score": 0.5,
                "category_fit_score": 0.0,
                "idle_fraction": 0.1,
                "dominant_bundle_id": "com.figma.Desktop",
                "dominant_category": "design",
            },
            headers=device_headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["should_suggest"] is True
        assert body["project_id"] == proj_id

    def test_suggest_timer_persists_pending_suggestion_for_companion_poll(
        self, client, auth_headers
    ):
        """A positive `/suggest-timer` response also writes a
        PendingSuggestion so the companion's notification poller can
        pick it up later via `GET /api/signals/pending-suggestions`.
        Without this the daemon's macOS osascript prompt was the only
        surface that fired on auto-timer matches.
        """
        # Project that will match by editor_repo.
        resp = client.post(
            "/api/projects/",
            json={"name": "Persisted Suggest", "category": "coding"},
            headers=auth_headers,
        )
        proj_id = resp.json()["id"]
        client.put(
            "/api/projects/",
            json={
                "id": proj_id,
                "name": "Persisted Suggest",
                "category": "coding",
                "autostart_repos": ["/Users/me/code/pending-test"],
            },
            headers=auth_headers,
        )

        _, device_headers = _pair_device(client, auth_headers)
        before = client.get("/api/signals/pending-suggestions", headers=device_headers).json()[
            "suggestions"
        ]
        before_ids = {s["id"] for s in before}

        resp = client.post(
            "/api/signals/suggest-timer",
            json={
                "window_start": (datetime.now(UTC) - timedelta(minutes=1)).isoformat(),
                "window_end": datetime.now(UTC).isoformat(),
                "flow_score": 0.85,
                "cadence_score": 0.5,
                "coherence_score": 0.5,
                "category_fit_score": 0.0,
                "idle_fraction": 0.1,
                "dominant_bundle_id": "com.microsoft.VSCode",
                "dominant_category": "coding",
                "editor_repo": "/Users/me/code/pending-test",
            },
            headers=device_headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["should_suggest"] is True

        # Pending suggestion should now be readable via the GET endpoint.
        resp = client.get("/api/signals/pending-suggestions", headers=device_headers)
        assert resp.status_code == 200, resp.text
        ours = [
            s
            for s in resp.json()["suggestions"]
            if s["id"] not in before_ids and s["project_id"] == proj_id
        ]
        assert len(ours) == 1, ours
        s = ours[0]
        assert s["project_name"] == "Persisted Suggest"
        # editor_repo round-trips so a future "yes" tap can confirm the match.
        assert s["editor_repo"] == "/Users/me/code/pending-test"
        assert s["id"]
        # suggested_at parses as a UTC ISO timestamp within the last minute.
        ts = datetime.fromisoformat(s["suggested_at"])
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=UTC)
        assert (datetime.now(UTC) - ts) < timedelta(minutes=1)

    def test_suggest_timer_does_not_persist_when_no_match(self, client, auth_headers):
        """`should_suggest=False` responses must NOT leave a pending
        suggestion behind. Otherwise the companion poller would fire a
        notification for a project the API explicitly didn't suggest.
        """
        _, device_headers = _pair_device(client, auth_headers)
        before = client.get("/api/signals/pending-suggestions", headers=device_headers).json()[
            "suggestions"
        ]
        before_ids = {s["id"] for s in before}

        resp = client.post(
            "/api/signals/suggest-timer",
            json={
                "window_start": (datetime.now(UTC) - timedelta(minutes=1)).isoformat(),
                "window_end": datetime.now(UTC).isoformat(),
                "flow_score": 0.85,
                "cadence_score": 0.5,
                "coherence_score": 0.5,
                "category_fit_score": 0.0,
                "idle_fraction": 0.1,
                "dominant_bundle_id": "com.unknown.app",
                "dominant_category": "no-such-category-anywhere",
            },
            headers=device_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["should_suggest"] is False

        # No new suggestions appeared.
        resp = client.get("/api/signals/pending-suggestions", headers=device_headers)
        new_ids = {s["id"] for s in resp.json()["suggestions"]} - before_ids
        assert new_ids == set(), new_ids

    def test_pending_suggestions_explicit_since_window(self, client, auth_headers):
        """Explicit `since` filters out suggestions older than the cutoff.
        The default `since` (last 30 min) follows the same parameter, so
        this covers both code paths that matter for the companion poller's
        contract."""
        # Project that matches by category so a /suggest-timer POST
        # produces a pending suggestion under our user.
        resp = client.post(
            "/api/projects/",
            json={"name": "Since Window Test", "category": "explicit-since-cat"},
            headers=auth_headers,
        )
        assert resp.status_code == 201

        _, device_headers = _pair_device(client, auth_headers)
        client.post(
            "/api/signals/suggest-timer",
            json={
                "window_start": (datetime.now(UTC) - timedelta(minutes=1)).isoformat(),
                "window_end": datetime.now(UTC).isoformat(),
                "flow_score": 0.85,
                "cadence_score": 0.5,
                "coherence_score": 0.5,
                "category_fit_score": 0.0,
                "idle_fraction": 0.1,
                "dominant_bundle_id": "com.test.app",
                "dominant_category": "explicit-since-cat",
            },
            headers=device_headers,
        )

        # Wide window includes our just-posted suggestion.
        resp = client.get(
            "/api/signals/pending-suggestions",
            params={"since": (datetime.now(UTC) - timedelta(minutes=5)).isoformat()},
            headers=device_headers,
        )
        names_wide = {s["project_name"] for s in resp.json()["suggestions"]}
        assert "Since Window Test" in names_wide

        # Narrow window in the future excludes it — no suggestions in that
        # slice. (Asserts our suggestion specifically; other tests' rows
        # could exist but none would be after `now`.)
        resp = client.get(
            "/api/signals/pending-suggestions",
            params={"since": (datetime.now(UTC) + timedelta(minutes=5)).isoformat()},
            headers=device_headers,
        )
        names_future = {s["project_name"] for s in resp.json()["suggestions"]}
        assert "Since Window Test" not in names_future

    def test_pending_suggestions_requires_auth(self, client):
        """No token → 401, same as every other read endpoint."""
        resp = client.get("/api/signals/pending-suggestions")
        assert resp.status_code == 401

    def test_create_project_persists_every_settable_field(self, client, auth_headers):
        """Regression guard: create used to accept fewer fields than update.
        First the route never forwarded `category` to the domain Project, so
        the daemon's flow-score category_fit silently never matched a new
        project; then the schema itself lacked goal_type, github_repo and
        autostart_repos, so whatever the create form sent for them was
        dropped (pydantic ignores extras) until a separate PUT. Round-trip
        all of them through POST and the list.
        """
        sent = {
            "category": "coding",
            "goal_type": "cap",
            "github_repo": "lanterno/beats",
            "autostart_repos": ["/Users/me/code/beats"],
        }
        resp = client.post(
            "/api/projects/",
            json={"name": "Drift Test Coding", **sent},
            headers=auth_headers,
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert {k: body[k] for k in sent} == sent, body

        # Read back via the list to confirm persistence.
        resp = client.get("/api/projects/", headers=auth_headers)
        match = next(p for p in resp.json() if p["id"] == body["id"])
        assert {k: match[k] for k in sent} == sent

    def test_update_project_persists_autostart_repos(self, client, auth_headers):
        """update_project also used to drop autostart_repos on the
        floor — the schema accepted them but the domain Project was
        built without them, so the daemon's auto-timer-by-repo rules
        never matched. Locks in that the round-trip works.
        """
        resp = client.post(
            "/api/projects/",
            json={"name": "Autostart Test"},
            headers=auth_headers,
        )
        project_id = resp.json()["id"]
        resp = client.put(
            "/api/projects/",
            json={
                "id": project_id,
                "name": "Autostart Test",
                "autostart_repos": ["/Users/me/code/example", "/Users/me/code/other"],
            },
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["autostart_repos"] == ["/Users/me/code/example", "/Users/me/code/other"]

    def test_update_project_rejects_invalid_goal_type_with_422(self, client, auth_headers):
        """goal_type is a GoalType StrEnum at the schema layer, so an
        invalid string ("dangerous") fails request validation with a
        clean 422 + envelope `{detail, code, fields}` instead of
        bubbling up as a 500 from Project() construction. Locks in
        the contract — without the enum at the schema, an old client
        passing a typoed goal_type would 500, hiding the actual
        validation error from observability.
        """
        resp = client.post(
            "/api/projects/",
            json={"name": "Goal Type Test"},
            headers=auth_headers,
        )
        project_id = resp.json()["id"]
        resp = client.put(
            "/api/projects/",
            json={"id": project_id, "name": "Goal Type Test", "goal_type": "dangerous"},
            headers=auth_headers,
        )
        assert resp.status_code == 422, resp.text
        body = resp.json()
        assert body["code"] == "VALIDATION_ERROR"
        # The fields[] entry surfaces the offending key and the
        # allowed-values message — clients can show this verbatim.
        paths = [f["path"] for f in body["fields"]]
        assert "goal_type" in paths

    def test_update_project_accepts_valid_goal_types(self, client, auth_headers):
        """target and cap both round-trip cleanly."""
        resp = client.post(
            "/api/projects/",
            json={"name": "Goal Type Round-Trip"},
            headers=auth_headers,
        )
        project_id = resp.json()["id"]
        for valid in ("target", "cap"):
            resp = client.put(
                "/api/projects/",
                json={"id": project_id, "name": "Goal Type Round-Trip", "goal_type": valid},
                headers=auth_headers,
            )
            assert resp.status_code == 200, f"goal_type={valid} should be valid: {resp.text}"
            assert resp.json()["goal_type"] == valid

    def test_timer_context_no_active_timer(self, client, auth_headers):
        """GET /api/signals/timer-context returns timer_running=false
        with empty project fields when no timer is running. The daemon's
        pollTimerContext goroutine reads this every 30s; the shield uses
        the boolean to gate drift detection (no drift when no timer).
        """
        _, device_headers = _pair_device(client, auth_headers)
        resp = client.get("/api/signals/timer-context", headers=device_headers)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["timer_running"] is False
        # project_id / project_category are present-but-null when no timer.
        # The daemon's TimerContextResponse struct decodes these as
        # empty strings via Go's zero-value default for missing JSON.
        assert "project_id" in body
        assert "project_category" in body

    def test_timer_context_with_active_timer_carries_category(self, client, auth_headers):
        """When a timer IS running, the response includes the project's
        category so the daemon's flow-score computation can compute
        category_fit (whether the dominant app matches the project's
        category, e.g. coding work in VS Code while a coding-tagged
        project is active)."""
        # Create a coding project + start a timer
        resp = client.post(
            "/api/projects/",
            json={"name": "Daemon TC Test", "category": "coding"},
            headers=auth_headers,
        )
        assert resp.status_code == 201
        project_id = resp.json()["id"]
        resp = client.post(
            f"/api/projects/{project_id}/start",
            json={"time": datetime.now(UTC).isoformat()},
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text

        _, device_headers = _pair_device(client, auth_headers)
        resp = client.get("/api/signals/timer-context", headers=device_headers)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["timer_running"] is True
        assert body["project_id"] == project_id
        assert body["project_category"] == "coding"

    def test_post_drift_event_records_flow_window_with_drift_category(self, client, auth_headers):
        """POST /api/signals/drift records a FlowWindow with category=drift.

        The daemon's distraction shield POSTs to this endpoint when
        the user drifts to a known time-sink while a timer is running
        (commit a3b8f3f). Until that commit shipped, the endpoint
        existed but no caller invoked it — and there was no API-side
        test to catch a regression. Locks in the behavior the daemon
        relies on: 201 + an id, and the resulting record reads back
        with category="drift" so the UI's history view can filter."""
        _, device_headers = _pair_device(client, auth_headers)
        now = datetime.now(UTC)
        started_at = now - timedelta(seconds=45)
        resp = client.post(
            "/api/signals/drift",
            json={
                "started_at": started_at.isoformat(),
                "duration_seconds": 45.0,
                "bundle_id": "com.twitter.twitter-mac",
            },
            headers=device_headers,
        )
        assert resp.status_code == 201, resp.text
        assert "id" in resp.json()

        # Read back: the drift event should be findable as a flow
        # window with category="drift" and the bundle id we sent.
        resp = client.get(
            "/api/signals/flow-windows",
            params={
                "start": (now - timedelta(minutes=5)).isoformat(),
                "end": (now + timedelta(minutes=5)).isoformat(),
            },
            headers=auth_headers,
        )
        assert resp.status_code == 200
        windows = resp.json()
        drift_windows = [w for w in windows if w.get("dominant_category") == "drift"]
        assert len(drift_windows) >= 1, windows
        target = next(
            w for w in drift_windows if w.get("dominant_bundle_id") == "com.twitter.twitter-mac"
        )
        # The endpoint used to set window_end == window_start, dropping
        # duration_seconds on the floor. Lock in that the duration is
        # actually preserved: window_end - window_start ≈ 45s, so a
        # downstream analytics view can compute "total drift time".
        window_start = datetime.fromisoformat(target["window_start"])
        window_end = datetime.fromisoformat(target["window_end"])
        elapsed = (window_end - window_start).total_seconds()
        assert 44.5 <= elapsed <= 45.5, f"expected ≈45s window, got {elapsed}s"

    def test_post_drift_event_requires_auth(self, client):
        """A drift event with no auth gets 401 — same as every
        other write endpoint."""
        resp = client.post(
            "/api/signals/drift",
            json={
                "started_at": datetime.now(UTC).isoformat(),
                "duration_seconds": 30.0,
                "bundle_id": "com.spotify.client",
            },
        )
        assert resp.status_code == 401

    def test_post_drift_event_validates_required_fields(self, client, auth_headers):
        """Missing required fields (started_at / duration_seconds /
        bundle_id) trip the unified 422 envelope, same shape the
        daemon's describeErrorBody knows how to surface."""
        _, device_headers = _pair_device(client, auth_headers)
        resp = client.post(
            "/api/signals/drift",
            json={},  # missing all three required fields
            headers=device_headers,
        )
        assert resp.status_code == 422
        body = resp.json()
        assert body["code"] == "VALIDATION_ERROR"
        # All three required fields should appear in the envelope's
        # fields[] array — locked in so the UI/daemon can render them.
        paths = {f["path"] for f in body["fields"]}
        assert {"started_at", "duration_seconds", "bundle_id"}.issubset(paths), paths

    def test_recent_drift_returns_drift_events_only(self, client, auth_headers):
        """GET /api/signals/recent-drift returns just the drift category
        windows (not arbitrary flow windows), each carrying the round-
        tripped started_at / duration_seconds / bundle_id the daemon
        originally posted. The companion poller relies on this shape to
        fire the local notification + dedupe by id."""
        _, device_headers = _pair_device(client, auth_headers)
        now = datetime.now(UTC)
        # Two drift events with bundle ids unique to this test (the
        # surrounding TestSignalsAPI class creates other drifts in
        # earlier tests; assert by content rather than total count) plus
        # a normal flow window that should NOT leak into the response.
        spotify_at = now - timedelta(seconds=120)
        chess_at = now - timedelta(seconds=60)
        client.post(
            "/api/signals/drift",
            json={
                "started_at": spotify_at.isoformat(),
                "duration_seconds": 30.0,
                "bundle_id": "com.recentdrift.spotify",
            },
            headers=device_headers,
        )
        client.post(
            "/api/signals/drift",
            json={
                "started_at": chess_at.isoformat(),
                "duration_seconds": 45.0,
                "bundle_id": "com.recentdrift.chess",
            },
            headers=device_headers,
        )
        client.post(
            "/api/signals/flow-windows",
            json={
                "window_start": (now - timedelta(minutes=2)).isoformat(),
                "window_end": (now - timedelta(minutes=1)).isoformat(),
                "flow_score": 0.8,
                "cadence_score": 0.5,
                "coherence_score": 1.0,
                "category_fit_score": 0.0,
                "idle_fraction": 0.1,
                "dominant_bundle_id": "com.recentdrift.xcode",
                "dominant_category": "coding",
                "context_switches": 2,
            },
            headers=device_headers,
        )

        resp = client.get(
            "/api/signals/recent-drift",
            params={"since": (now - timedelta(minutes=10)).isoformat()},
            headers=device_headers,
        )
        assert resp.status_code == 200, resp.text
        events = resp.json()["events"]
        # Pick out the two we just posted; ignore drifts from other tests.
        ours = [e for e in events if e["bundle_id"].startswith("com.recentdrift.")]
        assert len(ours) == 2, ours
        # The coding window must NOT leak into the drift feed even though
        # its bundle id matches the test prefix.
        assert all(e["bundle_id"] != "com.recentdrift.xcode" for e in ours)
        # Newest first — chess at 60s ago beats spotify at 120s ago.
        ours_by_time = sorted(ours, key=lambda e: e["started_at"], reverse=True)
        assert ours_by_time[0]["bundle_id"] == "com.recentdrift.chess"
        assert ours_by_time[0]["duration_seconds"] == 45.0
        assert ours_by_time[1]["bundle_id"] == "com.recentdrift.spotify"
        assert ours_by_time[1]["duration_seconds"] == 30.0
        # Endpoint orders newest-first; same order ours pulled out.
        first_idx = next(i for i, e in enumerate(events) if e in ours)
        second_idx = next(i for i, e in enumerate(events) if e in ours and i > first_idx)
        assert events[first_idx]["bundle_id"] == "com.recentdrift.chess"
        assert events[second_idx]["bundle_id"] == "com.recentdrift.spotify"
        # Each event carries the id the companion poller dedupes on.
        for e in ours:
            assert e["id"]

    def test_recent_drift_default_since_is_30_minutes(self, client, auth_headers):
        """When the companion calls without `since`, the endpoint defaults
        to the last 30 minutes — long enough that a couple of missed poll
        ticks (5 min apart) don't drop a notification, short enough that
        the response stays small for an active drifter."""
        _, device_headers = _pair_device(client, auth_headers)
        now = datetime.now(UTC)
        # One recent (15 min ago) — should appear; one old (45 min ago)
        # — should NOT appear under the default window. Bundle ids are
        # unique to this test so other TestSignalsAPI tests' drifts don't
        # interfere with the assertions.
        client.post(
            "/api/signals/drift",
            json={
                "started_at": (now - timedelta(minutes=15)).isoformat(),
                "duration_seconds": 60.0,
                "bundle_id": "com.defaultsince.recent",
            },
            headers=device_headers,
        )
        client.post(
            "/api/signals/drift",
            json={
                "started_at": (now - timedelta(minutes=45)).isoformat(),
                "duration_seconds": 60.0,
                "bundle_id": "com.defaultsince.old",
            },
            headers=device_headers,
        )

        resp = client.get("/api/signals/recent-drift", headers=device_headers)
        assert resp.status_code == 200
        ours = {
            e["bundle_id"]
            for e in resp.json()["events"]
            if e["bundle_id"].startswith("com.defaultsince.")
        }
        assert ours == {"com.defaultsince.recent"}

    def test_recent_drift_respects_limit(self, client, auth_headers):
        """Limit caps the response so a runaway day of distractions
        doesn't return a multi-MB payload to a polling phone."""
        _, device_headers = _pair_device(client, auth_headers)
        now = datetime.now(UTC)
        # Pin `since` to 5 seconds ago so prior tests' drifts stay out
        # of the slice; the loop posts 5 events within that window.
        slice_start = now - timedelta(seconds=5)
        for i in range(5):
            client.post(
                "/api/signals/drift",
                json={
                    "started_at": (now - timedelta(seconds=4 - i * 0.5)).isoformat(),
                    "duration_seconds": 5.0,
                    "bundle_id": f"com.limittest.{i}",
                },
                headers=device_headers,
            )
        resp = client.get(
            "/api/signals/recent-drift",
            params={"limit": 2, "since": slice_start.isoformat()},
            headers=device_headers,
        )
        assert resp.status_code == 200
        assert len(resp.json()["events"]) == 2

    def test_recent_drift_requires_auth(self, client):
        """No token → 401, same as every other read endpoint."""
        resp = client.get("/api/signals/recent-drift")
        assert resp.status_code == 401
