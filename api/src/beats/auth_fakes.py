"""Fakes and factories the auth suites share — no tests of their own.

`test_auth.py` grew past the size ceiling (CLAUDE.md § Conventions) and split
into its session and WebAuthn halves; the fixed secret, the session
manager factory and the in-memory credential and user stores are used by
both. Not `test_`-prefixed, so pytest does not collect it.
"""

from __future__ import annotations

from beats.auth.storage import StoredCredential

JWT_SECRET = "test-secret-do-not-use-in-prod-this-is-a-fixed-string-32+bytes"


def _sm(session_ttl: int = 3600):
    """Build a SessionManager with a fixed JWT secret."""
    from beats.auth.session import SessionManager

    return SessionManager(JWT_SECRET, session_ttl=session_ttl)


class _FakeCredentialStorage:
    """In-memory credential storage. Mirrors MongoCredentialStorage's
    surface — the methods WebAuthnManager calls."""

    def __init__(self):
        self._creds: list[tuple[str, StoredCredential]] = []

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
