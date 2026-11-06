"""The daemon's signals: flow windows, the timer suggestion and its
pending poll, drift, and the signal summaries.

Split out of `test_api.py` at the ceiling in roadmaps/file-sizes.md; the
harness is `conftest.py`'s and the shared fixtures `api_helpers.py`'s.
"""

from datetime import UTC, datetime, timedelta


class TestSignalsAPI:
    """Test suite for signals (flow windows + signal summaries) endpoints."""

    def _pair_device(self, client, auth_headers):
        """Helper: pair a device and return (device_token, device_headers)."""
        resp = client.post("/api/device/pair/code", headers=auth_headers)
        code = resp.json()["code"]
        resp = client.post("/api/device/pair/exchange", json={"code": code})
        data = resp.json()
        return data["device_token"], {"Authorization": f"Bearer {data['device_token']}"}

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

        _, device_headers = self._pair_device(client, auth_headers)
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

        _, device_headers = self._pair_device(client, auth_headers)
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

        _, device_headers = self._pair_device(client, auth_headers)
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
        _, device_headers = self._pair_device(client, auth_headers)
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

        _, device_headers = self._pair_device(client, auth_headers)
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
        _, device_headers = self._pair_device(client, auth_headers)
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

        _, device_headers = self._pair_device(client, auth_headers)
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
        _, device_headers = self._pair_device(client, auth_headers)
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
        _, device_headers = self._pair_device(client, auth_headers)
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
        _, device_headers = self._pair_device(client, auth_headers)
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
        _, device_headers = self._pair_device(client, auth_headers)
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
        _, device_headers = self._pair_device(client, auth_headers)
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

    def test_post_flow_window_with_device_token(self, client, auth_headers):
        """Device token can POST a flow window."""
        _, device_headers = self._pair_device(client, auth_headers)
        now = datetime.now(UTC)
        resp = client.post(
            "/api/signals/flow-windows",
            json={
                "window_start": (now - timedelta(minutes=1)).isoformat(),
                "window_end": now.isoformat(),
                "flow_score": 0.75,
                "cadence_score": 0.5,
                "coherence_score": 1.0,
                "category_fit_score": 0.0,
                "idle_fraction": 0.1,
                "dominant_bundle_id": "com.apple.dt.Xcode",
                "dominant_category": "coding",
                "context_switches": 2,
            },
            headers=device_headers,
        )
        assert resp.status_code == 201
        assert "id" in resp.json()

    def test_flow_window_round_trips_editor_context(self, client, auth_headers):
        """Editor heartbeat fields (repo, branch, language) round-trip."""
        _, device_headers = self._pair_device(client, auth_headers)
        now = datetime.now(UTC)
        client.post(
            "/api/signals/flow-windows",
            json={
                "window_start": (now - timedelta(minutes=1)).isoformat(),
                "window_end": now.isoformat(),
                "flow_score": 0.92,
                "cadence_score": 0.9,
                "coherence_score": 1.0,
                "category_fit_score": 1.0,
                "idle_fraction": 0.0,
                "dominant_bundle_id": "com.microsoft.VSCode",
                "dominant_category": "coding",
                "editor_repo": "/Users/me/code/example",
                "editor_branch": "main",
                "editor_language": "go",
            },
            headers=device_headers,
        )
        resp = client.get(
            "/api/signals/flow-windows",
            params={
                "start": (now - timedelta(hours=1)).isoformat(),
                "end": (now + timedelta(hours=1)).isoformat(),
            },
            headers=auth_headers,
        )
        assert resp.status_code == 200
        match = next((w for w in resp.json() if w["flow_score"] == 0.92), None)
        assert match is not None, "posted flow window not found in list"
        assert match["editor_repo"] == "/Users/me/code/example"
        assert match["editor_branch"] == "main"
        assert match["editor_language"] == "go"

    def test_flow_windows_filter_by_project_id(self, client, auth_headers):
        """GET /api/signals/flow-windows?project_id=X returns only windows
        whose active_project_id matches."""
        _, device_headers = self._pair_device(client, auth_headers)
        now = datetime.now(UTC)
        # Two windows tagged with different project ids.
        for pid, score in [("proj-A", 0.4), ("proj-B", 0.81)]:
            client.post(
                "/api/signals/flow-windows",
                json={
                    "window_start": (now - timedelta(minutes=2)).isoformat(),
                    "window_end": (now - timedelta(minutes=1)).isoformat(),
                    "flow_score": score,
                    "cadence_score": 0.5,
                    "coherence_score": 0.5,
                    "category_fit_score": 0.0,
                    "idle_fraction": 0.0,
                    "dominant_bundle_id": "com.apple.dt.Xcode",
                    "dominant_category": "coding",
                    "active_project_id": pid,
                },
                headers=device_headers,
            )

        resp = client.get(
            "/api/signals/flow-windows",
            params={
                "start": (now - timedelta(hours=1)).isoformat(),
                "end": (now + timedelta(hours=1)).isoformat(),
                "project_id": "proj-B",
            },
            headers=auth_headers,
        )
        assert resp.status_code == 200
        windows = resp.json()
        # Only proj-B's window comes back, no cross-contamination.
        assert all(w["active_project_id"] == "proj-B" for w in windows)
        assert any(w["flow_score"] == 0.81 for w in windows)

    def test_flow_windows_filter_by_editor_repo(self, client, auth_headers):
        """GET /api/signals/flow-windows?editor_repo=… narrows to that
        workspace path, used by future per-repo UI views."""
        _, device_headers = self._pair_device(client, auth_headers)
        now = datetime.now(UTC)
        for repo_path, score in [
            ("/Users/me/code/alpha", 0.55),
            ("/Users/me/code/beta", 0.77),
        ]:
            client.post(
                "/api/signals/flow-windows",
                json={
                    "window_start": (now - timedelta(minutes=2)).isoformat(),
                    "window_end": (now - timedelta(minutes=1)).isoformat(),
                    "flow_score": score,
                    "cadence_score": 0.5,
                    "coherence_score": 0.5,
                    "category_fit_score": 1.0,
                    "idle_fraction": 0.0,
                    "dominant_bundle_id": "com.microsoft.VSCode",
                    "dominant_category": "coding",
                    "editor_repo": repo_path,
                },
                headers=device_headers,
            )

        resp = client.get(
            "/api/signals/flow-windows",
            params={
                "start": (now - timedelta(hours=1)).isoformat(),
                "end": (now + timedelta(hours=1)).isoformat(),
                "editor_repo": "/Users/me/code/beta",
            },
            headers=auth_headers,
        )
        assert resp.status_code == 200
        windows = resp.json()
        assert all(w["editor_repo"] == "/Users/me/code/beta" for w in windows)
        assert any(w["flow_score"] == 0.77 for w in windows)

    def test_flow_windows_filter_by_editor_language(self, client, auth_headers):
        """GET /api/signals/flow-windows?editor_language=… narrows to that
        language id, used for click-to-filter on FlowByLanguage."""
        _, device_headers = self._pair_device(client, auth_headers)
        now = datetime.now(UTC)
        for lang, score in [("go", 0.61), ("typescript", 0.83)]:
            client.post(
                "/api/signals/flow-windows",
                json={
                    "window_start": (now - timedelta(minutes=2)).isoformat(),
                    "window_end": (now - timedelta(minutes=1)).isoformat(),
                    "flow_score": score,
                    "cadence_score": 0.5,
                    "coherence_score": 0.5,
                    "category_fit_score": 1.0,
                    "idle_fraction": 0.0,
                    "dominant_bundle_id": "com.microsoft.VSCode",
                    "dominant_category": "coding",
                    "editor_language": lang,
                },
                headers=device_headers,
            )

        resp = client.get(
            "/api/signals/flow-windows",
            params={
                "start": (now - timedelta(hours=1)).isoformat(),
                "end": (now + timedelta(hours=1)).isoformat(),
                "editor_language": "typescript",
            },
            headers=auth_headers,
        )
        assert resp.status_code == 200
        windows = resp.json()
        assert all(w["editor_language"] == "typescript" for w in windows)
        assert any(w["flow_score"] == 0.83 for w in windows)

    def test_flow_windows_summary_aggregates_and_picks_top_buckets(self, client, auth_headers):
        """GET /api/signals/flow-windows/summary returns avg/peak/count
        plus the top bucket on each grouping axis in a single round-trip,
        honoring the same filter params as the JSON endpoint."""
        _, device_headers = self._pair_device(client, auth_headers)
        now = datetime.now(UTC)
        # Use a bundle id no other test in the class POSTs, then filter by
        # it so prior windows in the shared class state can't leak in.
        marker_bundle = "com.test.summary_aggregate_marker"
        # Two go windows on the beats repo, one rust window on a different repo.
        # The summary should call out beats + go + that bundle as the top buckets.
        rows = [
            ("/Users/me/code/beats-summary", "go", 0.8),
            ("/Users/me/code/beats-summary", "go", 0.9),
            ("/Users/me/code/other-summary", "rust", 0.3),
        ]
        for repo_path, lang, score in rows:
            client.post(
                "/api/signals/flow-windows",
                json={
                    "window_start": (now - timedelta(minutes=2)).isoformat(),
                    "window_end": (now - timedelta(minutes=1)).isoformat(),
                    "flow_score": score,
                    "cadence_score": 0.5,
                    "coherence_score": 0.5,
                    "category_fit_score": 1.0,
                    "idle_fraction": 0.0,
                    "dominant_bundle_id": marker_bundle,
                    "dominant_category": "coding",
                    "editor_repo": repo_path,
                    "editor_language": lang,
                },
                headers=device_headers,
            )

        resp = client.get(
            "/api/signals/flow-windows/summary",
            params={
                "start": (now - timedelta(hours=1)).isoformat(),
                "end": (now + timedelta(hours=1)).isoformat(),
                "bundle_id": marker_bundle,
            },
            headers=auth_headers,
        )
        assert resp.status_code == 200
        body = resp.json()

        assert body["count"] == 3
        assert abs(body["avg"] - (0.8 + 0.9 + 0.3) / 3) < 1e-6
        assert body["peak"] == 0.9
        assert body["peak_at"] is not None

        assert body["top_repo"]["key"] == "/Users/me/code/beats-summary"
        assert body["top_repo"]["count"] == 2
        assert body["top_language"]["key"] == "go"
        assert body["top_language"]["count"] == 2
        assert body["top_bundle"]["key"] == marker_bundle
        assert body["top_bundle"]["count"] == 3

    def test_flow_windows_summary_empty_slice_returns_zeros(self, client, auth_headers):
        """No windows in the range → zero/None response, not 404 — callers
        can render an empty state without parsing an error."""
        self._pair_device(client, auth_headers)
        now = datetime.now(UTC)
        resp = client.get(
            "/api/signals/flow-windows/summary",
            params={
                "start": (now - timedelta(hours=2)).isoformat(),
                "end": (now - timedelta(hours=1)).isoformat(),
            },
            headers=auth_headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["count"] == 0
        assert body["avg"] == 0.0
        assert body["peak"] == 0.0
        assert body["peak_at"] is None
        assert body["top_repo"] is None
        assert body["top_language"] is None
        assert body["top_bundle"] is None

    def test_flow_windows_summary_respects_filter(self, client, auth_headers):
        """The summary honors the language filter — same slice the user
        sees in the chip-row download is what the summary endpoint
        aggregates. Uses a unique marker repo to avoid pollution from
        other tests in this shared-state class."""
        _, device_headers = self._pair_device(client, auth_headers)
        now = datetime.now(UTC)
        marker_repo = "/Users/me/code/summary-filter-marker"
        for lang, score in [("haskell", 0.9), ("scala", 0.4), ("scala", 0.5)]:
            client.post(
                "/api/signals/flow-windows",
                json={
                    "window_start": (now - timedelta(minutes=2)).isoformat(),
                    "window_end": (now - timedelta(minutes=1)).isoformat(),
                    "flow_score": score,
                    "cadence_score": 0.5,
                    "coherence_score": 0.5,
                    "category_fit_score": 1.0,
                    "idle_fraction": 0.0,
                    "dominant_bundle_id": "com.microsoft.VSCode",
                    "dominant_category": "coding",
                    "editor_repo": marker_repo,
                    "editor_language": lang,
                },
                headers=device_headers,
            )

        resp = client.get(
            "/api/signals/flow-windows/summary",
            params={
                "start": (now - timedelta(hours=1)).isoformat(),
                "end": (now + timedelta(hours=1)).isoformat(),
                "editor_repo": marker_repo,
                "editor_language": "scala",
            },
            headers=auth_headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["count"] == 2
        assert abs(body["avg"] - 0.45) < 1e-6
        assert body["top_language"]["key"] == "scala"

    def test_csv_filename_helper_single_day(self):
        """Single-day range gets a single date in the filename."""
        from beats.api.routers.signals import _csv_filename_for_range

        start = datetime(2026, 4, 1, 9, 0, 0, tzinfo=UTC)
        end = datetime(2026, 4, 1, 18, 0, 0, tzinfo=UTC)
        assert _csv_filename_for_range(start, end) == "beats_flow_windows_20260401.csv"

    def test_csv_filename_helper_multi_day(self):
        """Multi-day range uses the start_to_end form so the file
        name reflects what the user actually downloaded."""
        from beats.api.routers.signals import _csv_filename_for_range

        start = datetime(2026, 4, 1, 0, 0, 0, tzinfo=UTC)
        end = datetime(2026, 4, 30, 23, 59, 59, tzinfo=UTC)
        assert _csv_filename_for_range(start, end) == "beats_flow_windows_20260401_to_20260430.csv"

    def test_csv_filename_helper_is_utc_stable(self):
        """A user in UTC+02:00 exporting at 01:30 local on April 2nd
        is exporting a range that's still April 1st in UTC. The
        filename should reflect the UTC date so it's stable across
        timezones."""
        from datetime import timezone

        from beats.api.routers.signals import _csv_filename_for_range

        # 01:30 on 2026-04-02 in UTC+02:00 == 23:30 on 2026-04-01 in UTC.
        plus2 = timezone(timedelta(hours=2))
        start = datetime(2026, 4, 2, 1, 30, 0, tzinfo=plus2)
        end = datetime(2026, 4, 2, 1, 45, 0, tzinfo=plus2)
        assert _csv_filename_for_range(start, end) == "beats_flow_windows_20260401.csv"

    def test_flow_windows_csv_export_respects_filter(self, client, auth_headers):
        """GET /api/signals/flow-windows.csv streams a CSV that honors
        the same filter params as the JSON endpoint, so the "Download"
        button on Insights returns exactly the visible slice."""
        _, device_headers = self._pair_device(client, auth_headers)
        now = datetime.now(UTC)
        for lang, score in [("go", 0.74), ("typescript", 0.55)]:
            client.post(
                "/api/signals/flow-windows",
                json={
                    "window_start": (now - timedelta(minutes=2)).isoformat(),
                    "window_end": (now - timedelta(minutes=1)).isoformat(),
                    "flow_score": score,
                    "cadence_score": 0.5,
                    "coherence_score": 0.5,
                    "category_fit_score": 1.0,
                    "idle_fraction": 0.0,
                    "dominant_bundle_id": "com.microsoft.VSCode",
                    "dominant_category": "coding",
                    "editor_language": lang,
                },
                headers=device_headers,
            )

        resp = client.get(
            "/api/signals/flow-windows.csv",
            params={
                "start": (now - timedelta(hours=1)).isoformat(),
                "end": (now + timedelta(hours=1)).isoformat(),
                "editor_language": "go",
            },
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/csv")
        assert "attachment" in resp.headers["content-disposition"]

        body = resp.text
        # Header row + at least one data row, only the "go" rows.
        lines = [ln for ln in body.splitlines() if ln.strip()]
        assert lines[0].startswith("window_start,window_end,flow_score")
        assert "0.7400" in body
        assert "0.5500" not in body  # the typescript row should be filtered out
        assert "com.microsoft.VSCode" in body
        # The filename in Content-Disposition reflects the queried
        # range, not today's date. Single-day query (start and end
        # within the same UTC day) produces `..._YYYYMMDD.csv`. The
        # query above straddles ±1h around `now` so it lives within
        # one day in either direction; assert the start side appears.
        cd = resp.headers["content-disposition"]
        # Compute the same start_day the helper would have used.
        start_day = (now - timedelta(hours=1)).astimezone(UTC).strftime("%Y%m%d")
        assert f"beats_flow_windows_{start_day}" in cd, cd

    def test_flow_windows_filter_by_bundle_id(self, client, auth_headers):
        """GET /api/signals/flow-windows?bundle_id=… narrows to that
        macOS bundle id, used for click-to-filter on FlowByApp."""
        _, device_headers = self._pair_device(client, auth_headers)
        now = datetime.now(UTC)
        for bundle, score in [
            ("com.microsoft.VSCode", 0.82),
            ("com.apple.Safari", 0.31),
        ]:
            client.post(
                "/api/signals/flow-windows",
                json={
                    "window_start": (now - timedelta(minutes=2)).isoformat(),
                    "window_end": (now - timedelta(minutes=1)).isoformat(),
                    "flow_score": score,
                    "cadence_score": 0.5,
                    "coherence_score": 0.5,
                    "category_fit_score": 1.0,
                    "idle_fraction": 0.0,
                    "dominant_bundle_id": bundle,
                    "dominant_category": "coding",
                },
                headers=device_headers,
            )

        resp = client.get(
            "/api/signals/flow-windows",
            params={
                "start": (now - timedelta(hours=1)).isoformat(),
                "end": (now + timedelta(hours=1)).isoformat(),
                "bundle_id": "com.microsoft.VSCode",
            },
            headers=auth_headers,
        )
        assert resp.status_code == 200
        windows = resp.json()
        assert all(w["dominant_bundle_id"] == "com.microsoft.VSCode" for w in windows)
        assert any(w["flow_score"] == 0.82 for w in windows)

    def test_flow_window_without_editor_context_still_validates(self, client, auth_headers):
        """Older daemons that don't send editor_* fields are still accepted."""
        _, device_headers = self._pair_device(client, auth_headers)
        now = datetime.now(UTC)
        resp = client.post(
            "/api/signals/flow-windows",
            json={
                "window_start": (now - timedelta(minutes=1)).isoformat(),
                "window_end": now.isoformat(),
                "flow_score": 0.4,
                "cadence_score": 0.5,
                "coherence_score": 0.5,
                "category_fit_score": 0.0,
                "idle_fraction": 0.5,
                "dominant_bundle_id": "com.apple.Safari",
                "dominant_category": "browser",
            },
            headers=device_headers,
        )
        assert resp.status_code == 201

    def test_read_flow_windows_with_session_token(self, client, auth_headers):
        """Session token can read flow windows posted by the device."""
        _, device_headers = self._pair_device(client, auth_headers)
        now = datetime.now(UTC)

        # Post a window
        client.post(
            "/api/signals/flow-windows",
            json={
                "window_start": (now - timedelta(minutes=1)).isoformat(),
                "window_end": now.isoformat(),
                "flow_score": 0.8,
                "cadence_score": 0.5,
                "coherence_score": 1.0,
                "category_fit_score": 1.0,
                "idle_fraction": 0.0,
                "dominant_bundle_id": "com.microsoft.VSCode",
                "dominant_category": "coding",
            },
            headers=device_headers,
        )

        # Read back with session token
        resp = client.get(
            "/api/signals/flow-windows",
            params={
                "start": (now - timedelta(hours=1)).isoformat(),
                "end": (now + timedelta(hours=1)).isoformat(),
            },
            headers=auth_headers,
        )
        assert resp.status_code == 200
        windows = resp.json()
        assert len(windows) >= 1
        assert any(w["flow_score"] == 0.8 for w in windows)

    def test_post_signal_summary(self, client, auth_headers):
        """Device token can POST signal summaries."""
        _, device_headers = self._pair_device(client, auth_headers)
        now = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)

        resp = client.post(
            "/api/signals/summaries",
            json={
                "hour": now.isoformat(),
                "categories": {"coding": 50, "browser": 10},
                "total_samples": 60,
                "idle_samples": 5,
            },
            headers=device_headers,
        )
        assert resp.status_code == 200
        assert "id" in resp.json()

    def test_read_signal_summaries(self, client, auth_headers):
        """Session token can read signal summaries."""
        _, device_headers = self._pair_device(client, auth_headers)
        now = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)

        # Post a summary
        client.post(
            "/api/signals/summaries",
            json={
                "hour": now.isoformat(),
                "categories": {"coding": 42},
                "total_samples": 42,
                "idle_samples": 0,
            },
            headers=device_headers,
        )

        # Read back
        resp = client.get(
            "/api/signals/summaries",
            params={
                "start": (now - timedelta(hours=1)).isoformat(),
                "end": (now + timedelta(hours=1)).isoformat(),
            },
            headers=auth_headers,
        )
        assert resp.status_code == 200
        summaries = resp.json()
        assert len(summaries) >= 1

    def test_summary_upsert(self, client, auth_headers):
        """Posting the same hour twice upserts (updates, not duplicates)."""
        _, device_headers = self._pair_device(client, auth_headers)
        now = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)

        # First post
        client.post(
            "/api/signals/summaries",
            json={"hour": now.isoformat(), "categories": {"coding": 10}, "total_samples": 10},
            headers=device_headers,
        )
        # Second post (same hour, different data)
        client.post(
            "/api/signals/summaries",
            json={"hour": now.isoformat(), "categories": {"coding": 20}, "total_samples": 20},
            headers=device_headers,
        )

        # Should have exactly one summary for this hour
        resp = client.get(
            "/api/signals/summaries",
            params={
                "start": (now - timedelta(minutes=1)).isoformat(),
                "end": (now + timedelta(minutes=1)).isoformat(),
            },
            headers=auth_headers,
        )
        summaries = resp.json()
        matching = [s for s in summaries if s["total_samples"] == 20]
        assert len(matching) == 1

    def test_delete_all_signals(self, client, auth_headers):
        """DELETE /api/signals/all removes all summaries."""
        _, device_headers = self._pair_device(client, auth_headers)
        now = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)

        client.post(
            "/api/signals/summaries",
            json={"hour": now.isoformat(), "categories": {"coding": 5}, "total_samples": 5},
            headers=device_headers,
        )

        resp = client.delete("/api/signals/all", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["deleted_summaries"] >= 1

    def test_device_token_blocked_on_non_allowed_paths(self, client, auth_headers):
        """Device token cannot access endpoints outside DEVICE_ALLOWED_PREFIXES."""
        _, device_headers = self._pair_device(client, auth_headers)
        resp = client.get("/api/analytics/rhythm", headers=device_headers)
        assert resp.status_code == 403

    def test_device_token_reads_coach_memory_but_cannot_change_it(self, client, auth_headers):
        """A read-only prefix lets a device GET and nothing else: deleting or
        rewriting the coach's memory stays with a signed-in browser."""
        _, device_headers = self._pair_device(client, auth_headers)

        assert client.get("/api/coach/memory", headers=device_headers).status_code == 200

        for method, path in [
            ("delete", "/api/coach/memory"),
            ("post", "/api/coach/memory/rewrite"),
        ]:
            resp = client.request(method.upper(), path, headers=device_headers)
            assert resp.status_code == 403, (method, path)
            assert resp.json()["code"] == "DEVICE_PATH_FORBIDDEN"

    def test_flow_window_validation(self, client, auth_headers):
        """Flow score values are validated to [0, 1]."""
        _, device_headers = self._pair_device(client, auth_headers)
        now = datetime.now(UTC)
        resp = client.post(
            "/api/signals/flow-windows",
            json={
                "window_start": now.isoformat(),
                "window_end": now.isoformat(),
                "flow_score": 1.5,  # out of range
                "cadence_score": 0.5,
                "coherence_score": 0.5,
                "category_fit_score": 0.5,
                "idle_fraction": 0.0,
            },
            headers=device_headers,
        )
        assert resp.status_code == 422
