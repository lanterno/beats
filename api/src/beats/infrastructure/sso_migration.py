"""Startup pass: retire the home.space SSO links.

Before OpenID Connect, single sign-on meant one provider — the home.space
identity service — and a user document held at most one link to it, in flat
`sso_issuer` / `sso_subject` / `sso_holder_name` / `sso_roles` /
`sso_linked_at` fields, unique-indexed as a pair. Nothing reads those fields
any more, and the issuer they point at is no longer one beats can verify, so
this pass unsets them and drops their index. `sso_provisioned` stays: it is
still true of how the account was made, and `identities` replaces the rest.

An account that came in through home.space and never registered a passkey is
left with no way to sign in. The pass can't give it one; it names each such
account in the log, so the operator knows whom to help back in (sign in once
more on a build before this one and register a passkey, or link a provider).

Idempotent: it acts on documents that still have `sso_subject`, and a second
boot finds none.
"""

import logging

from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import OperationFailure

logger = logging.getLogger(__name__)

LEGACY_FIELDS = ("sso_issuer", "sso_subject", "sso_holder_name", "sso_roles", "sso_linked_at")
LEGACY_INDEX = "sso_issuer_1_sso_subject_1"


async def retire_home_sso_links(db: AsyncDatabase) -> list[str]:
    """Unset the legacy link fields; return the ids of accounts left with no way in."""
    stranded: list[str] = []
    async for doc in db.users.find({"sso_subject": {"$exists": True}}, {"identities": 1}):
        has_passkey = await db.credentials.count_documents({"user_id": str(doc["_id"])}, limit=1)
        if not has_passkey and not doc.get("identities"):
            stranded.append(str(doc["_id"]))

    result = await db.users.update_many(
        {"sso_subject": {"$exists": True}},
        {"$unset": dict.fromkeys(LEGACY_FIELDS, "")},
    )
    if result.modified_count:
        logger.info("Retired %d home.space SSO link(s)", result.modified_count)
    for user_id in stranded:
        logger.warning(
            "User %s signed in only through home.space SSO and has no passkey: "
            "it has no way to sign in now",
            user_id,
        )

    try:
        await db.users.drop_index(LEGACY_INDEX)
        logger.info("Dropped index users.%s", LEGACY_INDEX)
    except OperationFailure:
        pass  # already gone (or never built)
    return stranded
