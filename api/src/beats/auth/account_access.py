"""A short-lived cache of an account's auth state.

Suspension and sign-out-everywhere are checked in the auth middleware on every
authenticated request, on the session branch and the device branch alike. Done
naively that is a Mongo round-trip per request; this caches the verdict the
way `device_access` caches a device's, with the same reasoning:

- the token's signature is still checked on every request; only the account
  lookup is skipped;
- the TTL bounds staleness. A suspension or sign-out written by a script or by
  the operator deployment — another process, whose write cannot drop entries
  here — takes effect within TTL_SECONDS on every instance;
- process-local by design. A second API process keeps its own copy, which is
  sound for a bound this short.

The entry also carries the day the account was last seen, so the middleware
can stamp `last_seen_on` at most once a day instead of on every request.
"""

import time
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime

from bson import ObjectId
from bson.errors import InvalidId
from pymongo.asynchronous.database import AsyncDatabase

TTL_SECONDS = 30.0


@dataclass(frozen=True)
class AccountAccess:
    """What the middleware needs to know about an account, and nothing else."""

    exists: bool
    suspended_at: datetime | None = None
    suspended_kind: str | None = None
    sessions_valid_after: datetime | None = None
    last_seen_on: date | None = None

    @property
    def suspended(self) -> bool:
        return self.suspended_at is not None


MISSING = AccountAccess(exists=False)

_entries: dict[str, tuple[float, AccountAccess]] = {}


def get(user_id: str) -> AccountAccess | None:
    """Cached state for an account, or None when unknown or stale."""
    entry = _entries.get(user_id)
    if entry is None:
        return None
    expires_at, access = entry
    if expires_at <= time.monotonic():
        _entries.pop(user_id, None)
        return None
    return access


def remember(user_id: str, access: AccountAccess) -> None:
    _entries[user_id] = (time.monotonic() + TTL_SECONDS, access)


def forget(user_id: str) -> None:
    """Drop an account's entry so the next request re-reads it."""
    _entries.pop(user_id, None)


def clear() -> None:
    """Empty the cache. Used by tests."""
    _entries.clear()


def note_seen(user_id: str, day: date) -> None:
    """Record in the cached entry that today's `last_seen_on` was written,
    so the entry's remaining TTL doesn't repeat the write."""
    entry = _entries.get(user_id)
    if entry is not None:
        expires_at, access = entry
        _entries[user_id] = (expires_at, replace(access, last_seen_on=day))


def _as_datetime(value: object) -> datetime | None:
    """Users are stored in the model's JSON form (ISO strings), but fixtures
    and older rows hold native BSON datetimes; read either."""
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, str):
        return datetime.fromisoformat(value)
    return None


def _as_date(value: object) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        return date.fromisoformat(value)
    return None


async def lookup(db: AsyncDatabase, user_id: str) -> AccountAccess:
    """Read an account's auth state. One projected read; no model built."""
    try:
        oid = ObjectId(user_id)
    except InvalidId:
        return MISSING
    doc = await db.users.find_one(
        {"_id": oid},
        projection=["suspended_at", "suspended_kind", "sessions_valid_after", "last_seen_on"],
    )
    if doc is None:
        return MISSING
    return AccountAccess(
        exists=True,
        suspended_at=_as_datetime(doc.get("suspended_at")),
        suspended_kind=doc.get("suspended_kind"),
        sessions_valid_after=_as_datetime(doc.get("sessions_valid_after")),
        last_seen_on=_as_date(doc.get("last_seen_on")),
    )


async def resolve(db: AsyncDatabase, user_id: str) -> AccountAccess:
    """The cached state, read and remembered on a miss."""
    access = get(user_id)
    if access is None:
        access = await lookup(db, user_id)
        remember(user_id, access)
    return access
