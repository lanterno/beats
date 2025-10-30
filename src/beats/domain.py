from datetime import UTC, date, datetime, timedelta
from typing import Any

import pymongo
from bson.objectid import ObjectId
from pydantic import BaseModel, ConfigDict, Field, computed_field
from pymongo.collection import Collection

from .db import db
from .exceptions import CanNotStopNonBeatingHeart, InconsistentEndTime, NoObjectMatched


class BaseRepository:
    table: Collection[Any] | None = None

    @classmethod
    def retrieve_by_id(cls, _id: str) -> dict[str, Any]:
        if cls.table is None:
            raise ValueError("Table is not initialized")
        return cls.table.find({"_id": ObjectId(_id)})[0]

    @classmethod
    def create(cls, obj: dict) -> dict[str, Any]:
        if cls.table is None:
            raise ValueError("Table is not initialized")
        # Remove computed/non-storable fields
        obj = dict(obj)
        obj.pop("day", None)
        _id = str(cls.table.insert_one(obj).inserted_id)
        obj.update({"_id": _id})
        return obj

    @classmethod
    def update(cls, obj: dict[str, Any]) -> dict[str, Any]:
        if cls.table is None:
            raise ValueError("Table is not initialized")
        if not obj.get("_id"):
            raise ValueError("_id required for update")
        # Remove computed/non-storable fields
        obj = dict(obj)
        obj.pop("day", None)
        cls.table.replace_one({"_id": obj.get("_id")}, obj)
        return obj

    @classmethod
    def list(cls, filters: dict | None = None) -> list[dict[str, Any]]:
        if cls.table is None:
            raise ValueError("Table is not initialized")
        return cls.table.find(filters or {})

    @classmethod
    def delete(cls, _id: str) -> bool:
        if cls.table is None:
            raise ValueError("Table is not initialized")
        return cls.table.delete_one({"_id": ObjectId(_id)})


class BeatRepository(BaseRepository):
    table = db.timeLogs

    @classmethod
    def get_last(cls):
        record = cls.table.find_one(sort=[("start", pymongo.DESCENDING)])
        if not record:
            raise NoObjectMatched()
        return record


class ProjectRepository(BaseRepository):
    table = db.projects


class Beat(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str | None = None
    start: datetime = Field(default_factory=lambda: datetime.now(UTC))
    end: datetime | None = None
    project_id: str | None = None

    def stop_timer(self, time: datetime) -> None:
        """
        Closes the log with the provided time.
        Validates the closing time is consistent with the start time -> comes after it.
        """
        if self.end:
            raise CanNotStopNonBeatingHeart
        # Normalize timezone awareness for safe comparison
        start = self.start
        if start.tzinfo is None:
            start = start.replace(tzinfo=UTC)
        comp_time = time
        if comp_time.tzinfo is None:
            comp_time = comp_time.replace(tzinfo=UTC)
        if (
            comp_time < start
        ):  # less than symbol "<" means "before" when comparing times
            raise InconsistentEndTime
        # Preserve original provided time value when storing
        self.end = time

    def is_beating(self) -> bool:
        return not self.end

    @property
    def duration(self) -> timedelta:
        end = self.end or datetime.now(UTC)
        # Ensure both datetimes are timezone-aware before subtraction
        start = self.start
        if start.tzinfo is None:
            start = start.replace(tzinfo=UTC)
        if end.tzinfo is None:
            end = end.replace(tzinfo=UTC)
        return end - start

    @computed_field
    @property
    def day(self) -> date:
        return self.start.date()


class Project(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str | None = None
    name: str
    description: str | None = None
    estimation: str | None = None
    archived: bool = False
