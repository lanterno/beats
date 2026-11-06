"""Persistence for a day job's absences and balance adjustments.

Split out of `repositories.py` at the ceiling in roadmaps/file-sizes.md.
Their only readers are the week, the ledger and the vacation year
(docs/work-contracts.md).
"""

from datetime import date
from typing import Protocol

from bson import ObjectId
from bson.errors import InvalidId
from pymongo import ReturnDocument

from beats.domain.models import (
    Absence,
    BalanceAdjustment,
)
from beats.infrastructure.repositories import (
    MongoStore,
)


class AbsenceRepository(Protocol):
    async def list_by_project(self, project_id: str, start: date, end: date) -> list[Absence]: ...
    async def list_all(self) -> list[Absence]: ...
    async def upsert(self, absence: Absence) -> Absence: ...
    async def delete(self, project_id: str, absence_id: str) -> bool: ...
    async def day_of(self, project_id: str, absence_id: str) -> date | None: ...
    async def list_for_organisation(self, organisation_id: str) -> list[Absence]: ...
    async def stamp_organisation(
        self, project_id: str, organisation_id: str, since: date
    ) -> int: ...


class MongoAbsenceRepository(MongoStore[Absence], AbsenceRepository):
    model = Absence

    async def list_by_project(self, project_id: str, start: date, end: date) -> list[Absence]:
        return await self._find_many(
            {
                "project_id": project_id,
                "date": {"$gte": start.isoformat(), "$lte": end.isoformat()},
            },
            sort=("date", 1),
        )

    async def list_all(self) -> list[Absence]:
        # Every project's, for the full export: an absence outlives a kind
        # change away from day_job, and a backup keeps it all the same.
        return await self._find_many(sort=("date", 1))

    async def list_for_organisation(self, organisation_id: str) -> list[Absence]:
        """The caller's own absences stamped as one organisation's record, for
        the archive they keep after leaving. User-scoped like every read here."""
        return await self._find_many({"organisation_id": organisation_id}, sort=("date", 1))

    async def stamp_organisation(self, project_id: str, organisation_id: str, since: date) -> int:
        """As `MongoBeatRepository.stamp_organisation`: the caller's absences
        on the project from `since` on become the organisation's record."""
        result = await self.collection.update_many(
            self._q({"project_id": project_id, "date": {"$gte": since.isoformat()}}),
            {"$set": {"organisation_id": organisation_id}},
        )
        return result.modified_count

    async def upsert(self, absence: Absence) -> Absence:
        # A replace rather than the shared `$set` merge: the document IS the
        # absence, and posting a sick day over a vacation that carried a note
        # must not keep the note. The (user, project, date) unique index makes
        # this filter the document's identity.
        data = self._dump(absence)
        data.pop("_id", None)
        result = await self.collection.find_one_and_replace(
            self._q({"project_id": data["project_id"], "date": data["date"]}),
            data,
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        if result is None:
            raise RuntimeError("upsert of Absence returned no document")
        return self._load(result)

    async def delete(self, project_id: str, absence_id: str) -> bool:
        # Scoped to the project in the URL as well as the user, so a 404 means
        # "not on this project". A malformed id is "no such absence", the same
        # answer as an unknown one — the route turns False into a 404 either way.
        try:
            oid = ObjectId(absence_id)
        except InvalidId:
            return False
        return await self._delete_one({"_id": oid, "project_id": project_id})

    async def day_of(self, project_id: str, absence_id: str) -> date | None:
        """The day a stored absence falls on, which a delete reads before it
        deletes: a day inside an approved month is refused, and the date is
        all the check needs. None when there is no such absence here."""
        try:
            oid = ObjectId(absence_id)
        except InvalidId:
            return None
        doc = await self.collection.find_one(
            self._q({"_id": oid, "project_id": project_id}), {"date": 1}
        )
        return date.fromisoformat(doc["date"]) if doc else None


class AdjustmentRepository(Protocol):
    async def list_by_project(
        self, project_id: str, start: date, end: date
    ) -> list[BalanceAdjustment]: ...
    async def list_all(self) -> list[BalanceAdjustment]: ...
    async def upsert(self, adjustment: BalanceAdjustment) -> BalanceAdjustment: ...
    async def delete(self, project_id: str, adjustment_id: str) -> bool: ...
    async def day_of(self, project_id: str, adjustment_id: str) -> date | None: ...
    async def earliest(self, project_id: str, on_or_after: date) -> date | None: ...
    async def delete_by_project(self, project_id: str) -> int: ...


class MongoAdjustmentRepository(MongoStore[BalanceAdjustment], AdjustmentRepository):
    model = BalanceAdjustment

    async def list_by_project(
        self, project_id: str, start: date, end: date
    ) -> list[BalanceAdjustment]:
        return await self._find_many(
            {
                "project_id": project_id,
                "date": {"$gte": start.isoformat(), "$lte": end.isoformat()},
            },
            sort=("date", 1),
        )

    async def list_all(self) -> list[BalanceAdjustment]:
        # Every project's, for the full export.
        return await self._find_many(sort=("date", 1))

    async def upsert(self, adjustment: BalanceAdjustment) -> BalanceAdjustment:
        # A replace, as an absence's: the document IS the adjustment, so a
        # reset posted over a payout that carried a note must not keep the
        # note. The (user, project, date) unique index makes this filter the
        # document's identity, and the id survives the replace.
        data = self._dump(adjustment)
        data.pop("_id", None)
        result = await self.collection.find_one_and_replace(
            self._q({"project_id": data["project_id"], "date": data["date"]}),
            data,
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        if result is None:
            raise RuntimeError("upsert of BalanceAdjustment returned no document")
        return self._load(result)

    async def delete(self, project_id: str, adjustment_id: str) -> bool:
        # Scoped to the project in the URL as well as the user; a malformed
        # id is "no such adjustment", as it is for an absence.
        try:
            oid = ObjectId(adjustment_id)
        except InvalidId:
            return False
        return await self._delete_one({"_id": oid, "project_id": project_id})

    async def day_of(self, project_id: str, adjustment_id: str) -> date | None:
        """The day a stored adjustment falls on, read before a delete for
        the approved-month check, as an absence's is."""
        try:
            oid = ObjectId(adjustment_id)
        except InvalidId:
            return None
        doc = await self.collection.find_one(
            self._q({"_id": oid, "project_id": project_id}), {"date": 1}
        )
        return date.fromisoformat(doc["date"]) if doc else None

    async def earliest(self, project_id: str, on_or_after: date) -> date | None:
        # ISO dates sort as strings, so the first by date is the earliest.
        doc = await self.collection.find_one(
            self._q({"project_id": project_id, "date": {"$gte": on_or_after.isoformat()}}),
            sort=[("date", 1)],
        )
        return None if doc is None else date.fromisoformat(doc["date"])

    async def delete_by_project(self, project_id: str) -> int:
        result = await self.collection.delete_many(self._q({"project_id": project_id}))
        return result.deleted_count
