"""Mapping an identity a provider vouched for onto a beats account.

Three operations, and the difference between them is *who initiated*:

- `link`   — the user is already signed into beats and asks to attach an
             identity at a provider. Started with a beats session, finished
             with that same session (see `routers/sso.py`).
- `sign_in`— a verified identity arrives cold. If it is already linked, sign
             that user in. If not, create an account — only when the provider
             is configured to allow it.
- `unlink` — detach, refusing if it would leave the account with no way in.

What is deliberately absent is the fourth option: matching an arriving
identity against an existing account by its email and linking them
automatically. That is the standard account-takeover bug in federated login.
Beats' own sign-up doesn't verify addresses, and a provider's `email` is
whatever that provider lets its users set, so "same address" proves nothing
about "same person". An identity reaches an existing account only by being
linked from inside it.
"""

import hashlib
import logging

from beats.auth.oidc import OIDCIdentity
from beats.brand import APP_NAME
from beats.domain.models import LinkedIdentity, User
from beats.infrastructure.repositories import UserRepository

logger = logging.getLogger(__name__)

# Namespace for the addresses of accounts a provider created.
#
# `users.email` is unique-indexed and reachable from public signup, so an
# invented address in a namespace someone could register is both a future
# collision and a squatting vector: register it first and you inherit the
# account the sign-in would have created. `.invalid` is reserved by RFC 2606
# so it can never resolve or be registered.
SSO_EMAIL_DOMAIN = "sso.invalid"


class SSOAccountError(Exception):
    """Base for account-mapping failures."""


class SSOSignupClosed(SSOAccountError):
    """The identity is valid, but its provider doesn't create accounts."""


class SSOAlreadyLinked(SSOAccountError):
    """The identity is already linked to a different beats account."""


class SSOProviderLinked(SSOAccountError):
    """This account already has a different identity at the same provider."""


class SSONotLinked(SSOAccountError):
    """Nothing to unlink."""


class SSOLastCredential(SSOAccountError):
    """Unlinking would leave the account with no way to sign in."""


def sso_email_for(identity: OIDCIdentity) -> str:
    """A deterministic, non-registerable address for an account a provider created.

    Hashed from the issuer and subject together, since a `sub` is only unique
    within its issuer. The same identity always lands on the same address,
    which keeps a re-provision after a database restore from duplicating the
    user.
    """
    digest = hashlib.sha256(f"{identity.issuer}\n{identity.subject}".encode()).hexdigest()[:24]
    return f"{identity.provider}-{digest}@{SSO_EMAIL_DOMAIN}"


class SSOAccountService:
    """Resolves verified identities to beats users."""

    def __init__(self, user_repo: UserRepository):
        self._users = user_repo

    # Cold arrival: sign in, or create the account

    async def sign_in(self, identity: OIDCIdentity, *, allow_signup: bool) -> tuple[User, bool]:
        """Resolve a verified identity to a beats user.

        Returns `(user, created)`. Raises `SSOSignupClosed` when the identity
        is unknown and its provider does not create accounts.
        """
        existing = await self._users.get_by_identity(identity.issuer, identity.subject)
        if existing is not None:
            return await self._refresh_claims(existing, identity), False

        if not allow_signup:
            logger.info(
                "Refusing to create an account for %s %s: sign-up is off for that provider",
                identity.provider,
                identity.subject,
            )
            raise SSOSignupClosed(
                f"No {APP_NAME} account is linked to this identity. Sign in with a passkey, "
                "then link it from Settings."
            )

        user = User(
            email=sso_email_for(identity),
            display_name=identity.name,
            identities=[_linked(identity)],
            sso_provisioned=True,
        )
        created = await self._users.create(user)
        logger.info(
            "Created account %s for %s identity %s", created.id, identity.provider, identity.subject
        )
        return created, True

    # Warm arrival: link an identity to the account already signed in

    async def link(self, user_id: str, identity: OIDCIdentity) -> User:
        """Attach a verified identity to an existing, authenticated account."""
        holder = await self._users.get_by_identity(identity.issuer, identity.subject)
        if holder is not None and holder.id != user_id:
            raise SSOAlreadyLinked(
                f"That identity is already linked to another {APP_NAME} account."
            )

        user = await self._users.get_by_id(user_id)
        if user is None:
            raise SSOAccountError("User not found")

        current = user.identity_for(identity.provider)
        if current is not None and current.subject != identity.subject:
            raise SSOProviderLinked(
                "This account is already linked to a different identity at that provider. "
                "Unlink it first."
            )
        if current is not None:
            return await self._refresh_claims(user, identity)

        user.identities.append(_linked(identity))
        updated = await self._users.update(user)
        logger.info("Linked %s identity %s to %s", identity.provider, identity.subject, user_id)
        return updated

    async def unlink(self, user_id: str, provider: str, passkey_count: int) -> User:
        """Detach the identity linked through `provider`.

        `passkey_count` is the number of beats passkeys the account holds.
        Refused when nothing else would be left to sign in with — the same
        guard `WebAuthnManager.delete_credential` applies to the last passkey,
        seen from the other side.
        """
        user = await self._users.get_by_id(user_id)
        if user is None:
            raise SSOAccountError("User not found")
        if user.identity_for(provider) is None:
            raise SSONotLinked("No identity is linked through that provider.")
        remaining = [i for i in user.identities if i.provider != provider]
        if passkey_count < 1 and not remaining:
            raise SSOLastCredential(
                "Unlinking would leave this account with no way to sign in. "
                "Register a passkey first."
            )

        user.identities = remaining
        # `sso_provisioned` stays as it is: it is a fact about how the
        # account came into being, and stays true after the link is cut.
        updated = await self._users.update(user)
        logger.info("Unlinked %s identity from %s", provider, user_id)
        return updated

    async def _refresh_claims(self, user: User, identity: OIDCIdentity) -> User:
        """Re-sync what the provider owns on each sign-in.

        The name and address shown for the identity, and the provider id it
        arrived through (which changes if an operator renames a provider). The
        account's own `display_name` follows only on an account the provider
        created; on any other it was set here, and the provider has no say.
        """
        linked = next(
            i
            for i in user.identities
            if i.issuer == identity.issuer and i.subject == identity.subject
        )
        fresh = (identity.provider, identity.name, identity.email)
        if (linked.provider, linked.name, linked.email) == fresh:
            return user
        linked.provider, linked.name, linked.email = fresh
        if user.sso_provisioned and identity.name:
            user.display_name = identity.name
        return await self._users.update(user)


def _linked(identity: OIDCIdentity) -> LinkedIdentity:
    return LinkedIdentity(
        provider=identity.provider,
        issuer=identity.issuer,
        subject=identity.subject,
        name=identity.name,
        email=identity.email,
    )
