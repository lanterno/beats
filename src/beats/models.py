from typing import List
from datetime import datetime

import pymongo

from pydantic import BaseModel, Field
from bson.objectid import ObjectId

from .db import db
from .exceptions import LogIsStopped, InconsistentEndTime


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
    def list(cls, _filter: dict = None) -> List[dict]:
        return cls.table.find(_filter or {})

    @classmethod
    def delete(cls, obj_id: str) -> bool:
        pass


class TimeLogRepository(BaseRepository):
    table = db.timeLogs

    @classmethod
    def get_last(cls):
        return cls.table.find_one(sort=[("start", pymongo.DESCENDING)])


class ProjectRepository(BaseRepository):
    table = db.projects

    @classmethod
    def list(cls, _filter: dict = None) -> List[dict]:
        _filter = _filter or {}
        _filter.update({"archived": False})
        return cls.table.find(_filter)


class TimeLog(BaseModel):
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
            raise LogIsStopped
        if time < self.start:  # less than symbol "<" means "before" when comparing times
            raise InconsistentEndTime
        self.end = time

    def is_beating(self):
        return not self.end

    @property
    def duration(self):
        end = self.end or datetime.utcnow()
        return end - self.start


class Project(BaseModel):
    id: str = None
    name: str
    description: str = None
    estimation: str = None
    archived: bool = False
