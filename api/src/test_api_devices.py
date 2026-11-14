"""Device pairing and the companion's biometrics.

Split out of `test_api.py` at the size ceiling (CLAUDE.md § Conventions); the
harness is `conftest.py`'s and the shared fixtures `api_helpers.py`'s.
"""

import hashlib
from datetime import UTC, date, datetime, timedelta

from api_helpers import (
    _billing_budget_body,
)


class TestDevicePairingAPI:
    """Test suite for daemon device pairing and device token auth."""

    def test_generate_pair_code_requires_auth(self, client):
        """POST /api/device/pair/code without token returns 401."""
        resp = client.post("/api/device/pair/code")
        assert resp.status_code == 401

    def test_generate_pair_code_success(self, client, auth_headers):
        """POST /api/device/pair/code returns a 6-char code."""
        resp = client.post("/api/device/pair/code", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["code"]) == 6
        assert data["expires_in_seconds"] == 300

    def test_exchange_code_success(self, client, auth_headers):
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

    def test_exchange_code_invalid(self, client):
        """Exchange with bad code returns 404."""
        resp = client.post(
            "/api/device/pair/exchange",
            json={"code": "BADCOD"},
        )
        assert resp.status_code == 404

    def test_exchange_code_one_time_use(self, client, auth_headers):
        """Same code can only be exchanged once."""
        resp = client.post("/api/device/pair/code", headers=auth_headers)
        code = resp.json()["code"]

        # First exchange succeeds
        resp = client.post("/api/device/pair/exchange", json={"code": code})
        assert resp.status_code == 200

        # Second exchange fails
        resp = client.post("/api/device/pair/exchange", json={"code": code})
        assert resp.status_code == 404

    def test_a_code_is_stored_with_dates_its_ttl_index_expires(self, client, auth_headers, mongo):
        """The TTL index on `expires_at` acts only on BSON dates. Codes were
        stored with ISO strings, so none was ever removed: every code issued
        stayed in the collection with its hash and owner."""
        resp = client.post("/api/device/pair/code", headers=auth_headers)
        code_hash = hashlib.sha256(resp.json()["code"].encode()).hexdigest()
        doc = mongo.pairing_codes.find_one({"code_hash": code_hash})
        assert isinstance(doc["expires_at"], datetime)
        assert isinstance(doc["created_at"], datetime)

    def test_an_expired_code_is_refused_before_the_ttl_monitor_removes_it(
        self, client, auth_headers, mongo
    ):
        """The TTL monitor runs about once a minute, so redemption checks the
        expiry itself, against a date."""
        code = client.post("/api/device/pair/code", headers=auth_headers).json()["code"]
        code_hash = hashlib.sha256(code.encode()).hexdigest()
        mongo.pairing_codes.update_one(
            {"code_hash": code_hash},
            {"$set": {"expires_at": datetime.now(UTC) - timedelta(seconds=1)}},
        )
        resp = client.post("/api/device/pair/exchange", json={"code": code})
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Invalid or expired pairing code"

    def test_device_token_allows_heartbeat(self, client, auth_headers):
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

    def test_device_token_blocked_on_non_allowed_endpoints(self, client, auth_headers):
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

    def test_device_token_reaches_no_money(self, client, auth_headers):
        """Clients, rates, billable marks and billing budgets are kept off
        every paired device: none of their routes sits under a device prefix
        (see the comment on `DEVICE_ALLOWED_PREFIXES`), so a route moved under
        /api/projects or /api/beats, or a prefix added, shows here."""
        resp = client.post("/api/device/pair/code", headers=auth_headers)
        code = resp.json()["code"]
        resp = client.post("/api/device/pair/exchange", json={"code": code})
        device_headers = {"Authorization": f"Bearer {resp.json()['device_token']}"}

        for resp in (
            client.get("/api/clients/", headers=device_headers),
            client.get(
                "/api/billing/month",
                params={"month": "2026-03", "tz": "UTC"},
                headers=device_headers,
            ),
            client.put("/api/billing/entries/x", json={"billable": True}, headers=device_headers),
            client.get("/api/billing/budgets", params={"tz": "UTC"}, headers=device_headers),
            client.put(
                "/api/billing/budgets/clients/x",
                json=_billing_budget_body(),
                headers=device_headers,
            ),
            client.get("/api/clients/x/links", headers=device_headers),
            # /api/reports is public, so this is the one of these that a
            # device could reach by the prefix rules alone. It cannot: the
            # middleware resolves the bearer token and checks the device
            # allowlist before a path's publicness is ever considered.
            client.get(
                "/api/reports",
                headers={**device_headers, "X-Report-Token": "sometoken"},
            ),
        ):
            assert resp.status_code == 403, resp.text
            assert resp.json()["code"] == "DEVICE_PATH_FORBIDDEN"

    def test_device_token_allowed_on_analytics_heatmap(self, client, auth_headers):
        """Device tokens can read the heatmap (companion timer-screen totals)."""
        resp = client.post("/api/device/pair/code", headers=auth_headers)
        code = resp.json()["code"]
        resp = client.post("/api/device/pair/exchange", json={"code": code})
        device_token = resp.json()["device_token"]
        device_headers = {"Authorization": f"Bearer {device_token}"}

        resp = client.get("/api/analytics/heatmap", headers=device_headers)
        assert resp.status_code == 200

    def test_device_token_allowed_on_analytics_tags(self, client, auth_headers):
        """Device tokens can read /api/analytics/tags — the companion surfaces
        the auto-derived tag list (repo/language) in its analytics views."""
        resp = client.post("/api/device/pair/code", headers=auth_headers)
        code = resp.json()["code"]
        resp = client.post("/api/device/pair/exchange", json={"code": code})
        device_token = resp.json()["device_token"]
        device_headers = {"Authorization": f"Bearer {device_token}"}

        resp = client.get("/api/analytics/tags", headers=device_headers)
        assert resp.status_code == 200

    def test_device_token_allowed_on_beats(self, client, auth_headers):
        """Device tokens can read /api/beats — the companion lists recent
        sessions after a timer stops (no manual note/tags edit anymore)."""
        resp = client.post("/api/device/pair/code", headers=auth_headers)
        code = resp.json()["code"]
        resp = client.post("/api/device/pair/exchange", json={"code": code})
        device_token = resp.json()["device_token"]
        device_headers = {"Authorization": f"Bearer {device_token}"}

        resp = client.get("/api/beats/", headers=device_headers)
        assert resp.status_code == 200

    def test_list_registrations(self, client, auth_headers):
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

    def test_revoke_device(self, client, auth_headers):
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

    def test_revoked_device_not_in_list(self, client, auth_headers):
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

    def test_device_status_shape_is_what_the_wall_clock_reads(self, client, auth_headers):
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
            assert isinstance(component, int), component
            assert 0 <= component <= 255, component

        # When clocked_in is True, project_color_rgb / elapsed_minutes
        # / project_name / project_id are also present. Default fresh-
        # user state has no active timer so we don't exercise that
        # branch here — but the firmware's struct provides defaults
        # for all of them, so the un-clocked-in path is the
        # interesting one to lock.
        assert body["clocked_in"] is False
        assert body["daily_total_minutes"] == 0
        assert body["energy_level"] == 0

    def test_device_favorites_shape_is_what_the_wall_clock_reads(self, client, auth_headers):
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
            assert "id" in fav, fav
            assert "name" in fav, fav
            # color_rgb is the int[3] the wall-clock's rgbFromArray reads.
            # NOT "color" (the previously-misnamed hex-string key).
            assert "color_rgb" in fav, fav
            assert "color" not in fav, (
                f"unexpected legacy 'color' key — wall-clock reads color_rgb: {fav}"
            )
            assert isinstance(fav["color_rgb"], list)
            assert len(fav["color_rgb"]) == 3

    def test_device_weekly_returns_seven_days_oldest_first(self, client, auth_headers):
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
        from datetime import timedelta

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

    def test_device_heartbeat_persists_telemetry_for_get(self, client, auth_headers):
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


class TestBiometricsAPI:
    """Test suite for biometrics endpoints."""

    def _pair_device(self, client, auth_headers):
        """Helper: pair a device and return device_headers."""
        resp = client.post("/api/device/pair/code", headers=auth_headers)
        code = resp.json()["code"]
        resp = client.post("/api/device/pair/exchange", json={"code": code})
        return {"Authorization": f"Bearer {resp.json()['device_token']}"}

    def test_post_biometric_day(self, client, auth_headers):
        """POST biometric data with device token."""
        device_headers = self._pair_device(client, auth_headers)
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

    def test_post_biometric_day_session_token(self, client, auth_headers):
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

    def test_read_biometrics(self, client, auth_headers):
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

    def test_biometric_upsert(self, client, auth_headers):
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

    def test_delete_biometrics(self, client, auth_headers):
        """DELETE removes all biometric data."""
        client.post(
            "/api/biometrics/daily",
            json={"date": "2026-04-14", "source": "healthkit", "steps": 3000},
            headers=auth_headers,
        )
        resp = client.delete("/api/biometrics/", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["deleted"] >= 1

    def test_fitbit_status_disconnected(self, client, auth_headers):
        """GET /api/fitbit/status returns disconnected by default."""
        resp = client.get("/api/fitbit/status", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["connected"] is False

    def test_oura_status_disconnected(self, client, auth_headers):
        """GET /api/oura/status returns disconnected by default."""
        resp = client.get("/api/oura/status", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["connected"] is False
