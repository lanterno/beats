"""The operator's narrow writes and its own records.

`MongoAccountLimitsStore` writes the one user-keyed operator collection
(`account_limits`, keyed on `user_id` **deliberately** so erasure's sweep
takes it). `MongoOperatorAudit` writes `operator_audit`, which names its
subject as `subject_id` and **never `user_id`** — erasure's sweep runs
`delete_many({"user_id": …})` over every collection, and would otherwise
delete the record of the erasure itself. Ids, never addresses: an audit row
outlives the account it names, so after an erasure the page resolves to
"erased account" rather than keeping a name.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

from bson import ObjectId
from bson.errors import InvalidId
from pymongo import ReturnDocument
from pymongo.asynchronous.database import AsyncDatabase

from beats.domain.models import AccountLimits
from beats.platform_controls import COLLECTION as CONTROLS_COLLECTION


class MongoAccountLimitsStore:
    def __init__(self, db: AsyncDatabase):
        self._col = db.account_limits

    async def set(self, limits: AccountLimits) -> AccountLimits:
        data = limits.model_dump(mode="json", exclude={"id"})
        doc = await self._col.find_one_and_update(
            {"user_id": limits.user_id},
            {"$set": data},
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        # upsert=True with AFTER always returns the document.
        assert doc is not None
        doc["id"] = str(doc.pop("_id"))
        return AccountLimits(**doc)

    async def clear(self, user_id: str) -> bool:
        result = await self._col.delete_one({"user_id": user_id})
        return result.deleted_count > 0


class MongoPlatformControlsStore:
    """`platform_controls` (docs/backoffice.md § Controls): one document per
    control, keyed on its name — and for `signups`, one more per network
    slowed, keyed on the name and the network's key, so the control for
    everyone and any number of network ones stand side by side and each is
    set and cleared alone. Written by `control.set` and `control.clear` and
    nothing else. No `user_id` — it is the platform's, not anyone's — so
    erasure's sweep never sees it.

    A network's document carries `expires_at`, its `until` as a date, and
    the TTL index on it (`ensure_indexes`) takes the document within a
    minute of its end: the key is a hash of a network, and it is kept no
    longer than the control that needs it. The one for everyone has none,
    and an expired one stays, read as open, until it is cleared or set
    again."""

    def __init__(self, db: AsyncDatabase):
        self._col = db[CONTROLS_COLLECTION]

    @staticmethod
    def _key(name: str, network: str | None) -> dict[str, Any]:
        # `network: None` matches a document whose field is null or absent.
        return {"name": name, "network": network}

    async def get(self, name: str, network: str | None = None) -> dict[str, Any] | None:
        return await self._col.find_one(self._key(name, network), projection={"_id": False})

    async def all(self) -> list[dict[str, Any]]:
        return await self._col.find({}, projection={"_id": False}).to_list()

    async def set(
        self,
        name: str,
        *,
        until: datetime | None,
        value: int | None,
        reason: str | None,
        set_by: str,
        network: str | None = None,
    ) -> dict[str, Any]:
        doc = {
            "name": name,
            "until": until.isoformat() if until is not None else None,
            "value": value,
            "reason": reason,
            "set_by": set_by,
            "set_at": datetime.now(UTC).isoformat(),
            "network": network,
            "expires_at": until if network is not None else None,
        }
        await self._col.update_one(self._key(name, network), {"$set": doc}, upsert=True)
        return doc

    async def clear(self, name: str, network: str | None = None) -> bool:
        result = await self._col.delete_one(self._key(name, network))
        return result.deleted_count > 0


# A closed request is kept this long, then the TTL index takes it.
ERASURE_REQUEST_RETENTION_DAYS = 365


class MongoErasureRequests:
    """`erasure_requests` (docs/backoffice.md § The pages, Compliance): the
    day a request arrived by mail, a reference the operator chose, and the
    account it names as `subject_id` — never `user_id`, or erasure's own
    sweep would delete the record that the erasure was asked for, and
    **never an address**. A request from someone with no account is a
    reference alone."""

    def __init__(self, db: AsyncDatabase):
        self._col = db.erasure_requests

    @staticmethod
    def _out(doc: dict[str, Any]) -> dict[str, Any]:
        doc["id"] = str(doc.pop("_id"))
        return doc

    async def log(
        self,
        *,
        request_id: str,
        reference: str,
        received_on: str,
        subject_id: str | None,
        logged_by: str,
    ) -> dict[str, Any]:
        """`request_id` is made by the caller, before the write, so the
        audit of logging it can name a request with no account by its id."""
        doc = {
            "reference": reference,
            "received_on": received_on,
            "subject_id": subject_id,
            "logged_by": logged_by,
            "logged_at": datetime.now(UTC).isoformat(),
            "closed_at": None,
            "closed_reason": None,
            "closed_by": None,
            "expires_at": None,
        }
        await self._col.insert_one({"_id": ObjectId(request_id), **doc})
        return {**doc, "id": request_id}

    async def get(self, request_id: str) -> dict[str, Any] | None:
        try:
            oid = ObjectId(request_id)
        except InvalidId:
            return None
        doc = await self._col.find_one({"_id": oid})
        return self._out(doc) if doc else None

    async def close(self, request_id: str, *, reason: str, closed_by: str) -> dict[str, Any] | None:
        try:
            oid = ObjectId(request_id)
        except InvalidId:
            return None
        now = datetime.now(UTC)
        doc = await self._col.find_one_and_update(
            {"_id": oid, "closed_at": None},
            {
                "$set": {
                    "closed_at": now.isoformat(),
                    "closed_reason": reason,
                    "closed_by": closed_by,
                    # A BSON date: the TTL index reads nothing else.
                    "expires_at": now + timedelta(days=ERASURE_REQUEST_RETENTION_DAYS),
                }
            },
            return_document=ReturnDocument.AFTER,
        )
        return self._out(doc) if doc else None

    async def close_erased(self, subject_id: str) -> int:
        """Every open request naming this account, closed `erased` by the
        erasure itself as it finishes, so a request's year starts the day
        it was answered rather than never. `closed_by` stays empty: nobody
        closed it by hand, and the audit of `account.erase` names who queued
        it. Closes nothing on a re-run."""
        now = datetime.now(UTC)
        result = await self._col.update_many(
            {"subject_id": subject_id, "closed_at": None},
            {
                "$set": {
                    "closed_at": now.isoformat(),
                    "closed_reason": "erased",
                    "closed_by": None,
                    "expires_at": now + timedelta(days=ERASURE_REQUEST_RETENTION_DAYS),
                }
            },
        )
        return result.modified_count

    async def all(self) -> list[dict[str, Any]]:
        docs = await self._col.find({}).sort("received_on", -1).to_list()
        return [self._out(d) for d in docs]


class MongoOperatorAudit:
    """Append-only; editable by nobody; kept four years, the platform's
    default retention (the whole-platform purge removes older entries)."""

    def __init__(self, db: AsyncDatabase):
        self._col = db.operator_audit

    async def record(
        self,
        *,
        command: str,
        operator_sub: str,
        operator_email: str,
        subject_kind: str,
        subject_id: str,
        before: dict[str, Any],
        after: dict[str, Any],
    ) -> dict[str, Any]:
        entry = {
            "at": datetime.now(UTC).isoformat(),
            "command": command,
            # The operator's own identity, not a user's: it names who acted,
            # and no erasure sweep touches it (no user_id key).
            "operator_sub": operator_sub,
            "operator_email": operator_email,
            "subject_kind": subject_kind,
            "subject_id": subject_id,
            "before": before,
            "after": after,
        }
        result = await self._col.insert_one(dict(entry))
        entry["id"] = str(result.inserted_id)
        return entry
