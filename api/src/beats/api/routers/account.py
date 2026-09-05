"""Account router for authenticated user endpoints (profile, credentials, session)."""

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel

from beats.api.dependencies import CurrentUserId
from beats.api.routers.auth import UserRepoDep, WebAuthnDep, _session_manager, limiter
from beats.api.routers.sso import SSOAccountsDep, get_sso_verifier, verify_home_cookie
from beats.auth.sso import SSOError, SSORejected
from beats.auth.sso_accounts import (
    SSOAccountError,
    SSOAlreadyLinked,
    SSOLastCredential,
    SSOLinkConflict,
    SSONotLinked,
)
from beats.domain.models import User
from beats.settings import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/account", tags=["account"])


# ============================================================================
# Response Models
# ============================================================================


class SSOLinkInfo(BaseModel):
    """The home.space identity attached to this account, if any."""

    linked: bool
    provider_name: str
    did: str | None = None
    holder_name: str | None = None
    roles: list[str] = []
    linked_at: str | None = None
    # True when SSO created this account. Such an account has no passkey
    # until the user registers one, which is what the unlink guard checks.
    provisioned: bool = False


class UserResponse(BaseModel):
    email: str
    display_name: str | None
    sso: SSOLinkInfo


class RefreshResponse(BaseModel):
    token: str


def _user_response(user: User) -> UserResponse:
    """Render a user for the API, including its home.space link state."""
    return UserResponse(
        email=user.email,
        display_name=user.display_name,
        sso=SSOLinkInfo(
            linked=user.has_sso_link,
            provider_name=settings.sso_provider_name,
            did=user.sso_subject,
            holder_name=user.sso_holder_name,
            roles=list(user.sso_roles),
            linked_at=user.sso_linked_at.isoformat() if user.sso_linked_at else None,
            provisioned=user.sso_provisioned,
        ),
    )


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
    """Exchange a valid session token for a new one.

    A session that began as a home.space SSO login carries an `sso` claim,
    and is re-checked against the issuer here before being extended.
    Without that, revoking a device in `auth`'s `/devices` would stop new
    logins while leaving an already-issued beats session renewing itself
    forever — the revocation would be cosmetic.

    Sessions from beats' own passkey login carry no `sso` claim and are
    untouched by any of this.
    """
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bearer token required",
        )
    token = auth_header[7:]

    payload = _session_manager.validate_session_token(token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    sso_subject = payload.get("sso")
    if sso_subject and settings.sso_enabled:
        await _revalidate_sso_session(request, sso_subject)

    new_token = _session_manager.refresh_token(token)
    if new_token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )
    return RefreshResponse(token=new_token)


async def _revalidate_sso_session(request: Request, sso_subject: str) -> None:
    """Re-check an SSO-derived session against the issuer before extending it.

    Three outcomes, and they are deliberately not the same:

    - **Cookie gone** — the home.space session ended (logged out at the
      issuer, or ran past its 24h life). End the beats session too. This is
      what makes `POST /api/session/logout` on `auth` propagate here.
    - **Issuer says no** — expired, tampered with, or the device was
      revoked. End the session.
    - **Issuer unreachable** — no verdict. Extend anyway and log it. The
      alternative is beats hard-failing whenever `home-auth.service` is
      down, which is precisely the coupling this design set out to avoid;
      the session being extended was already verified once.
    """
    cookie = request.cookies.get(settings.sso_cookie_name, "")
    if not cookie:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "SSO_SESSION_ENDED",
                "message": "Your home.space session has ended. Sign in again.",
            },
        )

    try:
        identity = await get_sso_verifier().verify(cookie)
    except SSOError as e:
        # Covers both a rejection and an unreachable issuer. Only a
        # rejection should end the session; `verify` raises SSORejected for
        # that and SSOUnavailable for the outage.
        if isinstance(e, SSORejected):
            logger.info("Ending beats session: home.space identity %s rejected", sso_subject)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "code": "SSO_SESSION_REVOKED",
                    "message": "Your home.space identity is no longer valid. Sign in again.",
                },
            ) from e
        logger.warning(
            "Extending beats session for %s without re-check: issuer unavailable (%s)",
            sso_subject,
            e,
        )
        return

    if identity.did != sso_subject:
        # The browser now carries a DIFFERENT home identity than the one
        # this session was minted for. Refusing rather than silently
        # switching: the beats token names a user, and quietly re-pointing
        # it at whoever holds the cookie now would be an account swap.
        logger.warning(
            "Refusing refresh: session was issued to %s, cookie now carries %s",
            sso_subject,
            identity.did,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "SSO_SUBJECT_CHANGED",
                "message": "A different home.space identity is signed in. Sign in again.",
            },
        )


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
    return _user_response(user)


# ============================================================================
# home.space identity linking
#
# Both directions require an authenticated beats session. Linking from an
# unauthenticated SSO arrival — "we see identity X, is this your account?" —
# is the shape that turns a settable attribute into account takeover, and is
# not offered. See `beats.auth.sso_accounts` for the full reasoning.
# ============================================================================


@router.post("/sso/link", response_model=UserResponse)
@limiter.limit("10/minute")
async def link_sso_identity(
    request: Request,
    user_id: CurrentUserId,
    accounts: SSOAccountsDep,
) -> UserResponse:
    """Attach the caller's home.space identity to their beats account.

    Proves both sides in one request: the Bearer token proves the beats
    account, the `Home-Session` cookie proves the home.space identity.
    """
    if not settings.sso_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "SSO_DISABLED",
                "message": "home.space SSO is not enabled on this instance.",
            },
        )

    identity = await verify_home_cookie(request, get_sso_verifier())

    try:
        user = await accounts.link(user_id, identity)
    except SSOAlreadyLinked as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "SSO_ALREADY_LINKED", "message": str(e)},
        ) from e
    except SSOLinkConflict as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "SSO_LINK_CONFLICT", "message": str(e)},
        ) from e
    except SSOAccountError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "SSO_LINK_FAILED", "message": str(e)},
        ) from e

    return _user_response(user)


@router.delete("/sso/link", response_model=UserResponse)
@limiter.limit("10/minute")
async def unlink_sso_identity(
    request: Request,
    user_id: CurrentUserId,
    accounts: SSOAccountsDep,
    webauthn: WebAuthnDep,
) -> UserResponse:
    """Detach the linked home.space identity.

    Refused if the account holds no passkey, since the link would be the
    only remaining way in — the same rule `delete_credential` applies to the
    last passkey, seen from the other side.
    """
    passkeys = await webauthn.get_credentials_info(user_id)

    try:
        user = await accounts.unlink(user_id, passkey_count=len(passkeys))
    except SSONotLinked as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "SSO_NOT_LINKED", "message": str(e)},
        ) from e
    except SSOLastCredential as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "SSO_LAST_CREDENTIAL", "message": str(e)},
        ) from e
    except SSOAccountError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "SSO_UNLINK_FAILED", "message": str(e)},
        ) from e

    return _user_response(user)


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
