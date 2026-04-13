"""Account router for authenticated user endpoints (profile, credentials, session)."""

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel

from beats.api.dependencies import CurrentUserId
from beats.api.routers.auth import UserRepoDep, WebAuthnDep, _session_manager, limiter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/account", tags=["account"])


# ============================================================================
# Response Models
# ============================================================================


class UserResponse(BaseModel):
    email: str
    display_name: str | None


class RefreshResponse(BaseModel):
    token: str


# ============================================================================
# Session Endpoints
# ============================================================================


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("10/minute")
async def logout(request: Request) -> None:
    """Revoke the current session token."""
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        _session_manager.revoke_token(token)


@router.post("/refresh", response_model=RefreshResponse)
@limiter.limit("10/minute")
async def refresh_token(request: Request) -> RefreshResponse:
    """Exchange a valid session token for a new one."""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bearer token required",
        )
    token = auth_header[7:]
    new_token = _session_manager.refresh_token(token)
    if new_token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )
    return RefreshResponse(token=new_token)


# ============================================================================
# Profile Endpoints
# ============================================================================


@router.get("/me", response_model=UserResponse)
async def get_current_user(
    user_id: CurrentUserId,
    user_repo: UserRepoDep,
) -> UserResponse:
    """Get the currently authenticated user's info."""
    user = await user_repo.get_by_id(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    return UserResponse(email=user.email, display_name=user.display_name)


# ============================================================================
# Credential Endpoints
# ============================================================================


@router.get("/credentials")
async def list_credentials(
    user_id: CurrentUserId,
    webauthn: WebAuthnDep,
) -> list[dict[str, Any]]:
    """List registered credentials for the current user."""
    return await webauthn.get_credentials_info(user_id)


@router.delete("/credentials/{credential_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_credential(
    user_id: CurrentUserId,
    credential_id: str,
    webauthn: WebAuthnDep,
) -> None:
    """Delete a registered credential for the current user."""
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
