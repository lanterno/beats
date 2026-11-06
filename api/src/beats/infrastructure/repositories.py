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

from collections.abc import Iterable
from datetime import UTC, date, datetime
from typing import Any, Literal, Protocol

from bson import ObjectId
from pydantic import BaseModel
from pymongo import ReturnDocument
from pymongo.asynchronous.collection import AsyncCollection

from beats.domain.models import (
    CalendarIntegration,
    DeviceRegistration,
    FitbitIntegration,
    GitHubIntegration,
    OuraIntegration,
    PairingCode,
    SSOFlow,
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

    async def _ids_held_elsewhere(self, ids: Iterable[str]) -> set[str]:
        """Which of these ids another user's document already has. Unscoped on
        purpose, and the one read that is: a restore keeps a record's id, so
        an id someone else holds has to be found before anything is written.
        The ids must already be valid ObjectIds."""
        oids = [ObjectId(i) for i in ids]
        if not oids:
            return set()
        docs = await self.collection.find(
            {"_id": {"$in": oids}, "user_id": {"$ne": self.user_id}}, {"_id": 1}
        ).to_list(length=None)
        return {str(doc["_id"]) for doc in docs}


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
    async def get_by_identity(self, issuer: str, subject: str) -> User | None: ...
    async def create(self, user: User) -> User: ...
    async def update(self, user: User) -> User: ...
    async def count(self) -> int: ...


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

    async def get_by_identity(self, issuer: str, subject: str) -> User | None:
        """Find the user holding a linked identity.

        Matched on the (issuer, subject) pair within one array element: a
        `sub` is only unique within its issuer.
        """
        return await self._find_one(
            {"identities": {"$elemMatch": {"issuer": issuer, "subject": subject}}}
        )

    async def create(self, user: User) -> User:
        data = serialize_to_document(user.model_dump(mode="json", exclude_none=True))
        result = await self.collection.insert_one(data)
        return User(**serialize_from_document({**data, "_id": result.inserted_id}))

    async def update(self, user: User) -> User:
        """Persist a mutated user. Requires `user.id`.

        `exclude_none` is deliberately NOT used here, unlike `create`: a field
        set back to None has to reach the document, or the old value stays.
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
    async def upsert(self, insights: UserInsights, /) -> UserInsights: ...
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
    async def upsert(self, integration: GitHubIntegration, /) -> GitHubIntegration: ...
    async def delete(self) -> bool: ...


class MongoGitHubIntegrationRepository(
    MongoSingletonStore[GitHubIntegration], GitHubIntegrationRepository
):
    model = GitHubIntegration


class CalendarIntegrationRepository(Protocol):
    async def get(self) -> CalendarIntegration | None: ...
    async def upsert(self, integration: CalendarIntegration, /) -> CalendarIntegration: ...
    async def delete(self) -> bool: ...


class MongoCalendarIntegrationRepository(
    MongoSingletonStore[CalendarIntegration], CalendarIntegrationRepository
):
    model = CalendarIntegration


class FitbitIntegrationRepository(Protocol):
    async def get(self) -> FitbitIntegration | None: ...
    async def upsert(self, integration: FitbitIntegration, /) -> FitbitIntegration: ...
    async def delete(self) -> bool: ...


class MongoFitbitIntegrationRepository(
    MongoSingletonStore[FitbitIntegration], FitbitIntegrationRepository
):
    model = FitbitIntegration


class OuraIntegrationRepository(Protocol):
    async def get(self) -> OuraIntegration | None: ...
    async def upsert(self, integration: OuraIntegration, /) -> OuraIntegration: ...
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
        # The dates stay BSON dates (not the ISO strings `model_dump(mode=
        # "json")` would make them): the TTL index only expires dates, and a
        # string `expires_at` kept every code ever issued. Codes stored as
        # strings before this are converted at startup
        # (`migrations.date_pairing_codes`).
        data = serialize_to_document(code.model_dump(exclude_none=True))
        result = await self.collection.insert_one(data)
        return PairingCode(**serialize_from_document({**data, "_id": result.inserted_id}))

    async def find_by_hash(self, code_hash: str) -> PairingCode | None:
        # The TTL monitor runs about once a minute, hence the explicit expiry
        # check. A date, since `$gt` matches only values of its own BSON type.
        doc = await self.collection.find_one(
            {
                "code_hash": code_hash,
                "expires_at": {"$gt": datetime.now(UTC)},
            }
        )
        if not doc:
            return None
        return PairingCode(**serialize_from_document(doc))

    async def delete(self, code_id: str) -> bool:
        result = await self.collection.delete_one({"_id": ObjectId(code_id)})
        return result.deleted_count > 0


class SSOFlowRepository(Protocol):
    async def create(self, flow: SSOFlow) -> None: ...
    async def take(self, state_hash: str) -> SSOFlow | None: ...


class MongoSSOFlowRepository(SSOFlowRepository):
    """Not user-scoped: a sign-in finishes before anyone is signed in."""

    def __init__(self, collection: AsyncCollection):
        self.collection = collection

    async def create(self, flow: SSOFlow) -> None:
        # `expires_at` stays a BSON date (not the ISO string `model_dump(mode=
        # "json")` would make it): the TTL index only expires dates.
        await self.collection.insert_one({"_id": flow.state_hash, **flow.model_dump()})

    async def take(self, state_hash: str) -> SSOFlow | None:
        """Remove and return the flow, if it exists and hasn't expired.

        One atomic delete, so a state can finish one sign-in and no more,
        even when two requests carry it at once. The TTL monitor runs about
        once a minute, hence the explicit expiry check.
        """
        doc = await self.collection.find_one_and_delete(
            {"_id": state_hash, "expires_at": {"$gt": datetime.now(UTC)}}
        )
        if doc is None:
            return None
        doc.pop("_id")
        return SSOFlow(**doc)


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
        """Stamp when the device last authenticated, at most once a day.

        A BSON datetime, not the ISO string this used to write (the bug
        `date_pairing_codes` had to fix for pairing codes): a string never
        matches the `$lt` below, so the once-a-day condition would stop
        holding. Called by the auth middleware on a device-cache miss.
        """
        now = datetime.now(UTC)
        day_start = datetime(now.year, now.month, now.day, tzinfo=UTC)
        await self.collection.update_one(
            {
                "device_id": device_id,
                "$or": [{"last_seen": None}, {"last_seen": {"$lt": day_start}}],
            },
            {"$set": {"last_seen": now}},
        )
