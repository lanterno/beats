"""Domain utilities.

Datetime convention: all datetimes in the domain layer are UTC-aware.
MongoDB returns naive datetimes; the TzNormalizedModel base class adds
UTC tzinfo on construction. Code should use ``datetime.now(UTC)`` freely
and never need to call ``normalize_tz()`` manually — it's applied
automatically by the model validator.
"""

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from pydantic import BaseModel, model_validator


def local_dt(dt: datetime, tz: ZoneInfo) -> datetime:
    """Convert an aware-or-naive-UTC datetime to a localized datetime in ``tz``.

    Naive datetimes are treated as UTC (the DB stores UTC; Mongo may return
    naive datetimes). Use this for ``.hour`` slot math and cross-midnight
    splitting that must run in the user's local wall clock.

    Args:
        dt: A datetime, either UTC-aware or naive (interpreted as UTC).
        tz: The target timezone.

    Returns:
        The same instant expressed in ``tz``.
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(tz)


def local_date(dt: datetime, tz: ZoneInfo) -> date:
    """Convert an aware-or-naive-UTC datetime to the local calendar date in ``tz``.

    Naive datetimes are treated as UTC. Use this for day-bucketing so a
    late-evening session lands on the correct local calendar day.

    Args:
        dt: A datetime, either UTC-aware or naive (interpreted as UTC).
        tz: The target timezone.

    Returns:
        The local calendar date in ``tz``.
    """
    return local_dt(dt, tz).date()


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


class TzNormalizedModel(BaseModel):
    """Pydantic base model that normalizes all datetime fields to UTC-aware.

    Inherit from this instead of ``BaseModel`` for any domain model that
    may be constructed from MongoDB documents (which return naive datetimes).
    """

    @model_validator(mode="after")
    def _normalize_datetimes(self):
        for field_name in type(self).model_fields:
            value = getattr(self, field_name)
            if isinstance(value, datetime) and value.tzinfo is None:
                object.__setattr__(self, field_name, value.replace(tzinfo=UTC))
        return self
