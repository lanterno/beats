"""Projects and goal overrides.

Split out of `test_api.py` at the size ceiling (CLAUDE.md § Conventions); the
harness is `conftest.py`'s and the shared fixtures `api_helpers.py`'s.
"""

import time
from datetime import UTC, datetime, timedelta

from api_helpers import (
    _log,
)


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

    def _project_with_every_field(self, client, auth_headers) -> dict:
        response = client.post(
            "/api/projects/",
            json={
                "name": f"kept-{time.time()}",
                "description": "the description",
                "color": "#5B9CF6",
                "weekly_goal": 12.5,
                "goal_type": "cap",
                "github_repo": "lanterno/beats",
                "category": "coding",
                "autostart_repos": ["/Users/me/code/beats"],
            },
            headers=auth_headers,
        )
        assert response.status_code == 201, response.text
        return response.json()

    def test_a_colour_change_keeps_every_field_it_leaves_out(self, client, auth_headers):
        """AHM-89: the project page's colour picker sends id, name and colour
        (and a few fields it happens to know), never the GitHub repo, the
        category or the autostart repos. Absence read as a reset, so one
        colour change wiped all three."""
        project = self._project_with_every_field(client, auth_headers)
        client.post(f"/api/projects/{project['id']}/archive", headers=auth_headers)

        response = client.put(
            "/api/projects/",
            json={"id": project["id"], "name": project["name"], "color": "#FBBF24"},
            headers=auth_headers,
        )
        assert response.status_code == 200, response.text
        listed = client.get("/api/projects/?archived=true", headers=auth_headers).json()
        stored = next(p for p in listed if p["id"] == project["id"])
        assert stored["color"] == "#FBBF24"
        assert stored["description"] == "the description"
        assert stored["archived"] is True
        assert stored["weekly_goal"] == 12.5
        assert stored["goal_type"] == "cap"
        assert stored["github_repo"] == "lanterno/beats"
        assert stored["category"] == "coding"
        assert stored["autostart_repos"] == ["/Users/me/code/beats"]

    def test_an_explicit_null_or_empty_value_still_clears(self, client, auth_headers):
        """Left out keeps; sent clears. The settings drawer clears a field by
        sending null (or `[]` for the autostart repos), and must go on doing so."""
        project = self._project_with_every_field(client, auth_headers)

        response = client.put(
            "/api/projects/",
            json={
                "id": project["id"],
                "name": project["name"],
                "description": None,
                "color": None,
                "weekly_goal": None,
                "github_repo": None,
                "category": None,
                "autostart_repos": [],
            },
            headers=auth_headers,
        )
        assert response.status_code == 200, response.text
        updated = response.json()
        assert updated["description"] is None
        assert updated["color"] is None
        assert updated["weekly_goal"] is None
        assert updated["github_repo"] is None
        assert updated["category"] is None
        assert updated["autostart_repos"] == []
        assert updated["goal_type"] == "cap"

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
