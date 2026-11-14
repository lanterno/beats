"""`database_sizes` — the database's size, kept once a UTC day (docs/backoffice.md
§ The pages, Capacity).

The one series the control plane stores, because nothing else keeps a size
over time and a pace needs two. Sizes and counts only — each collection's
name, documents, size on disk, uncompressed size and indexes, the
`$collStats` figures Capacity already reads live — so nothing here is
anyone's content, and no row names an account.

The job runner (`beats.operator.jobs`) keeps today's after it has drained
the queue, on every 15-minute tick, so the first run of a UTC day keeps it
and the rest find it there. The document's id is its day, and the write is
an upsert that only sets on insert, so two runs that overlap keep one size,
never two and never a later one over the first. Kept `SIZE_KEEP_DAYS`, by
the TTL index on `expires_at` that `ensure_indexes` builds — the public API
holds the index grant; the job's database user creates none.
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import DuplicateKeyError

from beats.operator.reads import SIZE_KEEP_DAYS, SizeDay

COLLECTION = "database_sizes"


@dataclass(frozen=True)
class CollectionStats:
    """One collection's `$collStats` storage figures: on disk (compressed),
    uncompressed — what Atlas's free tier measures its limit against, with
    the indexes — and the indexes."""

    name: str
    documents: int
    storage_bytes: int
    data_bytes: int
    index_bytes: int


async def collection_stats(db: AsyncDatabase) -> list[CollectionStats]:
    """Every collection's figures, by name. Needs `listCollections` and
    `collStats` on the database, and nothing that reads a document."""
    out = []
    for name in sorted(await db.list_collection_names()):
        cursor = await db[name].aggregate([{"$collStats": {"storageStats": {}}}])
        rows = await cursor.to_list(1)
        stats = rows[0].get("storageStats", {}) if rows else {}
        out.append(
            CollectionStats(
                name=name,
                documents=int(stats.get("count", 0)),
                storage_bytes=int(stats.get("storageSize", 0)),
                data_bytes=int(stats.get("size", 0)),
                index_bytes=int(stats.get("totalIndexSize", 0)),
            )
        )
    return out


class MongoDatabaseSizes:
    def __init__(self, db: AsyncDatabase):
        self._db = db
        self._col = db[COLLECTION]

    async def keep(self, now: datetime) -> bool:
        """Keep the size for `now`'s UTC day unless it is kept already; True
        when this call kept it. Reading the figures is skipped when the day
        is there, so the day's other 95 ticks cost one indexed lookup."""
        day = now.astimezone(UTC).date().isoformat()
        if await self._col.find_one({"_id": day}, projection={"_id": 1}) is not None:
            return False
        stats = await collection_stats(self._db)
        try:
            result = await self._col.update_one(
                {"_id": day},
                {
                    "$setOnInsert": {
                        "taken_at": now,
                        "expires_at": now + timedelta(days=SIZE_KEEP_DAYS),
                        "collections": [
                            {
                                "name": s.name,
                                "documents": s.documents,
                                "storage_bytes": s.storage_bytes,
                                "data_bytes": s.data_bytes,
                                "index_bytes": s.index_bytes,
                            }
                            for s in stats
                        ],
                    }
                },
                upsert=True,
            )
        except DuplicateKeyError:
            # Another run inserted the day between the lookup and this write.
            return False
        return result.upserted_id is not None

    async def series(self) -> list[SizeDay]:
        """Every day kept, oldest first: the collections' sizes on disk
        added up, the way the page adds up today's."""
        cursor = await self._col.aggregate(
            [
                {"$sort": {"_id": -1}},
                {"$limit": SIZE_KEEP_DAYS},
                {"$project": {"storage_bytes": {"$sum": "$collections.storage_bytes"}}},
                {"$sort": {"_id": 1}},
            ]
        )
        return [
            SizeDay(day=date.fromisoformat(doc["_id"]), storage_bytes=int(doc["storage_bytes"]))
            async for doc in cursor
        ]

    async def on(self, day: date) -> dict[str, int]:
        """Each collection's size on disk that day, by name; empty for a day
        not kept."""
        doc = await self._col.find_one(
            {"_id": day.isoformat()},
            projection={"collections.name": 1, "collections.storage_bytes": 1},
        )
        if doc is None:
            return {}
        return {c["name"]: int(c["storage_bytes"]) for c in doc.get("collections", [])}
