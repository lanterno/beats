from datetime import datetime

from pydantic import BaseModel, Field


class RecordTimeValidator(BaseModel):
    """Used to validate a datetime input for start and stop time endpoints"""
    time: datetime = Field(default_factory=datetime.utcnow)