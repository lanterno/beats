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
from beats.infrastructure.database import Database
from beats.infrastructure.repositories import MongoUserRepository, UserRepository
from beats.settings import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])
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


# ============================================================================
# Request/Response Models
# ============================================================================


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


class UserResponse(BaseModel):
    email: str
    display_name: str | None


# ============================================================================
# Endpoints
# ============================================================================


@router.post("/register/start", response_model=RegisterStartResponse)
@limiter.limit("5/minute")
async def register_start(
    request: Request,
    body: RegisterStartRequest,
    user_repo: UserRepoDep,
    webauthn: WebAuthnDep,
) -> RegisterStartResponse:
    """Start registration: create user and return WebAuthn options."""
    # Check if email is already taken
    existing = await user_repo.get_by_email(body.email)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    # Create the user
    from beats.domain.models import User

    user = await user_repo.create(User(email=body.email, display_name=body.display_name))

    try:
        options = await webauthn.get_registration_options(user)
        return RegisterStartResponse(options=options, user_id=user.id or "")
    except Exception as e:
        logger.error(f"Failed to generate registration options: {e}")
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
        logger.warning(f"Registration verification failed: {e}")
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
        logger.warning(f"Login verification failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
        ) from e


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request) -> None:
    """Revoke the current session token."""
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        _session_manager.revoke_token(token)


@router.get("/me", response_model=UserResponse)
async def get_current_user(
    request: Request,
    user_repo: UserRepoDep,
) -> UserResponse:
    """Get the currently authenticated user's info."""
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    user = await user_repo.get_by_id(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    return UserResponse(email=user.email, display_name=user.display_name)


@router.get("/credentials")
async def list_credentials(
    request: Request,
    webauthn: WebAuthnDep,
) -> list[dict[str, Any]]:
    """List registered credentials for the current user."""
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    return await webauthn.get_credentials_info(user_id)


@router.delete("/credentials/{credential_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_credential(
    request: Request,
    credential_id: str,
    webauthn: WebAuthnDep,
) -> None:
    """Delete a registered credential for the current user."""
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    try:
        deleted = await webauthn.delete_credential(credential_id, user_id)
        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Credential not found",
            )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e
