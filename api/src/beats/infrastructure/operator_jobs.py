"""`operator_jobs` — the queue the irreversible work waits in.

A queued job is just a serialised command: one abstraction, not two
mechanisms (docs/backoffice.md § Jobs). Like `operator_audit`, the
subject is `subject_id`, **never `user_id`** — erasure's sweep would
otherwise delete the erasure job's own entry mid-run.

Claiming is one `find_one_and_update`: an entry that is `queued` with its
`run_after` past, or `running` with a `claimed_at` over an hour old (a run
that died). Overlapping runs cannot take the same entry, and a re-run of a
claimed entry is the command's own problem to make safe — erasure tombstones
before it deletes, the purge is idempotent by decision 30, and a deletion's
hand-back takes the assignment with it (#414).
"""

from datetime import UTC, datetime, timedelta
from typing import Any

from bson import ObjectId
from bson.errors import InvalidId
from pymongo import ReturnDocument
from pymongo.asynchronous.database import AsyncDatabase

# A running claim older than this belonged to a run that died.
STALE_CLAIM = timedelta(hours=1)
# After this many attempts an entry is failed: it shows on the landing page,
# and the job logs at ERROR, which the Terraform alert sends to the owner.
MAX_ATTEMPTS = 3


def _public(doc: dict[str, Any]) -> dict[str, Any]:
    doc["id"] = str(doc.pop("_id"))
    return doc


class MongoOperatorJobs:
    def __init__(self, db: AsyncDatabase):
        self._col = db.operator_jobs

    async def enqueue(
        self,
        *,
        command: str,
        args: dict[str, Any],
        subject_kind: str,
        subject_id: str,
        queued_by_sub: str,
        queued_by_email: str,
        window: timedelta,
    ) -> dict[str, Any]:
        now = datetime.now(UTC)
        doc: dict[str, Any] = {
            "command": command,
            "args": args,
            "subject_kind": subject_kind,
            "subject_id": subject_id,
            "queued_by": {"sub": queued_by_sub, "email": queued_by_email},
            "queued_at": now.isoformat(),
            "run_after": (now + window).isoformat(),
            "state": "queued",
            "attempts": 0,
            "claimed_at": None,
            "finished_at": None,
            "error": None,
        }
        result = await self._col.insert_one(dict(doc))
        doc["_id"] = result.inserted_id
        return _public(doc)

    async def find_queued(self, command: str, subject_id: str) -> dict[str, Any] | None:
        """The queued entry for a command and subject, if one waits. What the
        runner's dedup and the unsuspend guard read: two queued erasures for
        one account would let a cancel lift the suspension while the other
        ran on schedule."""
        doc = await self._col.find_one(
            {"command": command, "subject_id": subject_id, "state": "queued"}
        )
        return _public(doc) if doc else None

    async def claim(self) -> dict[str, Any] | None:
        """One due entry, marked running — or None when nothing is due."""
        now = datetime.now(UTC)
        stale = (now - STALE_CLAIM).isoformat()
        doc = await self._col.find_one_and_update(
            {
                "$or": [
                    {"state": "queued", "run_after": {"$lte": now.isoformat()}},
                    {"state": "running", "claimed_at": {"$lt": stale}},
                ]
            },
            {
                "$set": {"state": "running", "claimed_at": now.isoformat()},
                "$inc": {"attempts": 1},
            },
            return_document=ReturnDocument.AFTER,
        )
        return _public(doc) if doc else None

    async def finish(self, job_id: str, *, error: str | None = None) -> None:
        """Done on success; on failure, back to queued until MAX_ATTEMPTS,
        then failed."""
        oid = ObjectId(job_id)
        now = datetime.now(UTC).isoformat()
        if error is None:
            await self._col.update_one(
                {"_id": oid}, {"$set": {"state": "done", "finished_at": now, "error": None}}
            )
            return
        doc = await self._col.find_one({"_id": oid})
        attempts = int(doc.get("attempts", 0)) if doc else MAX_ATTEMPTS
        state = "failed" if attempts >= MAX_ATTEMPTS else "queued"
        update: dict[str, Any] = {"state": state, "error": error}
        if state == "failed":
            update["finished_at"] = now
        await self._col.update_one({"_id": oid}, {"$set": update})

    async def cancel(self, job_id: str) -> dict[str, Any] | None:
        """A queued entry becomes cancelled; a running or finished one is
        left alone — second thoughts have a window, not a brake."""
        try:
            oid = ObjectId(job_id)
        except InvalidId:
            return None
        doc = await self._col.find_one_and_update(
            {"_id": oid, "state": "queued"},
            {"$set": {"state": "cancelled", "finished_at": datetime.now(UTC).isoformat()}},
            return_document=ReturnDocument.AFTER,
        )
        return _public(doc) if doc else None

    async def get(self, job_id: str) -> dict[str, Any] | None:
        try:
            oid = ObjectId(job_id)
        except InvalidId:
            return None
        doc = await self._col.find_one({"_id": oid})
        return _public(doc) if doc else None
