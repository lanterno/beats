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
    yield


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


class TestCoachRouterGapFill:
    """Coach routes whose logic isn't covered by the smoke suite —
    /chat/history pagination + filtering, /usage with seeded rows,
    /review/start + /review/answer happy paths, and the
    BUDGET_EXCEEDED 429 envelope. Mocks the LLM-touching modules so
    the tests run deterministically; uses real Mongo via testcontainers
    for the persistence assertions."""

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
            "review_answers",
        ):
            db[coll].delete_many({})
        sync.close()
        yield

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

    def test_chat_history_empty_returns_empty_list(self, auth_info):
        resp = client.get("/api/coach/chat/history", headers=auth_info["headers"])
        assert resp.status_code == 200
        assert resp.json() == []

    def test_chat_history_returns_chronological_order(self, auth_info):
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

    def test_chat_history_filters_by_conversation_id(self, auth_info):
        self._seed_message(auth_info, "c-1", "user", "in c1")
        self._seed_message(auth_info, "c-2", "user", "in c2")

        resp = client.get(
            "/api/coach/chat/history?conversation_id=c-1",
            headers=auth_info["headers"],
        )
        assert resp.status_code == 200
        contents = [m["content"] for m in resp.json()]
        assert contents == ["in c1"]

    def test_chat_history_respects_limit(self, auth_info):
        for i in range(5):
            self._seed_message(auth_info, "c-1", "user", f"msg {i}", seconds_ago=100 - i)

        resp = client.get("/api/coach/chat/history?limit=3", headers=auth_info["headers"])
        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 3

    def test_chat_history_validates_limit_bounds(self, auth_info):
        # Router declares Query(default=50, ge=1, le=200).
        for q in ("?limit=0", "?limit=201"):
            resp = client.get(f"/api/coach/chat/history{q}", headers=auth_info["headers"])
            assert resp.status_code == 422

    # ── /usage ───────────────────────────────────────────────────────

    def test_usage_aggregates_seeded_rows_by_day(self, auth_info):
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

    def test_usage_validates_days_param(self, auth_info):
        # ge=1, le=90.
        for q in ("?days=0", "?days=91"):
            resp = client.get(f"/api/coach/usage{q}", headers=auth_info["headers"])
            assert resp.status_code == 422

    # ── /review/start + /review/answer ───────────────────────────────

    def test_review_start_returns_questions_after_generation(self, auth_info, monkeypatch):
        """Router calls generate_review_questions then reads the
        persisted doc. Mock the LLM-touching call; verify the response
        shape matches what the UI parses."""
        from datetime import UTC as _UTC
        from datetime import datetime as _dt

        from beats.api.routers import coach as coach_router

        # Stub the heavy generate_review_questions to write a doc and
        # return — exactly what the real one does after the LLM call.
        async def fake_generate(user_id, target_date=None):
            import os

            from bson import ObjectId
            from pymongo import MongoClient

            dsn = os.environ.get("DB_DSN", "mongodb://localhost:27017")
            db_name = os.environ.get("DB_NAME", "beats_test")
            sync = MongoClient(dsn)
            today = (target_date or _dt.now(_UTC).date()).isoformat()
            sync[db_name].review_answers.insert_one(
                {
                    "_id": ObjectId(),
                    "user_id": user_id,
                    "date": today,
                    "questions": [
                        {"question": "Q1", "derived_from": {"kind": "x"}},
                        {"question": "Q2", "derived_from": {"kind": "y"}},
                        {"question": "Q3", "derived_from": {"kind": "z"}},
                    ],
                    "answers": [None, None, None],
                }
            )
            sync.close()
            return []

        monkeypatch.setattr(coach_router, "generate_review_questions", fake_generate)

        resp = client.post("/api/coach/review/start", headers=auth_info["headers"])
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "date" in body
        assert "questions" in body
        assert len(body["questions"]) == 3
        # Each question carries the documented shape.
        for q in body["questions"]:
            assert "question" in q
            assert "derived_from" in q

    def test_review_start_budget_exceeded_returns_429_with_envelope(self, auth_info, monkeypatch):
        """When the user's monthly budget is over, the router maps
        BudgetExceeded → 429 with code=BUDGET_EXCEEDED. Pin the
        envelope shape; clients use the code to render
        "monthly LLM budget reached" instead of "rate limited"."""
        from beats.api.routers import coach as coach_router
        from beats.coach.usage import BudgetExceeded

        async def fake_generate(_user_id, _target_date=None):
            raise BudgetExceeded(spent=15.0, limit=10.0)

        monkeypatch.setattr(coach_router, "generate_review_questions", fake_generate)

        resp = client.post("/api/coach/review/start", headers=auth_info["headers"])
        assert resp.status_code == 429
        body = resp.json()
        assert body["code"] == "BUDGET_EXCEEDED"

    def test_review_start_generic_failure_returns_502(self, auth_info, monkeypatch):
        """Any other exception during generation surfaces as 502
        with the friendly "coach is resting" message — distinct
        from BUDGET_EXCEEDED so clients can tell "your budget is
        over" from "the LLM API is down"."""
        from beats.api.routers import coach as coach_router

        async def fake_generate(_user_id, _target_date=None):
            raise RuntimeError("anthropic 500")

        monkeypatch.setattr(coach_router, "generate_review_questions", fake_generate)

        resp = client.post("/api/coach/review/start", headers=auth_info["headers"])
        assert resp.status_code == 502
        body = resp.json()
        assert "coach is resting" in body["detail"]

    def test_review_answer_persists_and_returns_ok(self, auth_info):
        """Seed a review doc, post an answer, verify it landed in the
        right slot."""
        # Seed
        import os
        from datetime import UTC as _UTC
        from datetime import datetime as _dt

        from bson import ObjectId
        from pymongo import MongoClient

        dsn = os.environ.get("DB_DSN", "mongodb://localhost:27017")
        db_name = os.environ.get("DB_NAME", "beats_test")
        today = _dt.now(_UTC).date().isoformat()
        sync = MongoClient(dsn)
        sync[db_name].review_answers.insert_one(
            {
                "_id": ObjectId(),
                "user_id": auth_info["user_id"],
                "date": today,
                "questions": [
                    {"question": "Q1", "derived_from": {"kind": "x"}},
                ],
                "answers": [None],
            }
        )
        sync.close()

        resp = client.post(
            "/api/coach/review/answer",
            json={"date": today, "question_index": 0, "answer": "my answer"},
            headers=auth_info["headers"],
        )
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}

        # Verify persistence.
        sync = MongoClient(dsn)
        doc = sync[db_name].review_answers.find_one(
            {"user_id": auth_info["user_id"], "date": today}
        )
        sync.close()
        assert doc is not None
        assert doc["answers"][0]["text"] == "my answer"

    def test_review_answer_invalid_date_returns_400_envelope(self, auth_info):
        """The handler raises with code=INVALID_DATE on bad date input
        (locks the override pattern that this session's coach error-
        codes commit established)."""
        resp = client.post(
            "/api/coach/review/answer",
            json={"date": "not-a-date", "question_index": 0, "answer": "x"},
            headers=auth_info["headers"],
        )
        assert resp.status_code == 400
        body = resp.json()
        assert body["code"] == "INVALID_DATE"

    def test_memory_rewrite_budget_exceeded_uses_envelope_code(self, auth_info, monkeypatch):
        """Pin parity with /brief and /review: a BudgetExceeded on
        memory rewrite must surface as 429 + code=BUDGET_EXCEEDED,
        not the generic RATE_LIMITED. Without this, a client that
        branches on the code field would render "rate limited" for
        memory but "budget reached" for brief — confusing UX. Locks
        the parity fix from the T4 audit."""
        from beats.api.routers import coach as coach_router
        from beats.coach.usage import BudgetExceeded

        async def fake_rewrite(_user_id):
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
       five collections (memory + briefs + reviews + conversations
       + usage)
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
            "review_answers",
            "coach_conversations",
            "llm_usage",
        ):
            db[coll].delete_many({})
        sync.close()
        yield

    def _seed_all_coach_data(self, user_id: str):
        """Insert one row in each of the five coach collections
        for the given user. Used by the DELETE /data test to
        verify all five are wiped in one shot."""
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
        db.review_answers.insert_one(
            {
                "user_id": user_id,
                "date": "2026-04-01",
                "questions": [],
                "answers": [],
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
                "review_answers",
                "coach_conversations",
                "llm_usage",
            )
        }
        sync.close()
        return out

    # ---------------- DELETE /api/coach/memory ----------------

    def test_delete_memory_wipes_only_this_users_memory(self, auth_info):
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

    def test_delete_data_wipes_all_five_collections_for_user(self, auth_info):
        """DELETE /data is the "factory reset" — it MUST wipe all
        five coach collections (memory + briefs + reviews +
        conversations + usage) for the requesting user. Pin all
        five so a refactor that skips one (e.g. forgets the new
        usage logs) is caught."""
        self._seed_all_coach_data(auth_info["user_id"])

        # Sanity: all five non-zero before the delete
        before = self._count_user_data(auth_info["user_id"])
        assert all(c == 1 for c in before.values()), before

        resp = client.delete("/api/coach/data", headers=auth_info["headers"])
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert "all coach data" in body["deleted"]

        # All five collections empty for this user
        after = self._count_user_data(auth_info["user_id"])
        assert all(c == 0 for c in after.values()), after

    def test_delete_data_does_not_touch_other_users(self, auth_info):
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

    def test_delete_endpoints_require_auth(self):
        """Both destructive endpoints must reject unauthenticated
        requests. Pin the auth gate — an unauthenticated DELETE
        on these would be a catastrophic data-wipe primitive."""
        assert client.delete("/api/coach/memory").status_code == 401
        assert client.delete("/api/coach/data").status_code == 401

    # ---------------- /api/coach/chat SSE ----------------

    def test_chat_sse_streams_events(self, monkeypatch):
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

    def test_chat_sse_emits_budget_exceeded_envelope(self, monkeypatch):
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
        # The exception's stringified body propagates to the SSE event
        assert "$12.50" in body
        assert "$10.00" in body
        assert body.rstrip().endswith("data: [DONE]")

    def test_chat_sse_emits_generic_502_envelope_on_unexpected_failure(self, monkeypatch):
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


class TestCoachBriefAndReviewErrorPaths:
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
        yield

    def test_brief_today_returns_doc_when_exists(self, auth_info):
        """GET /brief/today with a seeded brief → BriefResponse
        envelope. Pin so the dashboard can render the brief
        without a separate "no brief yet" empty state when one
        exists."""
        from datetime import UTC, date, datetime

        sync, db = self._db()
        today_iso = date.today().isoformat()
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

    def test_brief_generate_budget_exceeded_returns_429_envelope(self, monkeypatch, auth_info):
        """POST /brief/generate when BudgetExceeded fires inside
        generate_brief → 429 with BUDGET_EXCEEDED code (NOT the
        generic RATE_LIMITED). Pin so the UI's "monthly LLM
        budget reached" toast triggers from the right code."""
        from beats.api.routers import coach as coach_router
        from beats.coach.usage import BudgetExceeded

        async def fake_generate_brief(*args, **kwargs):  # noqa: ARG001
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

    def test_brief_generate_generic_failure_returns_502_envelope(self, monkeypatch, auth_info):
        """Any other exception inside generate_brief → 502 with a
        SANITIZED message. Pin so the actual exception text
        ("anthropic exploded") doesn't leak to the user — only
        the canned "the coach is resting" string surfaces."""
        from beats.api.routers import coach as coach_router

        async def fake_generate_brief(*args, **kwargs):  # noqa: ARG001
            raise RuntimeError("anthropic exploded")

        monkeypatch.setattr(coach_router, "generate_brief", fake_generate_brief)

        resp = client.post("/api/coach/brief/generate", headers=auth_info["headers"])
        assert resp.status_code == 502
        text = resp.text
        assert "coach is resting" in text
        # Internal exception message MUST NOT leak
        assert "anthropic exploded" not in text

    def test_brief_generate_invalid_date_returns_400_envelope(self, auth_info):
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

    def test_memory_rewrite_generic_failure_returns_502(self, monkeypatch, auth_info):
        """Generic exception inside rewrite_coach_memory → 502.
        Pin so the rewrite endpoint doesn't expose internal error
        text. BudgetExceeded → 429 path is already covered by
        TestCoachRouterGapFill.test_memory_rewrite_budget_exceeded."""
        from beats.api.routers import coach as coach_router

        async def fake_rewrite(*args, **kwargs):  # noqa: ARG001
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

    def _create_project(self) -> str:
        resp = client.post(
            "/api/projects/",
            json={"name": "Analytics Probe"},
            headers=auth_headers,
        )
        assert resp.status_code == 201
        return resp.json()["id"]

    def test_rhythm_returns_48_slots_for_session_token(self):
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

    def test_gaps_returns_list_for_session_token(self):
        """GET /api/analytics/gaps returns a list (possibly empty
        for a no-data day). Pin the array shape — the dashboard's
        Untracked Gaps panel iterates directly on the response."""
        resp = client.get("/api/analytics/gaps", headers=auth_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body, list)

    def test_tags_returns_sorted_unique_tags_from_user_beats(self):
        """GET /api/analytics/tags surfaces every unique tag across
        the user's beats, sorted alphabetically. Pin the
        deduplication + sort — the companion app's tag-suggestion
        chips bind to this list directly."""
        project_id = self._create_project()
        # Start + stop a timer to create one completed beat
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
        # Find that beat's id and update with tags
        resp = client.get("/api/beats/", headers=auth_headers)
        assert resp.status_code == 200
        beats = resp.json()
        assert len(beats) >= 1
        beat = beats[0]
        # Update via PUT — same shape as the companion's post-stop edit
        beat["tags"] = ["focus", "morning", "focus"]  # dedup probe
        client.put(
            "/api/beats/",
            json=beat,
            headers=auth_headers,
        )

        resp = client.get("/api/analytics/tags", headers=auth_headers)
        assert resp.status_code == 200
        tags = resp.json()
        # Deduplicated AND sorted
        assert tags == ["focus", "morning"]


class TestErrorEnvelope:
    """Every HTTP error from the API now flows through the unified envelope:
    {detail: str, code: str, fields?: list}."""

    def test_404_uses_envelope(self):
        # Valid ObjectId shape but no such record.
        resp = client.get("/api/beats/507f1f77bcf86cd799439011", headers=auth_headers)
        assert resp.status_code == 404
        body = resp.json()
        assert isinstance(body.get("detail"), str)
        assert body["code"] == "NOT_FOUND"

    def test_validation_error_lists_fields(self):
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
            assert "path" in f and "message" in f and "type" in f

    def test_missing_auth_envelope(self):
        resp = client.get("/api/projects/")
        assert resp.status_code == 401
        body = resp.json()
        assert body["code"] == "MISSING_TOKEN"
        assert "Authentication" in body["detail"]

    def test_validation_error_strips_loc_prefix_from_field_path(self):
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

    def test_validation_singular_summary(self):
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

    def test_router_can_override_default_code_with_dict_detail(self):
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

    def test_domain_exception_uses_envelope(self):
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


class TestIntentionsAPI:
    """Intentions endpoints — list, create, patch, delete."""

    def _create_project(self) -> str:
        resp = client.post(
            "/api/projects/",
            json={"name": "Intention Test Project"},
            headers=auth_headers,
        )
        assert resp.status_code == 201, resp.text
        return resp.json()["id"]

    def test_patch_finds_intention_by_id_regardless_of_date(self):
        """Regression guard: PATCH /api/intentions/{id} used to scan
        only today's intentions and 404 anything older — even though
        the GET endpoint accepts a target_date for any day. Locks in
        that the lookup is now by id, so a user can toggle off an
        intention from yesterday or earlier (the companion app's
        intentions screen surfaces them).
        """
        project_id = self._create_project()
        # Create an intention dated yesterday so PATCH can't find it
        # if it's still doing the today-only filter.
        yesterday = (datetime.now(UTC).date() - timedelta(days=1)).isoformat()
        resp = client.post(
            "/api/intentions",
            json={
                "project_id": project_id,
                "date": yesterday,
                "planned_minutes": 60,
            },
            headers=auth_headers,
        )
        assert resp.status_code == 201, resp.text
        intention_id = resp.json()["id"]

        # Toggle completed — must succeed even though the intention
        # belongs to yesterday, not today.
        resp = client.patch(
            f"/api/intentions/{intention_id}",
            json={"completed": True},
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["completed"] is True

    def test_patch_returns_404_for_unknown_intention_id(self):
        """A genuinely missing id still 404s — important to keep the
        existing behavior since the companion's error toast routes
        on this status code."""
        resp = client.patch(
            "/api/intentions/507f1f77bcf86cd799439011",
            json={"completed": True},
            headers=auth_headers,
        )
        assert resp.status_code == 404

    def test_list_intentions_returns_today_by_default(self):
        """GET /api/intentions without ?target_date= scopes to today.
        Pin so the dashboard's "today's intentions" widget binds to
        a stable default."""
        project_id = self._create_project()
        # Create one for today, one for yesterday
        yesterday = (datetime.now(UTC).date() - timedelta(days=1)).isoformat()
        client.post(
            "/api/intentions",
            json={"project_id": project_id, "planned_minutes": 60},
            headers=auth_headers,
        )
        client.post(
            "/api/intentions",
            json={"project_id": project_id, "date": yesterday, "planned_minutes": 30},
            headers=auth_headers,
        )
        resp = client.get("/api/intentions", headers=auth_headers)
        assert resp.status_code == 200
        items = resp.json()
        # Today's intention is in the result; yesterday's is not
        today_iso = datetime.now(UTC).date().isoformat()
        dates = {i["date"] for i in items}
        assert today_iso in dates
        assert yesterday not in dates

    def test_patch_planned_minutes_persists(self):
        """PATCH with `planned_minutes` only (no `completed`) updates
        the time-box. Pin the second branch of the patch handler —
        the existing test_patch_finds_intention_by_id only exercises
        the `completed` branch."""
        project_id = self._create_project()
        resp = client.post(
            "/api/intentions",
            json={"project_id": project_id, "planned_minutes": 60},
            headers=auth_headers,
        )
        intention_id = resp.json()["id"]

        resp = client.patch(
            f"/api/intentions/{intention_id}",
            json={"planned_minutes": 90},
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["planned_minutes"] == 90
        # Existing completed state should be preserved
        assert body["completed"] is False

    def test_delete_intention_returns_204(self):
        """DELETE /api/intentions/{id} → 204 No Content. Pin the
        status code (companion app uses it to confirm deletion)."""
        project_id = self._create_project()
        resp = client.post(
            "/api/intentions",
            json={"project_id": project_id, "planned_minutes": 30},
            headers=auth_headers,
        )
        intention_id = resp.json()["id"]
        resp = client.delete(f"/api/intentions/{intention_id}", headers=auth_headers)
        assert resp.status_code == 204
        # Confirm it's actually gone — PATCH on the deleted id 404s
        resp = client.patch(
            f"/api/intentions/{intention_id}",
            json={"completed": True},
            headers=auth_headers,
        )
        assert resp.status_code == 404


class TestDailyNotes:
    """Daily-notes endpoints: upsert (PUT + POST alias), single-day get,
    and the date-range list used by mood sparklines."""

    def test_upsert_via_put(self):
        resp = client.put(
            "/api/daily-notes",
            json={"date": "2026-04-30", "mood": 4, "note": "good day"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["date"] == "2026-04-30"
        assert body["mood"] == 4
        assert body["note"] == "good day"

    def test_upsert_via_post_alias(self):
        # POST is exposed as an alias to keep older clients working.
        resp = client.post(
            "/api/daily-notes",
            json={"date": "2026-04-29", "mood": 3, "note": ""},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["mood"] == 3

    def test_get_single_day(self):
        client.put(
            "/api/daily-notes",
            json={"date": "2026-04-28", "mood": 5},
            headers=auth_headers,
        )
        resp = client.get(
            "/api/daily-notes",
            params={"target_date": "2026-04-28"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["mood"] == 5

    def test_list_by_range(self):
        # Seed a few days, fetch a window that covers them.
        for d, m in [("2026-04-25", 2), ("2026-04-26", 3), ("2026-04-27", 4)]:
            client.put(
                "/api/daily-notes",
                json={"date": d, "mood": m, "note": ""},
                headers=auth_headers,
            )
        resp = client.get(
            "/api/daily-notes/range",
            params={"start": "2026-04-25", "end": "2026-04-27"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        rows = resp.json()
        assert isinstance(rows, list)
        moods = {row["date"]: row["mood"] for row in rows}
        assert moods["2026-04-25"] == 2
        assert moods["2026-04-26"] == 3
        assert moods["2026-04-27"] == 4

    def test_range_requires_auth(self):
        resp = client.get(
            "/api/daily-notes/range",
            params={"start": "2026-04-25", "end": "2026-04-27"},
        )
        assert resp.status_code == 401


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

    def test_failed_mutation_is_not_cached_for_replay(self):
        """A 4xx response on a guarded path MUST NOT be cached in
        mutation_log — the user must be able to fix and retry
        with the same client id. Pin the non-2xx skip branch
        in the middleware: a regression that cached failures
        would lock the user out of retrying the same operation.

        Idempotency middleware ONLY covers /api/projects/{id}/start
        and /stop (per IDEMPOTENT_PATH_SUFFIXES) — so we trigger
        the failure on /start with a malformed body."""
        project_id = self._create_project()
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


class TestCsvAndJsonExport:
    """The CSV-sessions and full-JSON export endpoints, plus the
    JSON-import round trip. Pin the response shape (Content-Type,
    Content-Disposition, header row, JSON keys) — these power the
    user's Settings → Export panel and the cross-deploy migration
    path."""

    def _create_project(self, name: str) -> str:
        res = client.post(
            "/api/projects/",
            json={"name": name, "description": "csv probe"},
            headers=auth_headers,
        )
        assert res.status_code == 201, res.text
        return res.json()["id"]

    def test_csv_sessions_export_empty(self):
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

    def test_csv_sessions_export_with_data(self):
        """A completed beat renders one row with the project name
        resolved (not the project_id) and tags joined with `;`.
        Pin both — users' downstream spreadsheets parse on those
        specific separators."""
        project_id = self._create_project("CSV Probe")
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

    def test_csv_sessions_export_filters_by_project(self):
        """`?project_id=X` scopes the export to one project. Pin so
        a regression doesn't leak other projects' rows when the
        user clicks "Export this project"."""
        a_id = self._create_project("CSV Filter A")
        b_id = self._create_project("CSV Filter B")
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

    def test_full_json_export_shape(self):
        """GET /api/export/full returns a JSON envelope with the
        five top-level keys the import endpoint reads back. Pin so
        the export → reimport round trip can't drift."""
        self._create_project("JSON Probe")
        resp = client.get("/api/export/full", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("application/json")
        body = resp.json()
        assert set(body.keys()) >= {
            "exported_at",
            "version",
            "projects",
            "beats",
            "intentions",
            "daily_notes",
        }
        # version is a string
        assert isinstance(body["version"], str)
        # The JSON-format export uses the legacy "1.0" version
        # (the signed SQLite export uses "sqlite-1")
        assert body["version"] == "1.0"

    def test_full_json_round_trip(self):
        """Export → Import round-trip: posting the exported JSON
        back to /api/export/import upserts the rows by ID. Pin so
        a user can move data between deploys (the doc-stated use
        case for this pair of endpoints)."""
        self._create_project("Round Trip")
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

    def test_sqlite_import_rejects_non_zip_blob(self):
        """POST /api/export/sqlite/import with a non-zip file →
        400 "not a zip". Pin the user-facing envelope so a malformed
        upload doesn't 500 the import flow."""
        resp = client.post(
            "/api/export/sqlite/import",
            files={"file": ("garbage.zip", b"not a zip file at all", "application/zip")},
            headers=auth_headers,
        )
        assert resp.status_code == 400
        assert "not a zip" in resp.text.lower()

    def test_sqlite_import_rejects_zip_missing_entries(self):
        """A zip without manifest.json / data.sqlite / manifest.sig →
        400 "missing entries". Pin so a bundle from another tool
        can't be silently imported."""
        import io
        import zipfile

        bad_zip = io.BytesIO()
        with zipfile.ZipFile(bad_zip, "w") as zf:
            # Only one of three required entries
            zf.writestr("data.sqlite", b"\x00" * 16)
        resp = client.post(
            "/api/export/sqlite/import",
            files={"file": ("incomplete.zip", bad_zip.getvalue(), "application/zip")},
            headers=auth_headers,
        )
        assert resp.status_code == 400
        assert "missing entries" in resp.text.lower()

    def test_full_json_round_trip_with_all_four_entity_types(self):
        """Existing round-trip seeds only projects. Pin that beats,
        intentions, AND daily_notes round-trip too — those are
        separate import branches (lines 280-292) and a regression
        in any one would silently lose user data on cross-deploy
        migrations."""
        # Seed: project + beat + intention + daily note
        project_id = self._create_project("Full Round Trip")
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
        client.post(
            "/api/intentions",
            json={"project_id": project_id, "planned_minutes": 60},
            headers=auth_headers,
        )
        client.put(
            "/api/daily-notes",
            json={"date": "2026-04-01", "note": "good day", "mood": 4},
            headers=auth_headers,
        )

        export = client.get("/api/export/full", headers=auth_headers)
        assert export.status_code == 200
        body = export.json()
        # All four entity types present in export
        assert len(body["projects"]) >= 1
        assert len(body["beats"]) >= 1
        assert len(body["intentions"]) >= 1
        assert len(body["daily_notes"]) >= 1

        imported = client.post(
            "/api/export/import",
            files={"file": ("backup.json", export.content, "application/json")},
            headers=auth_headers,
        )
        assert imported.status_code == 200
        imp = imported.json()["imported"]
        # All four counts non-zero — pin so a refactor that drops
        # one of the four import branches surfaces immediately
        assert imp["projects"] >= 1
        assert imp["beats"] >= 1
        assert imp["intentions"] >= 1
        assert imp["daily_notes"] >= 1

    def test_sqlite_round_trip_with_all_four_entity_types(self):
        """Same as the JSON round-trip test, but for the signed
        SQLite bundle. The SQLite import has its own four
        branches (lines 236-253) — pin so a regression in the
        sqlite3.execute(SELECT data FROM ...) loop on any one
        table doesn't silently drop user data on import."""
        project_id = self._create_project("SQLite Round Trip")
        client.post(
            f"/api/projects/{project_id}/start",
            json={"time": "2026-04-02T09:00:00Z"},
            headers=auth_headers,
        )
        client.post(
            "/api/projects/stop",
            json={"time": "2026-04-02T09:15:00Z"},
            headers=auth_headers,
        )
        client.post(
            "/api/intentions",
            json={"project_id": project_id, "planned_minutes": 30},
            headers=auth_headers,
        )
        client.put(
            "/api/daily-notes",
            json={"date": "2026-04-02", "note": "shipping", "mood": 5},
            headers=auth_headers,
        )

        export = client.get("/api/export/sqlite", headers=auth_headers)
        assert export.status_code == 200
        imported = client.post(
            "/api/export/sqlite/import",
            files={"file": ("backup.zip", export.content, "application/zip")},
            headers=auth_headers,
        )
        assert imported.status_code == 200
        imp = imported.json()["imported"]
        assert imp["projects"] >= 1
        assert imp["beats"] >= 1
        assert imp["intentions"] >= 1
        assert imp["daily_notes"] >= 1


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
        body = response.json()
        assert "Invalid or expired" in body["detail"]
        assert body["code"] == "INVALID_TOKEN"

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
        yield

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

    def test_me_returns_current_user(self, auth_info):
        resp = client.get("/api/account/me", headers=auth_info["headers"])
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body == {"email": "test@example.com", "display_name": "Test User"}

    def test_me_404_when_user_deleted_under_token(self, auth_info):
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

    def test_refresh_issues_a_new_working_token(self, auth_info):
        resp = client.post("/api/account/refresh", headers=auth_info["headers"])
        assert resp.status_code == 200, resp.text
        new_token = resp.json()["token"]
        assert new_token and new_token != auth_info["headers"]["Authorization"].split(" ", 1)[1]

        # The new token actually works on a protected endpoint.
        new_headers = {"Authorization": f"Bearer {new_token}"}
        assert client.get("/api/projects/", headers=new_headers).status_code == 200

    def test_refresh_without_bearer_returns_401(self):
        resp = client.post("/api/account/refresh")
        # The auth middleware fires before the handler — MISSING_TOKEN, not
        # the handler's "Bearer token required". Either way it's a 401.
        assert resp.status_code == 401

    def test_refresh_with_invalid_token_returns_401(self):
        resp = client.post(
            "/api/account/refresh",
            headers={"Authorization": "Bearer not-a-jwt"},
        )
        assert resp.status_code == 401

    def test_credentials_list_empty_for_fresh_user(self, auth_info):
        resp = client.get("/api/account/credentials", headers=auth_info["headers"])
        assert resp.status_code == 200
        assert resp.json() == []

    def test_credentials_list_returns_seeded_creds(self, auth_info):
        self._seed_credential(auth_info["user_id"], "cred-A", "Mac")
        self._seed_credential(auth_info["user_id"], "cred-B", "iPhone")

        resp = client.get("/api/account/credentials", headers=auth_info["headers"])
        assert resp.status_code == 200
        body = resp.json()
        ids = sorted(c["id"] for c in body)
        assert ids == ["cred-A", "cred-B"]
        names = sorted(c["device_name"] for c in body)
        assert names == ["Mac", "iPhone"]

    def test_delete_credential_removes_non_last(self, auth_info):
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

    def test_delete_last_credential_blocked(self, auth_info):
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

    def test_delete_nonexistent_credential_returns_404(self, auth_info):
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

    def test_account_endpoints_require_auth(self):
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
        sync.close()
        yield

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

    def test_score_returns_envelope_with_no_data(self):
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

    def test_score_history_validates_weeks_range(self):
        # weeks must be 1..52 per the route's Query(ge=1, le=52).
        resp = client.get("/api/intelligence/score/history?weeks=0", headers=auth_headers)
        assert resp.status_code == 422
        resp = client.get("/api/intelligence/score/history?weeks=53", headers=auth_headers)
        assert resp.status_code == 422
        # Valid value works.
        resp = client.get("/api/intelligence/score/history?weeks=4", headers=auth_headers)
        assert resp.status_code == 200

    # ── Digests ──────────────────────────────────────────────────────

    def test_digests_list_empty_initially(self):
        resp = client.get("/api/intelligence/digests", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json() == []

    def test_get_digest_404_when_missing(self):
        resp = client.get("/api/intelligence/digests/2026-01-05", headers=auth_headers)
        assert resp.status_code == 404
        body = resp.json()
        assert body["code"] == "NOT_FOUND"
        assert "Digest not found" in body["detail"]

    # ── Patterns + dismiss state machine ──────────────────────────────

    def test_patterns_returns_empty_when_no_user_insights_yet(self):
        resp = client.get("/api/intelligence/patterns", headers=auth_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["insights"] == []
        assert body["generated_at"]

    def test_patterns_filters_dismissed(self, auth_info):
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

    def test_dismiss_pattern_persists_across_requests(self, auth_info):
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

    def test_refresh_preserves_dismissed_ids(self, auth_info):
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

    def test_inbox_sorts_by_severity_high_first(self, auth_info):
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

    def test_inbox_honors_dismissed_patterns(self, auth_info):
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

    # ── Auth ──────────────────────────────────────────────────────────

    def test_endpoints_require_auth(self):
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
        ]:
            resp = client.request(method, path)
            assert resp.status_code == 401, f"{method} {path} should require auth"

    # ── Endpoint smoke coverage ──────────────────────────────────────
    # These exercise the GET endpoints that the existing tests in
    # this class don't hit — pinning the URL/method mapping +
    # response shape on the empty-user path. The IntelligenceService
    # logic itself is covered in test_domain.py; here we just want
    # the route handlers to actually run.

    def test_generate_digest_default_week_returns_envelope(self):
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

    def test_suggestions_returns_list_for_empty_user(self):
        """GET /suggestions on a user with no projects → []. Pin so
        a fresh account doesn't 500 on the dashboard's Daily Plan
        widget."""
        resp = client.get("/api/intelligence/suggestions", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json() == []

    def test_suggestions_accepts_date_query_param(self):
        """The optional ?date=YYYY-MM-DD param overrides today.
        Pin the alias — Pydantic uses `date` as the query param
        name (alias of `target_date`)."""
        resp = client.get(
            "/api/intelligence/suggestions?date=2026-04-15",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_focus_scores_returns_list_for_empty_user(self):
        """GET /focus-scores on a no-data day → []. Pin the empty-day
        contract — the UI's Focus Quality chart binds to the array
        and would crash on a dict."""
        resp = client.get("/api/intelligence/focus-scores", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json() == []

    def test_mood_returns_envelope_for_empty_user(self):
        """GET /mood with no notes → {correlation:{r,description},
        high_mood_avg_hours, low_mood_avg_hours, mood_trend}.
        Pin the keys — the Mood panel binds to the correlation
        nested object directly."""
        resp = client.get("/api/intelligence/mood", headers=auth_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert "correlation" in body
        assert body["correlation"]["r"] == 0
        assert body["correlation"]["description"] == "neutral"
        assert body["high_mood_avg_hours"] == 0
        assert body["low_mood_avg_hours"] == 0
        assert body["mood_trend"] == []

    def test_estimation_accuracy_returns_list_for_empty_user(self):
        """GET /estimation with no intentions → []. Pin so the
        Estimation Accuracy section renders an empty state."""
        resp = client.get("/api/intelligence/estimation", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json() == []

    def test_project_health_returns_list_for_empty_user(self):
        """GET /project-health with no projects → []. Pin the empty
        contract for first-run users."""
        resp = client.get("/api/intelligence/project-health", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json() == []


class TestAutoStartAPI:
    """/api/auto-start — webhook-triggered auto-start rules. Pinned
    behavior: the trigger endpoint matches the webhook payload's
    repository against rule.config['repo'] and starts the timer for
    the first match. Pins both happy paths and the no-match
    'started: false' branch (clients rely on this shape to display
    'no rule matched, ignored' in the GitHub webhook config UI)."""

    @pytest.fixture(autouse=True)
    def _reset_autostart_state(self):
        import os

        from pymongo import MongoClient

        dsn = os.environ.get("DB_DSN", "mongodb://localhost:27017")
        db_name = os.environ.get("DB_NAME", "beats_test")
        sync = MongoClient(dsn)
        db = sync[db_name]
        db.auto_start_rules.delete_many({})
        # Stop any timers from prior tests so trigger doesn't see a
        # leftover active beat.
        db.timeLogs.delete_many({})
        sync.close()
        yield

    def _create_project(self, name: str = "AutoStart Test") -> str:
        resp = client.post("/api/projects/", json={"name": name}, headers=auth_headers)
        assert resp.status_code == 201, resp.text
        return resp.json()["id"]

    def test_list_rules_empty_initially(self):
        resp = client.get("/api/auto-start/", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json() == []

    def test_create_then_list_rule(self):
        pid = self._create_project()
        resp = client.post(
            "/api/auto-start/",
            json={
                "type": "webhook_trigger",
                "project_id": pid,
                "config": {"repo": "ahmedElghable/beats"},
            },
            headers=auth_headers,
        )
        assert resp.status_code == 201, resp.text
        created = resp.json()
        assert created["type"] == "webhook_trigger"
        assert created["project_id"] == pid
        assert created["config"]["repo"] == "ahmedElghable/beats"
        assert created["enabled"] is True

        listing = client.get("/api/auto-start/", headers=auth_headers).json()
        assert len(listing) == 1
        assert listing[0]["id"] == created["id"]

    def test_delete_rule(self):
        pid = self._create_project()
        created = client.post(
            "/api/auto-start/",
            json={"type": "webhook_trigger", "project_id": pid, "config": {"repo": "x/y"}},
            headers=auth_headers,
        ).json()

        resp = client.delete(f"/api/auto-start/{created['id']}", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["deleted"] is True

        assert client.get("/api/auto-start/", headers=auth_headers).json() == []

    def test_trigger_starts_timer_for_matching_repo(self):
        pid = self._create_project("Webhook Match")
        client.post(
            "/api/auto-start/",
            json={"type": "webhook_trigger", "project_id": pid, "config": {"repo": "me/mine"}},
            headers=auth_headers,
        )

        resp = client.post(
            "/api/auto-start/trigger",
            json={"repository": "me/mine"},
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["started"] is True
        assert body["project_id"] == pid
        assert body["beat_id"]

    def test_trigger_no_match_returns_started_false(self):
        pid = self._create_project()
        client.post(
            "/api/auto-start/",
            json={"type": "webhook_trigger", "project_id": pid, "config": {"repo": "me/mine"}},
            headers=auth_headers,
        )

        resp = client.post(
            "/api/auto-start/trigger",
            json={"repository": "different/repo"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["started"] is False
        assert "No matching rule" in body["reason"]

    def test_trigger_with_no_rules_returns_started_false(self):
        resp = client.post(
            "/api/auto-start/trigger",
            json={"repository": "me/mine"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["started"] is False

    def test_trigger_only_matches_webhook_type_rules(self):
        """A 'schedule'-type rule whose config happens to contain a
        repo key must NOT fire from a webhook trigger — schedule
        rules are owned by the daemon's cron path, not this endpoint.
        Locks in the list_by_type('webhook_trigger') filter."""
        pid = self._create_project()
        client.post(
            "/api/auto-start/",
            json={
                "type": "schedule",
                "project_id": pid,
                "config": {"repo": "me/mine", "cron": "0 9 * * 1-5"},
            },
            headers=auth_headers,
        )

        resp = client.post(
            "/api/auto-start/trigger",
            json={"repository": "me/mine"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["started"] is False

    def test_trigger_swallows_already_running_into_started_false(self):
        """If the timer is already running, TimerService raises
        TimerAlreadyRunning. The route catches all exceptions and
        returns started=false with the reason — a webhook firing
        twice (e.g. GitHub retry) shouldn't 500 the handler."""
        pid = self._create_project("Already Running Project")
        client.post(
            "/api/auto-start/",
            json={"type": "webhook_trigger", "project_id": pid, "config": {"repo": "me/mine"}},
            headers=auth_headers,
        )

        first = client.post(
            "/api/auto-start/trigger",
            json={"repository": "me/mine"},
            headers=auth_headers,
        ).json()
        assert first["started"] is True

        resp = client.post(
            "/api/auto-start/trigger",
            json={"repository": "me/mine"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["started"] is False
        assert body["reason"]

    def test_endpoints_require_auth(self):
        for method, path in [
            ("GET", "/api/auto-start/"),
            ("POST", "/api/auto-start/"),
            ("DELETE", "/api/auto-start/anything"),
            ("POST", "/api/auto-start/trigger"),
        ]:
            resp = client.request(method, path)
            assert resp.status_code == 401, f"{method} {path} should require auth"


class TestDailyNotesAPI:
    """/api/daily-notes — end-of-day reflections (note + mood). Consumed
    by the EndOfDayReview modal in the UI and the coach's day context.
    Previously zero coverage; tests pin GET/PUT/POST round-trip,
    range listing, today-as-default, and the dual-method upsert."""

    @pytest.fixture(autouse=True)
    def _reset_daily_notes(self):
        import os

        from pymongo import MongoClient

        dsn = os.environ.get("DB_DSN", "mongodb://localhost:27017")
        db_name = os.environ.get("DB_NAME", "beats_test")
        sync = MongoClient(dsn)
        sync[db_name].daily_notes.delete_many({})
        sync.close()
        yield

    def test_get_returns_null_when_no_note_for_today(self):
        resp = client.get("/api/daily-notes", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json() is None

    def test_put_creates_note_and_get_returns_it(self):
        resp = client.put(
            "/api/daily-notes",
            json={"date": "2026-05-01", "note": "shipped X", "mood": 4},
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["note"] == "shipped X"
        assert body["mood"] == 4
        assert body["date"] == "2026-05-01"
        assert body["id"]

        # GET round-trips by date.
        resp = client.get("/api/daily-notes?target_date=2026-05-01", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["note"] == "shipped X"

    def test_put_is_idempotent_on_date(self):
        """The repo upserts on (user_id, date), so a second write for
        the same date overwrites — locks in that the EndOfDayReview's
        re-saves don't pile up duplicate rows."""
        for note, mood in [("first", 3), ("revised", 5)]:
            resp = client.put(
                "/api/daily-notes",
                json={"date": "2026-05-01", "note": note, "mood": mood},
                headers=auth_headers,
            )
            assert resp.status_code == 200

        body = client.get("/api/daily-notes?target_date=2026-05-01", headers=auth_headers).json()
        assert body["note"] == "revised"
        assert body["mood"] == 5

    def test_post_alias_works_for_older_clients(self):
        """The route accepts both PUT and POST so a client that posts
        doesn't silently 405. Pins this — without the dual decorator
        a stray POST would land somewhere unexpected."""
        resp = client.post(
            "/api/daily-notes",
            json={"date": "2026-05-02", "note": "via POST", "mood": 3},
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["note"] == "via POST"

    def test_get_today_default_when_no_target_date(self):
        from datetime import datetime as _dt

        today = _dt.now(UTC).date().isoformat()
        client.put(
            "/api/daily-notes",
            json={"date": today, "note": "today's reflection", "mood": 4},
            headers=auth_headers,
        )

        # No target_date → defaults to today.
        resp = client.get("/api/daily-notes", headers=auth_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body is not None
        assert body["note"] == "today's reflection"

    def test_range_returns_inclusive_window(self):
        # Seed three days; query a window that covers two of them.
        for d, note in [
            ("2026-04-29", "before"),
            ("2026-04-30", "in-window-1"),
            ("2026-05-01", "in-window-2"),
            ("2026-05-02", "after"),
        ]:
            client.put(
                "/api/daily-notes",
                json={"date": d, "note": note, "mood": 3},
                headers=auth_headers,
            )

        resp = client.get(
            "/api/daily-notes/range?start=2026-04-30&end=2026-05-01",
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        notes = sorted(n["note"] for n in body)
        assert notes == ["in-window-1", "in-window-2"]

    def test_mood_is_optional(self):
        resp = client.put(
            "/api/daily-notes",
            json={"date": "2026-05-03", "note": "no mood today"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["mood"] is None

    def test_endpoints_require_auth(self):
        for method, path in [
            ("GET", "/api/daily-notes"),
            ("GET", "/api/daily-notes/range?start=2026-01-01&end=2026-01-31"),
            ("PUT", "/api/daily-notes"),
            ("POST", "/api/daily-notes"),
        ]:
            resp = client.request(method, path)
            assert resp.status_code == 401, f"{method} {path} should require auth"


class TestWebhooksAPI:
    """/api/webhooks/* — CRUD + the daily-summary dispatch path. The
    dispatch path is the important one: it's fire-and-forget, was
    previously broken by an asyncio GC race (tasks reaped mid-flight
    because nothing held a strong ref), and now uses a module-level
    set to pin task references. Tests pin both the CRUD contract and
    the GC-race fix so a future refactor can't quietly regress."""

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
        yield

    # ── CRUD ──────────────────────────────────────────────────────────

    def test_list_webhooks_empty_initially(self):
        resp = client.get("/api/webhooks/", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json() == []

    def test_create_then_list_webhook(self):
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

    def test_create_uses_default_events_when_omitted(self):
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

    def test_delete_webhook(self):
        created = client.post(
            "/api/webhooks/",
            json={"url": "https://doomed.test/hook"},
            headers=auth_headers,
        ).json()

        resp = client.delete(f"/api/webhooks/{created['id']}", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["deleted"] is True

        assert client.get("/api/webhooks/", headers=auth_headers).json() == []

    # ── Daily summary dispatch ────────────────────────────────────────

    def test_daily_summary_returns_payload_shape(self):
        """Even with no beats and no subscribed webhooks, the endpoint
        produces the canonical payload shape that subscribers can rely
        on. Pins the schema."""
        resp = client.post(
            "/api/webhooks/daily-summary/trigger",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        # Required keys present even when there's nothing to report.
        for key in (
            "date",
            "total_minutes",
            "session_count",
            "project_breakdown",
            "intentions",
            "daily_note",
            "mood",
        ):
            assert key in body, f"missing {key} in payload"
        assert body["total_minutes"] == 0
        assert body["session_count"] == 0
        assert body["project_breakdown"] == []
        assert body["intentions"] == []
        assert body["daily_note"] is None
        assert body["mood"] is None

    def test_daily_summary_dispatch_pins_task_against_gc(self, monkeypatch):
        """The asyncio GC race fix: dispatch_webhook_event creates
        background tasks via asyncio.create_task and *must* hold a
        strong reference to each so the GC doesn't reap them
        mid-flight (the create_task docs warn about this explicitly).
        The module keeps an _pending_dispatches set; tasks discard
        themselves on completion.

        Test: monkeypatch httpx.AsyncClient with a fake whose POST
        never returns until we let it. After triggering the dispatch,
        assert the task IS in _pending_dispatches (the strong ref is
        held). If the fix regressed (e.g. someone replaced the set
        with create_task and forgot the pin), the assertion still
        passes if the GC hasn't run yet — but the live set membership
        is the contract we're locking."""
        import asyncio as _asyncio

        from beats.api.routers import webhooks as wh

        # Subscribe a webhook to the daily.summary event so the
        # dispatch loop has work to do.
        client.post(
            "/api/webhooks/",
            json={
                "url": "https://blackhole.test/hook",
                "events": ["daily.summary"],
            },
            headers=auth_headers,
        )

        # Replace AsyncClient.post with a coroutine that hangs forever
        # — a real slow webhook URL. The dispatch task remains alive
        # and visible in _pending_dispatches while we inspect it.
        gate = _asyncio.Event()  # never set → task pends

        class _FakeAsyncClient:
            def __init__(self, *_args, **_kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *_):
                return False

            async def post(self, *_args, **_kwargs):
                await gate.wait()

        monkeypatch.setattr(wh.httpx, "AsyncClient", _FakeAsyncClient)

        # Trigger.
        resp = client.post("/api/webhooks/daily-summary/trigger", headers=auth_headers)
        assert resp.status_code == 200

        # The task should be live in the pinning set. If the fix were
        # regressed (no strong ref), the GC could have already reaped
        # it; the set is the canonical pin and the contract we're
        # locking in.
        assert len(wh._pending_dispatches) >= 1, (
            "dispatch task missing from _pending_dispatches — the GC-pinning "
            "guarantee is broken. See routers/webhooks.py:124."
        )
        # And the pinned task must not be done — the body is gated on
        # an Event we never set, so it should still be running.
        assert all(not t.done() for t in wh._pending_dispatches)

        # Cleanly unblock and cancel so the test process exits clean.
        for t in list(wh._pending_dispatches):
            t.cancel()

    # ── Auth ──────────────────────────────────────────────────────────

    def test_webhook_endpoints_require_auth(self):
        for method, path in [
            ("GET", "/api/webhooks/"),
            ("POST", "/api/webhooks/"),
            ("DELETE", "/api/webhooks/anything"),
            ("POST", "/api/webhooks/daily-summary/trigger"),
        ]:
            resp = client.request(method, path)
            assert resp.status_code == 401, f"{method} {path} should require auth"


class TestPlanningAPI:
    """/api/plans/* — weekly plans, recurring intentions, weekly reviews,
    intention streaks. Previously zero coverage. Tests pin the
    template-application logic (day-of-week filter + dedup against
    existing) and the streak math (current walks back from today, best
    scans the full set), since those are the parts with real logic
    rather than thin CRUD."""

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
        for coll in (
            "weekly_plans",
            "recurring_intentions",
            "weekly_reviews",
            "intentions",
        ):
            db[coll].delete_many({})
        sync.close()
        yield

    # ── Weekly plans ──────────────────────────────────────────────────

    def test_get_weekly_plan_default_is_current_monday_empty_budgets(self):
        from datetime import date, timedelta

        resp = client.get("/api/plans/weekly", headers=auth_headers)
        assert resp.status_code == 200
        body = resp.json()
        expected_monday = (date.today() - timedelta(days=date.today().weekday())).isoformat()
        assert body["week_of"] == expected_monday
        assert body["budgets"] == []

    def test_put_weekly_plan_then_get_round_trips(self):
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

    def test_put_weekly_plan_upserts(self):
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

    # ── Recurring intentions ──────────────────────────────────────────

    def test_create_then_list_recurring_intention(self):
        resp = client.post(
            "/api/plans/recurring",
            json={"project_id": "p-x", "planned_minutes": 90, "days_of_week": [0, 2, 4]},
            headers=auth_headers,
        )
        assert resp.status_code == 201, resp.text
        created = resp.json()
        assert created["project_id"] == "p-x"
        assert created["planned_minutes"] == 90
        assert created["days_of_week"] == [0, 2, 4]
        assert created["enabled"] is True

        listing = client.get("/api/plans/recurring", headers=auth_headers).json()
        assert len(listing) == 1
        assert listing[0]["project_id"] == "p-x"

    def test_delete_recurring_intention(self):
        created = client.post(
            "/api/plans/recurring",
            json={"project_id": "p-doomed"},
            headers=auth_headers,
        ).json()

        resp = client.delete(f"/api/plans/recurring/{created['id']}", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["deleted"] is True

        assert client.get("/api/plans/recurring", headers=auth_headers).json() == []

    def test_apply_creates_intentions_for_matching_weekday(self):
        """Templates whose days_of_week includes today's weekday should
        produce intentions; others should not. Templates that match but
        whose project already has an intention today should be skipped
        (idempotent re-apply)."""
        from datetime import date

        today_dow = date.today().weekday()
        other_dow = (today_dow + 1) % 7

        # Matches today
        client.post(
            "/api/plans/recurring",
            json={
                "project_id": "fires-today",
                "planned_minutes": 45,
                "days_of_week": [today_dow],
            },
            headers=auth_headers,
        )
        # Doesn't match today
        client.post(
            "/api/plans/recurring",
            json={
                "project_id": "fires-other-day",
                "planned_minutes": 30,
                "days_of_week": [other_dow],
            },
            headers=auth_headers,
        )

        # First apply creates exactly the matching one.
        resp = client.post("/api/plans/recurring/apply", headers=auth_headers)
        assert resp.status_code == 200
        first = resp.json()
        assert first["created"] == 1
        assert first["date"] == date.today().isoformat()

        # Second apply is idempotent — the intention already exists.
        resp = client.post("/api/plans/recurring/apply", headers=auth_headers)
        assert resp.json()["created"] == 0

    # ── Weekly reviews ────────────────────────────────────────────────

    def test_get_weekly_review_default_returns_empty_shape(self):
        from datetime import date, timedelta

        resp = client.get("/api/plans/reviews/weekly", headers=auth_headers)
        assert resp.status_code == 200
        body = resp.json()
        expected = (date.today() - timedelta(days=date.today().weekday())).isoformat()
        assert body == {
            "week_of": expected,
            "went_well": "",
            "didnt_go_well": "",
            "to_change": "",
        }

    def test_upsert_weekly_review_round_trip(self):
        client.put(
            "/api/plans/reviews/weekly",
            json={
                "week_of": "2026-04-27",
                "went_well": "shipped feature X",
                "didnt_go_well": "too many context switches",
                "to_change": "block mornings for deep work",
            },
            headers=auth_headers,
        )
        body = client.get(
            "/api/plans/reviews/weekly?week_of=2026-04-27", headers=auth_headers
        ).json()
        assert body["went_well"] == "shipped feature X"
        assert body["didnt_go_well"] == "too many context switches"
        assert body["to_change"] == "block mornings for deep work"

    def test_recent_reviews_lists_in_recency_order(self):
        for week, note in [
            ("2026-03-30", "older"),
            ("2026-04-06", "middle"),
            ("2026-04-13", "newer"),
        ]:
            client.put(
                "/api/plans/reviews/weekly",
                json={"week_of": week, "went_well": note},
                headers=auth_headers,
            )

        body = client.get("/api/plans/reviews/weekly/recent", headers=auth_headers).json()
        assert len(body) == 3
        # repo.list_recent is by week descending — newest first.
        assert body[0]["week_of"] == "2026-04-13"
        assert body[-1]["week_of"] == "2026-03-30"

    # ── Streaks ───────────────────────────────────────────────────────

    def test_streaks_zero_on_no_data(self):
        resp = client.get("/api/plans/intention-streaks", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json() == {"current_streak": 0, "best_streak": 0}

    def test_streaks_count_only_days_where_all_intentions_completed(self, auth_info):
        """A day with one completed and one not-completed intention does
        NOT count — the current/best streaks both walk only the
        all-complete days. Locks in the predicate at planning.py:196."""
        import os
        from datetime import date, timedelta

        from bson import ObjectId
        from pymongo import MongoClient

        dsn = os.environ.get("DB_DSN", "mongodb://localhost:27017")
        db_name = os.environ.get("DB_NAME", "beats_test")
        sync = MongoClient(dsn)
        db = sync[db_name]

        user_id = auth_info["user_id"]
        today = date.today()
        yesterday = today - timedelta(days=1)
        # Today: two intentions, both completed → counts.
        # Yesterday: two intentions, one not completed → does not count.
        db.intentions.insert_many(
            [
                {
                    "_id": ObjectId(),
                    "user_id": user_id,
                    "project_id": "p1",
                    "date": today.isoformat(),
                    "planned_minutes": 60,
                    "completed": True,
                },
                {
                    "_id": ObjectId(),
                    "user_id": user_id,
                    "project_id": "p2",
                    "date": today.isoformat(),
                    "planned_minutes": 60,
                    "completed": True,
                },
                {
                    "_id": ObjectId(),
                    "user_id": user_id,
                    "project_id": "p1",
                    "date": yesterday.isoformat(),
                    "planned_minutes": 60,
                    "completed": True,
                },
                {
                    "_id": ObjectId(),
                    "user_id": user_id,
                    "project_id": "p2",
                    "date": yesterday.isoformat(),
                    "planned_minutes": 60,
                    "completed": False,  # ← breaks the streak
                },
            ]
        )
        sync.close()

        body = client.get("/api/plans/intention-streaks", headers=auth_headers).json()
        # Today is the only fully-complete day → current = 1, best = 1.
        assert body == {"current_streak": 1, "best_streak": 1}

    # ── Auth ──────────────────────────────────────────────────────────

    def test_planning_endpoints_require_auth(self):
        for method, path in [
            ("GET", "/api/plans/weekly"),
            ("PUT", "/api/plans/weekly"),
            ("GET", "/api/plans/recurring"),
            ("POST", "/api/plans/recurring"),
            ("POST", "/api/plans/recurring/apply"),
            ("GET", "/api/plans/reviews/weekly"),
            ("PUT", "/api/plans/reviews/weekly"),
            ("GET", "/api/plans/reviews/weekly/recent"),
            ("GET", "/api/plans/intention-streaks"),
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

    def test_orphan_user_can_retry_register_start(self):
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
        yield

    def _db(self):
        import os

        from pymongo import MongoClient

        dsn = os.environ.get("DB_DSN", "mongodb://localhost:27017")
        db_name = os.environ.get("DB_NAME", "beats_test")
        sync_client = MongoClient(dsn)
        return sync_client, sync_client[db_name]

    def test_register_start_existing_email_with_credentials_returns_409(self):
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

    def test_register_verify_without_pending_returns_400(self):
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

    def test_login_verify_with_invalid_credential_returns_401(self):
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

    def test_login_options_returns_options_dict(self):
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

    def test_register_start_brand_new_email_creates_user(self):
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

    def test_register_verify_value_error_returns_400_envelope(self, monkeypatch):
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
        async def fake_verify_registration(*args, **kwargs):  # noqa: ARG001
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

    def test_login_options_rate_limited(self):
        """GET /api/auth/login/options is rate-limited after repeated requests."""
        for _ in range(10):
            client.get("/api/auth/login/options")

        response = client.get("/api/auth/login/options")
        assert response.status_code == 429

    def test_pair_exchange_rate_limited(self):
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

    def test_projects_isolated_between_users(self):
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

    def test_flow_windows_isolated_between_users(self):
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

        # Try accessing rhythm (not in DEVICE_ALLOWED_PREFIXES — only /heatmap is)
        resp = client.get("/api/analytics/rhythm", headers=device_headers)
        assert resp.status_code == 403

    def test_device_token_allowed_on_analytics_heatmap(self):
        """Device tokens can read the heatmap (companion timer-screen totals)."""
        resp = client.post("/api/device/pair/code", headers=auth_headers)
        code = resp.json()["code"]
        resp = client.post("/api/device/pair/exchange", json={"code": code})
        device_token = resp.json()["device_token"]
        device_headers = {"Authorization": f"Bearer {device_token}"}

        resp = client.get("/api/analytics/heatmap", headers=device_headers)
        assert resp.status_code == 200

    def test_device_token_allowed_on_analytics_tags(self):
        """Device tokens can read /api/analytics/tags — used by companion's
        post-stop prompt to suggest recent tags as one-tap chips."""
        resp = client.post("/api/device/pair/code", headers=auth_headers)
        code = resp.json()["code"]
        resp = client.post("/api/device/pair/exchange", json={"code": code})
        device_token = resp.json()["device_token"]
        device_headers = {"Authorization": f"Bearer {device_token}"}

        resp = client.get("/api/analytics/tags", headers=device_headers)
        assert resp.status_code == 200

    def test_device_token_allowed_on_beats(self):
        """Device tokens can read /api/beats — used by companion's post-stop
        'How did it go?' prompt to update the just-stopped beat with note + tags."""
        resp = client.post("/api/device/pair/code", headers=auth_headers)
        code = resp.json()["code"]
        resp = client.post("/api/device/pair/exchange", json={"code": code})
        device_token = resp.json()["device_token"]
        device_headers = {"Authorization": f"Bearer {device_token}"}

        resp = client.get("/api/beats/", headers=device_headers)
        assert resp.status_code == 200

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
        body = resp.json()
        assert "revoked" in body["detail"]
        assert body["code"] == "DEVICE_REVOKED"

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

    def test_device_status_shape_is_what_the_wall_clock_reads(self):
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
            assert isinstance(component, int) and 0 <= component <= 255, component

        # When clocked_in is True, project_color_rgb / elapsed_minutes
        # / project_name / project_id are also present. Default fresh-
        # user state has no active timer so we don't exercise that
        # branch here — but the firmware's struct provides defaults
        # for all of them, so the un-clocked-in path is the
        # interesting one to lock.
        assert body["clocked_in"] is False
        assert body["daily_total_minutes"] == 0
        assert body["energy_level"] == 0

    def test_device_favorites_shape_is_what_the_wall_clock_reads(self):
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
            assert "id" in fav and "name" in fav, fav
            # color_rgb is the int[3] the wall-clock's rgbFromArray reads.
            # NOT "color" (the previously-misnamed hex-string key).
            assert "color_rgb" in fav, fav
            assert "color" not in fav, (
                f"unexpected legacy 'color' key — wall-clock reads color_rgb: {fav}"
            )
            assert isinstance(fav["color_rgb"], list) and len(fav["color_rgb"]) == 3

    def test_device_weekly_returns_seven_days_oldest_first(self):
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

    def test_device_heartbeat_persists_telemetry_for_get(self):
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

    def _pair_device(self):
        """Helper: pair a device and return (device_token, device_headers)."""
        resp = client.post("/api/device/pair/code", headers=auth_headers)
        code = resp.json()["code"]
        resp = client.post("/api/device/pair/exchange", json={"code": code})
        data = resp.json()
        return data["device_token"], {"Authorization": f"Bearer {data['device_token']}"}

    def test_suggest_timer_matches_editor_repo_against_autostart_repos(self):
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

        _, device_headers = self._pair_device()
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

    def test_suggest_timer_falls_back_to_category_when_no_editor_repo_match(self):
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

        _, device_headers = self._pair_device()
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

    def test_create_project_with_category_persists(self):
        """Regression guard: the create handler used to ignore the
        \`category\` field — the schema accepted it but the route never
        forwarded it to the domain Project, so a freshly-created
        project's category was always None until a separate PUT.
        That broke the daemon's flow-score category_fit silently
        for new projects.

        The fix lives at api/src/beats/api/routers/projects.py
        (create_project + update_project both forward category +
        autostart_repos now). Test asserts the round-trip.
        """
        resp = client.post(
            "/api/projects/",
            json={"name": "Drift Test Coding", "category": "coding"},
            headers=auth_headers,
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["category"] == "coding", body

        # Read back via list + by-id to confirm persistence.
        resp = client.get("/api/projects/", headers=auth_headers)
        match = next(p for p in resp.json() if p["id"] == body["id"])
        assert match["category"] == "coding"

    def test_update_project_persists_autostart_repos(self):
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

    def test_update_project_rejects_invalid_goal_type_with_422(self):
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

    def test_update_project_accepts_valid_goal_types(self):
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

    def test_timer_context_no_active_timer(self):
        """GET /api/signals/timer-context returns timer_running=false
        with empty project fields when no timer is running. The daemon's
        pollTimerContext goroutine reads this every 30s; the shield uses
        the boolean to gate drift detection (no drift when no timer).
        """
        _, device_headers = self._pair_device()
        resp = client.get("/api/signals/timer-context", headers=device_headers)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["timer_running"] is False
        # project_id / project_category are present-but-null when no timer.
        # The daemon's TimerContextResponse struct decodes these as
        # empty strings via Go's zero-value default for missing JSON.
        assert "project_id" in body
        assert "project_category" in body

    def test_timer_context_with_active_timer_carries_category(self):
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

        _, device_headers = self._pair_device()
        resp = client.get("/api/signals/timer-context", headers=device_headers)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["timer_running"] is True
        assert body["project_id"] == project_id
        assert body["project_category"] == "coding"

    def test_post_drift_event_records_flow_window_with_drift_category(self):
        """POST /api/signals/drift records a FlowWindow with category=drift.

        The daemon's distraction shield POSTs to this endpoint when
        the user drifts to a known time-sink while a timer is running
        (commit a3b8f3f). Until that commit shipped, the endpoint
        existed but no caller invoked it — and there was no API-side
        test to catch a regression. Locks in the behavior the daemon
        relies on: 201 + an id, and the resulting record reads back
        with category="drift" so the UI's history view can filter."""
        _, device_headers = self._pair_device()
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

    def test_post_drift_event_requires_auth(self):
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

    def test_post_drift_event_validates_required_fields(self):
        """Missing required fields (started_at / duration_seconds /
        bundle_id) trip the unified 422 envelope, same shape the
        daemon's describeErrorBody knows how to surface."""
        _, device_headers = self._pair_device()
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

    def test_flow_window_round_trips_editor_context(self):
        """Editor heartbeat fields (repo, branch, language) round-trip."""
        _, device_headers = self._pair_device()
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

    def test_flow_windows_filter_by_project_id(self):
        """GET /api/signals/flow-windows?project_id=X returns only windows
        whose active_project_id matches."""
        _, device_headers = self._pair_device()
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

    def test_flow_windows_filter_by_editor_repo(self):
        """GET /api/signals/flow-windows?editor_repo=… narrows to that
        workspace path, used by future per-repo UI views."""
        _, device_headers = self._pair_device()
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

    def test_flow_windows_filter_by_editor_language(self):
        """GET /api/signals/flow-windows?editor_language=… narrows to that
        language id, used for click-to-filter on FlowByLanguage."""
        _, device_headers = self._pair_device()
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

    def test_flow_windows_summary_aggregates_and_picks_top_buckets(self):
        """GET /api/signals/flow-windows/summary returns avg/peak/count
        plus the top bucket on each grouping axis in a single round-trip,
        honoring the same filter params as the JSON endpoint."""
        _, device_headers = self._pair_device()
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

    def test_flow_windows_summary_empty_slice_returns_zeros(self):
        """No windows in the range → zero/None response, not 404 — callers
        can render an empty state without parsing an error."""
        self._pair_device()
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

    def test_flow_windows_summary_respects_filter(self):
        """The summary honors the language filter — same slice the user
        sees in the chip-row download is what the summary endpoint
        aggregates. Uses a unique marker repo to avoid pollution from
        other tests in this shared-state class."""
        _, device_headers = self._pair_device()
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

    def test_flow_windows_csv_export_respects_filter(self):
        """GET /api/signals/flow-windows.csv streams a CSV that honors
        the same filter params as the JSON endpoint, so the "Download"
        button on Insights returns exactly the visible slice."""
        _, device_headers = self._pair_device()
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

    def test_flow_windows_filter_by_bundle_id(self):
        """GET /api/signals/flow-windows?bundle_id=… narrows to that
        macOS bundle id, used for click-to-filter on FlowByApp."""
        _, device_headers = self._pair_device()
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

    def test_flow_window_without_editor_context_still_validates(self):
        """Older daemons that don't send editor_* fields are still accepted."""
        _, device_headers = self._pair_device()
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
        resp = client.get("/api/analytics/rhythm", headers=device_headers)
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

    def test_calendar_auth_url_returns_google_consent_url(self, auth_info):
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

    def test_calendar_status_connected_when_integration_exists(self, auth_info):
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

    def test_calendar_status_disconnected_when_no_doc(self, auth_info):
        """GET /api/calendar/status with no integration → connected:
        False, provider: None. Pin so the UI can render the
        "Connect Calendar" button on first load."""
        resp = client.get("/api/calendar/status", headers=auth_info["headers"])
        assert resp.status_code == 200
        body = resp.json()
        assert body["connected"] is False
        assert body["provider"] is None

    def test_calendar_events_empty_when_not_connected(self, auth_info):
        """GET /api/calendar/events without an integration → []
        (not 500, not "connection required" error). Pin so the
        coach's day context falls through gracefully when the
        user hasn't connected calendar."""
        resp = client.get("/api/calendar/events", headers=auth_info["headers"])
        assert resp.status_code == 200
        assert resp.json() == []

    def test_calendar_disconnect_returns_false_when_not_connected(self, auth_info):
        """DELETE /api/calendar/disconnect without an integration →
        disconnected: False (idempotent). Pin so a "disconnect"
        button click on an already-disconnected account doesn't
        500 the user."""
        resp = client.delete("/api/calendar/disconnect", headers=auth_info["headers"])
        assert resp.status_code == 200
        assert resp.json()["disconnected"] is False

    # -------- /api/github --------

    def test_github_auth_url_returns_github_consent_url(self, auth_info):
        """GET /api/github/auth-url returns the GitHub OAuth URL."""
        resp = client.get("/api/github/auth-url", headers=auth_info["headers"])
        assert resp.status_code == 200
        url = resp.json()["url"]
        assert url.startswith("https://github.com/login/oauth/authorize?")

    def test_github_status_connected_when_integration_exists(self, auth_info):
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

    def test_github_status_disconnected_when_no_doc(self, auth_info):
        resp = client.get("/api/github/status", headers=auth_info["headers"])
        assert resp.status_code == 200
        body = resp.json()
        assert body["connected"] is False
        assert body["github_username"] is None

    def test_github_disconnect_returns_true_when_connected(self, auth_info):
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

    def test_fitbit_auth_url_returns_fitbit_consent_url(self, auth_info):
        resp = client.get("/api/fitbit/auth-url", headers=auth_info["headers"])
        assert resp.status_code == 200
        url = resp.json()["url"]
        assert url.startswith("https://www.fitbit.com/oauth2/authorize?")

    def test_fitbit_status_connected_reports_user_id(self, auth_info):
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

    def test_fitbit_disconnect_returns_true_when_connected(self, auth_info):
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

    def test_oura_status_connected_reports_user_id(self, auth_info):
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

    def test_oura_disconnect_returns_false_when_not_connected(self, auth_info):
        """DELETE /api/oura/disconnect without an integration →
        disconnected: False. Same idempotent contract as
        calendar/disconnect."""
        resp = client.delete("/api/oura/disconnect", headers=auth_info["headers"])
        assert resp.status_code == 200
        assert resp.json()["disconnected"] is False

    # -------- Auth wall — unauthenticated requests rejected --------

    def test_calendar_auth_url_requires_auth(self):
        """GET /api/calendar/auth-url without a token → 401.
        Pin the auth gate so an unauthenticated caller can't
        even discover the OAuth flow start URL."""
        resp = client.get("/api/calendar/auth-url")
        assert resp.status_code == 401

    def test_oura_status_requires_auth(self):
        resp = client.get("/api/oura/status")
        assert resp.status_code == 401
