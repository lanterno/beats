"""home.space SSO — verification of the `Home-Session` cookie.

Beats is deployed into a stack (`/home/green/lab/home`) that already has a
Self-Sovereign Identity issuer: `auth.home.space`, port 6007. It mints an
Ed25519-signed JWT into a `Home-Session` cookie scoped to `.home.space`, so
every sibling vhost — `rizq.home.space`, `mailmind.home.space`, and now
`beats.home.space` — receives it on every request.

The sibling services are gated by nginx `auth_request`, at the edge, before
the backend sees anything. Beats deliberately is **not**: it has its own user
system, and the whole point of this integration is that either door works. So
beats is the stack's first *native in-service verifier* — the case
`IDENTITY_ARCHITECTURE.md` §2.3 anticipated but nothing had needed yet.

Two ways to check a token, in this order:

1. **Ask the issuer** (`GET /api/session/verify`). Authoritative, because it
   is the only check that sees `auth.db` — a device revoked in `/devices`
   fails here immediately, while its already-issued cookie stays
   cryptographically valid until it expires up to 24h later.
2. **Verify the signature offline** against a cached JWKS. Used only when the
   issuer is unreachable, so a stopped `home-auth.service` degrades beats to
   "existing sessions keep working" instead of "nobody can log in".

The distinction that makes this safe is between an issuer that *says no* and
an issuer that *does not answer*. A 401 is a decision and is final —
falling back to offline verification there would let a revoked device walk
straight past the revocation it just failed. Only a transport failure
(connection refused, timeout, 5xx) is allowed to reach the fallback.
"""

import logging
import time
from typing import Any, Literal

import httpx
import jwt
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class HomeIdentity(BaseModel):
    """A verified `home.space` identity.

    `did` is the stable subject — a `did:key:z6Mku…` derived from the device's
    own public key. It is the only field safe to key a local account on:
    `holder_name` is a free-text label chosen at enrollment ("Primary
    Laptop") and is neither unique nor immutable.
    """

    did: str
    holder_name: str
    roles: list[str]
    issuer: str
    verified_by: Literal["issuer", "offline"]

    def has_any_role(self, allowed: frozenset[str]) -> bool:
        """True if any of this identity's roles is in `allowed`.

        An empty `allowed` means "no role gate configured", not "deny all".
        """
        if not allowed:
            return True
        return any(role.lower() in allowed for role in self.roles)


class SSOError(Exception):
    """Base for SSO verification failures."""


class SSORejected(SSOError):
    """The token is not valid — bad signature, expired, wrong issuer, revoked.

    An authoritative "no". Never retried against a weaker check.
    """


class SSOUnavailable(SSOError):
    """The token could not be judged either way.

    The issuer did not answer and no cached JWKS exists to fall back on.
    Distinct from `SSORejected` so callers can return 503 rather than 401 —
    telling a user their identity is invalid when we simply could not look is
    both wrong and unhelpful.
    """


class HomeSSOVerifier:
    """Verifies `Home-Session` tokens, issuer-first with an offline fallback.

    One instance is shared process-wide (see `routers/sso.py`); the JWKS cache
    lives on it. Cheap to construct, so tests make their own.
    """

    def __init__(
        self,
        *,
        auth_base_url: str,
        issuer: str,
        jwks_ttl_seconds: int = 300,
        timeout_seconds: float = 2.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self._base = auth_base_url.rstrip("/")
        self._issuer = issuer
        self._jwks_ttl = jwks_ttl_seconds
        self._timeout = timeout_seconds
        # Only set by tests, which hand in an `httpx.MockTransport`. Kept as
        # a constructor argument rather than a patched module global so a
        # test can stand up a verifier with a scripted issuer without
        # touching the one the app is using.
        self._transport = transport

        # Last good JWKS, kept indefinitely. `_jwks_fetched_at` only decides
        # when to *refresh*; expiry never empties the cache, because the whole
        # value of holding it is being able to verify while the issuer that
        # would serve a fresh copy is down.
        self._jwks: list[dict[str, Any]] | None = None
        self._jwks_fetched_at: float = 0.0

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=self._timeout, transport=self._transport)

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    async def verify(self, token: str) -> HomeIdentity:
        """Verify a `Home-Session` token and return the identity it carries.

        Raises `SSORejected` if the token is bad, `SSOUnavailable` if no
        verdict could be reached at all.
        """
        if not token:
            raise SSORejected("No session token presented")

        try:
            return await self._verify_via_issuer(token)
        except SSORejected:
            # The issuer looked and said no. That is the answer.
            raise
        except SSOUnavailable as e:
            logger.warning("SSO issuer unreachable (%s); falling back to offline verify", e)

        return await self._verify_offline(token)

    # ------------------------------------------------------------------
    # 1. Issuer introspection — authoritative, sees revocation
    # ------------------------------------------------------------------

    async def _verify_via_issuer(self, token: str) -> HomeIdentity:
        url = f"{self._base}/api/session/verify"
        try:
            async with self._client() as client:
                response = await client.get(url, headers={"Authorization": f"Bearer {token}"})
        except httpx.HTTPError as e:
            raise SSOUnavailable(f"{type(e).__name__}: {e}") from e

        if response.status_code in (401, 403):
            # Covers an expired token, a bad signature, and — the reason this
            # path exists at all — a device revoked since the cookie was
            # minted. `get_session_verify` checks `is_device_revoked` against
            # auth.db on every call.
            raise SSORejected("Issuer rejected the session token")

        if response.status_code >= 500 or response.status_code == 404:
            # A broken or mid-deploy issuer is a transport problem, not a
            # verdict on the token.
            raise SSOUnavailable(f"Issuer returned HTTP {response.status_code}")

        if response.status_code != 200:
            raise SSORejected(f"Issuer returned HTTP {response.status_code}")

        try:
            body = response.json()
        except ValueError as e:
            raise SSOUnavailable(f"Issuer returned non-JSON: {e}") from e

        did = body.get("did")
        if not body.get("authenticated") or not did:
            raise SSORejected("Issuer reported the session as unauthenticated")

        return HomeIdentity(
            did=did,
            holder_name=body.get("holder_name") or did,
            roles=list(body.get("roles") or []),
            issuer=self._issuer,
            verified_by="issuer",
        )

    # ------------------------------------------------------------------
    # 2. Offline signature verification — no revocation, but survives outage
    # ------------------------------------------------------------------

    async def _verify_offline(self, token: str) -> HomeIdentity:
        keys = await self._get_jwks()
        if not keys:
            raise SSOUnavailable(
                "Issuer unreachable and no cached JWKS available to verify against"
            )

        # The issuer's session tokens carry `{"alg":"EdDSA","typ":"JWT"}` and
        # deliberately no `kid`, so there is nothing to select a key by. That
        # rules out `jwt.PyJWKClient`, which resolves strictly by `kid`, and
        # leaves trying each published key. There is one today; a rotation
        # would publish two, and both would be tried.
        last_error: Exception | None = None
        for key_dict in keys:
            try:
                signing_key = jwt.PyJWK.from_dict(key_dict).key
            except Exception as e:  # malformed entry — skip, try the next
                last_error = e
                continue
            try:
                payload = jwt.decode(
                    token,
                    key=signing_key,
                    algorithms=["EdDSA"],
                    issuer=self._issuer,
                    options={"verify_aud": False, "require": ["exp", "sub", "iss"]},
                )
            except jwt.InvalidTokenError as e:
                last_error = e
                continue

            did = payload.get("sub")
            if not did:
                raise SSORejected("Session token has no subject")

            return HomeIdentity(
                did=did,
                holder_name=payload.get("name") or did,
                roles=list(payload.get("roles") or []),
                issuer=self._issuer,
                verified_by="offline",
            )

        raise SSORejected(f"No published key verified the session token: {last_error}")

    async def _get_jwks(self) -> list[dict[str, Any]] | None:
        """Return the issuer's public keys, refetching when the TTL has passed.

        A failed refetch keeps the previous copy rather than discarding it:
        this is the fallback path, and the issuer being down is exactly when
        it is needed.
        """
        age = time.monotonic() - self._jwks_fetched_at
        if self._jwks is not None and age < self._jwks_ttl:
            return self._jwks

        try:
            async with self._client() as client:
                response = await client.get(f"{self._base}/.well-known/jwks.json")
            response.raise_for_status()
            keys = response.json().get("keys")
            if isinstance(keys, list) and keys:
                self._jwks = keys
                self._jwks_fetched_at = time.monotonic()
        except (httpx.HTTPError, ValueError) as e:
            logger.warning("Could not refresh SSO JWKS: %s", e)

        return self._jwks
