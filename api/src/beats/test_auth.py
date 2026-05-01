"""Tests for the auth layer — SessionManager, WebAuthnManager, storage."""

from __future__ import annotations

import time

import jwt
import pytest

# =============================================================================
# SessionManager — JWT tokens, WebAuthn challenges, revocation
# =============================================================================


JWT_SECRET = "test-secret-do-not-use-in-prod-this-is-a-fixed-string-32+bytes"


def _sm(session_ttl: int = 3600):
    """Build a SessionManager with a fixed JWT secret."""
    from beats.auth.session import SessionManager

    return SessionManager(JWT_SECRET, session_ttl=session_ttl)


class TestSessionManagerSessionTokens:
    """create_session_token / validate_session_token round-trip,
    plus the four error paths: expired, wrong type, revoked,
    malformed. Pin every path — auth bugs ship silently."""

    def test_create_validate_round_trip(self):
        sm = _sm()
        token = sm.create_session_token("user-1", email="a@b.com")
        payload = sm.validate_session_token(token)
        assert payload is not None
        assert payload["sub"] == "user-1"
        assert payload["email"] == "a@b.com"
        assert payload["type"] == "session"
        # jti is per-token unique — pin so two issuances differ
        assert "jti" in payload

    def test_token_without_email_omits_email_claim(self):
        """Pin: an empty email kwarg results in NO email field on
        the payload (not "" — absent). Lets the consumer branch
        on `.get("email")` cleanly."""
        sm = _sm()
        token = sm.create_session_token("user-2")
        payload = sm.validate_session_token(token)
        assert payload is not None
        assert "email" not in payload

    def test_two_tokens_have_distinct_jtis(self):
        """jti is a per-token uuid — two tokens for the same user
        are distinct by jti. Pin so the revocation list can't
        accidentally revoke ALL sessions for a user just because
        one was revoked."""
        sm = _sm()
        a = sm.create_session_token("user-1")
        b = sm.create_session_token("user-1")
        pa = sm.validate_session_token(a)
        pb = sm.validate_session_token(b)
        assert pa is not None and pb is not None
        assert pa["jti"] != pb["jti"]

    def test_validate_returns_none_for_expired_token(self):
        """An expired session token must validate to None, not
        raise. Pin so middleware can branch on None rather than
        catch jwt.ExpiredSignatureError."""
        sm = _sm(session_ttl=1)
        token = sm.create_session_token("user-1")
        # Sleep past expiry
        time.sleep(1.1)
        assert sm.validate_session_token(token) is None

    def test_validate_returns_none_for_device_token(self):
        """A device token presented at a session-only endpoint
        must validate to None — pin the type field check so a
        compromised device token can't be reused as a session
        token."""
        sm = _sm()
        device_token = sm.create_device_token("user-1", "device-abc")
        assert sm.validate_session_token(device_token) is None

    def test_validate_returns_none_for_garbage(self):
        sm = _sm()
        assert sm.validate_session_token("not-a-jwt") is None
        assert sm.validate_session_token("") is None

    def test_validate_returns_none_for_wrong_secret(self):
        """A token signed with secret A must not validate against
        secret B. Pin so a leaked secret rotation actually
        invalidates outstanding tokens."""
        from beats.auth.session import SessionManager

        sm_a = SessionManager("secret-a-first-deploy-with-enough-length-bytes")
        sm_b = SessionManager("secret-b-second-deploy-with-enough-length-bytes")
        token = sm_a.create_session_token("user-1")
        assert sm_b.validate_session_token(token) is None


class TestSessionManagerDeviceTokens:
    """Device tokens (daemon JWTs) are long-lived (no exp) and
    carry a device_id. Pin both the type check and the absence
    of an exp claim — otherwise a long-running daemon would silently
    stop talking to the API after token expiry."""

    def test_device_token_round_trip(self):
        sm = _sm()
        token = sm.create_device_token("user-1", "device-abc")
        payload = sm.validate_device_token(token)
        assert payload is not None
        assert payload["sub"] == "user-1"
        assert payload["device_id"] == "device-abc"
        assert payload["type"] == "device"

    def test_device_token_has_no_exp_claim(self):
        """Daemons run for months — pin no exp claim is set so
        they don't surprise-fail at a deploy boundary."""
        sm = _sm()
        token = sm.create_device_token("user-1", "device-abc")
        # Decode without expiry verification to inspect raw payload
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"], options={"verify_exp": False})
        assert "exp" not in payload

    def test_session_token_rejected_by_validate_device(self):
        """Type confusion the other direction — a session token
        must not pass validate_device_token. Pin so the device
        endpoints can't accept user-session JWTs."""
        sm = _sm()
        session_token = sm.create_session_token("user-1")
        assert sm.validate_device_token(session_token) is None

    def test_validate_device_returns_none_for_garbage(self):
        sm = _sm()
        assert sm.validate_device_token("not-a-jwt") is None


class TestSessionManagerRevocation:
    """revoke_token + the validate-rejects-revoked path. Pin so a
    "logout" actually invalidates the token rather than just
    clearing the client-side cookie."""

    def test_revoked_token_no_longer_validates(self):
        sm = _sm()
        token = sm.create_session_token("user-1")
        assert sm.validate_session_token(token) is not None  # baseline
        sm.revoke_token(token)
        assert sm.validate_session_token(token) is None

    def test_revoke_invalid_token_is_silent(self):
        """Revoking a malformed token is a no-op (doesn't raise) —
        pin so a logout endpoint can call revoke unconditionally."""
        sm = _sm()
        sm.revoke_token("not-a-jwt")
        sm.revoke_token("")

    def test_revocation_list_self_cleans_after_natural_expiry(self):
        """An expired token's entry is removed from the revocation
        list on next cleanup — keeps memory bounded. Pin so a
        long-running process doesn't grow the revoked dict
        unboundedly."""
        sm = _sm(session_ttl=1)
        token = sm.create_session_token("user-1")
        sm.revoke_token(token)
        # internals exposed — _revoked_tokens dict
        assert token in sm._revoked_tokens
        time.sleep(1.1)
        # Validation triggers cleanup
        sm.validate_session_token("trigger-cleanup")
        assert token not in sm._revoked_tokens


class TestSessionManagerRefresh:
    """refresh_token issues a new token from a valid one and
    revokes the old. Pin both halves of the trade — losing
    either would either let stolen tokens live forever (no
    rotation) or break the user session on every refresh
    attempt (no replacement)."""

    def test_refresh_issues_new_token_and_revokes_old(self):
        sm = _sm()
        old = sm.create_session_token("user-1", email="a@b.com")
        new = sm.refresh_token(old)
        assert new is not None
        assert new != old
        # New token validates with the same identity
        payload = sm.validate_session_token(new)
        assert payload is not None
        assert payload["sub"] == "user-1"
        assert payload["email"] == "a@b.com"
        # Old token is now invalid
        assert sm.validate_session_token(old) is None

    def test_refresh_invalid_token_returns_none(self):
        """Refreshing an expired or garbage token returns None
        — pin so the refresh endpoint maps that to 401 rather
        than silently issuing a fresh token to an unauthenticated
        caller."""
        sm = _sm(session_ttl=1)
        token = sm.create_session_token("user-1")
        time.sleep(1.1)
        assert sm.refresh_token(token) is None
        assert sm.refresh_token("garbage") is None


class TestSessionManagerChallenges:
    """WebAuthn challenges are stored in-memory with a 5-minute
    TTL. Pin: store-then-validate-then-consumed (one-time use),
    type mismatch rejection, and expired-cleanup."""

    def test_store_and_validate_round_trip(self):
        sm = _sm()
        challenge_bytes = b"random-bytes-32-byte-challenge!!"
        b64 = sm.store_challenge(challenge_bytes, challenge_type="registration")
        assert sm.validate_challenge(b64, "registration") is True

    def test_validate_consumes_challenge_one_time_use(self):
        """A challenge that validated once cannot validate again.
        Pin so a replayed registration response can't succeed
        twice."""
        sm = _sm()
        b64 = sm.store_challenge(b"X" * 32, challenge_type="registration")
        assert sm.validate_challenge(b64, "registration") is True
        assert sm.validate_challenge(b64, "registration") is False

    def test_validate_rejects_type_mismatch(self):
        """A registration challenge presented at an authentication
        endpoint must NOT validate. Pin so an attacker can't
        recycle a registration challenge for login."""
        sm = _sm()
        b64 = sm.store_challenge(b"X" * 32, challenge_type="registration")
        assert sm.validate_challenge(b64, "authentication") is False
        # And the type-mismatch attempt does NOT consume the challenge
        assert sm.validate_challenge(b64, "registration") is True

    def test_validate_rejects_unknown_challenge(self):
        sm = _sm()
        assert sm.validate_challenge("never-stored", "registration") is False

    def test_get_current_challenge_returns_most_recent(self):
        """Multiple stored challenges of the same type → most
        recent wins. Pin so a slow user (challenge A) followed by
        a fresh request (challenge B) verifies against B."""
        sm = _sm()
        first = sm.store_challenge(b"A" * 32, challenge_type="authentication")
        # Tiny sleep so created_at differs
        time.sleep(0.01)
        second = sm.store_challenge(b"B" * 32, challenge_type="authentication")
        assert sm.get_current_challenge("authentication") == second
        assert second != first

    def test_get_stored_challenge_decodes_back_to_bytes(self):
        """get_stored_challenge round-trips through urlsafe_b64
        even when the base64 length needs padding. Pin so the
        py_webauthn library gets bytes it can verify."""
        sm = _sm()
        original = bytes(range(32))  # 32 bytes — produces unpadded b64
        sm.store_challenge(original, challenge_type="authentication")
        recovered = sm.get_stored_challenge("authentication")
        assert recovered == original

    def test_expired_challenges_get_cleaned_up(self):
        """A challenge older than CHALLENGE_TTL (5min) is dropped
        on the next cleanup. Pin by monkeypatching time.time so
        the test isn't slow."""
        from beats.auth import session as session_mod

        sm = _sm()
        b64 = sm.store_challenge(b"X" * 32, challenge_type="registration")
        # Force the challenge's created_at far into the past
        sm._challenges[b64].created_at = time.time() - session_mod.CHALLENGE_TTL - 1
        # Any cleanup-triggering call drops it
        sm._cleanup_expired_challenges()
        assert sm.validate_challenge(b64, "registration") is False
        assert sm.get_challenge_count() == 0

    def test_pending_registration_round_trip(self):
        """store_pending_registration + get_pending_registration_user_id
        keep the user_id associated with a registration challenge.
        Pin so the verify step can map the validated challenge
        back to "this user is registering"."""
        sm = _sm()
        sm.store_challenge(b"R" * 32, challenge_type="registration")
        sm.store_pending_registration(b"R" * 32, user_id="user-1")
        assert sm.get_pending_registration_user_id("registration") == "user-1"

    def test_pending_registration_dropped_with_expired_challenge(self):
        """When a registration challenge expires and is cleaned up,
        the pending-registration user_id is dropped too. Pin so a
        registration that times out can't be completed later by
        replaying the user_id."""
        from beats.auth import session as session_mod

        sm = _sm()
        sm.store_challenge(b"R" * 32, challenge_type="registration")
        sm.store_pending_registration(b"R" * 32, user_id="user-1")
        # Expire the challenge
        b64_key = next(iter(sm._challenges))
        sm._challenges[b64_key].created_at = time.time() - session_mod.CHALLENGE_TTL - 1
        sm._cleanup_expired_challenges()
        assert sm.get_pending_registration_user_id("registration") is None


# =============================================================================
# WebAuthnManager — registration + authentication orchestration
# =============================================================================


class _FakeCredentialStorage:
    """In-memory credential storage. Mirrors MongoCredentialStorage's
    surface — the methods WebAuthnManager calls."""

    def __init__(self):
        self._creds: list[tuple[str, object]] = []

    async def is_registered(self, user_id: str | None = None) -> bool:
        if user_id:
            return any(uid == user_id for uid, _ in self._creds)
        return len(self._creds) > 0

    async def get_credentials(self, user_id: str | None = None):
        if user_id:
            return [c for uid, c in self._creds if uid == user_id]
        return [c for _, c in self._creds]

    async def get_credential_ids(self, user_id: str | None = None) -> list[str]:
        creds = await self.get_credentials(user_id)
        return [c.credential_id for c in creds]

    async def get_credential_by_id(self, credential_id: str):
        for _, c in self._creds:
            if c.credential_id == credential_id:
                return c
        return None

    async def get_user_id_for_credential(self, credential_id: str) -> str | None:
        for uid, c in self._creds:
            if c.credential_id == credential_id:
                return uid
        return None

    async def save_credential(
        self, user_id, credential_id, public_key, sign_count, device_name=None
    ):
        from beats.auth.storage import StoredCredential

        cred = StoredCredential(
            credential_id=credential_id,
            public_key=public_key,
            sign_count=sign_count,
            created_at="2026-04-01T00:00:00",
            device_name=device_name,
        )
        self._creds.append((user_id, cred))
        return cred

    async def delete_credential(self, credential_id, user_id) -> bool:
        for i, (uid, c) in enumerate(self._creds):
            if uid == user_id and c.credential_id == credential_id:
                self._creds.pop(i)
                return True
        return False

    async def count_credentials(self, user_id: str) -> int:
        return sum(1 for uid, _ in self._creds if uid == user_id)

    async def update_sign_count(self, credential_id, new_sign_count) -> bool:
        from beats.auth.storage import StoredCredential

        for i, (uid, c) in enumerate(self._creds):
            if c.credential_id == credential_id:
                self._creds[i] = (
                    uid,
                    StoredCredential(
                        credential_id=c.credential_id,
                        public_key=c.public_key,
                        sign_count=new_sign_count,
                        created_at=c.created_at,
                        device_name=c.device_name,
                    ),
                )
                return True
        return False


class _FakeUserRepo:
    def __init__(self, users: list | None = None):
        self._users = users or []

    async def get_by_id(self, user_id: str):
        for u in self._users:
            if u.id == user_id:
                return u
        return None


def _wam(
    *,
    storage=None,
    session=None,
    user_repo=None,
    rp_id="beats.test",
    rp_name="Beats",
    origin="https://beats.test",
):
    from beats.auth.webauthn import WebAuthnManager

    return WebAuthnManager(
        rp_id=rp_id,
        rp_name=rp_name,
        origin=origin,
        credential_storage=storage or _FakeCredentialStorage(),
        session_manager=session or _sm(),
        user_repo=user_repo or _FakeUserRepo(),
    )


def _user(
    id_: str = "user-1",
    email: str = "ahmed@example.com",
    display_name: str | None = "Ahmed",
):
    from beats.domain.models import User

    return User(id=id_, email=email, display_name=display_name)


class TestWebAuthnRegistrationOptions:
    """get_registration_options builds the dict the browser hands
    to navigator.credentials.create. Two side effects: the
    challenge is stored on SessionManager AND the
    pending-registration user_id is recorded — so verify_*
    can find both."""

    async def test_returns_options_dict_with_required_keys(self):
        wam = _wam()
        out = await wam.get_registration_options(_user())
        for key in (
            "rp",
            "user",
            "challenge",
            "pubKeyCredParams",
            "authenticatorSelection",
            "attestation",
            "excludeCredentials",
        ):
            assert key in out, f"missing key {key!r}"
        assert out["rp"]["id"] == "beats.test"
        assert out["rp"]["name"] == "Beats"
        assert out["user"]["name"] == "ahmed@example.com"
        assert out["user"]["displayName"] == "Ahmed"
        assert "id" in out["user"]
        # authenticatorSelection: residentKey REQUIRED, userVerification PREFERRED
        assert out["authenticatorSelection"]["residentKey"] == "required"
        assert out["authenticatorSelection"]["userVerification"] == "preferred"

    async def test_stores_challenge_and_pending_registration(self):
        """Side effect: SessionManager has a "registration" challenge
        AND the pending-registration map points to the user. Pin
        both so verify_registration can find them."""
        sm = _sm()
        wam = _wam(session=sm)
        await wam.get_registration_options(_user(id_="user-42"))
        assert sm.get_current_challenge("registration") is not None
        assert sm.get_pending_registration_user_id("registration") == "user-42"

    async def test_excludes_existing_credentials(self):
        """A user with an existing credential gets it surfaced in
        excludeCredentials so the browser refuses to register the
        same authenticator twice. Pin so a second registration
        attempt with the same hardware shows a useful error rather
        than silently overwriting."""
        storage = _FakeCredentialStorage()
        await storage.save_credential(
            user_id="user-1",
            credential_id="AQIDBA",  # valid base64url, decodes to 4 bytes
            public_key="AQID",
            sign_count=0,
        )
        wam = _wam(storage=storage)
        out = await wam.get_registration_options(_user())
        ids = [c["id"] for c in out["excludeCredentials"]]
        assert "AQIDBA" in ids

    async def test_user_without_display_name_falls_back_to_email(self):
        """display_name=None → user.displayName is the email. Pin
        so the browser's native picker shows a non-empty label."""
        wam = _wam()
        out = await wam.get_registration_options(_user(display_name=None))
        assert out["user"]["displayName"] == "ahmed@example.com"


class TestWebAuthnRegistrationVerificationGuards:
    """verify_registration's crypto path needs a real authenticator
    signature, so cover the PRE-checks (business logic) here. The
    crypto path is exercised by HTTP integration tests in test_api."""

    async def test_max_credentials_per_user_blocks_new_registration(self):
        """A user at MAX_CREDENTIALS_PER_USER (10) → ValueError
        BEFORE the crypto path runs. Pin so a malicious or buggy
        client can't register unbounded keys."""
        from beats.auth.webauthn import MAX_CREDENTIALS_PER_USER

        storage = _FakeCredentialStorage()
        for i in range(MAX_CREDENTIALS_PER_USER):
            await storage.save_credential(
                user_id="user-1",
                credential_id=f"cred-{i}",
                public_key=f"pk-{i}",
                sign_count=0,
            )
        wam = _wam(storage=storage)
        with pytest.raises(ValueError, match="Maximum"):
            await wam.verify_registration(credential={}, user=_user())

    async def test_no_pending_challenge_raises(self):
        """verify_registration without a prior get_registration_options
        call → ValueError. Pin so an attacker who skips the challenge
        step gets rejected at the service layer."""
        wam = _wam()
        with pytest.raises(ValueError, match="No pending registration"):
            await wam.verify_registration(credential={}, user=_user())

    async def test_happy_path_persists_credential_and_returns_token(self, monkeypatch):
        """Mock py_webauthn's verify_registration_response to return
        a fake success object — exercises the try-block (lines
        148-173): save_credential is called with the verified
        material AND a session token is returned in the response.

        Pin so a refactor of the storage interaction (e.g. forgets
        to base64-encode credential_id) or the token-issue path
        gets caught."""
        from beats.auth import webauthn as webauthn_module

        class _FakeVerification:
            credential_id = b"\x01\x02\x03\x04"
            credential_public_key = b"\x05\x06\x07\x08"
            sign_count = 0

        def fake_verify(*, credential, **_kwargs):  # noqa: ARG001
            return _FakeVerification()

        monkeypatch.setattr(webauthn_module, "verify_registration_response", fake_verify)

        storage = _FakeCredentialStorage()
        sm = _sm()
        # Seed the pending registration challenge so the pre-check passes
        sm.store_challenge(b"X" * 32, "registration")
        wam = _wam(storage=storage, session=sm)

        result = await wam.verify_registration(
            credential={"id": "fake"},
            user=_user(),
            device_name="iPhone",
        )

        # Response shape pinned: verified + token
        assert result["verified"] is True
        assert isinstance(result["token"], str) and result["token"]

        # Credential persisted via save_credential
        creds = await storage.get_credentials("user-1")
        assert len(creds) == 1
        # base64url(b"\x01\x02\x03\x04") == "AQIDBA"
        assert creds[0].credential_id == "AQIDBA"
        assert creds[0].device_name == "iPhone"
        # Token validates against the SessionManager
        payload = sm.validate_session_token(result["token"])
        assert payload is not None
        assert payload["sub"] == "user-1"

    async def test_crypto_failure_wraps_to_value_error(self, monkeypatch):
        """When verify_registration_response raises (signature
        mismatch, malformed origin, etc.), the broad except wraps
        it as ValueError("Registration verification failed: ...").
        Pin the wrapper so the API router's `except ValueError` →
        400 path stays reachable from the real py_webauthn library."""
        from beats.auth import webauthn as webauthn_module

        def fake_verify_raises(*, credential, **_kwargs):  # noqa: ARG001
            raise RuntimeError("origin mismatch")

        monkeypatch.setattr(webauthn_module, "verify_registration_response", fake_verify_raises)

        sm = _sm()
        sm.store_challenge(b"X" * 32, "registration")
        wam = _wam(session=sm)

        with pytest.raises(ValueError, match="Registration verification failed"):
            await wam.verify_registration(credential={"id": "fake"}, user=_user())


class TestWebAuthnAuthenticationOptions:
    """get_authentication_options uses an empty allowCredentials list
    so the browser triggers its native picker for discoverable
    credentials. Pin the empty-list invariant — exposing registered
    credential IDs to unauthenticated callers leaks user existence."""

    async def test_returns_options_with_empty_allow_credentials(self):
        wam = _wam()
        out = await wam.get_authentication_options()
        assert out["rpId"] == "beats.test"
        assert out["allowCredentials"] == []
        assert "challenge" in out
        assert out["userVerification"] == "preferred"

    async def test_stores_authentication_challenge(self):
        sm = _sm()
        wam = _wam(session=sm)
        await wam.get_authentication_options()
        assert sm.get_current_challenge("authentication") is not None
        # Pin: it's NOT also a registration challenge
        assert sm.get_current_challenge("registration") is None


class TestWebAuthnAuthenticationVerificationGuards:
    """Pin the pre-checks of verify_authentication without needing
    a real authenticator signature."""

    async def test_no_pending_challenge_raises(self):
        wam = _wam()
        with pytest.raises(ValueError, match="No pending authentication"):
            await wam.verify_authentication(credential={"id": "any"})

    async def test_unknown_credential_raises(self):
        """Credential ID not in storage → ValueError "Credential
        not found". Pin so an attacker can't probe for valid
        credential IDs by checking which error fires."""
        sm = _sm()
        sm.store_challenge(b"X" * 32, challenge_type="authentication")
        wam = _wam(session=sm)
        with pytest.raises(ValueError, match="Credential not found"):
            await wam.verify_authentication(credential={"id": "ghost"})

    async def test_credential_without_user_raises(self):
        """A credential that exists but isn't mapped to a user
        (orphaned data) → ValueError "No user found". Pin so a
        partial DB state doesn't auth the wrong user."""
        from beats.auth.storage import StoredCredential

        storage = _FakeCredentialStorage()
        # Insert orphaned credential directly — empty user_id
        storage._creds.append(
            (
                "",
                StoredCredential(
                    credential_id="orphan",
                    public_key="pk",
                    sign_count=0,
                    created_at="2026-04-01T00:00:00",
                ),
            )
        )
        sm = _sm()
        sm.store_challenge(b"X" * 32, challenge_type="authentication")
        wam = _wam(storage=storage, session=sm)
        with pytest.raises(ValueError, match="No user"):
            await wam.verify_authentication(credential={"id": "orphan"})

    async def test_happy_path_updates_sign_count_and_returns_token(self, monkeypatch):
        """Mock verify_authentication_response to return a fake
        success object → exercises the try-block (lines 229-252):
        update_sign_count is called with the new value AND a
        session token is issued for the credential's owner.

        Pin the sign_count-update side effect — without it, the
        WebAuthn replay-attack prevention is silently broken."""
        from beats.auth import webauthn as webauthn_module
        from beats.auth.storage import StoredCredential
        from beats.domain.models import User

        class _FakeAuth:
            new_sign_count = 42

        def fake_verify(*, credential, **_kwargs):  # noqa: ARG001
            return _FakeAuth()

        monkeypatch.setattr(webauthn_module, "verify_authentication_response", fake_verify)

        storage = _FakeCredentialStorage()
        # Seed a credential — credential_id="cred-1", base64url-decodable
        # public_key = "pk" (also valid base64url for 1 byte)
        storage._creds.append(
            (
                "user-99",
                StoredCredential(
                    credential_id="cred-1",
                    public_key="pk",
                    sign_count=10,
                    created_at="2026-04-01T00:00:00",
                ),
            )
        )

        sm = _sm()
        sm.store_challenge(b"X" * 32, challenge_type="authentication")

        user = User(id="user-99", email="ahmed@example.com")
        wam = _wam(storage=storage, session=sm, user_repo=_FakeUserRepo([user]))

        result = await wam.verify_authentication(credential={"id": "cred-1"})

        # Response shape pinned
        assert result["verified"] is True
        assert result["user_id"] == "user-99"
        assert isinstance(result["token"], str) and result["token"]

        # sign_count was advanced from 10 → 42
        cred = await storage.get_credential_by_id("cred-1")
        assert cred is not None
        assert cred.sign_count == 42

        # Token validates with the user's identity
        payload = sm.validate_session_token(result["token"])
        assert payload is not None
        assert payload["sub"] == "user-99"
        assert payload["email"] == "ahmed@example.com"

    async def test_crypto_failure_wraps_to_value_error(self, monkeypatch):
        """When verify_authentication_response raises (signature
        mismatch, sign-count rollback, etc.), the broad except
        wraps it as ValueError("Authentication verification
        failed: ..."). Pin so the router's `except ValueError`
        → 401 path stays reachable from the real py_webauthn
        library."""
        from beats.auth import webauthn as webauthn_module
        from beats.auth.storage import StoredCredential

        def fake_verify_raises(*, credential, **_kwargs):  # noqa: ARG001
            raise RuntimeError("sign-count rollback detected")

        monkeypatch.setattr(webauthn_module, "verify_authentication_response", fake_verify_raises)

        storage = _FakeCredentialStorage()
        storage._creds.append(
            (
                "user-99",
                StoredCredential(
                    credential_id="cred-X",
                    public_key="pk",
                    sign_count=0,
                    created_at="2026-04-01T00:00:00",
                ),
            )
        )
        sm = _sm()
        sm.store_challenge(b"X" * 32, challenge_type="authentication")
        wam = _wam(storage=storage, session=sm)

        with pytest.raises(ValueError, match="Authentication verification failed"):
            await wam.verify_authentication(credential={"id": "cred-X"})


class TestWebAuthnIsRegistered:
    """is_registered passes through to storage."""

    async def test_no_credentials_returns_false(self):
        wam = _wam()
        assert await wam.is_registered() is False

    async def test_with_credentials_returns_true(self):
        storage = _FakeCredentialStorage()
        await storage.save_credential(
            user_id="user-1",
            credential_id="cred-1",
            public_key="pk",
            sign_count=0,
        )
        wam = _wam(storage=storage)
        assert await wam.is_registered() is True


class TestWebAuthnGetCredentialsInfo:
    """get_credentials_info shapes stored credentials into the
    UI-facing dict {id, device_name, created_at}."""

    async def test_empty_returns_empty_list(self):
        wam = _wam()
        assert await wam.get_credentials_info("user-1") == []

    async def test_returns_credentials_with_expected_shape(self):
        storage = _FakeCredentialStorage()
        await storage.save_credential(
            user_id="user-1",
            credential_id="cred-1",
            public_key="pk-1",
            sign_count=0,
            device_name="iPhone",
        )
        wam = _wam(storage=storage)
        out = await wam.get_credentials_info("user-1")
        assert len(out) == 1
        entry = out[0]
        assert set(entry.keys()) == {"id", "device_name", "created_at"}
        assert entry["id"] == "cred-1"
        assert entry["device_name"] == "iPhone"


class TestWebAuthnDeleteCredential:
    """delete_credential refuses to delete a user's only credential.
    Pin so a user who hits "remove" on their last passkey doesn't
    lock themselves out — the API surface forces them to register
    a new one first."""

    async def test_cannot_delete_last_credential(self):
        storage = _FakeCredentialStorage()
        await storage.save_credential(
            user_id="user-1",
            credential_id="only-one",
            public_key="pk",
            sign_count=0,
        )
        wam = _wam(storage=storage)
        with pytest.raises(ValueError, match="only passkey"):
            await wam.delete_credential("only-one", "user-1")
        # Confirm the credential is still there
        assert await storage.count_credentials("user-1") == 1

    async def test_can_delete_when_multiple_exist(self):
        storage = _FakeCredentialStorage()
        await storage.save_credential(
            user_id="user-1",
            credential_id="cred-1",
            public_key="pk-1",
            sign_count=0,
        )
        await storage.save_credential(
            user_id="user-1",
            credential_id="cred-2",
            public_key="pk-2",
            sign_count=0,
        )
        wam = _wam(storage=storage)
        assert await wam.delete_credential("cred-1", "user-1") is True
        assert await storage.count_credentials("user-1") == 1

    async def test_delete_scoped_to_owning_user(self):
        """User A cannot delete User B's credential — pin the
        scoping so a compromised account can't strip another
        user's passkeys."""
        storage = _FakeCredentialStorage()
        # B has 2, A has 2 (so the last-one guard doesn't fire on A)
        for uid, cid in [
            ("user-B", "b1"),
            ("user-B", "b2"),
            ("user-A", "a1"),
            ("user-A", "a2"),
        ]:
            await storage.save_credential(
                user_id=uid, credential_id=cid, public_key="pk", sign_count=0
            )
        wam = _wam(storage=storage)
        # User A tries to delete User B's credential
        result = await wam.delete_credential("b1", "user-A")
        assert result is False
        # B's credentials are intact
        assert await storage.count_credentials("user-B") == 2


# =============================================================================
# Settings — JWT_SECRET length validator
# =============================================================================


class TestJwtSecretValidator:
    """JWT_SECRET must be at least 32 bytes (RFC 7518 §3.2 for
    HS256). The validator is the only thing standing between a
    deploy with a too-short shared secret and an attacker who
    can mint session tokens.

    Why this matters: pyjwt logs `InsecureKeyLengthWarning` on
    short keys but still signs with them. A self-host that
    forgot to set JWT_SECRET (and got the dev fallback) or
    typed a 16-character password would have been silently
    insecure. Pin so the validator fires before the app starts."""

    def test_short_secret_rejected_at_construction(self, monkeypatch):
        """An 11-byte secret (the previous .env.test value) is
        now rejected by Settings(). Pin so a regression in the
        validator surfaces immediately rather than after a
        Settings refactor."""
        from pydantic import ValidationError

        from beats.settings import Settings

        monkeypatch.setenv("JWT_SECRET", "test-secret")  # 11 bytes
        with pytest.raises(ValidationError) as exc:
            Settings()
        # Error message tells the operator how to generate a key
        msg = str(exc.value)
        assert "32 bytes" in msg
        assert "openssl rand" in msg

    def test_exact_32_byte_secret_accepted(self, monkeypatch):
        """The 32-byte boundary case is accepted (>=, not >).
        Pin so a `openssl rand -base64 24` (which yields a
        32-byte base64 string) is exactly at the threshold."""
        from beats.settings import Settings

        secret = "x" * 32
        monkeypatch.setenv("JWT_SECRET", secret)
        s = Settings()
        assert s.jwt_secret == secret

    def test_long_secret_accepted(self, monkeypatch):
        """A typical openssl-generated 48-byte secret passes."""
        from beats.settings import Settings

        secret = "W2wIN5fOg1WaO7KSekBWsTnqFp4MnRVXIDEkOhWp9vRqEQ7+y/lqBvBe7yVe7Ev1"
        monkeypatch.setenv("JWT_SECRET", secret)
        s = Settings()
        assert s.jwt_secret == secret

    def test_byte_length_not_character_length(self, monkeypatch):
        """The validator counts UTF-8 BYTES, not Python str
        characters. A 32-character string with multi-byte
        runes encodes to >32 bytes and passes; a 31-character
        ASCII string fails. Pin so a refactor to len(v) instead
        of len(v.encode('utf-8')) is caught."""
        from pydantic import ValidationError

        from beats.settings import Settings

        # 31 ASCII chars = 31 bytes → should fail
        short_ascii = "x" * 31
        monkeypatch.setenv("JWT_SECRET", short_ascii)
        with pytest.raises(ValidationError):
            Settings()

        # 11 chars × 3 bytes (em dashes are 3 bytes in UTF-8) = 33 bytes
        # → should pass even though the str is short
        multibyte = "—" * 11  # 11 em dashes = 33 bytes
        monkeypatch.setenv("JWT_SECRET", multibyte)
        s = Settings()
        assert s.jwt_secret == multibyte


# =============================================================================
# MongoCredentialStorage — real-Mongo CRUD coverage
# =============================================================================


class TestMongoCredentialStorage:
    """Direct CRUD tests for the Mongo-backed credential store. The
    earlier WebAuthn tests use _FakeCredentialStorage; this class
    pins the actual MongoCredentialStorage implementation against
    a real test Mongo (via testcontainers in conftest).

    Why bother when the in-memory fake has the same surface: the
    real implementation handles dict→StoredCredential conversion,
    Mongo's $set update semantics, and the count_documents query
    shape. A regression in any of those three would silently break
    auth across the deploy without any test failure (the
    in-memory fake has different code paths)."""

    @pytest.fixture(autouse=True)
    async def _setup(self):
        from beats.infrastructure.database import Database

        await Database.connect()
        db = Database.get_db()
        await db.credentials.delete_many({})
        yield
        await Database.disconnect()

    def _store(self):
        from beats.auth.storage import MongoCredentialStorage
        from beats.infrastructure.database import Database

        return MongoCredentialStorage(Database.get_db().credentials)

    async def test_save_and_get_round_trip(self):
        """save_credential persists; get_credentials returns it
        with the matching shape. Pin the dict→StoredCredential
        conversion."""
        store = self._store()
        await store.save_credential(
            user_id="user-A",
            credential_id="cred-1",
            public_key="pk-1",
            sign_count=0,
            device_name="iPhone",
        )
        creds = await store.get_credentials(user_id="user-A")
        assert len(creds) == 1
        assert creds[0].credential_id == "cred-1"
        assert creds[0].public_key == "pk-1"
        assert creds[0].sign_count == 0
        assert creds[0].device_name == "iPhone"
        assert creds[0].created_at  # non-empty ISO timestamp

    async def test_is_registered_scoped_to_user(self):
        """is_registered with a user_id only sees that user's
        credentials. Pin so a regression doesn't accidentally
        do a global count and report cross-user state."""
        store = self._store()
        # User A has a credential, User B does not
        await store.save_credential(
            user_id="user-A",
            credential_id="cred-A",
            public_key="pk",
            sign_count=0,
        )
        assert await store.is_registered("user-A") is True
        assert await store.is_registered("user-B") is False
        # Global is_registered (no user) sees A's credential
        assert await store.is_registered() is True

    async def test_get_credentials_filters_by_user(self):
        """A and B have credentials; get_credentials(user_id="A")
        returns only A's. Pin the user-scoping — the Settings →
        Passkeys panel binds to this."""
        store = self._store()
        await store.save_credential(
            user_id="user-A", credential_id="a1", public_key="pk", sign_count=0
        )
        await store.save_credential(
            user_id="user-B", credential_id="b1", public_key="pk", sign_count=0
        )
        a_creds = await store.get_credentials(user_id="user-A")
        b_creds = await store.get_credentials(user_id="user-B")
        assert {c.credential_id for c in a_creds} == {"a1"}
        assert {c.credential_id for c in b_creds} == {"b1"}

    async def test_get_credential_by_id_user_agnostic(self):
        """get_credential_by_id is the login path — by design it
        does NOT filter by user (the user is unknown until the
        credential matches). Pin so a regression doesn't add a
        spurious user_id filter that would break login."""
        store = self._store()
        await store.save_credential(
            user_id="user-A", credential_id="lookup-me", public_key="pk", sign_count=5
        )
        cred = await store.get_credential_by_id("lookup-me")
        assert cred is not None
        assert cred.credential_id == "lookup-me"
        assert cred.sign_count == 5

    async def test_get_credential_by_id_returns_none_for_missing(self):
        """Unknown credential_id → None (not raise). Pin so the
        login service's "Credential not found" ValueError fires
        instead of an unhandled exception."""
        store = self._store()
        result = await store.get_credential_by_id("ghost")
        assert result is None

    async def test_get_user_id_for_credential_round_trip(self):
        """get_user_id_for_credential returns the owning user_id
        — used during login to resolve credential → user. Pin
        the user_id is correct."""
        store = self._store()
        await store.save_credential(
            user_id="user-42", credential_id="cred-42", public_key="pk", sign_count=0
        )
        owner = await store.get_user_id_for_credential("cred-42")
        assert owner == "user-42"
        # Unknown id → None
        assert await store.get_user_id_for_credential("ghost") is None

    async def test_update_sign_count_persists(self):
        """update_sign_count overwrites the sign_count field —
        the WebAuthn replay-attack prevention mechanism. Pin
        that the new value is read back AND that the function
        returns True on success."""
        store = self._store()
        await store.save_credential(
            user_id="user-A", credential_id="cred-A", public_key="pk", sign_count=10
        )
        result = await store.update_sign_count("cred-A", 42)
        assert result is True
        # Confirm persisted
        cred = await store.get_credential_by_id("cred-A")
        assert cred is not None
        assert cred.sign_count == 42

    async def test_update_sign_count_returns_false_for_unknown_credential(self):
        """update_sign_count for a missing credential_id → False
        (not raise, not silently succeed). Pin so a stale
        credential reference doesn't quietly succeed and let
        an attacker-controlled sign_count slip through."""
        store = self._store()
        result = await store.update_sign_count("nonexistent", 99)
        assert result is False

    async def test_delete_credential_scoped_to_user(self):
        """delete_credential requires BOTH credential_id AND
        user_id to match. Pin so User A can't delete User B's
        credential (mirrors the WebAuthnManager test, but here
        verifies the actual Mongo query rather than the
        in-memory fake)."""
        store = self._store()
        await store.save_credential(
            user_id="user-A", credential_id="a1", public_key="pk", sign_count=0
        )
        await store.save_credential(
            user_id="user-B", credential_id="b1", public_key="pk", sign_count=0
        )
        # User A tries to delete User B's credential → False
        result = await store.delete_credential("b1", "user-A")
        assert result is False
        # B's credential is intact
        assert await store.get_credential_by_id("b1") is not None
        # A deleting their own credential succeeds
        result = await store.delete_credential("a1", "user-A")
        assert result is True
        assert await store.get_credential_by_id("a1") is None

    async def test_count_credentials_per_user(self):
        """count_credentials returns the count for one user only.
        Pin the user-scoping — the WebAuthnManager.delete-
        credential guard ("can't delete your only passkey") relies
        on this returning the per-user count, not the global one."""
        store = self._store()
        await store.save_credential(
            user_id="user-A", credential_id="a1", public_key="pk", sign_count=0
        )
        await store.save_credential(
            user_id="user-A", credential_id="a2", public_key="pk", sign_count=0
        )
        await store.save_credential(
            user_id="user-B", credential_id="b1", public_key="pk", sign_count=0
        )
        assert await store.count_credentials("user-A") == 2
        assert await store.count_credentials("user-B") == 1
        assert await store.count_credentials("user-C") == 0

    async def test_get_credential_ids_returns_id_list(self):
        """get_credential_ids is a thin wrapper over get_credentials
        that flattens to a list of strings. Used by
        get_registration_options to build excludeCredentials. Pin
        so the dict→[str] mapping doesn't drift."""
        store = self._store()
        await store.save_credential(
            user_id="user-A", credential_id="a1", public_key="pk", sign_count=0
        )
        await store.save_credential(
            user_id="user-A", credential_id="a2", public_key="pk", sign_count=0
        )
        ids = await store.get_credential_ids(user_id="user-A")
        assert set(ids) == {"a1", "a2"}
