"""A short-lived cache of whether a device token is still allowed.

The wall clock polls `/api/device/status` every ten seconds and the daemon
posts flow windows continuously, so the auth middleware was making a Mongo
round-trip on every one of those requests purely to ask "is this device still
registered?".

Caching that is safe because it does not weaken the token check: the signature
and expiry are still verified on every request, and this only skips re-reading
the revocation flag. Revoking through the API drops the entry outright, so a
revoked device is refused immediately rather than after the TTL — the TTL only
bounds staleness from a revocation made directly in the database.

Process-local by design. A second API process keeps its own copy, which is
sound for a bound this short.
"""

import time

TTL_SECONDS = 30.0

_entries: dict[str, tuple[float, bool]] = {}


def get(device_id: str) -> bool | None:
    """Cached verdict for a device, or None when unknown or stale."""
    entry = _entries.get(device_id)
    if entry is None:
        return None
    expires_at, allowed = entry
    if expires_at <= time.monotonic():
        _entries.pop(device_id, None)
        return None
    return allowed


def remember(device_id: str, *, allowed: bool) -> None:
    _entries[device_id] = (time.monotonic() + TTL_SECONDS, allowed)


def forget(device_id: str) -> None:
    """Drop a device's entry so the next request re-reads it."""
    _entries.pop(device_id, None)


def clear() -> None:
    """Empty the cache. Used by tests."""
    _entries.clear()
