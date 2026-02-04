"""Domain utilities - shared helper functions."""

from datetime import UTC, datetime


def normalize_tz(dt: datetime) -> datetime:
    """Ensure datetime is timezone-aware (UTC if naive).

    Args:
        dt: A datetime that may or may not have timezone info.

    Returns:
        The same datetime with UTC timezone if it was naive,
        or unchanged if it already had timezone info.
    """
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt
