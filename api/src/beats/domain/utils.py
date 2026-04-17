"""Domain utilities.

Datetime convention: all datetimes in the domain layer are UTC-aware.
MongoDB returns naive datetimes; the TzNormalizedModel base class adds
UTC tzinfo on construction. Code should use ``datetime.now(UTC)`` freely
and never need to call ``normalize_tz()`` manually — it's applied
automatically by the model validator.
"""

from datetime import UTC, datetime

from pydantic import BaseModel, model_validator


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
