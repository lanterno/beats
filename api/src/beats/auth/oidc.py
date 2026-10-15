"""Single sign-on through OpenID Connect — any provider that speaks the standard.

The authorization code flow, with PKCE (S256) and a nonce on every request,
whether or not the client also has a secret:

1. `authorization_url` sends the browser to the provider with a fresh state,
   nonce and code challenge (the caller keeps the state, nonce and verifier
   server-side, see `routers/sso.py`).
2. The provider sends the browser back to the web app's `/auth/callback`,
   which posts the code and state to the API.
3. `redeem` trades the code (with the verifier) for an ID token at the token
   endpoint and checks that token: signature against the provider's published
   keys, `iss`, `aud`, `azp`, `exp`, `iat`, and the nonce.

What comes out is an `OIDCIdentity`, keyed on the provider's issuer and its
`sub` — never on an email, which a provider may let people change, or reuse.

Errors come in two kinds, and callers treat them differently: `OIDCRejected`
is a verdict (a used or expired code, a token that fails a check) and says
"start again"; `OIDCUnavailable` means the provider could not be reached or
answered nonsense, and says "try again shortly".
"""

import base64
import hashlib
import hmac
import logging
import secrets
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import httpx
import jwt

from beats.settings import OIDCProviderSettings

logger = logging.getLogger(__name__)

# Asymmetric only. `none` would accept an unsigned token, and the HS family
# would verify against the client secret — a value the provider is not the
# only one to hold.
SAFE_ALGORITHMS = frozenset(
    {"RS256", "RS384", "RS512", "PS256", "PS384", "PS512", "ES256", "ES384", "ES512", "EdDSA"}
)

# Clock skew allowed on `exp` and `iat`, between this server and the provider.
LEEWAY_SECONDS = 60


class OIDCError(Exception):
    """Base for sign-in failures."""


class OIDCRejected(OIDCError):
    """A verdict: the code or the token is not good. Start the sign-in again."""


class OIDCUnavailable(OIDCError):
    """No verdict: the provider could not be reached, or answered nonsense."""


@dataclass(frozen=True)
class OIDCIdentity:
    """Someone a provider vouched for."""

    # The configured provider's id, which names it in the UI.
    provider: str
    # Together, the identity. `sub` is only unique within one issuer.
    issuer: str
    subject: str
    # Display only: neither is used to find or match an account.
    name: str | None
    email: str | None


def new_pkce_pair() -> tuple[str, str]:
    """A PKCE code verifier and its S256 challenge (RFC 7636)."""
    verifier = secrets.token_urlsafe(48)  # 64 characters, within 43–128
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


class OIDCProvider:
    """One configured provider: its discovery document, keys and token exchange.

    One instance per provider is shared process-wide (see `OIDCRegistry`), so
    the discovery document and keys are fetched once and refreshed on a TTL.
    """

    def __init__(
        self,
        config: OIDCProviderSettings,
        *,
        timeout_seconds: float = 5.0,
        metadata_ttl_seconds: int = 3600,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self.config = config
        self._timeout = timeout_seconds
        self._ttl = metadata_ttl_seconds
        # Only set by tests, which hand in an `httpx.MockTransport` that plays
        # the provider.
        self._transport = transport
        self._metadata: dict[str, Any] | None = None
        self._metadata_at = 0.0
        self._jwks: list[dict[str, Any]] = []
        self._jwks_at = 0.0

    @property
    def id(self) -> str:
        return self.config.id

    @property
    def name(self) -> str:
        return self.config.name

    @property
    def allow_signup(self) -> bool:
        return self.config.allow_signup

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=self._timeout, transport=self._transport)

    async def _get_json(self, url: str) -> dict[str, Any]:
        try:
            async with self._client() as client:
                response = await client.get(url)
            response.raise_for_status()
            body = response.json()
        except (httpx.HTTPError, ValueError) as e:
            raise OIDCUnavailable(f"{self.id}: {url}: {e}") from e
        if not isinstance(body, dict):
            raise OIDCUnavailable(f"{self.id}: {url} did not return a JSON object")
        return body

    # Discovery

    async def metadata(self) -> dict[str, Any]:
        """The provider's discovery document, cached for the TTL."""
        if self._metadata is not None and time.monotonic() - self._metadata_at < self._ttl:
            return self._metadata

        url = f"{self.config.issuer}/.well-known/openid-configuration"
        body = await self._get_json(url)
        # OpenID Connect Discovery §4.3: the document must name the issuer it
        # was fetched for, exactly. A mismatch is a misconfigured issuer URL,
        # and every token would then fail its `iss` check anyway.
        if body.get("issuer") != self.config.issuer:
            raise OIDCUnavailable(
                f"{self.id}: discovery names issuer {body.get('issuer')!r}, "
                f"configured as {self.config.issuer!r}"
            )
        for field in ("authorization_endpoint", "token_endpoint", "jwks_uri"):
            if not isinstance(body.get(field), str):
                raise OIDCUnavailable(f"{self.id}: discovery has no {field}")
        self._metadata = body
        self._metadata_at = time.monotonic()
        return body

    async def _keys(self, *, refresh: bool) -> list[dict[str, Any]]:
        if self._jwks and not refresh and time.monotonic() - self._jwks_at < self._ttl:
            return self._jwks
        meta = await self.metadata()
        keys = (await self._get_json(meta["jwks_uri"])).get("keys")
        if not isinstance(keys, list) or not keys:
            raise OIDCUnavailable(f"{self.id}: the JWKS lists no keys")
        self._jwks = [k for k in keys if isinstance(k, dict) and k.get("use", "sig") == "sig"]
        self._jwks_at = time.monotonic()
        return self._jwks

    # 1. Where to send the browser

    async def authorization_url(
        self, *, redirect_uri: str, state: str, nonce: str, code_challenge: str
    ) -> str:
        meta = await self.metadata()
        query = urlencode(
            {
                "response_type": "code",
                "client_id": self.config.client_id,
                "redirect_uri": redirect_uri,
                "scope": self.config.scopes,
                "state": state,
                "nonce": nonce,
                "code_challenge": code_challenge,
                "code_challenge_method": "S256",
            }
        )
        endpoint = meta["authorization_endpoint"]
        return f"{endpoint}{'&' if '?' in endpoint else '?'}{query}"

    # 2. Trading the code for an identity

    async def redeem(
        self, *, code: str, code_verifier: str, redirect_uri: str, nonce: str
    ) -> OIDCIdentity:
        id_token = await self._exchange(code, code_verifier, redirect_uri)
        claims = await self._verify_id_token(id_token, nonce)
        return OIDCIdentity(
            provider=self.id,
            issuer=self.config.issuer,
            subject=claims["sub"],
            name=claims.get("name") or claims.get("preferred_username"),
            email=claims.get("email"),
        )

    async def _exchange(self, code: str, code_verifier: str, redirect_uri: str) -> str:
        meta = await self.metadata()
        form = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "code_verifier": code_verifier,
            "client_id": self.config.client_id,
        }
        # httpx takes no `auth=None` (it means "the client default"), so it is
        # passed only when there is a secret to send.
        extra: dict[str, Any] = {}
        if self.config.client_secret:
            # Basic is the spec's default when a provider lists nothing.
            methods = meta.get("token_endpoint_auth_methods_supported") or ["client_secret_basic"]
            if "client_secret_basic" in methods:
                extra["auth"] = httpx.BasicAuth(self.config.client_id, self.config.client_secret)
            else:
                form["client_secret"] = self.config.client_secret

        try:
            async with self._client() as client:
                response = await client.post(
                    meta["token_endpoint"],
                    data=form,
                    headers={"Accept": "application/json"},
                    **extra,
                )
        except httpx.HTTPError as e:
            raise OIDCUnavailable(f"{self.id}: token endpoint: {e}") from e

        if response.status_code in (400, 401):
            # invalid_grant (a used, expired or foreign code) and friends.
            error = _error_of(response)
            logger.info("%s refused the code: %s", self.id, error)
            raise OIDCRejected(f"{self.id} refused the sign-in code ({error})")
        if response.status_code != 200:
            raise OIDCUnavailable(f"{self.id}: token endpoint returned {response.status_code}")
        try:
            id_token = response.json().get("id_token")
        except ValueError as e:
            raise OIDCUnavailable(f"{self.id}: token endpoint returned non-JSON") from e
        if not isinstance(id_token, str) or not id_token:
            raise OIDCUnavailable(f"{self.id}: token response has no id_token (is openid a scope?)")
        return id_token

    async def _verify_id_token(self, id_token: str, nonce: str) -> dict[str, Any]:
        try:
            header = jwt.get_unverified_header(id_token)
        except jwt.InvalidTokenError as e:
            raise OIDCRejected(f"{self.id}: the ID token is malformed") from e

        alg = header.get("alg")
        if alg not in SAFE_ALGORITHMS:
            raise OIDCRejected(f"{self.id}: the ID token is signed with {alg!r}, not accepted")

        key = await self._signing_key(header.get("kid"), alg)
        try:
            claims = jwt.decode(
                id_token,
                key=key,
                algorithms=[alg],
                audience=self.config.client_id,
                issuer=self.config.issuer,
                leeway=LEEWAY_SECONDS,
                options={"require": ["iss", "sub", "aud", "exp", "iat"]},
            )
        except jwt.InvalidTokenError as e:
            raise OIDCRejected(f"{self.id}: the ID token failed a check: {e}") from e

        # Core §3.1.3.7: with more than one audience, the token must have
        # been issued to us specifically.
        aud = claims["aud"]
        if isinstance(aud, list) and len(aud) > 1 and claims.get("azp") != self.config.client_id:
            raise OIDCRejected(f"{self.id}: the ID token was issued to another party")

        if not hmac.compare_digest(str(claims.get("nonce", "")), nonce):
            raise OIDCRejected(f"{self.id}: the ID token's nonce does not match this sign-in")
        if not isinstance(claims["sub"], str) or not claims["sub"]:
            raise OIDCRejected(f"{self.id}: the ID token has no subject")
        return claims

    async def _signing_key(self, kid: str | None, alg: str) -> Any:
        """The published key that signed the token.

        Looked up by `kid`. A `kid` we have not seen means the provider has
        rotated its keys since we fetched them, so fetch once more before
        giving up. A token without a `kid` is accepted only when the provider
        publishes a single key, since there is then nothing to choose.
        """
        for refresh in (False, True):
            keys = await self._keys(refresh=refresh)
            if kid is None:
                if len(keys) == 1:
                    return _key_for(keys[0], alg, self.id)
                raise OIDCRejected(f"{self.id}: the ID token names no key, and several exist")
            match = next((k for k in keys if k.get("kid") == kid), None)
            if match is not None:
                return _key_for(match, alg, self.id)
        raise OIDCRejected(f"{self.id}: the ID token was signed with an unknown key")


def _key_for(jwk: dict[str, Any], alg: str, provider: str) -> Any:
    try:
        return jwt.PyJWK.from_dict(jwk, algorithm=alg).key
    except jwt.PyJWKError as e:
        raise OIDCUnavailable(f"{provider}: a published key cannot be used: {e}") from e


def _error_of(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return f"HTTP {response.status_code}"
    return str(body.get("error") or f"HTTP {response.status_code}")


class OIDCRegistry:
    """The configured providers, by id, in the order they were configured."""

    def __init__(self, providers: list[OIDCProvider]):
        self._providers = {p.id: p for p in providers}

    @classmethod
    def from_settings(cls, configs: list[OIDCProviderSettings]) -> OIDCRegistry:
        return cls([OIDCProvider(c) for c in configs])

    def get(self, provider_id: str) -> OIDCProvider | None:
        return self._providers.get(provider_id)

    def all(self) -> list[OIDCProvider]:
        return list(self._providers.values())

    def name_of(self, provider_id: str) -> str:
        """The provider's display name, or its id once it is no longer configured."""
        provider = self._providers.get(provider_id)
        return provider.name if provider else provider_id
