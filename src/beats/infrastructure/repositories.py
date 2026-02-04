"""Repository implementations for MongoDB using Motor async driver."""

from abc import ABC, abstractmethod
from datetime import date, datetime
from typing import Any

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorCollection

from beats.domain.exceptions import BeatNotFound, NoObjectMatched, ProjectNotFound
from beats.domain.models import Beat, Project


def serialize_from_document(doc: dict[str, Any]) -> dict[str, Any]:
    """Convert MongoDB document to domain model format.

    Converts ObjectId _id to string id.
    """
    if doc is None:
        return doc
    result = dict(doc)
    if "_id" in result:
        result["id"] = str(result.pop("_id"))
    return result


def serialize_to_document(data: dict[str, Any]) -> dict[str, Any]:
    """Convert domain model data to MongoDB document format.

    Converts string id to ObjectId _id.
    """
    result = dict(data)
    if "id" in result:
        id_value = result.pop("id")
        if id_value:
            result["_id"] = ObjectId(id_value)
    # Remove computed fields that shouldn't be stored
    result.pop("day", None)
    result.pop("is_active", None)
    result.pop("duration", None)
    return result


# Abstract Repository Interfaces


class BeatRepository(ABC):
    """Abstract interface for Beat persistence operations."""

    @abstractmethod
    async def get_by_id(self, beat_id: str) -> Beat:
        """Retrieve a beat by its ID."""
        ...

    @abstractmethod
    async def get_active(self) -> Beat | None:
        """Get the currently active beat (timer running), if any."""
        ...

    @abstractmethod
    async def get_last(self) -> Beat:
        """Get the most recent beat by start time."""
        ...

    @abstractmethod
    async def create(self, beat: Beat) -> Beat:
        """Create a new beat and return it with its assigned ID."""
        ...

    @abstractmethod
    async def update(self, beat: Beat) -> Beat:
        """Update an existing beat."""
        ...

    @abstractmethod
    async def delete(self, beat_id: str) -> bool:
        """Delete a beat by ID. Returns True if deleted."""
        ...

    @abstractmethod
    async def list(
        self,
        project_id: str | None = None,
        date_filter: date | None = None,
    ) -> list[Beat]:
        """List beats with optional filters."""
        ...

    @abstractmethod
    async def list_by_project(self, project_id: str) -> list[Beat]:
        """List all beats for a specific project."""
        ...


class ProjectRepository(ABC):
    """Abstract interface for Project persistence operations."""

    @abstractmethod
    async def get_by_id(self, project_id: str) -> Project:
        """Retrieve a project by its ID."""
        ...

    @abstractmethod
    async def exists(self, project_id: str) -> bool:
        """Check if a project exists."""
        ...

    @abstractmethod
    async def create(self, project: Project) -> Project:
        """Create a new project and return it with its assigned ID."""
        ...

    @abstractmethod
    async def update(self, project: Project) -> Project:
        """Update an existing project."""
        ...

    @abstractmethod
    async def delete(self, project_id: str) -> bool:
        """Delete a project by ID. Returns True if deleted."""
        ...

    @abstractmethod
    async def list(self, archived: bool = False) -> list[Project]:
        """List projects with optional archived filter."""
        ...


# MongoDB Implementations


class MongoBeatRepository(BeatRepository):
    """MongoDB implementation of BeatRepository using Motor."""

    def __init__(self, collection: AsyncIOMotorCollection):
        self.collection = collection

    async def get_by_id(self, beat_id: str) -> Beat:
        doc = await self.collection.find_one({"_id": ObjectId(beat_id)})
        if not doc:
            raise BeatNotFound(beat_id)
        return Beat(**serialize_from_document(doc))

    async def get_active(self) -> Beat | None:
        doc = await self.collection.find_one({"end": None})
        if not doc:
            return None
        return Beat(**serialize_from_document(doc))

    async def get_last(self) -> Beat:
        doc = await self.collection.find_one(sort=[("start", -1)])
        if not doc:
            raise NoObjectMatched()
        return Beat(**serialize_from_document(doc))

    async def create(self, beat: Beat) -> Beat:
        data = serialize_to_document(beat.model_dump(exclude_none=True))
        result = await self.collection.insert_one(data)
        return Beat(**serialize_from_document({**data, "_id": result.inserted_id}))

    async def update(self, beat: Beat) -> Beat:
        if not beat.id:
            raise ValueError("Beat ID is required for update")
        data = serialize_to_document(beat.model_dump(exclude_none=True))
        await self.collection.replace_one({"_id": ObjectId(beat.id)}, data)
        return beat

    async def delete(self, beat_id: str) -> bool:
        result = await self.collection.delete_one({"_id": ObjectId(beat_id)})
        return result.deleted_count > 0

    async def list(
        self,
        project_id: str | None = None,
        date_filter: date | None = None,
    ) -> list[Beat]:
        query: dict[str, Any] = {}
        if project_id:
            query["project_id"] = project_id
        if date_filter:
            # Filter by date (start of day to end of day)
            start_of_day = datetime.combine(date_filter, datetime.min.time())
            end_of_day = datetime.combine(date_filter, datetime.max.time())
            query["start"] = {"$gte": start_of_day, "$lte": end_of_day}

        cursor = self.collection.find(query)
        docs = await cursor.to_list(length=None)
        return [Beat(**serialize_from_document(doc)) for doc in docs]

    async def list_by_project(self, project_id: str) -> list[Beat]:
        cursor = self.collection.find({"project_id": project_id})
        docs = await cursor.to_list(length=None)
        return [Beat(**serialize_from_document(doc)) for doc in docs]


class MongoProjectRepository(ProjectRepository):
    """MongoDB implementation of ProjectRepository using Motor."""

    def __init__(self, collection: AsyncIOMotorCollection):
        self.collection = collection

    async def get_by_id(self, project_id: str) -> Project:
        doc = await self.collection.find_one({"_id": ObjectId(project_id)})
        if not doc:
            raise ProjectNotFound(project_id)
        return Project(**serialize_from_document(doc))

    async def exists(self, project_id: str) -> bool:
        try:
            doc = await self.collection.find_one({"_id": ObjectId(project_id)})
            return doc is not None
        except Exception:
            return False

    async def create(self, project: Project) -> Project:
        data = serialize_to_document(project.model_dump(exclude_none=True))
        result = await self.collection.insert_one(data)
        return Project(**serialize_from_document({**data, "_id": result.inserted_id}))

    async def update(self, project: Project) -> Project:
        if not project.id:
            raise ValueError("Project ID is required for update")
        data = serialize_to_document(project.model_dump(exclude_none=True))
        await self.collection.replace_one({"_id": ObjectId(project.id)}, data)
        return project

    async def delete(self, project_id: str) -> bool:
        result = await self.collection.delete_one({"_id": ObjectId(project_id)})
        return result.deleted_count > 0

    async def list(self, archived: bool = False) -> list[Project]:
        cursor = self.collection.find({"archived": archived})
        docs = await cursor.to_list(length=None)
        return [Project(**serialize_from_document(doc)) for doc in docs]
