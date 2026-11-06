"""Sessions and the timer: direct writes, edits, one timer at a time.

Split out of `test_api.py` at the ceiling in roadmaps/file-sizes.md; the
harness is `conftest.py`'s and the shared fixtures `api_helpers.py`'s.
"""

import contextlib
import json
import time
from datetime import UTC, datetime

import pytest


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


class TestBeatEdit:
    """PUT /api/beats/ changes what the request carries — the project, the
    start, the end and, since #348, a note that is actually sent — and the
    tags those times derive, and nothing else. The note's wire rule: a
    string sets it, an empty string clears it, omitted keeps it as stored —
    so the daemon, the companion and the extension, which send none, keep
    meaning what they meant, and an edit that rebuilt the session from the
    request still cannot erase one."""

    START = "2026-04-01T09:00:00Z"
    END = "2026-04-01T09:30:00Z"

    @staticmethod
    def _project(client, headers) -> str:
        resp = client.post("/api/projects/", json={"name": "Edit"}, headers=headers)
        assert resp.status_code == 201, resp.text
        return resp.json()["id"]

    def _session(self, client, headers, *, note: str | None = None, tags=()) -> dict:
        """A finished session, with the note and tags an import brings."""
        project_id = self._project(client, headers)
        beat = client.post(
            "/api/beats/",
            json={"project_id": project_id, "start": self.START, "end": self.END},
            headers=headers,
        ).json()
        backup = {"beats": [{**beat, "note": note, "tags": list(tags)}]}
        imported = client.post(
            "/api/export/import",
            files={"file": ("backup.json", json.dumps(backup), "application/json")},
            headers=headers,
        )
        assert imported.status_code == 200, imported.text
        return beat

    @staticmethod
    def _edit(client, headers, beat: dict, **changes):
        """The body the companion sends: the four fields, nothing else."""
        body = {k: beat[k] for k in ("id", "project_id", "start", "end")}
        return client.put("/api/beats/", json={**body, **changes}, headers=headers)

    @staticmethod
    def _window(client, headers, start: str, end: str, repo: str) -> None:
        resp = client.post(
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
                "editor_language": "Go",
            },
            headers=headers,
        )
        assert resp.status_code in (200, 201), resp.text

    def test_a_time_edit_keeps_the_note(self, client, auth_headers):
        beat = self._session(client, auth_headers, note="Call with the auditors")

        resp = self._edit(client, auth_headers, beat, end="2026-04-01T10:15:00Z")

        assert resp.status_code == 200, resp.text
        assert resp.json()["note"] == "Call with the auditors"
        stored = client.get(f"/api/beats/{beat['id']}", headers=auth_headers).json()
        assert stored["end"].startswith("2026-04-01T10:15:00")
        assert stored["note"] == "Call with the auditors"

    def test_a_sent_note_sets_and_an_empty_one_clears(self, client, auth_headers):
        """#348: the one free-text input writes through here."""
        beat = self._session(client, auth_headers, note="From the import")

        written = self._edit(client, auth_headers, beat, note="  Standup and review  ")
        assert written.status_code == 200, written.text
        assert written.json()["note"] == "Standup and review"

        cleared = self._edit(client, auth_headers, beat, note="")
        assert cleared.status_code == 200, cleared.text
        assert cleared.json()["note"] is None

    def test_a_null_note_keeps_the_stored_one(self, client, auth_headers):
        """Explicit null is a client without the input, not a clearing."""
        beat = self._session(client, auth_headers, note="Kept")

        resp = self._edit(client, auth_headers, beat, note=None)

        assert resp.status_code == 200, resp.text
        assert resp.json()["note"] == "Kept"

    def test_moving_a_session_to_another_project_keeps_the_note(self, client, auth_headers):
        beat = self._session(client, auth_headers, note="Billable")
        other = self._project(client, auth_headers)

        resp = self._edit(client, auth_headers, beat, project_id=other)

        assert resp.status_code == 200, resp.text
        stored = client.get(f"/api/beats/{beat['id']}", headers=auth_headers).json()
        assert (stored["project_id"], stored["note"]) == (other, "Billable")

    def test_reopening_a_session_keeps_the_note(self, client, auth_headers):
        """`end: null` reopens it as the running timer, as the companion's
        undo of a stop does."""
        beat = self._session(client, auth_headers, note="Deep work")

        resp = self._edit(client, auth_headers, beat, end=None)

        assert resp.status_code == 200, resp.text
        stored = client.get(f"/api/beats/{beat['id']}", headers=auth_headers).json()
        assert stored["end"] is None
        assert stored["note"] == "Deep work"

    def test_an_edit_with_no_flow_windows_keeps_the_tags(self, client, auth_headers):
        beat = self._session(client, auth_headers, tags=["imported"])

        resp = self._edit(client, auth_headers, beat, end="2026-04-01T10:00:00Z")

        assert resp.status_code == 200, resp.text
        stored = client.get(f"/api/beats/{beat['id']}", headers=auth_headers).json()
        assert stored["tags"] == ["imported"]

    def test_an_edit_over_flow_windows_takes_their_tags(self, client, auth_headers):
        beat = self._session(client, auth_headers, note="Kept", tags=["imported"])
        self._window(client, auth_headers, "2026-04-01T09:40:00Z", "2026-04-01T09:50:00Z", "acme")

        resp = self._edit(client, auth_headers, beat, end="2026-04-01T10:00:00Z")

        assert resp.status_code == 200, resp.text
        stored = client.get(f"/api/beats/{beat['id']}", headers=auth_headers).json()
        assert (stored["tags"], stored["note"]) == (["acme", "go"], "Kept")

    def test_an_unknown_session_is_404(self, client, auth_headers):
        beat = self._session(client, auth_headers)

        resp = self._edit(client, auth_headers, beat, id="0123456789abcdef01234567")

        assert resp.status_code == 404, resp.text

    def test_someone_elses_session_is_404_and_left_alone(
        self, client, auth_headers, other_auth_headers
    ):
        """Even when the caller's own flow windows cover its times: deriving
        tags is no reason to skip finding the session first."""
        beat = self._session(client, auth_headers, note="Mine")
        self._window(
            client, other_auth_headers, "2026-04-01T09:05:00Z", "2026-04-01T09:15:00Z", "theirs"
        )

        resp = self._edit(client, other_auth_headers, beat, end="2026-04-01T11:00:00Z")

        assert resp.status_code == 404, resp.text
        stored = client.get(f"/api/beats/{beat['id']}", headers=auth_headers).json()
        assert stored["end"].startswith("2026-04-01T09:30:00")
        assert (stored["note"], stored["tags"]) == ("Mine", [])

    # An edit can carry `expected`, the session as it was made against it:
    # the companion replays edits it queued offline, after another device
    # may have changed the same session.

    @staticmethod
    def _expected(beat: dict) -> dict:
        return {k: beat[k] for k in ("project_id", "start", "end")}

    def test_an_edit_made_against_the_stored_session_applies(self, client, auth_headers):
        beat = self._session(client, auth_headers)

        resp = self._edit(
            client, auth_headers, beat, start="2026-04-01T08:45:00Z", expected=self._expected(beat)
        )

        assert resp.status_code == 200, resp.text
        assert resp.json()["start"].startswith("2026-04-01T08:45:00")

    def test_an_edit_made_before_another_device_changed_it_is_refused(self, client, auth_headers):
        beat = self._session(client, auth_headers)
        assert self._edit(client, auth_headers, beat, end="2026-04-01T10:00:00Z").status_code == 200

        resp = self._edit(
            client, auth_headers, beat, start="2026-04-01T08:45:00Z", expected=self._expected(beat)
        )

        assert resp.status_code == 409, resp.text
        assert resp.json()["code"] == "BEAT_CHANGED"
        stored = client.get(f"/api/beats/{beat['id']}", headers=auth_headers).json()
        assert stored["start"].startswith("2026-04-01T09:00:00")
        assert stored["end"].startswith("2026-04-01T10:00:00")

    def test_moving_a_running_start_does_not_reopen_a_session_stopped_elsewhere(
        self, client, auth_headers
    ):
        """The companion moved the running timer's start while offline; by
        the replay another device had stopped it. The edit carries end None,
        and applied it would set the session running again."""
        # An earlier test in the class reopened a session; nothing may run.
        client.post("/api/projects/stop", json={}, headers=auth_headers)
        project_id = self._project(client, auth_headers)
        running = client.post(
            f"/api/projects/{project_id}/start",
            json={"time": "2026-04-02T09:00:00Z"},
            headers=auth_headers,
        ).json()
        stopped = client.post(
            "/api/projects/stop", json={"time": "2026-04-02T10:00:00Z"}, headers=auth_headers
        )
        assert stopped.status_code == 200, stopped.text

        resp = self._edit(
            client,
            auth_headers,
            running,
            start="2026-04-02T08:30:00Z",
            expected=self._expected(running),
        )

        assert resp.status_code == 409, resp.text
        assert client.get("/api/timer/status", headers=auth_headers).json()["isBeating"] is False

    def test_an_edit_to_a_session_deleted_elsewhere_is_404(self, client, auth_headers):
        beat = self._session(client, auth_headers)
        assert client.delete(f"/api/beats/{beat['id']}", headers=auth_headers).status_code == 200

        resp = self._edit(
            client, auth_headers, beat, start="2026-04-01T08:45:00Z", expected=self._expected(beat)
        )

        assert resp.status_code == 404, resp.text


class TestOneTimerAtATime:
    """A session with no `end` is a running timer whichever door opened it,
    so the CRUD routes make the check `/start` makes. Before #376 only
    `/start` did, and either of these left two sessions running at once —
    after which `get_active` answers with whichever storage returns first,
    and a single stop closes only one of them."""

    @staticmethod
    def _project(client, headers, name: str) -> str:
        resp = client.post("/api/projects/", json={"name": name}, headers=headers)
        assert resp.status_code == 201, resp.text
        return resp.json()["id"]

    @pytest.fixture(autouse=True)
    def _no_timer_left_running(self, client, auth_headers):
        """Each test here opens a timer; none may outlive its test."""
        yield
        with contextlib.suppress(Exception):
            client.post(
                "/api/projects/stop",
                json={"time": datetime.now(UTC).isoformat()},
                headers=auth_headers,
            )

    def test_create_without_end_is_refused_while_a_timer_runs(self, client, auth_headers):
        running = self._project(client, auth_headers, f"running-{time.time()}")
        other = self._project(client, auth_headers, f"other-{time.time()}")
        client.post(
            f"/api/projects/{running}/start",
            json={"time": "2026-05-01T09:00:00Z"},
            headers=auth_headers,
        )

        resp = client.post(
            "/api/beats/",
            json={"project_id": other, "start": "2026-05-01T10:00:00Z"},
            headers=auth_headers,
        )

        assert resp.status_code == 400, resp.text
        # The running session is named, so a client can say which one blocks.
        assert resp.json()["detail"]

        status = client.get("/api/timer/status", headers=auth_headers).json()
        assert status["isBeating"] is True
        assert status["project"]["id"] == running

    def test_create_without_end_is_allowed_when_nothing_runs(self, client, auth_headers):
        project = self._project(client, auth_headers, f"first-{time.time()}")

        resp = client.post(
            "/api/beats/",
            json={"project_id": project, "start": "2026-05-01T09:00:00Z"},
            headers=auth_headers,
        )

        assert resp.status_code == 201, resp.text
        assert resp.json()["end"] is None

    def test_reopening_is_refused_while_another_timer_runs(self, client, auth_headers):
        finished_project = self._project(client, auth_headers, f"finished-{time.time()}")
        beat = client.post(
            "/api/beats/",
            json={
                "project_id": finished_project,
                "start": "2026-05-01T09:00:00Z",
                "end": "2026-05-01T10:00:00Z",
            },
            headers=auth_headers,
        ).json()
        running = self._project(client, auth_headers, f"running2-{time.time()}")
        client.post(
            f"/api/projects/{running}/start",
            json={"time": "2026-05-01T11:00:00Z"},
            headers=auth_headers,
        )

        resp = client.put(
            "/api/beats/",
            json={
                "id": beat["id"],
                "project_id": finished_project,
                "start": beat["start"],
                "end": None,
            },
            headers=auth_headers,
        )

        assert resp.status_code == 400, resp.text
        # The edit did not land: the session is still finished.
        stored = client.get(f"/api/beats/{beat['id']}", headers=auth_headers).json()
        assert stored["end"] is not None

    def test_reopening_is_allowed_when_nothing_else_runs(self, client, auth_headers):
        project = self._project(client, auth_headers, f"reopen-{time.time()}")
        beat = client.post(
            "/api/beats/",
            json={
                "project_id": project,
                "start": "2026-05-01T09:00:00Z",
                "end": "2026-05-01T10:00:00Z",
            },
            headers=auth_headers,
        ).json()

        resp = client.put(
            "/api/beats/",
            json={
                "id": beat["id"],
                "project_id": project,
                "start": beat["start"],
                "end": None,
            },
            headers=auth_headers,
        )

        assert resp.status_code == 200, resp.text
        assert resp.json()["end"] is None

    def test_editing_the_running_session_is_not_blocked_by_itself(self, client, auth_headers):
        """The open session an edit is editing is not a second one — else a
        running timer could never have its start corrected."""
        project = self._project(client, auth_headers, f"self-{time.time()}")
        client.post(
            f"/api/projects/{project}/start",
            json={"time": "2026-05-01T09:00:00Z"},
            headers=auth_headers,
        )
        beats = client.get(f"/api/beats/?project_id={project}", headers=auth_headers).json()
        active = next(b for b in beats if b["end"] is None)

        resp = client.put(
            "/api/beats/",
            json={
                "id": active["id"],
                "project_id": project,
                "start": "2026-05-01T08:30:00Z",
                "end": None,
            },
            headers=auth_headers,
        )

        assert resp.status_code == 200, resp.text
        assert resp.json()["start"].startswith("2026-05-01T08:30")


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
