"""Session management with JWT tokens and in-memory challenge storage."""

import base64
import logging
import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# Challenge TTL in seconds (5 minutes)
CHALLENGE_TTL = 300

# Session token TTL in seconds (1 hour)
SESSION_TTL = 3600


class Challenge(BaseModel):
    """A WebAuthn challenge with expiration."""

    value: str
    created_at: float
    challenge_type: str  # "registration" or "authentication"


class SessionManager:
    """Manages JWT sessions and WebAuthn challenges."""

    def __init__(self, jwt_secret: str, session_ttl: int = SESSION_TTL):
        self._jwt_secret = jwt_secret
        self._session_ttl = session_ttl
        # In-memory challenge storage: challenge_value -> Challenge
        self._challenges: dict[str, Challenge] = {}
        # Pending registration: challenge_b64 -> user_id
        self._pending_registrations: dict[str, str] = {}
        # Revoked tokens: token -> expiry timestamp (auto-cleaned)
        self._revoked_tokens: dict[str, float] = {}

    def get_current_challenge(self, challenge_type: str) -> str | None:
        """Get the most recent unexpired challenge of the given type."""
        self._cleanup_expired_challenges()

        # Find the most recent challenge of the given type
        valid_challenges = [
            c for c in self._challenges.values() if c.challenge_type == challenge_type
        ]

        if not valid_challenges:
            return None

        # Return the most recent one
        most_recent = max(valid_challenges, key=lambda c: c.created_at)
        return most_recent.value

    def validate_challenge(self, challenge: str, challenge_type: str) -> bool:
        """Validate and consume a challenge."""
        self._cleanup_expired_challenges()

        stored = self._challenges.get(challenge)
        if stored is None:
            logger.warning(f"Challenge not found: {challenge[:20]}...")
            return False

        if stored.challenge_type != challenge_type:
            logger.warning(
                f"Challenge type mismatch: expected {challenge_type}, got {stored.challenge_type}"
            )
            return False

        # Challenge is valid, consume it (one-time use)
        del self._challenges[challenge]
        logger.debug(f"Validated and consumed challenge: {challenge[:20]}...")
        return True

    def store_challenge(self, challenge: bytes, challenge_type: str = "authentication") -> str:
        """Store a challenge that was generated externally (e.g., by py_webauthn)."""
        self._cleanup_expired_challenges()

        challenge_b64 = base64.urlsafe_b64encode(challenge).rstrip(b"=").decode("ascii")

        self._challenges[challenge_b64] = Challenge(
            value=challenge_b64,
            created_at=time.time(),
            challenge_type=challenge_type,
        )

        logger.debug(f"Stored {challenge_type} challenge: {challenge_b64[:20]}...")
        return challenge_b64

    def get_stored_challenge(self, challenge_type: str) -> bytes | None:
        """Get the raw bytes of the most recent challenge of the given type."""
        challenge_b64 = self.get_current_challenge(challenge_type)
        if challenge_b64 is None:
            return None

        # Add back padding and decode
        padding = 4 - len(challenge_b64) % 4
        if padding != 4:
            challenge_b64 += "=" * padding

        return base64.urlsafe_b64decode(challenge_b64)

    def _cleanup_expired_challenges(self) -> None:
        """Remove expired challenges and their pending registrations from memory."""
        now = time.time()
        expired = [
            key
            for key, challenge in self._challenges.items()
            if now - challenge.created_at > CHALLENGE_TTL
        ]
        for key in expired:
            del self._challenges[key]
            self._pending_registrations.pop(key, None)

        if expired:
            logger.debug(f"Cleaned up {len(expired)} expired challenges")

    def store_pending_registration(self, challenge: bytes, user_id: str) -> None:
        """Store user_id for a pending registration challenge."""
        challenge_b64 = base64.urlsafe_b64encode(challenge).rstrip(b"=").decode("ascii")
        self._pending_registrations[challenge_b64] = user_id

    def get_pending_registration_user_id(self, challenge_type: str) -> str | None:
        """Get the user_id for the current pending registration."""
        challenge_b64 = self.get_current_challenge(challenge_type)
        if challenge_b64 is None:
            return None
        return self._pending_registrations.get(challenge_b64)

    def create_session_token(self, user_id: str, email: str = "") -> str:
        """Create a JWT session token."""
        now = datetime.now(UTC)
        payload: dict[str, Any] = {
            "sub": user_id,
            "iat": now,
            "exp": now + timedelta(seconds=self._session_ttl),
            "type": "session",
            "jti": str(uuid.uuid4()),
        }
        if email:
            payload["email"] = email

        token = jwt.encode(payload, self._jwt_secret, algorithm="HS256")
        logger.info(f"Created session token for user: {user_id}")
        return token

    def validate_session_token(self, token: str) -> dict | None:
        """Validate a JWT session token and return the payload."""
        self._cleanup_revoked_tokens()

        if token in self._revoked_tokens:
            logger.debug("Token has been revoked")
            return None

        try:
            payload = jwt.decode(token, self._jwt_secret, algorithms=["HS256"])

            if payload.get("type") != "session":
                logger.warning("Token type is not 'session'")
                return None

            return payload
        except jwt.ExpiredSignatureError:
            logger.debug("Session token expired")
            return None
        except jwt.InvalidTokenError as e:
            logger.warning(f"Invalid session token: {e}")
            return None

    def refresh_token(self, token: str) -> str | None:
        """Issue a new token from a valid existing one, revoking the old one."""
        payload = self.validate_session_token(token)
        if payload is None:
            return None

        user_id = payload["sub"]
        email = payload.get("email", "")

        # Revoke the old token and issue a new one
        self.revoke_token(token)
        return self.create_session_token(user_id, email)

    def revoke_token(self, token: str) -> None:
        """Add a token to the revocation list. It stays until its natural expiry."""
        try:
            # Decode without verification to read the expiry time
            payload = jwt.decode(
                token, self._jwt_secret, algorithms=["HS256"], options={"verify_exp": False}
            )
            exp = payload.get("exp", time.time())
            self._revoked_tokens[token] = float(exp)
            logger.info("Revoked session token for user: %s", payload.get("sub"))
        except jwt.InvalidTokenError:
            pass  # Invalid token, nothing to revoke

    def _cleanup_revoked_tokens(self) -> None:
        """Remove expired entries from the revocation list."""
        now = time.time()
        expired = [t for t, exp in self._revoked_tokens.items() if now > exp]
        for t in expired:
            del self._revoked_tokens[t]

    def get_challenge_count(self) -> int:
        """Get the number of active challenges (for debugging)."""
        self._cleanup_expired_challenges()
        return len(self._challenges)
