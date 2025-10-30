from datetime import UTC, datetime

from pydantic import BaseModel, Field


class RecordTimeValidator(BaseModel):
    """Used to validate a datetime input for start and stop time endpoints"""
    time: datetime = Field(default_factory=lambda: datetime.now(UTC))