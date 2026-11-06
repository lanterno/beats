"""The OAuth integration routers, and single sign-on over HTTP.

Split out of `test_api.py` at the ceiling in roadmaps/file-sizes.md; the
harness is `conftest.py`'s and the shared fixtures `api_helpers.py`'s.
"""

from datetime import UTC, datetime, timedelta

import pytest


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

    def test_calendar_auth_url_returns_google_consent_url(self, client, auth_info):
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

    def test_calendar_status_connected_when_integration_exists(self, client, auth_info):
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

    def test_calendar_status_disconnected_when_no_doc(self, client, auth_info):
        """GET /api/calendar/status with no integration → connected:
        False, provider: None. Pin so the UI can render the
        "Connect Calendar" button on first load."""
        resp = client.get("/api/calendar/status", headers=auth_info["headers"])
        assert resp.status_code == 200
        body = resp.json()
        assert body["connected"] is False
        assert body["provider"] is None

    def test_calendar_events_empty_when_not_connected(self, client, auth_info):
        """GET /api/calendar/events without an integration → []
        (not 500, not "connection required" error). Pin so the
        coach's day context falls through gracefully when the
        user hasn't connected calendar."""
        resp = client.get("/api/calendar/events", headers=auth_info["headers"])
        assert resp.status_code == 200
        assert resp.json() == []

    def test_calendar_disconnect_returns_false_when_not_connected(self, client, auth_info):
        """DELETE /api/calendar/disconnect without an integration →
        disconnected: False (idempotent). Pin so a "disconnect"
        button click on an already-disconnected account doesn't
        500 the user."""
        resp = client.delete("/api/calendar/disconnect", headers=auth_info["headers"])
        assert resp.status_code == 200
        assert resp.json()["disconnected"] is False

    # -------- /api/github --------

    def test_github_auth_url_returns_github_consent_url(self, client, auth_info):
        """GET /api/github/auth-url returns the GitHub OAuth URL."""
        resp = client.get("/api/github/auth-url", headers=auth_info["headers"])
        assert resp.status_code == 200
        url = resp.json()["url"]
        assert url.startswith("https://github.com/login/oauth/authorize?")

    def test_github_status_connected_when_integration_exists(self, client, auth_info):
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

    def test_github_status_disconnected_when_no_doc(self, client, auth_info):
        resp = client.get("/api/github/status", headers=auth_info["headers"])
        assert resp.status_code == 200
        body = resp.json()
        assert body["connected"] is False
        assert body["github_username"] is None

    def test_github_disconnect_returns_true_when_connected(self, client, auth_info):
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

    def test_fitbit_auth_url_returns_fitbit_consent_url(self, client, auth_info):
        resp = client.get("/api/fitbit/auth-url", headers=auth_info["headers"])
        assert resp.status_code == 200
        url = resp.json()["url"]
        assert url.startswith("https://www.fitbit.com/oauth2/authorize?")

    def test_fitbit_status_connected_reports_user_id(self, client, auth_info):
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

    def test_fitbit_disconnect_returns_true_when_connected(self, client, auth_info):
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

    def test_oura_status_connected_reports_user_id(self, client, auth_info):
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

    def test_oura_disconnect_returns_false_when_not_connected(self, client, auth_info):
        """DELETE /api/oura/disconnect without an integration →
        disconnected: False. Same idempotent contract as
        calendar/disconnect."""
        resp = client.delete("/api/oura/disconnect", headers=auth_info["headers"])
        assert resp.status_code == 200
        assert resp.json()["disconnected"] is False

    # -------- Auth wall — unauthenticated requests rejected --------

    def test_calendar_auth_url_requires_auth(self, client):
        """GET /api/calendar/auth-url without a token → 401.
        Pin the auth gate so an unauthenticated caller can't
        even discover the OAuth flow start URL."""
        resp = client.get("/api/calendar/auth-url")
        assert resp.status_code == 401

    def test_oura_status_requires_auth(self, client):
        resp = client.get("/api/oura/status")
        assert resp.status_code == 401


# Single sign-on — the second front door


class TestSSOAPI:
    """/api/auth/sso/* and /api/account/sso/*.

    The provider is `fake_idp.FakeIdP` (a real token endpoint's checks, real
    RS256 tokens) swapped in through the `get_oidc_registry` dependency, so
    these exercise the real HTTP contract — the flow stored in Mongo and taken
    once, status codes, error envelope codes — with the browser's trip through
    the provider's login page played by `FakeIdP.issue_code`.
    """

    @pytest.fixture(autouse=True)
    def _sso_env(self, auth_info, mongo, monkeypatch):
        from bson import ObjectId

        from beats.api.routers.sso import get_oidc_registry
        from beats.auth.oidc import OIDCRegistry
        from beats.settings import settings
        from fake_idp import REDIRECT_URI, FakeIdP
        from server import app

        self.open_idp = FakeIdP(provider_id="open", name="Open IdP")
        self.closed_idp = FakeIdP(provider_id="closed", name="Closed IdP")
        registry = OIDCRegistry(
            [
                self.open_idp.provider(allow_signup=True),
                self.closed_idp.provider(),
            ]
        )
        app.dependency_overrides[get_oidc_registry] = lambda: registry
        monkeypatch.setattr(settings, "oidc_redirect_uri", REDIRECT_URI)

        # Drop anything an earlier test in this class linked or created, but
        # keep the fixture user the JWT in auth_info points at.
        mongo.users.delete_many({"_id": {"$ne": ObjectId(auth_info["user_id"])}})
        mongo.users.update_one(
            {"_id": ObjectId(auth_info["user_id"])},
            {"$set": {"identities": []}, "$unset": {"sso_provisioned": ""}},
        )
        mongo.credentials.delete_many({})
        mongo.sso_flows.delete_many({})
        yield
        app.dependency_overrides.pop(get_oidc_registry, None)

    def _start(self, client, provider: str, headers=None) -> dict:
        path = f"/api/account/sso/{provider}/link" if headers else f"/api/auth/sso/{provider}/start"
        resp = client.post(path, headers=headers or {})
        assert resp.status_code == 200, resp.text
        return resp.json()

    def _round_trip(self, client, idp, *, headers=None, sub="idp-user-1", **claims):
        """Start, sign in at the provider, and post the code back."""
        started = self._start(client, idp.provider_id, headers)
        code = idp.issue_code(started["authorize_url"], sub=sub, **claims)
        return client.post(
            "/api/auth/sso/complete",
            json={"code": code, "state": started["state"]},
            headers=headers or {},
        )

    def _passkey(self, mongo, user_id: str) -> None:
        mongo.credentials.insert_one(
            {
                "user_id": user_id,
                "credential_id": f"cred-{user_id}",
                "public_key": "k",
                "sign_count": 0,
                "created_at": datetime.now(UTC).isoformat(),
                "device_name": "Laptop",
            }
        )

    # -------- providers --------

    def test_lists_the_configured_providers_in_order(self, client):
        resp = client.get("/api/auth/sso/providers")
        assert resp.status_code == 200
        assert resp.json() == {
            "providers": [
                {"id": "open", "name": "Open IdP"},
                {"id": "closed", "name": "Closed IdP"},
            ]
        }

    def test_an_unknown_provider_is_404(self, client):
        resp = client.post("/api/auth/sso/nope/start")
        assert resp.status_code == 404
        assert resp.json()["code"] == "SSO_UNKNOWN_PROVIDER"

    def test_an_unreachable_provider_is_503(self, client):
        self.open_idp.discovery_issuer = "https://elsewhere.test"
        resp = client.post("/api/auth/sso/open/start")
        assert resp.status_code == 503
        assert resp.json()["code"] == "SSO_UNAVAILABLE"

    # -------- sign-in --------

    def test_sign_up_through_an_open_provider_then_sign_in_again(self, client):
        first = self._round_trip(client, self.open_idp, name="Ada", email="ada@example.com")
        assert first.status_code == 200, first.text
        body = first.json()
        assert (body["intent"], body["provider"], body["created"]) == ("sign_in", "open", True)

        me = client.get(
            "/api/account/me", headers={"Authorization": f"Bearer {body['token']}"}
        ).json()
        assert me["display_name"] == "Ada"
        assert me["sso_provisioned"] is True
        assert [(i["provider"], i["provider_name"], i["email"]) for i in me["identities"]] == [
            ("open", "Open IdP", "ada@example.com")
        ]

        again = self._round_trip(client, self.open_idp)
        assert again.status_code == 200
        assert again.json()["created"] is False

    def test_a_closed_provider_does_not_create_accounts(self, client):
        resp = self._round_trip(client, self.closed_idp)
        assert resp.status_code == 403
        assert resp.json()["code"] == "SSO_SIGNUP_CLOSED"

    def test_a_state_finishes_one_sign_in_and_no_more(self, client):
        started = self._start(client, "open")
        code = self.open_idp.issue_code(started["authorize_url"])
        body = {"code": code, "state": started["state"]}
        assert client.post("/api/auth/sso/complete", json=body).status_code == 200
        replay = client.post("/api/auth/sso/complete", json=body)
        assert replay.status_code == 400
        assert replay.json()["code"] == "SSO_FLOW_EXPIRED"

    def test_an_expired_flow_is_refused(self, client, mongo):
        started = self._start(client, "open")
        code = self.open_idp.issue_code(started["authorize_url"])
        mongo.sso_flows.update_many(
            {}, {"$set": {"expires_at": datetime.now(UTC) - timedelta(seconds=1)}}
        )
        resp = client.post("/api/auth/sso/complete", json={"code": code, "state": started["state"]})
        assert resp.json()["code"] == "SSO_FLOW_EXPIRED"

    def test_a_code_the_provider_refuses_is_401(self, client):
        started = self._start(client, "open")
        resp = client.post(
            "/api/auth/sso/complete", json={"code": "forged", "state": started["state"]}
        )
        assert resp.status_code == 401
        assert resp.json()["code"] == "SSO_REJECTED"

    # -------- linking --------

    def test_link_then_sign_in_with_the_identity(self, client, auth_info):
        resp = self._round_trip(client, self.closed_idp, headers=auth_info["headers"])
        assert resp.status_code == 200, resp.text
        assert resp.json() == {
            "intent": "link",
            "provider": "closed",
            "token": None,
            "created": False,
        }

        # Linked, so even the provider that creates no accounts signs in.
        signed_in = self._round_trip(client, self.closed_idp)
        assert signed_in.status_code == 200
        token = signed_in.json()["token"]
        me = client.get("/api/account/me", headers={"Authorization": f"Bearer {token}"})
        assert me.json()["email"] == "test@example.com"

    def test_a_link_finishes_only_in_the_session_that_started_it(
        self, client, auth_info, other_auth_headers
    ):
        started = self._start(client, "closed", auth_info["headers"])
        code = self.closed_idp.issue_code(started["authorize_url"])
        body = {"code": code, "state": started["state"]}
        for headers in ({}, other_auth_headers):
            resp = client.post("/api/auth/sso/complete", json=body, headers=headers)
            assert resp.status_code in (400, 403)
        # The first attempt spent the flow; neither linked anything.
        me = client.get("/api/account/me", headers=auth_info["headers"]).json()
        assert me["identities"] == []

    def test_an_identity_on_another_account_cannot_be_linked(self, client, auth_info):
        assert self._round_trip(client, self.open_idp).status_code == 200  # creates an account
        resp = self._round_trip(client, self.open_idp, headers=auth_info["headers"])
        assert resp.status_code == 409
        assert resp.json()["code"] == "SSO_ALREADY_LINKED"

    def test_linking_needs_a_session(self, client):
        assert client.post("/api/account/sso/open/link").status_code == 401

    # -------- unlinking --------

    def test_unlink_refuses_when_no_way_in_would_remain(self, client, auth_info):
        self._round_trip(client, self.open_idp, headers=auth_info["headers"])
        resp = client.delete("/api/account/sso/open", headers=auth_info["headers"])
        assert resp.status_code == 409
        assert resp.json()["code"] == "SSO_LAST_CREDENTIAL"

    def test_unlink_with_a_passkey_left(self, client, auth_info, mongo):
        self._round_trip(client, self.open_idp, headers=auth_info["headers"])
        self._passkey(mongo, auth_info["user_id"])
        resp = client.delete("/api/account/sso/open", headers=auth_info["headers"])
        assert resp.status_code == 200
        assert resp.json()["identities"] == []

    def test_unlink_when_not_linked_is_404(self, client, auth_info):
        resp = client.delete("/api/account/sso/open", headers=auth_info["headers"])
        assert resp.status_code == 404
        assert resp.json()["code"] == "SSO_NOT_LINKED"

    # -------- suspension at this door --------

    def test_a_suspended_account_cannot_sign_in_through_a_provider(self, client, mongo):
        """The door refuses after the code exchange, so only someone the
        provider vouched for learns that the account is suspended — and the
        refusal carries the address to write to."""
        from beats.brand import CONTACT_EMAIL

        created = self._round_trip(client, self.open_idp).json()
        assert created["token"]
        mongo.users.update_one(
            {"identities.subject": "idp-user-1"},
            {
                "$set": {
                    "suspended_at": datetime.now(UTC).isoformat(),
                    "suspended_kind": "abuse",
                    "suspended_by": "test",
                    "suspended_reason": "testing",
                }
            },
        )

        resp = self._round_trip(client, self.open_idp)

        assert resp.status_code == 403, resp.text
        assert resp.json()["code"] == "ACCOUNT_SUSPENDED"
        assert CONTACT_EMAIL in resp.json()["detail"]
