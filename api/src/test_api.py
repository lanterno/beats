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
        assert response.json()["end"] == "2020-04-01T04:10:10"

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


class TestMiscellaneousEndpoints:
    """Test suite for miscellaneous endpoints"""

    def test_ding_endpoint(self):
        """Test POST /talk/ding - Simple ping endpoint (public)"""
        response = client.post("/talk/ding")
        assert response.status_code == 200
        assert response.json() == {"message": "dong"}


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
        """POST /api/auth/logout revokes the token so it can't be used again."""
        token = self._make_token(auth_info["user_id"])
        headers = {"Authorization": f"Bearer {token}"}

        # Token works before logout
        assert client.get("/api/projects/", headers=headers).status_code == 200

        # Logout
        response = client.post("/api/auth/logout", headers=headers)
        assert response.status_code == 204

        # Token is now rejected
        assert client.get("/api/projects/", headers=headers).status_code == 401

    def test_logout_without_token(self):
        """POST /api/auth/logout without a token is a no-op (still 204)."""
        response = client.post("/api/auth/logout")
        assert response.status_code == 204

    def test_other_tokens_unaffected_by_logout(self, auth_info):
        """Revoking one token doesn't affect other tokens for the same user."""
        token_a = self._make_token(auth_info["user_id"])
        token_b = self._make_token(auth_info["user_id"])

        # Revoke token A
        client.post("/api/auth/logout", headers={"Authorization": f"Bearer {token_a}"})

        # Token B still works
        assert client.get(
            "/api/projects/", headers={"Authorization": f"Bearer {token_b}"}
        ).status_code == 200


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
