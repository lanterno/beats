"""Persistence for beats, projects and the approved month's lock.

Split out of `repositories.py` at the size ceiling (CLAUDE.md § Conventions).
`MongoProjectRepository` is the one user-scoped repository whose scope is
wider than `user_id`: it merges in the organisation projects the member is
assigned to (docs/organisations.md).
"""

import builtins
from collections.abc import Collection, Iterable
from datetime import UTC, date, datetime
from typing import Any, NamedTuple, Protocol
from zoneinfo import ZoneInfo

from bson import ObjectId
from bson.errors import InvalidId
from pymongo import ReturnDocument
from pymongo.asynchronous.collection import AsyncCollection

from beats.domain.exceptions import (
    BeatNotFound,
    NoObjectMatched,
    ProjectNotFound,
)
from beats.domain.models import (
    PERSONAL_FIELDS,
    Beat,
    OrgAssignment,
    Project,
    ProjectOrganisation,
)
from beats.infrastructure.repositories import (
    MongoStore,
    serialize_from_document,
)


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
    async def list_by_project(
        self, project_id: str, since: datetime | None = None
    ) -> builtins.list[Beat]: ...
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

    async def list_by_project(
        self, project_id: str, since: datetime | None = None
    ) -> builtins.list[Beat]:
        """A project's sessions, those that started at or after `since` when
        one is given.

        The bound is served by the `(user_id, project_id, start)` index, so a
        caller that knows the earliest day it can use — the ledger does, and
        its reads were the API's slowest (#376) — fetches and parses only
        those documents instead of every session ever tracked on the project.
        """
        query: dict[str, Any] = {"project_id": project_id}
        if since is not None:
            query["start"] = {"$gte": since}
        return await self._find_many(query)

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
    write splits them again. The other user-scoped repositories are untouched:
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
            private_before=assignment.private_before,
            private_before_day=assignment.private_before_day,
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

    async def mark_terms_changed(self, project_id: str, from_day: date, at: datetime) -> int:
        """The member's own contract write marking the approved months it
        moves (docs/organisations.md, decision 23). Scoped to the caller, as
        every read here is: a service that writes projects gets this one
        write and nothing wider."""
        return await mark_timesheets_superseded(
            self.db.org_timesheets,
            project_id=project_id,
            user_id=self.user_id,
            from_day=from_day,
            by=self.user_id,
            at=at,
        )


async def mark_timesheets_superseded(
    timesheets: Any,
    *,
    project_id: str,
    user_id: str,
    from_day: date,
    by: str,
    at: datetime,
    organisation_id: str | None = None,
) -> int:
    """Mark every approved sheet of one member on one project whose month
    ends on or after `from_day`: the contract behind it changed. How many.

    The one write both contract writes share — the member's through
    `MongoPeriodLocks`, the employer's through `MongoOrganisationStore` — so
    the two cannot drift. `status` is left alone on purpose: the month is
    still approved and still locked, and `MongoPeriodLocks.locked_day` keys
    on that status, so a `superseded` status would unlock it. The sheet
    carries the mark (`superseded_at`, `superseded_by`) and its history
    carries the step, so the sheet reads in order — submitted, approved,
    terms changed — which is what a works council asks to see.
    """
    query: dict[str, Any] = {
        "project_id": project_id,
        "user_id": user_id,
        "status": "approved",
        "month": {"$gte": from_day.replace(day=1).isoformat()},
    }
    if organisation_id is not None:
        query["organisation_id"] = organisation_id
    result = await timesheets.update_many(
        query,
        {
            "$set": {"superseded_at": at.isoformat(), "superseded_by": by},
            "$push": {"history": {"at": at.isoformat(), "by": by, "action": "terms_changed"}},
        },
    )
    return result.modified_count


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
