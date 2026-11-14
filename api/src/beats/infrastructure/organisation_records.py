"""The organisation's read of its working-time record — the wall, in SQL terms.

Split out of `organisations.py` at the size ceiling (CLAUDE.md § Conventions). The
two classes were already independent: the store writes the organisation's own
collections, this one reads beats and absences by the organisation's stamp and
touches no other collection (docs/organisations.md, rule 3).
"""

from collections.abc import Iterable
from datetime import UTC, date, datetime
from typing import Any

from pydantic import BaseModel
from pymongo.asynchronous.collection import AsyncCollection
from pymongo.asynchronous.database import AsyncDatabase

from beats.domain.models import (
    Absence,
    BalanceAdjustment,
    Beat,
    MemberTotals,
)
from beats.domain.utils import normalize_tz
from beats.infrastructure.repositories import serialize_from_document


def _load[T: BaseModel](model: type[T], doc: dict[str, Any]) -> T:
    return model(**serialize_from_document(doc))


class MongoOrganisationRecords:
    """The organisation's read of its working-time record, and the only one.

    Every query names the organisation's stamp (`organisation_id` on the
    beat or the absence) and the project ids the organisation owns, and
    where the reader is one member looking at their own slice, their
    `user_id` as well. Only finished beats: a running one is nobody's
    record yet, and the read says nothing about now (decision 2). The
    adjustments are read by project and member, since they carry no stamp:
    they are read to compute the balance the member's contract already
    shows the organisation, and for nothing else.
    """

    def __init__(self, db: AsyncDatabase):
        self.beats: AsyncCollection = db.timeLogs
        self.absences: AsyncCollection = db.absences
        self.adjustments: AsyncCollection = db.balance_adjustments

    def _beats_query(
        self, organisation_id: str, project_ids: Iterable[str], user_id: str | None
    ) -> dict[str, Any]:
        query: dict[str, Any] = {
            "organisation_id": organisation_id,
            "project_id": {"$in": sorted(project_ids)},
            "end": {"$ne": None},
        }
        if user_id is not None:
            query["user_id"] = user_id
        return query

    async def beats_between(
        self,
        organisation_id: str,
        project_ids: Iterable[str],
        start: datetime,
        end: datetime,
        *,
        user_id: str | None = None,
    ) -> list[tuple[str, Beat]]:
        """Finished beats started in [start, end) on these projects, each with
        the member whose it is."""
        query = self._beats_query(organisation_id, project_ids, user_id)
        if not query["project_id"]["$in"]:
            return []
        query["start"] = {"$gte": start, "$lt": end}
        docs = await self.beats.find(query).sort("start", 1).to_list(length=None)
        return [(doc["user_id"], _load(Beat, doc)) for doc in docs]

    async def beats_of_member(
        self, organisation_id: str, project_id: str, user_id: str
    ) -> list[Beat]:
        """Every finished beat of one member on one project — what a balance
        is computed from."""
        query = self._beats_query(organisation_id, [project_id], user_id)
        docs = await self.beats.find(query).sort("start", 1).to_list(length=None)
        return [_load(Beat, doc) for doc in docs]

    async def running_in(
        self, organisation_id: str, project_id: str, user_id: str, start: datetime, end: datetime
    ) -> bool:
        """Whether a stamped timer is still running in [start, end) — what
        makes an approval wait: a running beat is in no figure yet, and
        freezing around it would guarantee a drift."""
        doc = await self.beats.find_one(
            {
                "organisation_id": organisation_id,
                "project_id": project_id,
                "user_id": user_id,
                "end": None,
                "start": {"$gte": start, "$lt": end},
            },
            {"_id": 1},
        )
        return doc is not None

    async def has_unshared(
        self,
        organisation_id: str,
        project_id: str,
        user_id: str,
        *,
        private_before: datetime | None,
        private_before_day: date | None,
        expired_before: date,
    ) -> bool:
        """Whether the member has an entry or an absence on the project that
        is not this organisation's record — one dated before the day they
        chose to share from. Read to withhold a balance, never to show
        anything: the answer is a yes or a no.

        A row the retention purge unstamped is not one of those. The purge
        takes the stamp off a living member's rows older than the cutoff
        (decision 30) and leaves the rows theirs; asking only whether an
        unstamped row exists then answers yes for every long-standing
        member, and the organisation loses the balance on its own record
        for good (#409). So a row dated in the shared window and already
        past the cutoff is read as expired, not as withheld: it was shared
        once. Every row a purge unstamped is older than the cutoff it ran
        with, which is never later than today's.

        The window opens at `private_before` — what a connect kept back —
        and at the beginning of time where a connect kept back nothing.
        """
        unstamped: dict[str, Any] = {"organisation_id": {"$ne": organisation_id}}
        expired_at = datetime(
            expired_before.year, expired_before.month, expired_before.day, tzinfo=UTC
        )
        kept_back_or_expired: list[dict[str, Any]] = [{"start": {"$gte": expired_at}}]
        if private_before is not None:
            kept_back_or_expired.append({"start": {"$lt": normalize_tz(private_before)}})
        beat = await self.beats.find_one(
            {
                "project_id": project_id,
                "user_id": user_id,
                **unstamped,
                "$or": kept_back_or_expired,
            },
            {"_id": 1},
        )
        if beat is not None:
            return True
        by_day: list[dict[str, Any]] = [{"date": {"$gte": expired_before.isoformat()}}]
        if private_before_day is not None:
            by_day.append({"date": {"$lt": private_before_day.isoformat()}})
        absence = await self.absences.find_one(
            {"project_id": project_id, "user_id": user_id, **unstamped, "$or": by_day},
            {"_id": 1},
        )
        return absence is not None

    async def totals(
        self, organisation_id: str, project_ids: Iterable[str], *, user_id: str | None = None
    ) -> dict[tuple[str, str], MemberTotals]:
        """All-time totals per (project, member): how many entries, how many
        hours, the first start and the last end."""
        query = self._beats_query(organisation_id, project_ids, user_id)
        if not query["project_id"]["$in"]:
            return {}
        pipeline = [
            {"$match": query},
            {
                "$group": {
                    "_id": {"project_id": "$project_id", "user_id": "$user_id"},
                    "entries": {"$sum": 1},
                    "ms": {"$sum": {"$subtract": ["$end", "$start"]}},
                    "first": {"$min": "$start"},
                    "last": {"$max": "$end"},
                }
            },
        ]
        cursor = await self.beats.aggregate(pipeline)
        rows = await cursor.to_list(length=None)
        out: dict[tuple[str, str], MemberTotals] = {}
        for row in rows:
            key = (row["_id"]["project_id"], row["_id"]["user_id"])
            out[key] = MemberTotals(
                entries=int(row["entries"]),
                hours=round(float(row["ms"]) / 3_600_000, 2),
                first=row.get("first"),
                last=row.get("last"),
            )
        return out

    async def absences_between(
        self,
        organisation_id: str,
        project_ids: Iterable[str],
        start: date,
        end: date,
        *,
        user_id: str | None = None,
    ) -> list[tuple[str, Absence]]:
        ids = sorted(project_ids)
        if not ids:
            return []
        query: dict[str, Any] = {
            "organisation_id": organisation_id,
            "project_id": {"$in": ids},
            "date": {"$gte": start.isoformat(), "$lte": end.isoformat()},
        }
        if user_id is not None:
            query["user_id"] = user_id
        docs = await self.absences.find(query).sort("date", 1).to_list(length=None)
        return [(doc["user_id"], _load(Absence, doc)) for doc in docs]

    async def adjustments_of_member(
        self, project_id: str, user_id: str, start: date, end: date
    ) -> list[BalanceAdjustment]:
        docs = (
            await self.adjustments.find(
                {
                    "project_id": project_id,
                    "user_id": user_id,
                    "date": {"$gte": start.isoformat(), "$lte": end.isoformat()},
                }
            )
            .sort("date", 1)
            .to_list(length=None)
        )
        return [_load(BalanceAdjustment, doc) for doc in docs]
