import uuid

from typing import List
from datetime import datetime
from pydantic import BaseModel, Field

from .db import db


class BaseManager:
    table = None

    @classmethod
    def create(cls, obj: dict) -> dict:
        return cls.table.insert_one(obj)

    @classmethod
    def update(cls, obj: dict) -> dict:
        if not obj["_id"]:
            raise Exception("_id required for update")
        return cls.table.replace_one({"_id": obj.get("_id")}, obj)

    @classmethod
    def list(cls, _filter: dict = None) -> List[dict]:
        return cls.table.find(_filter or {})

    @classmethod
    def delete(cls, time_log: dict) -> bool:
        pass


class TimeLogManager(BaseManager):
    table = db.timeLogs


class ProjectManager(BaseManager):
    table = db.projects


class TimeLog(BaseModel):
    _id: uuid.UUID = None
    start: datetime = Field(default_factory=datetime.utcnow)
    end: datetime = None
    project_id: str = None


class Project(BaseModel):
    _id: uuid.UUID = None
    name: str
    description: str = None
    estimation: str = None
    time_logs: List[TimeLog] = []
