"""CSV and JSON export, and the backup import.

Split out of `test_api.py` at the size ceiling (CLAUDE.md § Conventions); the
harness is `conftest.py`'s and the shared fixtures `api_helpers.py`'s.
"""

import copy
import csv
import io
import json
import logging
from datetime import timedelta

from api_helpers import (
    BILLING_BACKUP_KEYS,
    COMPANY_DAY,
    FULL_TIME,
    KITE_RATE,
    NOWHERE,
    WEEK,
    _beat,
    _bill,
    _billable_from,
    _billing_budget_body,
    _billing_budgets,
    _create_client,
    _create_project,
    _day_job,
    _freelance,
    _last_month,
    _log,
    _month,
    _put_billing_budget,
    _put_contract,
    _this_month,
    _without_ids,
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
            "clients",
            "project_billing",
            "billable_overrides",
            "billing_budgets",
        }
        # 1.3 is the format that carries billing budgets, beside 1.2's
        # clients and their billing and 1.1's absences and balance adjustments.
        assert body["version"] == "1.3"

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

    def test_the_size_of_an_import_is_logged_and_its_contents_are_not(
        self, client, auth_headers, caplog
    ):
        """`IMPORT_RECEIVED` is the only record of how big a restore was —
        the Abuse page reads the spread of them (docs/backoffice.md
        § *Abuse*) — and a backup is the one request body made entirely of
        a person's own content, so the line carries its length and nothing
        out of it."""
        backup = {"version": "1.3", "projects": [{"name": "Secret Garden"}]}
        with caplog.at_level(logging.INFO, logger="beats.api.routers.export"):
            assert self._import(client, auth_headers, backup).status_code == 200
        [line] = [r.getMessage() for r in caplog.records if "IMPORT_RECEIVED" in r.getMessage()]
        assert f"bytes={len(json.dumps(backup))}" in line
        assert "Secret Garden" not in line

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
            "clients": len(backup["clients"]),
            "project_billing": len(backup["project_billing"]),
            "billable_overrides": len(backup["billable_overrides"]),
            "billing_budgets": len(backup["billing_budgets"]),
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
        # 1.0 had no absences or adjustments, nor billing or its budgets; a
        # file without the keys is a backup with none of them, not a 422.
        project = _day_job(client, auth_headers)
        _log(client, auth_headers, project["id"], "2026-03-02T08:00:00+00:00", 60)
        backup = self._export(client, auth_headers)
        backup["version"] = "1.0"
        for key in (*BILLING_BACKUP_KEYS, "billing_budgets", "absences", "balance_adjustments"):
            del backup[key]

        resp = self._import(client, auth_headers, backup)

        assert resp.status_code == 200, resp.text
        assert resp.json() == {
            "status": "ok",
            "imported": {
                "projects": len(backup["projects"]),
                "beats": len(backup["beats"]),
                "absences": 0,
                "balance_adjustments": 0,
                "clients": 0,
                "project_billing": 0,
                "billable_overrides": 0,
                "billing_budgets": 0,
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

    # --- 1.2: clients, project billing and billable marks ---

    @staticmethod
    def _billed(client, headers, name: str) -> tuple[dict, dict]:
        kite = _create_client(client, headers, rates=KITE_RATE)
        project = _freelance(client, headers, name)
        terms = _billable_from("2026-03-01")
        assert _bill(client, headers, project["id"], kite["id"], terms).status_code == 200
        return kite, project

    @staticmethod
    def _imported_billing(resp) -> tuple[int, int, int]:
        imported = resp.json()["imported"]
        return tuple(imported[key] for key in BILLING_BACKUP_KEYS)

    def test_billing_is_the_same_after_a_round_trip(self, client, auth_headers, auth_info, mongo):
        # An archived client with a billed project, and an entry marked not
        # billable: the ids are kept, so the mark still finds its entry and
        # the month reads as it did.
        kite, website = self._billed(client, auth_headers, "Round trip")
        _beat(client, auth_headers, website["id"], "2026-03-10T09:00:00", 120)
        marked = _beat(client, auth_headers, website["id"], "2026-03-11T09:00:00", 60)
        resp = client.put(
            f"/api/billing/entries/{marked['id']}", json={"billable": False}, headers=auth_headers
        )
        assert resp.status_code == 200, resp.text
        resp = client.post(f"/api/clients/{kite['id']}/archive", headers=auth_headers)
        assert resp.status_code == 200, resp.text
        before = _month(client, auth_headers)
        [figures] = [c for c in before["clients"] if c["client_id"] == kite["id"]]
        assert (figures["archived"], figures["amount_minor"]) == (True, 17000)

        backup = self._export(client, auth_headers)
        assert backup["version"] == "1.3"
        for collection in (
            "projects",
            "timeLogs",
            "absences",
            "balance_adjustments",
            *BILLING_BACKUP_KEYS,
        ):
            mongo[collection].delete_many({"user_id": auth_info["user_id"]})
        resp = self._import(client, auth_headers, backup)

        assert resp.status_code == 200, resp.text
        assert self._imported_billing(resp) == tuple(
            len(backup[key]) for key in BILLING_BACKUP_KEYS
        )
        archived = client.get("/api/clients/", params={"archived": True}, headers=auth_headers)
        assert kite["id"] in [c["id"] for c in archived.json()]
        assert _month(client, auth_headers) == before

    def test_a_dangling_reference_is_a_422_naming_it_and_writes_nothing(self, client, auth_headers):
        _, website = self._billed(client, auth_headers, "Dangling")
        _beat(client, auth_headers, website["id"], "2026-03-12T09:00:00", 60)
        sessions = client.get("/api/beats/", headers=auth_headers).json()
        backup = self._export(client, auth_headers)
        for record in backup["projects"]:
            if record["id"] == website["id"]:
                record["name"] = "renamed by the backup"
        [billing] = [b for b in backup["project_billing"] if b["project_id"] == website["id"]]
        # A client, a project and an entry neither in the file nor the account.
        backup["project_billing"] = [
            {**billing, "client_id": NOWHERE},
            {**billing, "project_id": NOWHERE},
        ]
        backup["billable_overrides"] = [{"beat_id": NOWHERE, "billable": True}]

        resp = self._import(client, auth_headers, backup)

        assert resp.status_code == 422, resp.text
        assert [f["path"] for f in resp.json()["fields"]] == [
            "project_billing.0.client_id",
            "project_billing.1.project_id",
            "billable_overrides.0.beat_id",
        ]
        listed = client.get("/api/projects/", headers=auth_headers).json()
        assert next(p for p in listed if p["id"] == website["id"])["name"] == website["name"]
        assert client.get("/api/beats/", headers=auth_headers).json() == sessions

    def test_another_accounts_client_is_refused_and_stays_theirs(
        self, client, auth_headers, other_auth_headers
    ):
        theirs = _create_client(client, other_auth_headers, name="Their client")
        their_backup = self._export(client, other_auth_headers)

        resp = self._import(client, auth_headers, {"clients": their_backup["clients"]})

        assert resp.status_code == 409, resp.text
        assert resp.json()["code"] == "BACKUP_OF_ANOTHER_ACCOUNT"
        resp = client.get(f"/api/clients/{theirs['id']}", headers=other_auth_headers)
        assert resp.json() == theirs
        mine = client.get("/api/clients/", headers=auth_headers).json()
        assert theirs["id"] not in [c["id"] for c in mine]

    def test_a_write_billing_would_refuse_is_refused_naming_it_and_writes_nothing(
        self, client, auth_headers
    ):
        # Each file breaks one rule a billing write is held to, behind a
        # project renamed ahead of it: the rule is checked before the rename
        # is written, and answered as its route answers it.
        kite, website = self._billed(client, auth_headers, "Refused")
        dollars = _create_client(client, auth_headers, name="Dollar Co", currency="USD")
        ahead = _create_project(client, auth_headers)
        exported = self._export(client, auth_headers)

        def record(collection: str, key: str, value: str) -> dict:
            return copy.deepcopy(next(r for r in exported[collection] if r[key] == value))

        def backup(**edits) -> dict:
            projects = [
                {**record("projects", "id", ahead["id"]), "name": "renamed by the backup"},
                {**record("projects", "id", website["id"]), **edits.get("project", {})},
            ]
            clients = [
                {**record("clients", "id", kite["id"]), **edits.get("kite", {})},
                {**record("clients", "id", dollars["id"]), **edits.get("dollars", {})},
            ]
            billing = {
                **record("project_billing", "project_id", website["id"]),
                **edits.get("billing", {}),
            }
            return {
                "projects": projects,
                "clients": clients,
                "project_billing": [] if edits.get("unbilled") else [billing],
            }

        side_project = {"kind": "side_project"}
        cases = [
            (backup(project=side_project), 409, "NOT_FREELANCE", "project_billing.0"),
            (backup(project=side_project, unbilled=True), 409, "PROJECT_HAS_BILLING", "projects.1"),
            (backup(kite={"currency": "USD"}), 409, "CURRENCY_IN_USE", "clients.0"),
            (
                backup(
                    billing={
                        "client_id": dollars["id"],
                        "terms": _billable_from("2026-03-01", rate_minor=9000),
                    }
                ),
                409,
                "CURRENCY_MISMATCH",
                "project_billing.0",
            ),
            (backup(dollars={"currency": "EUX"}), 400, "UNKNOWN_CURRENCY", "clients.1"),
        ]
        for file, status, code, where in cases:
            resp = self._import(client, auth_headers, file)
            assert resp.status_code == status, resp.text
            assert resp.json()["code"] == code
            assert resp.json()["detail"].startswith(f"{where}: "), resp.text

        listed = client.get("/api/projects/", headers=auth_headers).json()
        assert next(p for p in listed if p["id"] == ahead["id"])["name"] == ahead["name"]
        assert next(p for p in listed if p["id"] == website["id"])["kind"] == "freelance"
        mine = {c["id"]: c for c in client.get("/api/clients/", headers=auth_headers).json()}
        assert (mine[kite["id"]]["currency"], mine[dollars["id"]]["currency"]) == ("EUR", "USD")
        billed = client.get("/api/billing/projects", headers=auth_headers).json()
        assert (
            next(b for b in billed if b["project_id"] == website["id"])["client_id"] == kite["id"]
        )

    def test_a_move_to_another_currency_counts_the_files_billable_marks(self, client, auth_headers):
        # Billed from this month on, the project has a past figure only once
        # an entry before it is marked billable; here the file marks it, as
        # it moves the billing to a client in dollars.
        kite = _create_client(client, auth_headers, rates=KITE_RATE)
        dollars = _create_client(client, auth_headers, name="Dollar Co", currency="USD")
        project = _freelance(client, auth_headers, "Marked")
        now = _billable_from(_this_month())
        assert _bill(client, auth_headers, project["id"], kite["id"], now).status_code == 200
        past = _beat(
            client,
            auth_headers,
            project["id"],
            f"{_last_month() + timedelta(days=10)}T09:00:00",
            60,
        )
        file = {
            "project_billing": [
                {"project_id": project["id"], "client_id": dollars["id"], "terms": now}
            ],
            "billable_overrides": [{"beat_id": past["id"], "billable": True}],
        }

        resp = self._import(client, auth_headers, file)

        assert resp.status_code == 409, resp.text
        assert resp.json()["code"] == "CURRENCY_MISMATCH"
        assert resp.json()["detail"].startswith("project_billing.0: "), resp.text
        marks = client.get("/api/billing/entries", headers=auth_headers).json()
        assert past["id"] not in [mark["beat_id"] for mark in marks]

    def test_the_accounts_money_budget_holds_a_currency_through_a_restore(
        self, client, auth_headers
    ):
        # No rate anywhere: only the account's money budget on the project
        # keeps its client's currency, and keeps it from moving to dollars.
        euros = _create_client(client, auth_headers, name="Budgeted euros")
        dollars = _create_client(client, auth_headers, name="Budgeted dollars", currency="USD")
        project = _freelance(client, auth_headers, "Budgeted")
        now = _billable_from(_this_month())
        assert _bill(client, auth_headers, project["id"], euros["id"], now).status_code == 200
        resp = _put_billing_budget(
            client,
            auth_headers,
            "projects",
            project["id"],
            unit="money",
            limit_hours=None,
            limit_minor=100000,
        )
        assert resp.status_code == 200, resp.text
        [record] = [
            c for c in self._export(client, auth_headers)["clients"] if c["id"] == euros["id"]
        ]
        cases = [
            ({"clients": [{**record, "currency": "GBP"}]}, "CURRENCY_IN_USE", "clients.0"),
            (
                {
                    "project_billing": [
                        {"project_id": project["id"], "client_id": dollars["id"], "terms": now}
                    ]
                },
                "CURRENCY_MISMATCH",
                "project_billing.0",
            ),
        ]
        for file, code, where in cases:
            resp = self._import(client, auth_headers, file)
            assert resp.status_code == 409, resp.text
            assert resp.json()["code"] == code
            assert resp.json()["detail"].startswith(f"{where}: "), resp.text

        got = client.get(f"/api/clients/{euros['id']}", headers=auth_headers).json()
        assert got["currency"] == "EUR"
        billed = client.get("/api/billing/projects", headers=auth_headers).json()
        assert (
            next(b for b in billed if b["project_id"] == project["id"])["client_id"] == euros["id"]
        )

    def test_a_backup_from_before_billing_imports_and_leaves_billing_alone(
        self, client, auth_headers
    ):
        _, website = self._billed(client, auth_headers, "Before billing")
        backup = self._export(client, auth_headers)
        backup["version"] = "1.1"
        for key in BILLING_BACKUP_KEYS:
            del backup[key]

        resp = self._import(client, auth_headers, backup)

        assert resp.status_code == 200, resp.text
        assert self._imported_billing(resp) == (0, 0, 0)
        billed = client.get("/api/billing/projects", headers=auth_headers).json()
        assert website["id"] in [b["project_id"] for b in billed]

    # --- 1.3: billing budgets ---

    @staticmethod
    def _money_billing_budget(client, headers, project_id: str, **fields) -> None:
        resp = _put_billing_budget(
            client,
            headers,
            "projects",
            project_id,
            unit="money",
            period="total",
            limit_hours=None,
            limit_minor=100000,
            starts_on="2026-03-01",
            **fields,
        )
        assert resp.status_code == 200, resp.text

    def test_billing_budgets_are_the_same_after_a_round_trip(
        self, client, auth_headers, auth_info, mongo
    ):
        kite, website = self._billed(client, auth_headers, "Budgeted round trip")
        _beat(client, auth_headers, website["id"], "2026-03-10T09:00:00", 120)
        self._money_billing_budget(client, auth_headers, website["id"])
        resp = _put_billing_budget(client, auth_headers, "clients", kite["id"])
        assert resp.status_code == 200, resp.text
        mine = {kite["id"], website["id"]}

        def readings() -> list[dict]:
            return [s for s in _billing_budgets(client, auth_headers) if s["scope_id"] in mine]

        before = readings()
        assert [(s["scope"], s["amount_minor"]) for s in before] == [
            ("client", 0),
            ("project", 17000),
        ]

        backup = self._export(client, auth_headers)
        assert backup["version"] == "1.3"
        assert {b["scope_id"] for b in backup["billing_budgets"]} >= mine
        for collection in ("projects", "timeLogs", *BILLING_BACKUP_KEYS, "billing_budgets"):
            mongo[collection].delete_many({"user_id": auth_info["user_id"]})
        resp = self._import(client, auth_headers, backup)

        assert resp.status_code == 200, resp.text
        assert resp.json()["imported"]["billing_budgets"] == len(backup["billing_budgets"])
        assert resp.json()["skipped"] == []
        assert readings() == before

    def test_a_backup_from_before_billing_budgets_leaves_the_accounts_alone(
        self, client, auth_headers
    ):
        _, website = self._billed(client, auth_headers, "Before budgets")
        self._money_billing_budget(client, auth_headers, website["id"])
        backup = self._export(client, auth_headers)
        backup["version"] = "1.2"
        del backup["billing_budgets"]

        resp = self._import(client, auth_headers, backup)

        assert resp.status_code == 200, resp.text
        assert resp.json()["imported"]["billing_budgets"] == 0
        scopes = [s["scope_id"] for s in _billing_budgets(client, auth_headers)]
        assert website["id"] in scopes

    def test_a_billing_budget_on_a_scope_nowhere_is_a_422_naming_it(self, client, auth_headers):
        budget = {**_billing_budget_body(), "scope": "client", "scope_id": NOWHERE}
        file = {
            "billing_budgets": [
                {**budget, "scope": "project"},
                budget,
            ]
        }

        resp = self._import(client, auth_headers, file)

        assert resp.status_code == 422, resp.text
        assert [f["path"] for f in resp.json()["fields"]] == [
            "billing_budgets.0.scope_id",
            "billing_budgets.1.scope_id",
        ]

    def test_a_billing_budget_without_its_limit_or_start_is_a_422_naming_them(
        self, client, auth_headers
    ):
        # A file written by hand, or by another tool, can leave a key out
        # where an export writes null: it must be refused as the null is,
        # not stored to fail every budgets read after it.
        kite = _create_client(client, auth_headers, name="Keys left out")
        total = {"scope": "client", "scope_id": kite["id"], "unit": "hours", "period": "total"}
        money = {**total, "unit": "money", "period": "monthly"}
        file = {
            "billing_budgets": [{**total, "warn_at_percent": 80}, {**money, "warn_at_percent": 80}]
        }

        resp = self._import(client, auth_headers, file)

        assert resp.status_code == 422, resp.text
        assert [f["path"] for f in resp.json()["fields"]] == [
            "billing_budgets.0.limit_hours",
            "billing_budgets.0.starts_on",
            "billing_budgets.1.limit_minor",
        ]
        assert kite["id"] not in [s["scope_id"] for s in _billing_budgets(client, auth_headers)]

    def test_a_budget_on_a_project_billed_nowhere_is_refused_and_writes_nothing(
        self, client, auth_headers, auth_info, mongo
    ):
        # A client and a project only the file holds: they would be written
        # first, were the budget not checked before any write.
        acme = _create_client(client, auth_headers, name="Only in the file")
        unbilled = _freelance(client, auth_headers, "Only in the file")
        exported = self._export(client, auth_headers)
        file = {
            "clients": [c for c in exported["clients"] if c["id"] == acme["id"]],
            "projects": [p for p in exported["projects"] if p["id"] == unbilled["id"]],
            "billing_budgets": [
                {**_billing_budget_body(), "scope": "project", "scope_id": unbilled["id"]}
            ],
        }
        mongo.clients.delete_one({"user_id": auth_info["user_id"], "name": acme["name"]})
        mongo.projects.delete_one({"user_id": auth_info["user_id"], "name": unbilled["name"]})

        resp = self._import(client, auth_headers, file)

        assert resp.status_code == 409, resp.text
        assert resp.json()["code"] == "BILLING_BUDGET_NEEDS_BILLING"
        assert resp.json()["detail"].startswith("billing_budgets.0: "), resp.text
        assert client.get(f"/api/clients/{acme['id']}", headers=auth_headers).status_code == 404
        listed = client.get("/api/projects/", params={"archived": True}, headers=auth_headers)
        listed = [*listed.json(), *client.get("/api/projects/", headers=auth_headers).json()]
        assert unbilled["id"] not in [p["id"] for p in listed]

    def test_a_files_own_budget_replaces_the_accounts_before_a_move(self, client, auth_headers):
        # The account's money budget would hold the project in euros; the
        # file carries one in hours for it, so the move to dollars is what
        # the file leaves consistent.
        euros = _create_client(client, auth_headers, name="Replaced euros")
        dollars = _create_client(client, auth_headers, name="Replaced dollars", currency="USD")
        project = _freelance(client, auth_headers, "Replaced")
        now = _billable_from(_this_month())
        assert _bill(client, auth_headers, project["id"], euros["id"], now).status_code == 200
        self._money_billing_budget(client, auth_headers, project["id"])
        file = {
            "project_billing": [
                {"project_id": project["id"], "client_id": dollars["id"], "terms": now}
            ],
            "billing_budgets": [
                {**_billing_budget_body(), "scope": "project", "scope_id": project["id"]}
            ],
        }

        resp = self._import(client, auth_headers, file)

        assert resp.status_code == 200, resp.text
        [status] = [
            s for s in _billing_budgets(client, auth_headers) if s["scope_id"] == project["id"]
        ]
        assert (status["client_id"], status["unit"]) == (dollars["id"], "hours")
