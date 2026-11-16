"""Who uses the platform and how much is logged — the pipelines behind the
back office's People and Hours pages (docs/backoffice.md § The pages).

Carved out of `operator_reads.py` at the size ceiling; `MongoOperatorReads`
delegates here. The same line holds: every figure is the left-hand column —
an address, dates, states and counts per account; hours, sessions and
accounts per UTC day, week or month across everyone — and the wall test in
`test_operator.py` reads both pages with a sentinel planted on the right.

A pipeline per request, as everywhere in the control plane: `users` and
`projects` are small, and `timeLogs` is grouped once per read over an index
on `start`.
"""

from datetime import UTC, date, datetime, timedelta

from pymongo.asynchronous.database import AsyncDatabase

from beats.operator.reads import (
    HOURS_MAX_PERIODS,
    AccountRow,
    AccountsReport,
    HoursBucket,
    HoursReport,
    HoursUnit,
)

# How `$dateTrunc` names a bucket: the first day of it. A week starts on
# Monday, as the app's weeks do.
_BUCKET = {
    "day": {"unit": "day"},
    "week": {"unit": "week", "startOfWeek": "monday"},
    "month": {"unit": "month"},
}


def _as_datetime(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None
    return None


def _as_date(value: object) -> date | None:
    dt = _as_datetime(value)
    return dt.date() if dt is not None else None


def bucket_start(day: date, unit: HoursUnit) -> date:
    """The first day of the bucket `day` is in: the day itself, its Monday,
    or the first of its month."""
    if unit == "week":
        return day - timedelta(days=day.weekday())
    if unit == "month":
        return day.replace(day=1)
    return day


def periods_back(day: date, unit: HoursUnit, periods: int) -> date:
    """The first day of the bucket `periods - 1` buckets before the one
    `day` is in, so a read of `periods` buckets ends on today's."""
    start = bucket_start(day, unit)
    if unit == "day":
        return start - timedelta(days=periods - 1)
    if unit == "week":
        return start - timedelta(weeks=periods - 1)
    months = start.year * 12 + start.month - 1 - (periods - 1)
    return date(months // 12, months % 12 + 1, 1)


async def _counts_by_user(db: AsyncDatabase, collection: str) -> dict[str, int]:
    pipeline = [
        {"$match": {"user_id": {"$type": "string"}}},
        {"$group": {"_id": "$user_id", "n": {"$sum": 1}}},
    ]
    cursor = await db[collection].aggregate(pipeline)
    return {d["_id"]: int(d["n"]) async for d in cursor}


async def accounts(db: AsyncDatabase, limit: int) -> AccountsReport:
    """Every account, newest first, with its project and session counts.

    `created_at` is an ISO string on rows the repository wrote and a BSON
    date on older ones, so the sort and the counts are done here rather
    than in a pipeline that would choke on the mixture."""
    now = datetime.now(UTC)
    today = now.date()
    projects = await _counts_by_user(db, "projects")
    sessions = await _counts_by_user(db, "timeLogs")
    rows: list[AccountRow] = []
    cursor = db.users.find({}, projection=["email", "created_at", "last_seen_on", "suspended_at"])
    async for doc in cursor:
        uid = str(doc["_id"])
        rows.append(
            AccountRow(
                id=uid,
                email=doc.get("email", ""),
                created_at=_as_datetime(doc.get("created_at")),
                last_seen_on=_as_date(doc.get("last_seen_on")),
                suspended=doc.get("suspended_at") is not None,
                projects=projects.get(uid, 0),
                sessions=sessions.get(uid, 0),
            )
        )
    rows.sort(key=lambda r: r.created_at or datetime.min.replace(tzinfo=UTC), reverse=True)
    month_ago = now - timedelta(days=30)
    return AccountsReport(
        total=len(rows),
        created_last_30d=sum(1 for r in rows if r.created_at and r.created_at >= month_ago),
        seen_last_7d=sum(
            1 for r in rows if r.last_seen_on and r.last_seen_on >= today - timedelta(days=7)
        ),
        seen_last_30d=sum(
            1 for r in rows if r.last_seen_on and r.last_seen_on >= today - timedelta(days=30)
        ),
        suspended=sum(1 for r in rows if r.suspended),
        rows=rows[:limit],
    )


# Finished sessions with BSON dates on both ends: a running timer is not yet
# hours, and a row stored otherwise would stop `$dateTrunc`.
_FINISHED = {"start": {"$type": "date"}, "end": {"$type": "date"}}
_HOURS = {"$divide": [{"$subtract": ["$end", "$start"]}, 3_600_000]}


async def _totals(db: AsyncDatabase, match: dict) -> tuple[float, int, int]:
    pipeline = [
        {"$match": {**_FINISHED, **match}},
        {
            "$group": {
                "_id": None,
                "hours": {"$sum": _HOURS},
                "sessions": {"$sum": 1},
                "accounts": {"$addToSet": "$user_id"},
            }
        },
    ]
    cursor = await db.timeLogs.aggregate(pipeline)
    async for d in cursor:
        return round(float(d["hours"]), 2), int(d["sessions"]), len(d["accounts"])
    return 0.0, 0, 0


async def hours(db: AsyncDatabase, unit: HoursUnit, periods: int) -> HoursReport:
    """Hours logged all told and in `periods` buckets of `unit` ending on
    today's, UTC, by the day each session started on."""
    periods = max(1, min(periods, HOURS_MAX_PERIODS[unit]))
    now = datetime.now(UTC)
    since = periods_back(now.date(), unit, periods)
    since_dt = datetime(since.year, since.month, since.day, tzinfo=UTC)
    month_start = datetime(now.year, now.month, 1, tzinfo=UTC)

    total_hours, total_sessions, accounts_ever = await _totals(db, {})
    this_month_hours, _, _ = await _totals(db, {"start": {"$gte": month_start}})
    _, _, accounts_recent = await _totals(db, {"start": {"$gte": now - timedelta(days=30)}})

    pipeline = [
        {"$match": {**_FINISHED, "start": {"$gte": since_dt}}},
        {
            "$group": {
                "_id": {"$dateTrunc": {"date": "$start", **_BUCKET[unit]}},
                "hours": {"$sum": _HOURS},
                "sessions": {"$sum": 1},
                "accounts": {"$addToSet": "$user_id"},
            }
        },
        {"$sort": {"_id": 1}},
    ]
    cursor = await db.timeLogs.aggregate(pipeline)
    buckets = [
        HoursBucket(
            period=d["_id"].date().isoformat(),
            hours=round(float(d["hours"]), 2),
            sessions=int(d["sessions"]),
            accounts=len(d["accounts"]),
        )
        async for d in cursor
    ]
    return HoursReport(
        unit=unit,
        periods=periods,
        since=since.isoformat(),
        total_hours=total_hours,
        total_sessions=total_sessions,
        accounts_ever=accounts_ever,
        accounts_last_30d=accounts_recent,
        this_month_hours=this_month_hours,
        buckets=buckets,
    )
