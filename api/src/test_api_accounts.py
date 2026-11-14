"""The account routes, the authentication middleware, logout and token
revocation, the registration doors and the rate limits.

Split out of `test_api.py` at the size ceiling (CLAUDE.md § Conventions); the
harness is `conftest.py`'s and the shared fixtures `api_helpers.py`'s.
"""

from datetime import UTC, datetime

import pytest


class TestAuthenticationMiddleware:
    """Test suite for authentication middleware"""

    def test_all_requests_require_auth(self, client):
        """Test that all requests (including GET) require authentication"""
        response = client.get("/api/projects/")
        assert response.status_code == 401

    def test_post_requests_require_auth(self, client):
        """Test POST requests require authentication"""
        response = client.post("/api/projects/", json={"name": "test", "description": "test"})
        assert response.status_code == 401

    def test_put_requests_require_auth(self, client):
        """Test PUT requests require authentication"""
        response = client.put(
            "/api/projects/", json={"id": "test", "name": "test", "description": "test"}
        )
        assert response.status_code == 401

    def test_invalid_bearer_token(self, client):
        """Test invalid Bearer token is rejected"""
        response = client.get(
            "/api/projects/",
            headers={"Authorization": "Bearer invalid-jwt-token"},
        )
        assert response.status_code == 401
        body = response.json()
        assert "Invalid or expired" in body["detail"]
        assert body["code"] == "INVALID_TOKEN"

    def test_public_endpoints_no_auth(self, client):
        """Test public endpoints don't require auth"""
        response = client.get("/health")
        assert response.status_code == 200

    def test_auth_endpoints_no_auth(self, client):
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

    def test_logout_revokes_token(self, client, auth_info):
        """POST /api/account/logout revokes the token so it can't be used again."""
        token = self._make_token(auth_info["user_id"])
        headers = {"Authorization": f"Bearer {token}"}

        # Token works before logout
        assert client.get("/api/projects/", headers=headers).status_code == 200

        # Logout
        response = client.post("/api/account/logout", headers=headers)
        assert response.status_code == 204

        # Token is now rejected
        assert client.get("/api/projects/", headers=headers).status_code == 401

    def test_logout_without_token_requires_auth(self, client):
        """POST /api/account/logout without a token returns 401."""
        response = client.post("/api/account/logout")
        assert response.status_code == 401

    def test_other_tokens_unaffected_by_logout(self, client, auth_info):
        """Revoking one token doesn't affect other tokens for the same user."""
        token_a = self._make_token(auth_info["user_id"])
        token_b = self._make_token(auth_info["user_id"])

        # Revoke token A
        client.post("/api/account/logout", headers={"Authorization": f"Bearer {token_a}"})

        # Token B still works
        assert (
            client.get("/api/projects/", headers={"Authorization": f"Bearer {token_b}"}).status_code
            == 200
        )


class TestAccountAPI:
    """/api/account/{me,refresh,credentials} — auth-critical endpoints
    consumed by every authenticated client surface (UI, companion, daemon
    pair flow). Previously zero coverage — tests pin the contract so a
    future refactor can't quietly break passkey deletion semantics.
    """

    @pytest.fixture(autouse=True)
    def _reset_account_state(self, auth_info):
        """clean_db is class-scoped, so credentials seeded in one test
        leak into the next. Drop credentials and (re-)ensure the test
        user exists before every test in this class. Also clear the
        session manager's in-memory revoked-tokens set so a refresh-
        test that revokes auth_info's token doesn't 401 every later
        test that reuses auth_info["headers"]."""
        import os

        from bson import ObjectId
        from pymongo import MongoClient

        from beats.api.routers.auth import _session_manager

        dsn = os.environ.get("DB_DSN", "mongodb://localhost:27017")
        db_name = os.environ.get("DB_NAME", "beats_test")
        sync = MongoClient(dsn)
        db = sync[db_name]
        db.credentials.delete_many({})
        # test_me_404 deletes the user; restore it so the rest of the
        # tests can still resolve the JWT's sub.
        db.users.update_one(
            {"_id": ObjectId(auth_info["user_id"])},
            {
                "$set": {
                    "email": "test@example.com",
                    "display_name": "Test User",
                    "created_at": datetime.now(UTC),
                }
            },
            upsert=True,
        )
        sync.close()
        _session_manager._revoked_tokens.clear()
        return

    def _seed_credential(self, user_id: str, credential_id: str, device_name: str = "Test") -> None:
        """Insert a credential row directly to skip the WebAuthn ceremony.
        Schema is the same as auth/storage.py:save_credential writes."""
        import os

        from pymongo import MongoClient

        dsn = os.environ.get("DB_DSN", "mongodb://localhost:27017")
        db_name = os.environ.get("DB_NAME", "beats_test")
        sync_client = MongoClient(dsn)
        db = sync_client[db_name]
        db.credentials.insert_one(
            {
                "user_id": user_id,
                "credential_id": credential_id,
                "public_key": "fake-public-key-base64url",
                "sign_count": 0,
                "created_at": "2026-04-30T10:00:00",
                "device_name": device_name,
            }
        )
        sync_client.close()

    def test_me_returns_current_user(self, client, auth_info):
        resp = client.get("/api/account/me", headers=auth_info["headers"])
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["email"] == "test@example.com"
        assert body["display_name"] == "Test User"
        assert body["identities"] == []
        assert body["sso_provisioned"] is False
        assert set(body) == {"email", "display_name", "identities", "sso_provisioned"}

    def test_me_401_when_user_deleted_under_token(self, client, auth_info):
        """Token still validates JWT-wise but the user row is gone — the
        middleware's account lookup answers 401 INVALID_TOKEN before any
        route runs: the session has ended with the account (an erasure), and
        a client's sign-out handling of a 401 is right for it. This used to
        reach the route and 404."""
        import os

        from bson import ObjectId
        from pymongo import MongoClient

        dsn = os.environ.get("DB_DSN", "mongodb://localhost:27017")
        db_name = os.environ.get("DB_NAME", "beats_test")
        sync_client = MongoClient(dsn)
        sync_client[db_name].users.delete_one({"_id": ObjectId(auth_info["user_id"])})
        sync_client.close()

        resp = client.get("/api/account/me", headers=auth_info["headers"])
        assert resp.status_code == 401
        assert resp.json()["code"] == "INVALID_TOKEN"

    def test_refresh_issues_a_new_working_token(self, client, auth_info):
        resp = client.post("/api/account/refresh", headers=auth_info["headers"])
        assert resp.status_code == 200, resp.text
        new_token = resp.json()["token"]
        assert new_token
        assert new_token != auth_info["headers"]["Authorization"].split(" ", 1)[1]

        # The new token actually works on a protected endpoint.
        new_headers = {"Authorization": f"Bearer {new_token}"}
        assert client.get("/api/projects/", headers=new_headers).status_code == 200

    def test_refresh_without_bearer_returns_401(self, client):
        resp = client.post("/api/account/refresh")
        # The auth middleware fires before the handler — MISSING_TOKEN, not
        # the handler's "Bearer token required". Either way it's a 401.
        assert resp.status_code == 401

    def test_refresh_with_invalid_token_returns_401(self, client):
        resp = client.post(
            "/api/account/refresh",
            headers={"Authorization": "Bearer not-a-jwt"},
        )
        assert resp.status_code == 401

    def test_credentials_list_empty_for_fresh_user(self, client, auth_info):
        resp = client.get("/api/account/credentials", headers=auth_info["headers"])
        assert resp.status_code == 200
        assert resp.json() == []

    def test_credentials_list_returns_seeded_creds(self, client, auth_info):
        self._seed_credential(auth_info["user_id"], "cred-A", "Mac")
        self._seed_credential(auth_info["user_id"], "cred-B", "iPhone")

        resp = client.get("/api/account/credentials", headers=auth_info["headers"])
        assert resp.status_code == 200
        body = resp.json()
        ids = sorted(c["id"] for c in body)
        assert ids == ["cred-A", "cred-B"]
        names = sorted(c["device_name"] for c in body)
        assert names == ["Mac", "iPhone"]

    def test_delete_credential_removes_non_last(self, client, auth_info):
        self._seed_credential(auth_info["user_id"], "cred-keep")
        self._seed_credential(auth_info["user_id"], "cred-doomed")

        resp = client.delete(
            "/api/account/credentials/cred-doomed",
            headers=auth_info["headers"],
        )
        assert resp.status_code == 204, resp.text

        # Only the survivor remains.
        listing = client.get("/api/account/credentials", headers=auth_info["headers"]).json()
        assert [c["id"] for c in listing] == ["cred-keep"]

    def test_delete_last_credential_blocked(self, client, auth_info):
        """Locks in the "must keep at least one passkey" guard. Without
        this, a user could nuke their last credential and lock themselves
        out — the very scenario auth.py's orphan-retry doesn't recover
        from (orphan happens *before* the user has any credential, this
        guard prevents them from getting *back* into that state)."""
        self._seed_credential(auth_info["user_id"], "cred-only")

        resp = client.delete(
            "/api/account/credentials/cred-only",
            headers=auth_info["headers"],
        )
        assert resp.status_code == 400, resp.text
        assert "only passkey" in resp.json()["detail"].lower()

    def test_delete_nonexistent_credential_returns_404(self, client, auth_info):
        # Seed two so the keep-at-least-one guard (count <= 1) doesn't
        # short-circuit our 404 path. delete_credential checks the count
        # before checking existence — a single seeded credential plus a
        # request for a different ID would 400 with "only passkey", which
        # isn't the branch we're documenting here.
        self._seed_credential(auth_info["user_id"], "cred-real-1")
        self._seed_credential(auth_info["user_id"], "cred-real-2")

        resp = client.delete(
            "/api/account/credentials/cred-does-not-exist",
            headers=auth_info["headers"],
        )
        assert resp.status_code == 404

    def test_add_credential_start_offers_options_for_the_session(self, client, auth_info):
        """The add-passkey door (#376). /api/auth/register/start cannot do
        this — it 409s for an email that already has a credential — so an
        account could hold exactly one passkey and no second device."""
        self._seed_credential(auth_info["user_id"], "AQIDBA", "Mac")

        resp = client.post("/api/account/credentials/start", headers=auth_info["headers"])

        assert resp.status_code == 200, resp.text
        options = resp.json()["options"]
        assert options["challenge"]
        assert options["user"]["name"] == "test@example.com"
        # The passkey already held is excluded, so the browser refuses to
        # enrol the same authenticator twice instead of making a duplicate.
        assert [c["id"] for c in options["excludeCredentials"]] == ["AQIDBA"]
        # No token: the caller already holds a session, and a second would
        # have to be revoked on logout like the first.
        assert "token" not in resp.json()

    def test_add_credential_verify_saves_against_the_session_user(
        self, client, auth_info, monkeypatch
    ):
        """The account a verified passkey is saved against is the token's,
        never anything the ceremony carries."""
        from beats.auth import webauthn as webauthn_module

        class _FakeVerification:
            credential_id = b"\x0a\x0b\x0c"
            credential_public_key = b"\x01\x02"
            sign_count = 0

        monkeypatch.setattr(
            webauthn_module, "verify_registration_response", lambda **_kw: _FakeVerification()
        )
        self._seed_credential(auth_info["user_id"], "AQIDBA", "Mac")
        assert (
            client.post("/api/account/credentials/start", headers=auth_info["headers"]).status_code
            == 200
        )

        resp = client.post(
            "/api/account/credentials/verify",
            json={"credential": {"id": "whatever"}, "device_name": "Work laptop"},
            headers=auth_info["headers"],
        )

        assert resp.status_code == 200, resp.text
        assert resp.json() == {"verified": True}
        listing = client.get("/api/account/credentials", headers=auth_info["headers"]).json()
        assert sorted(c["device_name"] for c in listing) == ["Mac", "Work laptop"]

    def test_add_credential_verify_without_a_start_is_400(self, client, auth_info):
        resp = client.post(
            "/api/account/credentials/verify",
            json={"credential": {"id": "whatever"}},
            headers=auth_info["headers"],
        )
        assert resp.status_code == 400, resp.text

    def test_account_endpoints_require_auth(self, client):
        for method, path in [
            ("GET", "/api/account/me"),
            ("POST", "/api/account/refresh"),
            ("GET", "/api/account/credentials"),
            ("POST", "/api/account/credentials/start"),
            ("POST", "/api/account/credentials/verify"),
            ("DELETE", "/api/account/credentials/anything"),
        ]:
            resp = client.request(method, path)
            assert resp.status_code == 401, f"{method} {path} should require auth"


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


class TestRegisterStartOrphanRetry:
    """A user record without credentials is an abandoned /register/start.
    The handler must let the same email retry instead of returning 409 —
    the orphan can't log in (no credential exists for them) and would
    otherwise be locked out forever.
    """

    def test_orphan_user_can_retry_register_start(self, client):
        """register/start for an existing email with zero credentials reuses
        the user instead of returning 409."""
        import os

        from bson import ObjectId
        from pymongo import MongoClient

        dsn = os.environ.get("DB_DSN", "mongodb://localhost:27017")
        db_name = os.environ.get("DB_NAME", "beats_test")
        sync_client = MongoClient(dsn)
        db = sync_client[db_name]

        # Simulate an abandoned /register/start: a user row, no credentials.
        email = "orphan-retry@example.com"
        orphan_id = ObjectId()
        db.users.insert_one({"_id": orphan_id, "email": email, "display_name": None})
        sync_client.close()

        # Same email comes back to retry registration. Should succeed and
        # reuse the existing user_id (no second user row is created).
        response = client.post(
            "/api/auth/register/start",
            json={"email": email, "display_name": "Retry"},
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["user_id"] == str(orphan_id)

        # And — exactly one user row for that email, not two.
        sync_client = MongoClient(dsn)
        db = sync_client[db_name]
        assert db.users.count_documents({"email": email}) == 1
        sync_client.close()


class TestAuthRouterErrorPaths:
    """Error-path coverage for the unauthenticated /api/auth/*
    endpoints. The happy-path crypto verification needs a real
    authenticator, but the pre-checks (existing-with-credentials,
    no-pending-registration, no-pending-authentication, malformed
    credential) are all reachable via plain HTTP and worth pinning
    — these are the user-facing error envelopes."""

    @pytest.fixture(autouse=True)
    def _reset_session_manager(self):
        """The auth router's SessionManager is a process-global
        singleton. Earlier tests in the suite (e.g. orphan-retry,
        rate-limit) call /register/start or /login/options, which
        leave challenges and pending registrations in memory.
        Clear them before each test in this class so the
        no-pending-registration paths actually fire."""
        from beats.api.routers.auth import _session_manager

        _session_manager._challenges.clear()
        _session_manager._pending_registrations.clear()
        return

    def _db(self):
        import os

        from pymongo import MongoClient

        dsn = os.environ.get("DB_DSN", "mongodb://localhost:27017")
        db_name = os.environ.get("DB_NAME", "beats_test")
        sync_client = MongoClient(dsn)
        return sync_client, sync_client[db_name]

    def test_register_start_existing_email_with_credentials_returns_409(self, client):
        """A user row with at least one credential → 409 on
        register/start (the email is "really registered"). Pin the
        409 vs the 200 orphan-retry path (test_orphan_user_can_retry_register_start
        covers the 200 case)."""
        from bson import ObjectId

        sync_client, db = self._db()
        email = "already-registered@example.com"
        user_id = ObjectId()
        db.users.insert_one({"_id": user_id, "email": email, "display_name": "Already"})
        # Add a credential — turns the user from orphan into "real"
        db.credentials.insert_one(
            {
                "user_id": str(user_id),
                "credential_id": "cred-existing",
                "public_key": "pk",
                "sign_count": 0,
                "created_at": "2026-04-01T00:00:00",
            }
        )
        sync_client.close()

        resp = client.post(
            "/api/auth/register/start",
            json={"email": email, "display_name": "Retry"},
        )
        assert resp.status_code == 409
        assert "already registered" in resp.json()["detail"].lower()

    def test_register_verify_without_pending_returns_400(self, client):
        """POST /register/verify before /register/start was called
        → 400 "No pending registration found". Pin the user-facing
        envelope so an attacker who skips the challenge step gets
        a clear error rather than crashing the verify path."""
        resp = client.post(
            "/api/auth/register/verify",
            json={
                "credential": {
                    "id": "fake",
                    "rawId": "fake",
                    "response": {},
                    "type": "public-key",
                },
                "device_name": "Test",
            },
        )
        assert resp.status_code == 400
        assert "No pending registration" in resp.json()["detail"]

    def test_login_verify_with_invalid_credential_returns_401(self, client):
        """POST /login/verify without a pending challenge / with an
        unknown credential → 401. Pin the 401 envelope (ValueError
        from WebAuthnManager.verify_authentication maps to
        UNAUTHORIZED, not BAD_REQUEST)."""
        resp = client.post(
            "/api/auth/login/verify",
            json={
                "credential": {
                    "id": "nonexistent-cred",
                    "rawId": "nonexistent-cred",
                    "response": {},
                    "type": "public-key",
                }
            },
        )
        assert resp.status_code == 401

    def test_login_options_returns_options_dict(self, client):
        """GET /login/options returns a dict with rpId + challenge +
        empty allowCredentials. Pin the empty allowCredentials list
        so a regression doesn't start leaking registered credential
        IDs to unauthenticated callers (would let an attacker
        enumerate user existence)."""
        resp = client.get("/api/auth/login/options")
        assert resp.status_code == 200
        opts = resp.json()["options"]
        assert "challenge" in opts
        assert opts["allowCredentials"] == []
        assert "rpId" in opts

    def test_register_start_brand_new_email_creates_user(self, client):
        """POST /register/start with an email that has NO user row →
        creates a new user (the `else` branch at line 133) and
        returns its id. Pin both: 200 status AND a fresh user_id
        is assigned (not the existing-user ObjectId)."""
        sync_client, db = self._db()
        email = "fresh-account@example.com"
        # Confirm the email starts unknown
        assert db.users.count_documents({"email": email}) == 0
        sync_client.close()

        resp = client.post(
            "/api/auth/register/start",
            json={"email": email, "display_name": "Fresh"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        new_user_id = body["user_id"]
        assert new_user_id  # non-empty

        # Exactly one user row created with the matching email
        sync_client, db = self._db()
        assert db.users.count_documents({"email": email}) == 1
        sync_client.close()

    def test_register_verify_value_error_returns_400_envelope(self, client, monkeypatch):
        """When a pending registration challenge exists AND the user
        is found, but webauthn.verify_registration raises ValueError
        (malformed credential / signature mismatch), the response is
        400 with the exception text in the detail. Pin the 400
        envelope — distinct from the no-pending 400 (different
        cause, same status)."""
        from bson import ObjectId

        from beats.api.routers import auth as auth_router

        sync_client, db = self._db()
        # Seed a user the verify handler will look up
        user_id = str(ObjectId())
        db.users.insert_one(
            {
                "_id": ObjectId(user_id),
                "email": "verify-test@example.com",
                "display_name": "Verify",
            }
        )
        sync_client.close()

        # Register a pending challenge for this user_id directly,
        # bypassing the OAuth crypto roundtrip
        challenge_bytes = b"X" * 32
        auth_router._session_manager.store_challenge(challenge_bytes, "registration")
        auth_router._session_manager.store_pending_registration(challenge_bytes, user_id)

        # Make verify_registration raise ValueError — this is the
        # branch that catches malformed credentials / sig mismatches
        async def fake_verify_registration(*args, **kwargs):
            raise ValueError("malformed credential blob")

        # Patch through the WebAuthnDep — find the actual instance
        # the router uses
        from beats.auth.webauthn import WebAuthnManager

        monkeypatch.setattr(WebAuthnManager, "verify_registration", fake_verify_registration)

        resp = client.post(
            "/api/auth/register/verify",
            json={
                "credential": {
                    "id": "fake",
                    "rawId": "fake",
                    "response": {},
                    "type": "public-key",
                },
                "device_name": "Test",
            },
        )
        assert resp.status_code == 400
        # Exception message propagates so the user sees the actual
        # reason (not just a generic "registration failed")
        assert "malformed credential blob" in resp.json()["detail"]


class TestRateLimiting:
    """Test that auth endpoints are rate-limited."""

    def test_login_options_rate_limited(self, client):
        """GET /api/auth/login/options is rate-limited after repeated requests."""
        for _ in range(10):
            client.get("/api/auth/login/options")

        response = client.get("/api/auth/login/options")
        assert response.status_code == 429

    def test_an_exhausted_auth_route_answers_in_the_envelope(self, client):
        """slowapi's own handler answered `{"error": ...}`, which none of the
        clients parse. A 429 is an error like any other: `{detail, code}`, and
        a `Retry-After` within the minute the limit counts over."""
        for _ in range(10):
            client.get("/api/auth/login/options")

        response = client.get("/api/auth/login/options")
        assert response.status_code == 429
        body = response.json()
        assert set(body) == {"detail", "code"}
        assert body["code"] == "RATE_LIMITED"
        assert "10 per 1 minute" in body["detail"]
        assert 1 <= int(response.headers["Retry-After"]) <= 60

    def test_pair_exchange_rate_limited(self, client):
        """POST /api/device/pair/exchange is rate-limited.

        Endpoint is unauthenticated and accepts a 6-char base32 pairing
        code (~30 bits of entropy). Without a rate limit, an attacker
        with network access could grind through the keyspace. Cap is
        10/min — eleventh request in the same window must 429.
        """
        for _ in range(10):
            client.post(
                "/api/device/pair/exchange",
                json={"code": "AAAAAA", "device_name": "test"},
            )

        response = client.post(
            "/api/device/pair/exchange",
            json={"code": "AAAAAA", "device_name": "test"},
        )
        assert response.status_code == 429

    # -------- whose address a limit counts --------

    @staticmethod
    def _through_cloud_run():
        """Requests whose peer is Cloud Run's front end, as the uvicorn access log
        shows it, a proxy .env.test trusts (as terraform does). Not entered as a
        context manager: that would run the lifespan again, and its shutdown
        would disconnect the session's database."""
        from starlette.testclient import TestClient

        from server import app

        return TestClient(app, client=("169.254.169.126", 443))

    def test_visitors_behind_the_proxy_get_a_bucket_each(self, client):
        """Behind Cloud Run every request came from the front end's address, so
        every visitor shared one bucket: one script could lock everyone out of
        signing in. The limit counts per address the proxy appended."""
        proxy = self._through_cloud_run()
        first = {"X-Forwarded-For": "203.0.113.1"}
        for _ in range(10):
            assert proxy.get("/api/auth/login/options", headers=first).status_code == 200
        assert proxy.get("/api/auth/login/options", headers=first).status_code == 429

        second = {"X-Forwarded-For": "203.0.113.2"}
        assert proxy.get("/api/auth/login/options", headers=second).status_code == 200

    def test_a_visitor_cannot_write_itself_a_fresh_bucket(self, client):
        """Entries left of the one the proxy appended are the client's own
        words; a new one on every request must not reset its count."""
        proxy = self._through_cloud_run()
        for i in range(10):
            spoofed = {"X-Forwarded-For": f"198.51.100.{i}, 203.0.113.1"}
            proxy.get("/api/auth/login/options", headers=spoofed)

        again = {"X-Forwarded-For": "198.51.100.99, 203.0.113.1"}
        assert proxy.get("/api/auth/login/options", headers=again).status_code == 429

    def test_a_peer_that_is_no_trusted_proxy_is_not_believed(self, client):
        """Straight from a peer that is not a trusted proxy, X-Forwarded-For is
        only the caller's claim: the limit counts the peer."""
        for i in range(10):
            client.get("/api/auth/login/options", headers={"X-Forwarded-For": f"198.51.100.{i}"})

        claimed = {"X-Forwarded-For": "198.51.100.99"}
        assert client.get("/api/auth/login/options", headers=claimed).status_code == 429
