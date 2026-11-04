"""The job runner: `python -m beats.operator.jobs`, on Cloud Scheduler's tick.

It finds nothing due and exits on almost every run, which on Cloud Run Jobs
costs next to nothing. It is not an app in a costume: no `OperatorSettings`
(which refuses to load unless exactly one of the IAP audience and the local
stand-in is set, and a job has neither), no allowlist, no `JWT_SECRET` — it
reads settings of its own, the DSN and the database's name, and nothing else.

Each claimed entry is run through the same runner the request path uses,
with `from_queue=True`: the role and the typed confirmation were checked
once, by the request that queued it, and the audit is written under the
operator the command carries. A command's rules are checked when it runs,
not when it was queued — a deletion whose organisation has been given an
owner while it waited is refused then, which this runner records as the
job's failure.
"""

import asyncio
import logging
import os
import sys

from pymongo import AsyncMongoClient
from pymongo.asynchronous.database import AsyncDatabase

from beats.infrastructure.operator_jobs import MongoOperatorJobs
from beats.operator.context import build_command_context
from beats.operator.runner import run_command
from beats.operator.settings import OperatorIdentity

logger = logging.getLogger(__name__)


async def run_due_jobs(db: AsyncDatabase) -> int:
    """Claim and run entries until nothing is due; the count handled."""
    jobs = MongoOperatorJobs(db)
    handled = 0
    while (job := await jobs.claim()) is not None:
        handled += 1
        queued_by = job.get("queued_by") or {}
        operator = OperatorIdentity(
            sub=str(queued_by.get("sub", "")) or "unknown",
            email=str(queued_by.get("email", "")),
            role="operator",
        )
        try:
            ctx = build_command_context(db, operator)
            await run_command(ctx, job["command"], job["args"], None, from_queue=True)
            await jobs.finish(job["id"])
            logger.info("operator job %s (%s) done", job["id"], job["command"])
        except Exception as e:  # noqa: BLE001 — a job's failure is data, not a crash
            # ERROR is what the log-based alert in terraform/alerts.tf
            # watches: a silently failing erasure must page somebody.
            logger.error("operator job %s (%s) failed: %s", job["id"], job["command"], e)
            await jobs.finish(job["id"], error=str(e))
    return handled


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    dsn = os.environ.get("OPERATOR_JOBS_DB_DSN", "")
    db_name = os.environ.get("OPERATOR_JOBS_DB_NAME", "")
    if not dsn or not db_name:
        print(
            "OPERATOR_JOBS_DB_DSN and OPERATOR_JOBS_DB_NAME are required — the job's own "
            "credential, never the API's",
            file=sys.stderr,
        )
        return 2

    async def run() -> int:
        client: AsyncMongoClient = AsyncMongoClient(dsn)
        try:
            return await run_due_jobs(client[db_name])
        finally:
            await client.close()

    handled = asyncio.run(run())
    print(f"handled {handled} job(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
