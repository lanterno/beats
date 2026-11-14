"""Flow windows and signal summaries: the device token's write, the
editor context, the filters, the summary, the CSV export and the
delete.

Split out of `test_api.py` at the size ceiling (CLAUDE.md § Conventions); the
harness is `conftest.py`'s and the shared fixtures `api_helpers.py`'s.
"""

from datetime import UTC, datetime, timedelta

from api_helpers import _pair_device


class TestSignalsAPI:
    """Flow windows and signal summaries over HTTP."""

    def test_post_flow_window_with_device_token(self, client, auth_headers):
        """Device token can POST a flow window."""
        _, device_headers = _pair_device(client, auth_headers)
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
        _, device_headers = _pair_device(client, auth_headers)
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
        _, device_headers = _pair_device(client, auth_headers)
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
        _, device_headers = _pair_device(client, auth_headers)
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
        _, device_headers = _pair_device(client, auth_headers)
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
        _, device_headers = _pair_device(client, auth_headers)
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
        _pair_device(client, auth_headers)
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
        _, device_headers = _pair_device(client, auth_headers)
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
        _, device_headers = _pair_device(client, auth_headers)
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
        _, device_headers = _pair_device(client, auth_headers)
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
        _, device_headers = _pair_device(client, auth_headers)
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
        _, device_headers = _pair_device(client, auth_headers)
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
        _, device_headers = _pair_device(client, auth_headers)
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
        _, device_headers = _pair_device(client, auth_headers)
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
        _, device_headers = _pair_device(client, auth_headers)
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
        _, device_headers = _pair_device(client, auth_headers)
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
        _, device_headers = _pair_device(client, auth_headers)
        resp = client.get("/api/analytics/rhythm", headers=device_headers)
        assert resp.status_code == 403

    def test_device_token_reads_coach_memory_but_cannot_change_it(self, client, auth_headers):
        """A read-only prefix lets a device GET and nothing else: deleting or
        rewriting the coach's memory stays with a signed-in browser."""
        _, device_headers = _pair_device(client, auth_headers)

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
        _, device_headers = _pair_device(client, auth_headers)
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
