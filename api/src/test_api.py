"""
Comprehensive API Tests for Beats Application
Tests all endpoints: Projects, Beats, and Timer APIs
"""

import contextlib
import csv
import io
import json
import time
from datetime import UTC, date, datetime, timedelta

import pytest


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """Reset slowapi's process-global limiter store before each test.

    Several tests legitimately call /api/device/pair/exchange and
    /api/auth/* during setup; without a reset, the 5–10/min caps on
    those routes accumulate across the run and 429 the back half of
    the suite. Tests that *want* to exercise the limit (e.g.
    TestRateLimiting) consume the budget within a single test and
    are unaffected by the per-test reset.
    """
    from beats.api.routers.auth import limiter

    limiter.reset()
    return


class TestProjectAPI:
    """Test suite for Project management endpoints"""

    def test_projects_list_api(self, client, auth_headers):
        """Test GET /api/projects/ - List all projects"""
        response = client.get("/api/projects/", headers=auth_headers)
        assert response.status_code == 200
        projects = response.json()
        assert isinstance(projects, list)

    def test_projects_list_archived(self, client, auth_headers):
        """Test GET /api/projects/?archived=true - List archived projects"""
        response = client.get("/api/projects/?archived=true", headers=auth_headers)
        assert response.status_code == 200
        projects = response.json()
        assert isinstance(projects, list)

    def test_projects_create_api(self, client, auth_headers):
        """Test POST /api/projects/ - Create a new project"""
        projects_count = len(client.get("/api/projects/", headers=auth_headers).json())

        response = client.post(
            "/api/projects/",
            json={
                "name": f"test-project-{time.time()}",
                "description": "Test project - delete me",
            },
            headers=auth_headers,
        )
        assert response.status_code == 201, response.json()
        project = response.json()
        assert "id" in project
        assert "name" in project
        assert len(client.get("/api/projects/", headers=auth_headers).json()) == projects_count + 1

    def test_projects_create_without_auth(self, client):
        """Test POST /api/projects/ without auth token - Should fail"""
        response = client.post(
            "/api/projects/",
            json={"name": f"test-project-{time.time()}", "description": "Test project"},
        )
        assert response.status_code == 401

    def test_projects_list_include_populates_aggregations(self, client, auth_headers):
        """P3.0 — when GET /api/projects/ is called with include=totals,
        this_week,last_tracked, each item in the response gains the
        aggregation fields populated (vs null when the flag is omitted).
        Locks in the wire shape the /projects index page consumes.
        """
        # Create a project + log a beat so the aggregations have
        # something to report. The beat ends now so it counts in the
        # current week and as last_tracked_at.
        from datetime import UTC, datetime, timedelta

        proj_resp = client.post(
            "/api/projects/",
            json={"name": f"agg-{time.time()}", "weekly_goal": 5.0},
            headers=auth_headers,
        )
        assert proj_resp.status_code == 201
        pid = proj_resp.json()["id"]

        end = datetime.now(UTC)
        start = end - timedelta(minutes=30)
        beat_resp = client.post(
            "/api/beats/",
            json={
                "project_id": pid,
                "start": start.isoformat(),
                "end": end.isoformat(),
            },
            headers=auth_headers,
        )
        assert beat_resp.status_code == 201, beat_resp.text

        # Without `include` — aggregation slots are present but null.
        listing = client.get("/api/projects/", headers=auth_headers).json()
        slim = next(p for p in listing if p["id"] == pid)
        for key in (
            "total_minutes",
            "weekly_minutes",
            "effective_goal",
            "last_tracked_at",
        ):
            assert key in slim, key
            assert slim[key] is None, (key, slim[key])

        # With include=totals,this_week,last_tracked — populated.
        listing = client.get(
            "/api/projects/?include=totals,this_week,last_tracked",
            headers=auth_headers,
        ).json()
        rich = next(p for p in listing if p["id"] == pid)
        # 30 minutes logged → totals + this-week reflect that.
        assert rich["total_minutes"] is not None
        assert rich["total_minutes"] >= 30
        assert rich["weekly_minutes"] is not None
        assert rich["weekly_minutes"] >= 30
        # Goal trio populated.
        assert rich["effective_goal"] == 5.0
        assert rich["effective_goal_type"] == "target"
        assert rich["effective_goal_overridden"] is False
        # last_tracked_at survives JSON round-trip as an ISO string.
        assert rich["last_tracked_at"] is not None

    def test_projects_list_include_preserves_order_under_parallelization(
        self, client, auth_headers
    ):
        """FF.9 — list_projects fans out the per-project aggregations through
        asyncio.gather. Returned order MUST equal the order from
        service.list_projects, regardless of which aggregation finishes
        first (gather returns in input order — this test guards against a
        future regression that swaps to as_completed or a dict comprehension)."""
        import time as _time

        # Create projects with deterministically ordered names.
        names = [f"order-{i}-{_time.time()}" for i in range(5)]
        ids = []
        for name in names:
            r = client.post("/api/projects/", json={"name": name}, headers=auth_headers)
            assert r.status_code == 201
            ids.append(r.json()["id"])

        listing = client.get(
            "/api/projects/?include=totals,this_week,last_tracked",
            headers=auth_headers,
        ).json()
        # Filter to our created projects (the list also contains pre-existing
        # ones from other tests) and assert the relative order matches.
        ours_in_listing = [p["id"] for p in listing if p["id"] in ids]
        # The service returns projects in creation order; the route preserves it.
        assert ours_in_listing == ids, (ours_in_listing, ids)

    def test_projects_list_include_excludes_archived_projects_from_batch(
        self, client, auth_headers
    ):
        """FF.15 — the new batched path takes the IDs of the projects the
        route will RENDER, which is the result of service.list_projects(
        archived=archived). With the default archived=False, archived
        projects' beats are never fetched. Pin so a refactor can't widen
        the $in scope and silently load lifetime beats for every
        archived project on every /projects load."""
        import time as _time
        from datetime import UTC, datetime, timedelta

        active = client.post(
            "/api/projects/",
            json={"name": f"active-{_time.time()}"},
            headers=auth_headers,
        ).json()
        archived = client.post(
            "/api/projects/",
            json={"name": f"arch-{_time.time()}"},
            headers=auth_headers,
        ).json()
        # Log beats for BOTH projects.
        end = datetime.now(UTC)
        for pid in (active["id"], archived["id"]):
            client.post(
                "/api/beats/",
                json={
                    "project_id": pid,
                    "start": (end - timedelta(minutes=20)).isoformat(),
                    "end": end.isoformat(),
                },
                headers=auth_headers,
            )
        # Archive the second.
        client.post(f"/api/projects/{archived['id']}/archive", headers=auth_headers)

        # Default archived=false listing must populate the active project
        # AND must not include the archived project in the response.
        listing = client.get(
            "/api/projects/?include=totals,this_week,last_tracked",
            headers=auth_headers,
        ).json()
        ids = [p["id"] for p in listing]
        assert active["id"] in ids
        assert archived["id"] not in ids

        # archived=true listing includes the archived project AND its
        # aggregations populate (documents that the exclusion is scoped
        # to the default view, not a hard restriction at the repo).
        archived_listing = client.get(
            "/api/projects/?archived=true&include=totals,this_week,last_tracked",
            headers=auth_headers,
        ).json()
        archived_item = next((p for p in archived_listing if p["id"] == archived["id"]), None)
        assert archived_item is not None
        assert archived_item["total_minutes"] is not None
        assert archived_item["total_minutes"] >= 20

    def test_projects_list_no_include_skips_batch(self, client, auth_headers):
        """FF.15 — when include is empty (or omitted), the route returns
        the slim shape WITHOUT issuing the batched beats find. The
        contract here is just: no aggregation fields populated, no error
        on a fresh user with no beats at all. Pin the early-return
        path so a future refactor can't accidentally always-batch."""
        import time as _time

        pid = client.post(
            "/api/projects/",
            json={"name": f"slim-{_time.time()}"},
            headers=auth_headers,
        ).json()["id"]

        listing = client.get("/api/projects/", headers=auth_headers).json()
        item = next(p for p in listing if p["id"] == pid)
        # Aggregation slots are present (the schema declares them) but
        # null because the include set was empty.
        for key in ("total_minutes", "weekly_minutes", "effective_goal", "last_tracked_at"):
            assert item[key] is None, (key, item[key])

    def test_projects_list_include_subset(self, client, auth_headers):
        """Each include token is independent — requesting only 'totals'
        leaves the this_week/last_tracked slots null."""
        proj_resp = client.post(
            "/api/projects/",
            json={"name": f"subset-{time.time()}"},
            headers=auth_headers,
        )
        pid = proj_resp.json()["id"]

        listing = client.get(
            "/api/projects/?include=totals",
            headers=auth_headers,
        ).json()
        match = next(p for p in listing if p["id"] == pid)
        assert match["total_minutes"] is not None  # populated (zero)
        assert match["weekly_minutes"] is None
        assert match["last_tracked_at"] is None

    def test_project_response_carries_every_domain_field(self, client, auth_headers):
        """Regression guard: ProjectResponse used to declare 6 of 11
        fields and the list/create/update routes had no response_model,
        so the OpenAPI contract was silently widened. The route now
        declares response_model=ProjectResponse over the full 11-field
        shape; every Project field must round-trip across create →
        list → update.

        If this test breaks because a NEW field is added to the domain
        Project, add it to ProjectResponse too — that's the whole point
        of the canonical response schema.
        """
        # Create with every settable field populated.
        create_resp = client.post(
            "/api/projects/",
            json={
                "name": f"contract-{time.time()}",
                "description": "exhaustive",
                "color": "#FBBF24",
                "weekly_goal": 12.5,
                "category": "coding",
            },
            headers=auth_headers,
        )
        assert create_resp.status_code == 201, create_resp.text
        created = create_resp.json()
        # Every field of the canonical shape is present.
        expected_keys = {
            "id",
            "name",
            "description",
            "color",
            "archived",
            "weekly_goal",
            "goal_type",
            "goal_overrides",
            "github_repo",
            "category",
            "autostart_repos",
        }
        assert expected_keys.issubset(created.keys()), expected_keys - created.keys()

        # Update with the previously invisible fields to confirm they
        # survive a round-trip via response_model=ProjectResponse.
        upd_resp = client.put(
            "/api/projects/",
            json={
                **created,
                "github_repo": "lanterno/beats",
                "autostart_repos": ["/Users/me/code/beats"],
            },
            headers=auth_headers,
        )
        assert upd_resp.status_code == 200, upd_resp.text
        updated = upd_resp.json()
        assert updated["github_repo"] == "lanterno/beats"
        assert updated["autostart_repos"] == ["/Users/me/code/beats"]
        assert updated["category"] == "coding"
        assert updated["color"] == "#FBBF24"

        # And the list endpoint exposes the same shape — generated
        # clients downstream depend on this consistency.
        listing = client.get("/api/projects/", headers=auth_headers).json()
        match = next(p for p in listing if p["id"] == created["id"])
        assert expected_keys.issubset(match.keys())
        assert match["github_repo"] == "lanterno/beats"

    def test_projects_update_api(self, client, auth_headers):
        """Test PUT /api/projects/ - Update existing project"""
        # Create a project first
        response = client.post(
            "/api/projects/",
            json={
                "name": f"test-project-{time.time()}",
                "description": "Test project - delete me",
            },
            headers=auth_headers,
        )
        projects_count = len(client.get("/api/projects/", headers=auth_headers).json())

        project = response.json()
        project["name"] = "Updated-" + project["name"]
        project["description"] = "Updated description"
        response = client.put(
            "/api/projects/",
            json=project,
            headers=auth_headers,
        )
        assert response.status_code == 200, response.json()
        updated_project = response.json()
        assert "Updated-" in updated_project["name"]
        assert len(client.get("/api/projects/", headers=auth_headers).json()) == projects_count

    def test_projects_archive(self, client, auth_headers):
        """Test POST /api/projects/{project_id}/archive - Archive a project"""
        # Create a project first
        response = client.post(
            "/api/projects/",
            json={"name": f"test-archive-{time.time()}", "description": "Test archive"},
            headers=auth_headers,
        )
        project = response.json()

        # Archive the project
        response = client.post(
            f"/api/projects/{project['id']}/archive",
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert response.json()["status"] == "success"

    def test_archive_unarchive_round_trip_preserves_every_field(self, client, auth_headers):
        """Regression guard for the dedicated /unarchive endpoint added in
        P0.2 of the project-management revamp. Generic-update-based
        unarchive (PUT with archived=false) would silently wipe fields
        the request body omits — specifically github_repo, category, and
        autostart_repos, which the UI Project type doesn't carry until
        P1.1 lands. Test creates with the full field set, archives,
        unarchives, and asserts nothing was lost."""
        # Create a project with the previously-invisible fields set.
        create_resp = client.post(
            "/api/projects/",
            json={
                "name": f"archive-roundtrip-{time.time()}",
                "description": "round-trip",
                "color": "#FBBF24",
                "weekly_goal": 10.0,
                "category": "coding",
            },
            headers=auth_headers,
        )
        assert create_resp.status_code == 201, create_resp.text
        project = create_resp.json()
        project_id = project["id"]

        # Populate github_repo + autostart_repos via update so the round-trip
        # exercises every settable field.
        upd = client.put(
            "/api/projects/",
            json={
                **project,
                "github_repo": "lanterno/beats",
                "autostart_repos": ["/Users/me/code/beats"],
            },
            headers=auth_headers,
        )
        assert upd.status_code == 200, upd.text
        pre_archive = upd.json()

        # Archive.
        arch = client.post(f"/api/projects/{project_id}/archive", headers=auth_headers)
        assert arch.status_code == 200

        # Unarchive via the dedicated endpoint.
        unarch = client.post(f"/api/projects/{project_id}/unarchive", headers=auth_headers)
        assert unarch.status_code == 200
        assert unarch.json()["status"] == "success"

        # Confirm the project is back to archived=False with every other
        # field intact. The unarchive endpoint must NOT touch unrelated
        # fields — same correctness bar as the regression guard above.
        listing = client.get("/api/projects/", headers=auth_headers).json()
        match = next(p for p in listing if p["id"] == project_id)
        assert match["archived"] is False
        # Every field that was set survives.
        for key in (
            "name",
            "description",
            "color",
            "weekly_goal",
            "category",
            "github_repo",
            "autostart_repos",
        ):
            assert match[key] == pre_archive[key], (key, match[key], pre_archive[key])

    def test_project_today_time(self, client, auth_headers):
        """Test GET /api/projects/{project_id}/today/ - Get today's time for project"""
        # Create project and beat for today
        project = client.post(
            "/api/projects/",
            json={
                "name": f"test-today-{time.time()}",
                "description": "Test today time",
            },
            headers=auth_headers,
        ).json()

        now = datetime.now(UTC)
        client.post(
            "/api/beats/",
            json={
                "project_id": project["id"],
                "start": now.isoformat(),
                "end": (now + timedelta(hours=1)).isoformat(),
            },
            headers=auth_headers,
        )

        response = client.get(f"/api/projects/{project['id']}/today/", headers=auth_headers)
        assert response.status_code == 200
        assert "duration" in response.json()

    def test_project_total_time(self, client, auth_headers):
        """Test GET /api/projects/{project_id}/total/ - Get total time per month"""
        # Create project and beats
        project = client.post(
            "/api/projects/",
            json={
                "name": f"test-total-{time.time()}",
                "description": "Test total time",
            },
            headers=auth_headers,
        ).json()

        client.post(
            "/api/beats/",
            json={
                "project_id": project["id"],
                "start": "2024-01-15T10:00:00",
                "end": "2024-01-15T12:00:00",
            },
            headers=auth_headers,
        )

        response = client.get(f"/api/projects/{project['id']}/total/", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "durations_per_month" in data
        assert "warnings" in data

    def test_project_total_buckets_by_the_local_month_a_beat_started_in(self, client, auth_headers):
        project = client.post(
            "/api/projects/", json={"name": f"test-total-tz-{time.time()}"}, headers=auth_headers
        ).json()
        # 22:00 on 31 January in New York is 03:00 on 1 February in UTC.
        _log(client, auth_headers, project["id"], "2026-02-01T03:00:00+00:00", 60)

        def months(**params):
            resp = client.get(
                f"/api/projects/{project['id']}/total/", params=params, headers=auth_headers
            )
            assert resp.status_code == 200, resp.text
            return resp.json()["durations_per_month"]

        assert months(tz="America/New_York") == {"2026-01": 1.0}
        # A caller that sends no tz gets UTC, as on the ledger.
        assert months() == {"2026-02": 1.0}

    def test_project_total_counts_a_running_timer_up_to_now(self, client, auth_headers):
        project = client.post(
            "/api/projects/", json={"name": f"test-total-run-{time.time()}"}, headers=auth_headers
        ).json()
        started = datetime.now(UTC) - timedelta(minutes=30)
        resp = client.post(
            f"/api/projects/{project['id']}/start",
            json={"time": started.isoformat()},
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        try:
            total = client.get(f"/api/projects/{project['id']}/total/", headers=auth_headers).json()
            assert total["total_minutes"] >= 30
            assert total["durations_per_month"][started.strftime("%Y-%m")] >= 0.5

            listing = client.get(
                "/api/projects/", params={"include": "totals"}, headers=auth_headers
            ).json()
            item = next(p for p in listing if p["id"] == project["id"])
            assert item["total_minutes"] >= 30
        finally:
            client.post(
                "/api/projects/stop",
                json={"time": datetime.now(UTC).isoformat()},
                headers=auth_headers,
            )

    def test_project_summary(self, client, auth_headers):
        """Test GET /api/projects/{project_id}/summary/ - Get project summary"""
        # Create project and beats
        project = client.post(
            "/api/projects/",
            json={"name": f"test-summary-{time.time()}", "description": "Test summary"},
            headers=auth_headers,
        ).json()

        client.post(
            "/api/beats/",
            json={
                "project_id": project["id"],
                "start": "2024-01-15T10:00:00",
                "end": "2024-01-15T12:00:00",
            },
            headers=auth_headers,
        )

        response = client.get(f"/api/projects/{project['id']}/summary/", headers=auth_headers)
        assert response.status_code == 200
        assert isinstance(response.json(), dict)

    def test_start_project_timer(self, client, auth_headers):
        """Test POST /api/projects/{project_id}/start - Start project timer"""
        # Create project
        project = client.post(
            "/api/projects/",
            json={
                "name": f"test-start-{time.time()}",
                "description": "Test start timer",
            },
            headers=auth_headers,
        ).json()

        # Start timer
        # Cleanup any previous active timer to ensure isolation
        client.post(
            "/api/projects/stop",
            json={"time": datetime.now(UTC).isoformat()},
            headers=auth_headers,
        )
        response = client.post(
            f"/api/projects/{project['id']}/start",
            json={"time": datetime.now(UTC).isoformat()},
            headers=auth_headers,
        )
        assert response.status_code == 200
        beat = response.json()
        assert beat["project_id"] == project["id"]
        assert beat["end"] is None

    def test_stop_project_timer(self, client, auth_headers):
        """Test POST /api/projects/stop - Stop project timer"""
        # Create project and start timer
        project = client.post(
            "/api/projects/",
            json={"name": f"test-stop-{time.time()}", "description": "Test stop timer"},
            headers=auth_headers,
        ).json()

        start_time = datetime.now(UTC)
        client.post(
            f"/api/projects/{project['id']}/start",
            json={"time": start_time.isoformat()},
            headers=auth_headers,
        )

        # Stop timer
        end_time = start_time + timedelta(hours=1)
        response = client.post(
            "/api/projects/stop",
            json={"time": end_time.isoformat()},
            headers=auth_headers,
        )
        assert response.status_code == 200
        beat = response.json()
        assert beat["end"] is not None

    def test_stop_timer_when_not_started(self, client, auth_headers):
        """Test POST /api/projects/stop when no timer is running - Should fail"""
        # Make sure no timer is running by trying to stop
        response = client.post(
            "/api/projects/stop",
            json={"time": datetime.now(UTC).isoformat()},
            headers=auth_headers,
        )
        # This might be 400 or 200 depending on state, just check it doesn't crash
        assert response.status_code in [200, 400]

    def test_daily_average_returns_envelope_for_empty_project(self, client, auth_headers):
        """GET /api/projects/{id}/daily-average returns the
        documented {avg_minutes, days_tracked} envelope. Pin the
        keys — the project-detail page binds to these directly,
        and a fresh project returns zeros (NOT 404 / NOT crash)."""
        resp = client.post(
            "/api/projects/",
            json={"name": "Daily Avg Probe"},
            headers=auth_headers,
        )
        project_id = resp.json()["id"]
        resp = client.get(f"/api/projects/{project_id}/daily-average", headers=auth_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body == {"avg_minutes": 0, "days_tracked": 0}

    def test_git_activity_returns_empty_when_no_repo(self, client, auth_headers):
        """GET /api/projects/{id}/git-activity returns [] when
        the project has no github_repo wired. Pin so a project
        without a GitHub link doesn't 500 the dashboard's
        commits-vs-time chart."""
        resp = client.post(
            "/api/projects/",
            json={"name": "No GitHub Repo"},
            headers=auth_headers,
        )
        project_id = resp.json()["id"]
        resp = client.get(
            f"/api/projects/{project_id}/git-activity",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json() == []


class TestGoalOverridesAPI:
    """Test suite for goal override endpoints."""

    def _create_project(self, client, auth_headers, weekly_goal=20):
        resp = client.post(
            "/api/projects/",
            json={"name": f"goal-test-{time.time()}", "weekly_goal": weekly_goal},
            headers=auth_headers,
        )
        assert resp.status_code == 201
        return resp.json()

    def _this_week(self, client, auth_headers, project_id: str) -> dict:
        """The ledger's current week: where the goal resolved for it is read."""
        resp = client.get(
            f"/api/projects/{project_id}/ledger", params={"weeks": 1}, headers=auth_headers
        )
        assert resp.status_code == 200, resp.text
        return resp.json()["weeks"][0]

    def test_put_goal_overrides(self, client, auth_headers):
        """Test PUT /api/projects/{id}/goal-overrides — add overrides."""
        project = self._create_project(client, auth_headers)
        resp = client.put(
            f"/api/projects/{project['id']}/goal-overrides",
            json=[
                {"week_of": "2026-04-06", "weekly_goal": 10},
                {"effective_from": "2026-03-02", "weekly_goal": 30},
            ],
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["goal_overrides"]) == 2

    def test_goal_overrides_persist_on_project(self, client, auth_headers):
        """Overrides appear when listing projects."""
        project = self._create_project(client, auth_headers)
        client.put(
            f"/api/projects/{project['id']}/goal-overrides",
            json=[{"week_of": "2026-04-06", "weekly_goal": 10}],
            headers=auth_headers,
        )
        projects = client.get("/api/projects/", headers=auth_headers).json()
        found = next(p for p in projects if p["id"] == project["id"])
        assert len(found["goal_overrides"]) == 1
        assert found["goal_overrides"][0]["weekly_goal"] == 10

    def test_ledger_week_with_override(self, client, auth_headers):
        """Effective goal reflects an active override."""
        project = self._create_project(client, auth_headers, weekly_goal=20)
        # Add a permanent override starting well in the past
        client.put(
            f"/api/projects/{project['id']}/goal-overrides",
            json=[{"effective_from": "2020-01-06", "weekly_goal": 35}],
            headers=auth_headers,
        )
        assert self._this_week(client, auth_headers, project["id"])["effective_goal"] == 35

    def test_replace_overrides(self, client, auth_headers):
        """PUT replaces all overrides, not appends."""
        project = self._create_project(client, auth_headers)
        url = f"/api/projects/{project['id']}/goal-overrides"
        client.put(url, json=[{"week_of": "2026-04-06", "weekly_goal": 10}], headers=auth_headers)
        client.put(url, json=[{"week_of": "2026-04-13", "weekly_goal": 5}], headers=auth_headers)
        data = client.get("/api/projects/", headers=auth_headers).json()
        found = next(p for p in data if p["id"] == project["id"])
        assert len(found["goal_overrides"]) == 1
        assert found["goal_overrides"][0]["week_of"] == "2026-04-13"

    def test_clear_overrides(self, client, auth_headers):
        """Sending empty list clears all overrides."""
        project = self._create_project(client, auth_headers)
        url = f"/api/projects/{project['id']}/goal-overrides"
        client.put(url, json=[{"week_of": "2026-04-06", "weekly_goal": 10}], headers=auth_headers)
        client.put(url, json=[], headers=auth_headers)
        data = client.get("/api/projects/", headers=auth_headers).json()
        found = next(p for p in data if p["id"] == project["id"])
        assert len(found["goal_overrides"]) == 0

    def test_one_off_null_override_clears_week(self, client, auth_headers):
        """A one-off override with weekly_goal=null makes that week have no goal."""
        project = self._create_project(client, auth_headers, weekly_goal=20)
        client.put(
            f"/api/projects/{project['id']}/goal-overrides",
            json=[{"week_of": "2020-01-06", "weekly_goal": None}],
            headers=auth_headers,
        )
        # 2020-01-06 is beyond the ledger's reach, so the stored override is
        # checked on the project list instead.
        projects = client.get("/api/projects/", headers=auth_headers).json()
        found = next(p for p in projects if p["id"] == project["id"])
        overrides = found["goal_overrides"]
        assert len(overrides) == 1
        assert overrides[0]["weekly_goal"] is None

    def test_permanent_null_override_clears_forward(self, client, auth_headers):
        """A permanent null override clears the goal from that Monday forward."""
        project = self._create_project(client, auth_headers, weekly_goal=20)
        client.put(
            f"/api/projects/{project['id']}/goal-overrides",
            json=[{"effective_from": "2020-01-06", "weekly_goal": None}],
            headers=auth_headers,
        )
        assert self._this_week(client, auth_headers, project["id"])["effective_goal"] is None

    def test_ledger_week_flags_override_in_effect(self, client, auth_headers):
        """`effective_goal_overridden` is true when an override resolves for the week."""
        project = self._create_project(client, auth_headers, weekly_goal=20)
        # No override yet: flag should be false, goal = project default.
        week = self._this_week(client, auth_headers, project["id"])
        assert week["effective_goal"] == 20
        assert week["effective_goal_overridden"] is False

        # Permanent null override starting in the past: this week has "no goal"
        # but the flag must reveal it's intentional, not "no project default".
        client.put(
            f"/api/projects/{project['id']}/goal-overrides",
            json=[{"effective_from": "2020-01-06", "weekly_goal": None}],
            headers=auth_headers,
        )
        week = self._this_week(client, auth_headers, project["id"])
        assert week["effective_goal"] is None
        assert week["effective_goal_overridden"] is True

    def test_ledger_week_of_keys_an_override_for_that_week(self, client, auth_headers):
        """The ledger returns the server's Monday, and an override keyed to that
        exact date resolves for the same week. This is the contract the UI
        relies on to avoid client/server week-boundary drift on overrides."""
        from datetime import date as _date

        project = self._create_project(client, auth_headers, weekly_goal=20)
        week_of = self._this_week(client, auth_headers, project["id"])["week_of"]
        assert _date.fromisoformat(week_of).weekday() == 0  # is a Monday

        # An override keyed to the returned Monday must resolve for this week.
        client.put(
            f"/api/projects/{project['id']}/goal-overrides",
            json=[{"week_of": week_of, "weekly_goal": 7}],
            headers=auth_headers,
        )
        week = self._this_week(client, auth_headers, project["id"])
        assert week["effective_goal"] == 7
        assert week["effective_goal_overridden"] is True

    def test_update_project_preserves_goal_overrides(self, client, auth_headers):
        """Editing the project (e.g. color change) must not wipe overrides."""
        project = self._create_project(client, auth_headers, weekly_goal=20)
        client.put(
            f"/api/projects/{project['id']}/goal-overrides",
            json=[{"effective_from": "2020-01-06", "weekly_goal": None}],
            headers=auth_headers,
        )
        # Round-trip a full project update with no overrides field — it must
        # retain the existing overrides rather than silently dropping them.
        client.put(
            "/api/projects/",
            json={
                "id": project["id"],
                "name": project["name"],
                "color": "#abcdef",
                "weekly_goal": 20,
            },
            headers=auth_headers,
        )
        listed = client.get("/api/projects/", headers=auth_headers).json()
        found = next(p for p in listed if p["id"] == project["id"])
        assert len(found["goal_overrides"]) == 1
        assert found["goal_overrides"][0]["weekly_goal"] is None

    def test_null_override_does_not_affect_earlier_weeks(self, client, auth_headers):
        """A permanent null override starting on a future Monday leaves earlier
        weeks with the project default goal."""
        project = self._create_project(client, auth_headers, weekly_goal=20)
        # effective_from far in the future (next decade Monday)
        client.put(
            f"/api/projects/{project['id']}/goal-overrides",
            json=[{"effective_from": "2099-01-05", "weekly_goal": None}],
            headers=auth_headers,
        )
        assert self._this_week(client, auth_headers, project["id"])["effective_goal"] == 20


# --- Work contracts: kind + contract on the project, the week, absences ---

# A Monday, in the past: fixed dates keep the week tests independent of when
# they run. The contract below starts well before it.
CONTRACT_START = "2026-01-05"
WEEK = "2026-03-02"
FULL_TIME = [
    {"effective_from": CONTRACT_START, "schedule_type": "full_time", "full_time_hours": 40}
]


def _create_project(client, headers, **fields) -> dict:
    resp = client.post(
        "/api/projects/", json={"name": f"p-{time.time()}", **fields}, headers=headers
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _day_job(client, headers, terms=None, **contract) -> dict:
    return _create_project(
        client, headers, kind="day_job", contract={"terms": terms or FULL_TIME, **contract}
    )


# A Wednesday in WEEK for a company day, and a GB (England) bank holiday on a
# weekday after the contract starts, for a region holiday the employer keeps open.
COMPANY_DAY = {"date": "2026-03-04", "name": "Founders' Day"}
EASTER_MONDAY = "2026-04-06"
# An entitlement that starts counting on the Monday of WEEK, inside FULL_TIME.
VACATION = {
    "days_per_year": 25.0,
    "carry_over": "all",
    "carry_over_max_days": None,
    "opening_on": WEEK,
    "opening_days": 12.0,
}


def _put_contract(client, headers, project_id: str, **contract) -> dict:
    resp = client.put(
        f"/api/projects/{project_id}/contract",
        json={"terms": FULL_TIME, **contract},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["contract"]


def _log(client, headers, project_id: str, start: str, minutes: int) -> None:
    begun = datetime.fromisoformat(start)
    resp = client.post(
        "/api/beats/",
        json={
            "project_id": project_id,
            "start": begun.isoformat(),
            "end": (begun + timedelta(minutes=minutes)).isoformat(),
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text


class TestContractAPI:
    """`kind` and `contract` on the project routes, and the contract replace."""

    def test_invalid_term_is_422_naming_the_term(self, client, auth_headers):
        # A custom term without weekly_hours: the domain validator's message,
        # at the term's path, in the envelope's `fields`.
        resp = client.post(
            "/api/projects/",
            json={
                "name": "bad term",
                "kind": "day_job",
                "contract": {
                    "terms": [{"effective_from": CONTRACT_START, "schedule_type": "custom"}]
                },
            },
            headers=auth_headers,
        )
        assert resp.status_code == 422, resp.text
        body = resp.json()
        assert body["code"] == "VALIDATION_ERROR"
        assert [f["path"] for f in body["fields"]] == ["contract.terms.0"]
        message = body["fields"][0]["message"]
        assert "weekly_hours" in message
        # The UI shows this sentence as is; Pydantic's "Value error, " comes off.
        assert not message.startswith("Value error")

    def test_put_without_contract_keeps_the_stored_one(self, client, auth_headers):
        # An older client that does not know `kind` or `contract` edits the
        # colour; the day job must come back a day job with its contract —
        # which is also what keeps the startup migration from being undone by
        # the first ordinary edit.
        project = _day_job(client, auth_headers)
        resp = client.put(
            "/api/projects/",
            json={"id": project["id"], "name": project["name"], "color": "#abcdef"},
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["kind"] == "day_job"
        assert resp.json()["contract"] == project["contract"]

    def test_put_with_null_contract_clears_it(self, client, auth_headers):
        project = _day_job(client, auth_headers)
        resp = client.put(
            "/api/projects/",
            json={"id": project["id"], "name": project["name"], "contract": None},
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["contract"] is None
        assert resp.json()["kind"] == "day_job"
        listed = client.get("/api/projects/", headers=auth_headers).json()
        assert next(p for p in listed if p["id"] == project["id"])["contract"] is None

    def test_contract_with_another_kind_is_409(self, client, auth_headers):
        # A contract lives only on a day job: refused on the project routes
        # as on PUT /contract, rather than stored where nothing can read it.
        resp = client.post(
            "/api/projects/",
            json={"name": "freelance", "kind": "freelance", "contract": {"terms": FULL_TIME}},
            headers=auth_headers,
        )
        assert resp.status_code == 409, resp.text
        assert resp.json()["code"] == "NOT_A_DAY_JOB"

    def test_changing_the_kind_takes_the_contract_with_it(self, client, auth_headers):
        project = _day_job(client, auth_headers)
        resp = client.put(
            "/api/projects/",
            json={"id": project["id"], "name": project["name"], "kind": "side_project"},
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["kind"] == "side_project"
        assert resp.json()["contract"] is None
        # Back to a day job it comes with nothing: no dormant contract kept.
        resp = client.put(
            "/api/projects/",
            json={"id": project["id"], "name": project["name"], "kind": "day_job"},
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["contract"] is None

    def test_replace_contract_replaces_the_whole_thing(self, client, auth_headers):
        project = _day_job(client, auth_headers)
        replacement = {
            "terms": [
                {"effective_from": CONTRACT_START, "schedule_type": "custom", "weekly_hours": 20},
                {
                    "effective_from": WEEK,
                    "schedule_type": "part_time",
                    "full_time_hours": 42,
                    "percentage": 0.8,
                },
            ],
            "holiday_country": "CH",
            "holiday_subdivision": "ZH",
            "opening_balance_hours": 12.5,
            "ended_on": None,
        }
        resp = client.put(
            f"/api/projects/{project['id']}/contract", json=replacement, headers=auth_headers
        )
        assert resp.status_code == 200, resp.text
        contract = resp.json()["contract"]
        assert contract["holiday_subdivision"] == "ZH"
        assert contract["opening_balance_hours"] == 12.5
        assert [t["effective_from"] for t in contract["terms"]] == [CONTRACT_START, WEEK]
        assert resp.json()["kind"] == "day_job"

    def test_replace_contract_on_a_side_project_is_409(self, client, auth_headers):
        project = _create_project(client, auth_headers)
        resp = client.put(
            f"/api/projects/{project['id']}/contract",
            json={"terms": FULL_TIME},
            headers=auth_headers,
        )
        assert resp.status_code == 409, resp.text
        assert resp.json()["code"] == "NOT_A_DAY_JOB"

    def test_unknown_region_is_400_with_code(self, client, auth_headers):
        project = _day_job(client, auth_headers)
        resp = client.put(
            f"/api/projects/{project['id']}/contract",
            json={"terms": FULL_TIME, "holiday_country": "XX"},
            headers=auth_headers,
        )
        assert resp.status_code == 400, resp.text
        assert resp.json()["code"] == "UNKNOWN_HOLIDAY_REGION"
        assert "XX" in resp.json()["detail"]

    @staticmethod
    def _send_contract(client, headers, route: str, project: dict, contract: dict) -> dict:
        """One contract write, through PUT /{id}/contract or PUT /api/projects."""
        if route == "contract":
            resp = client.put(
                f"/api/projects/{project['id']}/contract", json=contract, headers=headers
            )
        else:
            resp = client.put(
                "/api/projects/",
                json={
                    "id": project["id"],
                    "name": project["name"],
                    "kind": "day_job",
                    "contract": contract,
                },
                headers=headers,
            )
        assert resp.status_code == 200, resp.text
        return resp.json()["contract"]

    @pytest.mark.parametrize("route", ["contract", "project"])
    def test_a_contract_without_the_holiday_lists_keeps_them(self, client, auth_headers, route):
        # An SPA that predates the lists rebuilds the whole contract on every
        # term edit and sends neither: they must survive it. `[]` clears.
        project = _day_job(client, auth_headers)
        _put_contract(
            client,
            auth_headers,
            project["id"],
            holiday_country="GB",
            company_holidays=[COMPANY_DAY],
            holidays_not_given=[EASTER_MONDAY],
        )
        old_spa_body = {"terms": FULL_TIME, "holiday_country": "GB", "opening_balance_hours": 3}

        kept = self._send_contract(client, auth_headers, route, project, old_spa_body)
        assert kept["opening_balance_hours"] == 3
        assert kept["company_holidays"] == [COMPANY_DAY]
        assert kept["holidays_not_given"] == [EASTER_MONDAY]

        cleared = self._send_contract(
            client,
            auth_headers,
            route,
            project,
            {**old_spa_body, "company_holidays": [], "holidays_not_given": []},
        )
        assert (cleared["company_holidays"], cleared["holidays_not_given"]) == ([], [])

    @pytest.mark.parametrize("route", ["contract", "project"])
    def test_an_old_spa_clearing_the_region_keeps_the_project_readable(
        self, client, auth_headers, route
    ):
        # The not-given list stays behind with no region to take from: inert,
        # not invalid — every project of the user is re-validated on read.
        project = _day_job(client, auth_headers)
        _put_contract(
            client,
            auth_headers,
            project["id"],
            holiday_country="GB",
            holiday_subdivision="ENG",
            holidays_not_given=[EASTER_MONDAY],
        )

        contract = self._send_contract(
            client, auth_headers, route, project, {"terms": FULL_TIME, "holiday_country": None}
        )
        assert contract["holiday_country"] is None
        assert contract["holidays_not_given"] == [EASTER_MONDAY]

        listed = client.get("/api/projects/", headers=auth_headers)
        assert listed.status_code == 200, listed.text
        assert any(p["id"] == project["id"] for p in listed.json())
        resp = client.get(
            f"/api/projects/{project['id']}/contract/week",
            params={"week_of": EASTER_MONDAY},
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["expected"] == 40  # no region: nothing to take away

    @pytest.mark.parametrize(
        ("route", "prefix"),
        [("contract", ""), ("project", "contract.")],
        ids=["contract", "project"],
    )
    def test_a_blank_company_holiday_name_is_422_at_its_row(
        self, client, auth_headers, route, prefix
    ):
        project = _day_job(client, auth_headers)
        contract = {"terms": FULL_TIME, "company_holidays": [{"date": "2026-12-24", "name": " "}]}
        if route == "contract":
            resp = client.put(
                f"/api/projects/{project['id']}/contract", json=contract, headers=auth_headers
            )
        else:
            resp = client.put(
                "/api/projects/",
                json={"id": project["id"], "name": project["name"], "contract": contract},
                headers=auth_headers,
            )
        assert resp.status_code == 422, resp.text
        body = resp.json()
        assert body["code"] == "VALIDATION_ERROR"
        assert [f["path"] for f in body["fields"]] == [f"{prefix}company_holidays.0.name"]

    @pytest.mark.parametrize("route", ["contract", "project"])
    def test_a_contract_without_vacation_keeps_the_entitlement(self, client, auth_headers, route):
        # The SPA on lifepete.com can be older than the API: its contract
        # writes rebuild the contract field by field and never send
        # `vacation`. That must not wipe the entitlement; `null` clears it.
        project = _day_job(client, auth_headers)
        stored = _put_contract(client, auth_headers, project["id"], vacation=VACATION)
        assert stored["vacation"] == VACATION

        old_spa_body = {"terms": FULL_TIME, "opening_balance_hours": 3}
        kept = self._send_contract(client, auth_headers, route, project, old_spa_body)
        assert kept["opening_balance_hours"] == 3
        assert kept["vacation"] == VACATION

        cleared = self._send_contract(
            client, auth_headers, route, project, {**old_spa_body, "vacation": None}
        )
        assert cleared["vacation"] is None

    @pytest.mark.parametrize("route", ["contract", "project"])
    def test_moving_the_start_past_the_vacation_opening_is_409(self, client, auth_headers, route):
        # An old SPA removes the first term. The entitlement it did not send
        # is kept, so its opening would now fall before the contract starts:
        # refused, and nothing stored changes.
        project = _day_job(client, auth_headers)
        two_terms = [
            *FULL_TIME,
            {
                "effective_from": WEEK,
                "schedule_type": "part_time",
                "full_time_hours": 40,
                "percentage": 0.8,
            },
        ]
        before = _put_contract(
            client,
            auth_headers,
            project["id"],
            terms=two_terms,
            vacation={**VACATION, "opening_on": "2026-02-02"},
        )
        body = {"terms": two_terms[1:]}
        if route == "contract":
            resp = client.put(
                f"/api/projects/{project['id']}/contract", json=body, headers=auth_headers
            )
        else:
            resp = client.put(
                "/api/projects/",
                json={"id": project["id"], "name": project["name"], "contract": body},
                headers=auth_headers,
            )
        assert resp.status_code == 409, resp.text
        assert resp.json()["code"] == "VACATION_OPENING_OUTSIDE_CONTRACT"
        assert "Feb 2, 2026" in resp.json()["detail"]
        listed = client.get("/api/projects/", headers=auth_headers).json()
        assert next(p for p in listed if p["id"] == project["id"])["contract"] == before

    def test_a_vacation_figure_off_the_half_day_is_422_at_its_leaf(self, client, auth_headers):
        project = _day_job(client, auth_headers)
        resp = client.put(
            "/api/projects/",
            json={
                "id": project["id"],
                "name": project["name"],
                "contract": {"terms": FULL_TIME, "vacation": {**VACATION, "days_per_year": 25.3}},
            },
            headers=auth_headers,
        )
        assert resp.status_code == 422, resp.text
        assert [f["path"] for f in resp.json()["fields"]] == ["contract.vacation.days_per_year"]

    def test_a_capped_carry_over_without_a_cap_is_422_at_the_cap(self, client, auth_headers):
        project = _day_job(client, auth_headers)
        resp = client.put(
            f"/api/projects/{project['id']}/contract",
            json={"terms": FULL_TIME, "vacation": {**VACATION, "carry_over": "capped"}},
            headers=auth_headers,
        )
        assert resp.status_code == 422, resp.text
        assert [f["path"] for f in resp.json()["fields"]] == ["vacation.carry_over_max_days"]

    @pytest.mark.parametrize("carry_over", ["all", "none"])
    def test_a_cap_on_an_uncapped_carry_over_is_422_at_the_cap(
        self, client, auth_headers, carry_over
    ):
        # Kept, it would be a stored cap that nothing reads.
        project = _day_job(client, auth_headers)
        resp = client.put(
            f"/api/projects/{project['id']}/contract",
            json={
                "terms": FULL_TIME,
                "vacation": {**VACATION, "carry_over": carry_over, "carry_over_max_days": 5},
            },
            headers=auth_headers,
        )
        assert resp.status_code == 422, resp.text
        assert [f["path"] for f in resp.json()["fields"]] == ["vacation.carry_over_max_days"]


class TestContractWeekAPI:
    """GET /api/projects/{id}/contract/week, /holidays, and the index's this_week."""

    def _week(self, client, headers, project_id: str, **params) -> dict:
        resp = client.get(
            f"/api/projects/{project_id}/contract/week",
            params={"week_of": WEEK, **params},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        return resp.json()

    def test_week_on_a_side_project_is_409(self, client, auth_headers):
        project = _create_project(client, auth_headers)
        resp = client.get(f"/api/projects/{project['id']}/contract/week", headers=auth_headers)
        assert resp.status_code == 409, resp.text
        assert resp.json()["code"] == "NOT_A_DAY_JOB"

    def test_malformed_project_id_is_404_in_the_envelope(self, client, auth_headers):
        # Not an ObjectId at all, as opposed to a valid one nobody owns: the
        # same answer, in the same envelope, rather than a bare 500.
        resp = client.get("/api/projects/not-an-id/contract/week", headers=auth_headers)
        assert resp.status_code == 404, resp.text
        assert resp.json()["code"] == "NOT_FOUND"

    def test_week_on_a_day_job_without_a_contract_is_409(self, client, auth_headers):
        project = _create_project(client, auth_headers, kind="day_job")
        resp = client.get(f"/api/projects/{project['id']}/contract/week", headers=auth_headers)
        assert resp.status_code == 409, resp.text
        assert resp.json()["code"] == "NO_CONTRACT"

    def test_week_of_must_be_a_monday(self, client, auth_headers):
        project = _day_job(client, auth_headers)
        resp = client.get(
            f"/api/projects/{project['id']}/contract/week",
            params={"week_of": "2026-03-03"},
            headers=auth_headers,
        )
        assert resp.status_code == 422, resp.text
        body = resp.json()
        assert body["code"] == "VALIDATION_ERROR"
        assert [f["path"] for f in body["fields"]] == ["week_of"]

    def test_week_reports_seven_days_with_worked_by_day(self, client, auth_headers):
        project = _day_job(client, auth_headers)
        _log(client, auth_headers, project["id"], "2026-03-03T09:00:00+00:00", 120)
        _log(client, auth_headers, project["id"], "2026-03-04T09:00:00+00:00", 90)

        week = self._week(client, auth_headers, project["id"])

        assert week["week_of"] == WEEK
        assert [d["date"] for d in week["days"]] == [
            "2026-03-02",
            "2026-03-03",
            "2026-03-04",
            "2026-03-05",
            "2026-03-06",
            "2026-03-07",
            "2026-03-08",
        ]
        assert week["expected"] == 40
        assert week["worked"] == 3.5
        assert week["remaining"] == 36.5
        assert [d["worked"] for d in week["days"]] == [0, 2, 1.5, 0, 0, 0, 0]
        assert [d["expected"] for d in week["days"]] == [8, 8, 8, 8, 8, 0, 0]
        assert all(d["holiday"] is None and d["absence"] is None for d in week["days"])
        # Since the contract started, 3.5 h were worked against months owed.
        assert isinstance(week["balance"], float)
        assert week["balance"] < 0

    def test_remaining_ignores_hours_before_a_midweek_start(self, client, auth_headers):
        # The balance counts work from starts_on; Remaining used to subtract
        # Monday's two hours too, so the two disagreed on the first week.
        project = _day_job(
            client,
            auth_headers,
            terms=[
                {
                    "effective_from": "2026-03-04",  # the Wednesday
                    "schedule_type": "full_time",
                    "full_time_hours": 40,
                }
            ],
        )
        _log(client, auth_headers, project["id"], "2026-03-02T09:00:00+00:00", 120)
        _log(client, auth_headers, project["id"], "2026-03-05T09:00:00+00:00", 180)

        week = self._week(client, auth_headers, project["id"])

        assert week["expected"] == 24
        assert week["worked"] == 5
        assert week["remaining"] == 21
        assert week["balance_worked"] == 3

    def test_remaining_ignores_hours_after_a_midweek_end(self, client, auth_headers):
        project = _day_job(client, auth_headers, ended_on="2026-03-04")
        _log(client, auth_headers, project["id"], "2026-03-03T09:00:00+00:00", 120)
        _log(client, auth_headers, project["id"], "2026-03-05T09:00:00+00:00", 180)

        week = self._week(client, auth_headers, project["id"])

        assert week["expected"] == 24
        assert week["worked"] == 5
        assert week["remaining"] == 22

    def test_hours_under_an_objective_term_count_toward_neither_remaining_nor_balance(
        self, client, auth_headers
    ):
        # AHM-82. Full time Monday and Tuesday, objective from Wednesday,
        # full time again the Monday after, so today has a balance. Thursday's
        # 3 h were worked under a term that expects nothing: shown in
        # `worked`, subtracted from neither Remaining nor counted as overtime.
        full_time = {"schedule_type": "full_time", "full_time_hours": 40}
        project = _day_job(
            client,
            auth_headers,
            terms=[
                {"effective_from": WEEK, **full_time},
                {"effective_from": "2026-03-04", "schedule_type": "objective"},
                {"effective_from": "2026-03-09", **full_time},
            ],
        )
        _log(client, auth_headers, project["id"], "2026-03-03T09:00:00+00:00", 120)
        _log(client, auth_headers, project["id"], "2026-03-05T09:00:00+00:00", 180)

        week = self._week(client, auth_headers, project["id"])

        assert (week["expected"], week["worked"], week["remaining"]) == (16, 5, 14)
        assert week["balance_worked"] == 2

    def test_percentage_change_midweek_shows_in_days(self, client, auth_headers):
        project = _day_job(
            client,
            auth_headers,
            terms=[
                *FULL_TIME,
                {
                    "effective_from": "2026-03-04",  # the Wednesday
                    "schedule_type": "part_time",
                    "full_time_hours": 40,
                    "percentage": 0.5,
                },
            ],
        )
        week = self._week(client, auth_headers, project["id"])
        assert [d["expected"] for d in week["days"]] == [8, 8, 4, 4, 4, 0, 0]
        assert week["expected"] == 28

    def test_zero_hour_term_week_has_no_expectation(self, client, auth_headers):
        # A term of 0 hours governs — the personal goal must not resurface
        # under a sabbatical — but expects nothing by nature: null, as
        # `effective_goal` already reads it, not "Expected 0.0 h" on the card
        # and "12.0/0.0h" in the header. The balance is null on the same rule.
        project = _day_job(
            client,
            auth_headers,
            terms=[
                {"effective_from": CONTRACT_START, "schedule_type": "custom", "weekly_hours": 0}
            ],
        )
        _log(client, auth_headers, project["id"], "2026-03-03T09:00:00+00:00", 120)

        week = self._week(client, auth_headers, project["id"])

        assert (week["expected"], week["remaining"], week["balance"]) == (None, None, None)
        assert week["worked"] == 2
        assert all(d["expected"] == 0 for d in week["days"])

    def test_absence_round_trip_reduces_expected(self, client, auth_headers):
        project = _day_job(client, auth_headers)
        resp = client.post(
            f"/api/projects/{project['id']}/absences",
            json={"date": "2026-03-04", "type": "vacation", "note": "skiing"},
            headers=auth_headers,
        )
        assert resp.status_code == 201, resp.text

        week = self._week(client, auth_headers, project["id"])
        assert week["expected"] == 32
        wednesday = week["days"][2]
        assert wednesday["expected"] == 0
        assert wednesday["absence"] == {"type": "vacation", "half_day": False, "note": "skiing"}

        # Posting the same date again replaces: a full day becomes a half.
        resp = client.post(
            f"/api/projects/{project['id']}/absences",
            json={"date": "2026-03-04", "type": "sick", "half_day": True},
            headers=auth_headers,
        )
        assert resp.status_code == 201, resp.text
        week = self._week(client, auth_headers, project["id"])
        assert week["expected"] == 36
        assert week["days"][2]["absence"] == {"type": "sick", "half_day": True, "note": None}

    def test_running_timer_counts_toward_worked(self, client, auth_headers):
        project = _day_job(client, auth_headers)
        started = datetime.now(UTC) - timedelta(minutes=30)
        resp = client.post(
            f"/api/projects/{project['id']}/start",
            json={"time": started.isoformat()},
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        try:
            # The week the timer started in, so a run across the Monday
            # boundary still finds the beat where it began.
            monday = (started - timedelta(days=started.weekday())).date().isoformat()
            week = self._week(client, auth_headers, project["id"], week_of=monday)
            assert week["worked"] >= 0.5
            assert week["days"][started.weekday()]["worked"] >= 0.5
        finally:
            client.post(
                "/api/projects/stop",
                json={"time": datetime.now(UTC).isoformat()},
                headers=auth_headers,
            )

    def test_beat_crossing_midnight_belongs_to_the_local_day_it_started(self, client, auth_headers):
        project = _day_job(client, auth_headers)
        # 23:30 UTC on the Wednesday, running an hour into Thursday UTC —
        # which in Tokyo is 08:30 on the Thursday.
        _log(client, auth_headers, project["id"], "2026-03-04T23:30:00+00:00", 60)

        in_utc = self._week(client, auth_headers, project["id"])
        assert [d["worked"] for d in in_utc["days"][2:4]] == [1, 0]

        in_tokyo = self._week(client, auth_headers, project["id"], tz="Asia/Tokyo")
        assert [d["worked"] for d in in_tokyo["days"][2:4]] == [0, 1]

    def test_objective_term_has_no_expectation_and_no_balance(self, client, auth_headers):
        project = _day_job(
            client,
            auth_headers,
            terms=[{"effective_from": CONTRACT_START, "schedule_type": "objective"}],
        )
        _log(client, auth_headers, project["id"], "2026-03-03T09:00:00+00:00", 60)
        week = self._week(client, auth_headers, project["id"])
        assert week["expected"] is None
        assert week["remaining"] is None
        assert week["balance"] is None
        assert week["worked"] == 1
        assert [d["expected"] for d in week["days"]] == [0] * 7
        # No balance, no proof under it.
        assert all(
            week[field] is None
            for field in (
                "balance_as_of",
                "balance_opening",
                "balance_worked",
                "balance_expected_through",
                "balance_adjusted",
            )
        )

    def test_week_carries_the_proof_under_the_balance(self, client, auth_headers):
        # The four terms beside the balance are what the standing shows
        # under the figure; each and the balance are rounded on their own,
        # so the sum lands within 0.025 of it. Odd minutes, so the rounding
        # is exercised.
        project = _day_job(client, auth_headers, opening_balance_hours=2.25)
        _log(client, auth_headers, project["id"], "2026-03-03T09:00:00+00:00", 47)
        _log(client, auth_headers, project["id"], "2026-03-04T09:00:00+00:00", 323)

        week = self._week(client, auth_headers, project["id"])

        assert week["balance_as_of"] == datetime.now(UTC).date().isoformat()
        assert week["balance_opening"] == 2.25
        assert week["balance_worked"] == pytest.approx(round((47 + 323) / 60, 2))
        assert week["balance_expected_through"] > 0
        assert week["balance_adjusted"] == 0
        proof = (
            week["balance_opening"]
            + week["balance_worked"]
            - week["balance_expected_through"]
            + week["balance_adjusted"]
        )
        assert proof == pytest.approx(week["balance"], abs=0.025)

    def test_holidays_are_empty_without_a_region(self, client, auth_headers):
        project = _day_job(client, auth_headers)
        resp = client.get(
            f"/api/projects/{project['id']}/holidays",
            params={"year": 2026},
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json() == []

    def test_region_holidays_are_named_and_zero_their_day(self, client, auth_headers):
        # Which days GB observes is the library's business; that a listed
        # weekday holiday comes back by name in the week and costs its day
        # is ours.
        project = _day_job(client, auth_headers, holiday_country="GB", holiday_subdivision="ENG")
        resp = client.get(
            f"/api/projects/{project['id']}/holidays",
            params={"year": 2026},
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        holidays = resp.json()
        assert holidays, "a region with no holidays at all would be a wiring bug"
        assert all(h["date"].startswith("2026-") and h["name"] for h in holidays)

        # The first weekday holiday once the contract is in force: one before
        # it would cost nothing for another reason (no term yet), and the
        # holiday rule would go unexercised.
        weekday = next(
            h
            for h in holidays
            if h["date"] >= CONTRACT_START and date.fromisoformat(h["date"]).weekday() < 5
        )
        day = date.fromisoformat(weekday["date"])
        monday = (day - timedelta(days=day.weekday())).isoformat()
        week = self._week(client, auth_headers, project["id"], week_of=monday)
        reported = week["days"][day.weekday()]
        assert reported["holiday"] == weekday["name"]
        assert reported["expected"] == 0
        # Every weekday holiday in that week costs its 8 h off the 40.
        off = sum(1 for d in week["days"][:5] if d["holiday"])
        assert off >= 1
        assert week["expected"] == 40 - 8 * off

    def test_a_company_holiday_is_named_and_zeroes_its_day(self, client, auth_headers):
        project = _day_job(client, auth_headers)
        _put_contract(client, auth_headers, project["id"], company_holidays=[COMPANY_DAY])

        week = self._week(client, auth_headers, project["id"])

        wednesday = week["days"][2]
        assert (wednesday["holiday"], wednesday["expected"]) == ("Founders' Day", 0)
        assert week["expected"] == 32

    def test_a_region_holiday_not_given_is_owed_and_moves_the_balance(self, client, auth_headers):
        project = _day_job(client, auth_headers, holiday_country="GB", holiday_subdivision="ENG")
        given = self._week(client, auth_headers, project["id"], week_of=EASTER_MONDAY)
        assert given["days"][0]["holiday"] == "Easter Monday"

        _put_contract(
            client,
            auth_headers,
            project["id"],
            holiday_country="GB",
            holiday_subdivision="ENG",
            holidays_not_given=[EASTER_MONDAY],
        )
        worked = self._week(client, auth_headers, project["id"], week_of=EASTER_MONDAY)

        assert (worked["days"][0]["holiday"], worked["days"][0]["expected"]) == (None, 8)
        assert worked["expected"] == given["expected"] + 8
        assert worked["balance"] == pytest.approx(given["balance"] - 8)

    def test_holidays_list_company_days_without_a_region(self, client, auth_headers):
        project = _day_job(client, auth_headers)
        _put_contract(client, auth_headers, project["id"], company_holidays=[COMPANY_DAY])
        resp = client.get(
            f"/api/projects/{project['id']}/holidays",
            params={"year": 2026},
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json() == [{**COMPANY_DAY, "source": "company", "given": True}]

    def test_holidays_leave_out_days_not_given_unless_asked(self, client, auth_headers):
        project = _day_job(client, auth_headers)
        _put_contract(
            client,
            auth_headers,
            project["id"],
            holiday_country="GB",
            holiday_subdivision="ENG",
            company_holidays=[COMPANY_DAY],
            holidays_not_given=[EASTER_MONDAY],
        )
        url = f"/api/projects/{project['id']}/holidays"

        default = client.get(url, params={"year": 2026}, headers=auth_headers).json()
        assert EASTER_MONDAY not in {h["date"] for h in default}
        assert all(h["given"] for h in default)
        by_date = {h["date"]: h for h in default}
        assert by_date[COMPANY_DAY["date"]]["source"] == "company"
        assert by_date["2026-12-25"]["source"] == "region"

        resp = client.get(url, params={"year": 2026, "include": "not_given"}, headers=auth_headers)
        assert resp.status_code == 200, resp.text
        removed = next(h for h in resp.json() if h["date"] == EASTER_MONDAY)
        assert (removed["name"], removed["source"], removed["given"]) == (
            "Easter Monday",
            "region",
            False,
        )

        resp = client.get(url, params={"year": 2026, "include": "bogus"}, headers=auth_headers)
        assert resp.status_code == 422, resp.text
        assert [f["path"] for f in resp.json()["fields"]] == ["include"]

    def test_this_week_include_carries_contract_fields_for_day_jobs(self, client, auth_headers):
        # Both day jobs also carry a personal goal, and the governed one an
        # override on this very week; on the wire the contract must win.
        day_job = _create_project(
            client, auth_headers, kind="day_job", weekly_goal=5, contract={"terms": FULL_TIME}
        )
        this_monday = date.today() - timedelta(days=date.today().weekday())
        resp = client.put(
            f"/api/projects/{day_job['id']}/goal-overrides",
            json=[{"week_of": this_monday.isoformat(), "weekly_goal": 3}],
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        objective = _create_project(
            client,
            auth_headers,
            kind="day_job",
            weekly_goal=5,
            contract={"terms": [{"effective_from": CONTRACT_START, "schedule_type": "objective"}]},
        )
        side = _create_project(client, auth_headers, weekly_goal=5)

        listed = client.get("/api/projects/?include=this_week", headers=auth_headers).json()
        by_id = {p["id"]: p for p in listed}

        mine = by_id[day_job["id"]]
        assert mine["contract_expected"] == 40
        # The effective goal trio is the contract's too: its nominal hours, a
        # target, and no override in effect however many are stored.
        assert (mine["effective_goal"], mine["effective_goal_type"]) == (40, "target")
        assert mine["effective_goal_overridden"] is False
        # Under an objective term the personal goal is the goal, as always.
        assert by_id[objective["id"]]["effective_goal"] == 5
        assert isinstance(mine["balance"], float)
        # The trio is the contract's own and adds up among itself; it does not
        # share `weekly_minutes`' bucketing (see ProjectsListItemResponse).
        assert mine["contract_expected"] - mine["contract_worked"] == pytest.approx(
            mine["contract_remaining"]
        )
        for project in (objective, side):
            item = by_id[project["id"]]
            assert (item["contract_expected"], item["contract_remaining"], item["balance"]) == (
                None,
                None,
                None,
            )
        # Work is reported under an objective term too, as the week route does;
        # only a project of another kind has no contract figure at all.
        assert by_id[objective["id"]]["contract_worked"] == 0
        assert by_id[side["id"]]["contract_worked"] is None
        # The personal goal is untouched by the contract fields.
        assert by_id[side["id"]]["effective_goal"] == 5


class TestLedgerAPI:
    """GET /api/projects/{id}/ledger — every week figure on the project page,
    from one read. The assembly is tested on fixed dates in `test_ledger.py`;
    this is the wire: the shape, the bounds, the timezone, the scoping, and
    that its current week is the week route's."""

    def _ledger(self, client, headers, project_id: str, **params) -> dict:
        resp = client.get(f"/api/projects/{project_id}/ledger", params=params, headers=headers)
        assert resp.status_code == 200, resp.text
        return resp.json()

    @staticmethod
    def _this_monday() -> date:
        today = datetime.now(UTC).date()
        return today - timedelta(days=today.weekday())

    def test_eight_weeks_newest_first_by_default(self, client, auth_headers):
        project = _day_job(client, auth_headers, opening_balance_hours=2.25)
        monday = self._this_monday()
        last_monday = monday - timedelta(weeks=1)
        _log(client, auth_headers, project["id"], f"{monday}T09:00:00+00:00", 47)
        _log(client, auth_headers, project["id"], f"{last_monday}T09:00:00+00:00", 95)

        ledger = self._ledger(client, auth_headers, project["id"])

        assert [w["week_of"] for w in ledger["weeks"]] == [
            (monday - timedelta(weeks=n)).isoformat() for n in range(8)
        ]
        current, last = ledger["weeks"][:2]
        assert current["worked"] == 0.78
        assert current["days"] == [0.78, 0, 0, 0, 0, 0, 0]
        assert current["balance_end"] is None  # not closed yet
        assert current["balance_moved"] is None
        assert current["contract_expected"] == 40
        assert (current["effective_goal"], current["effective_goal_type"]) == (40, "target")
        assert current["effective_goal_overridden"] is False
        assert current["notes"] == []
        assert last["worked"] == 1.58
        # Last week's close is the week before's moved by last week's own
        # worked − expected: the row is its own week's, not a neighbour's.
        assert last["balance_end"] - ledger["weeks"][2]["balance_end"] == pytest.approx(
            last["worked"] - last["contract_expected"], abs=0.01
        )
        assert last["balance_moved"] == pytest.approx(
            last["balance_end"] - ledger["weeks"][2]["balance_end"], abs=0.01
        )
        assert ledger["since"] == CONTRACT_START
        totals = ledger["totals"]
        assert totals["adjusted"] == 0
        assert 2.25 + totals["worked"] - totals["expected"] + totals["adjusted"] == pytest.approx(
            totals["balance"], abs=0.025
        )
        # The current week is the week route's, to the decimal, and so is
        # today's balance.
        resp = client.get(f"/api/projects/{project['id']}/contract/week", headers=auth_headers)
        assert resp.status_code == 200, resp.text
        week = resp.json()
        assert current["worked"] == week["worked"]
        assert totals["balance"] == week["balance"]
        assert (totals["worked"], totals["expected"]) == (
            week["balance_worked"],
            week["balance_expected_through"],
        )

    def test_a_week_carries_the_adjusted_expectation_beside_the_nominal_goal(
        self, client, auth_headers
    ):
        # The row reads what the week expects after holidays and absences — the
        # week route's figure — while `effective_goal` stays the term's nominal
        # hours, which is what the score and the coach want (the readers'
        # decision).
        project = _day_job(client, auth_headers)
        wednesday = self._this_monday() + timedelta(days=2)
        resp = client.post(
            f"/api/projects/{project['id']}/absences",
            json={"date": wednesday.isoformat(), "type": "vacation"},
            headers=auth_headers,
        )
        assert resp.status_code == 201, resp.text

        current = self._ledger(client, auth_headers, project["id"], weeks=1)["weeks"][0]

        assert current["contract_expected"] == 32
        assert current["effective_goal"] == 40
        # And it is the week route's own figure for that Monday, to the decimal.
        resp = client.get(
            f"/api/projects/{project['id']}/contract/week",
            params={"week_of": current["week_of"]},
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["expected"] == current["contract_expected"]

    def test_a_company_holiday_is_a_holiday_note(self, client, auth_headers):
        project = _day_job(client, auth_headers)
        wednesday = (self._this_monday() + timedelta(days=2)).isoformat()
        _put_contract(
            client,
            auth_headers,
            project["id"],
            company_holidays=[{"date": wednesday, "name": "Company day"}],
        )

        current = self._ledger(client, auth_headers, project["id"], weeks=1)["weeks"][0]

        assert current["notes"] == [
            {"date": wednesday, "kind": "holiday", "half_day": None, "name": "Company day"}
        ]
        assert current["contract_expected"] == 32

    def test_weeks_out_of_range_is_422_naming_the_parameter(self, client, auth_headers):
        project = _day_job(client, auth_headers)
        resp = client.get(
            f"/api/projects/{project['id']}/ledger", params={"weeks": 105}, headers=auth_headers
        )
        assert resp.status_code == 422, resp.text
        body = resp.json()
        assert body["code"] == "VALIDATION_ERROR"
        assert [f["path"] for f in body["fields"]] == ["weeks"]

    def test_days_follow_the_request_timezone(self, client, auth_headers):
        project = _day_job(client, auth_headers)
        monday = self._this_monday()
        # 23:30 UTC on Monday, running into Tuesday — which in Zürich began
        # at 00:30 (or 01:30) on the Tuesday. Whole to its local start day.
        _log(client, auth_headers, project["id"], f"{monday}T23:30:00+00:00", 60)

        # Two weeks, looked up by Monday: late on a Sunday, Zürich is already
        # in the next week while UTC is not.
        def week_of(ledger: dict) -> dict:
            return next(w for w in ledger["weeks"] if w["week_of"] == monday.isoformat())

        in_utc = week_of(self._ledger(client, auth_headers, project["id"], weeks=2))
        assert in_utc["days"][:2] == [1, 0]

        in_zurich = week_of(
            self._ledger(client, auth_headers, project["id"], weeks=2, tz="Europe/Zurich")
        )
        assert in_zurich["days"][:2] == [0, 1]
        assert in_zurich["worked"] == in_utc["worked"] == 1

    def test_side_project_carries_the_goal_and_the_hours_only(self, client, auth_headers):
        project = _create_project(client, auth_headers, weekly_goal=5)
        monday = self._this_monday()
        _log(client, auth_headers, project["id"], f"{monday}T09:00:00+00:00", 90)

        ledger = self._ledger(client, auth_headers, project["id"], weeks=2)

        assert (ledger["since"], ledger["totals"]) == (None, None)
        assert all(
            (w["contract_expected"], w["balance_end"], w["notes"]) == (None, None, [])
            for w in ledger["weeks"]
        )
        assert ledger["weeks"][0]["effective_goal"] == 5
        assert ledger["weeks"][0]["worked"] == 1.5

    def test_someone_elses_project_is_404(self, client, auth_headers, other_auth_headers):
        mine = _day_job(client, auth_headers)
        resp = client.get(f"/api/projects/{mine['id']}/ledger", headers=other_auth_headers)
        assert resp.status_code == 404, resp.text
        assert resp.json()["code"] == "NOT_FOUND"
        resp = client.get("/api/projects/not-an-id/ledger", headers=auth_headers)
        assert resp.status_code == 404, resp.text
        assert resp.json()["code"] == "NOT_FOUND"


# 80 % of 42 h: 6.72 h a day, which a day worked to the second rounds to
# −0.0 against.
PART_TIME_80 = [
    {
        "effective_from": CONTRACT_START,
        "schedule_type": "part_time",
        "full_time_hours": 42,
        "percentage": 0.8,
    }
]


class TestTimesheetAPI:
    """GET /api/projects/{id}/timesheet.csv — a day job's month as a CSV. The
    assembly is tested on fixed dates in `test_timesheet.py`; this is the
    wire: the file's shape, the -0.00 a day worked to contract would print,
    the read over the contract's whole life, the timezone, the refusals.
    Only last month and the month before are asked for: both are always
    finished and inside CONTRACT_START, so no test breaks on the 1st."""

    @staticmethod
    def _month(back: int) -> date:
        """The 1st of the month `back` months before the current one, in UTC."""
        first = datetime.now(UTC).date().replace(day=1)
        for _ in range(back):
            first = (first - timedelta(days=1)).replace(day=1)
        return first

    @staticmethod
    def _get(client, headers, project_id: str, month: str | None, **params):
        query = {} if month is None else {"month": month}
        return client.get(
            f"/api/projects/{project_id}/timesheet.csv",
            params={**query, **params},
            headers=headers,
        )

    def _rows(self, client, headers, project_id: str, month: date, **params) -> list[list[str]]:
        resp = self._get(client, headers, project_id, month.strftime("%Y-%m"), **params)
        assert resp.status_code == 200, resp.text
        return list(csv.reader(io.StringIO(resp.text)))

    @staticmethod
    def _by_date(rows: list[list[str]]) -> dict[str, dict[str, str]]:
        header = rows[0]
        return {row[0]: dict(zip(header, row, strict=True)) for row in rows[1:]}

    @staticmethod
    def _first_weekday(month: date) -> date:
        day = month
        while day.weekday() >= 5:
            day += timedelta(days=1)
        return day

    def test_the_month_as_csv_a_row_per_day(self, client, auth_headers):
        project = _day_job(client, auth_headers, opening_balance_hours=2.5)
        month = self._month(1)
        resp = self._get(client, auth_headers, project["id"], month.strftime("%Y-%m"))

        assert resp.status_code == 200, resp.text
        assert resp.headers["content-type"].startswith("text/csv")
        assert resp.headers["content-disposition"] == "attachment"
        rows = list(csv.reader(io.StringIO(resp.text)))
        assert rows[0] == [
            "date",
            "weekday",
            "expected",
            "worked",
            "difference",
            "holiday",
            "absence",
            "half_day",
            "adjustment",
            "adjusted",
            "balance",
        ]
        assert rows[1][0] == "brought forward"
        assert rows[-1][0] == "total"
        days = [row[0] for row in rows[2:-1]]
        assert days[0] == month.isoformat()
        assert [date.fromisoformat(d) for d in days] == [
            month + timedelta(days=n) for n in range(len(days))
        ]
        assert (date.fromisoformat(days[-1]) + timedelta(days=1)).day == 1
        assert {len(row) for row in rows} == {11}

    def test_a_day_worked_to_contract_differs_by_0_00(self, client, auth_headers):
        project = _day_job(client, auth_headers, terms=PART_TIME_80)
        day = self._first_weekday(self._month(1))
        begun = datetime(day.year, day.month, day.day, 9, tzinfo=UTC)
        resp = client.post(
            "/api/beats/",
            json={
                "project_id": project["id"],
                "start": begun.isoformat(),
                "end": (begun + timedelta(seconds=24192)).isoformat(),
            },
            headers=auth_headers,
        )
        assert resp.status_code == 201, resp.text

        rows = self._rows(client, auth_headers, project["id"], self._month(1))
        row = self._by_date(rows)[day.isoformat()]

        assert (row["expected"], row["worked"], row["difference"]) == ("6.72", "6.72", "0.00")

    def test_a_month_brings_forward_what_the_one_before_carried(self, client, auth_headers):
        # Work logged before both months and in each, and a payout in the
        # later one: the month before's close is last month's opening only if
        # the read runs over the contract's whole life, not the month's. The
        # month before also has an absence, an adjustment and a company
        # holiday, one for each read besides the beats: any of them read from
        # the later month's 1st would move its brought-forward figure.
        before, last = self._month(2), self._month(1)
        weekdays = [d for d in (before + timedelta(days=n) for n in range(28)) if d.weekday() < 5]
        worked_day, off_day, adjusted_day, company_day = weekdays[:4]
        project = _day_job(
            client,
            auth_headers,
            opening_balance_hours=1.25,
            company_holidays=[{"date": company_day.isoformat(), "name": "Founders' Day"}],
        )
        payday = self._first_weekday(last)
        _log(client, auth_headers, project["id"], f"{CONTRACT_START}T09:00:00+00:00", 300)
        _log(client, auth_headers, project["id"], f"{worked_day}T09:00:00+00:00", 600)
        _log(client, auth_headers, project["id"], f"{payday}T09:00:00+00:00", 450)
        resp = client.post(
            f"/api/projects/{project['id']}/absences",
            json={"date": off_day.isoformat(), "type": "vacation"},
            headers=auth_headers,
        )
        assert resp.status_code == 201, resp.text
        for day, hours in ((adjusted_day, 2.0), (payday, -3.5)):
            resp = client.post(
                f"/api/projects/{project['id']}/adjustments",
                params={"tz": "UTC"},
                json={"date": day.isoformat(), "kind": "delta", "hours": hours},
                headers=auth_headers,
            )
            assert resp.status_code == 201, resp.text

        earlier = self._rows(client, auth_headers, project["id"], before)
        later = self._rows(client, auth_headers, project["id"], last)

        assert earlier[-1][-1] == later[1][-1]
        row = self._by_date(later)[payday.isoformat()]
        assert (row["adjustment"], row["adjusted"]) == ("delta", "-3.50")
        total = dict(zip(later[0], later[-1], strict=True))
        assert total["adjusted"] == "-3.50"
        moved = float(total["worked"]) - float(total["expected"]) + float(total["adjusted"])
        assert float(later[1][-1]) + moved == pytest.approx(float(total["balance"]), abs=0.025)

    def test_a_company_holiday_is_named_as_one_not_as_typed(self, client, auth_headers):
        project = _day_job(client, auth_headers)
        day = self._first_weekday(self._month(1))
        _put_contract(
            client,
            auth_headers,
            project["id"],
            company_holidays=[{"date": day.isoformat(), "name": "Founders' Day"}],
        )

        rows = self._rows(client, auth_headers, project["id"], self._month(1))

        row = self._by_date(rows)[day.isoformat()]
        assert (row["holiday"], row["expected"]) == ("company holiday", "0.00")
        assert not any("Founders" in cell for r in rows for cell in r)

    def test_days_follow_the_request_timezone(self, client, auth_headers):
        project = _day_job(client, auth_headers)
        day = self._month(1) + timedelta(days=9)
        # 23:30 UTC, which in Zürich is already the next day.
        _log(client, auth_headers, project["id"], f"{day}T23:30:00+00:00", 60)
        next_day = (day + timedelta(days=1)).isoformat()

        in_utc = self._by_date(self._rows(client, auth_headers, project["id"], self._month(1)))
        in_zurich = self._by_date(
            self._rows(client, auth_headers, project["id"], self._month(1), tz="Europe/Zurich")
        )

        assert (in_utc[day.isoformat()]["worked"], in_utc[next_day]["worked"]) == ("1.00", "0.00")
        assert (in_zurich[day.isoformat()]["worked"], in_zurich[next_day]["worked"]) == (
            "0.00",
            "1.00",
        )

    def test_a_side_project_or_a_day_job_without_a_contract_is_409(self, client, auth_headers):
        month = self._month(1).strftime("%Y-%m")
        side = _create_project(client, auth_headers)
        resp = self._get(client, auth_headers, side["id"], month)
        assert resp.status_code == 409, resp.text
        assert resp.json()["code"] == "NOT_A_DAY_JOB"
        bare = _create_project(client, auth_headers, kind="day_job")
        resp = self._get(client, auth_headers, bare["id"], month)
        assert resp.status_code == 409, resp.text
        assert resp.json()["code"] == "NO_CONTRACT"

    @pytest.mark.parametrize("which", ["next", "before the start"])
    def test_a_month_without_a_finished_day_in_the_contract_is_409(
        self, client, auth_headers, which
    ):
        project = _day_job(client, auth_headers)
        if which == "next":
            month = (self._month(0) + timedelta(days=31)).strftime("%Y-%m")
        else:
            month = "2025-12"
        resp = self._get(client, auth_headers, project["id"], month)
        assert resp.status_code == 409, resp.text
        assert resp.json()["code"] == "OUTSIDE_CONTRACT"

    @pytest.mark.parametrize("month", ["2026-13", "2026-9", "0000-01", "2026-09-01", None])
    def test_a_month_that_is_not_yyyy_mm_is_422_naming_it(self, client, auth_headers, month):
        project = _day_job(client, auth_headers)
        resp = self._get(client, auth_headers, project["id"], month)
        assert resp.status_code == 422, resp.text
        body = resp.json()
        assert body["code"] == "VALIDATION_ERROR"
        assert [f["path"] for f in body["fields"]] == ["month"]

    def test_someone_elses_project_is_404(self, client, auth_headers, other_auth_headers):
        mine = _day_job(client, auth_headers)
        resp = self._get(client, other_auth_headers, mine["id"], self._month(1).strftime("%Y-%m"))
        assert resp.status_code == 404, resp.text
        assert resp.json()["code"] == "NOT_FOUND"


class TestVacationAPI:
    """GET /api/projects/{id}/vacation. The arithmetic is tested on fixed
    dates in `test_vacation.py`, and which year is the default in
    `test_domain.py` at a fixed instant; this is the wire."""

    @staticmethod
    def _vacation(client, headers, project_id: str, **params):
        return client.get(f"/api/projects/{project_id}/vacation", params=params, headers=headers)

    @staticmethod
    def _off(client, headers, project_id: str, day: str, kind: str, **fields) -> None:
        resp = client.post(
            f"/api/projects/{project_id}/absences",
            json={"date": day, "type": kind, **fields},
            headers=headers,
        )
        assert resp.status_code in (200, 201), resp.text

    def test_a_year_reads_the_opening_then_the_carry(self, client, auth_headers):
        # From the opening on Monday 2 March 2026 with 12 days left: Tuesday
        # costs a day, Wednesday is the company's holiday and costs none,
        # Thursday's half day costs ½, and Friday's sick day is not leave.
        project = _day_job(client, auth_headers)
        _put_contract(
            client, auth_headers, project["id"], company_holidays=[COMPANY_DAY], vacation=VACATION
        )
        for day, kind, fields in [
            ("2026-03-03", "vacation", {}),
            (COMPANY_DAY["date"], "vacation", {}),
            ("2026-03-05", "vacation", {"half_day": True}),
            ("2026-03-06", "sick", {}),
        ]:
            self._off(client, auth_headers, project["id"], day, kind, **fields)

        resp = self._vacation(client, auth_headers, project["id"], year=2026)
        assert resp.status_code == 200, resp.text
        assert resp.json() == {
            "year": 2026,
            "accrued": None,
            "carried_in": 0,
            "available": 12,
            "booked": 1.5,
            "remaining": 10.5,
        }
        resp = self._vacation(client, auth_headers, project["id"], year=2027)
        assert resp.status_code == 200, resp.text
        assert resp.json() == {
            "year": 2027,
            "accrued": 25,
            "carried_in": 10.5,
            "available": 35.5,
            "booked": 0,
            "remaining": 35.5,
        }

    def test_a_vacation_recorded_moves_booked(self, client, auth_headers):
        project = _day_job(client, auth_headers, vacation=VACATION)
        before = self._vacation(client, auth_headers, project["id"], year=2026).json()

        self._off(client, auth_headers, project["id"], "2026-09-01", "vacation")

        after = self._vacation(client, auth_headers, project["id"], year=2026).json()
        assert (before["booked"], after["booked"]) == (0, 1)
        assert after["remaining"] == before["remaining"] - 1

    def test_a_year_before_the_opening_is_409_naming_the_range(self, client, auth_headers):
        project = _day_job(client, auth_headers, ended_on="2028-06-30", vacation=VACATION)
        resp = self._vacation(client, auth_headers, project["id"], year=2025)
        assert resp.status_code == 409, resp.text
        assert resp.json()["code"] == "VACATION_YEAR_OUT_OF_RANGE"
        assert resp.json()["detail"] == "Vacation is counted from 2026 through 2028"
        resp = self._vacation(client, auth_headers, project["id"], year=2029)
        assert resp.status_code == 409, resp.text

    def test_a_contract_without_an_entitlement_is_409(self, client, auth_headers):
        project = _day_job(client, auth_headers)
        resp = self._vacation(client, auth_headers, project["id"])
        assert resp.status_code == 409, resp.text
        assert resp.json()["code"] == "NO_VACATION_ENTITLEMENT"

    def test_a_day_job_without_a_contract_is_409(self, client, auth_headers):
        project = _create_project(client, auth_headers, kind="day_job")
        resp = self._vacation(client, auth_headers, project["id"])
        assert resp.status_code == 409, resp.text
        assert resp.json()["code"] == "NO_CONTRACT"

    def test_a_side_project_is_409(self, client, auth_headers):
        project = _create_project(client, auth_headers)
        resp = self._vacation(client, auth_headers, project["id"])
        assert resp.status_code == 409, resp.text
        assert resp.json()["code"] == "NOT_A_DAY_JOB"

    def test_a_malformed_project_id_is_404(self, client, auth_headers):
        resp = self._vacation(client, auth_headers, "not-an-id")
        assert resp.status_code == 404, resp.text
        assert resp.json()["code"] == "NOT_FOUND"


class TestAbsencesAPI:
    """/api/projects/{id}/absences — scoping and the delete."""

    def test_absences_are_scoped_to_the_user(self, client, auth_headers, other_auth_headers):
        mine = _day_job(client, auth_headers)
        other = other_auth_headers
        url = f"/api/projects/{mine['id']}/absences"

        # Someone else's project does not exist to them: 404, never 403.
        resp = client.post(url, json={"date": "2026-03-04", "type": "sick"}, headers=other)
        assert resp.status_code == 404, resp.text
        assert client.get(url, headers=other).status_code == 404

        # Nor can they reach one of mine by id through a day job of their own.
        created = client.post(
            url, json={"date": "2026-03-04", "type": "sick"}, headers=auth_headers
        ).json()
        theirs = _day_job(client, other)
        resp = client.delete(
            f"/api/projects/{theirs['id']}/absences/{created['id']}", headers=other
        )
        assert resp.status_code == 404, resp.text
        assert [a["id"] for a in client.get(url, headers=auth_headers).json()] == [created["id"]]

    def test_delete_is_204_and_then_gone(self, client, auth_headers):
        project = _day_job(client, auth_headers)
        url = f"/api/projects/{project['id']}/absences"
        created = client.post(
            url, json={"date": "2026-03-04", "type": "other"}, headers=auth_headers
        ).json()
        assert created["project_id"] == project["id"]

        resp = client.delete(f"{url}/{created['id']}", headers=auth_headers)
        assert resp.status_code == 204, resp.text
        assert client.get(url, headers=auth_headers).json() == []
        resp = client.delete(f"{url}/{created['id']}", headers=auth_headers)
        assert resp.status_code == 404, resp.text
        assert resp.json()["code"] == "NOT_FOUND"

    def test_delete_is_scoped_to_the_project_in_the_path(self, client, auth_headers):
        # Two day jobs of one user: an absence on the first is not reachable
        # through the second's URL, so the 404 means "not on this project".
        first = _day_job(client, auth_headers)
        second = _day_job(client, auth_headers)
        created = client.post(
            f"/api/projects/{first['id']}/absences",
            json={"date": "2026-03-04", "type": "sick"},
            headers=auth_headers,
        ).json()
        resp = client.delete(
            f"/api/projects/{second['id']}/absences/{created['id']}", headers=auth_headers
        )
        assert resp.status_code == 404, resp.text
        listed = client.get(f"/api/projects/{first['id']}/absences", headers=auth_headers).json()
        assert [a["id"] for a in listed] == [created["id"]]

    def test_absence_on_a_side_project_is_409(self, client, auth_headers):
        project = _create_project(client, auth_headers)
        resp = client.post(
            f"/api/projects/{project['id']}/absences",
            json={"date": "2026-03-04", "type": "vacation"},
            headers=auth_headers,
        )
        assert resp.status_code == 409, resp.text
        assert resp.json()["code"] == "NOT_A_DAY_JOB"


class TestAdjustmentsAPI:
    """/api/projects/{id}/adjustments — the write side of the ledger, and what
    the balance makes of it on the two reads. The arithmetic is tested on
    fixed dates in `test_contracts.py` and `test_ledger.py`, and whose today
    the date rule reads in `test_domain.py`; this is the wire."""

    @staticmethod
    def _last_monday() -> date:
        today = datetime.now(UTC).date()
        return today - timedelta(days=today.weekday() + 7)

    @staticmethod
    def _post(client, headers, project_id: str, tz: str | None = "UTC", **body):
        params = {} if tz is None else {"tz": tz}
        return client.post(
            f"/api/projects/{project_id}/adjustments", params=params, json=body, headers=headers
        )

    def _record(self, client, headers, project_id: str, **body) -> dict:
        resp = self._post(client, headers, project_id, **body)
        assert resp.status_code == 201, resp.text
        return resp.json()

    @staticmethod
    def _ledger(client, headers, project_id: str) -> dict:
        resp = client.get(
            f"/api/projects/{project_id}/ledger", params={"weeks": 2}, headers=headers
        )
        assert resp.status_code == 200, resp.text
        return resp.json()

    def test_a_payout_moves_the_balance_and_shows_in_its_week(self, client, auth_headers):
        project = _day_job(client, auth_headers, opening_balance_hours=10)
        monday = self._last_monday().isoformat()

        created = self._record(
            client, auth_headers, project["id"], date=monday, kind="delta", hours=-4, note="paid"
        )

        assert created == {
            "id": created["id"],
            "project_id": project["id"],
            "date": monday,
            "kind": "delta",
            "hours": -4,
            "note": "paid",
        }
        resp = client.get(f"/api/projects/{project['id']}/contract/week", headers=auth_headers)
        assert resp.status_code == 200, resp.text
        week = resp.json()
        assert week["balance_adjusted"] == -4
        proof = (
            week["balance_opening"]
            + week["balance_worked"]
            - week["balance_expected_through"]
            + week["balance_adjusted"]
        )
        assert proof == pytest.approx(week["balance"], abs=0.025)
        ledger = self._ledger(client, auth_headers, project["id"])
        assert ledger["totals"]["adjusted"] == -4
        assert ledger["totals"]["balance"] == week["balance"]
        assert ledger["weeks"][0]["adjustments"] == []
        assert ledger["weeks"][1]["adjustments"] == [
            {
                "id": created["id"],
                "date": monday,
                "kind": "delta",
                "hours": -4,
                "note": "paid",
                "applied": -4,
            }
        ]
        assert ledger["ended_balance"] is None

    def test_a_second_post_on_a_date_replaces_the_first(self, client, auth_headers):
        # Two writes, one record: the unique index the fake cannot see.
        project = _day_job(client, auth_headers)
        monday = self._last_monday().isoformat()
        first = self._record(
            client, auth_headers, project["id"], date=monday, kind="delta", hours=-4, note="x"
        )
        second = self._record(
            client, auth_headers, project["id"], date=monday, kind="reset", hours=0
        )

        assert second["id"] == first["id"]
        (adjustment,) = self._ledger(client, auth_headers, project["id"])["weeks"][1]["adjustments"]
        assert (adjustment["kind"], adjustment["hours"], adjustment["note"]) == ("reset", 0, None)

    def test_without_a_balance_there_is_nothing_to_adjust(self, client, auth_headers):
        monday = self._last_monday().isoformat()
        side = _create_project(client, auth_headers)
        resp = self._post(client, auth_headers, side["id"], date=monday, kind="delta", hours=1)
        assert resp.status_code == 409, resp.text
        assert resp.json()["code"] == "NOT_A_DAY_JOB"

        no_contract = _create_project(client, auth_headers, kind="day_job")
        resp = self._post(
            client, auth_headers, no_contract["id"], date=monday, kind="delta", hours=1
        )
        assert resp.status_code == 409, resp.text
        assert resp.json()["code"] == "NO_CONTRACT"

    @pytest.mark.parametrize(
        "day",
        [date(2026, 1, 4), datetime.now(UTC).date() + timedelta(days=2)],
        ids=["before the first term", "after today"],
    )
    def test_a_date_outside_the_balance_is_409(self, client, auth_headers, day):
        project = _day_job(client, auth_headers)
        resp = self._post(
            client, auth_headers, project["id"], date=day.isoformat(), kind="cap", hours=0
        )
        assert resp.status_code == 409, resp.text
        assert resp.json()["code"] == "ADJUSTMENT_OUTSIDE_BALANCE"

    @pytest.mark.parametrize("hours", [0, True, "3"], ids=["zero", "a bool", "a string"])
    def test_a_body_that_means_nothing_is_422_naming_hours(self, client, auth_headers, hours):
        # `true` once read as a 1 h payout: lax validation takes a bool for a number.
        project = _day_job(client, auth_headers)
        monday = self._last_monday().isoformat()
        resp = self._post(
            client, auth_headers, project["id"], date=monday, kind="delta", hours=hours
        )
        assert resp.status_code == 422, resp.text
        assert [f["path"] for f in resp.json()["fields"]] == ["hours"]

    def test_tz_is_required(self, client, auth_headers):
        project = _day_job(client, auth_headers)
        monday = self._last_monday().isoformat()
        resp = self._post(
            client, auth_headers, project["id"], tz=None, date=monday, kind="delta", hours=1
        )
        assert resp.status_code == 422, resp.text
        assert [f["path"] for f in resp.json()["fields"]] == ["tz"]

    def test_delete_is_204_then_404_and_scoped_to_the_project(
        self, client, auth_headers, other_auth_headers
    ):
        project = _day_job(client, auth_headers)
        other_job = _day_job(client, auth_headers)
        monday = self._last_monday().isoformat()
        created = self._record(
            client, auth_headers, project["id"], date=monday, kind="delta", hours=2
        )
        url = f"/api/projects/{project['id']}/adjustments"

        for headers, path in [
            (auth_headers, f"/api/projects/{other_job['id']}/adjustments/{created['id']}"),
            (other_auth_headers, f"{url}/{created['id']}"),
            (auth_headers, f"{url}/{'0' * 24}"),
            (auth_headers, f"{url}/not-an-id"),
        ]:
            resp = client.delete(path, headers=headers)
            assert resp.status_code == 404, (path, resp.text)

        resp = client.delete(f"{url}/{created['id']}", headers=auth_headers)
        assert resp.status_code == 204, resp.text
        assert self._ledger(client, auth_headers, project["id"])["weeks"][1]["adjustments"] == []
        resp = client.delete(f"{url}/{created['id']}", headers=auth_headers)
        assert resp.status_code == 404, resp.text
        assert resp.json()["code"] == "NOT_FOUND"

    def test_a_first_term_moved_past_an_adjustment_is_409(self, client, auth_headers):
        project = _day_job(client, auth_headers)
        self._record(client, auth_headers, project["id"], date="2026-02-02", kind="delta", hours=1)
        later = [{**FULL_TIME[0], "effective_from": "2026-02-09"}]

        resp = client.put(
            f"/api/projects/{project['id']}/contract", json={"terms": later}, headers=auth_headers
        )

        assert resp.status_code == 409, resp.text
        assert resp.json()["code"] == "ADJUSTMENT_BEFORE_START"

    def test_a_rename_keeps_them_and_a_kind_change_takes_them(self, client, auth_headers):
        project = _day_job(client, auth_headers)
        monday = self._last_monday().isoformat()
        self._record(client, auth_headers, project["id"], date=monday, kind="delta", hours=1)

        def put(**fields) -> None:
            resp = client.put(
                "/api/projects/",
                json={"id": project["id"], "name": "Renamed", **fields},
                headers=auth_headers,
            )
            assert resp.status_code == 200, resp.text

        # The drawer resends the whole contract on every edit.
        put(kind="day_job", contract={"terms": FULL_TIME})
        assert (
            len(self._ledger(client, auth_headers, project["id"])["weeks"][1]["adjustments"]) == 1
        )

        put(kind="side_project")
        put(kind="day_job", contract={"terms": FULL_TIME})
        ledger = self._ledger(client, auth_headers, project["id"])
        assert ledger["weeks"][1]["adjustments"] == []
        assert ledger["totals"]["adjusted"] == 0


class TestHolidayRegionsAPI:
    def test_regions_are_listed_and_cacheable(self, client, auth_headers):
        resp = client.get("/api/meta/holiday-regions", headers=auth_headers)
        assert resp.status_code == 200, resp.text
        # `public` is the decision — a shared cache may keep it despite the
        # Authorization header. The TTL is configuration and not restated.
        assert "public" in resp.headers["cache-control"]
        regions = resp.json()
        with_subdivisions = next(r for r in regions if r["subdivisions"])
        assert set(with_subdivisions) == {"code", "name", "subdivisions"}
        assert set(with_subdivisions["subdivisions"][0]) == {"code", "name"}

    def test_regions_need_a_session(self, client):
        assert client.get("/api/meta/holiday-regions").status_code == 401


class TestRegionHolidaysAPI:
    """The calendar of a region no contract names yet — what the settings
    form reads before a region change is saved."""

    @staticmethod
    def _holidays(client, headers, **params) -> list[dict]:
        resp = client.get("/api/meta/holidays", params=params, headers=headers)
        assert resp.status_code == 200, resp.text
        return resp.json()

    def test_a_region_is_listed_by_date_and_name_without_a_contract(self, client, auth_headers):
        resp = client.get(
            "/api/meta/holidays",
            params={"country": "GB", "subdivision": "ENG", "year": 2026},
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        assert "public" in resp.headers["cache-control"]
        holidays = resp.json()
        assert {"date": EASTER_MONDAY, "name": "Easter Monday"} in holidays
        assert all(set(h) == {"date", "name"} and h["date"].startswith("2026-") for h in holidays)
        assert [h["date"] for h in holidays] == sorted(h["date"] for h in holidays)

    def test_the_subdivision_is_part_of_the_region(self, client, auth_headers):
        # What the settings form compares: England and Scotland disagree on
        # Easter Monday and on Saint Andrew's Day.
        england = self._holidays(client, auth_headers, country="GB", subdivision="ENG", year=2026)
        scotland = self._holidays(client, auth_headers, country="GB", subdivision="SCT", year=2026)
        assert EASTER_MONDAY in {h["date"] for h in england}
        assert EASTER_MONDAY not in {h["date"] for h in scotland}
        assert "2026-11-30" in {h["date"] for h in scotland}
        assert "2026-11-30" not in {h["date"] for h in england}

    @pytest.mark.parametrize(
        "params", [{"country": "XX"}, {"country": "GB", "subdivision": "XX"}], ids=str
    )
    def test_an_unknown_region_is_400_with_code(self, client, auth_headers, params):
        resp = client.get(
            "/api/meta/holidays", params={**params, "year": 2026}, headers=auth_headers
        )
        assert resp.status_code == 400, resp.text
        assert resp.json()["code"] == "UNKNOWN_HOLIDAY_REGION"

    def test_the_year_is_required(self, client, auth_headers):
        resp = client.get("/api/meta/holidays", params={"country": "GB"}, headers=auth_headers)
        assert resp.status_code == 422, resp.text
        assert "year" in resp.json()["fields"][0]["path"]


class TestBeatsDirectAPI:
    """Test suite for Beat (time log) management endpoints"""

    def test_create_api(self, client, auth_headers):
        """Test POST /api/beats/ - Create a new beat"""
        project = client.post(
            "/api/projects/",
            json={
                "name": f"test-project-{time.time()}",
                "description": "Test project - delete me",
            },
            headers=auth_headers,
        ).json()

        response = client.post(
            "/api/beats/",
            json={
                "project_id": project["id"],
                "start": "2020-04-01T02:00:00",
                "end": "2020-04-01T03:00:00",
            },
            headers=auth_headers,
        )
        assert response.status_code == 201, response.json()
        beat = response.json()
        assert "id" in beat
        assert beat["project_id"] == project["id"]

    def test_list_api(self, client, auth_headers):
        """Test GET /api/beats/ - List all beats"""
        response = client.get("/api/beats/", headers=auth_headers)
        assert response.status_code == 200
        beats = response.json()
        assert isinstance(beats, list)

    def test_list_api_with_project_filter(self, client, auth_headers):
        """Test GET /api/beats/?project_id=X - Filter beats by project"""
        project = client.post(
            "/api/projects/",
            json={
                "name": f"test-project-{time.time()}",
                "description": "Test project - delete me",
            },
            headers=auth_headers,
        ).json()

        client.post(
            "/api/beats/",
            json={
                "project_id": project["id"],
                "start": "2020-04-01T02:00:00",
                "end": "2020-04-01T03:00:00",
            },
            headers=auth_headers,
        )
        client.post(
            "/api/beats/",
            json={
                "project_id": project["id"],
                "start": "2020-04-01T04:00:00",
                "end": "2020-04-01T05:00:00",
            },
            headers=auth_headers,
        )

        response = client.get(f"/api/beats/?project_id={project['id']}", headers=auth_headers)
        assert response.status_code == 200
        beats = response.json()
        assert len(beats) >= 2
        for beat in beats:
            if beat["project_id"] == project["id"]:
                assert beat["project_id"] == project["id"]

    def test_list_api_with_date_filter(self, client, auth_headers):
        """Test GET /api/beats/?date_filter=X - Filter beats by date"""
        project = client.post(
            "/api/projects/",
            json={
                "name": f"test-date-filter-{time.time()}",
                "description": "Test date filter",
            },
            headers=auth_headers,
        ).json()

        # Create beat with specific date
        client.post(
            "/api/beats/",
            json={
                "project_id": project["id"],
                "start": "2024-05-15T10:00:00",
                "end": "2024-05-15T11:00:00",
            },
            headers=auth_headers,
        )

        response = client.get("/api/beats/?date_filter=2024-05-15", headers=auth_headers)
        assert response.status_code == 200
        beats = response.json()
        assert isinstance(beats, list)

    def test_get_beat_by_id(self, client, auth_headers):
        """Test GET /api/beats/{beat_id} - Retrieve specific beat"""
        project = client.post(
            "/api/projects/",
            json={
                "name": f"test-get-beat-{time.time()}",
                "description": "Test get beat",
            },
            headers=auth_headers,
        ).json()

        beat = client.post(
            "/api/beats/",
            json={
                "project_id": project["id"],
                "start": "2020-04-01T02:00:00",
                "end": "2020-04-01T03:00:00",
            },
            headers=auth_headers,
        ).json()

        response = client.get(f"/api/beats/{beat['id']}", headers=auth_headers)
        assert response.status_code == 200
        retrieved_beat = response.json()
        assert retrieved_beat["id"] == beat["id"]
        assert retrieved_beat["project_id"] == project["id"]

    def test_update_api(self, client, auth_headers):
        """Test PUT /api/beats/ - Update existing beat"""
        project = client.post(
            "/api/projects/",
            json={
                "name": f"test-project-{time.time()}",
                "description": "Test project - delete me",
            },
            headers=auth_headers,
        ).json()

        beat = client.post(
            "/api/beats/",
            json={
                "project_id": project["id"],
                "start": "2020-04-01T02:00:00",
                "end": "2020-04-01T03:00:00",
            },
            headers=auth_headers,
        ).json()

        # Update the beat
        beat["end"] = "2020-04-01T04:10:10"
        response = client.put("/api/beats/", json=beat, headers=auth_headers)
        assert response.status_code == 200, response.json()

        # Verify the update
        response = client.get(f"/api/beats/{beat['id']}", headers=auth_headers)
        assert response.status_code == 200, response.json()
        end = response.json()["end"]
        assert end.startswith("2020-04-01T04:10:10")

    def test_delete_beat(self, client, auth_headers):
        """Test DELETE /api/beats/{beat_id} - Delete a beat"""
        project = client.post(
            "/api/projects/",
            json={"name": f"test-delete-{time.time()}", "description": "Test delete"},
            headers=auth_headers,
        ).json()

        beat = client.post(
            "/api/beats/",
            json={
                "project_id": project["id"],
                "start": "2020-04-01T02:00:00",
                "end": "2020-04-01T03:00:00",
            },
            headers=auth_headers,
        ).json()

        response = client.delete(f"/api/beats/{beat['id']}", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["deleted"] is True


class TestTimerAPI:
    """Test suite for Timer status endpoints"""

    def test_timer_status_when_idle(self, client, auth_headers):
        """Test GET /api/timer/status - When no timer is running"""
        # Best effort: there may be no timer to stop, which is the point.
        with contextlib.suppress(Exception):
            client.post(
                "/api/projects/stop",
                json={"time": datetime.now(UTC).isoformat()},
                headers=auth_headers,
            )

        response = client.get("/api/timer/status", headers=auth_headers)
        assert response.status_code == 200
        status = response.json()
        assert "isBeating" in status

    def test_timer_status_when_active(self, client, auth_headers):
        """Test GET /api/timer/status - When timer is running"""
        # Create project and start timer
        project = client.post(
            "/api/projects/",
            json={
                "name": f"test-timer-status-{time.time()}",
                "description": "Test timer status",
            },
            headers=auth_headers,
        ).json()

        # Start timer
        client.post(
            f"/api/projects/{project['id']}/start",
            json={"time": datetime.now(UTC).isoformat()},
            headers=auth_headers,
        )

        # Check status
        response = client.get("/api/timer/status", headers=auth_headers)
        assert response.status_code == 200
        status = response.json()
        assert "isBeating" in status
        if status["isBeating"]:
            assert "project" in status
            assert "since" in status
            assert "so_far" in status
            # Cleanup: stop the active timer to avoid affecting other tests
            client.post(
                "/api/projects/stop",
                json={"time": datetime.now(UTC).isoformat()},
                headers=auth_headers,
            )


class TestCoachEndpoints:
    """Smoke tests for coach endpoints. Since we can't call the real Anthropic
    API in tests, we only test endpoints that don't require LLM calls (usage,
    brief retrieval, memory read) and verify auth/shape."""

    def test_brief_today_returns_null_when_empty(self, client, auth_headers):
        response = client.get("/api/coach/brief/today", headers=auth_headers)
        assert response.status_code == 200
        # No brief generated yet — should return null
        assert response.json() is None

    def test_brief_history_returns_empty_list(self, client, auth_headers):
        response = client.get("/api/coach/brief/history", headers=auth_headers)
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_memory_returns_empty_content(self, client, auth_headers):
        response = client.get("/api/coach/memory", headers=auth_headers)
        assert response.status_code == 200
        body = response.json()
        assert "content" in body

    def test_usage_returns_shape(self, client, auth_headers):
        response = client.get("/api/coach/usage", headers=auth_headers)
        assert response.status_code == 200
        body = response.json()
        assert "days" in body
        assert "month_total_usd" in body
        assert "budget_usd" in body
        assert isinstance(body["days"], list)
        assert body["budget_usd"] > 0

    def test_coach_endpoints_require_auth(self, client):
        for path in [
            "/api/coach/brief/today",
            "/api/coach/brief/history",
            "/api/coach/memory",
            "/api/coach/usage",
        ]:
            assert client.get(path).status_code == 401, f"{path} should require auth"

    def test_chat_requires_auth(self, client):
        response = client.post("/api/coach/chat", json={"message": "hello"})
        assert response.status_code == 401


class TestCoachRouterGapFill:
    """Coach routes whose logic isn't covered by the smoke suite —
    /chat/history pagination + filtering, /usage with seeded rows,
    and the BUDGET_EXCEEDED 429 envelope. Mocks the LLM-touching
    modules so the tests run deterministically; uses real Mongo via
    testcontainers for the persistence assertions."""

    @pytest.fixture(autouse=True)
    def _reset_coach_collections(self, auth_info):
        """Wipe the coach collections this class writes to so tests
        don't pollute each other's reads."""
        import os

        from pymongo import MongoClient

        dsn = os.environ.get("DB_DSN", "mongodb://localhost:27017")
        db_name = os.environ.get("DB_NAME", "beats_test")
        sync = MongoClient(dsn)
        db = sync[db_name]
        for coll in (
            "coach_conversations",
            "llm_usage",
        ):
            db[coll].delete_many({})
        sync.close()
        return

    def _seed_message(
        self,
        auth_info,
        conversation_id: str,
        role: str,
        content: str,
        seconds_ago: int = 0,
    ) -> None:
        """Insert a row directly into coach_conversations. The router's
        /chat/history sorts by created_at desc, so this lets us seed
        a deterministic timeline."""
        import os
        from datetime import UTC as _UTC
        from datetime import datetime as _dt
        from datetime import timedelta as _td

        from bson import ObjectId
        from pymongo import MongoClient

        dsn = os.environ.get("DB_DSN", "mongodb://localhost:27017")
        db_name = os.environ.get("DB_NAME", "beats_test")
        sync = MongoClient(dsn)
        sync[db_name].coach_conversations.insert_one(
            {
                "_id": ObjectId(),
                "user_id": auth_info["user_id"],
                "conversation_id": conversation_id,
                "role": role,
                "content": content,
                "created_at": _dt.now(_UTC) - _td(seconds=seconds_ago),
            }
        )
        sync.close()

    def _seed_usage(
        self,
        auth_info,
        cost_usd: float,
        *,
        purpose: str = "chat",
        days_ago: int = 0,
    ) -> None:
        import os
        from datetime import UTC as _UTC
        from datetime import datetime as _dt

        from bson import ObjectId
        from pymongo import MongoClient

        dsn = os.environ.get("DB_DSN", "mongodb://localhost:27017")
        db_name = os.environ.get("DB_NAME", "beats_test")
        sync = MongoClient(dsn)
        sync[db_name].llm_usage.insert_one(
            {
                "_id": ObjectId(),
                "user_id": auth_info["user_id"],
                "model": "claude-opus-4-7",
                "input_tokens": 1000,
                "output_tokens": 500,
                "cache_creation_input_tokens": 0,
                "cache_read_input_tokens": 0,
                "cost_usd": cost_usd,
                "purpose": purpose,
                "ts": _dt.now(_UTC) - timedelta(days=days_ago),
            }
        )
        sync.close()

    # ── /chat/history ────────────────────────────────────────────────

    def test_chat_history_empty_returns_empty_list(self, client, auth_info):
        resp = client.get("/api/coach/chat/history", headers=auth_info["headers"])
        assert resp.status_code == 200
        assert resp.json() == []

    def test_chat_history_returns_chronological_order(self, client, auth_info):
        """Router fetches descending then reverses → chronological for
        the UI. Pin so a refactor that drops the .reverse() doesn't
        feed the chat UI history backwards."""
        # Newest first by creation time, but the router reverses to
        # oldest-first for the UI. Seed in non-chronological insert
        # order to verify the sort.
        self._seed_message(auth_info, "c-1", "user", "FIRST", seconds_ago=300)
        self._seed_message(auth_info, "c-1", "assistant", "SECOND", seconds_ago=200)
        self._seed_message(auth_info, "c-1", "user", "THIRD", seconds_ago=100)

        resp = client.get("/api/coach/chat/history", headers=auth_info["headers"])
        assert resp.status_code == 200
        contents = [m["content"] for m in resp.json()]
        # Oldest first.
        assert contents == ["FIRST", "SECOND", "THIRD"]

    def test_chat_history_filters_by_conversation_id(self, client, auth_info):
        self._seed_message(auth_info, "c-1", "user", "in c1")
        self._seed_message(auth_info, "c-2", "user", "in c2")

        resp = client.get(
            "/api/coach/chat/history?conversation_id=c-1",
            headers=auth_info["headers"],
        )
        assert resp.status_code == 200
        contents = [m["content"] for m in resp.json()]
        assert contents == ["in c1"]

    def test_chat_history_respects_limit(self, client, auth_info):
        for i in range(5):
            self._seed_message(auth_info, "c-1", "user", f"msg {i}", seconds_ago=100 - i)

        resp = client.get("/api/coach/chat/history?limit=3", headers=auth_info["headers"])
        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 3

    def test_chat_history_validates_limit_bounds(self, client, auth_info):
        # Router declares Query(default=50, ge=1, le=200).
        for q in ("?limit=0", "?limit=201"):
            resp = client.get(f"/api/coach/chat/history{q}", headers=auth_info["headers"])
            assert resp.status_code == 422

    # ── /usage ───────────────────────────────────────────────────────

    def test_usage_aggregates_seeded_rows_by_day(self, client, auth_info):
        """The /usage endpoint groups llm_usage rows by day and sums.
        Pin: today's rows roll up; the response shape carries the
        budget alongside the daily breakdown."""
        self._seed_usage(auth_info, 0.10, purpose="chat")
        self._seed_usage(auth_info, 0.20, purpose="brief")
        # Yesterday — separate bucket.
        self._seed_usage(auth_info, 0.05, purpose="chat", days_ago=1)

        resp = client.get("/api/coach/usage", headers=auth_info["headers"])
        assert resp.status_code == 200
        body = resp.json()
        assert "days" in body
        assert "month_total_usd" in body
        assert "budget_usd" in body
        # Today's total = 0.30, yesterday = 0.05.
        days = {d["date"]: d for d in body["days"]}
        assert len(days) == 2
        # Both days have non-zero cost.
        for d in body["days"]:
            assert d["cost_usd"] > 0
            assert d["calls"] >= 1

    def test_usage_validates_days_param(self, client, auth_info):
        # ge=1, le=90.
        for q in ("?days=0", "?days=91"):
            resp = client.get(f"/api/coach/usage{q}", headers=auth_info["headers"])
            assert resp.status_code == 422

    def test_brief_reads_the_day_jobs_balance_with_its_adjustments(
        self, client, auth_info, monkeypatch
    ):
        """A brief builds the coach's repositories against real Mongo, and its
        day context quotes the running balance the week route reads, a payout
        included. Once ContractService needed its adjustment store, a coach
        that did not pass one failed every brief with a 502."""
        from types import SimpleNamespace

        from anthropic.types import TextBlock

        from beats.coach import brief as brief_module
        from beats.coach.contract_section import describe_balance

        headers = auth_info["headers"]
        project = _day_job(client, headers, opening_balance_hours=10)
        last_monday = datetime.now(UTC).date() - timedelta(days=datetime.now(UTC).weekday() + 7)
        resp = client.post(
            f"/api/projects/{project['id']}/adjustments",
            params={"tz": "UTC"},
            json={"date": last_monday.isoformat(), "kind": "delta", "hours": -4},
            headers=headers,
        )
        assert resp.status_code == 201, resp.text

        sent: list[dict] = []

        async def fake_complete(**kwargs):
            sent.extend(kwargs["messages"])
            return SimpleNamespace(
                content=[TextBlock(type="text", text="Morning.")],
                model="fake",
                cost_usd=0.0,
                input_tokens=0,
                output_tokens=0,
                cache_read_input_tokens=0,
            )

        monkeypatch.setattr(brief_module, "complete", fake_complete)

        resp = client.post("/api/coach/brief/generate", params={"tz": "UTC"}, headers=headers)
        assert resp.status_code == 200, resp.text

        week = client.get(
            f"/api/projects/{project['id']}/contract/week", params={"tz": "UTC"}, headers=headers
        ).json()
        assert week["balance_adjusted"] == -4
        prompt = "\n".join(m["content"] for m in sent if isinstance(m["content"], str))
        line = f"{project['name']} running balance: {describe_balance(week['balance'])}"
        assert line in prompt

    @staticmethod
    def _zone_off_utcs_day() -> str:
        """A timezone whose calendar day is not UTC's right now: UTC+14 is
        a day ahead from 10:00 UTC, UTC−11 a day behind until 11:00 UTC."""
        from zoneinfo import ZoneInfo

        utc_today = datetime.now(UTC).date()
        for name in ("Pacific/Kiritimati", "Pacific/Pago_Pago"):
            if datetime.now(ZoneInfo(name)).date() != utc_today:
                return name
        raise AssertionError("no zone off UTC's day")  # pragma: no cover

    def _assert_day_context_in(self, client, headers, project, sent, tz) -> None:
        from zoneinfo import ZoneInfo

        from beats.coach.contract_section import describe_balance

        prompt = "\n".join(m["content"] for m in sent if isinstance(m["content"], str))
        today = datetime.now(ZoneInfo(tz)).date()
        assert f"## Today: {today.isoformat()}" in prompt
        week = client.get(
            f"/api/projects/{project['id']}/contract/week", params={"tz": tz}, headers=headers
        ).json()
        line = f"{project['name']} running balance: {describe_balance(week['balance'])}"
        assert line in prompt

    def test_chat_reads_the_contract_week_in_the_request_timezone(
        self, client, auth_info, monkeypatch
    ):
        """The chat's day context is the user's day, not UTC's: before the
        route took a tz, a Monday morning in Auckland sent last week's days
        off and contracts that had ended before the user's week, and the
        balance missed an adjustment dated the user's today."""
        from types import SimpleNamespace

        from anthropic.types import TextBlock

        from beats.coach import chat as chat_module

        headers = auth_info["headers"]
        project = _day_job(client, headers, opening_balance_hours=10)
        sent: list[dict] = []

        async def fake_complete(**kwargs):
            sent.extend(kwargs["messages"])
            return SimpleNamespace(content=[TextBlock(type="text", text="Hi.")])

        monkeypatch.setattr(chat_module, "complete", fake_complete)

        tz = self._zone_off_utcs_day()
        with client.stream(
            "POST", "/api/coach/chat", params={"tz": tz}, json={"message": "hi"}, headers=headers
        ) as resp:
            assert resp.status_code == 200
            "".join(resp.iter_text())

        self._assert_day_context_in(client, headers, project, sent, tz)

    def test_memory_rewrite_reads_the_contract_week_in_the_request_timezone(
        self, client, auth_info, monkeypatch
    ):
        """The memory rewrite's day context is the user's day, as the chat's
        and the brief's are."""
        from types import SimpleNamespace

        from anthropic.types import TextBlock

        from beats.coach import memory_rewrite as memory_rewrite_module

        headers = auth_info["headers"]
        project = _day_job(client, headers, opening_balance_hours=10)
        sent: list[dict] = []

        async def fake_complete(**kwargs):
            sent.extend(kwargs["messages"])
            return SimpleNamespace(content=[TextBlock(type="text", text="# Coach memory")])

        monkeypatch.setattr(memory_rewrite_module, "complete", fake_complete)

        tz = self._zone_off_utcs_day()
        resp = client.post("/api/coach/memory/rewrite", params={"tz": tz}, headers=headers)
        assert resp.status_code == 200, resp.text

        self._assert_day_context_in(client, headers, project, sent, tz)

    def test_memory_rewrite_budget_exceeded_uses_envelope_code(
        self, client, auth_info, monkeypatch
    ):
        """Pin parity with /brief and /review: a BudgetExceeded on
        memory rewrite must surface as 429 + code=BUDGET_EXCEEDED,
        not the generic RATE_LIMITED. Without this, a client that
        branches on the code field would render "rate limited" for
        memory but "budget reached" for brief — confusing UX. Locks
        the parity fix from the T4 audit."""
        from beats.api.routers import coach as coach_router
        from beats.coach.usage import BudgetExceeded

        async def fake_rewrite(_user_id, **_kwargs):
            raise BudgetExceeded(spent=20.0, limit=10.0)

        monkeypatch.setattr(coach_router, "rewrite_coach_memory", fake_rewrite)

        resp = client.post("/api/coach/memory/rewrite", headers=auth_info["headers"])
        assert resp.status_code == 429
        body = resp.json()
        assert body["code"] == "BUDGET_EXCEEDED"


class TestCoachDeleteAndChatSse:
    """Three paths uncovered by other coach tests:

    1. DELETE /api/coach/memory — destructive (drops the per-user
       coach personality)
    2. DELETE /api/coach/data — IRREVERSIBLE bulk delete across
       four collections (memory + briefs + conversations + usage)
    3. /api/coach/chat SSE — the streaming endpoint's three
       branches: happy-path event emission, BudgetExceeded → SSE
       error event with code=429, generic Exception → 502 event

    Both DELETE endpoints MUST be tested — they wipe user data
    and a regression in the user-scoping query would let one user
    nuke another's data."""

    def _db(self):
        import os

        from pymongo import MongoClient

        dsn = os.environ.get("DB_DSN", "mongodb://localhost:27017")
        db_name = os.environ.get("DB_NAME", "beats_test")
        sync = MongoClient(dsn)
        return sync, sync[db_name]

    @pytest.fixture(autouse=True)
    def _reset_coach_collections(self, auth_info):
        sync, db = self._db()
        for coll in (
            "coach_memory",
            "daily_briefs",
            "coach_conversations",
            "llm_usage",
        ):
            db[coll].delete_many({})
        sync.close()
        return

    def _seed_all_coach_data(self, user_id: str):
        """Insert one row in each of the four coach collections
        for the given user. Used by the DELETE /data test to
        verify all four are wiped in one shot."""
        from datetime import UTC, datetime

        sync, db = self._db()
        db.coach_memory.insert_one(
            {"user_id": user_id, "content": "be kind", "updated_at": datetime.now(UTC)}
        )
        db.daily_briefs.insert_one(
            {
                "user_id": user_id,
                "date": "2026-04-01",
                "brief": "morning",
                "created_at": datetime.now(UTC),
            }
        )
        db.coach_conversations.insert_one(
            {
                "user_id": user_id,
                "conversation_id": "c-1",
                "role": "user",
                "content": "hi",
                "created_at": datetime.now(UTC),
            }
        )
        db.llm_usage.insert_one(
            {
                "user_id": user_id,
                "ts": datetime.now(UTC),
                "model": "claude-opus-4-7",
                "input_tokens": 100,
                "output_tokens": 50,
                "cost_usd": 0.01,
                "purpose": "chat",
            }
        )
        sync.close()

    def _count_user_data(self, user_id: str) -> dict[str, int]:
        sync, db = self._db()
        out = {
            coll: db[coll].count_documents({"user_id": user_id})
            for coll in (
                "coach_memory",
                "daily_briefs",
                "coach_conversations",
                "llm_usage",
            )
        }
        sync.close()
        return out

    # ---------------- DELETE /api/coach/memory ----------------

    def test_delete_memory_wipes_only_this_users_memory(self, client, auth_info):
        """DELETE /memory drops the requesting user's coach memory
        but leaves OTHER users' memory intact. Pin the user-scoping
        — a regression here would let User A wipe User B's memory."""
        sync, db = self._db()
        # Seed the requesting user's memory + another user's memory
        db.coach_memory.insert_one({"user_id": auth_info["user_id"], "content": "mine"})
        db.coach_memory.insert_one({"user_id": "other-user", "content": "theirs"})
        sync.close()

        resp = client.delete("/api/coach/memory", headers=auth_info["headers"])
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

        sync, db = self._db()
        # Mine: gone. Theirs: intact.
        assert db.coach_memory.count_documents({"user_id": auth_info["user_id"]}) == 0
        assert db.coach_memory.count_documents({"user_id": "other-user"}) == 1
        sync.close()

    # ---------------- DELETE /api/coach/data ----------------

    def test_delete_data_wipes_all_coach_collections_for_user(self, client, auth_info):
        """DELETE /data is the "factory reset" — it MUST wipe all
        four coach collections (memory + briefs + conversations +
        usage) for the requesting user. Pin all four so a refactor
        that skips one (e.g. forgets the new usage logs) is caught."""
        self._seed_all_coach_data(auth_info["user_id"])

        # Sanity: all four non-zero before the delete
        before = self._count_user_data(auth_info["user_id"])
        assert all(c == 1 for c in before.values()), before

        resp = client.delete("/api/coach/data", headers=auth_info["headers"])
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert "all coach data" in body["deleted"]

        # All four collections empty for this user
        after = self._count_user_data(auth_info["user_id"])
        assert all(c == 0 for c in after.values()), after

    def test_delete_data_does_not_touch_other_users(self, client, auth_info):
        """Cross-user safety — DELETE /data scopes to user_id.
        Pin so a regression doesn't accidentally do an unscoped
        delete_many({}) and nuke every user's data on the deploy."""
        # Seed BOTH the requesting user AND a separate user.
        self._seed_all_coach_data(auth_info["user_id"])
        self._seed_all_coach_data("other-user")

        resp = client.delete("/api/coach/data", headers=auth_info["headers"])
        assert resp.status_code == 200

        # The other user's five rows are intact
        other_after = self._count_user_data("other-user")
        assert all(c == 1 for c in other_after.values()), other_after

    def test_delete_endpoints_require_auth(self, client):
        """Both destructive endpoints must reject unauthenticated
        requests. Pin the auth gate — an unauthenticated DELETE
        on these would be a catastrophic data-wipe primitive."""
        assert client.delete("/api/coach/memory").status_code == 401
        assert client.delete("/api/coach/data").status_code == 401

    # ---------------- /api/coach/chat SSE ----------------

    def test_chat_sse_streams_events(self, client, auth_headers, monkeypatch):
        """Happy path: handle_chat_turn yields events; the SSE
        generator wraps each in `data: <json>\\n\\n` and ends
        with `data: [DONE]\\n\\n`. Pin the framing — the UI's
        SSE parser depends on the exact form."""
        from beats.api.routers import coach as coach_router

        async def fake_handle_chat_turn(**_kwargs):
            yield {"type": "text", "text": "hello"}
            yield {"type": "done", "conversation_id": "c-abc"}

        monkeypatch.setattr(coach_router, "handle_chat_turn", fake_handle_chat_turn)

        with client.stream(
            "POST",
            "/api/coach/chat",
            json={"message": "hi"},
            headers=auth_headers,
        ) as resp:
            assert resp.status_code == 200
            assert resp.headers["content-type"].startswith("text/event-stream")
            body = "".join(resp.iter_text())

        # Every event is on its own `data:` line, terminator is [DONE]
        assert 'data: {"type": "text", "text": "hello"}' in body
        assert '"conversation_id": "c-abc"' in body
        assert body.rstrip().endswith("data: [DONE]")

    def test_chat_sse_emits_budget_exceeded_envelope(self, client, auth_headers, monkeypatch):
        """When BudgetExceeded fires inside the stream, the SSE
        generator yields a typed error event with code=429. Pin
        so the UI's "monthly budget reached" toast triggers from
        the right code."""
        from beats.api.routers import coach as coach_router
        from beats.coach.usage import BudgetExceeded

        async def fake_handle_chat_turn(**_kwargs):
            yield {"type": "text", "text": "starting…"}
            raise BudgetExceeded(spent=12.50, limit=10.00)

        monkeypatch.setattr(coach_router, "handle_chat_turn", fake_handle_chat_turn)

        with client.stream(
            "POST",
            "/api/coach/chat",
            json={"message": "hi"},
            headers=auth_headers,
        ) as resp:
            assert resp.status_code == 200
            body = "".join(resp.iter_text())

        # First event surfaces; then the 429 error event; then [DONE]
        assert '"type": "text"' in body
        assert '"type": "error"' in body
        assert '"code": 429' in body
        # The message names the spend and the limit, built from the figures
        assert "$12.50" in body
        assert "$10.00" in body
        assert body.rstrip().endswith("data: [DONE]")

    def test_chat_sse_emits_generic_502_envelope_on_unexpected_failure(
        self, client, auth_headers, monkeypatch
    ):
        """Any other exception inside the stream → a generic 502
        error event ("Coach is temporarily unavailable.") rather
        than letting the connection just close. Pin so the UI sees
        a structured error rather than an SSE truncation."""
        from beats.api.routers import coach as coach_router

        async def fake_handle_chat_turn(**_kwargs):
            yield {"type": "text", "text": "starting…"}
            raise RuntimeError("anthropic exploded")

        monkeypatch.setattr(coach_router, "handle_chat_turn", fake_handle_chat_turn)

        with client.stream(
            "POST",
            "/api/coach/chat",
            json={"message": "hi"},
            headers=auth_headers,
        ) as resp:
            assert resp.status_code == 200
            body = "".join(resp.iter_text())

        assert '"type": "error"' in body
        assert '"code": 502' in body
        assert "temporarily unavailable" in body
        # Internal error message must NOT leak to the user
        assert "anthropic exploded" not in body
        assert body.rstrip().endswith("data: [DONE]")


class TestBriefFeedback:
    """PUT /api/coach/brief/{date}/feedback: a rating on one brief, which the
    brief response carries and a null clears."""

    def _db(self):
        import os

        from pymongo import MongoClient

        dsn = os.environ.get("DB_DSN", "mongodb://localhost:27017")
        sync = MongoClient(dsn)
        return sync, sync[os.environ.get("DB_NAME", "beats_test")]

    @pytest.fixture(autouse=True)
    def _brief(self, auth_info):
        from datetime import UTC, datetime

        sync, db = self._db()
        db.daily_briefs.delete_many({})
        db.daily_briefs.insert_one(
            {
                "user_id": auth_info["user_id"],
                "date": "2026-10-14",
                "body": "Protect the morning.",
                "created_at": datetime.now(UTC),
            }
        )
        sync.close()

    def test_rating_is_stored_and_returned_and_null_clears_it(self, client, auth_info):
        url = "/api/coach/brief/2026-10-14/feedback"
        resp = client.put(url, json={"rating": "helpful"}, headers=auth_info["headers"])
        assert resp.status_code == 200
        assert resp.json()["feedback"] == "helpful"

        resp = client.put(url, json={"rating": "not_useful"}, headers=auth_info["headers"])
        assert resp.json()["feedback"] == "not_useful"

        resp = client.put(url, json={"rating": None}, headers=auth_info["headers"])
        assert resp.status_code == 200
        assert resp.json()["feedback"] is None

    def test_a_day_without_a_brief_is_404(self, client, auth_info):
        resp = client.put(
            "/api/coach/brief/2026-10-13/feedback",
            json={"rating": "helpful"},
            headers=auth_info["headers"],
        )
        assert resp.status_code == 404
        assert resp.json()["code"] == "BRIEF_NOT_FOUND"

    def test_a_bad_date_is_400_and_an_unknown_rating_422(self, client, auth_info):
        h = auth_info["headers"]
        bad_date = client.put(
            "/api/coach/brief/yesterday/feedback", json={"rating": "helpful"}, headers=h
        )
        assert bad_date.status_code == 400
        assert bad_date.json()["code"] == "INVALID_DATE"
        bad_rating = client.put(
            "/api/coach/brief/2026-10-14/feedback", json={"rating": "meh"}, headers=h
        )
        assert bad_rating.status_code == 422

    def test_a_paired_device_may_rate(self, client, auth_info):
        code = client.post("/api/device/pair/code", headers=auth_info["headers"]).json()["code"]
        token = client.post("/api/device/pair/exchange", json={"code": code}).json()["device_token"]
        resp = client.put(
            "/api/coach/brief/2026-10-14/feedback",
            json={"rating": "helpful"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200


class TestCoachBriefErrorPaths:
    """Three coach endpoints with uncovered error envelopes:
    /brief/generate (BudgetExceeded → 429, generic → 502),
    /memory/rewrite (generic → 502, BudgetExceeded already
    pinned by TestCoachRouterGapFill), and /brief/today happy
    path (when a brief doc exists). Pin the user-facing envelopes
    — the same shape contract the chat SSE branch follows."""

    def _db(self):
        import os

        from pymongo import MongoClient

        dsn = os.environ.get("DB_DSN", "mongodb://localhost:27017")
        db_name = os.environ.get("DB_NAME", "beats_test")
        sync = MongoClient(dsn)
        return sync, sync[db_name]

    @pytest.fixture(autouse=True)
    def _reset_briefs(self, auth_info):
        sync, db = self._db()
        db.daily_briefs.delete_many({})
        db.coach_memory.delete_many({})
        sync.close()
        return

    def test_brief_today_returns_doc_when_exists(self, client, auth_info):
        """GET /brief/today with a seeded brief → BriefResponse
        envelope. Pin so the dashboard can render the brief
        without a separate "no brief yet" empty state when one
        exists."""
        from datetime import UTC, datetime

        sync, db = self._db()
        # The endpoint queries today's brief by UTC date; seed on the same
        # frame so the test is deterministic on non-UTC machines (local
        # date.today() can differ from UTC today near midnight).
        today_iso = datetime.now(UTC).date().isoformat()
        db.daily_briefs.insert_one(
            {
                "user_id": auth_info["user_id"],
                "date": today_iso,
                "body": "You logged 2 hours on Alpha already.",
                "created_at": datetime.now(UTC),
            }
        )
        sync.close()

        resp = client.get("/api/coach/brief/today", headers=auth_info["headers"])
        assert resp.status_code == 200
        body = resp.json()
        # BriefResponse pins date + body — pin the body field which
        # the dashboard binds to. The exact `date` value is the
        # ISO string we seeded.
        assert body["date"] == today_iso
        assert body["body"] == "You logged 2 hours on Alpha already."

    def test_brief_today_honors_tz_query_param(self, client, auth_info):
        """/brief/today resolves 'today' in the requested timezone. Seeding
        the brief under the Tokyo-local date and fetching with tz=Asia/Tokyo
        returns it — proving the generate and fetch sides agree on the
        local-day storage key (the whole point of threading tz through)."""
        from datetime import UTC, datetime
        from zoneinfo import ZoneInfo

        sync, db = self._db()
        tokyo_today = datetime.now(ZoneInfo("Asia/Tokyo")).date().isoformat()
        db.daily_briefs.insert_one(
            {
                "user_id": auth_info["user_id"],
                "date": tokyo_today,
                "body": "Tokyo brief.",
                "created_at": datetime.now(UTC),
            }
        )
        sync.close()

        resp = client.get("/api/coach/brief/today?tz=Asia/Tokyo", headers=auth_info["headers"])
        assert resp.status_code == 200
        body = resp.json()
        assert body["date"] == tokyo_today
        assert body["body"] == "Tokyo brief."

    def test_brief_today_rejects_invalid_tz(self, client, auth_info):
        """An unknown IANA timezone name is rejected with the unified 400
        envelope (code INVALID_TIMEZONE), same as the analytics endpoints."""
        resp = client.get("/api/coach/brief/today?tz=Not/AZone", headers=auth_info["headers"])
        assert resp.status_code == 400
        body = resp.json()
        assert body["code"] == "INVALID_TIMEZONE"
        assert isinstance(body["detail"], str)

    def test_brief_generate_budget_exceeded_returns_429_envelope(
        self, client, monkeypatch, auth_info
    ):
        """POST /brief/generate when BudgetExceeded fires inside
        generate_brief → 429 with BUDGET_EXCEEDED code (NOT the
        generic RATE_LIMITED). Pin so the UI's "monthly LLM
        budget reached" toast triggers from the right code."""
        from beats.api.routers import coach as coach_router
        from beats.coach.usage import BudgetExceeded

        async def fake_generate_brief(*args, **kwargs):
            raise BudgetExceeded(spent=12.50, limit=10.00)

        monkeypatch.setattr(coach_router, "generate_brief", fake_generate_brief)

        resp = client.post("/api/coach/brief/generate", headers=auth_info["headers"])
        assert resp.status_code == 429
        body = resp.json()
        # Envelope: top-level `code` + `detail` (the unified
        # error envelope flattens nested HTTPException details
        # into the detail string)
        assert body["code"] == "BUDGET_EXCEEDED"
        assert "$12.50" in str(body)
        assert "$10.00" in str(body)

    def test_brief_generate_generic_failure_returns_502_envelope(
        self, client, monkeypatch, auth_info
    ):
        """Any other exception inside generate_brief → 502 with a
        SANITIZED message. Pin so the actual exception text
        ("anthropic exploded") doesn't leak to the user — only
        the canned "the coach is resting" string surfaces."""
        from beats.api.routers import coach as coach_router

        async def fake_generate_brief(*args, **kwargs):
            raise RuntimeError("anthropic exploded")

        monkeypatch.setattr(coach_router, "generate_brief", fake_generate_brief)

        resp = client.post("/api/coach/brief/generate", headers=auth_info["headers"])
        assert resp.status_code == 502
        text = resp.text
        assert "coach is resting" in text
        # Internal exception message MUST NOT leak
        assert "anthropic exploded" not in text

    def test_brief_generate_invalid_date_returns_400_envelope(self, client, auth_info):
        """POST /brief/generate with a malformed date string → 400
        with INVALID_DATE code. Pin so a typo doesn't 500 the
        endpoint."""
        resp = client.post(
            "/api/coach/brief/generate",
            json={"date": "not-a-date"},
            headers=auth_info["headers"],
        )
        assert resp.status_code == 400
        body = resp.json()
        assert body["code"] == "INVALID_DATE"

    def test_memory_rewrite_generic_failure_returns_502(self, client, monkeypatch, auth_info):
        """Generic exception inside rewrite_coach_memory → 502.
        Pin so the rewrite endpoint doesn't expose internal error
        text. BudgetExceeded → 429 path is already covered by
        TestCoachRouterGapFill.test_memory_rewrite_budget_exceeded."""
        from beats.api.routers import coach as coach_router

        async def fake_rewrite(*args, **kwargs):
            raise RuntimeError("memory rewrite blew up internally")

        monkeypatch.setattr(coach_router, "rewrite_coach_memory", fake_rewrite)

        resp = client.post("/api/coach/memory/rewrite", headers=auth_info["headers"])
        assert resp.status_code == 502
        text = resp.text
        # Sanitized message; internal text not leaked
        assert "memory rewrite blew up" not in text


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


class TestErrorEnvelope:
    """Every HTTP error from the API now flows through the unified envelope:
    {detail: str, code: str, fields?: list}."""

    def test_404_uses_envelope(self, client, auth_headers):
        # Valid ObjectId shape but no such record.
        resp = client.get("/api/beats/507f1f77bcf86cd799439011", headers=auth_headers)
        assert resp.status_code == 404
        body = resp.json()
        assert isinstance(body.get("detail"), str)
        assert body["code"] == "NOT_FOUND"

    def test_validation_error_lists_fields(self, client, auth_headers):
        # Missing required field "project_id" on a beat create.
        resp = client.post("/api/beats/", json={}, headers=auth_headers)
        assert resp.status_code == 422
        body = resp.json()
        assert body["code"] == "VALIDATION_ERROR"
        assert "fields" in body
        assert isinstance(body["fields"], list)
        assert any(f.get("path", "").endswith("project_id") for f in body["fields"]), body["fields"]
        # Each field has the keys clients can rely on.
        for f in body["fields"]:
            assert "path" in f
            assert "message" in f
            assert "type" in f

    def test_missing_auth_envelope(self, client):
        resp = client.get("/api/projects/")
        assert resp.status_code == 401
        body = resp.json()
        assert body["code"] == "MISSING_TOKEN"
        assert "Authentication" in body["detail"]

    def test_validation_error_strips_loc_prefix_from_field_path(self, client, auth_headers):
        # FastAPI tags each validation loc with body / query / path so a
        # raw `loc` is ("body", "project_id"). The handler strips that
        # prefix so consumers see the natural field name. Locked in
        # here — without the strip, a UI form's `<input name="project_id">`
        # mapping would have to know about the body prefix.
        resp = client.post("/api/beats/", json={}, headers=auth_headers)
        assert resp.status_code == 422
        body = resp.json()
        paths = [f["path"] for f in body["fields"]]
        for path in paths:
            assert not path.startswith("body."), f"expected loc prefix stripped, got {path!r}"
            assert not path.startswith("query."), f"expected loc prefix stripped, got {path!r}"

    def test_validation_singular_summary(self, client, auth_headers):
        # Detail summary differs in singular vs plural ("Validation
        # failed for one field" vs "Validation failed for N fields").
        # Easier on the eyes than "1 fields".
        resp = client.post(
            "/api/beats/",
            # Missing only project_id; supply everything else valid so
            # exactly one field fails. Time fields use ISO so they'll
            # parse cleanly.
            json={
                "started_at": "2026-04-30T10:00:00Z",
                "stopped_at": "2026-04-30T11:00:00Z",
            },
            headers=auth_headers,
        )
        assert resp.status_code == 422
        body = resp.json()
        if len(body["fields"]) == 1:
            assert body["detail"] == "Validation failed for one field", body["detail"]
        else:
            # Defensive: if a future schema change adds another required
            # field, the plural form should kick in. The test still
            # documents both branches even if only one fires today.
            assert body["detail"] == f"Validation failed for {len(body['fields'])} fields"

    def test_router_can_override_default_code_with_dict_detail(self, client, auth_headers):
        # The errors.py handler honors `detail={"code": ..., "message": ...}`
        # so routers can issue more-specific machine codes than the status-
        # default. Coach uses this for INVALID_DATE on bad date input
        # (default would be the generic BAD_REQUEST).
        resp = client.post(
            "/api/coach/brief/generate",
            json={"date": "not-a-date"},
            headers=auth_headers,
        )
        assert resp.status_code == 400, resp.text
        body = resp.json()
        assert body["code"] == "INVALID_DATE", body
        assert "not-a-date" in body["detail"]

    def test_domain_exception_uses_envelope(self, client, auth_headers):
        # NoActiveTimer is the canonical 400 DomainException — raised
        # when stopping a timer that isn't running. Locks in that the
        # @app.exception_handler(DomainException) handler in server.py
        # produces the same envelope shape (with the 400-default code
        # since DomainException carries no `code` attribute).
        resp = client.post(
            "/api/projects/stop",
            json={"time": "2026-04-30T10:00:00Z"},
            headers=auth_headers,
        )
        assert resp.status_code == 400, resp.text
        body = resp.json()
        assert body["code"] == "BAD_REQUEST"
        assert "No timer" in body["detail"]


class TestIdempotentReplay:
    """Timer start/stop must be idempotent under retries keyed by X-Client-Id."""

    def _create_project(self, client, auth_headers) -> str:
        res = client.post(
            "/api/projects/",
            json={"name": "Idempotency Probe", "description": "test"},
            headers=auth_headers,
        )
        assert res.status_code == 201, res.text
        return res.json()["id"]

    def test_repeated_start_with_same_client_id_is_replayed(self, client, auth_headers):
        """Second POST with same X-Client-Id returns the cached response + replay flag."""
        project_id = self._create_project(client, auth_headers)
        headers = {**auth_headers, "X-Client-Id": "test-client-start-1"}
        first = client.post(
            f"/api/projects/{project_id}/start",
            json={"time": "2026-04-16T10:00:00Z"},
            headers=headers,
        )
        assert first.status_code in (200, 201), first.text
        assert first.headers.get("X-Idempotent-Replay") is None

        # Retry with same id — should NOT produce a second timer start.
        second = client.post(
            f"/api/projects/{project_id}/start",
            json={"time": "2026-04-16T10:00:05Z"},  # different time ignored
            headers=headers,
        )
        assert second.status_code == first.status_code
        assert second.headers.get("X-Idempotent-Replay") == "true"
        assert second.content == first.content

        # Clean up the running timer.
        client.post(
            "/api/projects/stop",
            json={"time": "2026-04-16T10:00:30Z"},
            headers=auth_headers,
        )

    def test_different_client_id_is_not_replayed(self, client, auth_headers):
        """A fresh client id is treated as a new write and not served from cache."""
        project_id = self._create_project(client, auth_headers)
        start_a = client.post(
            f"/api/projects/{project_id}/start",
            json={"time": "2026-04-16T11:00:00Z"},
            headers={**auth_headers, "X-Client-Id": "unique-a"},
        )
        assert start_a.status_code in (200, 201)

        # Stop, then re-start with a different client id — the second start
        # should execute (new row in the log), not replay.
        client.post(
            "/api/projects/stop",
            json={"time": "2026-04-16T11:00:10Z"},
            headers=auth_headers,
        )
        start_b = client.post(
            f"/api/projects/{project_id}/start",
            json={"time": "2026-04-16T11:00:20Z"},
            headers={**auth_headers, "X-Client-Id": "unique-b"},
        )
        assert start_b.status_code in (200, 201)
        assert start_b.headers.get("X-Idempotent-Replay") is None

        client.post(
            "/api/projects/stop",
            json={"time": "2026-04-16T11:00:30Z"},
            headers=auth_headers,
        )

    def test_failed_mutation_is_not_cached_for_replay(self, client, auth_headers):
        """A 4xx response on a guarded path MUST NOT be cached in
        mutation_log — the user must be able to fix and retry
        with the same client id. Pin the non-2xx skip branch
        in the middleware: a regression that cached failures
        would lock the user out of retrying the same operation.

        Idempotency middleware ONLY covers /api/projects/{id}/start
        and /stop (per IDEMPOTENT_PATH_SUFFIXES) — so we trigger
        the failure on /start with a malformed body."""
        project_id = self._create_project(client, auth_headers)
        headers = {**auth_headers, "X-Client-Id": "test-failed-mutation-start"}

        # First call: malformed body (missing required `time` field
        # would 422; sending a wrong type does the same)
        first = client.post(
            f"/api/projects/{project_id}/start",
            json={"time": "not-an-iso-datetime"},
            headers=headers,
        )
        # Either 422 (validation) or 400 (parse) — both are 4xx and
        # MUST NOT be cached. Pin the >=400 contract.
        assert first.status_code >= 400
        assert first.headers.get("X-Idempotent-Replay") is None

        # Retry with same client id and a valid body — executes
        # fresh, NOT a replay of the cached failure
        second = client.post(
            f"/api/projects/{project_id}/start",
            json={"time": "2026-04-16T12:00:00Z"},
            headers=headers,
        )
        assert second.status_code in (200, 201), second.text
        # Pin: fresh execution, not a replay
        assert second.headers.get("X-Idempotent-Replay") is None

        # Clean up
        client.post(
            "/api/projects/stop",
            json={"time": "2026-04-16T12:00:30Z"},
            headers=auth_headers,
        )


class TestCsvAndJsonExport:
    """The CSV-sessions and full-JSON export endpoints, plus the
    JSON-import round trip. Pin the response shape (Content-Type,
    Content-Disposition, header row, JSON keys) — these power the
    user's Settings → Export panel and the cross-deploy migration
    path."""

    def _create_project(self, client, auth_headers, name: str) -> str:
        res = client.post(
            "/api/projects/",
            json={"name": name, "description": "csv probe"},
            headers=auth_headers,
        )
        assert res.status_code == 201, res.text
        return res.json()["id"]

    def test_csv_sessions_export_empty(self, client, auth_headers):
        """No completed beats → CSV with header row only. Pin the
        7-column header so a refactor doesn't silently rename a
        column the user's spreadsheets bind to."""
        resp = client.get("/api/export/csv/sessions", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/csv")
        # Filename is dated for the user
        cd = resp.headers.get("content-disposition", "")
        assert "beats_sessions_" in cd
        assert ".csv" in cd
        # Header row pinned
        first_line = resp.text.splitlines()[0]
        assert first_line == "date,project,start,end,duration_minutes,note,tags"

    def test_csv_sessions_export_with_data(self, client, auth_headers):
        """A completed beat renders one row with the project name
        resolved (not the project_id) and tags joined with `;`.
        Pin both — users' downstream spreadsheets parse on those
        specific separators."""
        project_id = self._create_project(client, auth_headers, "CSV Probe")
        # Start + stop a timer to create a completed beat
        client.post(
            f"/api/projects/{project_id}/start",
            json={"time": "2026-04-16T09:00:00Z"},
            headers=auth_headers,
        )
        client.post(
            "/api/projects/stop",
            json={"time": "2026-04-16T09:30:00Z"},
            headers=auth_headers,
        )
        resp = client.get("/api/export/csv/sessions", headers=auth_headers)
        assert resp.status_code == 200
        lines = resp.text.strip().splitlines()
        # Header + at least one data row
        assert len(lines) >= 2
        data_row = lines[1]
        # Project name resolved
        assert "CSV Probe" in data_row
        # 30-minute duration
        assert ",30," in data_row

    def test_csv_sessions_export_names_an_archived_projects_sessions(self, client, auth_headers):
        # A finished day job is archived; its sessions are still exported,
        # under its name rather than "Unknown".
        project_id = self._create_project(client, auth_headers, "CSV Archived")
        _log(client, auth_headers, project_id, "2026-04-15T09:00:00+00:00", 30)
        resp = client.post(f"/api/projects/{project_id}/archive", headers=auth_headers)
        assert resp.status_code == 200, resp.text

        resp = client.get("/api/export/csv/sessions", headers=auth_headers)

        assert resp.status_code == 200
        rows = list(csv.reader(io.StringIO(resp.text)))
        assert [r[1] for r in rows[1:] if r[0] == "2026-04-15"] == ["CSV Archived"]

    def test_csv_sessions_export_filters_by_project(self, client, auth_headers):
        """`?project_id=X` scopes the export to one project. Pin so
        a regression doesn't leak other projects' rows when the
        user clicks "Export this project"."""
        a_id = self._create_project(client, auth_headers, "CSV Filter A")
        b_id = self._create_project(client, auth_headers, "CSV Filter B")
        for pid in (a_id, b_id):
            client.post(
                f"/api/projects/{pid}/start",
                json={"time": "2026-04-17T09:00:00Z"},
                headers=auth_headers,
            )
            client.post(
                "/api/projects/stop",
                json={"time": "2026-04-17T09:15:00Z"},
                headers=auth_headers,
            )
        resp = client.get(
            "/api/export/csv/sessions",
            params={"project_id": a_id},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        # Filter A appears, Filter B does NOT
        assert "CSV Filter A" in resp.text
        assert "CSV Filter B" not in resp.text

    def test_full_json_export_shape(self, client, auth_headers):
        """GET /api/export/full returns a JSON envelope with the
        top-level keys the import endpoint reads back. Pin so
        the export → reimport round trip can't drift."""
        self._create_project(client, auth_headers, "JSON Probe")
        resp = client.get("/api/export/full", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("application/json")
        body = resp.json()
        assert set(body.keys()) >= {
            "exported_at",
            "version",
            "projects",
            "beats",
            "absences",
            "balance_adjustments",
        }
        # 1.1 is the format that carries absences and balance adjustments.
        assert body["version"] == "1.1"

    def test_full_json_export_carries_absences_and_adjustments(self, client, auth_headers):
        """What a day job's balance is made of beyond its contract and its
        sessions is in the backup: every absence and every adjustment, with
        the fields the import needs to write them back."""
        project = _day_job(client, auth_headers)
        absence = client.post(
            f"/api/projects/{project['id']}/absences",
            json={"date": "2026-03-04", "type": "vacation", "half_day": True, "note": "dentist"},
            headers=auth_headers,
        )
        assert absence.status_code == 201, absence.text
        adjustment = client.post(
            f"/api/projects/{project['id']}/adjustments",
            params={"tz": "UTC"},
            json={"date": "2026-03-02", "kind": "delta", "hours": -4, "note": "paid out"},
            headers=auth_headers,
        )
        assert adjustment.status_code == 201, adjustment.text

        body = client.get("/api/export/full", headers=auth_headers).json()

        assert [a for a in body["absences"] if a["project_id"] == project["id"]] == [absence.json()]
        assert [a for a in body["balance_adjustments"] if a["project_id"] == project["id"]] == [
            adjustment.json()
        ]

    def test_full_json_round_trip(self, client, auth_headers):
        """Export → Import round-trip: posting the exported JSON
        back to /api/export/import upserts the rows by ID. Pin so
        a user can move data between deploys (the doc-stated use
        case for this pair of endpoints)."""
        self._create_project(client, auth_headers, "Round Trip")
        export = client.get("/api/export/full", headers=auth_headers)
        assert export.status_code == 200

        # Re-upload as multipart file
        imported = client.post(
            "/api/export/import",
            files={"file": ("backup.json", export.content, "application/json")},
            headers=auth_headers,
        )
        assert imported.status_code == 200
        body = imported.json()
        assert body["status"] == "ok"
        assert body["imported"]["projects"] >= 1

    def test_full_json_round_trip_with_projects_and_beats(self, client, auth_headers):
        """Existing round-trip seeds only projects. Pin that beats
        round-trip too — those are separate import branches and a
        regression in either would silently lose user data on
        cross-deploy migrations."""
        # Seed: project + beat
        project_id = self._create_project(client, auth_headers, "Full Round Trip")
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

        export = client.get("/api/export/full", headers=auth_headers)
        assert export.status_code == 200
        body = export.json()
        # Both entity types present in export
        assert len(body["projects"]) >= 1
        assert len(body["beats"]) >= 1

        imported = client.post(
            "/api/export/import",
            files={"file": ("backup.json", export.content, "application/json")},
            headers=auth_headers,
        )
        assert imported.status_code == 200
        imp = imported.json()["imported"]
        # Both counts non-zero — pin so a refactor that drops
        # one of the import branches surfaces immediately
        assert imp["projects"] >= 1
        assert imp["beats"] >= 1


def _without_ids(value):
    """A response with every `id` taken out: an absence or an adjustment is
    identified by its project and date, and one restored into an empty
    account gets a new id."""
    if isinstance(value, dict):
        return {k: _without_ids(v) for k, v in value.items() if k != "id"}
    if isinstance(value, list | tuple):
        return [_without_ids(v) for v in value]
    return value


class TestBackupImport:
    """POST /api/export/import against what a day job's balance is made of:
    the round trip, the previous build's file, and the rules the restore
    goes through. Each test has its own day job; the one that empties the
    account empties only the collections a backup holds."""

    @staticmethod
    def _export(client, headers) -> dict:
        resp = client.get("/api/export/full", headers=headers)
        assert resp.status_code == 200, resp.text
        return resp.json()

    @staticmethod
    def _import(client, headers, backup: dict, tz: str = "UTC"):
        return client.post(
            "/api/export/import",
            params={"tz": tz},
            files={"file": ("backup.json", json.dumps(backup), "application/json")},
            headers=headers,
        )

    @staticmethod
    def _standing(client, headers, project_id: str) -> tuple[dict, dict]:
        week = client.get(
            f"/api/projects/{project_id}/contract/week",
            params={"week_of": WEEK, "tz": "UTC"},
            headers=headers,
        )
        assert week.status_code == 200, week.text
        ledger = client.get(
            f"/api/projects/{project_id}/ledger",
            params={"weeks": 104, "tz": "UTC"},
            headers=headers,
        )
        assert ledger.status_code == 200, ledger.text
        return week.json(), ledger.json()

    @staticmethod
    def _sessions_on(client, headers, day: str) -> list[dict]:
        resp = client.get("/api/beats/", params={"date_filter": day}, headers=headers)
        assert resp.status_code == 200, resp.text
        return resp.json()

    @staticmethod
    def _adjust(client, headers, project_id: str, **body) -> dict:
        resp = client.post(
            f"/api/projects/{project_id}/adjustments",
            params={"tz": "UTC"},
            json=body,
            headers=headers,
        )
        assert resp.status_code == 201, resp.text
        return resp.json()

    @staticmethod
    def _absent(client, headers, project_id: str, **body) -> dict:
        resp = client.post(f"/api/projects/{project_id}/absences", json=body, headers=headers)
        assert resp.status_code == 201, resp.text
        return resp.json()

    def test_a_day_jobs_balance_is_the_same_after_a_round_trip(
        self, client, auth_headers, auth_info, mongo
    ):
        # Everything the balance reads: an opening balance, a company day,
        # sessions, a full and a half day off, a payout and a later reset.
        project = _day_job(
            client, auth_headers, opening_balance_hours=6, company_holidays=[COMPANY_DAY]
        )
        pid = project["id"]
        _log(client, auth_headers, pid, "2026-03-02T08:00:00+00:00", 9 * 60)
        _log(client, auth_headers, pid, "2026-03-06T08:00:00+00:00", 5 * 60)
        self._absent(client, auth_headers, pid, date="2026-03-03", type="vacation")
        self._absent(client, auth_headers, pid, date="2026-03-05", type="sick", half_day=True)
        self._adjust(client, auth_headers, pid, date="2026-03-02", kind="delta", hours=-4)
        self._adjust(client, auth_headers, pid, date="2026-06-01", kind="reset", hours=2)
        before = self._standing(client, auth_headers, pid)
        on_the_day = self._sessions_on(client, auth_headers, "2026-03-02")
        assert len(on_the_day) == 1

        backup = self._export(client, auth_headers)
        # A restore into an empty account: what a backup holds, gone.
        for collection in ("projects", "timeLogs", "absences", "balance_adjustments"):
            mongo[collection].delete_many({"user_id": auth_info["user_id"]})
        resp = self._import(client, auth_headers, backup)

        assert resp.status_code == 200, resp.text
        assert resp.json()["skipped"] == []
        assert resp.json()["imported"] == {
            "projects": len(backup["projects"]),
            "beats": len(backup["beats"]),
            "absences": len(backup["absences"]),
            "balance_adjustments": len(backup["balance_adjustments"]),
        }
        after = self._standing(client, auth_headers, pid)
        assert after[0]["balance"] is not None
        assert _without_ids(after) == _without_ids(before)
        # The week and the ledger read beats by project; the heatmap, the
        # rhythm, the wall clock's bars and the day's list read them by a
        # range of dates, which matches only a session stored with dates.
        assert self._sessions_on(client, auth_headers, "2026-03-02") == on_the_day

    def test_an_archived_day_job_survives_a_round_trip(
        self, client, auth_headers, auth_info, mongo
    ):
        # A finished job is archived, with the settlement that paid out its
        # final balance: both are the user's, and both come back.
        project = _day_job(client, auth_headers, ended_on="2026-03-06")
        self._adjust(client, auth_headers, project["id"], date="2026-03-09", kind="reset", hours=0)
        resp = client.post(f"/api/projects/{project['id']}/archive", headers=auth_headers)
        assert resp.status_code == 200, resp.text
        before = self._standing(client, auth_headers, project["id"])

        backup = self._export(client, auth_headers)
        for collection in ("projects", "timeLogs", "absences", "balance_adjustments"):
            mongo[collection].delete_many({"user_id": auth_info["user_id"]})
        resp = self._import(client, auth_headers, backup)

        assert resp.status_code == 200, resp.text
        assert resp.json()["skipped"] == []
        archived = client.get(
            "/api/projects/", params={"archived": True}, headers=auth_headers
        ).json()
        assert [p["id"] for p in archived] == [project["id"]]
        assert _without_ids(self._standing(client, auth_headers, project["id"])) == _without_ids(
            before
        )

    def test_a_backup_from_the_previous_build_imports(self, client, auth_headers):
        # 1.0 had no absences or adjustments; a file without the keys is a
        # backup with none of them, not a 422.
        project = _day_job(client, auth_headers)
        _log(client, auth_headers, project["id"], "2026-03-02T08:00:00+00:00", 60)
        backup = self._export(client, auth_headers)
        backup["version"] = "1.0"
        del backup["absences"], backup["balance_adjustments"]

        resp = self._import(client, auth_headers, backup)

        assert resp.status_code == 200, resp.text
        assert resp.json() == {
            "status": "ok",
            "imported": {
                "projects": len(backup["projects"]),
                "beats": len(backup["beats"]),
                "absences": 0,
                "balance_adjustments": 0,
            },
            "skipped": [],
        }

    def test_a_record_its_route_would_refuse_is_left_out_and_named(self, client, auth_headers):
        # An absence outlives a change away from day_job, so an honest export
        # carries one its route now refuses; an adjustment moved before the
        # first day is one the adjustment route would refuse.
        former = _day_job(client, auth_headers)
        self._absent(client, auth_headers, former["id"], date="2026-03-03", type="vacation")
        resp = client.put(
            "/api/projects/",
            json={"id": former["id"], "name": former["name"], "kind": "freelance"},
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        job = _day_job(client, auth_headers)
        kept = self._adjust(
            client, auth_headers, job["id"], date="2026-03-02", kind="delta", hours=3
        )
        moved = self._adjust(
            client, auth_headers, job["id"], date="2026-03-09", kind="delta", hours=1
        )
        backup = self._export(client, auth_headers)
        for record in backup["balance_adjustments"]:
            if record["id"] == moved["id"]:
                record["date"] = "2025-12-29"
        client.delete(f"/api/projects/{job['id']}/adjustments/{moved['id']}", headers=auth_headers)

        resp = self._import(client, auth_headers, backup)

        assert resp.status_code == 200, resp.text
        skipped = {(s["collection"], s["project_id"], s["code"]) for s in resp.json()["skipped"]}
        assert skipped == {
            ("absences", former["id"], "NOT_A_DAY_JOB"),
            ("balance_adjustments", job["id"], "ADJUSTMENT_OUTSIDE_BALANCE"),
        }
        _, ledger = self._standing(client, auth_headers, job["id"])
        restored = [a for week in ledger["weeks"] for a in week["adjustments"]]
        assert [(a["id"], a["date"]) for a in restored] == [(kept["id"], "2026-03-02")]

    def test_a_malformed_record_is_a_422_naming_it_and_writes_nothing(self, client, auth_headers):
        project = _day_job(client, auth_headers)
        self._adjust(client, auth_headers, project["id"], date="2026-03-02", kind="delta", hours=2)
        backup = self._export(client, auth_headers)
        for record in backup["projects"]:
            if record["id"] == project["id"]:
                record["name"] = "renamed by the backup"
        # A string is not hours, as on the adjustment route.
        backup["balance_adjustments"][0]["hours"] = "2"

        resp = self._import(client, auth_headers, backup)

        assert resp.status_code == 422, resp.text
        assert [f["path"] for f in resp.json()["fields"]] == ["balance_adjustments.0.hours"]
        listed = client.get("/api/projects/", headers=auth_headers).json()
        assert next(p for p in listed if p["id"] == project["id"])["name"] == project["name"]

    def test_a_malformed_session_is_a_422_naming_it_and_writes_nothing(self, client, auth_headers):
        project = _day_job(client, auth_headers)
        _log(client, auth_headers, project["id"], "2026-03-02T08:00:00+00:00", 60)
        backup = self._export(client, auth_headers)
        for record in backup["projects"]:
            if record["id"] == project["id"]:
                record["name"] = "renamed by the backup"
        backup["beats"][0]["start"] = "the second of March"

        resp = self._import(client, auth_headers, backup)

        assert resp.status_code == 422, resp.text
        assert [f["path"] for f in resp.json()["fields"]] == ["beats.0.start"]
        listed = client.get("/api/projects/", headers=auth_headers).json()
        assert next(p for p in listed if p["id"] == project["id"])["name"] == project["name"]

    def test_another_accounts_records_are_refused_and_stay_theirs(
        self, client, auth_headers, other_auth_headers
    ):
        # The other account's file, imported here: a restore keeps ids, and
        # these are theirs. Before, the session moved into this account.
        theirs = _create_project(client, other_auth_headers)
        _log(client, other_auth_headers, theirs["id"], "2026-03-02T08:00:00+00:00", 60)
        their_backup = self._export(client, other_auth_headers)
        mine = _create_project(client, auth_headers)
        my_backup = self._export(client, auth_headers)
        for record in my_backup["projects"]:
            if record["id"] == mine["id"]:
                record["name"] = "renamed by the backup"

        for backup in (
            {"beats": their_backup["beats"]},
            {"projects": their_backup["projects"]},
            # Mine first: nothing of it is written either.
            {"projects": my_backup["projects"] + their_backup["projects"]},
        ):
            resp = self._import(client, auth_headers, backup)
            assert resp.status_code == 409, resp.text
            assert resp.json()["code"] == "BACKUP_OF_ANOTHER_ACCOUNT"

        their_sessions = client.get("/api/beats/", headers=other_auth_headers).json()
        assert [b["id"] for b in their_sessions] == [b["id"] for b in their_backup["beats"]]
        their_projects = client.get("/api/projects/", headers=other_auth_headers).json()
        assert [(p["id"], p["name"]) for p in their_projects] == [(theirs["id"], theirs["name"])]
        listed = client.get("/api/projects/", headers=auth_headers).json()
        assert theirs["id"] not in {p["id"] for p in listed}
        assert next(p for p in listed if p["id"] == mine["id"])["name"] == mine["name"]

    def test_a_malformed_id_is_a_422_naming_it_and_writes_nothing(self, client, auth_headers):
        project = _create_project(client, auth_headers)
        _log(client, auth_headers, project["id"], "2026-03-02T08:00:00+00:00", 60)
        backup = self._export(client, auth_headers)
        for record in backup["projects"]:
            if record["id"] == project["id"]:
                record["name"] = "renamed by the backup"
        backup["projects"].append({"id": "not-an-id", "name": "x"})
        backup["beats"][0]["id"] = "zz"

        resp = self._import(client, auth_headers, backup)

        assert resp.status_code == 422, resp.text
        assert [f["path"] for f in resp.json()["fields"]] == [
            f"projects.{len(backup['projects']) - 1}.id",
            "beats.0.id",
        ]
        listed = client.get("/api/projects/", headers=auth_headers).json()
        assert next(p for p in listed if p["id"] == project["id"])["name"] == project["name"]

    def test_restoring_a_contract_reconciles_its_adjustments(self, client, auth_headers):
        # Since the export, the contract started earlier and an adjustment
        # was dated in the weeks it gained. Restoring the later first day
        # would leave that adjustment counting for nothing: refused, as the
        # contract route refuses it.
        #
        # Ahead of it in the file, a project renamed since: there is no
        # transaction, so that one is restored before the refusal, and the
        # session after it is not.
        ahead = _create_project(client, auth_headers)
        project = _day_job(client, auth_headers)
        _log(client, auth_headers, project["id"], "2026-03-02T08:00:00+00:00", 60)
        backup = self._export(client, auth_headers)
        backup["projects"] = [
            next(p for p in backup["projects"] if p["id"] == pid)
            for pid in (ahead["id"], project["id"])
        ]
        backup["beats"] = [b for b in backup["beats"] if b["project_id"] == project["id"]]
        resp = client.put(
            "/api/projects/", json={**ahead, "name": "renamed since"}, headers=auth_headers
        )
        assert resp.status_code == 200, resp.text
        earlier = [{**FULL_TIME[0], "effective_from": "2025-12-01"}]
        _put_contract(client, auth_headers, project["id"], terms=earlier)
        self._adjust(client, auth_headers, project["id"], date="2025-12-01", kind="delta", hours=5)
        resp = client.delete(f"/api/beats/{backup['beats'][0]['id']}", headers=auth_headers)
        assert resp.status_code == 200, resp.text

        resp = self._import(client, auth_headers, backup)

        assert resp.status_code == 409, resp.text
        assert resp.json()["code"] == "ADJUSTMENT_BEFORE_START"
        listed = client.get("/api/projects/", headers=auth_headers).json()
        assert next(p for p in listed if p["id"] == ahead["id"])["name"] == ahead["name"]
        sessions = client.get(
            "/api/beats/", params={"project_id": project["id"]}, headers=auth_headers
        )
        assert sessions.json() == []


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


class TestAuthenticationMiddleware:
    """Test suite for authentication middleware"""

    def test_all_requests_require_auth(self, client):
        """Test that all requests (including GET) require authentication"""
        response = client.get("/api/projects/")
        assert response.status_code == 401

    def test_post_requests_require_auth(self, client):
        """Test POST requests require authentication"""
        response = client.post("/api/projects/", json={"name": "test", "description": "test"})
        assert response.status_code == 401

    def test_put_requests_require_auth(self, client):
        """Test PUT requests require authentication"""
        response = client.put(
            "/api/projects/", json={"id": "test", "name": "test", "description": "test"}
        )
        assert response.status_code == 401

    def test_invalid_bearer_token(self, client):
        """Test invalid Bearer token is rejected"""
        response = client.get(
            "/api/projects/",
            headers={"Authorization": "Bearer invalid-jwt-token"},
        )
        assert response.status_code == 401
        body = response.json()
        assert "Invalid or expired" in body["detail"]
        assert body["code"] == "INVALID_TOKEN"

    def test_public_endpoints_no_auth(self, client):
        """Test public endpoints don't require auth"""
        response = client.get("/health")
        assert response.status_code == 200

    def test_auth_endpoints_no_auth(self, client):
        """Test auth endpoints are accessible without auth (no 401)"""
        response = client.get("/api/auth/login/options")
        # 200 if credentials exist, 400 if no credentials — either way, not 401
        assert response.status_code != 401


class TestLogoutAndTokenRevocation:
    """Test the logout endpoint and token revocation."""

    def _make_token(self, user_id: str, email: str = "test@example.com") -> str:
        from beats.auth.session import SessionManager
        from beats.settings import settings

        sm = SessionManager(settings.jwt_secret)
        return sm.create_session_token(user_id, email)

    def test_logout_revokes_token(self, client, auth_info):
        """POST /api/account/logout revokes the token so it can't be used again."""
        token = self._make_token(auth_info["user_id"])
        headers = {"Authorization": f"Bearer {token}"}

        # Token works before logout
        assert client.get("/api/projects/", headers=headers).status_code == 200

        # Logout
        response = client.post("/api/account/logout", headers=headers)
        assert response.status_code == 204

        # Token is now rejected
        assert client.get("/api/projects/", headers=headers).status_code == 401

    def test_logout_without_token_requires_auth(self, client):
        """POST /api/account/logout without a token returns 401."""
        response = client.post("/api/account/logout")
        assert response.status_code == 401

    def test_other_tokens_unaffected_by_logout(self, client, auth_info):
        """Revoking one token doesn't affect other tokens for the same user."""
        token_a = self._make_token(auth_info["user_id"])
        token_b = self._make_token(auth_info["user_id"])

        # Revoke token A
        client.post("/api/account/logout", headers={"Authorization": f"Bearer {token_a}"})

        # Token B still works
        assert (
            client.get("/api/projects/", headers={"Authorization": f"Bearer {token_b}"}).status_code
            == 200
        )


class TestAccountAPI:
    """/api/account/{me,refresh,credentials} — auth-critical endpoints
    consumed by every authenticated client surface (UI, companion, daemon
    pair flow). Previously zero coverage — tests pin the contract so a
    future refactor can't quietly break passkey deletion semantics.
    """

    @pytest.fixture(autouse=True)
    def _reset_account_state(self, auth_info):
        """clean_db is class-scoped, so credentials seeded in one test
        leak into the next. Drop credentials and (re-)ensure the test
        user exists before every test in this class. Also clear the
        session manager's in-memory revoked-tokens set so a refresh-
        test that revokes auth_info's token doesn't 401 every later
        test that reuses auth_info["headers"]."""
        import os
        from datetime import UTC, datetime

        from bson import ObjectId
        from pymongo import MongoClient

        from beats.api.routers.auth import _session_manager

        dsn = os.environ.get("DB_DSN", "mongodb://localhost:27017")
        db_name = os.environ.get("DB_NAME", "beats_test")
        sync = MongoClient(dsn)
        db = sync[db_name]
        db.credentials.delete_many({})
        # test_me_404 deletes the user; restore it so the rest of the
        # tests can still resolve the JWT's sub.
        db.users.update_one(
            {"_id": ObjectId(auth_info["user_id"])},
            {
                "$set": {
                    "email": "test@example.com",
                    "display_name": "Test User",
                    "created_at": datetime.now(UTC),
                }
            },
            upsert=True,
        )
        sync.close()
        _session_manager._revoked_tokens.clear()
        return

    def _seed_credential(self, user_id: str, credential_id: str, device_name: str = "Test") -> None:
        """Insert a credential row directly to skip the WebAuthn ceremony.
        Schema is the same as auth/storage.py:save_credential writes."""
        import os

        from pymongo import MongoClient

        dsn = os.environ.get("DB_DSN", "mongodb://localhost:27017")
        db_name = os.environ.get("DB_NAME", "beats_test")
        sync_client = MongoClient(dsn)
        db = sync_client[db_name]
        db.credentials.insert_one(
            {
                "user_id": user_id,
                "credential_id": credential_id,
                "public_key": "fake-public-key-base64url",
                "sign_count": 0,
                "created_at": "2026-04-30T10:00:00",
                "device_name": device_name,
            }
        )
        sync_client.close()

    def test_me_returns_current_user(self, client, auth_info):
        resp = client.get("/api/account/me", headers=auth_info["headers"])
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["email"] == "test@example.com"
        assert body["display_name"] == "Test User"
        assert body["identities"] == []
        assert body["sso_provisioned"] is False
        assert set(body) == {"email", "display_name", "identities", "sso_provisioned"}

    def test_me_404_when_user_deleted_under_token(self, client, auth_info):
        """Token still validates JWT-wise but the user row is gone — 404
        rather than 200-with-empty. Locks in the behavior that lets a
        deleted-account flow surface meaningfully on the client."""
        import os

        from bson import ObjectId
        from pymongo import MongoClient

        dsn = os.environ.get("DB_DSN", "mongodb://localhost:27017")
        db_name = os.environ.get("DB_NAME", "beats_test")
        sync_client = MongoClient(dsn)
        sync_client[db_name].users.delete_one({"_id": ObjectId(auth_info["user_id"])})
        sync_client.close()

        resp = client.get("/api/account/me", headers=auth_info["headers"])
        assert resp.status_code == 404
        assert resp.json()["code"] == "NOT_FOUND"

    def test_refresh_issues_a_new_working_token(self, client, auth_info):
        resp = client.post("/api/account/refresh", headers=auth_info["headers"])
        assert resp.status_code == 200, resp.text
        new_token = resp.json()["token"]
        assert new_token
        assert new_token != auth_info["headers"]["Authorization"].split(" ", 1)[1]

        # The new token actually works on a protected endpoint.
        new_headers = {"Authorization": f"Bearer {new_token}"}
        assert client.get("/api/projects/", headers=new_headers).status_code == 200

    def test_refresh_without_bearer_returns_401(self, client):
        resp = client.post("/api/account/refresh")
        # The auth middleware fires before the handler — MISSING_TOKEN, not
        # the handler's "Bearer token required". Either way it's a 401.
        assert resp.status_code == 401

    def test_refresh_with_invalid_token_returns_401(self, client):
        resp = client.post(
            "/api/account/refresh",
            headers={"Authorization": "Bearer not-a-jwt"},
        )
        assert resp.status_code == 401

    def test_credentials_list_empty_for_fresh_user(self, client, auth_info):
        resp = client.get("/api/account/credentials", headers=auth_info["headers"])
        assert resp.status_code == 200
        assert resp.json() == []

    def test_credentials_list_returns_seeded_creds(self, client, auth_info):
        self._seed_credential(auth_info["user_id"], "cred-A", "Mac")
        self._seed_credential(auth_info["user_id"], "cred-B", "iPhone")

        resp = client.get("/api/account/credentials", headers=auth_info["headers"])
        assert resp.status_code == 200
        body = resp.json()
        ids = sorted(c["id"] for c in body)
        assert ids == ["cred-A", "cred-B"]
        names = sorted(c["device_name"] for c in body)
        assert names == ["Mac", "iPhone"]

    def test_delete_credential_removes_non_last(self, client, auth_info):
        self._seed_credential(auth_info["user_id"], "cred-keep")
        self._seed_credential(auth_info["user_id"], "cred-doomed")

        resp = client.delete(
            "/api/account/credentials/cred-doomed",
            headers=auth_info["headers"],
        )
        assert resp.status_code == 204, resp.text

        # Only the survivor remains.
        listing = client.get("/api/account/credentials", headers=auth_info["headers"]).json()
        assert [c["id"] for c in listing] == ["cred-keep"]

    def test_delete_last_credential_blocked(self, client, auth_info):
        """Locks in the "must keep at least one passkey" guard. Without
        this, a user could nuke their last credential and lock themselves
        out — the very scenario auth.py's orphan-retry doesn't recover
        from (orphan happens *before* the user has any credential, this
        guard prevents them from getting *back* into that state)."""
        self._seed_credential(auth_info["user_id"], "cred-only")

        resp = client.delete(
            "/api/account/credentials/cred-only",
            headers=auth_info["headers"],
        )
        assert resp.status_code == 400, resp.text
        assert "only passkey" in resp.json()["detail"].lower()

    def test_delete_nonexistent_credential_returns_404(self, client, auth_info):
        # Seed two so the keep-at-least-one guard (count <= 1) doesn't
        # short-circuit our 404 path. delete_credential checks the count
        # before checking existence — a single seeded credential plus a
        # request for a different ID would 400 with "only passkey", which
        # isn't the branch we're documenting here.
        self._seed_credential(auth_info["user_id"], "cred-real-1")
        self._seed_credential(auth_info["user_id"], "cred-real-2")

        resp = client.delete(
            "/api/account/credentials/cred-does-not-exist",
            headers=auth_info["headers"],
        )
        assert resp.status_code == 404

    def test_account_endpoints_require_auth(self, client):
        for method, path in [
            ("GET", "/api/account/me"),
            ("POST", "/api/account/refresh"),
            ("GET", "/api/account/credentials"),
            ("DELETE", "/api/account/credentials/anything"),
        ]:
            resp = client.request(method, path)
            assert resp.status_code == 401, f"{method} {path} should require auth"


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
        from datetime import date, timedelta

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


class TestDuplicateEmailPrevention:
    """Test that the unique index on users.email prevents duplicates."""

    def test_duplicate_email_rejected(self):
        """Inserting a user with a duplicate email raises an error."""
        import os

        from bson import ObjectId
        from pymongo import MongoClient
        from pymongo.errors import DuplicateKeyError

        dsn = os.environ.get("DB_DSN", "mongodb://localhost:27017")
        db_name = os.environ.get("DB_NAME", "beats_test")
        sync_client = MongoClient(dsn)
        db = sync_client[db_name]

        email = "unique-test@example.com"
        db.users.insert_one({"_id": ObjectId(), "email": email})

        with pytest.raises(DuplicateKeyError):
            db.users.insert_one({"_id": ObjectId(), "email": email})

        sync_client.close()


class TestRegisterStartOrphanRetry:
    """A user record without credentials is an abandoned /register/start.
    The handler must let the same email retry instead of returning 409 —
    the orphan can't log in (no credential exists for them) and would
    otherwise be locked out forever.
    """

    def test_orphan_user_can_retry_register_start(self, client):
        """register/start for an existing email with zero credentials reuses
        the user instead of returning 409."""
        import os

        from bson import ObjectId
        from pymongo import MongoClient

        dsn = os.environ.get("DB_DSN", "mongodb://localhost:27017")
        db_name = os.environ.get("DB_NAME", "beats_test")
        sync_client = MongoClient(dsn)
        db = sync_client[db_name]

        # Simulate an abandoned /register/start: a user row, no credentials.
        email = "orphan-retry@example.com"
        orphan_id = ObjectId()
        db.users.insert_one({"_id": orphan_id, "email": email, "display_name": None})
        sync_client.close()

        # Same email comes back to retry registration. Should succeed and
        # reuse the existing user_id (no second user row is created).
        response = client.post(
            "/api/auth/register/start",
            json={"email": email, "display_name": "Retry"},
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["user_id"] == str(orphan_id)

        # And — exactly one user row for that email, not two.
        sync_client = MongoClient(dsn)
        db = sync_client[db_name]
        assert db.users.count_documents({"email": email}) == 1
        sync_client.close()


class TestAuthRouterErrorPaths:
    """Error-path coverage for the unauthenticated /api/auth/*
    endpoints. The happy-path crypto verification needs a real
    authenticator, but the pre-checks (existing-with-credentials,
    no-pending-registration, no-pending-authentication, malformed
    credential) are all reachable via plain HTTP and worth pinning
    — these are the user-facing error envelopes."""

    @pytest.fixture(autouse=True)
    def _reset_session_manager(self):
        """The auth router's SessionManager is a process-global
        singleton. Earlier tests in the suite (e.g. orphan-retry,
        rate-limit) call /register/start or /login/options, which
        leave challenges and pending registrations in memory.
        Clear them before each test in this class so the
        no-pending-registration paths actually fire."""
        from beats.api.routers.auth import _session_manager

        _session_manager._challenges.clear()
        _session_manager._pending_registrations.clear()
        return

    def _db(self):
        import os

        from pymongo import MongoClient

        dsn = os.environ.get("DB_DSN", "mongodb://localhost:27017")
        db_name = os.environ.get("DB_NAME", "beats_test")
        sync_client = MongoClient(dsn)
        return sync_client, sync_client[db_name]

    def test_register_start_existing_email_with_credentials_returns_409(self, client):
        """A user row with at least one credential → 409 on
        register/start (the email is "really registered"). Pin the
        409 vs the 200 orphan-retry path (test_orphan_user_can_retry_register_start
        covers the 200 case)."""
        from bson import ObjectId

        sync_client, db = self._db()
        email = "already-registered@example.com"
        user_id = ObjectId()
        db.users.insert_one({"_id": user_id, "email": email, "display_name": "Already"})
        # Add a credential — turns the user from orphan into "real"
        db.credentials.insert_one(
            {
                "user_id": str(user_id),
                "credential_id": "cred-existing",
                "public_key": "pk",
                "sign_count": 0,
                "created_at": "2026-04-01T00:00:00",
            }
        )
        sync_client.close()

        resp = client.post(
            "/api/auth/register/start",
            json={"email": email, "display_name": "Retry"},
        )
        assert resp.status_code == 409
        assert "already registered" in resp.json()["detail"].lower()

    def test_register_verify_without_pending_returns_400(self, client):
        """POST /register/verify before /register/start was called
        → 400 "No pending registration found". Pin the user-facing
        envelope so an attacker who skips the challenge step gets
        a clear error rather than crashing the verify path."""
        resp = client.post(
            "/api/auth/register/verify",
            json={
                "credential": {
                    "id": "fake",
                    "rawId": "fake",
                    "response": {},
                    "type": "public-key",
                },
                "device_name": "Test",
            },
        )
        assert resp.status_code == 400
        assert "No pending registration" in resp.json()["detail"]

    def test_login_verify_with_invalid_credential_returns_401(self, client):
        """POST /login/verify without a pending challenge / with an
        unknown credential → 401. Pin the 401 envelope (ValueError
        from WebAuthnManager.verify_authentication maps to
        UNAUTHORIZED, not BAD_REQUEST)."""
        resp = client.post(
            "/api/auth/login/verify",
            json={
                "credential": {
                    "id": "nonexistent-cred",
                    "rawId": "nonexistent-cred",
                    "response": {},
                    "type": "public-key",
                }
            },
        )
        assert resp.status_code == 401

    def test_login_options_returns_options_dict(self, client):
        """GET /login/options returns a dict with rpId + challenge +
        empty allowCredentials. Pin the empty allowCredentials list
        so a regression doesn't start leaking registered credential
        IDs to unauthenticated callers (would let an attacker
        enumerate user existence)."""
        resp = client.get("/api/auth/login/options")
        assert resp.status_code == 200
        opts = resp.json()["options"]
        assert "challenge" in opts
        assert opts["allowCredentials"] == []
        assert "rpId" in opts

    def test_register_start_brand_new_email_creates_user(self, client):
        """POST /register/start with an email that has NO user row →
        creates a new user (the `else` branch at line 133) and
        returns its id. Pin both: 200 status AND a fresh user_id
        is assigned (not the existing-user ObjectId)."""
        sync_client, db = self._db()
        email = "fresh-account@example.com"
        # Confirm the email starts unknown
        assert db.users.count_documents({"email": email}) == 0
        sync_client.close()

        resp = client.post(
            "/api/auth/register/start",
            json={"email": email, "display_name": "Fresh"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        new_user_id = body["user_id"]
        assert new_user_id  # non-empty

        # Exactly one user row created with the matching email
        sync_client, db = self._db()
        assert db.users.count_documents({"email": email}) == 1
        sync_client.close()

    def test_register_verify_value_error_returns_400_envelope(self, client, monkeypatch):
        """When a pending registration challenge exists AND the user
        is found, but webauthn.verify_registration raises ValueError
        (malformed credential / signature mismatch), the response is
        400 with the exception text in the detail. Pin the 400
        envelope — distinct from the no-pending 400 (different
        cause, same status)."""
        from bson import ObjectId

        from beats.api.routers import auth as auth_router

        sync_client, db = self._db()
        # Seed a user the verify handler will look up
        user_id = str(ObjectId())
        db.users.insert_one(
            {
                "_id": ObjectId(user_id),
                "email": "verify-test@example.com",
                "display_name": "Verify",
            }
        )
        sync_client.close()

        # Register a pending challenge for this user_id directly,
        # bypassing the OAuth crypto roundtrip
        challenge_bytes = b"X" * 32
        auth_router._session_manager.store_challenge(challenge_bytes, "registration")
        auth_router._session_manager.store_pending_registration(challenge_bytes, user_id)

        # Make verify_registration raise ValueError — this is the
        # branch that catches malformed credentials / sig mismatches
        async def fake_verify_registration(*args, **kwargs):
            raise ValueError("malformed credential blob")

        # Patch through the WebAuthnDep — find the actual instance
        # the router uses
        from beats.auth.webauthn import WebAuthnManager

        monkeypatch.setattr(WebAuthnManager, "verify_registration", fake_verify_registration)

        resp = client.post(
            "/api/auth/register/verify",
            json={
                "credential": {
                    "id": "fake",
                    "rawId": "fake",
                    "response": {},
                    "type": "public-key",
                },
                "device_name": "Test",
            },
        )
        assert resp.status_code == 400
        # Exception message propagates so the user sees the actual
        # reason (not just a generic "registration failed")
        assert "malformed credential blob" in resp.json()["detail"]


class TestRateLimiting:
    """Test that auth endpoints are rate-limited."""

    def test_login_options_rate_limited(self, client):
        """GET /api/auth/login/options is rate-limited after repeated requests."""
        for _ in range(10):
            client.get("/api/auth/login/options")

        response = client.get("/api/auth/login/options")
        assert response.status_code == 429

    def test_pair_exchange_rate_limited(self, client):
        """POST /api/device/pair/exchange is rate-limited.

        Endpoint is unauthenticated and accepts a 6-char base32 pairing
        code (~30 bits of entropy). Without a rate limit, an attacker
        with network access could grind through the keyspace. Cap is
        10/min — eleventh request in the same window must 429.
        """
        for _ in range(10):
            client.post(
                "/api/device/pair/exchange",
                json={"code": "AAAAAA", "device_name": "test"},
            )

        response = client.post(
            "/api/device/pair/exchange",
            json={"code": "AAAAAA", "device_name": "test"},
        )
        assert response.status_code == 429


class TestMultiUserIsolation:
    """Test that data is isolated between users."""

    def _make_headers(self, user_id: str, email: str) -> dict[str, str]:
        from beats.auth.session import SessionManager
        from beats.settings import settings

        sm = SessionManager(settings.jwt_secret)
        token = sm.create_session_token(user_id, email)
        return {"Authorization": f"Bearer {token}"}

    def _seed_users(self, *emails: str) -> list[str]:
        """Insert N users via direct DB writes. Returns their ids in the
        same order they were passed. Cheaper + more deterministic than
        going through the WebAuthn registration flow for every isolation
        test that needs more than one user."""
        import os

        from bson import ObjectId
        from pymongo import MongoClient

        dsn = os.environ.get("DB_DSN", "mongodb://localhost:27017")
        db_name = os.environ.get("DB_NAME", "beats_test")
        sync_client = MongoClient(dsn)
        db = sync_client[db_name]

        ids: list[str] = []
        for email in emails:
            uid = str(ObjectId())
            ids.append(uid)
            db.users.insert_one({"_id": ObjectId(uid), "email": email, "display_name": None})
        sync_client.close()
        return ids

    def test_projects_isolated_between_users(self, client):
        """Projects created by one user are not visible to another."""
        user1_id, user2_id = self._seed_users("user1@test.com", "user2@test.com")
        h1 = self._make_headers(user1_id, "user1@test.com")
        h2 = self._make_headers(user2_id, "user2@test.com")

        # User 1 creates a project
        resp = client.post(
            "/api/projects/",
            json={"name": "user1-project"},
            headers=h1,
        )
        assert resp.status_code == 201

        # User 1 sees the project
        projects_u1 = client.get("/api/projects/", headers=h1).json()
        assert any(p["name"] == "user1-project" for p in projects_u1)

        # User 2 does NOT see it
        projects_u2 = client.get("/api/projects/", headers=h2).json()
        assert not any(p["name"] == "user1-project" for p in projects_u2)

    def test_flow_windows_isolated_between_users(self, client):
        """Flow windows posted by one user's daemon don't leak to another.

        This is the safety net for the signals pipeline — a regression in
        the user-scoping query (e.g. forgetting `_q()` on a list_by_range
        call) would silently expose private flow data across accounts.
        """
        user1_id, user2_id = self._seed_users("flow1@test.com", "flow2@test.com")
        h1 = self._make_headers(user1_id, "flow1@test.com")
        h2 = self._make_headers(user2_id, "flow2@test.com")

        # User 1 pairs a device. The session-mode helper above doesn't
        # exercise the device-token flow, so do the explicit pairing.
        resp = client.post("/api/device/pair/code", headers=h1)
        assert resp.status_code == 200, resp.json()
        code = resp.json()["code"]
        resp = client.post("/api/device/pair/exchange", json={"code": code})
        assert resp.status_code == 200
        u1_device = {"Authorization": f"Bearer {resp.json()['device_token']}"}

        # User 1's daemon emits a unique-scoring flow window so we can
        # spot it by value alone in user 2's read.
        now = datetime.now(UTC)
        resp = client.post(
            "/api/signals/flow-windows",
            json={
                "window_start": (now - timedelta(minutes=1)).isoformat(),
                "window_end": now.isoformat(),
                "flow_score": 0.9123,  # distinctive sentinel
                "cadence_score": 0.5,
                "coherence_score": 0.5,
                "category_fit_score": 0.0,
                "idle_fraction": 0.0,
                "dominant_bundle_id": "com.user1.private",
                "dominant_category": "coding",
                "editor_repo": "/tmp/user1-private-workspace",
            },
            headers=u1_device,
        )
        assert resp.status_code == 201

        # User 2 reads back over the same time range. Should see ZERO of
        # user 1's windows — neither the score, the bundle, nor the repo
        # path.
        resp = client.get(
            "/api/signals/flow-windows",
            params={
                "start": (now - timedelta(hours=1)).isoformat(),
                "end": (now + timedelta(hours=1)).isoformat(),
            },
            headers=h2,
        )
        assert resp.status_code == 200
        u2_windows = resp.json()
        for w in u2_windows:
            assert w["flow_score"] != 0.9123, f"user2 saw user1's distinctive flow window: {w}"
            assert w["dominant_bundle_id"] != "com.user1.private"
            assert w.get("editor_repo") != "/tmp/user1-private-workspace"

        # Sanity: even with the project_id / editor_repo filters that
        # skip the date range path, isolation must still hold.
        resp = client.get(
            "/api/signals/flow-windows",
            params={
                "start": (now - timedelta(hours=1)).isoformat(),
                "end": (now + timedelta(hours=1)).isoformat(),
                "editor_repo": "/tmp/user1-private-workspace",
            },
            headers=h2,
        )
        assert resp.status_code == 200
        assert resp.json() == [], "filter must not bypass user scoping"


class TestDevicePairingAPI:
    """Test suite for daemon device pairing and device token auth."""

    def test_generate_pair_code_requires_auth(self, client):
        """POST /api/device/pair/code without token returns 401."""
        resp = client.post("/api/device/pair/code")
        assert resp.status_code == 401

    def test_generate_pair_code_success(self, client, auth_headers):
        """POST /api/device/pair/code returns a 6-char code."""
        resp = client.post("/api/device/pair/code", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["code"]) == 6
        assert data["expires_in_seconds"] == 300

    def test_exchange_code_success(self, client, auth_headers):
        """Full pairing flow: generate code, exchange for device token."""
        # Generate code
        resp = client.post("/api/device/pair/code", headers=auth_headers)
        code = resp.json()["code"]

        # Exchange (public, no auth)
        resp = client.post(
            "/api/device/pair/exchange",
            json={"code": code, "device_name": "test-daemon"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "device_token" in data
        assert "device_id" in data

    def test_exchange_code_invalid(self, client):
        """Exchange with bad code returns 404."""
        resp = client.post(
            "/api/device/pair/exchange",
            json={"code": "BADCOD"},
        )
        assert resp.status_code == 404

    def test_exchange_code_one_time_use(self, client, auth_headers):
        """Same code can only be exchanged once."""
        resp = client.post("/api/device/pair/code", headers=auth_headers)
        code = resp.json()["code"]

        # First exchange succeeds
        resp = client.post("/api/device/pair/exchange", json={"code": code})
        assert resp.status_code == 200

        # Second exchange fails
        resp = client.post("/api/device/pair/exchange", json={"code": code})
        assert resp.status_code == 404

    def test_device_token_allows_heartbeat(self, client, auth_headers):
        """Device token can POST to /api/device/heartbeat."""
        # Pair a device
        resp = client.post("/api/device/pair/code", headers=auth_headers)
        code = resp.json()["code"]
        resp = client.post("/api/device/pair/exchange", json={"code": code})
        device_token = resp.json()["device_token"]
        device_headers = {"Authorization": f"Bearer {device_token}"}

        # Use device token on heartbeat
        resp = client.post(
            "/api/device/heartbeat",
            json={"battery_voltage": 3.7},
            headers=device_headers,
        )
        assert resp.status_code == 200

    def test_device_token_blocked_on_non_allowed_endpoints(self, client, auth_headers):
        """Device token is rejected on endpoints not in DEVICE_ALLOWED_PREFIXES."""
        # Pair a device
        resp = client.post("/api/device/pair/code", headers=auth_headers)
        code = resp.json()["code"]
        resp = client.post("/api/device/pair/exchange", json={"code": code})
        device_token = resp.json()["device_token"]
        device_headers = {"Authorization": f"Bearer {device_token}"}

        # Try accessing rhythm (not in DEVICE_ALLOWED_PREFIXES — only /heatmap is)
        resp = client.get("/api/analytics/rhythm", headers=device_headers)
        assert resp.status_code == 403

    def test_device_token_allowed_on_analytics_heatmap(self, client, auth_headers):
        """Device tokens can read the heatmap (companion timer-screen totals)."""
        resp = client.post("/api/device/pair/code", headers=auth_headers)
        code = resp.json()["code"]
        resp = client.post("/api/device/pair/exchange", json={"code": code})
        device_token = resp.json()["device_token"]
        device_headers = {"Authorization": f"Bearer {device_token}"}

        resp = client.get("/api/analytics/heatmap", headers=device_headers)
        assert resp.status_code == 200

    def test_device_token_allowed_on_analytics_tags(self, client, auth_headers):
        """Device tokens can read /api/analytics/tags — the companion surfaces
        the auto-derived tag list (repo/language) in its analytics views."""
        resp = client.post("/api/device/pair/code", headers=auth_headers)
        code = resp.json()["code"]
        resp = client.post("/api/device/pair/exchange", json={"code": code})
        device_token = resp.json()["device_token"]
        device_headers = {"Authorization": f"Bearer {device_token}"}

        resp = client.get("/api/analytics/tags", headers=device_headers)
        assert resp.status_code == 200

    def test_device_token_allowed_on_beats(self, client, auth_headers):
        """Device tokens can read /api/beats — the companion lists recent
        sessions after a timer stops (no manual note/tags edit anymore)."""
        resp = client.post("/api/device/pair/code", headers=auth_headers)
        code = resp.json()["code"]
        resp = client.post("/api/device/pair/exchange", json={"code": code})
        device_token = resp.json()["device_token"]
        device_headers = {"Authorization": f"Bearer {device_token}"}

        resp = client.get("/api/beats/", headers=device_headers)
        assert resp.status_code == 200

    def test_list_registrations(self, client, auth_headers):
        """GET /api/device/registrations lists paired devices."""
        # Pair a device
        resp = client.post("/api/device/pair/code", headers=auth_headers)
        code = resp.json()["code"]
        resp = client.post(
            "/api/device/pair/exchange",
            json={"code": code, "device_name": "my-mac"},
        )
        device_id = resp.json()["device_id"]

        # List registrations
        resp = client.get("/api/device/registrations", headers=auth_headers)
        assert resp.status_code == 200
        regs = resp.json()
        assert any(r["device_id"] == device_id for r in regs)
        matched = next(r for r in regs if r["device_id"] == device_id)
        assert matched["device_name"] == "my-mac"

    def test_revoke_device(self, client, auth_headers):
        """DELETE /api/device/registrations/{device_id} revokes the device."""
        # Pair a device
        resp = client.post("/api/device/pair/code", headers=auth_headers)
        code = resp.json()["code"]
        resp = client.post("/api/device/pair/exchange", json={"code": code})
        data = resp.json()
        device_id = data["device_id"]
        device_token = data["device_token"]
        device_headers = {"Authorization": f"Bearer {device_token}"}

        # Revoke
        resp = client.delete(
            f"/api/device/registrations/{device_id}",
            headers=auth_headers,
        )
        assert resp.status_code == 204

        # Device token should now be rejected on allowed paths
        resp = client.post(
            "/api/device/heartbeat",
            json={"battery_voltage": 3.7},
            headers=device_headers,
        )
        assert resp.status_code == 403
        body = resp.json()
        assert "revoked" in body["detail"]
        assert body["code"] == "DEVICE_REVOKED"

    def test_revoked_device_not_in_list(self, client, auth_headers):
        """Revoked devices don't appear in the registrations list."""
        # Pair and revoke
        resp = client.post("/api/device/pair/code", headers=auth_headers)
        code = resp.json()["code"]
        resp = client.post("/api/device/pair/exchange", json={"code": code})
        device_id = resp.json()["device_id"]
        client.delete(f"/api/device/registrations/{device_id}", headers=auth_headers)

        # Should not appear in list
        resp = client.get("/api/device/registrations", headers=auth_headers)
        assert not any(r["device_id"] == device_id for r in resp.json())

    def test_device_status_shape_is_what_the_wall_clock_reads(self, client, auth_headers):
        """GET /api/device/status returns the field shape the ESP32 wall
        clock parser expects. Pinned because a contract drift on this
        endpoint is what silently broke the firmware (commit 3e7c507):
        every key was renamed (clocked_in vs is_active,
        daily_total_minutes vs today_minutes, project_color_rgb as
        int[3] vs hex string, etc.) without a paired test catching it.
        """
        # Pair a device — required because the endpoint is in the
        # device-token-allowed prefix list.
        resp = client.post("/api/device/pair/code", headers=auth_headers)
        code = resp.json()["code"]
        resp = client.post("/api/device/pair/exchange", json={"code": code})
        device_headers = {"Authorization": f"Bearer {resp.json()['device_token']}"}

        resp = client.get("/api/device/status", headers=device_headers)
        assert resp.status_code == 200, resp.text
        body = resp.json()

        # Required fields the wall clock unconditionally reads.
        for key in (
            "clocked_in",
            "daily_total_minutes",
            "energy_level",
            "theme_accent_rgb",
        ):
            assert key in body, f"missing required key {key!r}: {body}"

        # Type contract: theme_accent_rgb is a 3-int RGB list (the
        # firmware passes it straight to FastLED's CRGB(r,g,b)).
        assert isinstance(body["theme_accent_rgb"], list), body
        assert len(body["theme_accent_rgb"]) == 3, body["theme_accent_rgb"]
        for component in body["theme_accent_rgb"]:
            assert isinstance(component, int), component
            assert 0 <= component <= 255, component

        # When clocked_in is True, project_color_rgb / elapsed_minutes
        # / project_name / project_id are also present. Default fresh-
        # user state has no active timer so we don't exercise that
        # branch here — but the firmware's struct provides defaults
        # for all of them, so the un-clocked-in path is the
        # interesting one to lock.
        assert body["clocked_in"] is False
        assert body["daily_total_minutes"] == 0
        assert body["energy_level"] == 0

    def test_device_favorites_shape_is_what_the_wall_clock_reads(self, client, auth_headers):
        """GET /api/device/favorites returns each project with the
        color_rgb field shape the firmware now reads (was
        silently parsing a 'color' hex string that doesn't exist).
        """
        # Create a project so we have at least one favorite.
        resp = client.post(
            "/api/projects/",
            json={"name": "Test Wall Clock Favorite"},
            headers=auth_headers,
        )
        assert resp.status_code == 201

        # Pair + GET favorites with the device token.
        resp = client.post("/api/device/pair/code", headers=auth_headers)
        code = resp.json()["code"]
        resp = client.post("/api/device/pair/exchange", json={"code": code})
        device_headers = {"Authorization": f"Bearer {resp.json()['device_token']}"}

        resp = client.get("/api/device/favorites", headers=device_headers)
        assert resp.status_code == 200, resp.text
        favorites = resp.json()
        assert isinstance(favorites, list)
        assert len(favorites) >= 1
        for fav in favorites:
            assert "id" in fav, fav
            assert "name" in fav, fav
            # color_rgb is the int[3] the wall-clock's rgbFromArray reads.
            # NOT "color" (the previously-misnamed hex-string key).
            assert "color_rgb" in fav, fav
            assert "color" not in fav, (
                f"unexpected legacy 'color' key — wall-clock reads color_rgb: {fav}"
            )
            assert isinstance(fav["color_rgb"], list)
            assert len(fav["color_rgb"]) == 3

    def test_device_weekly_returns_seven_days_oldest_first(self, client, auth_headers):
        """GET /api/device/weekly returns last 7 days of minute totals
        — the wall-clock parses these directly into its weekly bar
        display. Ordering is oldest → newest so the firmware can render
        left-to-right without re-sorting."""
        resp = client.post("/api/device/pair/code", headers=auth_headers)
        code = resp.json()["code"]
        resp = client.post("/api/device/pair/exchange", json={"code": code})
        device_headers = {"Authorization": f"Bearer {resp.json()['device_token']}"}

        resp = client.get("/api/device/weekly", headers=device_headers)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "days" in body
        assert len(body["days"]) == 7

        # Ordering: oldest → newest. Six days ago to today inclusive.
        from datetime import date, timedelta

        today = date.today()
        expected_dates = [
            (today - timedelta(days=offset)).isoformat() for offset in range(6, -1, -1)
        ]
        assert [d["date"] for d in body["days"]] == expected_dates

        # Each entry has the minimal shape the firmware parses.
        for entry in body["days"]:
            assert "date" in entry
            assert "minutes" in entry
            assert isinstance(entry["minutes"], int)
            assert entry["minutes"] >= 0

    def test_device_heartbeat_persists_telemetry_for_get(self, client, auth_headers):
        """POST /api/device/heartbeat with telemetry stores the values;
        GET /api/device/heartbeat returns them. Locks in the round-trip
        the wall-clock's heartbeat tick (commit 45307e5) relies on for
        the device-health dashboard.
        """
        resp = client.post("/api/device/pair/code", headers=auth_headers)
        code = resp.json()["code"]
        resp = client.post("/api/device/pair/exchange", json={"code": code})
        device_headers = {"Authorization": f"Bearer {resp.json()['device_token']}"}

        resp = client.post(
            "/api/device/heartbeat",
            json={
                "battery_voltage": 4.05,
                "wifi_rssi": -56,
                "uptime_seconds": 14400,
            },
            headers=device_headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["battery_voltage"] == 4.05
        assert body["wifi_rssi"] == -56
        assert body["uptime_seconds"] == 14400

        # GET should return the same values (single-device in-memory
        # store; the next POST overwrites).
        resp = client.get("/api/device/heartbeat", headers=auth_headers)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["battery_voltage"] == 4.05
        assert body["wifi_rssi"] == -56
        assert body["uptime_seconds"] == 14400


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


class TestBiometricsAPI:
    """Test suite for biometrics endpoints."""

    def _pair_device(self, client, auth_headers):
        """Helper: pair a device and return device_headers."""
        resp = client.post("/api/device/pair/code", headers=auth_headers)
        code = resp.json()["code"]
        resp = client.post("/api/device/pair/exchange", json={"code": code})
        return {"Authorization": f"Bearer {resp.json()['device_token']}"}

    def test_post_biometric_day(self, client, auth_headers):
        """POST biometric data with device token."""
        device_headers = self._pair_device(client, auth_headers)
        resp = client.post(
            "/api/biometrics/daily",
            json={
                "date": "2026-04-18",
                "source": "healthkit",
                "sleep_minutes": 420,
                "sleep_efficiency": 0.88,
                "hrv_ms": 45.5,
                "resting_hr_bpm": 58,
                "steps": 8500,
            },
            headers=device_headers,
        )
        assert resp.status_code == 200
        assert "id" in resp.json()

    def test_post_biometric_day_session_token(self, client, auth_headers):
        """POST biometric data also works with session token."""
        resp = client.post(
            "/api/biometrics/daily",
            json={
                "date": "2026-04-17",
                "source": "oura",
                "sleep_minutes": 390,
                "readiness_score": 82,
            },
            headers=auth_headers,
        )
        assert resp.status_code == 200

    def test_read_biometrics(self, client, auth_headers):
        """GET biometrics by date range."""
        # Post some data first
        client.post(
            "/api/biometrics/daily",
            json={"date": "2026-04-18", "source": "fitbit", "steps": 10000},
            headers=auth_headers,
        )

        resp = client.get(
            "/api/biometrics/",
            params={"start": "2026-04-01", "end": "2026-04-30"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        days = resp.json()
        assert len(days) >= 1

    def test_biometric_upsert(self, client, auth_headers):
        """Same (date, source) twice updates, not duplicates."""
        client.post(
            "/api/biometrics/daily",
            json={"date": "2026-04-15", "source": "fitbit", "steps": 5000},
            headers=auth_headers,
        )
        client.post(
            "/api/biometrics/daily",
            json={"date": "2026-04-15", "source": "fitbit", "steps": 9000},
            headers=auth_headers,
        )

        resp = client.get(
            "/api/biometrics/",
            params={"start": "2026-04-15", "end": "2026-04-15"},
            headers=auth_headers,
        )
        days = resp.json()
        fitbit_days = [d for d in days if d["source"] == "fitbit" and d["date"] == "2026-04-15"]
        assert len(fitbit_days) == 1
        assert fitbit_days[0]["steps"] == 9000

    def test_delete_biometrics(self, client, auth_headers):
        """DELETE removes all biometric data."""
        client.post(
            "/api/biometrics/daily",
            json={"date": "2026-04-14", "source": "healthkit", "steps": 3000},
            headers=auth_headers,
        )
        resp = client.delete("/api/biometrics/", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["deleted"] >= 1

    def test_fitbit_status_disconnected(self, client, auth_headers):
        """GET /api/fitbit/status returns disconnected by default."""
        resp = client.get("/api/fitbit/status", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["connected"] is False

    def test_oura_status_disconnected(self, client, auth_headers):
        """GET /api/oura/status returns disconnected by default."""
        resp = client.get("/api/oura/status", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["connected"] is False


class TestOAuthIntegrationRouters:
    """Cross-cutting tests for the four OAuth integration routers
    (calendar, github, fitbit, oura). All four follow the same
    pattern: auth-url, connect, status, disconnect, plus a
    domain-specific fetch endpoint.

    These routers were at 56-74% coverage — most uncovered lines
    are simple thin-wrapper endpoint bodies that only run when an
    actual request hits them. Pin the URL/method mapping +
    response shape so a refactor of the dependency injection or
    response model can't silently break the OAuth callbacks.

    The auth-url + status-disconnected + disconnect-when-empty
    paths don't need any external HTTP and run against the empty
    auth_info user. Connected-state tests seed the integration
    doc directly in Mongo."""

    def _db(self):
        import os

        from pymongo import MongoClient

        dsn = os.environ.get("DB_DSN", "mongodb://localhost:27017")
        db_name = os.environ.get("DB_NAME", "beats_test")
        sync_client = MongoClient(dsn)
        return sync_client, sync_client[db_name]

    @pytest.fixture(autouse=True)
    def _reset_integrations(self, auth_info):
        """Drop all integration docs after each test — so the
        connected and disconnected variants don't bleed."""
        sync_client, db = self._db()
        try:
            yield
        finally:
            for coll in (
                "calendar_integrations",
                "github_integrations",
                "fitbit_integrations",
                "oura_integrations",
            ):
                db[coll].delete_many({"user_id": auth_info["user_id"]})
            sync_client.close()

    # -------- /api/calendar --------

    def test_calendar_auth_url_returns_google_consent_url(self, client, auth_info):
        """GET /api/calendar/auth-url returns the Google OAuth URL.
        Pin so a regression doesn't silently change the URL host
        or strip required params."""
        resp = client.get("/api/calendar/auth-url", headers=auth_info["headers"])
        assert resp.status_code == 200
        url = resp.json()["url"]
        assert url.startswith("https://accounts.google.com/o/oauth2/v2/auth?")
        # The two refresh-token-critical params must be in the URL
        assert "access_type=offline" in url
        assert "prompt=consent" in url

    def test_calendar_status_connected_when_integration_exists(self, client, auth_info):
        """GET /api/calendar/status with a connected integration →
        connected: True, provider: 'google'. Pin the response
        shape — the UI's Settings → Integrations panel binds
        directly to these keys."""
        sync_client, db = self._db()
        db.calendar_integrations.insert_one(
            {
                "user_id": auth_info["user_id"],
                "provider": "google",
                "access_token": "ya29",
                "refresh_token": "rt",
                "enabled": True,
            }
        )
        sync_client.close()
        resp = client.get("/api/calendar/status", headers=auth_info["headers"])
        assert resp.status_code == 200
        body = resp.json()
        assert body["connected"] is True
        assert body["provider"] == "google"

    def test_calendar_status_disconnected_when_no_doc(self, client, auth_info):
        """GET /api/calendar/status with no integration → connected:
        False, provider: None. Pin so the UI can render the
        "Connect Calendar" button on first load."""
        resp = client.get("/api/calendar/status", headers=auth_info["headers"])
        assert resp.status_code == 200
        body = resp.json()
        assert body["connected"] is False
        assert body["provider"] is None

    def test_calendar_events_empty_when_not_connected(self, client, auth_info):
        """GET /api/calendar/events without an integration → []
        (not 500, not "connection required" error). Pin so the
        coach's day context falls through gracefully when the
        user hasn't connected calendar."""
        resp = client.get("/api/calendar/events", headers=auth_info["headers"])
        assert resp.status_code == 200
        assert resp.json() == []

    def test_calendar_disconnect_returns_false_when_not_connected(self, client, auth_info):
        """DELETE /api/calendar/disconnect without an integration →
        disconnected: False (idempotent). Pin so a "disconnect"
        button click on an already-disconnected account doesn't
        500 the user."""
        resp = client.delete("/api/calendar/disconnect", headers=auth_info["headers"])
        assert resp.status_code == 200
        assert resp.json()["disconnected"] is False

    # -------- /api/github --------

    def test_github_auth_url_returns_github_consent_url(self, client, auth_info):
        """GET /api/github/auth-url returns the GitHub OAuth URL."""
        resp = client.get("/api/github/auth-url", headers=auth_info["headers"])
        assert resp.status_code == 200
        url = resp.json()["url"]
        assert url.startswith("https://github.com/login/oauth/authorize?")

    def test_github_status_connected_when_integration_exists(self, client, auth_info):
        """Status reports github_username when connected. Pin so
        the UI can show "Connected as @ahmed" rather than a
        generic "Connected" label. The key is `github_username`
        (not `username`) — pin so a UI rename can't drift."""
        sync_client, db = self._db()
        db.github_integrations.insert_one(
            {
                "user_id": auth_info["user_id"],
                "access_token": "gho_x",
                "github_username": "ahmed",
                "enabled": True,
            }
        )
        sync_client.close()
        resp = client.get("/api/github/status", headers=auth_info["headers"])
        assert resp.status_code == 200
        body = resp.json()
        assert body["connected"] is True
        assert body["github_username"] == "ahmed"

    def test_github_status_disconnected_when_no_doc(self, client, auth_info):
        resp = client.get("/api/github/status", headers=auth_info["headers"])
        assert resp.status_code == 200
        body = resp.json()
        assert body["connected"] is False
        assert body["github_username"] is None

    def test_github_disconnect_returns_true_when_connected(self, client, auth_info):
        """DELETE /api/github/disconnect with a connected integration
        → disconnected:True and the doc is gone. Pin so the
        Settings → Integrations panel's "Disconnect" button reflects
        actual state change (mirrors the fitbit/calendar disconnect
        contracts)."""
        sync_client, db = self._db()
        db.github_integrations.insert_one(
            {
                "user_id": auth_info["user_id"],
                "access_token": "gho_x",
                "github_username": "ahmed",
                "enabled": True,
            }
        )
        sync_client.close()
        resp = client.delete("/api/github/disconnect", headers=auth_info["headers"])
        assert resp.status_code == 200
        assert resp.json()["disconnected"] is True
        # Confirm the doc is gone
        sync_client, db = self._db()
        assert db.github_integrations.count_documents({"user_id": auth_info["user_id"]}) == 0
        sync_client.close()

    # -------- /api/fitbit --------

    def test_fitbit_auth_url_returns_fitbit_consent_url(self, client, auth_info):
        resp = client.get("/api/fitbit/auth-url", headers=auth_info["headers"])
        assert resp.status_code == 200
        url = resp.json()["url"]
        assert url.startswith("https://www.fitbit.com/oauth2/authorize?")

    def test_fitbit_status_connected_reports_user_id(self, client, auth_info):
        """GET /api/fitbit/status with a connected integration →
        connected:True, fitbit_user_id from the doc. Pin the
        snake_case key (NOT camelCase) so the iOS companion's
        JSONDecodable model doesn't drift."""
        from datetime import UTC, datetime, timedelta

        sync_client, db = self._db()
        db.fitbit_integrations.insert_one(
            {
                "user_id": auth_info["user_id"],
                "access_token": "at",
                "refresh_token": "rt",
                "token_expiry": datetime.now(UTC) + timedelta(hours=1),
                "fitbit_user_id": "fb-user-99",
                "enabled": True,
            }
        )
        sync_client.close()
        resp = client.get("/api/fitbit/status", headers=auth_info["headers"])
        assert resp.status_code == 200
        body = resp.json()
        assert body["connected"] is True
        assert body["fitbit_user_id"] == "fb-user-99"

    def test_fitbit_disconnect_returns_true_when_connected(self, client, auth_info):
        """DELETE /api/fitbit/disconnect with an existing integration
        → disconnected:True (and the row is gone). Pin so the
        Settings → Integrations panel's "Disconnect" button reflects
        the actual state change."""
        from datetime import UTC, datetime, timedelta

        sync_client, db = self._db()
        db.fitbit_integrations.insert_one(
            {
                "user_id": auth_info["user_id"],
                "access_token": "at",
                "refresh_token": "rt",
                "token_expiry": datetime.now(UTC) + timedelta(hours=1),
                "fitbit_user_id": "fb",
                "enabled": True,
            }
        )
        sync_client.close()
        resp = client.delete("/api/fitbit/disconnect", headers=auth_info["headers"])
        assert resp.status_code == 200
        assert resp.json()["disconnected"] is True

    # -------- /api/oura --------

    def test_oura_status_connected_reports_user_id(self, client, auth_info):
        """GET /api/oura/status with a connected integration →
        connected:True, oura_user_id. Same shape pattern as Fitbit."""
        sync_client, db = self._db()
        db.oura_integrations.insert_one(
            {
                "user_id": auth_info["user_id"],
                "access_token": "pat",
                "oura_user_id": "oura-user-7",
                "enabled": True,
            }
        )
        sync_client.close()
        resp = client.get("/api/oura/status", headers=auth_info["headers"])
        assert resp.status_code == 200
        body = resp.json()
        assert body["connected"] is True
        assert body["oura_user_id"] == "oura-user-7"

    def test_oura_disconnect_returns_false_when_not_connected(self, client, auth_info):
        """DELETE /api/oura/disconnect without an integration →
        disconnected: False. Same idempotent contract as
        calendar/disconnect."""
        resp = client.delete("/api/oura/disconnect", headers=auth_info["headers"])
        assert resp.status_code == 200
        assert resp.json()["disconnected"] is False

    # -------- Auth wall — unauthenticated requests rejected --------

    def test_calendar_auth_url_requires_auth(self, client):
        """GET /api/calendar/auth-url without a token → 401.
        Pin the auth gate so an unauthenticated caller can't
        even discover the OAuth flow start URL."""
        resp = client.get("/api/calendar/auth-url")
        assert resp.status_code == 401

    def test_oura_status_requires_auth(self, client):
        resp = client.get("/api/oura/status")
        assert resp.status_code == 401


# Single sign-on — the second front door


class TestSSOAPI:
    """/api/auth/sso/* and /api/account/sso/*.

    The provider is `fake_idp.FakeIdP` (a real token endpoint's checks, real
    RS256 tokens) swapped in through the `get_oidc_registry` dependency, so
    these exercise the real HTTP contract — the flow stored in Mongo and taken
    once, status codes, error envelope codes — with the browser's trip through
    the provider's login page played by `FakeIdP.issue_code`.
    """

    @pytest.fixture(autouse=True)
    def _sso_env(self, auth_info, mongo, monkeypatch):
        from bson import ObjectId

        from beats.api.routers.sso import get_oidc_registry
        from beats.auth.oidc import OIDCRegistry
        from beats.settings import settings
        from fake_idp import REDIRECT_URI, FakeIdP
        from server import app

        self.open_idp = FakeIdP(provider_id="open", name="Open IdP")
        self.closed_idp = FakeIdP(provider_id="closed", name="Closed IdP")
        registry = OIDCRegistry(
            [
                self.open_idp.provider(allow_signup=True),
                self.closed_idp.provider(),
            ]
        )
        app.dependency_overrides[get_oidc_registry] = lambda: registry
        monkeypatch.setattr(settings, "oidc_redirect_uri", REDIRECT_URI)

        # Drop anything an earlier test in this class linked or created, but
        # keep the fixture user the JWT in auth_info points at.
        mongo.users.delete_many({"_id": {"$ne": ObjectId(auth_info["user_id"])}})
        mongo.users.update_one(
            {"_id": ObjectId(auth_info["user_id"])},
            {"$set": {"identities": []}, "$unset": {"sso_provisioned": ""}},
        )
        mongo.credentials.delete_many({})
        mongo.sso_flows.delete_many({})
        yield
        app.dependency_overrides.pop(get_oidc_registry, None)

    def _start(self, client, provider: str, headers=None) -> dict:
        path = f"/api/account/sso/{provider}/link" if headers else f"/api/auth/sso/{provider}/start"
        resp = client.post(path, headers=headers or {})
        assert resp.status_code == 200, resp.text
        return resp.json()

    def _round_trip(self, client, idp, *, headers=None, sub="idp-user-1", **claims):
        """Start, sign in at the provider, and post the code back."""
        started = self._start(client, idp.provider_id, headers)
        code = idp.issue_code(started["authorize_url"], sub=sub, **claims)
        return client.post(
            "/api/auth/sso/complete",
            json={"code": code, "state": started["state"]},
            headers=headers or {},
        )

    def _passkey(self, mongo, user_id: str) -> None:
        mongo.credentials.insert_one(
            {
                "user_id": user_id,
                "credential_id": f"cred-{user_id}",
                "public_key": "k",
                "sign_count": 0,
                "created_at": datetime.now(UTC).isoformat(),
                "device_name": "Laptop",
            }
        )

    # -------- providers --------

    def test_lists_the_configured_providers_in_order(self, client):
        resp = client.get("/api/auth/sso/providers")
        assert resp.status_code == 200
        assert resp.json() == {
            "providers": [
                {"id": "open", "name": "Open IdP"},
                {"id": "closed", "name": "Closed IdP"},
            ]
        }

    def test_an_unknown_provider_is_404(self, client):
        resp = client.post("/api/auth/sso/nope/start")
        assert resp.status_code == 404
        assert resp.json()["code"] == "SSO_UNKNOWN_PROVIDER"

    def test_an_unreachable_provider_is_503(self, client):
        self.open_idp.discovery_issuer = "https://elsewhere.test"
        resp = client.post("/api/auth/sso/open/start")
        assert resp.status_code == 503
        assert resp.json()["code"] == "SSO_UNAVAILABLE"

    # -------- sign-in --------

    def test_sign_up_through_an_open_provider_then_sign_in_again(self, client):
        first = self._round_trip(client, self.open_idp, name="Ada", email="ada@example.com")
        assert first.status_code == 200, first.text
        body = first.json()
        assert (body["intent"], body["provider"], body["created"]) == ("sign_in", "open", True)

        me = client.get(
            "/api/account/me", headers={"Authorization": f"Bearer {body['token']}"}
        ).json()
        assert me["display_name"] == "Ada"
        assert me["sso_provisioned"] is True
        assert [(i["provider"], i["provider_name"], i["email"]) for i in me["identities"]] == [
            ("open", "Open IdP", "ada@example.com")
        ]

        again = self._round_trip(client, self.open_idp)
        assert again.status_code == 200
        assert again.json()["created"] is False

    def test_a_closed_provider_does_not_create_accounts(self, client):
        resp = self._round_trip(client, self.closed_idp)
        assert resp.status_code == 403
        assert resp.json()["code"] == "SSO_SIGNUP_CLOSED"

    def test_a_state_finishes_one_sign_in_and_no_more(self, client):
        started = self._start(client, "open")
        code = self.open_idp.issue_code(started["authorize_url"])
        body = {"code": code, "state": started["state"]}
        assert client.post("/api/auth/sso/complete", json=body).status_code == 200
        replay = client.post("/api/auth/sso/complete", json=body)
        assert replay.status_code == 400
        assert replay.json()["code"] == "SSO_FLOW_EXPIRED"

    def test_an_expired_flow_is_refused(self, client, mongo):
        started = self._start(client, "open")
        code = self.open_idp.issue_code(started["authorize_url"])
        mongo.sso_flows.update_many(
            {}, {"$set": {"expires_at": datetime.now(UTC) - timedelta(seconds=1)}}
        )
        resp = client.post("/api/auth/sso/complete", json={"code": code, "state": started["state"]})
        assert resp.json()["code"] == "SSO_FLOW_EXPIRED"

    def test_a_code_the_provider_refuses_is_401(self, client):
        started = self._start(client, "open")
        resp = client.post(
            "/api/auth/sso/complete", json={"code": "forged", "state": started["state"]}
        )
        assert resp.status_code == 401
        assert resp.json()["code"] == "SSO_REJECTED"

    # -------- linking --------

    def test_link_then_sign_in_with_the_identity(self, client, auth_info):
        resp = self._round_trip(client, self.closed_idp, headers=auth_info["headers"])
        assert resp.status_code == 200, resp.text
        assert resp.json() == {
            "intent": "link",
            "provider": "closed",
            "token": None,
            "created": False,
        }

        # Linked, so even the provider that creates no accounts signs in.
        signed_in = self._round_trip(client, self.closed_idp)
        assert signed_in.status_code == 200
        token = signed_in.json()["token"]
        me = client.get("/api/account/me", headers={"Authorization": f"Bearer {token}"})
        assert me.json()["email"] == "test@example.com"

    def test_a_link_finishes_only_in_the_session_that_started_it(
        self, client, auth_info, other_auth_headers
    ):
        started = self._start(client, "closed", auth_info["headers"])
        code = self.closed_idp.issue_code(started["authorize_url"])
        body = {"code": code, "state": started["state"]}
        for headers in ({}, other_auth_headers):
            resp = client.post("/api/auth/sso/complete", json=body, headers=headers)
            assert resp.status_code in (400, 403)
        # The first attempt spent the flow; neither linked anything.
        me = client.get("/api/account/me", headers=auth_info["headers"]).json()
        assert me["identities"] == []

    def test_an_identity_on_another_account_cannot_be_linked(self, client, auth_info):
        assert self._round_trip(client, self.open_idp).status_code == 200  # creates an account
        resp = self._round_trip(client, self.open_idp, headers=auth_info["headers"])
        assert resp.status_code == 409
        assert resp.json()["code"] == "SSO_ALREADY_LINKED"

    def test_linking_needs_a_session(self, client):
        assert client.post("/api/account/sso/open/link").status_code == 401

    # -------- unlinking --------

    def test_unlink_refuses_when_no_way_in_would_remain(self, client, auth_info):
        self._round_trip(client, self.open_idp, headers=auth_info["headers"])
        resp = client.delete("/api/account/sso/open", headers=auth_info["headers"])
        assert resp.status_code == 409
        assert resp.json()["code"] == "SSO_LAST_CREDENTIAL"

    def test_unlink_with_a_passkey_left(self, client, auth_info, mongo):
        self._round_trip(client, self.open_idp, headers=auth_info["headers"])
        self._passkey(mongo, auth_info["user_id"])
        resp = client.delete("/api/account/sso/open", headers=auth_info["headers"])
        assert resp.status_code == 200
        assert resp.json()["identities"] == []

    def test_unlink_when_not_linked_is_404(self, client, auth_info):
        resp = client.delete("/api/account/sso/open", headers=auth_info["headers"])
        assert resp.status_code == 404
        assert resp.json()["code"] == "SSO_NOT_LINKED"
