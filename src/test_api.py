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
