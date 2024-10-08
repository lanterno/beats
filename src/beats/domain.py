from typing import List, Optional
from datetime import datetime

import pymongo

from pydantic import BaseModel, Field
from bson.objectid import ObjectId

from .db import db
from .exceptions import CanNotStopNonBeatingHeart, InconsistentEndTime, NoObjectMatched


class BaseRepository:
    table = None

    @classmethod
    def retrieve_by_id(cls, _id: str):
        return cls.table.find({"_id": ObjectId(_id)})[0]

    @classmethod
    def create(cls, obj: dict) -> dict:
        _id = str(cls.table.insert_one(obj).inserted_id)
        obj.update({"_id": _id})
        return obj

    @classmethod
    def update(cls, obj: dict) -> dict:
        if not obj.get("_id"):
            raise Exception("_id required for update")
        cls.table.replace_one({"_id": obj.get("_id")}, obj)
        return obj

    @classmethod
    def list(cls, filters: Optional[dict] = None) -> List[dict]:
        return cls.table.find(filters or {})

    @classmethod
    def delete(cls, _id: str) -> bool:
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
    id: str = None
    start: datetime = Field(default_factory=datetime.utcnow)
    end: datetime = None
    project_id: str = None

    def stop_timer(self, time: datetime):
        """
        Closes the log with the provided time.
        Validates the closing time is consistent with the start time -> comes after it.
        """
        if self.end:
            raise CanNotStopNonBeatingHeart
        if time < self.start:  # less than symbol "<" means "before" when comparing times
            print(self.id)
            raise InconsistentEndTime
        self.end = time

    def is_beating(self):
        return not self.end

    @property
    def duration(self):
        end = self.end or datetime.utcnow()
        return end - self.start

    @property
    def day(self):
        return self.start.date()


class Project(BaseModel):
    id: str = None
    name: str
    description: str = None
    estimation: str = None
    archived: bool = False
