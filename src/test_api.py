"""
---------------- pytest -----------------------
How to write pytest classes or functions?
Write my first test case to do the following
---------- First TestCase donne ---------------
"""
import time

from fastapi.testclient import TestClient
from server import app

client = TestClient(app)


class TestProjectAPI:
    def test_projects_list_api(self):
        response = client.get("/projects")
        assert response.status_code == 200
        projects = response.json()
        assert len(projects) >= 1

    def test_projects_create_api(self):
        projects_count = len(client.get("/projects").json())

        response = client.post(
            "/projects",
            json={"name": f"test-project-{time.time()}", "description": "Test project - delete me"},
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 201, response.json()

        assert len(client.get("/projects").json()) == projects_count + 1

    def test_projects_retrieve_api(self):
        response = client.post(
            "/projects",
            json={"name": "test-project-{}".format(time.time()), "description": "Test project - delete me"},
            headers={"Content-Type": "application/json"}
        )

    def test_projects_update_api(self):
        response = client.post(
            "/projects",
            json={"name": "test-project-{}".format(time.time()), "description": "Test project - delete me"},
            headers={"Content-Type": "application/json"}
        )
        projects_count = len(client.get("/projects").json())

        project = response.json()
        project["name"] = "Updated-" + project["name"]
        response = client.put(
            "/projects",
            json=project
        )
        assert response.status_code == 200, response.json()
        assert len(client.get("/projects").json()) == projects_count


class TestTimeLogsDirectAPI:
    def test_create_api(self):
        project = client.post(
            "/projects",
            json={"name": "test-project-{}".format(time.time()), "description": "Test project - delete me"},
        ).json()

        response = client.post(
            "/timelogs",
            json={"project_id": project["id"], "start": "2020-04-01T02:0:0", "end": "2020-04-01T03:0:0"}
        )
        assert response.status_code == 201, response.json()

    def test_list_api_with_project_filter(self):
        project = client.post(
            "/projects",
            json={"name": "test-project-{}".format(time.time()), "description": "Test project - delete me"},
        ).json()

        client.post(
            "/timelogs",
            json={"project_id": project["id"], "start": "2020-04-01T02:0:0", "end": "2020-04-01T03:0:0"}
        )
        client.post(
            "/timelogs",
            json={"project_id": project["id"], "start": "2020-04-01T02:0:0", "end": "2020-04-01T03:0:0"}
        )

        response = client.get(f"/timelogs?project_id={project['id']}")
        assert response.status_code == 200
        assert len(response.json()) == 2

    def test_list_api_with_date_filter(self):
        pass  # Can not implement this until we find a way to clean the db after usage

    def test_update_api(self):
        project = client.post(
            "/projects",
            json={"name": "test-project-{}".format(time.time()), "description": "Test project - delete me"},
        ).json()

        timelog = client.post(
            "/timelogs",
            json={"project_id": project["id"], "start": "2020-04-01T02:0:0", "end": "2020-04-01T03:0:0"}
        ).json()
        timelog["end"] = "2020-04-01T04:10:10"
        response = client.put(
            "/timelogs", json=timelog
        )
        assert response.status_code == 200, response.json()

        response = client.get(f"/timelogs/{timelog['id']}")
        assert response.status_code == 200, response.json()
        assert response.json()["end"] == "2020-04-01T04:10:10"
