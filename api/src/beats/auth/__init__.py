"""Authentication module.

Two independent ways in, deliberately kept separate:

- `webauthn` / `session` — beats' own passkey login and JWT sessions.
- `oidc` / `sso_accounts` — the optional single sign-on door, through any
  OpenID Connect provider configured in `OIDC_PROVIDERS`.

Nothing in the first group imports the second. With no provider configured,
the SSO modules are inert.
"""

from beats.auth.oidc import OIDCIdentity, OIDCProvider, OIDCRegistry
from beats.auth.session import SessionManager
from beats.auth.sso_accounts import SSOAccountService
from beats.auth.storage import MongoCredentialStorage
from beats.auth.webauthn import WebAuthnManager

__all__ = [
    "MongoCredentialStorage",
    "OIDCIdentity",
    "OIDCProvider",
    "OIDCRegistry",
    "SSOAccountService",
    "SessionManager",
    "WebAuthnManager",
]
