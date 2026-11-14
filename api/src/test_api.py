"""The HTTP contract itself: the unified error envelope, what a stop names,
the idempotency replay, and the isolation between two accounts.

The router areas each have a file of their own (`test_api_*.py`); what is
left here belongs to no one router.

Split out of `test_api.py` at the size ceiling (CLAUDE.md § Conventions); the
harness is `conftest.py`'s and the shared fixtures `api_helpers.py`'s.
"""

from datetime import UTC, datetime, timedelta

import pytest

from api_helpers import (
    KITE_RATE,
    _beat,
    _bill,
    _billable_from,
    _create_client,
    _freelance,
    _month,
    _put_client,
)


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


class TestStopNamesItsTimer:
    """POST /api/projects/stop with `expected`: the companion replays a stop
    it queued offline, and by then another device may have changed the
    timer. The stop applies only to the session it names; any other running
    session is left alone with a 409 TIMER_CHANGED."""

    @pytest.fixture(autouse=True)
    def _nothing_running(self, client, auth_headers):
        client.post("/api/projects/stop", json={}, headers=auth_headers)
        yield
        client.post("/api/projects/stop", json={}, headers=auth_headers)

    @staticmethod
    def _project(client, headers, name: str) -> str:
        resp = client.post("/api/projects/", json={"name": name}, headers=headers)
        assert resp.status_code == 201, resp.text
        return resp.json()["id"]

    @staticmethod
    def _start(client, headers, project_id: str, at: str) -> None:
        resp = client.post(f"/api/projects/{project_id}/start", json={"time": at}, headers=headers)
        assert resp.status_code == 200, resp.text

    @staticmethod
    def _stop(client, headers, at: str) -> None:
        resp = client.post("/api/projects/stop", json={"time": at}, headers=headers)
        assert resp.status_code == 200, resp.text

    @staticmethod
    def _running(client, headers) -> dict:
        return client.get("/api/timer/status", headers=headers).json()

    def test_the_named_timer_stops(self, client, auth_headers):
        # The start the client sent carried microseconds; Mongo keeps
        # milliseconds, and the client names the timer by what it sent.
        project = self._project(client, auth_headers, "Northwind")
        self._start(client, auth_headers, project, "2026-04-16T09:00:00.123456Z")

        resp = client.post(
            "/api/projects/stop",
            json={
                "time": "2026-04-16T10:30:00Z",
                "expected": {"project_id": project, "start": "2026-04-16T09:00:00.123456Z"},
            },
            headers=auth_headers,
        )

        assert resp.status_code == 200, resp.text
        assert resp.json()["end"].startswith("2026-04-16T10:30:00")
        assert self._running(client, auth_headers)["isBeating"] is False

    def test_a_timer_switched_elsewhere_keeps_running(self, client, auth_headers):
        northwind = self._project(client, auth_headers, "Northwind")
        kite = self._project(client, auth_headers, "Studio Kite")
        self._start(client, auth_headers, northwind, "2026-04-16T09:00:00Z")
        # Another device switches while this one is offline.
        self._stop(client, auth_headers, "2026-04-16T10:00:00Z")
        self._start(client, auth_headers, kite, "2026-04-16T10:00:00Z")

        resp = client.post(
            "/api/projects/stop",
            json={
                "time": "2026-04-16T10:30:00Z",
                "expected": {"project_id": northwind, "start": "2026-04-16T09:00:00Z"},
            },
            headers=auth_headers,
        )

        assert resp.status_code == 409, resp.text
        assert resp.json()["code"] == "TIMER_CHANGED"
        status = self._running(client, auth_headers)
        assert status["isBeating"] is True
        assert status["project"]["id"] == kite

    def test_the_same_project_restarted_elsewhere_keeps_running(self, client, auth_headers):
        project = self._project(client, auth_headers, "Northwind")
        self._start(client, auth_headers, project, "2026-04-16T09:00:00Z")
        self._stop(client, auth_headers, "2026-04-16T09:45:00Z")
        self._start(client, auth_headers, project, "2026-04-16T10:00:00Z")

        resp = client.post(
            "/api/projects/stop",
            json={
                "time": "2026-04-16T10:30:00Z",
                "expected": {"project_id": project, "start": "2026-04-16T09:00:00Z"},
            },
            headers=auth_headers,
        )

        assert resp.status_code == 409, resp.text
        assert self._running(client, auth_headers)["since"].startswith("2026-04-16T10:00:00")

    def test_a_replayed_stop_answers_as_it_did_rather_than_refusing(self, client, auth_headers):
        """The stop landed but its response was lost; meanwhile another
        timer started. The replay carries the same X-Client-Id, so it is
        answered from the record, not judged again against the new timer."""
        northwind = self._project(client, auth_headers, "Northwind")
        kite = self._project(client, auth_headers, "Studio Kite")
        self._start(client, auth_headers, northwind, "2026-04-16T09:00:00Z")
        stop = {
            "time": "2026-04-16T10:30:00Z",
            "expected": {"project_id": northwind, "start": "2026-04-16T09:00:00Z"},
        }
        headers = {**auth_headers, "X-Client-Id": "offline-stop-1"}
        first = client.post("/api/projects/stop", json=stop, headers=headers)
        assert first.status_code == 200, first.text
        self._start(client, auth_headers, kite, "2026-04-16T10:30:00Z")

        replay = client.post("/api/projects/stop", json=stop, headers=headers)

        assert replay.status_code == 200
        assert replay.headers.get("X-Idempotent-Replay") == "true"
        assert self._running(client, auth_headers)["project"]["id"] == kite


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

        Idempotency middleware covers /api/projects/{id}/start and
        /stop and the session writes on /api/beats/ — so we trigger
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

    def test_a_replayed_session_create_logs_it_once(self, client, auth_headers):
        """The companion queues "log time you forgot" while offline; a create
        whose response was lost is sent again with the same X-Client-Id."""
        project_id = self._create_project(client, auth_headers)
        session = {
            "project_id": project_id,
            "start": "2026-04-17T09:00:00Z",
            "end": "2026-04-17T10:00:00Z",
        }
        headers = {**auth_headers, "X-Client-Id": "offline-create-1"}
        first = client.post("/api/beats/", json=session, headers=headers)
        assert first.status_code == 201, first.text

        second = client.post("/api/beats/", json=session, headers=headers)

        assert second.status_code == 201
        assert second.headers.get("X-Idempotent-Replay") == "true"
        assert second.json()["id"] == first.json()["id"]
        beats = client.get(f"/api/beats/?project_id={project_id}", headers=auth_headers).json()
        assert len(beats) == 1

    def test_a_replayed_edit_does_not_undo_a_later_one(self, client, auth_headers):
        """An edit landed, its response was lost, and the session was edited
        again elsewhere. The replay is answered from the record and leaves
        the later edit standing."""
        project_id = self._create_project(client, auth_headers)
        beat = client.post(
            "/api/beats/",
            json={
                "project_id": project_id,
                "start": "2026-04-17T11:00:00Z",
                "end": "2026-04-17T12:00:00Z",
            },
            headers=auth_headers,
        ).json()
        edit = {
            "id": beat["id"],
            "project_id": project_id,
            "start": "2026-04-17T10:30:00Z",
            "end": "2026-04-17T12:00:00Z",
        }
        headers = {**auth_headers, "X-Client-Id": "offline-edit-1"}
        assert client.put("/api/beats/", json=edit, headers=headers).status_code == 200
        later = {**edit, "start": "2026-04-17T10:45:00Z"}
        assert client.put("/api/beats/", json=later, headers=auth_headers).status_code == 200

        replay = client.put("/api/beats/", json=edit, headers=headers)

        assert replay.status_code == 200
        assert replay.headers.get("X-Idempotent-Replay") == "true"
        stored = client.get(f"/api/beats/{beat['id']}", headers=auth_headers).json()
        assert stored["start"].startswith("2026-04-17T10:45:00")


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

    def test_billing_isolated_between_users(self, client, auth_headers, other_auth_headers):
        """Someone else's clients, billing, marks and month are not found,
        never forbidden, and never in a list or a report."""
        kite = _create_client(client, auth_headers, name="Private Kite", rates=KITE_RATE)
        project = _freelance(client, auth_headers)
        terms = _billable_from("2026-03-01")
        assert _bill(client, auth_headers, project["id"], kite["id"], terms).status_code == 200
        beat = _beat(client, auth_headers, project["id"], "2026-03-10T09:00:00", 60)
        client.put(
            f"/api/billing/entries/{beat['id']}", json={"billable": False}, headers=auth_headers
        )
        other = other_auth_headers

        assert client.get("/api/clients/", headers=other).json() == []
        assert client.get("/api/clients/?archived=true", headers=other).json() == []
        assert client.get("/api/billing/projects", headers=other).json() == []
        assert client.get("/api/billing/entries", headers=other).json() == []
        report = _month(client, other)
        assert (report["clients"], report["totals"], report["unattached"]) == ([], [], [])

        for resp in (
            client.get(f"/api/clients/{kite['id']}", headers=other),
            _put_client(client, other, kite["id"], name="Taken"),
            client.post(f"/api/clients/{kite['id']}/archive", headers=other),
            client.delete(f"/api/clients/{kite['id']}", headers=other),
            client.delete(
                f"/api/billing/projects/{project['id']}",
                params={"tz": "UTC", "rewrite_past": True, "remove_billing_budget": False},
                headers=other,
            ),
        ):
            assert resp.status_code == 404, resp.text

        # Their own client cannot take my project, nor clear my mark.
        theirs = _create_client(client, other)
        assert _bill(client, other, project["id"], theirs["id"], terms).status_code == 404
        client.delete(f"/api/billing/entries/{beat['id']}", headers=other)

        mine = client.get(f"/api/clients/{kite['id']}", headers=auth_headers).json()
        assert (mine["name"], mine["archived"]) == ("Private Kite", False)
        [billing] = client.get("/api/billing/projects", headers=auth_headers).json()
        assert billing["client_id"] == kite["id"]
        marks = client.get("/api/billing/entries", headers=auth_headers).json()
        assert marks == [{"beat_id": beat["id"], "billable": False}]
