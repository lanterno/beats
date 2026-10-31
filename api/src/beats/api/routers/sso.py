"""Single sign-on through OpenID Connect — the second front door.

Public, like the rest of `/api/auth`. Three steps, the same for every provider:

1. `POST /{provider}/start` keeps a fresh state, nonce and PKCE verifier
   server-side and answers with the provider's authorization URL. The web app
   keeps the state too (sessionStorage), then sends the browser there.
2. The provider sends the browser back to the web app's `/auth/callback`
   (`OIDC_REDIRECT_URI`), with a code and the state.
3. The web app checks the state is the one it sent — a callback this browser
   didn't start is refused there, which stops anyone signing a victim into
   the attacker's account with a link — and posts both to `POST /complete`.
   That takes the flow (once), redeems the code, and either signs in or, for
   a flow started from Settings, links the identity.

The code is redeemed here rather than at the API's own URL so one setup works
whether the web app and the API share an origin (the self-hosted stack) or not
(lifepete.com, where nothing the API sets in the browser would reach the web
app).

From the token on, nothing else in the API knows which door was used.
Linking starts in `account.py`, because it needs a signed-in account.
"""

import hashlib
import logging
import secrets
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from beats.api.routers.auth import UserRepoDep, _session_manager, limiter
from beats.auth.oidc import (
    OIDCProvider,
    OIDCRegistry,
    OIDCRejected,
    OIDCUnavailable,
    new_pkce_pair,
)
from beats.auth.sso_accounts import (
    SSOAccountError,
    SSOAccountService,
    SSOAlreadyLinked,
    SSOProviderLinked,
    SSOSignupClosed,
)
from beats.domain.models import SSOFlow
from beats.infrastructure.database import Database
from beats.infrastructure.repositories import MongoSSOFlowRepository, SSOFlowRepository
from beats.settings import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth/sso", tags=["sso"])

# Shared process-wide, so each provider's discovery document and keys are
# fetched once. Makes no network call until a sign-in starts.
_registry = OIDCRegistry.from_settings(settings.oidc_providers)


def get_oidc_registry() -> OIDCRegistry:
    """The configured providers (tests override this dependency)."""
    return _registry


def get_sso_flows() -> SSOFlowRepository:
    return MongoSSOFlowRepository(Database.get_db().sso_flows)


def get_sso_accounts(user_repo: UserRepoDep) -> SSOAccountService:
    return SSOAccountService(user_repo)


RegistryDep = Annotated[OIDCRegistry, Depends(get_oidc_registry)]
SSOFlowsDep = Annotated[SSOFlowRepository, Depends(get_sso_flows)]
SSOAccountsDep = Annotated[SSOAccountService, Depends(get_sso_accounts)]


class SSOProviderInfo(BaseModel):
    id: str
    name: str


class SSOProvidersResponse(BaseModel):
    providers: list[SSOProviderInfo]


class SSOStartResponse(BaseModel):
    # Where to send the browser.
    authorize_url: str
    # Echoed back by the provider. The web app keeps it to check that the
    # callback it receives is one it started.
    state: str


class SSOCompleteRequest(BaseModel):
    code: str = Field(min_length=1, max_length=4096)
    state: str = Field(min_length=1, max_length=512)


class SSOCompleteResponse(BaseModel):
    intent: Literal["sign_in", "link"]
    provider: str
    # A beats session token, for a sign-in. None for a link: the session that
    # started it is still the one in use.
    token: str | None = None
    # True when this sign-in created the account.
    created: bool = False


def _state_hash(state: str) -> str:
    return hashlib.sha256(state.encode()).hexdigest()


def sso_error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


def provider_or_404(registry: OIDCRegistry, provider_id: str) -> OIDCProvider:
    provider = registry.get(provider_id)
    if provider is None:
        raise sso_error(
            status.HTTP_404_NOT_FOUND,
            "SSO_UNKNOWN_PROVIDER",
            f"No sign-in provider called {provider_id!r} is set up here.",
        )
    return provider


def unavailable(provider: OIDCProvider, e: OIDCUnavailable) -> HTTPException:
    logger.warning("SSO provider unavailable: %s", e)
    return sso_error(
        status.HTTP_503_SERVICE_UNAVAILABLE,
        "SSO_UNAVAILABLE",
        f"{provider.name} can't be reached right now. Try again shortly.",
    )


async def start_flow(
    provider: OIDCProvider,
    flows: SSOFlowRepository,
    intent: Literal["sign_in", "link"],
    user_id: str | None = None,
) -> SSOStartResponse:
    """Keep a new flow and return where to send the browser (shared with linking)."""
    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    verifier, challenge = new_pkce_pair()
    try:
        url = await provider.authorization_url(
            redirect_uri=settings.oidc_redirect_uri,
            state=state,
            nonce=nonce,
            code_challenge=challenge,
        )
    except OIDCUnavailable as e:
        raise unavailable(provider, e) from e
    await flows.create(
        SSOFlow(
            state_hash=_state_hash(state),
            provider=provider.id,
            nonce=nonce,
            code_verifier=verifier,
            intent=intent,
            user_id=user_id,
        )
    )
    return SSOStartResponse(authorize_url=url, state=state)


@router.get("/providers", response_model=SSOProvidersResponse)
async def list_providers(registry: RegistryDep) -> SSOProvidersResponse:
    """The providers people can sign in with here, in configured order.

    Always 200: the login screen asks on every load, and an instance with
    none configured answers with an empty list.
    """
    return SSOProvidersResponse(
        providers=[SSOProviderInfo(id=p.id, name=p.name) for p in registry.all()]
    )


@router.post("/{provider_id}/start", response_model=SSOStartResponse)
@limiter.limit("10/minute")
async def start_sign_in(
    request: Request,
    provider_id: str,
    registry: RegistryDep,
    flows: SSOFlowsDep,
) -> SSOStartResponse:
    """Begin signing in through a provider."""
    provider = provider_or_404(registry, provider_id)
    return await start_flow(provider, flows, "sign_in")


@router.post("/complete", response_model=SSOCompleteResponse)
@limiter.limit("10/minute")
async def complete(
    request: Request,
    body: SSOCompleteRequest,
    registry: RegistryDep,
    flows: SSOFlowsDep,
    accounts: SSOAccountsDep,
) -> SSOCompleteResponse:
    """Finish a sign-in or a link with the code the provider sent back."""
    flow = await flows.take(_state_hash(body.state))
    if flow is None:
        raise sso_error(
            status.HTTP_400_BAD_REQUEST,
            "SSO_FLOW_EXPIRED",
            "This sign-in has expired or was already used. Start again.",
        )

    # A link must finish in the session that started it. The flow is
    # already spent, so a mismatch can't be retried with another token.
    if flow.intent == "link" and getattr(request.state, "user_id", None) != flow.user_id:
        raise sso_error(
            status.HTTP_403_FORBIDDEN,
            "SSO_LINK_SESSION_MISMATCH",
            "Finish linking in the same signed-in session that started it.",
        )

    provider = provider_or_404(registry, flow.provider)
    try:
        identity = await provider.redeem(
            code=body.code,
            code_verifier=flow.code_verifier,
            redirect_uri=settings.oidc_redirect_uri,
            nonce=flow.nonce,
        )
    except OIDCRejected as e:
        logger.info("SSO sign-in rejected: %s", e)
        raise sso_error(
            status.HTTP_401_UNAUTHORIZED,
            "SSO_REJECTED",
            f"{provider.name} didn't confirm this sign-in. Start again.",
        ) from e
    except OIDCUnavailable as e:
        raise unavailable(provider, e) from e

    if flow.intent == "link":
        assert flow.user_id is not None  # checked against the session above
        try:
            await accounts.link(flow.user_id, identity)
        except SSOAlreadyLinked as e:
            raise sso_error(status.HTTP_409_CONFLICT, "SSO_ALREADY_LINKED", str(e)) from e
        except SSOProviderLinked as e:
            raise sso_error(status.HTTP_409_CONFLICT, "SSO_PROVIDER_LINKED", str(e)) from e
        except SSOAccountError as e:
            raise sso_error(status.HTTP_400_BAD_REQUEST, "SSO_LINK_FAILED", str(e)) from e
        return SSOCompleteResponse(intent="link", provider=provider.id)

    try:
        user, created = await accounts.sign_in(identity, allow_signup=provider.allow_signup)
    except SSOSignupClosed as e:
        raise sso_error(status.HTTP_403_FORBIDDEN, "SSO_SIGNUP_CLOSED", str(e)) from e

    token = _session_manager.create_session_token(user.id or "", user.email)
    # The door is not recorded downstream (PRIVACY.md, Authentication): the
    # provider stays out of this line too, which Cloud Logging keeps for 30
    # days. A rejected sign-in above still names what rejected it.
    logger.info("SSO sign-in: user=%s created=%s", user.id, created)
    return SSOCompleteResponse(intent="sign_in", provider=provider.id, token=token, created=created)
