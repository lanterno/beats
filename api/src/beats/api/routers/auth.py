"""Authentication router for WebAuthn/Passkey endpoints."""

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
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

# Every rate limit in the API is this one limiter, keyed on the visitor's
# address (`ProxyHeadersMiddleware` in src/server.py is what makes that the
# visitor's and not the proxy's).
#
# **The counts are per instance, and that is a decision, not an oversight**
# (#376). slowapi keeps them in the process's memory, so on Cloud Run with
# `max_instances = 2` every limit is worth up to twice what it says, and with
# `min_instances = 0` the counts go when the service scales to zero.
#
# Shared storage is available — `limits` has a MongoDB backend and slowapi
# takes a `storage_uri` — and it is not used, because slowapi builds the
# *synchronous* storage (`storage_from_string`), so every rate-limited
# request would make a blocking Mongo round-trip on the event loop of a
# 1-CPU instance that already runs out of capacity under the ledger reads
# (#376 item 3). Paying that on the sign-in path to tighten 10/min to 5/min
# is the wrong trade.
#
# It is the right trade when the limits are protecting something guessable.
# These are not: the login and registration limits stand in front of a
# WebAuthn ceremony, the pairing exchange in front of a code that expires,
# and `/api/reports` in front of a 32-byte token. They are there so a leaked
# link or a stuck client cannot hammer the service, and 2× of that is still
# no hammering. Revisit if a limit ever guards a password, a one-time code
# short enough to enumerate, or anything billed per request — or if slowapi
# grows an async storage path, which removes the cost of the fix.
limiter = Limiter(key_func=get_remote_address)

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
