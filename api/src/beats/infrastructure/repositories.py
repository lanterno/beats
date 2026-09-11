"""Repository implementations for MongoDB using the PyMongo async driver.

The interfaces are `Protocol`s rather than ABCs. The Mongo classes inherit them
anyway, so a missing method is still a type error here, but the test suite's
in-memory fakes satisfy them structurally without having to subclass anything —
which is how they were already written, and what the ABCs could not express.

`MongoStore` holds the mechanics every user-scoped repository shares: the
user_id filter, and the conversion between documents and Pydantic models.
`MongoSingletonStore` adds the get/upsert/delete trio for the collections that
hold exactly one document per user.
"""

import builtins
from datetime import UTC, date, datetime
from typing import Any, Literal, Protocol

from bson import ObjectId
from bson.errors import InvalidId
from pydantic import BaseModel
from pymongo import ReturnDocument
from pymongo.asynchronous.collection import AsyncCollection

from beats.domain.exceptions import BeatNotFound, NoObjectMatched, ProjectNotFound
from beats.domain.models import (
    Beat,
    BiometricDay,
    CalendarIntegration,
    DeviceRegistration,
    FitbitIntegration,
    FlowWindow,
    GitHubIntegration,
    OuraIntegration,
    PairingCode,
    PendingSuggestion,
    Project,
    SignalSummary,
    User,
    UserInsights,
    Webhook,
    WeeklyDigest,
    WeeklyPlan,
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


class MongoStore[ModelT: BaseModel]:
    """Mechanics shared by every user-scoped Mongo repository."""

    model: type[ModelT]

    # Beats are stored with native datetimes; everything else stores the JSON
    # form, where datetimes become ISO strings. Changing either would silently
    # break range queries against already-written documents.
    dump_mode: Literal["json", "python"] = "json"

    def __init__(self, collection: AsyncCollection, user_id: str):
        self.collection = collection
        self.user_id = user_id

    def _q(self, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        q: dict[str, Any] = {"user_id": self.user_id}
        if extra:
            q.update(extra)
        return q

    def _load(self, doc: dict[str, Any]) -> ModelT:
        return self.model(**serialize_from_document(doc))

    def _dump(self, model: ModelT) -> dict[str, Any]:
        data = serialize_to_document(model.model_dump(mode=self.dump_mode, exclude_none=True))
        data["user_id"] = self.user_id
        return data

    async def _find_one(self, extra: dict[str, Any] | None = None) -> ModelT | None:
        doc = await self.collection.find_one(self._q(extra))
        return self._load(doc) if doc else None

    async def _find_many(
        self,
        extra: dict[str, Any] | None = None,
        *,
        sort: tuple[str, int] | None = None,
        limit: int | None = None,
    ) -> list[ModelT]:
        cursor = self.collection.find(self._q(extra))
        if sort is not None:
            cursor = cursor.sort(*sort)
        if limit is not None:
            cursor = cursor.limit(limit)
        docs = await cursor.to_list(length=None)
        return [self._load(doc) for doc in docs]

    async def _insert(self, model: ModelT) -> ModelT:
        data = self._dump(model)
        result = await self.collection.insert_one(data)
        return self._load({**data, "_id": result.inserted_id})

    async def _replace(self, model_id: str | None, model: ModelT) -> ModelT:
        if not model_id:
            raise ValueError(f"{self.model.__name__} ID is required for update")
        await self.collection.replace_one(self._q({"_id": ObjectId(model_id)}), self._dump(model))
        return model

    async def _upsert(self, model: ModelT, extra: dict[str, Any] | None = None) -> ModelT:
        data = self._dump(model)
        data.pop("_id", None)
        result = await self.collection.find_one_and_update(
            self._q(extra),
            {"$set": data},
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        if result is None:
            # upsert=True plus AFTER means the document exists by the time the
            # driver returns, so this cannot happen; raise rather than hand a
            # None to _load and fail somewhere less obvious.
            raise RuntimeError(f"upsert of {self.model.__name__} returned no document")
        return self._load(result)

    async def _delete_one(self, extra: dict[str, Any] | None = None) -> bool:
        result = await self.collection.delete_one(self._q(extra))
        return result.deleted_count > 0

    async def _delete_all(self) -> int:
        result = await self.collection.delete_many(self._q())
        return result.deleted_count

    async def _upsert_raw(self, data: dict) -> None:
        """Import/restore path: write a document that arrived as a dict."""
        doc = serialize_to_document(dict(data))
        doc["user_id"] = self.user_id
        doc_id = doc.pop("_id", None)
        if doc_id:
            await self.collection.update_one({"_id": doc_id}, {"$set": doc}, upsert=True)
        else:
            await self.collection.insert_one(doc)


class MongoSingletonStore[ModelT: BaseModel](MongoStore[ModelT]):
    """A collection holding exactly one document per user."""

    async def get(self) -> ModelT | None:
        return await self._find_one()

    async def upsert(self, model: ModelT) -> ModelT:
        return await self._upsert(model)

    async def delete(self) -> bool:
        return await self._delete_one()


class UserRepository(Protocol):
    """User persistence. Not user-scoped — it is what defines a user."""

    async def get_by_id(self, user_id: str) -> User | None: ...
    async def get_by_email(self, email: str) -> User | None: ...
    async def get_by_sso_subject(self, issuer: str, subject: str) -> User | None: ...
    async def create(self, user: User) -> User: ...
    async def update(self, user: User) -> User: ...
    async def count(self) -> int: ...


class BeatRepository(Protocol):
    """Beat persistence operations."""

    async def get_by_id(self, beat_id: str) -> Beat: ...
    async def get_active(self) -> Beat | None: ...
    async def get_last(self) -> Beat: ...
    async def create(self, beat: Beat) -> Beat: ...
    async def update(self, beat: Beat) -> Beat: ...
    async def delete(self, beat_id: str) -> bool: ...
    async def list(
        self, project_id: str | None = None, date_filter: date | None = None
    ) -> builtins.list[Beat]: ...
    async def list_by_project(self, project_id: str) -> builtins.list[Beat]: ...
    async def list_grouped_by_project_ids(
        self, project_ids: builtins.list[str]
    ) -> dict[str, builtins.list[Beat]]: ...
    async def list_all_completed(self) -> builtins.list[Beat]: ...
    async def list_completed_in_range(self, start: date, end: date) -> builtins.list[Beat]: ...
    async def upsert(self, data: dict) -> None: ...


class ProjectRepository(Protocol):
    """Project persistence operations."""

    async def get_by_id(self, project_id: str) -> Project: ...
    async def exists(self, project_id: str) -> bool: ...
    async def create(self, project: Project) -> Project: ...
    async def update(self, project: Project) -> Project: ...
    async def list(self, archived: bool = False) -> builtins.list[Project]: ...
    async def upsert(self, data: dict) -> None: ...


class MongoBeatRepository(MongoStore[Beat], BeatRepository):
    """MongoDB implementation of BeatRepository."""

    model = Beat
    dump_mode = "python"

    async def get_by_id(self, beat_id: str) -> Beat:
        beat = await self._find_one({"_id": ObjectId(beat_id)})
        if beat is None:
            raise BeatNotFound(beat_id)
        return beat

    async def get_active(self) -> Beat | None:
        return await self._find_one({"end": None})

    async def get_last(self) -> Beat:
        doc = await self.collection.find_one(self._q(), sort=[("start", -1)])
        if not doc:
            raise NoObjectMatched()
        return self._load(doc)

    async def create(self, beat: Beat) -> Beat:
        return await self._insert(beat)

    async def update(self, beat: Beat) -> Beat:
        return await self._replace(beat.id, beat)

    async def delete(self, beat_id: str) -> bool:
        return await self._delete_one({"_id": ObjectId(beat_id)})

    async def list(
        self,
        project_id: str | None = None,
        date_filter: date | None = None,
    ) -> builtins.list[Beat]:
        extra: dict[str, Any] = {}
        if project_id:
            extra["project_id"] = project_id
        if date_filter:
            extra["start"] = {
                "$gte": datetime.combine(date_filter, datetime.min.time()),
                "$lte": datetime.combine(date_filter, datetime.max.time()),
            }
        return await self._find_many(extra)

    async def list_by_project(self, project_id: str) -> builtins.list[Beat]:
        return await self._find_many({"project_id": project_id})

    async def list_grouped_by_project_ids(
        self, project_ids: builtins.list[str]
    ) -> dict[str, builtins.list[Beat]]:
        """Fetch every beat for the given projects in one round-trip, bucketed.

        Lets list_projects collapse an N×3 fan-out into a single query whose
        result is shared across totals, this-week and last-tracked. Every
        requested id gets a key, so callers never need a None check.
        """
        # $in: [] matches nothing but still costs a query — and a fresh user
        # with no projects hits this path on every page load.
        if not project_ids:
            return {}
        beats = await self._find_many({"project_id": {"$in": project_ids}})
        buckets: dict[str, builtins.list[Beat]] = {pid: [] for pid in project_ids}
        for beat in beats:
            # setdefault rather than [] in case Mongo returns a project_id we
            # did not ask for — shouldn't happen under $in, but it is cheap.
            buckets.setdefault(beat.project_id, []).append(beat)
        return buckets

    async def list_all_completed(self) -> builtins.list[Beat]:
        return await self._find_many({"end": {"$ne": None}})

    async def list_completed_in_range(self, start: date, end: date) -> builtins.list[Beat]:
        return await self._find_many(
            {
                "start": {
                    "$gte": datetime.combine(start, datetime.min.time()),
                    "$lte": datetime.combine(end, datetime.max.time()),
                },
                "end": {"$ne": None},
            }
        )

    async def upsert(self, data: dict) -> None:
        await self._upsert_raw(data)


class MongoProjectRepository(MongoStore[Project], ProjectRepository):
    """MongoDB implementation of ProjectRepository."""

    model = Project

    async def get_by_id(self, project_id: str) -> Project:
        project = await self._find_one({"_id": ObjectId(project_id)})
        if project is None:
            raise ProjectNotFound(project_id)
        return project

    async def exists(self, project_id: str) -> bool:
        # A malformed id is a "no such project", not an error. Anything else —
        # a dropped connection, an auth failure — must surface rather than be
        # reported to the caller as a missing project.
        try:
            oid = ObjectId(project_id)
        except InvalidId:
            return False
        return await self.collection.find_one(self._q({"_id": oid})) is not None

    async def create(self, project: Project) -> Project:
        return await self._insert(project)

    async def update(self, project: Project) -> Project:
        return await self._replace(project.id, project)

    async def list(self, archived: bool = False) -> builtins.list[Project]:
        return await self._find_many({"archived": archived})

    async def upsert(self, data: dict) -> None:
        await self._upsert_raw(data)


class MongoUserRepository(UserRepository):
    """MongoDB implementation of UserRepository.

    Not a MongoStore: users are the thing user scoping is defined against, so
    there is no user_id filter to inherit.
    """

    def __init__(self, collection: AsyncCollection):
        self.collection = collection

    async def _find_one(self, query: dict[str, Any]) -> User | None:
        doc = await self.collection.find_one(query)
        return User(**serialize_from_document(doc)) if doc else None

    async def get_by_id(self, user_id: str) -> User | None:
        return await self._find_one({"_id": ObjectId(user_id)})

    async def get_by_email(self, email: str) -> User | None:
        return await self._find_one({"email": email})

    async def get_by_sso_subject(self, issuer: str, subject: str) -> User | None:
        """Find the user holding a linked home.space identity.

        Matched on the (issuer, subject) pair rather than the subject alone, so
        that a second issuer added later cannot collide with this one's DIDs.
        """
        return await self._find_one({"sso_issuer": issuer, "sso_subject": subject})

    async def create(self, user: User) -> User:
        data = serialize_to_document(user.model_dump(mode="json", exclude_none=True))
        result = await self.collection.insert_one(data)
        return User(**serialize_from_document({**data, "_id": result.inserted_id}))

    async def update(self, user: User) -> User:
        """Persist a mutated user. Requires `user.id`.

        `exclude_none` is deliberately NOT used here, unlike `create`:
        unlinking an SSO identity sets the `sso_*` fields back to None, and
        dropping them from the update would leave the old link in place — the
        user would still be signed in by a credential they had just detached.
        """
        if not user.id:
            raise ValueError("Cannot update a user without an id")
        data = serialize_to_document(user.model_dump(mode="json"))
        data.pop("_id", None)
        data.pop("id", None)
        await self.collection.update_one({"_id": ObjectId(user.id)}, {"$set": data})
        return user

    async def count(self) -> int:
        return await self.collection.count_documents({})


class WebhookRepository(Protocol):
    async def list_all(self) -> list[Webhook]: ...
    async def list_by_event(self, event: str) -> list[Webhook]: ...
    async def create(self, webhook: Webhook) -> Webhook: ...
    async def delete(self, webhook_id: str) -> bool: ...
    async def update(self, webhook: Webhook) -> Webhook: ...


class MongoWebhookRepository(MongoStore[Webhook], WebhookRepository):
    model = Webhook

    async def list_all(self) -> list[Webhook]:
        return await self._find_many()

    async def list_by_event(self, event: str) -> list[Webhook]:
        return await self._find_many({"events": event, "active": True})

    async def create(self, webhook: Webhook) -> Webhook:
        return await self._insert(webhook)

    async def delete(self, webhook_id: str) -> bool:
        return await self._delete_one({"_id": ObjectId(webhook_id)})

    async def update(self, webhook: Webhook) -> Webhook:
        return await self._replace(webhook.id, webhook)


class WeeklyDigestRepository(Protocol):
    async def get_by_week(self, week_of: date) -> WeeklyDigest | None: ...
    async def list_recent(self, limit: int = 12) -> list[WeeklyDigest]: ...
    async def upsert(self, digest: WeeklyDigest) -> WeeklyDigest: ...


class MongoWeeklyDigestRepository(MongoStore[WeeklyDigest], WeeklyDigestRepository):
    model = WeeklyDigest

    async def get_by_week(self, week_of: date) -> WeeklyDigest | None:
        return await self._find_one({"week_of": week_of.isoformat()})

    async def list_recent(self, limit: int = 12) -> list[WeeklyDigest]:
        return await self._find_many(sort=("week_of", -1), limit=limit)

    async def upsert(self, digest: WeeklyDigest) -> WeeklyDigest:
        return await self._upsert(digest, {"week_of": digest.week_of.isoformat()})


class InsightsRepository(Protocol):
    async def get(self) -> UserInsights | None: ...
    async def upsert(self, insights: UserInsights) -> UserInsights: ...
    async def dismiss_insight(self, insight_id: str) -> None: ...


class MongoInsightsRepository(MongoSingletonStore[UserInsights], InsightsRepository):
    model = UserInsights

    async def dismiss_insight(self, insight_id: str) -> None:
        # Upsert: a user who has never had patterns generated has no
        # UserInsights doc, but can still dismiss a suggestion / health item.
        # Without upsert the $addToSet would silently no-op for them. The
        # filter (user_id) seeds the created doc; dismissed_ids becomes [id].
        await self.collection.update_one(
            self._q(),
            {"$addToSet": {"dismissed_ids": insight_id}},
            upsert=True,
        )


class GitHubIntegrationRepository(Protocol):
    async def get(self) -> GitHubIntegration | None: ...
    async def upsert(self, integration: GitHubIntegration) -> GitHubIntegration: ...
    async def delete(self) -> bool: ...


class MongoGitHubIntegrationRepository(
    MongoSingletonStore[GitHubIntegration], GitHubIntegrationRepository
):
    model = GitHubIntegration


class CalendarIntegrationRepository(Protocol):
    async def get(self) -> CalendarIntegration | None: ...
    async def upsert(self, integration: CalendarIntegration) -> CalendarIntegration: ...
    async def delete(self) -> bool: ...


class MongoCalendarIntegrationRepository(
    MongoSingletonStore[CalendarIntegration], CalendarIntegrationRepository
):
    model = CalendarIntegration


class FitbitIntegrationRepository(Protocol):
    async def get(self) -> FitbitIntegration | None: ...
    async def upsert(self, integration: FitbitIntegration) -> FitbitIntegration: ...
    async def delete(self) -> bool: ...


class MongoFitbitIntegrationRepository(
    MongoSingletonStore[FitbitIntegration], FitbitIntegrationRepository
):
    model = FitbitIntegration


class OuraIntegrationRepository(Protocol):
    async def get(self) -> OuraIntegration | None: ...
    async def upsert(self, integration: OuraIntegration) -> OuraIntegration: ...
    async def delete(self) -> bool: ...


class MongoOuraIntegrationRepository(
    MongoSingletonStore[OuraIntegration], OuraIntegrationRepository
):
    model = OuraIntegration


class WeeklyPlanRepository(Protocol):
    async def get_by_week(self, week_of: date) -> WeeklyPlan | None: ...
    async def upsert(self, plan: WeeklyPlan) -> WeeklyPlan: ...


class MongoWeeklyPlanRepository(MongoStore[WeeklyPlan], WeeklyPlanRepository):
    model = WeeklyPlan

    async def get_by_week(self, week_of: date) -> WeeklyPlan | None:
        return await self._find_one({"week_of": week_of.isoformat()})

    async def upsert(self, plan: WeeklyPlan) -> WeeklyPlan:
        return await self._upsert(plan, {"week_of": plan.week_of.isoformat()})


class PairingCodeRepository(Protocol):
    async def create(self, code: PairingCode) -> PairingCode: ...
    async def find_by_hash(self, code_hash: str) -> PairingCode | None: ...
    async def delete(self, code_id: str) -> bool: ...


class MongoPairingCodeRepository(PairingCodeRepository):
    """Not user-scoped: the exchange endpoint is public and looks up by hash."""

    def __init__(self, collection: AsyncCollection):
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


class DeviceRegistrationRepository(Protocol):
    async def create(self, reg: DeviceRegistration) -> DeviceRegistration: ...
    async def get_by_device_id(self, device_id: str) -> DeviceRegistration | None: ...
    async def list_by_user(self, user_id: str) -> list[DeviceRegistration]: ...
    async def revoke(self, device_id: str, user_id: str) -> bool: ...
    async def update_last_seen(self, device_id: str) -> None: ...


class MongoDeviceRegistrationRepository(DeviceRegistrationRepository):
    """Not user-scoped: device token validation looks up by device_id first,
    across all users, and only then checks who it belongs to."""

    def __init__(self, collection: AsyncCollection):
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


class FlowWindowRepository(Protocol):
    async def create(self, window: FlowWindow) -> FlowWindow: ...
    async def list_by_range(
        self,
        start: datetime,
        end: datetime,
        project_id: str | None = None,
        editor_repo: str | None = None,
        editor_language: str | None = None,
        bundle_id: str | None = None,
        dominant_category: str | None = None,
    ) -> list[FlowWindow]: ...


class MongoFlowWindowRepository(MongoStore[FlowWindow], FlowWindowRepository):
    model = FlowWindow

    async def create(self, window: FlowWindow) -> FlowWindow:
        return await self._insert(window)

    async def list_by_range(
        self,
        start: datetime,
        end: datetime,
        project_id: str | None = None,
        editor_repo: str | None = None,
        editor_language: str | None = None,
        bundle_id: str | None = None,
        dominant_category: str | None = None,
    ) -> list[FlowWindow]:
        """Windows overlapping [start, end], narrowed by any filter given.

        Filters are AND-composed and all optional. project_id matches windows
        captured while a timer was running on that project; editor_repo and
        editor_language match what the editor heartbeat reported; bundle_id
        matches the dominant frontmost app; dominant_category matches the
        rolled-up category, e.g. "drift" for the daemon shield's distractions.
        """
        extra: dict[str, Any] = {
            "window_start": {"$gte": start.isoformat(), "$lte": end.isoformat()}
        }
        for field, value in (
            ("active_project_id", project_id),
            ("editor_repo", editor_repo),
            ("editor_language", editor_language),
            ("dominant_bundle_id", bundle_id),
            ("dominant_category", dominant_category),
        ):
            if value is not None:
                extra[field] = value
        return await self._find_many(extra, sort=("window_start", 1))


class PendingSuggestionRepository(Protocol):
    async def create(self, suggestion: PendingSuggestion) -> PendingSuggestion: ...
    async def list_recent(self, since: datetime, limit: int = 20) -> list[PendingSuggestion]: ...


class MongoPendingSuggestionRepository(MongoStore[PendingSuggestion], PendingSuggestionRepository):
    model = PendingSuggestion

    async def create(self, suggestion: PendingSuggestion) -> PendingSuggestion:
        return await self._insert(suggestion)

    async def list_recent(self, since: datetime, limit: int = 20) -> list[PendingSuggestion]:
        return await self._find_many(
            {"suggested_at": {"$gte": since.isoformat()}},
            sort=("suggested_at", -1),
            limit=limit,
        )


class SignalSummaryRepository(Protocol):
    async def upsert(self, summary: SignalSummary) -> SignalSummary: ...
    async def list_by_range(self, start: datetime, end: datetime) -> list[SignalSummary]: ...
    async def delete_all(self) -> int: ...


class MongoSignalSummaryRepository(MongoStore[SignalSummary], SignalSummaryRepository):
    model = SignalSummary

    async def upsert(self, summary: SignalSummary) -> SignalSummary:
        # Filter on the serialized hour, not summary.hour: the two render
        # differently ("...T14:00:00Z" vs "...T14:00:00+00:00") and a mismatch
        # would insert a duplicate rather than update in place.
        data = self._dump(summary)
        return await self._upsert(summary, {"device_id": data["device_id"], "hour": data["hour"]})

    async def list_by_range(self, start: datetime, end: datetime) -> list[SignalSummary]:
        return await self._find_many(
            {"hour": {"$gte": start.isoformat(), "$lte": end.isoformat()}},
            sort=("hour", 1),
        )

    async def delete_all(self) -> int:
        return await self._delete_all()


class BiometricDayRepository(Protocol):
    async def upsert(self, day: BiometricDay) -> BiometricDay: ...
    async def list_by_range(self, start: date, end: date) -> list[BiometricDay]: ...
    async def delete_all(self) -> int: ...


class MongoBiometricDayRepository(MongoStore[BiometricDay], BiometricDayRepository):
    model = BiometricDay

    async def upsert(self, day: BiometricDay) -> BiometricDay:
        data = self._dump(day)
        return await self._upsert(day, {"date": data["date"], "source": data["source"]})

    async def list_by_range(self, start: date, end: date) -> list[BiometricDay]:
        return await self._find_many(
            {"date": {"$gte": start.isoformat(), "$lte": end.isoformat()}},
            sort=("date", 1),
        )

    async def delete_all(self) -> int:
        return await self._delete_all()
