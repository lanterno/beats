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
from collections.abc import Collection, Iterable
from datetime import UTC, date, datetime
from typing import Any, Literal, NamedTuple, Protocol
from zoneinfo import ZoneInfo

from bson import ObjectId
from bson.errors import InvalidId
from pydantic import BaseModel
from pymongo import ReturnDocument
from pymongo.asynchronous.collection import AsyncCollection

from beats.domain.exceptions import (
    BeatNotFound,
    ClientNotFound,
    NoObjectMatched,
    ProjectNotFound,
)
from beats.domain.models import (
    PERSONAL_FIELDS,
    Absence,
    BalanceAdjustment,
    Beat,
    BillableOverride,
    BillingBudget,
    BillingBudgetScope,
    BiometricDay,
    CalendarIntegration,
    Client,
    DeviceRegistration,
    FitbitIntegration,
    FlowWindow,
    GitHubIntegration,
    OrgAssignment,
    OuraIntegration,
    PairingCode,
    PendingSuggestion,
    Project,
    ProjectBilling,
    ProjectOrganisation,
    ReportLink,
    SignalSummary,
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


class BeatRepository(Protocol):
    """Beat persistence operations."""

    async def get_by_id(self, beat_id: str) -> Beat: ...
    async def get_active(self) -> Beat | None: ...
    async def get_last(self) -> Beat: ...
    async def create(self, beat: Beat) -> Beat: ...
    async def update(self, beat: Beat, fields: Collection[str]) -> Beat: ...
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
    async def list_started_between(
        self, project_ids: Iterable[str], start: datetime, end: datetime
    ) -> builtins.list[Beat]: ...
    async def exists(self, beat_id: str) -> bool: ...
    async def restore(self, beat: Beat) -> None: ...
    async def ids_held_elsewhere(self, ids: Iterable[str]) -> set[str]: ...
    async def list_for_organisation(self, organisation_id: str) -> builtins.list[Beat]: ...
    async def stamp_organisation(
        self, project_id: str, organisation_id: str, since: datetime
    ) -> int: ...


class ProjectRepository(Protocol):
    """Project persistence operations."""

    async def get_by_id(self, project_id: str) -> Project: ...
    async def exists(self, project_id: str) -> bool: ...
    async def create(self, project: Project) -> Project: ...
    async def update(self, project: Project) -> Project: ...
    async def list(self, archived: bool = False) -> builtins.list[Project]: ...
    async def ids_held_elsewhere(self, ids: Iterable[str]) -> set[str]: ...


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

    async def update(self, beat: Beat, fields: Collection[str]) -> Beat:
        """Write `fields` of `beat` onto the stored beat with its id, and only
        those: a `$set`, not a replace, so a field the write does not name
        keeps what is stored, whatever happened to it since the caller read
        it. A field written as None is unset, the shape `create` stores a
        running beat's `end` in. Scoped to this user like every other write:
        an id the user does not hold is `BeatNotFound`."""
        if beat.id is None:
            raise ValueError("Beat ID is required for update")
        data = beat.model_dump(mode=self.dump_mode, include=set(fields))
        changes: dict[str, Any] = {}
        if values := {k: v for k, v in data.items() if v is not None}:
            changes["$set"] = values
        if unset := {k: "" for k, v in data.items() if v is None}:
            changes["$unset"] = unset
        doc = await self.collection.find_one_and_update(
            self._q({"_id": ObjectId(beat.id)}), changes, return_document=ReturnDocument.AFTER
        )
        if doc is None:
            raise BeatNotFound(beat.id)
        return self._load(doc)

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

    async def list_started_between(
        self, project_ids: Iterable[str], start: datetime, end: datetime
    ) -> builtins.list[Beat]:
        """The beats of these projects that started in [start, end), running
        ones included. `start` and `end` are instants — aware datetimes,
        which the driver stores and compares in UTC — not the server's dates,
        so the caller can ask for local midnight to local midnight."""
        ids = list(project_ids)
        if not ids:
            return []
        return await self._find_many(
            {"project_id": {"$in": ids}, "start": {"$gte": start, "$lt": end}}
        )

    async def list_for_organisation(self, organisation_id: str) -> builtins.list[Beat]:
        """The caller's own finished beats stamped as one organisation's
        record — what the "Acme (left)" archive and the "what Acme can see"
        page show. User-scoped like every other read here: it is the
        person's view of their own hours, whatever the stamp says."""
        return await self._find_many(
            {"organisation_id": organisation_id, "end": {"$ne": None}}, sort=("start", 1)
        )

    async def stamp_organisation(
        self, project_id: str, organisation_id: str, since: datetime
    ) -> int:
        """Mark the caller's beats on `project_id` started at or after `since`
        as `organisation_id`'s record — connecting a project over the history
        the member chose to share (docs/organisations.md, rule 4). Nothing
        before `since` is touched, and the beats stay the member's documents."""
        result = await self.collection.update_many(
            self._q({"project_id": project_id, "start": {"$gte": since}}),
            {"$set": {"organisation_id": organisation_id}},
        )
        return result.modified_count

    async def exists(self, beat_id: str) -> bool:
        # A malformed id is "no such beat", as `MongoProjectRepository.exists`
        # has it, so a route taking the id from its path answers 404.
        try:
            oid = ObjectId(beat_id)
        except InvalidId:
            return False
        return await self.collection.find_one(self._q({"_id": oid}), {"_id": 1}) is not None

    async def restore(self, beat: Beat) -> None:
        """Write a beat read from a backup, keeping its id: a replace that
        inserts when there is none, scoped to this user like every other
        write, so an id another user holds cannot move their beat across.
        Through `_dump`, so `start` and `end` are stored as dates, as a
        tracked beat's are, and the date-range reads find it."""
        if beat.id is None:
            await self._insert(beat)
            return
        await self.collection.replace_one(
            self._q({"_id": ObjectId(beat.id)}), self._dump(beat), upsert=True
        )

    async def ids_held_elsewhere(self, ids: Iterable[str]) -> set[str]:
        return await self._ids_held_elsewhere(ids)


class OrgProjectCollections(NamedTuple):
    """The two collections a member's project read joins on: their active
    assignments, and the organisations those name. Passed to
    `MongoProjectRepository` by every caller that serves a person — left
    out, the repository reads personal projects alone, which is what the
    import's ownership check and the one-off scripts want."""

    assignments: AsyncCollection
    organisations: AsyncCollection


class MongoProjectRepository(MongoStore[Project], ProjectRepository):
    """MongoDB implementation of ProjectRepository.

    The one user-scoped repository whose scope is wider than `user_id`: a
    person's projects are their own documents plus every organisation
    project they hold an active assignment to (docs/organisations.md). An
    organisation's project document carries the organisation's fields and
    no `user_id`; the member's assignment carries the personal fields
    (`PERSONAL_FIELDS`); a read merges the two into one `Project`, and a
    write splits them again. The seventeen other repositories are untouched:
    a beat on an organisation's project is still the member's own document.

    The assignments are read once per repository, so per request, and the
    organisation projects are read by id — never by organisation, so a
    member who is on one of Acme's projects cannot list the rest of Acme's.
    """

    model = Project

    def __init__(
        self, collection: AsyncCollection, user_id: str, org: OrgProjectCollections | None = None
    ):
        super().__init__(collection, user_id)
        self.org = org
        self._assigned: dict[str, OrgAssignment] | None = None
        self._organisations: dict[str, dict[str, Any]] = {}

    async def _assignments(self) -> dict[str, OrgAssignment]:
        """The caller's active assignments, by project id. One read, cached
        for the life of the repository — a request."""
        if self._assigned is None:
            self._assigned = {}
            if self.org is not None:
                docs = await self.org.assignments.find(
                    {"user_id": self.user_id, "ended_at": None}
                ).to_list(length=None)
                for doc in docs:
                    assignment = OrgAssignment(**serialize_from_document(doc))
                    self._assigned[assignment.project_id] = assignment
        return self._assigned

    async def _organisation(self, organisation_id: str) -> dict[str, Any]:
        if organisation_id not in self._organisations and self.org is not None:
            doc = await self.org.organisations.find_one(
                {"_id": ObjectId(organisation_id)}, {"name": 1, "logo_url": 1}
            )
            self._organisations[organisation_id] = doc or {}
        return self._organisations.get(organisation_id, {})

    async def _merge(self, doc: dict[str, Any], assignment: OrgAssignment) -> Project:
        """One `Project` from an organisation's document and the member's
        assignment to it."""
        data = serialize_from_document(doc)
        org = await self._organisation(assignment.organisation_id)
        for field in PERSONAL_FIELDS:
            data[field] = getattr(assignment, field)
        data.pop("organisation_id", None)
        data["organisation"] = ProjectOrganisation(
            id=assignment.organisation_id,
            name=org.get("name", "an organisation"),
            logo_url=org.get("logo_url"),
            shared_from=assignment.shared_from,
            contract_managed=assignment.contract_managed,
        )
        return Project(**data)

    async def _org_project(self, project_id: str) -> Project | None:
        """The organisation project with this id, if the caller is assigned
        to it. The query names the organisation as well as the id, so an
        assignment left pointing at a document that has since changed hands
        resolves to nothing."""
        assignment = (await self._assignments()).get(project_id)
        if assignment is None:
            return None
        doc = await self.collection.find_one(
            {"_id": ObjectId(project_id), "organisation_id": assignment.organisation_id}
        )
        return await self._merge(doc, assignment) if doc else None

    async def get_by_id(self, project_id: str) -> Project:
        # A malformed id is "no such project", like an unknown one: every route
        # under /api/projects/{id} takes the id from the path, and a 404 in the
        # envelope is the answer they all promise. `exists` below does the same.
        try:
            oid = ObjectId(project_id)
        except InvalidId:
            raise ProjectNotFound(project_id) from None
        project = await self._find_one({"_id": oid})
        if project is None:
            project = await self._org_project(project_id)
        if project is None:
            raise ProjectNotFound(project_id)
        return project

    async def exists(self, project_id: str) -> bool:
        # A malformed id is a "no such project", not an error. Anything else —
        # a dropped connection, an auth failure — must surface rather than be
        # reported to the caller as a missing project.
        try:
            await self.get_by_id(project_id)
        except ProjectNotFound:
            return False
        return True

    async def create(self, project: Project) -> Project:
        # A created project is the caller's own; `organisation` is read-only.
        return await self._insert(project.model_copy(update={"organisation": None}))

    async def update(self, project: Project) -> Project:
        """Write a project the caller holds. Their own: replaced whole, as
        before. An organisation's they are assigned to: the personal fields
        go to the assignment and the organisation's fields are not written —
        `ProjectService.update_project` has already refused a change to them.
        Which it is comes from the stored document, never from the model
        passed in."""
        if not project.id:
            raise ValueError("Project ID is required for update")
        oid = ObjectId(project.id)
        stored = await self.collection.find_one({"_id": oid}, {"user_id": 1, "organisation_id": 1})
        if stored is None:
            raise ProjectNotFound(project.id)
        if stored.get("user_id") == self.user_id:
            return await self._replace(
                project.id, project.model_copy(update={"organisation": None})
            )
        assignment = (await self._assignments()).get(project.id)
        if (
            self.org is None
            or assignment is None
            or stored.get("organisation_id") != assignment.organisation_id
        ):
            raise ProjectNotFound(project.id)
        personal = project.model_dump(mode="json", include=set(PERSONAL_FIELDS))
        await self.org.assignments.update_one(
            {"project_id": project.id, "user_id": self.user_id, "ended_at": None},
            {"$set": personal},
        )
        self._assigned = None
        return await self.get_by_id(project.id)

    async def list(self, archived: bool = False) -> builtins.list[Project]:
        own = await self._find_many({"archived": archived})
        assignments = await self._assignments()
        if not assignments:
            return own
        docs = await self.collection.find(
            {
                "_id": {"$in": [ObjectId(pid) for pid in assignments]},
                "archived": archived,
                "organisation_id": {
                    "$in": sorted({a.organisation_id for a in assignments.values()})
                },
            }
        ).to_list(length=None)
        shared = []
        for doc in docs:
            assignment = assignments[str(doc["_id"])]
            if doc.get("organisation_id") == assignment.organisation_id:
                shared.append(await self._merge(doc, assignment))
        return own + shared

    async def ids_held_elsewhere(self, ids: Iterable[str]) -> set[str]:
        # An organisation's document has no `user_id`, so it reads as held
        # elsewhere, which for a restore is the right answer: a backup cannot
        # write over an organisation's project. The import handles those
        # before asking this.
        return await self._ids_held_elsewhere(ids)


class MongoPeriodLocks:
    """The member-side answer to "is this month approved?": a read of
    `org_timesheets` for the caller's own sheet on the project. The month is
    the organisation's timezone's, read off the organisation document, and
    cached per request — the check runs on every beat write on an
    organisation project."""

    def __init__(self, db: Any, user_id: str):
        self.db = db
        self.user_id = user_id
        self._zones: dict[str, ZoneInfo] = {}

    async def _zone_of(self, project_id: str) -> ZoneInfo:
        if project_id not in self._zones:
            zone = ZoneInfo("UTC")
            project = await self.db.projects.find_one(
                {"_id": ObjectId(project_id)}, {"organisation_id": 1}
            )
            if project and project.get("organisation_id"):
                org = await self.db.organisations.find_one(
                    {"_id": ObjectId(project["organisation_id"])}, {"timezone": 1}
                )
                try:
                    zone = ZoneInfo((org or {}).get("timezone", "UTC"))
                except KeyError, ValueError:
                    zone = ZoneInfo("UTC")
            self._zones[project_id] = zone
        return self._zones[project_id]

    async def locked_day(self, project_id: str, day: date) -> date | None:
        month = day.replace(day=1)
        doc = await self.db.org_timesheets.find_one(
            {
                "project_id": project_id,
                "user_id": self.user_id,
                "month": month.isoformat(),
                "status": "approved",
            },
            {"_id": 1},
        )
        return month if doc else None

    async def locked_instant(self, project_id: str, instant: datetime) -> date | None:
        zone = await self._zone_of(project_id)
        local = (instant if instant.tzinfo else instant.replace(tzinfo=UTC)).astimezone(zone)
        return await self.locked_day(project_id, local.date())


def project_repository_for(db: Any, user_id: str) -> MongoProjectRepository:
    """A person's project repository over `db`: their own projects and the
    organisation projects they are assigned to. Every reader that serves a
    person builds it this way; the import's ownership check and a one-off
    script may build the bare repository instead."""
    return MongoProjectRepository(
        db.projects,
        user_id=user_id,
        org=OrgProjectCollections(assignments=db.org_assignments, organisations=db.organisations),
    )


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


class AbsenceRepository(Protocol):
    async def list_by_project(self, project_id: str, start: date, end: date) -> list[Absence]: ...
    async def list_all(self) -> list[Absence]: ...
    async def upsert(self, absence: Absence) -> Absence: ...
    async def delete(self, project_id: str, absence_id: str) -> bool: ...
    async def list_for_organisation(self, organisation_id: str) -> list[Absence]: ...
    async def stamp_organisation(
        self, project_id: str, organisation_id: str, since: date
    ) -> int: ...


class MongoAbsenceRepository(MongoStore[Absence], AbsenceRepository):
    model = Absence

    async def list_by_project(self, project_id: str, start: date, end: date) -> list[Absence]:
        return await self._find_many(
            {
                "project_id": project_id,
                "date": {"$gte": start.isoformat(), "$lte": end.isoformat()},
            },
            sort=("date", 1),
        )

    async def list_all(self) -> list[Absence]:
        # Every project's, for the full export: an absence outlives a kind
        # change away from day_job, and a backup keeps it all the same.
        return await self._find_many(sort=("date", 1))

    async def list_for_organisation(self, organisation_id: str) -> list[Absence]:
        """The caller's own absences stamped as one organisation's record, for
        the archive they keep after leaving. User-scoped like every read here."""
        return await self._find_many({"organisation_id": organisation_id}, sort=("date", 1))

    async def stamp_organisation(self, project_id: str, organisation_id: str, since: date) -> int:
        """As `MongoBeatRepository.stamp_organisation`: the caller's absences
        on the project from `since` on become the organisation's record."""
        result = await self.collection.update_many(
            self._q({"project_id": project_id, "date": {"$gte": since.isoformat()}}),
            {"$set": {"organisation_id": organisation_id}},
        )
        return result.modified_count

    async def upsert(self, absence: Absence) -> Absence:
        # A replace rather than the shared `$set` merge: the document IS the
        # absence, and posting a sick day over a vacation that carried a note
        # must not keep the note. The (user, project, date) unique index makes
        # this filter the document's identity.
        data = self._dump(absence)
        data.pop("_id", None)
        result = await self.collection.find_one_and_replace(
            self._q({"project_id": data["project_id"], "date": data["date"]}),
            data,
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        if result is None:
            raise RuntimeError("upsert of Absence returned no document")
        return self._load(result)

    async def delete(self, project_id: str, absence_id: str) -> bool:
        # Scoped to the project in the URL as well as the user, so a 404 means
        # "not on this project". A malformed id is "no such absence", the same
        # answer as an unknown one — the route turns False into a 404 either way.
        try:
            oid = ObjectId(absence_id)
        except InvalidId:
            return False
        return await self._delete_one({"_id": oid, "project_id": project_id})


class AdjustmentRepository(Protocol):
    async def list_by_project(
        self, project_id: str, start: date, end: date
    ) -> list[BalanceAdjustment]: ...
    async def list_all(self) -> list[BalanceAdjustment]: ...
    async def upsert(self, adjustment: BalanceAdjustment) -> BalanceAdjustment: ...
    async def delete(self, project_id: str, adjustment_id: str) -> bool: ...
    async def earliest(self, project_id: str, on_or_after: date) -> date | None: ...
    async def delete_by_project(self, project_id: str) -> int: ...


class MongoAdjustmentRepository(MongoStore[BalanceAdjustment], AdjustmentRepository):
    model = BalanceAdjustment

    async def list_by_project(
        self, project_id: str, start: date, end: date
    ) -> list[BalanceAdjustment]:
        return await self._find_many(
            {
                "project_id": project_id,
                "date": {"$gte": start.isoformat(), "$lte": end.isoformat()},
            },
            sort=("date", 1),
        )

    async def list_all(self) -> list[BalanceAdjustment]:
        # Every project's, for the full export.
        return await self._find_many(sort=("date", 1))

    async def upsert(self, adjustment: BalanceAdjustment) -> BalanceAdjustment:
        # A replace, as an absence's: the document IS the adjustment, so a
        # reset posted over a payout that carried a note must not keep the
        # note. The (user, project, date) unique index makes this filter the
        # document's identity, and the id survives the replace.
        data = self._dump(adjustment)
        data.pop("_id", None)
        result = await self.collection.find_one_and_replace(
            self._q({"project_id": data["project_id"], "date": data["date"]}),
            data,
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        if result is None:
            raise RuntimeError("upsert of BalanceAdjustment returned no document")
        return self._load(result)

    async def delete(self, project_id: str, adjustment_id: str) -> bool:
        # Scoped to the project in the URL as well as the user; a malformed
        # id is "no such adjustment", as it is for an absence.
        try:
            oid = ObjectId(adjustment_id)
        except InvalidId:
            return False
        return await self._delete_one({"_id": oid, "project_id": project_id})

    async def earliest(self, project_id: str, on_or_after: date) -> date | None:
        # ISO dates sort as strings, so the first by date is the earliest.
        doc = await self.collection.find_one(
            self._q({"project_id": project_id, "date": {"$gte": on_or_after.isoformat()}}),
            sort=[("date", 1)],
        )
        return None if doc is None else date.fromisoformat(doc["date"])

    async def delete_by_project(self, project_id: str) -> int:
        result = await self.collection.delete_many(self._q({"project_id": project_id}))
        return result.deleted_count


class ClientRepository(Protocol):
    async def get_by_id(self, client_id: str) -> Client: ...
    async def list(self, archived: bool = False) -> builtins.list[Client]: ...
    async def list_all(self) -> builtins.list[Client]: ...
    async def create(self, client: Client) -> Client: ...
    async def update(self, client: Client) -> Client: ...
    async def delete(self, client_id: str) -> bool: ...
    async def restore(self, client: Client) -> None: ...
    async def ids_held_elsewhere(self, ids: Iterable[str]) -> set[str]: ...


class MongoClientRepository(MongoStore[Client], ClientRepository):
    model = Client

    async def get_by_id(self, client_id: str) -> Client:
        # A malformed id is "no such client", like an unknown one: every route
        # under /api/clients/{id} takes it from the path and answers 404.
        try:
            oid = ObjectId(client_id)
        except InvalidId:
            raise ClientNotFound(client_id) from None
        client = await self._find_one({"_id": oid})
        if client is None:
            raise ClientNotFound(client_id)
        return client

    async def list(self, archived: bool = False) -> builtins.list[Client]:
        return await self._find_many({"archived": archived})

    async def list_all(self) -> builtins.list[Client]:
        # Archived too, for a report — an archived client keeps the months it
        # has hours in — and for the full export.
        return await self._find_many()

    async def create(self, client: Client) -> Client:
        return await self._insert(client)

    async def update(self, client: Client) -> Client:
        return await self._replace(client.id, client)

    async def delete(self, client_id: str) -> bool:
        try:
            oid = ObjectId(client_id)
        except InvalidId:
            return False
        return await self._delete_one({"_id": oid})

    async def restore(self, client: Client) -> None:
        """Write a client read from a backup, keeping its id, as
        `MongoBeatRepository.restore` writes a beat: a replace that inserts
        when there is none, scoped to this user."""
        if client.id is None:
            await self._insert(client)
            return
        await self.collection.replace_one(
            self._q({"_id": ObjectId(client.id)}), self._dump(client), upsert=True
        )

    async def ids_held_elsewhere(self, ids: Iterable[str]) -> set[str]:
        return await self._ids_held_elsewhere(ids)


class ProjectBillingRepository(Protocol):
    async def get(self, project_id: str) -> ProjectBilling | None: ...
    async def exists(self, project_id: str) -> bool: ...
    async def list_all(self) -> list[ProjectBilling]: ...
    async def list_by_client(self, client_id: str) -> list[ProjectBilling]: ...
    async def upsert(self, billing: ProjectBilling) -> ProjectBilling: ...
    async def delete(self, project_id: str) -> bool: ...


class MongoProjectBillingRepository(MongoStore[ProjectBilling], ProjectBillingRepository):
    model = ProjectBilling

    async def get(self, project_id: str) -> ProjectBilling | None:
        return await self._find_one({"project_id": project_id})

    async def exists(self, project_id: str) -> bool:
        doc = await self.collection.find_one(self._q({"project_id": project_id}), {"_id": 1})
        return doc is not None

    async def list_all(self) -> list[ProjectBilling]:
        return await self._find_many()

    async def list_by_client(self, client_id: str) -> list[ProjectBilling]:
        return await self._find_many({"client_id": client_id})

    async def upsert(self, billing: ProjectBilling) -> ProjectBilling:
        # A replace, as an absence's: the document IS the billing, so a term
        # left out of the new list must not survive in the old one. The
        # (user, project) unique index makes this filter its identity.
        data = self._dump(billing)
        data.pop("_id", None)
        result = await self.collection.find_one_and_replace(
            self._q({"project_id": data["project_id"]}),
            data,
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        if result is None:
            raise RuntimeError("upsert of ProjectBilling returned no document")
        return self._load(result)

    async def delete(self, project_id: str) -> bool:
        return await self._delete_one({"project_id": project_id})


class BillingBudgetRepository(Protocol):
    async def list_all(self) -> list[BillingBudget]: ...
    async def get(self, scope: BillingBudgetScope, scope_id: str) -> BillingBudget | None: ...
    async def upsert(self, budget: BillingBudget) -> BillingBudget: ...
    async def delete(self, scope: BillingBudgetScope, scope_id: str) -> bool: ...


class MongoBillingBudgetRepository(MongoStore[BillingBudget], BillingBudgetRepository):
    model = BillingBudget

    async def list_all(self) -> list[BillingBudget]:
        return await self._find_many()

    async def get(self, scope: BillingBudgetScope, scope_id: str) -> BillingBudget | None:
        return await self._find_one({"scope": scope.value, "scope_id": scope_id})

    async def upsert(self, budget: BillingBudget) -> BillingBudget:
        # A replace, as a project's billing: the document IS the budget, so a
        # limit in the unit it no longer has must not survive. The (user,
        # scope, scope id) unique index makes this filter its identity.
        data = self._dump(budget)
        data.pop("_id", None)
        result = await self.collection.find_one_and_replace(
            self._q({"scope": data["scope"], "scope_id": data["scope_id"]}),
            data,
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        if result is None:
            raise RuntimeError("upsert of BillingBudget returned no document")
        return self._load(result)

    async def delete(self, scope: BillingBudgetScope, scope_id: str) -> bool:
        return await self._delete_one({"scope": scope.value, "scope_id": scope_id})


class BillableOverrideRepository(Protocol):
    async def list_all(self) -> list[BillableOverride]: ...
    async def list_for(self, beat_ids: Iterable[str]) -> list[BillableOverride]: ...
    async def upsert(self, override: BillableOverride) -> BillableOverride: ...
    async def delete(self, beat_id: str) -> bool: ...


class MongoBillableOverrideRepository(MongoStore[BillableOverride], BillableOverrideRepository):
    model = BillableOverride

    async def list_all(self) -> list[BillableOverride]:
        return await self._find_many()

    async def list_for(self, beat_ids: Iterable[str]) -> list[BillableOverride]:
        ids = list(beat_ids)
        if not ids:
            return []
        return await self._find_many({"beat_id": {"$in": ids}})

    async def upsert(self, override: BillableOverride) -> BillableOverride:
        # A replace keyed on the beat, which the (user, beat) unique index
        # makes the document's identity.
        data = self._dump(override)
        data.pop("_id", None)
        result = await self.collection.find_one_and_replace(
            self._q({"beat_id": data["beat_id"]}),
            data,
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        if result is None:
            raise RuntimeError("upsert of BillableOverride returned no document")
        return self._load(result)

    async def delete(self, beat_id: str) -> bool:
        return await self._delete_one({"beat_id": beat_id})


class ReportLinkRepository(Protocol):
    async def list_for_client(self, client_id: str) -> list[ReportLink]: ...
    async def create(self, link: ReportLink) -> ReportLink: ...
    async def delete(self, client_id: str, link_id: str) -> bool: ...
    async def delete_for_client(self, client_id: str) -> int: ...


class MongoReportLinkRepository(MongoStore[ReportLink], ReportLinkRepository):
    """The owner's side of report links: list, mint and revoke. User-scoped
    like every other billing collection. The public read goes through
    `MongoReportLinkLookup`, which is not."""

    model = ReportLink

    async def list_for_client(self, client_id: str) -> list[ReportLink]:
        return await self._find_many({"client_id": client_id}, sort=("created_at", -1))

    async def create(self, link: ReportLink) -> ReportLink:
        return await self._insert(link)

    async def delete(self, client_id: str, link_id: str) -> bool:
        # Keyed on the client as well as the id, so a link cannot be revoked
        # through the wrong client's path. A malformed id is "no such link",
        # as an unknown one is: the route answers 204 either way, since with
        # no link there is nothing left to clear.
        try:
            oid = ObjectId(link_id)
        except InvalidId:
            return False
        return await self._delete_one({"_id": oid, "client_id": client_id})

    async def delete_for_client(self, client_id: str) -> int:
        """Every link on one client, for when the client is deleted: a link
        whose client has gone would serve nothing, and must not linger as a
        live URL."""
        result = await self.collection.delete_many(self._q({"client_id": client_id}))
        return result.deleted_count


class OwnedReportLink(NamedTuple):
    """A resolved token: the link, and the account whose hours it serves.

    The owner is carried beside the link rather than on it because
    `user_id` is a column of every document and a field of no model — the
    scoping lives in `MongoStore`, not in the domain.
    """

    link: ReportLink
    user_id: str


class ReportLinkLookup(Protocol):
    async def find_by_token(self, token: str) -> OwnedReportLink | None: ...


class MongoReportLinkLookup(ReportLinkLookup):
    """Not user-scoped: the public report endpoint has no session, and the
    owner is not known until the token resolves. This is the only read in the
    system whose `user_id` comes from a stored record rather than a token —
    see the call site in `api/routers/reports.py`.
    """

    def __init__(self, collection: AsyncCollection):
        self.collection = collection

    async def find_by_token(self, token: str) -> OwnedReportLink | None:
        # An exact match on the unique-indexed token. No regex, no prefix: the
        # token is the whole secret and nothing about it is guessed at here.
        doc = await self.collection.find_one({"token": token})
        if not doc:
            return None
        owner = doc.get("user_id")
        if not isinstance(owner, str):
            # A link with no owner can serve nothing, and guessing one would
            # be the worst possible guess. Treat it as no link at all.
            return None
        return OwnedReportLink(ReportLink(**serialize_from_document(doc)), owner)
