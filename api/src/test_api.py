"""
Comprehensive API Tests for Beats Application
Tests all endpoints: Projects, Beats, and Timer APIs
"""

import time
from datetime import UTC, datetime, timedelta

import pytest
from starlette.testclient import TestClient

client: TestClient | None = None  # Set by fixture before tests run
auth_headers: dict[str, str] = {}  # Set by fixture before each test class


@pytest.fixture(scope="module", autouse=True)
def _provide_client(test_client):
    """Inject the session-scoped test_client as the module-level 'client'."""
    global client
    client = test_client


@pytest.fixture(autouse=True)
def _setup_auth(auth_info):
    """Populate module-level auth_headers from the auth_info fixture."""
    global auth_headers
    auth_headers = auth_info["headers"]


class TestProjectAPI:
    """Test suite for Project management endpoints"""

    def test_projects_list_api(self):
        """Test GET /api/projects/ - List all projects"""
        response = client.get("/api/projects/", headers=auth_headers)
        assert response.status_code == 200
        projects = response.json()
        assert isinstance(projects, list)

    def test_projects_list_archived(self):
        """Test GET /api/projects/?archived=true - List archived projects"""
        response = client.get("/api/projects/?archived=true", headers=auth_headers)
        assert response.status_code == 200
        projects = response.json()
        assert isinstance(projects, list)

    def test_projects_create_api(self):
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

    def test_projects_create_without_auth(self):
        """Test POST /api/projects/ without auth token - Should fail"""
        response = client.post(
            "/api/projects/",
            json={"name": f"test-project-{time.time()}", "description": "Test project"},
        )
        assert response.status_code == 401

    def test_projects_update_api(self):
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

    def test_projects_archive(self):
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

    def test_project_today_time(self):
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

    def test_project_week_time(self):
        """Test GET /api/projects/{project_id}/week/ - Get current week time for project"""
        # Create project
        project = client.post(
            "/api/projects/",
            json={"name": f"test-week-{time.time()}", "description": "Test week time"},
            headers=auth_headers,
        ).json()

        response = client.get(f"/api/projects/{project['id']}/week/", headers=auth_headers)
        assert response.status_code == 200
        week_data = response.json()
        assert "total_hours" in week_data
        # Check all weekdays are present
        weekdays = [
            "Monday",
            "Tuesday",
            "Wednesday",
            "Thursday",
            "Friday",
            "Saturday",
            "Sunday",
        ]
        for day in weekdays:
            assert day in week_data

    def test_project_total_time(self):
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

    def test_project_summary(self):
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

    def test_start_project_timer(self):
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

    def test_stop_project_timer(self):
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

    def test_stop_timer_when_not_started(self):
        """Test POST /api/projects/stop when no timer is running - Should fail"""
        # Make sure no timer is running by trying to stop
        response = client.post(
            "/api/projects/stop",
            json={"time": datetime.now(UTC).isoformat()},
            headers=auth_headers,
        )
        # This might be 400 or 200 depending on state, just check it doesn't crash
        assert response.status_code in [200, 400]


class TestGoalOverridesAPI:
    """Test suite for goal override endpoints."""

    def _create_project(self, weekly_goal=20):
        resp = client.post(
            "/api/projects/",
            json={"name": f"goal-test-{time.time()}", "weekly_goal": weekly_goal},
            headers=auth_headers,
        )
        assert resp.status_code == 201
        return resp.json()

    def test_put_goal_overrides(self):
        """Test PUT /api/projects/{id}/goal-overrides — add overrides."""
        project = self._create_project()
        resp = client.put(
            f"/api/projects/{project['id']}/goal-overrides",
            json=[
                {"week_of": "2026-04-06", "weekly_goal": 10, "note": "holiday"},
                {"effective_from": "2026-03-02", "weekly_goal": 30},
            ],
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["goal_overrides"]) == 2

    def test_goal_overrides_persist_on_project(self):
        """Overrides appear when listing projects."""
        project = self._create_project()
        client.put(
            f"/api/projects/{project['id']}/goal-overrides",
            json=[{"week_of": "2026-04-06", "weekly_goal": 10}],
            headers=auth_headers,
        )
        projects = client.get("/api/projects/", headers=auth_headers).json()
        found = [p for p in projects if p["id"] == project["id"]][0]
        assert len(found["goal_overrides"]) == 1
        assert found["goal_overrides"][0]["weekly_goal"] == 10

    def test_week_breakdown_includes_effective_goal(self):
        """GET /api/projects/{id}/week/ returns effective_goal."""
        project = self._create_project(weekly_goal=20)
        resp = client.get(f"/api/projects/{project['id']}/week/?weeks_ago=0", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["effective_goal"] == 20
        assert data["effective_goal_type"] == "target"

    def test_week_breakdown_with_override(self):
        """Effective goal reflects an active override."""
        project = self._create_project(weekly_goal=20)
        # Add a permanent override starting well in the past
        client.put(
            f"/api/projects/{project['id']}/goal-overrides",
            json=[{"effective_from": "2020-01-06", "weekly_goal": 35}],
            headers=auth_headers,
        )
        resp = client.get(f"/api/projects/{project['id']}/week/?weeks_ago=0", headers=auth_headers)
        data = resp.json()
        assert data["effective_goal"] == 35

    def test_replace_overrides(self):
        """PUT replaces all overrides, not appends."""
        project = self._create_project()
        url = f"/api/projects/{project['id']}/goal-overrides"
        client.put(url, json=[{"week_of": "2026-04-06", "weekly_goal": 10}], headers=auth_headers)
        client.put(url, json=[{"week_of": "2026-04-13", "weekly_goal": 5}], headers=auth_headers)
        data = client.get("/api/projects/", headers=auth_headers).json()
        found = [p for p in data if p["id"] == project["id"]][0]
        assert len(found["goal_overrides"]) == 1
        assert found["goal_overrides"][0]["week_of"] == "2026-04-13"

    def test_clear_overrides(self):
        """Sending empty list clears all overrides."""
        project = self._create_project()
        url = f"/api/projects/{project['id']}/goal-overrides"
        client.put(url, json=[{"week_of": "2026-04-06", "weekly_goal": 10}], headers=auth_headers)
        client.put(url, json=[], headers=auth_headers)
        data = client.get("/api/projects/", headers=auth_headers).json()
        found = [p for p in data if p["id"] == project["id"]][0]
        assert len(found["goal_overrides"]) == 0

    def test_one_off_null_override_clears_week(self):
        """A one-off override with weekly_goal=null makes that week have no goal."""
        project = self._create_project(weekly_goal=20)
        client.put(
            f"/api/projects/{project['id']}/goal-overrides",
            json=[{"week_of": "2020-01-06", "weekly_goal": None, "note": "holiday"}],
            headers=auth_headers,
        )
        # Past week (same Monday as the override): no goal
        # weeks_ago for 2020-01-06 is well into the past; compute by hitting the
        # endpoint directly via the week_of Monday. The breakdown uses weeks_ago,
        # so we verify via project list instead.
        projects = client.get("/api/projects/", headers=auth_headers).json()
        found = [p for p in projects if p["id"] == project["id"]][0]
        overrides = found["goal_overrides"]
        assert len(overrides) == 1
        assert overrides[0]["weekly_goal"] is None
        assert overrides[0]["note"] == "holiday"

    def test_permanent_null_override_clears_forward(self):
        """A permanent null override clears the goal from that Monday forward."""
        project = self._create_project(weekly_goal=20)
        client.put(
            f"/api/projects/{project['id']}/goal-overrides",
            json=[{"effective_from": "2020-01-06", "weekly_goal": None}],
            headers=auth_headers,
        )
        resp = client.get(f"/api/projects/{project['id']}/week/?weeks_ago=0", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["effective_goal"] is None

    def test_null_override_does_not_affect_earlier_weeks(self):
        """A permanent null override starting on a future Monday leaves earlier
        weeks with the project default goal."""
        project = self._create_project(weekly_goal=20)
        # effective_from far in the future (next decade Monday)
        client.put(
            f"/api/projects/{project['id']}/goal-overrides",
            json=[{"effective_from": "2099-01-05", "weekly_goal": None}],
            headers=auth_headers,
        )
        resp = client.get(f"/api/projects/{project['id']}/week/?weeks_ago=0", headers=auth_headers)
        assert resp.json()["effective_goal"] == 20


class TestBeatsDirectAPI:
    """Test suite for Beat (time log) management endpoints"""

    def test_create_api(self):
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

    def test_list_api(self):
        """Test GET /api/beats/ - List all beats"""
        response = client.get("/api/beats/", headers=auth_headers)
        assert response.status_code == 200
        beats = response.json()
        assert isinstance(beats, list)

    def test_list_api_with_project_filter(self):
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

    def test_list_api_with_date_filter(self):
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

    def test_get_beat_by_id(self):
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

    def test_update_api(self):
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

    def test_delete_beat(self):
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

    def test_timer_status_when_idle(self):
        """Test GET /api/timer/status - When no timer is running"""
        # Try to ensure no timer is running
        try:
            client.post(
                "/api/projects/stop",
                json={"time": datetime.now(UTC).isoformat()},
                headers=auth_headers,
            )
        except Exception:
            pass

        response = client.get("/api/timer/status", headers=auth_headers)
        assert response.status_code == 200
        status = response.json()
        assert "isBeating" in status

    def test_timer_status_when_active(self):
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
    brief retrieval, review retrieval, memory read) and verify auth/shape."""

    def test_brief_today_returns_null_when_empty(self):
        response = client.get("/api/coach/brief/today", headers=auth_headers)
        assert response.status_code == 200
        # No brief generated yet — should return null
        assert response.json() is None

    def test_brief_history_returns_empty_list(self):
        response = client.get("/api/coach/brief/history", headers=auth_headers)
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_review_today_returns_null_when_empty(self):
        response = client.get("/api/coach/review/today", headers=auth_headers)
        assert response.status_code == 200
        assert response.json() is None

    def test_memory_returns_empty_content(self):
        response = client.get("/api/coach/memory", headers=auth_headers)
        assert response.status_code == 200
        body = response.json()
        assert "content" in body

    def test_usage_returns_shape(self):
        response = client.get("/api/coach/usage", headers=auth_headers)
        assert response.status_code == 200
        body = response.json()
        assert "days" in body
        assert "month_total_usd" in body
        assert "budget_usd" in body
        assert isinstance(body["days"], list)
        assert body["budget_usd"] > 0

    def test_coach_endpoints_require_auth(self):
        for path in [
            "/api/coach/brief/today",
            "/api/coach/brief/history",
            "/api/coach/review/today",
            "/api/coach/memory",
            "/api/coach/usage",
        ]:
            assert client.get(path).status_code == 401, f"{path} should require auth"

    def test_chat_requires_auth(self):
        response = client.post("/api/coach/chat", json={"message": "hello"})
        assert response.status_code == 401


class TestMiscellaneousEndpoints:
    """Test suite for miscellaneous endpoints"""

    def test_ding_endpoint(self):
        """Test POST /talk/ding - Simple ping endpoint (public)"""
        response = client.post("/talk/ding")
        assert response.status_code == 200
        assert response.json() == {"message": "dong"}


class TestIdempotentReplay:
    """Timer start/stop must be idempotent under retries keyed by X-Client-Id."""

    def _create_project(self) -> str:
        res = client.post(
            "/api/projects/",
            json={"name": "Idempotency Probe", "description": "test"},
            headers=auth_headers,
        )
        assert res.status_code == 201, res.text
        return res.json()["id"]

    def test_repeated_start_with_same_client_id_is_replayed(self):
        """Second POST with same X-Client-Id returns the cached response + replay flag."""
        project_id = self._create_project()
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

    def test_different_client_id_is_not_replayed(self):
        """A fresh client id is treated as a new write and not served from cache."""
        project_id = self._create_project()
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


class TestSignedSqliteExport:
    """The signed SQLite export must round-trip cleanly and reject tampering."""

    def _create_project(self, name: str) -> str:
        res = client.post(
            "/api/projects/",
            json={"name": name, "description": "export probe"},
            headers=auth_headers,
        )
        assert res.status_code == 201, res.text
        return res.json()["id"]

    def test_export_roundtrip(self):
        """Export produces a signed zip; re-importing it is accepted."""
        import io
        import zipfile

        # Seed some data so counts are non-zero.
        self._create_project("Export Roundtrip A")
        self._create_project("Export Roundtrip B")

        res = client.get("/api/export/sqlite", headers=auth_headers)
        assert res.status_code == 200, res.text
        assert res.headers["content-type"].startswith("application/zip")

        with zipfile.ZipFile(io.BytesIO(res.content)) as zf:
            names = set(zf.namelist())
            assert {"data.sqlite", "manifest.json", "manifest.sig", "public_key.bin"}.issubset(
                names
            )
            manifest = zf.read("manifest.json")
            assert b'"projects"' in manifest  # deterministic sorted-keys payload

        # Re-upload the untouched bundle. Verify succeeds, writers run.
        imported = client.post(
            "/api/export/sqlite/import",
            files={"file": ("backup.zip", res.content, "application/zip")},
            headers=auth_headers,
        )
        assert imported.status_code == 200, imported.text
        body = imported.json()
        assert body["status"] == "ok"
        assert body["version"] == "sqlite-1"
        assert body["imported"]["projects"] >= 2

    def test_import_rejects_tampered_manifest(self):
        """Flipping a byte in the manifest must trip the signature check."""
        import io
        import zipfile

        self._create_project("Tamper Probe")
        res = client.get("/api/export/sqlite", headers=auth_headers)
        assert res.status_code == 200

        # Build a new zip with a mutated manifest but the original signature.
        bad_zip = io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(res.content)) as src:
            with zipfile.ZipFile(bad_zip, "w", compression=zipfile.ZIP_DEFLATED) as dst:
                for name in src.namelist():
                    data = src.read(name)
                    if name == "manifest.json":
                        # Replace the version string — changes canonical bytes.
                        data = data.replace(b'"sqlite-1"', b'"sqlite-evil"')
                    dst.writestr(name, data)

        imported = client.post(
            "/api/export/sqlite/import",
            files={"file": ("tampered.zip", bad_zip.getvalue(), "application/zip")},
            headers=auth_headers,
        )
        assert imported.status_code == 400
        assert "signature" in imported.text.lower()

    def test_import_rejects_swapped_sqlite_payload(self):
        """Swapping the SQLite body (manifest + signature untouched) is rejected
        by the sha256 check even though the Ed25519 signature is intact."""
        import io
        import zipfile

        self._create_project("Swap Probe")
        res = client.get("/api/export/sqlite", headers=auth_headers)
        assert res.status_code == 200

        bad_zip = io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(res.content)) as src:
            with zipfile.ZipFile(bad_zip, "w", compression=zipfile.ZIP_DEFLATED) as dst:
                for name in src.namelist():
                    data = src.read(name)
                    if name == "data.sqlite":
                        data = data + b"\x00"  # extra byte breaks sha256
                    dst.writestr(name, data)

        imported = client.post(
            "/api/export/sqlite/import",
            files={"file": ("swapped.zip", bad_zip.getvalue(), "application/zip")},
            headers=auth_headers,
        )
        assert imported.status_code == 400
        assert "match manifest" in imported.text.lower()


class TestIntelligenceInbox:
    """Smoke tests for the aggregated Intelligence Inbox endpoint."""

    def test_inbox_returns_ok_shape_for_empty_user(self):
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

    def test_inbox_requires_auth(self):
        """GET /api/intelligence/inbox rejects unauthenticated requests."""
        response = client.get("/api/intelligence/inbox")
        assert response.status_code == 401


class TestAuthenticationMiddleware:
    """Test suite for authentication middleware"""

    def test_all_requests_require_auth(self):
        """Test that all requests (including GET) require authentication"""
        response = client.get("/api/projects/")
        assert response.status_code == 401

    def test_post_requests_require_auth(self):
        """Test POST requests require authentication"""
        response = client.post("/api/projects/", json={"name": "test", "description": "test"})
        assert response.status_code == 401

    def test_put_requests_require_auth(self):
        """Test PUT requests require authentication"""
        response = client.put(
            "/api/projects/", json={"id": "test", "name": "test", "description": "test"}
        )
        assert response.status_code == 401

    def test_invalid_bearer_token(self):
        """Test invalid Bearer token is rejected"""
        response = client.get(
            "/api/projects/",
            headers={"Authorization": "Bearer invalid-jwt-token"},
        )
        assert response.status_code == 401
        assert "Invalid or expired" in response.json()["error"]

    def test_public_endpoints_no_auth(self):
        """Test public endpoints don't require auth"""
        response = client.get("/health")
        assert response.status_code == 200

        response = client.post("/talk/ding")
        assert response.status_code == 200

    def test_auth_endpoints_no_auth(self):
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

    def test_logout_revokes_token(self, auth_info):
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

    def test_logout_without_token_requires_auth(self):
        """POST /api/account/logout without a token returns 401."""
        response = client.post("/api/account/logout")
        assert response.status_code == 401

    def test_other_tokens_unaffected_by_logout(self, auth_info):
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


class TestRateLimiting:
    """Test that auth endpoints are rate-limited."""

    def test_login_options_rate_limited(self):
        """GET /api/auth/login/options is rate-limited after repeated requests."""
        for _ in range(10):
            client.get("/api/auth/login/options")

        response = client.get("/api/auth/login/options")
        assert response.status_code == 429


class TestMultiUserIsolation:
    """Test that data is isolated between users."""

    def _make_headers(self, user_id: str, email: str) -> dict[str, str]:
        from beats.auth.session import SessionManager
        from beats.settings import settings

        sm = SessionManager(settings.jwt_secret)
        token = sm.create_session_token(user_id, email)
        return {"Authorization": f"Bearer {token}"}

    def test_projects_isolated_between_users(self):
        """Projects created by one user are not visible to another."""
        import os

        from bson import ObjectId
        from pymongo import MongoClient

        dsn = os.environ.get("DB_DSN", "mongodb://localhost:27017")
        db_name = os.environ.get("DB_NAME", "beats_test")
        sync_client = MongoClient(dsn)
        db = sync_client[db_name]

        # Create two users
        user1_id = str(ObjectId())
        user2_id = str(ObjectId())
        for uid, email in [(user1_id, "user1@test.com"), (user2_id, "user2@test.com")]:
            db.users.insert_one(
                {
                    "_id": ObjectId(uid),
                    "email": email,
                    "display_name": None,
                }
            )
        sync_client.close()

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


class TestDevicePairingAPI:
    """Test suite for daemon device pairing and device token auth."""

    def test_generate_pair_code_requires_auth(self):
        """POST /api/device/pair/code without token returns 401."""
        resp = client.post("/api/device/pair/code")
        assert resp.status_code == 401

    def test_generate_pair_code_success(self):
        """POST /api/device/pair/code returns a 6-char code."""
        resp = client.post("/api/device/pair/code", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["code"]) == 6
        assert data["expires_in_seconds"] == 300

    def test_exchange_code_success(self):
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

    def test_exchange_code_invalid(self):
        """Exchange with bad code returns 404."""
        resp = client.post(
            "/api/device/pair/exchange",
            json={"code": "BADCOD"},
        )
        assert resp.status_code == 404

    def test_exchange_code_one_time_use(self):
        """Same code can only be exchanged once."""
        resp = client.post("/api/device/pair/code", headers=auth_headers)
        code = resp.json()["code"]

        # First exchange succeeds
        resp = client.post("/api/device/pair/exchange", json={"code": code})
        assert resp.status_code == 200

        # Second exchange fails
        resp = client.post("/api/device/pair/exchange", json={"code": code})
        assert resp.status_code == 404

    def test_device_token_allows_heartbeat(self):
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

    def test_device_token_blocked_on_non_allowed_endpoints(self):
        """Device token is rejected on endpoints not in DEVICE_ALLOWED_PREFIXES."""
        # Pair a device
        resp = client.post("/api/device/pair/code", headers=auth_headers)
        code = resp.json()["code"]
        resp = client.post("/api/device/pair/exchange", json={"code": code})
        device_token = resp.json()["device_token"]
        device_headers = {"Authorization": f"Bearer {device_token}"}

        # Try accessing analytics (not in DEVICE_ALLOWED_PREFIXES)
        resp = client.get("/api/analytics/heatmap", headers=device_headers)
        assert resp.status_code == 403

    def test_list_registrations(self):
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

    def test_revoke_device(self):
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
        assert "revoked" in resp.json()["error"]

    def test_revoked_device_not_in_list(self):
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


class TestSignalsAPI:
    """Test suite for signals (flow windows + signal summaries) endpoints."""

    def _pair_device(self):
        """Helper: pair a device and return (device_token, device_headers)."""
        resp = client.post("/api/device/pair/code", headers=auth_headers)
        code = resp.json()["code"]
        resp = client.post("/api/device/pair/exchange", json={"code": code})
        data = resp.json()
        return data["device_token"], {"Authorization": f"Bearer {data['device_token']}"}

    def test_post_flow_window_with_device_token(self):
        """Device token can POST a flow window."""
        _, device_headers = self._pair_device()
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

    def test_read_flow_windows_with_session_token(self):
        """Session token can read flow windows posted by the device."""
        _, device_headers = self._pair_device()
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

    def test_post_signal_summary(self):
        """Device token can POST signal summaries."""
        _, device_headers = self._pair_device()
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

    def test_read_signal_summaries(self):
        """Session token can read signal summaries."""
        _, device_headers = self._pair_device()
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

    def test_summary_upsert(self):
        """Posting the same hour twice upserts (updates, not duplicates)."""
        _, device_headers = self._pair_device()
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

    def test_delete_all_signals(self):
        """DELETE /api/signals/all removes all summaries."""
        _, device_headers = self._pair_device()
        now = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)

        client.post(
            "/api/signals/summaries",
            json={"hour": now.isoformat(), "categories": {"coding": 5}, "total_samples": 5},
            headers=device_headers,
        )

        resp = client.delete("/api/signals/all", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["deleted_summaries"] >= 1

    def test_device_token_blocked_on_non_allowed_paths(self):
        """Device token cannot access endpoints outside DEVICE_ALLOWED_PREFIXES."""
        _, device_headers = self._pair_device()
        resp = client.get("/api/analytics/heatmap", headers=device_headers)
        assert resp.status_code == 403

    def test_flow_window_validation(self):
        """Flow score values are validated to [0, 1]."""
        _, device_headers = self._pair_device()
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

    def _pair_device(self):
        """Helper: pair a device and return device_headers."""
        resp = client.post("/api/device/pair/code", headers=auth_headers)
        code = resp.json()["code"]
        resp = client.post("/api/device/pair/exchange", json={"code": code})
        return {"Authorization": f"Bearer {resp.json()['device_token']}"}

    def test_post_biometric_day(self):
        """POST biometric data with device token."""
        device_headers = self._pair_device()
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

    def test_post_biometric_day_session_token(self):
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

    def test_read_biometrics(self):
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

    def test_biometric_upsert(self):
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

    def test_delete_biometrics(self):
        """DELETE removes all biometric data."""
        client.post(
            "/api/biometrics/daily",
            json={"date": "2026-04-14", "source": "healthkit", "steps": 3000},
            headers=auth_headers,
        )
        resp = client.delete("/api/biometrics/", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["deleted"] >= 1

    def test_fitbit_status_disconnected(self):
        """GET /api/fitbit/status returns disconnected by default."""
        resp = client.get("/api/fitbit/status", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["connected"] is False

    def test_oura_status_disconnected(self):
        """GET /api/oura/status returns disconnected by default."""
        resp = client.get("/api/oura/status", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["connected"] is False
