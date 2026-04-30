"""Repository implementations for MongoDB using Motor async driver."""

from abc import ABC, abstractmethod
from datetime import UTC, date, datetime
from typing import Any

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorCollection

from beats.domain.exceptions import BeatNotFound, NoObjectMatched, ProjectNotFound
from beats.domain.models import (
    AutoStartRule,
    Beat,
    BiometricDay,
    CalendarIntegration,
    DailyNote,
    DeviceRegistration,
    FitbitIntegration,
    FlowWindow,
    GitHubIntegration,
    Intention,
    OuraIntegration,
    PairingCode,
    Project,
    RecurringIntention,
    SignalSummary,
    User,
    UserInsights,
    Webhook,
    WeeklyDigest,
    WeeklyPlan,
    WeeklyReview,
)


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


class MongoUserScoped:
    """Mixin: user-scoped query builder shared by all Mongo repositories."""

    def __init__(self, collection: AsyncIOMotorCollection, user_id: str):
        self.collection = collection
        self.user_id = user_id

    def _q(self, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        q: dict[str, Any] = {"user_id": self.user_id}
        if extra:
            q.update(extra)
        return q


# Abstract Repository Interfaces


class UserRepository(ABC):
    """Abstract interface for User persistence operations."""

    @abstractmethod
    async def get_by_id(self, user_id: str) -> User | None: ...

    @abstractmethod
    async def get_by_email(self, email: str) -> User | None: ...

    @abstractmethod
    async def create(self, user: User) -> User: ...

    @abstractmethod
    async def count(self) -> int: ...


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

    @abstractmethod
    async def list_all_completed(self) -> list[Beat]:
        """List all completed beats (with end time set)."""
        ...

    @abstractmethod
    async def list_completed_in_range(self, start: date, end: date) -> list[Beat]:
        """List completed beats with start date in [start, end]."""
        ...

    @abstractmethod
    async def upsert(self, data: dict) -> None:
        """Upsert a beat by ID for import/restore."""
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
    async def list(self, archived: bool = False) -> list[Project]:
        """List projects with optional archived filter."""
        ...

    @abstractmethod
    async def upsert(self, data: dict) -> None:
        """Upsert a project by ID for import/restore."""
        ...


# MongoDB Implementations


class MongoBeatRepository(MongoUserScoped, BeatRepository):
    """MongoDB implementation of BeatRepository using Motor."""

    async def get_by_id(self, beat_id: str) -> Beat:
        doc = await self.collection.find_one(self._q({"_id": ObjectId(beat_id)}))
        if not doc:
            raise BeatNotFound(beat_id)
        return Beat(**serialize_from_document(doc))

    async def get_active(self) -> Beat | None:
        doc = await self.collection.find_one(self._q({"end": None}))
        if not doc:
            return None
        return Beat(**serialize_from_document(doc))

    async def get_last(self) -> Beat:
        doc = await self.collection.find_one(self._q(), sort=[("start", -1)])
        if not doc:
            raise NoObjectMatched()
        return Beat(**serialize_from_document(doc))

    async def create(self, beat: Beat) -> Beat:
        data = serialize_to_document(beat.model_dump(exclude_none=True))
        data["user_id"] = self.user_id
        result = await self.collection.insert_one(data)
        return Beat(**serialize_from_document({**data, "_id": result.inserted_id}))

    async def update(self, beat: Beat) -> Beat:
        if not beat.id:
            raise ValueError("Beat ID is required for update")
        data = serialize_to_document(beat.model_dump(exclude_none=True))
        data["user_id"] = self.user_id
        await self.collection.replace_one(self._q({"_id": ObjectId(beat.id)}), data)
        return beat

    async def delete(self, beat_id: str) -> bool:
        result = await self.collection.delete_one(self._q({"_id": ObjectId(beat_id)}))
        return result.deleted_count > 0

    async def list(
        self,
        project_id: str | None = None,
        date_filter: date | None = None,
    ) -> list[Beat]:
        query = self._q()
        if project_id:
            query["project_id"] = project_id
        if date_filter:
            start_of_day = datetime.combine(date_filter, datetime.min.time())
            end_of_day = datetime.combine(date_filter, datetime.max.time())
            query["start"] = {"$gte": start_of_day, "$lte": end_of_day}

        cursor = self.collection.find(query)
        docs = await cursor.to_list(length=None)
        return [Beat(**serialize_from_document(doc)) for doc in docs]

    async def list_by_project(self, project_id: str) -> list[Beat]:
        cursor = self.collection.find(self._q({"project_id": project_id}))
        docs = await cursor.to_list(length=None)
        return [Beat(**serialize_from_document(doc)) for doc in docs]

    async def list_all_completed(self) -> list[Beat]:
        cursor = self.collection.find(self._q({"end": {"$ne": None}}))
        docs = await cursor.to_list(length=None)
        return [Beat(**serialize_from_document(doc)) for doc in docs]

    async def list_completed_in_range(self, start: date, end: date) -> list[Beat]:
        start_dt = datetime.combine(start, datetime.min.time())
        end_dt = datetime.combine(end, datetime.max.time())
        cursor = self.collection.find(
            self._q({"start": {"$gte": start_dt, "$lte": end_dt}, "end": {"$ne": None}})
        )
        docs = await cursor.to_list(length=None)
        return [Beat(**serialize_from_document(doc)) for doc in docs]

    async def upsert(self, data: dict) -> None:
        doc = serialize_to_document(dict(data))
        doc["user_id"] = self.user_id
        doc_id = doc.pop("_id", None)
        if doc_id:
            await self.collection.update_one({"_id": doc_id}, {"$set": doc}, upsert=True)
        else:
            await self.collection.insert_one(doc)


class MongoProjectRepository(MongoUserScoped, ProjectRepository):
    """MongoDB implementation of ProjectRepository using Motor."""

    async def get_by_id(self, project_id: str) -> Project:
        doc = await self.collection.find_one(self._q({"_id": ObjectId(project_id)}))
        if not doc:
            raise ProjectNotFound(project_id)
        return Project(**serialize_from_document(doc))

    async def exists(self, project_id: str) -> bool:
        try:
            doc = await self.collection.find_one(self._q({"_id": ObjectId(project_id)}))
            return doc is not None
        except Exception:
            return False

    async def create(self, project: Project) -> Project:
        data = serialize_to_document(project.model_dump(mode="json", exclude_none=True))
        data["user_id"] = self.user_id
        result = await self.collection.insert_one(data)
        return Project(**serialize_from_document({**data, "_id": result.inserted_id}))

    async def update(self, project: Project) -> Project:
        if not project.id:
            raise ValueError("Project ID is required for update")
        data = serialize_to_document(project.model_dump(mode="json", exclude_none=True))
        data["user_id"] = self.user_id
        await self.collection.replace_one(self._q({"_id": ObjectId(project.id)}), data)
        return project

    async def list(self, archived: bool = False) -> list[Project]:
        cursor = self.collection.find(self._q({"archived": archived}))
        docs = await cursor.to_list(length=None)
        return [Project(**serialize_from_document(doc)) for doc in docs]

    async def upsert(self, data: dict) -> None:
        doc = serialize_to_document(dict(data))
        doc["user_id"] = self.user_id
        doc_id = doc.pop("_id", None)
        if doc_id:
            await self.collection.update_one({"_id": doc_id}, {"$set": doc}, upsert=True)
        else:
            await self.collection.insert_one(doc)


# User Repository


class MongoUserRepository(UserRepository):
    """MongoDB implementation of UserRepository."""

    def __init__(self, collection: AsyncIOMotorCollection):
        self.collection = collection

    async def get_by_id(self, user_id: str) -> User | None:
        doc = await self.collection.find_one({"_id": ObjectId(user_id)})
        if not doc:
            return None
        return User(**serialize_from_document(doc))

    async def get_by_email(self, email: str) -> User | None:
        doc = await self.collection.find_one({"email": email})
        if not doc:
            return None
        return User(**serialize_from_document(doc))

    async def create(self, user: User) -> User:
        data = serialize_to_document(user.model_dump(mode="json", exclude_none=True))
        result = await self.collection.insert_one(data)
        return User(**serialize_from_document({**data, "_id": result.inserted_id}))

    async def count(self) -> int:
        return await self.collection.count_documents({})


# Intention Repository


class IntentionRepository(ABC):
    """Abstract interface for Intention persistence operations."""

    @abstractmethod
    async def list_by_date(self, target_date: date) -> list[Intention]: ...

    @abstractmethod
    async def list_by_date_range(self, start: date, end: date) -> list[Intention]: ...

    @abstractmethod
    async def list_all(self) -> list[Intention]: ...

    @abstractmethod
    async def create(self, intention: Intention) -> Intention: ...

    @abstractmethod
    async def update(self, intention: Intention) -> Intention: ...

    @abstractmethod
    async def delete(self, intention_id: str) -> bool: ...

    @abstractmethod
    async def upsert(self, data: dict) -> None: ...


class MongoIntentionRepository(MongoUserScoped, IntentionRepository):
    """MongoDB implementation of IntentionRepository."""

    async def list_by_date(self, target_date: date) -> list[Intention]:
        cursor = self.collection.find(self._q({"date": target_date.isoformat()}))
        docs = await cursor.to_list(length=None)
        return [Intention(**serialize_from_document(doc)) for doc in docs]

    async def list_by_date_range(self, start: date, end: date) -> list[Intention]:
        cursor = self.collection.find(
            self._q({"date": {"$gte": start.isoformat(), "$lte": end.isoformat()}})
        )
        docs = await cursor.to_list(length=None)
        return [Intention(**serialize_from_document(doc)) for doc in docs]

    async def create(self, intention: Intention) -> Intention:
        data = serialize_to_document(intention.model_dump(mode="json", exclude_none=True))
        data["user_id"] = self.user_id
        result = await self.collection.insert_one(data)
        return Intention(**serialize_from_document({**data, "_id": result.inserted_id}))

    async def update(self, intention: Intention) -> Intention:
        if not intention.id:
            raise ValueError("Intention ID is required for update")
        data = serialize_to_document(intention.model_dump(mode="json", exclude_none=True))
        data["user_id"] = self.user_id
        await self.collection.replace_one(self._q({"_id": ObjectId(intention.id)}), data)
        return intention

    async def list_all(self) -> list[Intention]:
        cursor = self.collection.find(self._q())
        docs = await cursor.to_list(length=None)
        return [Intention(**serialize_from_document(doc)) for doc in docs]

    async def delete(self, intention_id: str) -> bool:
        result = await self.collection.delete_one(self._q({"_id": ObjectId(intention_id)}))
        return result.deleted_count > 0

    async def upsert(self, data: dict) -> None:
        doc = serialize_to_document(dict(data))
        doc["user_id"] = self.user_id
        doc_id = doc.pop("_id", None)
        if doc_id:
            await self.collection.update_one({"_id": doc_id}, {"$set": doc}, upsert=True)
        else:
            await self.collection.insert_one(doc)


# DailyNote Repository


class DailyNoteRepository(ABC):
    """Abstract interface for DailyNote persistence operations."""

    @abstractmethod
    async def get_by_date(self, target_date: date) -> DailyNote | None: ...

    @abstractmethod
    async def list_by_date_range(self, start: date, end: date) -> list[DailyNote]: ...

    @abstractmethod
    async def list_all(self) -> list[DailyNote]: ...

    @abstractmethod
    async def upsert(self, note: DailyNote) -> DailyNote: ...

    @abstractmethod
    async def upsert_raw(self, data: dict) -> None:
        """Upsert from raw dict for import/restore."""
        ...


class MongoDailyNoteRepository(MongoUserScoped, DailyNoteRepository):
    """MongoDB implementation of DailyNoteRepository."""

    async def get_by_date(self, target_date: date) -> DailyNote | None:
        doc = await self.collection.find_one(self._q({"date": target_date.isoformat()}))
        if not doc:
            return None
        return DailyNote(**serialize_from_document(doc))

    async def list_by_date_range(self, start: date, end: date) -> list[DailyNote]:
        cursor = self.collection.find(
            self._q({"date": {"$gte": start.isoformat(), "$lte": end.isoformat()}})
        )
        docs = await cursor.to_list(length=None)
        return [DailyNote(**serialize_from_document(doc)) for doc in docs]

    async def list_all(self) -> list[DailyNote]:
        cursor = self.collection.find(self._q())
        docs = await cursor.to_list(length=None)
        return [DailyNote(**serialize_from_document(doc)) for doc in docs]

    async def upsert(self, note: DailyNote) -> DailyNote:
        data = serialize_to_document(note.model_dump(mode="json", exclude_none=True))
        data.pop("_id", None)
        data["user_id"] = self.user_id
        result = await self.collection.find_one_and_update(
            self._q({"date": note.date.isoformat()}),
            {"$set": data},
            upsert=True,
            return_document=True,
        )
        return DailyNote(**serialize_from_document(result))

    async def upsert_raw(self, data: dict) -> None:
        doc = serialize_to_document(dict(data))
        doc["user_id"] = self.user_id
        doc_id = doc.pop("_id", None)
        if doc_id:
            await self.collection.update_one({"_id": doc_id}, {"$set": doc}, upsert=True)
        else:
            await self.collection.insert_one(doc)


# Webhook Repository


class WebhookRepository(ABC):
    """Abstract interface for Webhook persistence operations."""

    @abstractmethod
    async def list_all(self) -> list[Webhook]: ...

    @abstractmethod
    async def list_by_event(self, event: str) -> list[Webhook]: ...

    @abstractmethod
    async def create(self, webhook: Webhook) -> Webhook: ...

    @abstractmethod
    async def delete(self, webhook_id: str) -> bool: ...

    @abstractmethod
    async def update(self, webhook: Webhook) -> Webhook: ...


class MongoWebhookRepository(MongoUserScoped, WebhookRepository):
    """MongoDB implementation of WebhookRepository."""

    async def list_all(self) -> list[Webhook]:
        cursor = self.collection.find(self._q())
        docs = await cursor.to_list(length=None)
        return [Webhook(**serialize_from_document(doc)) for doc in docs]

    async def list_by_event(self, event: str) -> list[Webhook]:
        cursor = self.collection.find(self._q({"events": event, "active": True}))
        docs = await cursor.to_list(length=None)
        return [Webhook(**serialize_from_document(doc)) for doc in docs]

    async def create(self, webhook: Webhook) -> Webhook:
        data = serialize_to_document(webhook.model_dump(mode="json", exclude_none=True))
        data["user_id"] = self.user_id
        result = await self.collection.insert_one(data)
        return Webhook(**serialize_from_document({**data, "_id": result.inserted_id}))

    async def delete(self, webhook_id: str) -> bool:
        result = await self.collection.delete_one(self._q({"_id": ObjectId(webhook_id)}))
        return result.deleted_count > 0

    async def update(self, webhook: Webhook) -> Webhook:
        if not webhook.id:
            raise ValueError("Webhook ID is required for update")
        data = serialize_to_document(webhook.model_dump(mode="json", exclude_none=True))
        data["user_id"] = self.user_id
        await self.collection.replace_one(self._q({"_id": ObjectId(webhook.id)}), data)
        return webhook


# Weekly Digest Repository


class WeeklyDigestRepository(ABC):
    """Abstract interface for WeeklyDigest persistence operations."""

    @abstractmethod
    async def get_by_week(self, week_of: date) -> WeeklyDigest | None: ...

    @abstractmethod
    async def list_recent(self, limit: int = 12) -> list[WeeklyDigest]: ...

    @abstractmethod
    async def upsert(self, digest: WeeklyDigest) -> WeeklyDigest: ...


class MongoWeeklyDigestRepository(MongoUserScoped, WeeklyDigestRepository):
    """MongoDB implementation of WeeklyDigestRepository."""

    async def get_by_week(self, week_of: date) -> WeeklyDigest | None:
        doc = await self.collection.find_one(self._q({"week_of": week_of.isoformat()}))
        if not doc:
            return None
        return WeeklyDigest(**serialize_from_document(doc))

    async def list_recent(self, limit: int = 12) -> list[WeeklyDigest]:
        cursor = self.collection.find(self._q()).sort("week_of", -1).limit(limit)
        docs = await cursor.to_list(length=None)
        return [WeeklyDigest(**serialize_from_document(doc)) for doc in docs]

    async def upsert(self, digest: WeeklyDigest) -> WeeklyDigest:
        data = serialize_to_document(digest.model_dump(mode="json", exclude_none=True))
        data.pop("_id", None)
        data["user_id"] = self.user_id
        result = await self.collection.find_one_and_update(
            self._q({"week_of": digest.week_of.isoformat()}),
            {"$set": data},
            upsert=True,
            return_document=True,
        )
        return WeeklyDigest(**serialize_from_document(result))


# Insights Repository


class InsightsRepository(ABC):
    """Abstract interface for UserInsights persistence operations."""

    @abstractmethod
    async def get(self) -> UserInsights | None: ...

    @abstractmethod
    async def upsert(self, insights: UserInsights) -> UserInsights: ...

    @abstractmethod
    async def dismiss_insight(self, insight_id: str) -> None: ...


class MongoInsightsRepository(MongoUserScoped, InsightsRepository):
    """MongoDB implementation of InsightsRepository."""

    async def get(self) -> UserInsights | None:
        doc = await self.collection.find_one(self._q())
        if not doc:
            return None
        return UserInsights(**serialize_from_document(doc))

    async def upsert(self, insights: UserInsights) -> UserInsights:
        data = serialize_to_document(insights.model_dump(mode="json", exclude_none=True))
        data.pop("_id", None)
        data["user_id"] = self.user_id
        result = await self.collection.find_one_and_update(
            self._q(),
            {"$set": data},
            upsert=True,
            return_document=True,
        )
        return UserInsights(**serialize_from_document(result))

    async def dismiss_insight(self, insight_id: str) -> None:
        await self.collection.update_one(
            self._q(),
            {"$addToSet": {"dismissed_ids": insight_id}},
        )


# Calendar Integration Repository


class GitHubIntegrationRepository(ABC):
    """Abstract interface for GitHubIntegration persistence."""

    @abstractmethod
    async def get(self) -> GitHubIntegration | None: ...

    @abstractmethod
    async def upsert(self, integration: GitHubIntegration) -> GitHubIntegration: ...

    @abstractmethod
    async def delete(self) -> bool: ...


class MongoGitHubIntegrationRepository(MongoUserScoped, GitHubIntegrationRepository):
    """MongoDB implementation of GitHubIntegrationRepository."""

    async def get(self) -> GitHubIntegration | None:
        doc = await self.collection.find_one(self._q())
        if not doc:
            return None
        return GitHubIntegration(**serialize_from_document(doc))

    async def upsert(self, integration: GitHubIntegration) -> GitHubIntegration:
        data = serialize_to_document(integration.model_dump(mode="json", exclude_none=True))
        data.pop("_id", None)
        data["user_id"] = self.user_id
        result = await self.collection.find_one_and_update(
            self._q(),
            {"$set": data},
            upsert=True,
            return_document=True,
        )
        return GitHubIntegration(**serialize_from_document(result))

    async def delete(self) -> bool:
        result = await self.collection.delete_one(self._q())
        return result.deleted_count > 0


class AutoStartRuleRepository(ABC):
    """Abstract interface for AutoStartRule persistence."""

    @abstractmethod
    async def list_all(self) -> list[AutoStartRule]: ...

    @abstractmethod
    async def list_by_type(self, rule_type: str) -> list[AutoStartRule]: ...

    @abstractmethod
    async def create(self, rule: AutoStartRule) -> AutoStartRule: ...

    @abstractmethod
    async def delete(self, rule_id: str) -> bool: ...


class MongoAutoStartRuleRepository(MongoUserScoped, AutoStartRuleRepository):
    """MongoDB implementation of AutoStartRuleRepository."""

    async def list_all(self) -> list[AutoStartRule]:
        cursor = self.collection.find(self._q())
        docs = await cursor.to_list(length=None)
        return [AutoStartRule(**serialize_from_document(doc)) for doc in docs]

    async def list_by_type(self, rule_type: str) -> list[AutoStartRule]:
        cursor = self.collection.find(self._q({"type": rule_type, "enabled": True}))
        docs = await cursor.to_list(length=None)
        return [AutoStartRule(**serialize_from_document(doc)) for doc in docs]

    async def create(self, rule: AutoStartRule) -> AutoStartRule:
        data = serialize_to_document(rule.model_dump(mode="json", exclude_none=True))
        data["user_id"] = self.user_id
        result = await self.collection.insert_one(data)
        return AutoStartRule(**serialize_from_document({**data, "_id": result.inserted_id}))

    async def delete(self, rule_id: str) -> bool:
        result = await self.collection.delete_one(self._q({"_id": ObjectId(rule_id)}))
        return result.deleted_count > 0


class CalendarIntegrationRepository(ABC):
    """Abstract interface for CalendarIntegration persistence."""

    @abstractmethod
    async def get(self) -> CalendarIntegration | None: ...

    @abstractmethod
    async def upsert(self, integration: CalendarIntegration) -> CalendarIntegration: ...

    @abstractmethod
    async def delete(self) -> bool: ...


class MongoCalendarIntegrationRepository(MongoUserScoped, CalendarIntegrationRepository):
    """MongoDB implementation of CalendarIntegrationRepository."""

    async def get(self) -> CalendarIntegration | None:
        doc = await self.collection.find_one(self._q())
        if not doc:
            return None
        return CalendarIntegration(**serialize_from_document(doc))

    async def upsert(self, integration: CalendarIntegration) -> CalendarIntegration:
        data = serialize_to_document(integration.model_dump(mode="json", exclude_none=True))
        data.pop("_id", None)
        data["user_id"] = self.user_id
        result = await self.collection.find_one_and_update(
            self._q(),
            {"$set": data},
            upsert=True,
            return_document=True,
        )
        return CalendarIntegration(**serialize_from_document(result))

    async def delete(self) -> bool:
        result = await self.collection.delete_one(self._q())
        return result.deleted_count > 0


# Weekly Plan Repository


class WeeklyPlanRepository(ABC):
    """Abstract interface for WeeklyPlan persistence."""

    @abstractmethod
    async def get_by_week(self, week_of: date) -> WeeklyPlan | None: ...

    @abstractmethod
    async def upsert(self, plan: WeeklyPlan) -> WeeklyPlan: ...


class MongoWeeklyPlanRepository(MongoUserScoped, WeeklyPlanRepository):
    """MongoDB implementation of WeeklyPlanRepository."""

    async def get_by_week(self, week_of: date) -> WeeklyPlan | None:
        doc = await self.collection.find_one(self._q({"week_of": week_of.isoformat()}))
        if not doc:
            return None
        return WeeklyPlan(**serialize_from_document(doc))

    async def upsert(self, plan: WeeklyPlan) -> WeeklyPlan:
        data = serialize_to_document(plan.model_dump(mode="json", exclude_none=True))
        data.pop("_id", None)
        data["user_id"] = self.user_id
        result = await self.collection.find_one_and_update(
            self._q({"week_of": plan.week_of.isoformat()}),
            {"$set": data},
            upsert=True,
            return_document=True,
        )
        return WeeklyPlan(**serialize_from_document(result))


# Recurring Intention Repository


class RecurringIntentionRepository(ABC):
    """Abstract interface for RecurringIntention persistence."""

    @abstractmethod
    async def list_all(self) -> list[RecurringIntention]: ...

    @abstractmethod
    async def create(self, intention: RecurringIntention) -> RecurringIntention: ...

    @abstractmethod
    async def delete(self, intention_id: str) -> bool: ...


class MongoRecurringIntentionRepository(MongoUserScoped, RecurringIntentionRepository):
    """MongoDB implementation of RecurringIntentionRepository."""

    async def list_all(self) -> list[RecurringIntention]:
        cursor = self.collection.find(self._q())
        docs = await cursor.to_list(length=None)
        return [RecurringIntention(**serialize_from_document(doc)) for doc in docs]

    async def create(self, intention: RecurringIntention) -> RecurringIntention:
        data = serialize_to_document(intention.model_dump(mode="json", exclude_none=True))
        data["user_id"] = self.user_id
        result = await self.collection.insert_one(data)
        return RecurringIntention(**serialize_from_document({**data, "_id": result.inserted_id}))

    async def delete(self, intention_id: str) -> bool:
        result = await self.collection.delete_one(self._q({"_id": ObjectId(intention_id)}))
        return result.deleted_count > 0


# Weekly Review Repository


class WeeklyReviewRepository(ABC):
    """Abstract interface for WeeklyReview persistence."""

    @abstractmethod
    async def get_by_week(self, week_of: date) -> WeeklyReview | None: ...

    @abstractmethod
    async def upsert(self, review: WeeklyReview) -> WeeklyReview: ...

    @abstractmethod
    async def list_recent(self, limit: int = 12) -> list[WeeklyReview]: ...


class MongoWeeklyReviewRepository(MongoUserScoped, WeeklyReviewRepository):
    """MongoDB implementation of WeeklyReviewRepository."""

    async def get_by_week(self, week_of: date) -> WeeklyReview | None:
        doc = await self.collection.find_one(self._q({"week_of": week_of.isoformat()}))
        if not doc:
            return None
        return WeeklyReview(**serialize_from_document(doc))

    async def upsert(self, review: WeeklyReview) -> WeeklyReview:
        data = serialize_to_document(review.model_dump(mode="json", exclude_none=True))
        data.pop("_id", None)
        data["user_id"] = self.user_id
        result = await self.collection.find_one_and_update(
            self._q({"week_of": review.week_of.isoformat()}),
            {"$set": data},
            upsert=True,
            return_document=True,
        )
        return WeeklyReview(**serialize_from_document(result))

    async def list_recent(self, limit: int = 12) -> list[WeeklyReview]:
        cursor = self.collection.find(self._q()).sort("week_of", -1).limit(limit)
        docs = await cursor.to_list(length=None)
        return [WeeklyReview(**serialize_from_document(doc)) for doc in docs]


# Pairing Code Repository


class PairingCodeRepository(ABC):
    """Abstract interface for PairingCode persistence (not user-scoped)."""

    @abstractmethod
    async def create(self, code: PairingCode) -> PairingCode: ...

    @abstractmethod
    async def find_by_hash(self, code_hash: str) -> PairingCode | None: ...

    @abstractmethod
    async def delete(self, code_id: str) -> bool: ...


class MongoPairingCodeRepository(PairingCodeRepository):
    """MongoDB implementation of PairingCodeRepository.

    Not user-scoped: the exchange endpoint is public and looks up by code_hash.
    """

    def __init__(self, collection: AsyncIOMotorCollection):
        self.collection = collection

    async def create(self, code: PairingCode) -> PairingCode:
        data = serialize_to_document(code.model_dump(mode="json", exclude_none=True))
        result = await self.collection.insert_one(data)
        return PairingCode(**serialize_from_document({**data, "_id": result.inserted_id}))

    async def find_by_hash(self, code_hash: str) -> PairingCode | None:
        doc = await self.collection.find_one(
            {
                "code_hash": code_hash,
                "expires_at": {"$gt": datetime.now(UTC).isoformat()},
            }
        )
        if not doc:
            return None
        return PairingCode(**serialize_from_document(doc))

    async def delete(self, code_id: str) -> bool:
        result = await self.collection.delete_one({"_id": ObjectId(code_id)})
        return result.deleted_count > 0


# Device Registration Repository


class DeviceRegistrationRepository(ABC):
    """Abstract interface for DeviceRegistration persistence (not user-scoped)."""

    @abstractmethod
    async def create(self, reg: DeviceRegistration) -> DeviceRegistration: ...

    @abstractmethod
    async def get_by_device_id(self, device_id: str) -> DeviceRegistration | None: ...

    @abstractmethod
    async def list_by_user(self, user_id: str) -> list[DeviceRegistration]: ...

    @abstractmethod
    async def revoke(self, device_id: str, user_id: str) -> bool: ...

    @abstractmethod
    async def update_last_seen(self, device_id: str) -> None: ...


class MongoDeviceRegistrationRepository(DeviceRegistrationRepository):
    """MongoDB implementation of DeviceRegistrationRepository.

    Not user-scoped: device token validation looks up by device_id across all users.
    """

    def __init__(self, collection: AsyncIOMotorCollection):
        self.collection = collection

    async def create(self, reg: DeviceRegistration) -> DeviceRegistration:
        data = serialize_to_document(reg.model_dump(mode="json", exclude_none=True))
        result = await self.collection.insert_one(data)
        return DeviceRegistration(**serialize_from_document({**data, "_id": result.inserted_id}))

    async def get_by_device_id(self, device_id: str) -> DeviceRegistration | None:
        doc = await self.collection.find_one({"device_id": device_id})
        if not doc:
            return None
        return DeviceRegistration(**serialize_from_document(doc))

    async def list_by_user(self, user_id: str) -> list[DeviceRegistration]:
        cursor = self.collection.find({"user_id": user_id, "revoked": False})
        docs = await cursor.to_list(length=None)
        return [DeviceRegistration(**serialize_from_document(doc)) for doc in docs]

    async def revoke(self, device_id: str, user_id: str) -> bool:
        result = await self.collection.update_one(
            {"device_id": device_id, "user_id": user_id},
            {"$set": {"revoked": True}},
        )
        return result.modified_count > 0

    async def update_last_seen(self, device_id: str) -> None:
        await self.collection.update_one(
            {"device_id": device_id},
            {"$set": {"last_seen": datetime.now(UTC).isoformat()}},
        )


# Flow Window Repository


class FlowWindowRepository(ABC):
    """Abstract interface for FlowWindow persistence."""

    @abstractmethod
    async def create(self, window: FlowWindow) -> FlowWindow: ...

    @abstractmethod
    async def list_by_range(
        self,
        start: datetime,
        end: datetime,
        project_id: str | None = None,
        editor_repo: str | None = None,
        editor_language: str | None = None,
    ) -> list[FlowWindow]: ...


class MongoFlowWindowRepository(MongoUserScoped, FlowWindowRepository):
    """MongoDB implementation of FlowWindowRepository."""

    async def create(self, window: FlowWindow) -> FlowWindow:
        data = serialize_to_document(window.model_dump(mode="json", exclude_none=True))
        data["user_id"] = self.user_id
        result = await self.collection.insert_one(data)
        return FlowWindow(**serialize_from_document({**data, "_id": result.inserted_id}))

    async def list_by_range(
        self,
        start: datetime,
        end: datetime,
        project_id: str | None = None,
        editor_repo: str | None = None,
        editor_language: str | None = None,
    ) -> list[FlowWindow]:
        # Filters are AND-composed. project_id matches windows captured
        # while a timer was running on that project; editor_repo matches
        # windows where the VS Code heartbeat covered them; editor_language
        # matches the language id reported by the heartbeat. All optional
        # so the existing call sites keep working.
        query: dict = {"window_start": {"$gte": start.isoformat(), "$lte": end.isoformat()}}
        if project_id is not None:
            query["active_project_id"] = project_id
        if editor_repo is not None:
            query["editor_repo"] = editor_repo
        if editor_language is not None:
            query["editor_language"] = editor_language
        cursor = self.collection.find(self._q(query)).sort("window_start", 1)
        docs = await cursor.to_list(length=None)
        return [FlowWindow(**serialize_from_document(doc)) for doc in docs]


# Signal Summary Repository


class SignalSummaryRepository(ABC):
    """Abstract interface for SignalSummary persistence."""

    @abstractmethod
    async def upsert(self, summary: SignalSummary) -> SignalSummary: ...

    @abstractmethod
    async def list_by_range(self, start: datetime, end: datetime) -> list[SignalSummary]: ...

    @abstractmethod
    async def delete_all(self) -> int: ...


class MongoSignalSummaryRepository(MongoUserScoped, SignalSummaryRepository):
    """MongoDB implementation of SignalSummaryRepository."""

    async def upsert(self, summary: SignalSummary) -> SignalSummary:
        data = serialize_to_document(summary.model_dump(mode="json", exclude_none=True))
        data.pop("_id", None)
        data["user_id"] = self.user_id
        # Use the serialized hour value for the filter to avoid isoformat mismatch
        # (e.g. "2026-04-18T14:00:00Z" vs "2026-04-18T14:00:00+00:00")
        result = await self.collection.find_one_and_update(
            self._q(
                {
                    "device_id": data["device_id"],
                    "hour": data["hour"],
                }
            ),
            {"$set": data},
            upsert=True,
            return_document=True,
        )
        return SignalSummary(**serialize_from_document(result))

    async def list_by_range(self, start: datetime, end: datetime) -> list[SignalSummary]:
        cursor = self.collection.find(
            self._q({"hour": {"$gte": start.isoformat(), "$lte": end.isoformat()}})
        ).sort("hour", 1)
        docs = await cursor.to_list(length=None)
        return [SignalSummary(**serialize_from_document(doc)) for doc in docs]

    async def delete_all(self) -> int:
        result = await self.collection.delete_many(self._q())
        return result.deleted_count


# Biometric Day Repository


class BiometricDayRepository(ABC):
    """Abstract interface for BiometricDay persistence."""

    @abstractmethod
    async def upsert(self, day: BiometricDay) -> BiometricDay: ...

    @abstractmethod
    async def list_by_range(self, start: date, end: date) -> list[BiometricDay]: ...

    @abstractmethod
    async def delete_all(self) -> int: ...


class MongoBiometricDayRepository(MongoUserScoped, BiometricDayRepository):
    """MongoDB implementation of BiometricDayRepository."""

    async def upsert(self, day: BiometricDay) -> BiometricDay:
        data = serialize_to_document(day.model_dump(mode="json", exclude_none=True))
        data.pop("_id", None)
        data["user_id"] = self.user_id
        result = await self.collection.find_one_and_update(
            self._q({"date": data["date"], "source": data["source"]}),
            {"$set": data},
            upsert=True,
            return_document=True,
        )
        return BiometricDay(**serialize_from_document(result))

    async def list_by_range(self, start: date, end: date) -> list[BiometricDay]:
        cursor = self.collection.find(
            self._q({"date": {"$gte": start.isoformat(), "$lte": end.isoformat()}})
        ).sort("date", 1)
        docs = await cursor.to_list(length=None)
        return [BiometricDay(**serialize_from_document(doc)) for doc in docs]

    async def delete_all(self) -> int:
        result = await self.collection.delete_many(self._q())
        return result.deleted_count


# Fitbit Integration Repository


class FitbitIntegrationRepository(ABC):
    """Abstract interface for FitbitIntegration persistence."""

    @abstractmethod
    async def get(self) -> FitbitIntegration | None: ...

    @abstractmethod
    async def upsert(self, integration: FitbitIntegration) -> FitbitIntegration: ...

    @abstractmethod
    async def delete(self) -> bool: ...


class MongoFitbitIntegrationRepository(MongoUserScoped, FitbitIntegrationRepository):
    """MongoDB implementation of FitbitIntegrationRepository."""

    async def get(self) -> FitbitIntegration | None:
        doc = await self.collection.find_one(self._q())
        if not doc:
            return None
        return FitbitIntegration(**serialize_from_document(doc))

    async def upsert(self, integration: FitbitIntegration) -> FitbitIntegration:
        data = serialize_to_document(integration.model_dump(mode="json", exclude_none=True))
        data.pop("_id", None)
        data["user_id"] = self.user_id
        result = await self.collection.find_one_and_update(
            self._q(),
            {"$set": data},
            upsert=True,
            return_document=True,
        )
        return FitbitIntegration(**serialize_from_document(result))

    async def delete(self) -> bool:
        result = await self.collection.delete_one(self._q())
        return result.deleted_count > 0


# Oura Integration Repository


class OuraIntegrationRepository(ABC):
    """Abstract interface for OuraIntegration persistence."""

    @abstractmethod
    async def get(self) -> OuraIntegration | None: ...

    @abstractmethod
    async def upsert(self, integration: OuraIntegration) -> OuraIntegration: ...

    @abstractmethod
    async def delete(self) -> bool: ...


class MongoOuraIntegrationRepository(MongoUserScoped, OuraIntegrationRepository):
    """MongoDB implementation of OuraIntegrationRepository."""

    async def get(self) -> OuraIntegration | None:
        doc = await self.collection.find_one(self._q())
        if not doc:
            return None
        return OuraIntegration(**serialize_from_document(doc))

    async def upsert(self, integration: OuraIntegration) -> OuraIntegration:
        data = serialize_to_document(integration.model_dump(mode="json", exclude_none=True))
        data.pop("_id", None)
        data["user_id"] = self.user_id
        result = await self.collection.find_one_and_update(
            self._q(),
            {"$set": data},
            upsert=True,
            return_document=True,
        )
        return OuraIntegration(**serialize_from_document(result))

    async def delete(self) -> bool:
        result = await self.collection.delete_one(self._q())
        return result.deleted_count > 0
