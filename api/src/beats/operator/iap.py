"""Verifying Google IAP's signed assertion (`x-goog-iap-jwt-assertion`).

Its own verifier, built the way `auth/oidc.py` is — an async httpx fetch of
the key set with a TTL cache, `jwt.PyJWK` per key — because `oidc.py` cannot
be reused here: it imports `beats.settings`, which the operator deployment
must never load. It doesn't use `PyJWKClient`, which is synchronous urllib
and would block the loop.

The checks are Google's guide to securing with signed headers:

- `alg` ES256 and no other;
- a `kid` among the keys Google publishes;
- `iss` https://cloud.google.com/iap;
- `aud` the Cloud Run service's audience, from `OperatorSettings`;
- `exp` and `iat`, within 30 seconds of skew.
"""

import time
from typing import Any

import httpx
import jwt

IAP_KEYS_URL = "https://www.gstatic.com/iap/verify/public_key-jwk"
IAP_ISSUER = "https://cloud.google.com/iap"
LEEWAY_SECONDS = 30
KEYS_TTL_SECONDS = 3600


class IAPRejected(Exception):
    """The assertion is not one IAP signed for this service. The middleware
    answers 401; the message is for the log, never the response."""


class IAPUnavailable(Exception):
    """Google's key set cannot be fetched right now — a 503, not a 401:
    nothing is known about the caller either way."""


class IAPVerifier:
    """Verifies assertions against Google's published keys, cached for an
    hour. A `kid` not in the cached set refetches once before giving up,
    so a key rotation doesn't refuse real operators for the TTL."""

    def __init__(
        self,
        audience: str,
        *,
        keys_url: str = IAP_KEYS_URL,
        ttl_seconds: float = KEYS_TTL_SECONDS,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self._audience = audience
        self._keys_url = keys_url
        self._ttl = ttl_seconds
        self._transport = transport
        self._keys: dict[str, dict[str, Any]] = {}
        self._keys_at = 0.0

    async def _fetch_keys(self, *, refresh: bool) -> dict[str, dict[str, Any]]:
        if self._keys and not refresh and time.monotonic() - self._keys_at < self._ttl:
            return self._keys
        try:
            async with httpx.AsyncClient(timeout=10, transport=self._transport) as client:
                response = await client.get(self._keys_url)
            response.raise_for_status()
            body = response.json()
        except (httpx.HTTPError, ValueError) as e:
            raise IAPUnavailable(f"IAP key set: {e}") from e
        # Google serves the set as {kid: jwk} and historically also as
        # {"keys": [...]}; read either.
        keys = body.get("keys") if isinstance(body.get("keys"), list) else None
        if keys is not None:
            jwks = {k.get("kid", ""): k for k in keys if isinstance(k, dict)}
        elif all(isinstance(v, dict) for v in body.values()):
            jwks = {kid: {"kid": kid, **jwk} for kid, jwk in body.items()}
        else:
            raise IAPUnavailable("IAP key set: not a JWK set")
        self._keys = jwks
        self._keys_at = time.monotonic()
        return self._keys

    async def _key_for(self, kid: str) -> Any:
        for refresh in (False, True):
            keys = await self._fetch_keys(refresh=refresh)
            jwk = keys.get(kid)
            if jwk is not None:
                try:
                    return jwt.PyJWK.from_dict(jwk, algorithm="ES256").key
                except jwt.PyJWKError as e:
                    raise IAPUnavailable(f"IAP key {kid}: {e}") from e
        raise IAPRejected("the assertion was signed with an unknown key")

    async def verify(self, assertion: str) -> dict[str, Any]:
        """The assertion's claims, or IAPRejected. `sub` is Google's stable
        id for the account — what the allowlist is keyed on."""
        try:
            header = jwt.get_unverified_header(assertion)
        except jwt.InvalidTokenError as e:
            raise IAPRejected(f"malformed assertion: {e}") from e
        if header.get("alg") != "ES256":
            raise IAPRejected(f"alg {header.get('alg')!r} is not ES256")
        kid = header.get("kid")
        if not isinstance(kid, str) or not kid:
            raise IAPRejected("the assertion names no key")

        key = await self._key_for(kid)
        try:
            claims = jwt.decode(
                assertion,
                key,
                algorithms=["ES256"],
                audience=self._audience,
                issuer=IAP_ISSUER,
                leeway=LEEWAY_SECONDS,
                options={"require": ["exp", "iat", "aud", "iss", "sub"]},
            )
        except jwt.InvalidTokenError as e:
            raise IAPRejected(str(e)) from e
        return claims
