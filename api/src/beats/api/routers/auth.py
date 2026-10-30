"""Authentication router for WebAuthn/Passkey endpoints."""

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from limits.storage import MongoDBStorage
from pydantic import BaseModel
from pymongo import MongoClient
from slowapi import Limiter
from slowapi.util import get_remote_address

from beats.auth.session import SessionManager
from beats.auth.storage import MongoCredentialStorage
from beats.auth.webauthn import WebAuthnManager
from beats.domain.models import User
from beats.infrastructure.database import Database
from beats.infrastructure.repositories import MongoUserRepository, UserRepository
from beats.settings import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])


class _MongoRateLimitStorage(MongoDBStorage):
    """`mongodb://` rate-limit storage whose destructor never dials Mongo.

    Upstream's `__del__` goes through the lazy `storage` property, so a
    process that imported the app but never served a limited route — the
    OpenAPI dump behind `pnpm gen:types`, any script — would connect to
    Mongo at interpreter exit and print an ignored traceback when it is
    unreachable. Registered under its own scheme (the metaclass keys on
    STORAGE_SCHEME), which `_init_mongo_client` strips back off before
    pymongo sees the URI.
    """

    # Upstream types this as an instance attribute, so ClassVar would break
    # the override check; the noqa stands in for it.
    STORAGE_SCHEME: list[str] | None = ["beats-mongodb", "beats-mongodb+srv"]  # noqa: RUF012

    def _init_mongo_client(self, uri: str | None, **options: int | str | bool) -> MongoClient:
        return super()._init_mongo_client((uri or "").removeprefix("beats-"), **options)

    def __del__(self) -> None:
        if self._storage is not None:
            self._storage.close()


# The counts live beside the data in Mongo, not in process memory: Cloud Run
# runs up to two instances, and a per-instance store both doubles every limit
# and forgets all of them whenever the service scales to zero (#391). The
# storage makes its own TTL indexes, so the collections clean themselves; when
# Mongo is unreachable the limiter falls back to this process's memory — the
# old behaviour — rather than failing the public routes.
limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=f"beats-{settings.db_dsn}",
    storage_options={
        "database_name": settings.db_name,
        "counter_collection_name": "rate_limit_counters",
        "window_collection_name": "rate_limit_windows",
    },
    in_memory_fallback_enabled=True,
)

# Shared singleton for session manager (needed by middleware)
_session_manager = SessionManager(settings.jwt_secret)


def get_session_manager() -> SessionManager:
    """Get the session manager instance (for use in middleware)."""
    return _session_manager


def get_credential_storage() -> MongoCredentialStorage:
    db = Database.get_db()
    return MongoCredentialStorage(db.credentials)


def get_user_repository() -> UserRepository:
    db = Database.get_db()
    return MongoUserRepository(db.users)


# Type aliases for dependency injection
CredentialStorageDep = Annotated[MongoCredentialStorage, Depends(get_credential_storage)]
UserRepoDep = Annotated[UserRepository, Depends(get_user_repository)]


def get_webauthn_manager(
    credential_storage: CredentialStorageDep,
    user_repo: UserRepoDep,
) -> WebAuthnManager:
    return WebAuthnManager(
        rp_id=settings.webauthn_rp_id,
        rp_name=settings.webauthn_rp_name,
        origin=settings.webauthn_origin,
        credential_storage=credential_storage,
        session_manager=_session_manager,
        user_repo=user_repo,
    )


WebAuthnDep = Annotated[WebAuthnManager, Depends(get_webauthn_manager)]


class RegisterStartRequest(BaseModel):
    email: str
    display_name: str | None = None


class RegisterStartResponse(BaseModel):
    options: dict[str, Any]
    user_id: str


class RegistrationVerifyRequest(BaseModel):
    credential: dict[str, Any]
    device_name: str | None = None


class RegistrationVerifyResponse(BaseModel):
    verified: bool
    token: str


class LoginOptionsResponse(BaseModel):
    options: dict[str, Any]


class LoginVerifyRequest(BaseModel):
    credential: dict[str, Any]


class LoginVerifyResponse(BaseModel):
    verified: bool
    token: str


@router.post("/register/start", response_model=RegisterStartResponse)
@limiter.limit("5/minute")
async def register_start(
    request: Request,
    body: RegisterStartRequest,
    user_repo: UserRepoDep,
    webauthn: WebAuthnDep,
) -> RegisterStartResponse:
    """Start registration: create user and return WebAuthn options."""
    # Check if email is already taken. A user who exists but has zero
    # credentials is a previously-abandoned /register/start — let them
    # retry instead of locking them out with 409 (they can't log in
    # either, since they have no credential, so the only way out
    # otherwise is customer support). Existing-with-credentials is a
    # real conflict.
    existing = await user_repo.get_by_email(body.email)
    if existing:
        creds = await webauthn.get_credentials_info(existing.id or "")
        if creds:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email already registered",
            )
        user = existing
    else:
        user = await user_repo.create(User(email=body.email, display_name=body.display_name))

    try:
        options = await webauthn.get_registration_options(user)
        return RegisterStartResponse(options=options, user_id=user.id or "")
    except Exception as e:
        logger.error("Failed to generate registration options: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        ) from e


@router.post("/register/verify", response_model=RegistrationVerifyResponse)
@limiter.limit("5/minute")
async def verify_registration(
    request: Request,
    body: RegistrationVerifyRequest,
    user_repo: UserRepoDep,
    webauthn: WebAuthnDep,
) -> RegistrationVerifyResponse:
    """Verify registration response and store the credential."""
    # Get the pending registration user_id
    user_id = _session_manager.get_pending_registration_user_id("registration")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No pending registration found",
        )

    user = await user_repo.get_by_id(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User not found for pending registration",
        )

    try:
        result = await webauthn.verify_registration(
            credential=body.credential,
            user=user,
            device_name=body.device_name,
        )
        return RegistrationVerifyResponse(
            verified=result["verified"],
            token=result["token"],
        )
    except ValueError as e:
        logger.warning("Registration verification failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e


@router.get("/login/options", response_model=LoginOptionsResponse)
@limiter.limit("10/minute")
async def get_login_options(request: Request, webauthn: WebAuthnDep) -> LoginOptionsResponse:
    """Get WebAuthn authentication options for login."""
    try:
        options = await webauthn.get_authentication_options()
        return LoginOptionsResponse(options=options)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e


@router.post("/login/verify", response_model=LoginVerifyResponse)
@limiter.limit("5/minute")
async def verify_login(
    request: Request,
    body: LoginVerifyRequest,
    webauthn: WebAuthnDep,
) -> LoginVerifyResponse:
    """Verify an authentication response and return a session token."""
    try:
        result = await webauthn.verify_authentication(credential=body.credential)
        return LoginVerifyResponse(
            verified=result["verified"],
            token=result["token"],
        )
    except ValueError as e:
        logger.warning("Login verification failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
        ) from e
