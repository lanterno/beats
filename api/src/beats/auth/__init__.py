"""Authentication module.

Two independent ways in, deliberately kept separate:

- `webauthn` / `session` — beats' own passkey login and JWT sessions.
- `sso` / `sso_accounts` — the optional `home.space` federated door.

Nothing in the first group imports the second. With `BEATS_SSO_ENABLED`
unset, the SSO modules are inert.
"""

from beats.auth.session import SessionManager
from beats.auth.sso import HomeIdentity, HomeSSOVerifier, SSORejected, SSOUnavailable
from beats.auth.sso_accounts import SSOAccountService
from beats.auth.storage import MongoCredentialStorage
from beats.auth.webauthn import WebAuthnManager

__all__ = [
    "HomeIdentity",
    "HomeSSOVerifier",
    "MongoCredentialStorage",
    "SSOAccountService",
    "SSORejected",
    "SSOUnavailable",
    "SessionManager",
    "WebAuthnManager",
]
