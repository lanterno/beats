"""Tests for the auth layer — SessionManager, WebAuthnManager, storage."""

from __future__ import annotations

import time

import jwt

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
