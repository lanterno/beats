from typing import List
from datetime import datetime
from pydantic import BaseModel, Field

from .db import db
from .exceptions import LogIsStopped


class BaseManager:
    table = None

    @classmethod
    def create(cls, obj: dict) -> dict:
        return cls.table.insert_one(obj)

    @classmethod
    def update(cls, obj: dict) -> dict:
        if not obj.get("_id"):
            raise Exception("_id required for update")
        return cls.table.replace_one({"_id": obj.get("_id")}, obj)

    @classmethod
    def list(cls, _filter: dict = None) -> List[dict]:
        return cls.table.find(_filter or {})

    @classmethod
    def delete(cls, obj_id: str) -> bool:
        pass


class TimeLogManager(BaseManager):
    table = db.timeLogs


class ProjectManager(BaseManager):
    table = db.projects


class TimeLog(BaseModel):
    id: str = None
    start: datetime = Field(default_factory=datetime.utcnow)
    end: datetime = None
    project_id: str = None

    def stop_timer(self, time):
        if self.end:
            raise LogIsStopped
        self.end = time

    def duration(self):
        end = self.end or datetime.utcnow()
        return end - self.start


class Project(BaseModel):
    id: str = None
    name: str
    description: str = None
    estimation: str = None
    archived: bool = False
