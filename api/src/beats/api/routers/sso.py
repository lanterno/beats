"""home.space SSO — the second front door.

Public, like the rest of `/api/auth`. Everything here turns a `Home-Session`
cookie minted by `auth.home.space` into an ordinary beats session token; from
that point on nothing else in the API knows or cares which door was used.

The linking endpoints deliberately live in `account.py` instead, because they
require an authenticated beats session — see the module docstring in
`beats.auth.sso_accounts` for why that direction is the only safe one.
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from beats.api.routers.auth import UserRepoDep, _session_manager, limiter
from beats.auth.sso import HomeIdentity, HomeSSOVerifier, SSORejected, SSOUnavailable
from beats.auth.sso_accounts import SSOAccountService, SSOProvisionForbidden
from beats.settings import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth/sso", tags=["sso"])


# Shared process-wide so the JWKS cache is shared. Constructed unconditionally
# — it makes no network call until something asks it to verify, so an instance
# with SSO disabled costs nothing.
_verifier = HomeSSOVerifier(
    auth_base_url=settings.sso_auth_base_url,
    issuer=settings.sso_issuer,
    jwks_ttl_seconds=settings.sso_jwks_ttl_seconds,
    timeout_seconds=settings.sso_issuer_timeout_seconds,
)


def get_sso_verifier() -> HomeSSOVerifier:
    """The shared verifier (also used by the account router)."""
    return _verifier


def get_sso_accounts(user_repo: UserRepoDep) -> SSOAccountService:
    return SSOAccountService(user_repo, settings.sso_provision_role_set)


SSOAccountsDep = Annotated[SSOAccountService, Depends(get_sso_accounts)]


# ============================================================================
# Response models
# ============================================================================


class SSOConfigResponse(BaseModel):
    enabled: bool
    provider_name: str
    # Where to send the browser to obtain a home.space session. Empty when
    # SSO is on but the URL could not be derived from this request's Host
    # (a bare `localhost`, typically) and none was configured.
    login_url: str
    # Whether this request already carried a Home-Session cookie. Lets the
    # UI attempt a silent sign-in instead of bouncing through the issuer.
    session_present: bool


class SSOSessionResponse(BaseModel):
    verified: bool
    token: str
    # True when this login created the beats account rather than signing
    # into an existing one — the UI uses it to show a welcome rather than
    # a plain redirect.
    created: bool
    did: str
    holder_name: str
    roles: list[str]
    display_name: str | None
    # "issuer" when auth.home.space confirmed the session (so revocation was
    # checked), "offline" when it was unreachable and only the signature
    # could be verified. Surfaced so the UI can say so rather than pretend
    # the two are the same.
    verified_by: str


# ============================================================================
# Helpers
# ============================================================================


def derive_login_url(request: Request) -> str:
    """Build the issuer's URL from the host this request arrived on.

    One build of beats runs at `beats.home.space`, `beats.<lan-ip>.nip.io`
    and `beats.home.elghareeb.space`, and the issuer is the sibling of
    whichever of those was used. Deriving it per-request is the same trick
    the auth service itself uses to pick a cookie domain, and it is why no
    per-deployment URL has to be configured.

    Returns "" when the host has too few labels to have a sibling — a bare
    `localhost:7999`, where there is no `auth.` to point at.
    """
    if settings.sso_login_url:
        return settings.sso_login_url.rstrip("/")

    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or ""
    if not host:
        return ""
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme or "http"

    hostname, _, port = host.partition(":")
    labels = hostname.split(".")
    # Needs a parent domain to hang `auth.` off: "beats.home.space" works,
    # "localhost" and a bare "home.space" do not.
    if len(labels) < 3:
        return ""

    auth_host = ".".join(["auth", *labels[1:]])
    return f"{proto}://{auth_host}" + (f":{port}" if port else "")


def _require_enabled() -> None:
    if not settings.sso_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "SSO_DISABLED",
                "message": "home.space SSO is not enabled on this instance.",
            },
        )


async def verify_home_cookie(request: Request, verifier: HomeSSOVerifier) -> HomeIdentity:
    """Verify the request's `Home-Session` cookie, or raise the right HTTP error.

    Shared with the account router's link endpoint, so the two agree on
    exactly which failure means what.
    """
    token = request.cookies.get(settings.sso_cookie_name, "")
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "SSO_NO_SESSION",
                "message": "No home.space session found. Sign in at the identity service first.",
            },
        )

    try:
        return await verifier.verify(token)
    except SSORejected as e:
        # The issuer looked and said no — expired, tampered with, or the
        # device was revoked. Not retryable.
        logger.info("home.space session rejected: %s", e)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "SSO_INVALID_SESSION",
                "message": "Your home.space session is no longer valid. Sign in again.",
            },
        ) from e
    except SSOUnavailable as e:
        # We could not reach a verdict. Saying "invalid" here would be a lie
        # and would push the user into a re-login that cannot succeed either.
        logger.warning("home.space session could not be verified: %s", e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "SSO_UNAVAILABLE",
                "message": "The home.space identity service is unreachable. Try again shortly.",
            },
        ) from e


# ============================================================================
# Endpoints
# ============================================================================


@router.get("/config", response_model=SSOConfigResponse)
async def get_sso_config(request: Request) -> SSOConfigResponse:
    """Whether this instance offers home.space SSO, and where to go for it.

    Always 200, even when disabled: the login screen calls this on every
    load to decide whether to render the second button, and an error there
    would be noise on every deployment that does not use SSO.
    """
    return SSOConfigResponse(
        enabled=settings.sso_enabled,
        provider_name=settings.sso_provider_name,
        login_url=derive_login_url(request) if settings.sso_enabled else "",
        session_present=bool(request.cookies.get(settings.sso_cookie_name)),
    )


@router.post("/session", response_model=SSOSessionResponse)
@limiter.limit("10/minute")
async def create_sso_session(
    request: Request,
    accounts: SSOAccountsDep,
) -> SSOSessionResponse:
    """Exchange a verified `Home-Session` cookie for a beats session token."""
    _require_enabled()
    identity = await verify_home_cookie(request, _verifier)

    try:
        user, created = await accounts.sign_in(identity)
    except SSOProvisionForbidden as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "SSO_PROVISION_FORBIDDEN", "message": str(e)},
        ) from e

    token = _session_manager.create_session_token(
        user.id or "", user.email, sso_subject=identity.did
    )
    logger.info(
        "home.space SSO sign-in: did=%s user=%s created=%s verified_by=%s",
        identity.did,
        user.id,
        created,
        identity.verified_by,
    )
    return SSOSessionResponse(
        verified=True,
        token=token,
        created=created,
        did=identity.did,
        holder_name=identity.holder_name,
        roles=identity.roles,
        display_name=user.display_name,
        verified_by=identity.verified_by,
    )
