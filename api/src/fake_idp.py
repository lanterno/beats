"""A scripted OpenID Connect provider, for the SSO tests.

Plays the provider's side of the authorization code flow through
`httpx.MockTransport`: a discovery document, a JWKS, and a token endpoint
that checks what a real one checks — the code exists and is unused, the
redirect URI matches, the PKCE verifier hashes to the challenge the code was
issued against, and the client authenticated — then returns an ID token
signed with a real RSA key.

`issue_code` stands in for the browser's trip through the provider's login
page: given what the authorization URL carried, it returns the code the
provider would send back.
"""

import base64
import hashlib
import json
import secrets
import time
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx
import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

from beats.auth.oidc import OIDCProvider
from beats.settings import OIDCProviderSettings

ISSUER = "https://idp.test"
CLIENT_ID = "beats-test"
CLIENT_SECRET = "s3cret"
REDIRECT_URI = "http://localhost:8080/auth/callback"

# One key for the whole run: RSA generation is the slow part.
_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _jwk(key: rsa.RSAPrivateKey, kid: str) -> dict[str, Any]:
    jwk = json.loads(RSAAlgorithm.to_jwk(key.public_key()))
    return {**jwk, "kid": kid, "use": "sig", "alg": "RS256"}


class FakeIdP:
    def __init__(self, *, provider_id: str = "test", name: str = "Test IdP"):
        self.provider_id = provider_id
        self.name = name
        self.key = _KEY
        self.kid = "k1"
        # Published keys; a test rotates by replacing this.
        self.jwks: list[dict[str, Any]] = [_jwk(self.key, self.kid)]
        self.auth_methods = ["client_secret_basic"]
        self.discovery_issuer = ISSUER
        # Set to a status to make the token endpoint fail with it.
        self.token_status: int | None = None
        self.codes: dict[str, dict[str, Any]] = {}
        self.token_requests: list[httpx.Request] = []
        self.jwks_fetches = 0

    # The provider's settings and client

    def settings(self, **overrides: Any) -> OIDCProviderSettings:
        fields: dict[str, Any] = {
            "id": self.provider_id,
            "name": self.name,
            "issuer": ISSUER,
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
        }
        return OIDCProviderSettings(**{**fields, **overrides})

    def provider(self, **overrides: Any) -> OIDCProvider:
        return OIDCProvider(self.settings(**overrides), transport=httpx.MockTransport(self.handle))

    # The browser's trip through the login page

    def issue_code(self, authorize_url: str, *, sub: str = "idp-user-1", **claims: Any) -> str:
        """The code the provider sends back after its user signs in as `sub`."""
        query = {k: v[0] for k, v in parse_qs(urlparse(authorize_url).query).items()}
        code = secrets.token_urlsafe(16)
        self.codes[code] = {
            "challenge": query["code_challenge"],
            "redirect_uri": query["redirect_uri"],
            "claims": {"sub": sub, "nonce": query["nonce"], **claims},
        }
        return code

    def id_token(self, *, kid: str | None = "k1", alg: str = "RS256", **claims: Any) -> str:
        now = int(time.time())
        payload = {"iss": ISSUER, "aud": CLIENT_ID, "iat": now, "exp": now + 300, **claims}
        headers = {"kid": kid} if kid else {}
        return jwt.encode(payload, self.key, algorithm=alg, headers=headers)

    # httpx.MockTransport handler

    def handle(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/.well-known/openid-configuration":
            return httpx.Response(
                200,
                json={
                    "issuer": self.discovery_issuer,
                    "authorization_endpoint": f"{ISSUER}/authorize",
                    "token_endpoint": f"{ISSUER}/token",
                    "jwks_uri": f"{ISSUER}/jwks",
                    "token_endpoint_auth_methods_supported": self.auth_methods,
                    "id_token_signing_alg_values_supported": ["RS256"],
                },
            )
        if path == "/jwks":
            self.jwks_fetches += 1
            return httpx.Response(200, json={"keys": self.jwks})
        if path == "/token":
            self.token_requests.append(request)
            return self._token(request)
        return httpx.Response(404)

    def _token(self, request: httpx.Request) -> httpx.Response:
        if self.token_status is not None:
            return httpx.Response(self.token_status, json={"error": "scripted"})
        form = {k: v[0] for k, v in parse_qs(request.content.decode()).items()}
        if not self._client_authenticated(request, form):
            return httpx.Response(401, json={"error": "invalid_client"})
        issued = self.codes.pop(form.get("code", ""), None)
        if issued is None or form.get("redirect_uri") != issued["redirect_uri"]:
            return httpx.Response(400, json={"error": "invalid_grant"})
        digest = hashlib.sha256(form.get("code_verifier", "").encode()).digest()
        if base64.urlsafe_b64encode(digest).rstrip(b"=").decode() != issued["challenge"]:
            return httpx.Response(400, json={"error": "invalid_grant"})
        return httpx.Response(
            200,
            json={
                "access_token": "unused",
                "token_type": "Bearer",
                "id_token": self.id_token(**issued["claims"]),
            },
        )

    def _client_authenticated(self, request: httpx.Request, form: dict[str, str]) -> bool:
        basic = request.headers.get("authorization", "")
        if basic.startswith("Basic "):
            pair = base64.b64decode(basic[6:]).decode()
            return pair == f"{CLIENT_ID}:{CLIENT_SECRET}"
        return form.get("client_id") == CLIENT_ID and form.get("client_secret") in (
            CLIENT_SECRET,
            None,
        )
