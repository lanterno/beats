"""Authentication router for WebAuthn/Passkey endpoints."""

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from beats.auth.session import SessionManager
from beats.auth.storage import CredentialStorage
from beats.auth.webauthn import WebAuthnManager
from beats.settings import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])

# Initialize auth components (singleton instances)
_credential_storage = CredentialStorage(settings.credentials_path)
_session_manager = SessionManager(settings.jwt_secret)
_webauthn_manager = WebAuthnManager(
    rp_id=settings.webauthn_rp_id,
    rp_name=settings.webauthn_rp_name,
    origin=settings.webauthn_origin,
    credential_storage=_credential_storage,
    session_manager=_session_manager,
)


def get_session_manager() -> SessionManager:
    """Get the session manager instance (for use in middleware)."""
    return _session_manager


# ============================================================================
# Request/Response Models
# ============================================================================


class AuthStatusResponse(BaseModel):
    """Response for auth status check."""

    is_registered: bool
    credentials_count: int


class RegistrationOptionsResponse(BaseModel):
    """Response containing WebAuthn registration options."""

    options: dict[str, Any]


class RegistrationVerifyRequest(BaseModel):
    """Request to verify a registration response."""

    credential: dict[str, Any]
    device_name: str | None = None


class RegistrationVerifyResponse(BaseModel):
    """Response after successful registration."""

    verified: bool
    token: str


class LoginOptionsResponse(BaseModel):
    """Response containing WebAuthn authentication options."""

    options: dict[str, Any]


class LoginVerifyRequest(BaseModel):
    """Request to verify an authentication response."""

    credential: dict[str, Any]


class LoginVerifyResponse(BaseModel):
    """Response after successful authentication."""

    verified: bool
    token: str


# ============================================================================
# Endpoints
# ============================================================================


@router.get("/status", response_model=AuthStatusResponse)
async def get_auth_status() -> AuthStatusResponse:
    """Check if any passkeys are registered.

    This endpoint is used by the frontend to determine whether to show
    the registration or login flow.
    """
    is_registered = _webauthn_manager.is_registered()
    credentials = _webauthn_manager.get_credentials_info()

    return AuthStatusResponse(
        is_registered=is_registered,
        credentials_count=len(credentials),
    )


@router.get("/register/options", response_model=RegistrationOptionsResponse)
async def get_registration_options() -> RegistrationOptionsResponse:
    """Get WebAuthn registration options.

    Call this to start the passkey registration ceremony.
    The returned options should be passed to navigator.credentials.create().
    """
    try:
        options = _webauthn_manager.get_registration_options()
        return RegistrationOptionsResponse(options=options)
    except Exception as e:
        logger.error(f"Failed to generate registration options: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        ) from e


@router.post("/register/verify", response_model=RegistrationVerifyResponse)
async def verify_registration(request: RegistrationVerifyRequest) -> RegistrationVerifyResponse:
    """Verify a registration response and store the credential.

    Call this after navigator.credentials.create() succeeds.
    Returns a session token on success.
    """
    try:
        result = _webauthn_manager.verify_registration(
            credential=request.credential,
            device_name=request.device_name,
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
    except Exception as e:
        logger.error(f"Registration verification error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Registration failed",
        ) from e


@router.get("/login/options", response_model=LoginOptionsResponse)
async def get_login_options() -> LoginOptionsResponse:
    """Get WebAuthn authentication options.

    Call this to start the passkey login ceremony.
    The returned options should be passed to navigator.credentials.get().
    """
    try:
        options = _webauthn_manager.get_authentication_options()
        return LoginOptionsResponse(options=options)
    except ValueError as e:
        # No credentials registered
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e
    except Exception as e:
        logger.error(f"Failed to generate login options: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        ) from e


@router.post("/login/verify", response_model=LoginVerifyResponse)
async def verify_login(request: LoginVerifyRequest) -> LoginVerifyResponse:
    """Verify an authentication response.

    Call this after navigator.credentials.get() succeeds.
    Returns a session token on success.
    """
    try:
        result = _webauthn_manager.verify_authentication(credential=request.credential)
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
    except Exception as e:
        logger.error(f"Login verification error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication failed",
        ) from e


@router.get("/credentials")
async def list_credentials() -> list[dict[str, Any]]:
    """List registered credentials (for management UI).

    Note: This endpoint should be protected in production.
    """
    return _webauthn_manager.get_credentials_info()
