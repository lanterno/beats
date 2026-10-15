"""Account router for authenticated user endpoints (profile, credentials, session)."""

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel

from beats.api.dependencies import CurrentUserId
from beats.api.routers.auth import UserRepoDep, WebAuthnDep, _session_manager, limiter
from beats.api.routers.sso import (
    RegistryDep,
    SSOAccountsDep,
    SSOFlowsDep,
    SSOStartResponse,
    provider_or_404,
    sso_error,
    start_flow,
)
from beats.auth.oidc import OIDCRegistry
from beats.auth.sso_accounts import SSOAccountError, SSOLastCredential, SSONotLinked
from beats.domain.models import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/account", tags=["account"])


class LinkedIdentityInfo(BaseModel):
    """An identity at a provider that signs into this account."""

    provider: str
    # The provider's display name, or its id once it is no longer configured.
    provider_name: str
    name: str | None
    email: str | None
    linked_at: str


class UserResponse(BaseModel):
    email: str
    display_name: str | None
    identities: list[LinkedIdentityInfo]
    # True when a provider created this account. Such an account has no
    # passkey until its owner registers one, which is what the unlink guard
    # checks.
    sso_provisioned: bool


class RefreshResponse(BaseModel):
    token: str


def _user_response(user: User, registry: OIDCRegistry) -> UserResponse:
    """Render a user for the API, including the identities linked to it."""
    return UserResponse(
        email=user.email,
        display_name=user.display_name,
        identities=[
            LinkedIdentityInfo(
                provider=i.provider,
                provider_name=registry.name_of(i.provider),
                name=i.name,
                email=i.email,
                linked_at=i.linked_at.isoformat(),
            )
            for i in user.identities
        ],
        sso_provisioned=user.sso_provisioned,
    )


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


@router.get("/me", response_model=UserResponse)
async def get_current_user(
    user_id: CurrentUserId,
    user_repo: UserRepoDep,
    registry: RegistryDep,
) -> UserResponse:
    """Get the currently authenticated user's info."""
    user = await user_repo.get_by_id(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    return _user_response(user, registry)


# Linking identities
#
# Both directions require a signed-in beats session. Linking from a cold
# sign-in — "we see identity X, is this your account?" — is the shape that
# turns a settable attribute into account takeover, and is not offered. See
# `beats.auth.sso_accounts` for the full reasoning.


@router.post("/sso/{provider_id}/link", response_model=SSOStartResponse)
@limiter.limit("10/minute")
async def start_link(
    request: Request,
    provider_id: str,
    user_id: CurrentUserId,
    registry: RegistryDep,
    flows: SSOFlowsDep,
) -> SSOStartResponse:
    """Begin linking an identity at a provider to this account.

    Finished by `POST /api/auth/sso/complete`, sent with this same session.
    """
    provider = provider_or_404(registry, provider_id)
    return await start_flow(provider, flows, "link", user_id=user_id)


@router.delete("/sso/{provider_id}", response_model=UserResponse)
@limiter.limit("10/minute")
async def unlink_identity(
    request: Request,
    provider_id: str,
    user_id: CurrentUserId,
    accounts: SSOAccountsDep,
    webauthn: WebAuthnDep,
    registry: RegistryDep,
) -> UserResponse:
    """Detach the identity linked through a provider.

    Works for a provider that is no longer configured, too. Refused when it
    would leave no passkey and no other identity — no way back in.
    """
    passkeys = await webauthn.get_credentials_info(user_id)
    try:
        user = await accounts.unlink(user_id, provider_id, passkey_count=len(passkeys))
    except SSONotLinked as e:
        raise sso_error(status.HTTP_404_NOT_FOUND, "SSO_NOT_LINKED", str(e)) from e
    except SSOLastCredential as e:
        raise sso_error(status.HTTP_409_CONFLICT, "SSO_LAST_CREDENTIAL", str(e)) from e
    except SSOAccountError as e:
        raise sso_error(status.HTTP_400_BAD_REQUEST, "SSO_UNLINK_FAILED", str(e)) from e
    return _user_response(user, registry)


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
