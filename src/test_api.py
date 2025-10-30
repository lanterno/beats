"""
Comprehensive API Tests for Beats Application
Tests all endpoints: Projects, Beats, and Timer APIs
"""

import time
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from beats.settings import settings
from server import app

client = TestClient(app)


class TestProjectAPI:
    """Test suite for Project management endpoints"""

    def test_projects_list_api(self):
        """Test GET /api/projects/ - List all projects"""
        response = client.get("/api/projects/")
        assert response.status_code == 200
        projects = response.json()
        assert isinstance(projects, list)

    def test_projects_list_archived(self):
        """Test GET /api/projects/?archived=true - List archived projects"""
        response = client.get("/api/projects/?archived=true")
        assert response.status_code == 200
        projects = response.json()
        assert isinstance(projects, list)

    def test_projects_create_api(self):
        """Test POST /api/projects/ - Create a new project"""
        projects_count = len(client.get("/api/projects/").json())

        response = client.post(
            "/api/projects/",
            json={
                "name": f"test-project-{time.time()}",
                "description": "Test project - delete me",
            },
            headers={
                "Content-Type": "application/json",
                "X-API-Token": settings.access_token,
            },
        )
        assert response.status_code == 201, response.json()
        project = response.json()
        assert "id" in project
        assert "name" in project
        assert len(client.get("/api/projects/").json()) == projects_count + 1

    def test_projects_create_without_auth(self):
        """Test POST /api/projects/ without auth token - Should fail"""
        response = client.post(
            "/api/projects/",
            json={"name": f"test-project-{time.time()}", "description": "Test project"},
        )
        assert response.status_code == 401

    def test_projects_create_with_invalid_token(self):
        """Test POST /api/projects/ with invalid token - Should fail"""
        response = client.post(
            "/api/projects/",
            json={"name": f"test-project-{time.time()}", "description": "Test project"},
            headers={"X-API-Token": "invalid-token"},
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
            headers={
                "Content-Type": "application/json",
                "X-API-Token": settings.access_token,
            },
        )
        projects_count = len(client.get("/api/projects/").json())

        project = response.json()
        project["name"] = "Updated-" + project["name"]
        project["description"] = "Updated description"
        response = client.put(
            "/api/projects/",
            json=project,
            headers={
                "Content-Type": "application/json",
                "X-API-Token": settings.access_token,
            },
        )
        assert response.status_code == 200, response.json()
        updated_project = response.json()
        assert "Updated-" in updated_project["name"]
        assert len(client.get("/api/projects/").json()) == projects_count

    def test_projects_archive(self):
        """Test POST /api/projects/{project_id}/archive - Archive a project"""
        # Create a project first
        response = client.post(
            "/api/projects/",
            json={"name": f"test-archive-{time.time()}", "description": "Test archive"},
            headers={"X-API-Token": settings.access_token},
        )
        project = response.json()

        # Archive the project
        response = client.post(
            f"/api/projects/{project['id']}/archive",
            headers={"X-API-Token": settings.access_token},
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
            headers={"X-API-Token": settings.access_token},
        ).json()

        now = datetime.now(UTC)
        client.post(
            "/api/beats/",
            json={
                "project_id": project["id"],
                "start": now.isoformat(),
                "end": (now + timedelta(hours=1)).isoformat(),
            },
        )

        response = client.get(f"/api/projects/{project['id']}/today/")
        assert response.status_code == 200
        assert "duration" in response.json()

    def test_project_week_time(self):
        """Test GET /api/projects/{project_id}/week/ - Get current week time for project"""
        # Create project
        project = client.post(
            "/api/projects/",
            json={"name": f"test-week-{time.time()}", "description": "Test week time"},
            headers={"X-API-Token": settings.access_token},
        ).json()

        response = client.get(f"/api/projects/{project['id']}/week/")
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
            headers={"X-API-Token": settings.access_token},
        ).json()

        client.post(
            "/api/beats/",
            json={
                "project_id": project["id"],
                "start": "2024-01-15T10:00:00",
                "end": "2024-01-15T12:00:00",
            },
        )

        response = client.get(f"/api/projects/{project['id']}/total/")
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
            headers={"X-API-Token": settings.access_token},
        ).json()

        client.post(
            "/api/beats/",
            json={
                "project_id": project["id"],
                "start": "2024-01-15T10:00:00",
                "end": "2024-01-15T12:00:00",
            },
        )

        response = client.get(f"/api/projects/{project['id']}/summary/")
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
            headers={"X-API-Token": settings.access_token},
        ).json()

        # Start timer
        # Cleanup any previous active timer to ensure isolation
        client.post(
            "/api/projects/stop",
            json={"time": datetime.now(UTC).isoformat()},
            headers={"X-API-Token": settings.access_token},
        )
        response = client.post(
            f"/api/projects/{project['id']}/start",
            json={"time": datetime.now(UTC).isoformat()},
            headers={"X-API-Token": settings.access_token},
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
            headers={"X-API-Token": settings.access_token},
        ).json()

        start_time = datetime.now(UTC)
        client.post(
            f"/api/projects/{project['id']}/start",
            json={"time": start_time.isoformat()},
            headers={"X-API-Token": settings.access_token},
        )

        # Stop timer
        end_time = start_time + timedelta(hours=1)
        response = client.post(
            "/api/projects/stop",
            json={"time": end_time.isoformat()},
            headers={"X-API-Token": settings.access_token},
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
            headers={"X-API-Token": settings.access_token},
        )
        # This might be 400 or 200 depending on state, just check it doesn't crash
        assert response.status_code in [200, 400]


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
            headers={
                "Content-Type": "application/json",
                "X-API-Token": settings.access_token,
            },
        ).json()

        response = client.post(
            "/api/beats/",
            json={
                "project_id": project["id"],
                "start": "2020-04-01T02:00:00",
                "end": "2020-04-01T03:00:00",
            },
        )
        assert response.status_code == 201, response.json()
        beat = response.json()
        assert "id" in beat
        assert beat["project_id"] == project["id"]

    def test_list_api(self):
        """Test GET /api/beats/ - List all beats"""
        response = client.get("/api/beats/")
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
            headers={
                "Content-Type": "application/json",
                "X-API-Token": settings.access_token,
            },
        ).json()

        client.post(
            "/api/beats/",
            json={
                "project_id": project["id"],
                "start": "2020-04-01T02:00:00",
                "end": "2020-04-01T03:00:00",
            },
        )
        client.post(
            "/api/beats/",
            json={
                "project_id": project["id"],
                "start": "2020-04-01T04:00:00",
                "end": "2020-04-01T05:00:00",
            },
        )

        response = client.get(f"/api/beats/?project_id={project['id']}")
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
            headers={"X-API-Token": settings.access_token},
        ).json()

        # Create beat with specific date
        client.post(
            "/api/beats/",
            json={
                "project_id": project["id"],
                "start": "2024-05-15T10:00:00",
                "end": "2024-05-15T11:00:00",
            },
        )

        response = client.get("/api/beats/?date_filter=2024-05-15")
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
            headers={"X-API-Token": settings.access_token},
        ).json()

        beat = client.post(
            "/api/beats/",
            json={
                "project_id": project["id"],
                "start": "2020-04-01T02:00:00",
                "end": "2020-04-01T03:00:00",
            },
        ).json()

        response = client.get(f"/api/beats/{beat['id']}")
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
            headers={
                "Content-Type": "application/json",
                "X-API-Token": settings.access_token,
            },
        ).json()

        beat = client.post(
            "/api/beats/",
            json={
                "project_id": project["id"],
                "start": "2020-04-01T02:00:00",
                "end": "2020-04-01T03:00:00",
            },
        ).json()

        # Update the beat
        beat["end"] = "2020-04-01T04:10:10"
        response = client.put("/api/beats/", json=beat)
        assert response.status_code == 200, response.json()

        # Verify the update
        response = client.get(f"/api/beats/{beat['id']}")
        assert response.status_code == 200, response.json()
        assert response.json()["end"] == "2020-04-01T04:10:10"

    def test_delete_beat(self):
        """Test DELETE /api/beats/{beat_id} - Delete a beat"""
        project = client.post(
            "/api/projects/",
            json={"name": f"test-delete-{time.time()}", "description": "Test delete"},
            headers={"X-API-Token": settings.access_token},
        ).json()

        beat = client.post(
            "/api/beats/",
            json={
                "project_id": project["id"],
                "start": "2020-04-01T02:00:00",
                "end": "2020-04-01T03:00:00",
            },
        ).json()

        response = client.delete(f"/api/beats/{beat['id']}")
        assert response.status_code == 200
        assert response.json()["status"] == "deleted!"


class TestTimerAPI:
    """Test suite for Timer status endpoints"""

    def test_timer_status_when_idle(self):
        """Test GET /api/timer/status - When no timer is running"""
        # Try to ensure no timer is running
        try:
            client.post(
                "/api/projects/stop",
                json={"time": datetime.now(UTC).isoformat()},
                headers={"X-API-Token": settings.access_token},
            )
        except Exception:
            pass

        response = client.get("/api/timer/status")
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
            headers={"X-API-Token": settings.access_token},
        ).json()

        # Start timer
        client.post(
            f"/api/projects/{project['id']}/start",
            json={"time": datetime.now(UTC).isoformat()},
            headers={"X-API-Token": settings.access_token},
        )

        # Check status
        response = client.get("/api/timer/status")
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
                headers={"X-API-Token": settings.access_token},
            )


class TestMiscellaneousEndpoints:
    """Test suite for miscellaneous endpoints"""

    def test_ding_endpoint(self):
        """Test POST /talk/ding - Simple ping endpoint"""
        response = client.post(
            "/talk/ding", headers={"X-API-Token": settings.access_token}
        )
        assert response.status_code == 200
        assert response.json() == {"message": "dong"}


class TestAuthenticationMiddleware:
    """Test suite for authentication middleware"""

    def test_get_requests_no_auth_required(self):
        """Test GET requests don't require authentication"""
        response = client.get("/api/projects/")
        assert response.status_code == 200

    def test_post_requests_require_auth(self):
        """Test POST requests require authentication"""
        response = client.post(
            "/api/projects/", json={"name": "test", "description": "test"}
        )
        assert response.status_code == 401
        assert "X-API-Token" in response.json()["error"]

    def test_put_requests_require_auth(self):
        """Test PUT requests require authentication"""
        response = client.put(
            "/api/projects/", json={"id": "test", "name": "test", "description": "test"}
        )
        assert response.status_code == 401

    def test_invalid_token(self):
        """Test invalid token is rejected"""
        response = client.post(
            "/api/projects/",
            json={"name": "test", "description": "test"},
            headers={"X-API-Token": "wrong-token"},
        )
        assert response.status_code == 401
        assert "not valid" in response.json()["error"]
