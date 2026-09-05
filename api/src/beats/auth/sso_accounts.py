"""Mapping a verified home.space identity onto a beats account.

Three operations, and the difference between them is *who initiated*:

- `link`   — the user is already signed into beats and asks to attach their
             home.space identity. Both sides prove themselves in one request.
- `sign_in`— a verified identity arrives cold. If it is already linked, sign
             that user in. If it is not, provision a new account, subject to
             the role gate.
- `unlink` — detach, refusing if it would leave the account with no way in.

What is deliberately absent is the fourth option: matching an arriving SSO
identity against an existing account by some shared attribute and linking
them automatically. That is the standard account-takeover bug in federated
login — it turns "can set an email/name" into "can take over an account" the
moment the issuer's claim is unverified.

Beats is structurally immune, and it is worth being explicit about why: the
`HomeAccessCredential` carries no email at all. Its subject is a `did:key`
derived from a device public key, and `holderName` is a free-text enrollment
label ("Primary Laptop"). Neither is matchable against `users.email`, so
there is nothing to auto-link on even accidentally. Linking is therefore
always an authenticated, user-initiated act.
"""

import logging
import re
from datetime import UTC, datetime

from beats.auth.sso import HomeIdentity
from beats.domain.models import User
from beats.infrastructure.repositories import UserRepository

logger = logging.getLogger(__name__)

# Namespace for the addresses of auto-provisioned accounts.
#
# `users.email` is unique-indexed and reachable from public signup, so an
# invented address in a namespace someone could actually register is both a
# future collision and a squatting vector — register the address first and
# you inherit the account the SSO login would have created. `.invalid` is
# reserved by RFC 2606 precisely so it can never resolve or be registered,
# which makes it the one safe choice here.
SSO_EMAIL_DOMAIN = "sso.home.space.invalid"

_EMAIL_LOCAL_SAFE = re.compile(r"[^A-Za-z0-9._-]")


class SSOAccountError(Exception):
    """Base for account-mapping failures."""


class SSOProvisionForbidden(SSOAccountError):
    """The identity is valid but not allowed to create a new beats account."""


class SSOAlreadyLinked(SSOAccountError):
    """The identity is already linked to a different beats account."""


class SSOLinkConflict(SSOAccountError):
    """This beats account already has a different identity linked."""


class SSONotLinked(SSOAccountError):
    """Nothing to unlink."""


class SSOLastCredential(SSOAccountError):
    """Unlinking would leave the account with no way to sign in."""


def sso_email_for(identity: HomeIdentity) -> str:
    """A deterministic, non-registerable address for a provisioned account.

    Derived from the DID's multibase suffix, which is unique by
    construction — it *is* the public key. The same identity therefore
    always lands on the same address, which keeps a re-provision after a
    database restore idempotent rather than duplicating the user.
    """
    suffix = identity.did.rsplit(":", 1)[-1]
    safe = _EMAIL_LOCAL_SAFE.sub("", suffix) or "unknown"
    return f"{safe}@{SSO_EMAIL_DOMAIN}"


class SSOAccountService:
    """Resolves verified identities to beats users."""

    def __init__(self, user_repo: UserRepository, provision_roles: frozenset[str]):
        self._users = user_repo
        self._provision_roles = provision_roles

    # ------------------------------------------------------------------
    # Cold arrival: sign in, or provision
    # ------------------------------------------------------------------

    async def sign_in(self, identity: HomeIdentity) -> tuple[User, bool]:
        """Resolve a verified identity to a beats user.

        Returns `(user, created)`. Raises `SSOProvisionForbidden` when the
        identity is unknown and its roles do not permit provisioning.
        """
        existing = await self._users.get_by_sso_subject(identity.issuer, identity.did)
        if existing is not None:
            return await self._refresh_claims(existing, identity), False

        if not identity.has_any_role(self._provision_roles):
            logger.warning(
                "Refusing to provision beats account for %s: roles %s not in %s",
                identity.did,
                identity.roles,
                sorted(self._provision_roles),
            )
            raise SSOProvisionForbidden(
                "This home.space identity is not allowed to create a new Beats account. "
                "Ask the owner to create one for you, then link it from Settings."
            )

        user = User(
            email=sso_email_for(identity),
            display_name=identity.holder_name,
            sso_issuer=identity.issuer,
            sso_subject=identity.did,
            sso_holder_name=identity.holder_name,
            sso_roles=list(identity.roles),
            sso_linked_at=datetime.now(UTC),
            sso_provisioned=True,
        )
        created = await self._users.create(user)
        logger.info(
            "Provisioned beats account %s for home.space identity %s (%s)",
            created.id,
            identity.did,
            identity.holder_name,
        )
        return created, True

    # ------------------------------------------------------------------
    # Warm arrival: link an identity to the account already signed in
    # ------------------------------------------------------------------

    async def link(self, user_id: str, identity: HomeIdentity) -> User:
        """Attach a verified identity to an existing, authenticated account."""
        holder = await self._users.get_by_sso_subject(identity.issuer, identity.did)
        if holder is not None and holder.id != user_id:
            raise SSOAlreadyLinked(
                "That home.space identity is already linked to another Beats account."
            )

        user = await self._users.get_by_id(user_id)
        if user is None:
            raise SSOAccountError("User not found")

        if user.sso_subject and user.sso_subject != identity.did:
            raise SSOLinkConflict(
                "This account is already linked to a different home.space identity. "
                "Unlink it first."
            )

        user.sso_issuer = identity.issuer
        user.sso_subject = identity.did
        user.sso_holder_name = identity.holder_name
        user.sso_roles = list(identity.roles)
        if user.sso_linked_at is None:
            user.sso_linked_at = datetime.now(UTC)

        updated = await self._users.update(user)
        logger.info("Linked home.space identity %s to beats account %s", identity.did, user_id)
        return updated

    # ------------------------------------------------------------------
    # Detach
    # ------------------------------------------------------------------

    async def unlink(self, user_id: str, passkey_count: int) -> User:
        """Detach the linked identity.

        `passkey_count` is the number of beats passkeys the account holds.
        Refusing at zero mirrors the guard already in
        `WebAuthnManager.delete_credential` — an account whose only way in
        is the thing being removed must not be able to remove it.
        """
        user = await self._users.get_by_id(user_id)
        if user is None:
            raise SSOAccountError("User not found")
        if not user.sso_subject:
            raise SSONotLinked("This account has no linked home.space identity.")
        if passkey_count < 1:
            raise SSOLastCredential(
                "Unlinking would leave this account with no way to sign in. "
                "Register a passkey first."
            )

        user.sso_issuer = None
        user.sso_subject = None
        user.sso_holder_name = None
        user.sso_roles = []
        user.sso_linked_at = None
        # `sso_provisioned` is left as-is on purpose: it is a fact about how
        # the account came into being, and stays true after the link is cut.

        updated = await self._users.update(user)
        logger.info("Unlinked home.space identity from beats account %s", user_id)
        return updated

    # ------------------------------------------------------------------

    async def _refresh_claims(self, user: User, identity: HomeIdentity) -> User:
        """Re-sync issuer-owned attributes on each sign-in.

        The issuer is authoritative for the holder name and roles: renaming a
        device in `/devices`, or re-issuing its credential with a different
        role, should be reflected here on the next login rather than frozen
        at whatever they were when the link was made.

        The user's own `display_name` is only overwritten for accounts that
        SSO provisioned. On a linked account it is the user's own, set during
        beats registration, and the issuer has no claim on it.
        """
        changed = False
        if user.sso_holder_name != identity.holder_name:
            user.sso_holder_name = identity.holder_name
            if user.sso_provisioned:
                user.display_name = identity.holder_name
            changed = True
        if list(user.sso_roles) != list(identity.roles):
            user.sso_roles = list(identity.roles)
            changed = True

        if not changed:
            return user
        return await self._users.update(user)
