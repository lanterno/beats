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

from datetime import UTC, datetime
from typing import Any

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
    control, keyed on its name, written by `control.set` and `control.clear`
    and nothing else. No `user_id` — it is the platform's, not anyone's — so
    erasure's sweep never sees it."""

    def __init__(self, db: AsyncDatabase):
        self._col = db[CONTROLS_COLLECTION]

    async def get(self, name: str) -> dict[str, Any] | None:
        doc = await self._col.find_one({"name": name}, projection={"_id": False})
        return doc

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
    ) -> dict[str, Any]:
        doc = {
            "name": name,
            "until": until.isoformat() if until is not None else None,
            "value": value,
            "reason": reason,
            "set_by": set_by,
            "set_at": datetime.now(UTC).isoformat(),
        }
        await self._col.update_one({"name": name}, {"$set": doc}, upsert=True)
        return doc

    async def clear(self, name: str) -> bool:
        result = await self._col.delete_one({"name": name})
        return result.deleted_count > 0


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
