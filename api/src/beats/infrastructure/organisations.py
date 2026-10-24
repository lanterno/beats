"""Persistence for organisations — the one part of the system not scoped by
`user_id` (docs/organisations.md).

Every query here names an organisation, and nothing else: an organisation
is found by its id, its members, invites, requests, assignments and audit by
`organisation_id`, and its projects by `organisation_id` on the project
document. The wall of rule 3 — hours, not the person — is kept by
`MongoOrganisationRecords`, which reads beats and absences by the
organisation's own stamp (`organisation_id` on the document) and reaches no
other collection: a flow score, a tag, a biometric or a personal project is
unreachable because the query for it is never made, not because a filter
removed it afterwards. The pattern is 1c's `MongoReportLinkLookup`: one
narrow unscoped class per cross-user read, with the service saying at the
call site why the account did not come from a token.
"""

from collections.abc import Iterable
from datetime import date, datetime
from typing import Any

from bson import ObjectId
from bson.errors import InvalidId
from pydantic import BaseModel
from pymongo import ReturnDocument
from pymongo.asynchronous.collection import AsyncCollection
from pymongo.asynchronous.database import AsyncDatabase

from beats.domain.models import (
    ORGANISATION_FIELDS,
    PERSONAL_FIELDS,
    Absence,
    BalanceAdjustment,
    Beat,
    JoinDecision,
    MembershipEnd,
    MemberTotals,
    Organisation,
    OrgAssignment,
    OrgAuditEvent,
    OrgInvite,
    OrgJoinRequest,
    OrgMembership,
    OrgProject,
    OrgRole,
    Project,
)
from beats.infrastructure.repositories import serialize_from_document, serialize_to_document


def oid_or_none(value: str) -> ObjectId | None:
    try:
        return ObjectId(value)
    except InvalidId, TypeError:
        return None


def _load[T: BaseModel](model: type[T], doc: dict[str, Any]) -> T:
    return model(**serialize_from_document(doc))


def _dump(model: BaseModel) -> dict[str, Any]:
    return serialize_to_document(model.model_dump(mode="json", exclude_none=True))


def _org_project(doc: dict[str, Any]) -> OrgProject:
    return OrgProject(**{**serialize_from_document(doc), "id": str(doc["_id"])})


class MongoOrganisationStore:
    """Organisations, their members, invites, join requests, assignments,
    projects and audit log. Scoped by organisation on every read and write
    that has one; the few that do not (an invite by token, a person's own
    memberships) are named as such."""

    def __init__(self, db: AsyncDatabase):
        self.organisations: AsyncCollection = db.organisations
        self.members: AsyncCollection = db.org_members
        self.invites: AsyncCollection = db.org_invites
        self.requests: AsyncCollection = db.org_join_requests
        self.assignments: AsyncCollection = db.org_assignments
        self.audit: AsyncCollection = db.org_audit
        self.projects: AsyncCollection = db.projects

    # --- organisations -------------------------------------------------

    async def create_organisation(self, organisation: Organisation) -> Organisation:
        data = _dump(organisation)
        result = await self.organisations.insert_one(data)
        return _load(Organisation, {**data, "_id": result.inserted_id})

    async def get_organisation(self, organisation_id: str) -> Organisation | None:
        oid = oid_or_none(organisation_id)
        if oid is None:
            return None
        doc = await self.organisations.find_one({"_id": oid})
        return _load(Organisation, doc) if doc else None

    async def get_organisations(self, ids: Iterable[str]) -> dict[str, Organisation]:
        oids = [o for o in (oid_or_none(i) for i in ids) if o is not None]
        if not oids:
            return {}
        docs = await self.organisations.find({"_id": {"$in": oids}}).to_list(length=None)
        return {str(doc["_id"]): _load(Organisation, doc) for doc in docs}

    async def update_organisation(self, organisation: Organisation) -> Organisation:
        if organisation.id is None:
            raise ValueError("Organisation ID is required for update")
        data = _dump(organisation)
        data.pop("_id", None)
        # `exclude_none` leaves out a field cleared to None; unset those so a
        # removed logo or region does not linger.
        unset = {
            field: ""
            for field in ("logo_url", "holiday_country", "holiday_subdivision")
            if getattr(organisation, field) is None
        }
        changes: dict[str, Any] = {"$set": data}
        if unset:
            changes["$unset"] = unset
        await self.organisations.update_one({"_id": ObjectId(organisation.id)}, changes)
        return organisation

    # --- memberships -----------------------------------------------------

    async def membership(self, organisation_id: str, user_id: str) -> OrgMembership | None:
        """The person's membership of the organisation, active or ended."""
        doc = await self.members.find_one({"organisation_id": organisation_id, "user_id": user_id})
        return _load(OrgMembership, doc) if doc else None

    async def memberships_of(self, user_id: str) -> list[OrgMembership]:
        """Every membership one person has or had — not scoped by
        organisation, because it is the person asking about themselves."""
        docs = (
            await self.members.find({"user_id": user_id}).sort("joined_at", 1).to_list(length=None)
        )
        return [_load(OrgMembership, doc) for doc in docs]

    async def list_members(
        self, organisation_id: str, *, active_only: bool = True
    ) -> list[OrgMembership]:
        query: dict[str, Any] = {"organisation_id": organisation_id}
        if active_only:
            query["left_at"] = None
        docs = await self.members.find(query).sort("joined_at", 1).to_list(length=None)
        return [_load(OrgMembership, doc) for doc in docs]

    async def count_owners(self, organisation_id: str) -> int:
        return await self.members.count_documents(
            {"organisation_id": organisation_id, "role": OrgRole.OWNER.value, "left_at": None}
        )

    async def open_membership(self, membership: OrgMembership) -> OrgMembership:
        """Add a member, or reopen the membership they had: one document per
        person per organisation, so a person who left and comes back has one
        history there."""
        data = _dump(membership)
        data.pop("_id", None)
        data["left_at"] = None
        data["left_reason"] = None
        doc = await self.members.find_one_and_update(
            {"organisation_id": membership.organisation_id, "user_id": membership.user_id},
            {"$set": data},
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        if doc is None:
            raise RuntimeError("upsert of OrgMembership returned no document")
        return _load(OrgMembership, doc)

    async def set_role(
        self, organisation_id: str, user_id: str, role: OrgRole
    ) -> OrgMembership | None:
        doc = await self.members.find_one_and_update(
            {"organisation_id": organisation_id, "user_id": user_id, "left_at": None},
            {"$set": {"role": role.value}},
            return_document=ReturnDocument.AFTER,
        )
        return _load(OrgMembership, doc) if doc else None

    async def end_membership(
        self, organisation_id: str, user_id: str, reason: MembershipEnd, at: datetime
    ) -> OrgMembership | None:
        doc = await self.members.find_one_and_update(
            {"organisation_id": organisation_id, "user_id": user_id, "left_at": None},
            {"$set": {"left_at": at.isoformat(), "left_reason": reason.value}},
            return_document=ReturnDocument.AFTER,
        )
        return _load(OrgMembership, doc) if doc else None

    # --- invites -------------------------------------------------------------

    async def create_invite(self, invite: OrgInvite) -> OrgInvite:
        data = _dump(invite)
        result = await self.invites.insert_one(data)
        return _load(OrgInvite, {**data, "_id": result.inserted_id})

    async def list_invites(self, organisation_id: str) -> list[OrgInvite]:
        docs = (
            await self.invites.find({"organisation_id": organisation_id})
            .sort("created_at", -1)
            .to_list(length=None)
        )
        return [_load(OrgInvite, doc) for doc in docs]

    async def invite_by_token(self, token: str) -> OrgInvite | None:
        """The one read keyed on something other than an organisation: the
        joiner presents a token and nothing else, as a report link's reader
        does. An exact match on the unique-indexed token."""
        doc = await self.invites.find_one({"token": token})
        return _load(OrgInvite, doc) if doc else None

    async def invites_for_email(self, email: str) -> list[OrgInvite]:
        """Invitations addressed to one address, open or not; the service
        filters to the open ones with its own clock."""
        docs = await self.invites.find({"email": email}).sort("created_at", -1).to_list(length=None)
        return [_load(OrgInvite, doc) for doc in docs]

    async def get_invite(self, organisation_id: str, invite_id: str) -> OrgInvite | None:
        oid = oid_or_none(invite_id)
        if oid is None:
            return None
        doc = await self.invites.find_one({"_id": oid, "organisation_id": organisation_id})
        return _load(OrgInvite, doc) if doc else None

    async def mark_invite_accepted(self, invite_id: str, user_id: str, at: datetime) -> None:
        await self.invites.update_one(
            {"_id": ObjectId(invite_id)},
            {"$set": {"accepted_at": at.isoformat(), "accepted_by": user_id}},
        )

    async def revoke_invite(self, organisation_id: str, invite_id: str, at: datetime) -> bool:
        oid = oid_or_none(invite_id)
        if oid is None:
            return False
        result = await self.invites.update_one(
            {"_id": oid, "organisation_id": organisation_id, "revoked_at": None},
            {"$set": {"revoked_at": at.isoformat()}},
        )
        return result.modified_count > 0

    # --- join requests -----------------------------------------------------

    async def create_request(self, request: OrgJoinRequest) -> OrgJoinRequest:
        data = _dump(request)
        result = await self.requests.insert_one(data)
        return _load(OrgJoinRequest, {**data, "_id": result.inserted_id})

    async def pending_request(self, organisation_id: str, user_id: str) -> OrgJoinRequest | None:
        doc = await self.requests.find_one(
            {"organisation_id": organisation_id, "user_id": user_id, "decided_at": None}
        )
        return _load(OrgJoinRequest, doc) if doc else None

    async def list_requests(self, organisation_id: str) -> list[OrgJoinRequest]:
        docs = (
            await self.requests.find({"organisation_id": organisation_id, "decided_at": None})
            .sort("requested_at", 1)
            .to_list(length=None)
        )
        return [_load(OrgJoinRequest, doc) for doc in docs]

    async def decide_request(
        self,
        organisation_id: str,
        request_id: str,
        decision: JoinDecision,
        decided_by: str,
        at: datetime,
    ) -> OrgJoinRequest | None:
        oid = oid_or_none(request_id)
        if oid is None:
            return None
        doc = await self.requests.find_one_and_update(
            {"_id": oid, "organisation_id": organisation_id, "decided_at": None},
            {
                "$set": {
                    "decided_at": at.isoformat(),
                    "decision": decision.value,
                    "decided_by": decided_by,
                }
            },
            return_document=ReturnDocument.AFTER,
        )
        return _load(OrgJoinRequest, doc) if doc else None

    # --- projects ------------------------------------------------------------

    async def create_project(self, organisation_id: str, fields: dict[str, Any]) -> OrgProject:
        """An organisation's own project: the organisation's fields, its id,
        and no `user_id` — nothing personal lives on the document, which
        reaches every paired device of every assigned member."""
        data = {k: v for k, v in fields.items() if k in ORGANISATION_FIELDS and v is not None}
        data.setdefault("archived", False)
        data["organisation_id"] = organisation_id
        result = await self.projects.insert_one(data)
        return _org_project({**data, "_id": result.inserted_id})

    async def list_projects(
        self, organisation_id: str, archived: bool | None = None
    ) -> list[OrgProject]:
        query: dict[str, Any] = {"organisation_id": organisation_id}
        if archived is not None:
            query["archived"] = archived
        docs = await self.projects.find(query).sort("name", 1).to_list(length=None)
        return [_org_project(doc) for doc in docs]

    async def get_project(self, organisation_id: str, project_id: str) -> OrgProject | None:
        oid = oid_or_none(project_id)
        if oid is None:
            return None
        doc = await self.projects.find_one({"_id": oid, "organisation_id": organisation_id})
        return _org_project(doc) if doc else None

    async def update_project(
        self, organisation_id: str, project_id: str, fields: dict[str, Any]
    ) -> OrgProject | None:
        """Write the organisation's fields of one of its projects. A field
        sent as None is unset; one not sent is kept."""
        oid = oid_or_none(project_id)
        if oid is None:
            return None
        values = {k: v for k, v in fields.items() if k in ORGANISATION_FIELDS and v is not None}
        unset = {k: "" for k, v in fields.items() if k in ORGANISATION_FIELDS and v is None}
        changes: dict[str, Any] = {}
        if values:
            changes["$set"] = values
        if unset:
            changes["$unset"] = unset
        if not changes:
            doc = await self.projects.find_one({"_id": oid, "organisation_id": organisation_id})
        else:
            doc = await self.projects.find_one_and_update(
                {"_id": oid, "organisation_id": organisation_id},
                changes,
                return_document=ReturnDocument.AFTER,
            )
        return _org_project(doc) if doc else None

    async def personal_project(self, project_id: str, user_id: str) -> Project | None:
        """One of a person's own projects, read for connecting it: the
        document as stored, `user_id` and all."""
        oid = oid_or_none(project_id)
        if oid is None:
            return None
        doc = await self.projects.find_one({"_id": oid, "user_id": user_id})
        return _load(Project, doc) if doc else None

    async def hand_project_to_organisation(
        self, project_id: str, user_id: str, organisation_id: str
    ) -> bool:
        """Connect: the document changes hands. The organisation's fields
        stay on it; the personal ones are unset — they have gone to the
        member's assignment, written just before — and `user_id` goes, so
        the project has exactly one owner (rule 2). The filter names the
        person, so it can only move a project of theirs."""
        result = await self.projects.update_one(
            {"_id": ObjectId(project_id), "user_id": user_id},
            {
                "$set": {"organisation_id": organisation_id},
                "$unset": {"user_id": "", **dict.fromkeys(PERSONAL_FIELDS, "")},
            },
        )
        return result.modified_count > 0

    async def project_names(
        self, organisation_id: str, project_ids: Iterable[str]
    ) -> dict[str, OrgProject]:
        """Name and colour of some of the organisation's projects, for a
        former member's archive: by id, so a person who left can name the
        projects they tracked on and no other."""
        oids = [o for o in (oid_or_none(i) for i in project_ids) if o is not None]
        if not oids:
            return {}
        docs = await self.projects.find(
            {"_id": {"$in": oids}, "organisation_id": organisation_id}
        ).to_list(length=None)
        return {str(doc["_id"]): _org_project(doc) for doc in docs}

    # --- assignments ---------------------------------------------------------

    async def assignment(
        self, organisation_id: str, project_id: str, user_id: str
    ) -> OrgAssignment | None:
        doc = await self.assignments.find_one(
            {"organisation_id": organisation_id, "project_id": project_id, "user_id": user_id}
        )
        return _load(OrgAssignment, doc) if doc else None

    async def list_assignments(
        self,
        organisation_id: str,
        *,
        project_id: str | None = None,
        user_id: str | None = None,
        active_only: bool = True,
    ) -> list[OrgAssignment]:
        query: dict[str, Any] = {"organisation_id": organisation_id}
        if project_id is not None:
            query["project_id"] = project_id
        if user_id is not None:
            query["user_id"] = user_id
        if active_only:
            query["ended_at"] = None
        docs = await self.assignments.find(query).sort("assigned_at", 1).to_list(length=None)
        return [_load(OrgAssignment, doc) for doc in docs]

    async def open_assignment(self, assignment: OrgAssignment) -> OrgAssignment:
        """Assign, or reopen an ended assignment: one document per member per
        project. Reopening replaces the personal fields with the ones sent
        (empty on a plain assignment; the project's own on a connect)."""
        data = _dump(assignment)
        data.pop("_id", None)
        data["ended_at"] = None
        for field in PERSONAL_FIELDS:
            data.setdefault(field, None)
        unset = {k: "" for k, v in list(data.items()) if v is None}
        for k in unset:
            data.pop(k)
        changes: dict[str, Any] = {"$set": data}
        if unset:
            changes["$unset"] = unset
        doc = await self.assignments.find_one_and_update(
            {"project_id": assignment.project_id, "user_id": assignment.user_id},
            changes,
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        if doc is None:
            raise RuntimeError("upsert of OrgAssignment returned no document")
        return _load(OrgAssignment, doc)

    async def end_assignments(
        self, organisation_id: str, user_id: str, at: datetime, project_id: str | None = None
    ) -> int:
        query: dict[str, Any] = {
            "organisation_id": organisation_id,
            "user_id": user_id,
            "ended_at": None,
        }
        if project_id is not None:
            query["project_id"] = project_id
        result = await self.assignments.update_many(query, {"$set": {"ended_at": at.isoformat()}})
        return result.modified_count

    # --- audit -------------------------------------------------------------------

    async def record(self, event: OrgAuditEvent) -> None:
        await self.audit.insert_one(_dump(event))


class MongoOrganisationRecords:
    """The organisation's read of its working-time record, and the only one.

    Every query names the organisation's stamp (`organisation_id` on the
    beat or the absence) and the project ids the organisation owns, and
    where the reader is one member looking at their own slice, their
    `user_id` as well. Only finished beats: a running one is nobody's
    record yet, and the read says nothing about now (decision 2). The
    adjustments are read by project and member, since they carry no stamp:
    they are read to compute the balance the member's contract already
    shows the organisation, and for nothing else.
    """

    def __init__(self, db: AsyncDatabase):
        self.beats: AsyncCollection = db.timeLogs
        self.absences: AsyncCollection = db.absences
        self.adjustments: AsyncCollection = db.balance_adjustments

    def _beats_query(
        self, organisation_id: str, project_ids: Iterable[str], user_id: str | None
    ) -> dict[str, Any]:
        query: dict[str, Any] = {
            "organisation_id": organisation_id,
            "project_id": {"$in": sorted(project_ids)},
            "end": {"$ne": None},
        }
        if user_id is not None:
            query["user_id"] = user_id
        return query

    async def beats_between(
        self,
        organisation_id: str,
        project_ids: Iterable[str],
        start: datetime,
        end: datetime,
        *,
        user_id: str | None = None,
    ) -> list[tuple[str, Beat]]:
        """Finished beats started in [start, end) on these projects, each with
        the member whose it is."""
        query = self._beats_query(organisation_id, project_ids, user_id)
        if not query["project_id"]["$in"]:
            return []
        query["start"] = {"$gte": start, "$lt": end}
        docs = await self.beats.find(query).sort("start", 1).to_list(length=None)
        return [(doc["user_id"], _load(Beat, doc)) for doc in docs]

    async def beats_of_member(
        self, organisation_id: str, project_id: str, user_id: str
    ) -> list[Beat]:
        """Every finished beat of one member on one project — what a balance
        is computed from."""
        query = self._beats_query(organisation_id, [project_id], user_id)
        docs = await self.beats.find(query).sort("start", 1).to_list(length=None)
        return [_load(Beat, doc) for doc in docs]

    async def totals(
        self, organisation_id: str, project_ids: Iterable[str], *, user_id: str | None = None
    ) -> dict[tuple[str, str], MemberTotals]:
        """All-time totals per (project, member): how many entries, how many
        hours, the first start and the last end."""
        query = self._beats_query(organisation_id, project_ids, user_id)
        if not query["project_id"]["$in"]:
            return {}
        pipeline = [
            {"$match": query},
            {
                "$group": {
                    "_id": {"project_id": "$project_id", "user_id": "$user_id"},
                    "entries": {"$sum": 1},
                    "ms": {"$sum": {"$subtract": ["$end", "$start"]}},
                    "first": {"$min": "$start"},
                    "last": {"$max": "$end"},
                }
            },
        ]
        cursor = await self.beats.aggregate(pipeline)
        rows = await cursor.to_list(length=None)
        out: dict[tuple[str, str], MemberTotals] = {}
        for row in rows:
            key = (row["_id"]["project_id"], row["_id"]["user_id"])
            out[key] = MemberTotals(
                entries=int(row["entries"]),
                hours=round(float(row["ms"]) / 3_600_000, 2),
                first=row.get("first"),
                last=row.get("last"),
            )
        return out

    async def absences_between(
        self,
        organisation_id: str,
        project_ids: Iterable[str],
        start: date,
        end: date,
        *,
        user_id: str | None = None,
    ) -> list[tuple[str, Absence]]:
        ids = sorted(project_ids)
        if not ids:
            return []
        query: dict[str, Any] = {
            "organisation_id": organisation_id,
            "project_id": {"$in": ids},
            "date": {"$gte": start.isoformat(), "$lte": end.isoformat()},
        }
        if user_id is not None:
            query["user_id"] = user_id
        docs = await self.absences.find(query).sort("date", 1).to_list(length=None)
        return [(doc["user_id"], _load(Absence, doc)) for doc in docs]

    async def adjustments_of_member(
        self, project_id: str, user_id: str, start: date, end: date
    ) -> list[BalanceAdjustment]:
        docs = (
            await self.adjustments.find(
                {
                    "project_id": project_id,
                    "user_id": user_id,
                    "date": {"$gte": start.isoformat(), "$lte": end.isoformat()},
                }
            )
            .sort("date", 1)
            .to_list(length=None)
        )
        return [_load(BalanceAdjustment, doc) for doc in docs]
