"""Session management with JWT tokens and in-memory challenge storage."""

import logging
import secrets
import time
from datetime import UTC, datetime, timedelta

import jwt
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# Challenge TTL in seconds (5 minutes)
CHALLENGE_TTL = 300

# Session token TTL in seconds (24 hours)
SESSION_TTL = 86400


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

    def generate_challenge(self, challenge_type: str = "authentication") -> bytes:
        """Generate a new WebAuthn challenge and store it."""
        # Clean up expired challenges first
        self._cleanup_expired_challenges()

        # Generate 32 random bytes for the challenge
        challenge_bytes = secrets.token_bytes(32)
        challenge_b64 = secrets.token_urlsafe(32)

        self._challenges[challenge_b64] = Challenge(
            value=challenge_b64,
            created_at=time.time(),
            challenge_type=challenge_type,
        )

        logger.debug(f"Generated {challenge_type} challenge: {challenge_b64[:20]}...")
        return challenge_bytes

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

        # Convert bytes to base64url string for storage key
        import base64

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
        import base64

        challenge_b64 = self.get_current_challenge(challenge_type)
        if challenge_b64 is None:
            return None

        # Add back padding and decode
        padding = 4 - len(challenge_b64) % 4
        if padding != 4:
            challenge_b64 += "=" * padding

        return base64.urlsafe_b64decode(challenge_b64)

    def _cleanup_expired_challenges(self) -> None:
        """Remove expired challenges from memory."""
        now = time.time()
        expired = [
            key
            for key, challenge in self._challenges.items()
            if now - challenge.created_at > CHALLENGE_TTL
        ]
        for key in expired:
            del self._challenges[key]

        if expired:
            logger.debug(f"Cleaned up {len(expired)} expired challenges")

    def create_session_token(self, user_id: str = "owner") -> str:
        """Create a JWT session token."""
        now = datetime.now(UTC)
        payload = {
            "sub": user_id,
            "iat": now,
            "exp": now + timedelta(seconds=self._session_ttl),
            "type": "session",
        }

        token = jwt.encode(payload, self._jwt_secret, algorithm="HS256")
        logger.info(f"Created session token for user: {user_id}")
        return token

    def validate_session_token(self, token: str) -> dict | None:
        """Validate a JWT session token and return the payload."""
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

    def get_challenge_count(self) -> int:
        """Get the number of active challenges (for debugging)."""
        self._cleanup_expired_challenges()
        return len(self._challenges)
