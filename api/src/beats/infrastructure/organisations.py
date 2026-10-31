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
from datetime import UTC, date, datetime
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
    OrgAbsenceRequest,
    Organisation,
    OrgAssignment,
    OrgAuditEvent,
    OrgInvite,
    OrgJoinRequest,
    OrgMembership,
    OrgProject,
    OrgRole,
    OrgTeam,
    OrgTimesheet,
    Project,
    RequestStatus,
    TimesheetStatus,
)
from beats.domain.utils import normalize_tz
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


def member_row_collections(db: AsyncDatabase) -> tuple[tuple[str, AsyncCollection], ...]:
    """The three collections of a member's own rows that can carry an
    organisation's stamp. One list, so the merge, the hand-back, the wipe
    and the retention purge agree on what "the rows" means."""
    return (
        ("beats", db.timeLogs),
        ("absences", db.absences),
        ("adjustments", db.balance_adjustments),
    )


def _org_project(doc: dict[str, Any]) -> OrgProject:
    return OrgProject(**{**serialize_from_document(doc), "id": str(doc["_id"])})


class MongoOrganisationStore:
    """Organisations, their members, invites, join requests, assignments,
    projects and audit log. Scoped by organisation on every read and write
    that has one; the few that do not (an invite by token, a person's own
    memberships) are named as such."""

    def __init__(self, db: AsyncDatabase):
        self._db = db  # the merge repoints member rows across users, as erasure does
        self.organisations: AsyncCollection = db.organisations
        self.members: AsyncCollection = db.org_members
        self.invites: AsyncCollection = db.org_invites
        self.requests: AsyncCollection = db.org_join_requests
        self.assignments: AsyncCollection = db.org_assignments
        self.audit: AsyncCollection = db.org_audit
        self.projects: AsyncCollection = db.projects
        self.teams: AsyncCollection = db.org_teams
        self.absence_requests: AsyncCollection = db.org_absence_requests
        self.timesheets: AsyncCollection = db.org_timesheets

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
        # removed logo or region — or a cancelled closing — does not linger.
        unset = {
            field: ""
            for field in (
                "logo_url",
                "holiday_country",
                "holiday_subdivision",
                "retention_years",
                "closes_on",
            )
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

    async def open_assignment(
        self, assignment: OrgAssignment, *, keep_personal: bool, reopen: bool = True
    ) -> OrgAssignment:
        """Assign, or reopen an ended assignment: one document per member per
        project. With `keep_personal` the personal fields stored on an ended
        assignment stay — a member taken off and put back keeps their goal,
        repo paths and contract; without it they are replaced by the ones
        sent, which only a connect does.

        `reopen` is what assigning means, and the merge is the one caller
        that turns it off: folding an assignment must not put a former
        member back on a project, only move their half of it."""
        data = _dump(assignment)
        data.pop("_id", None)
        if reopen:
            data["ended_at"] = None
        else:
            data.setdefault("ended_at", None)
        if keep_personal:
            for field in PERSONAL_FIELDS:
                data.pop(field, None)
        else:
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

    # --- merging a connected project (docs/organisations.md, decision 28) --------

    async def repoint_project_rows(self, source_id: str, target_id: str) -> dict[str, int]:
        """Every row keyed by the source project now keys by the target: the
        members' own beats, absences and balance adjustments — stamps
        untouched, so what was the organisation's record stays exactly that
        and what was private stays private — and the organisation's absence
        requests. One of the few writes that cross user scopes (with
        erasure, the deletion's hand-back and wipe, and the retention purge),
        made only by the merge, after the service has checked both projects
        are the same organisation's.

        The member's own references to the project move with their rows:
        a weekly plan's budget and a flow window's active project. Left
        behind they point at a document the merge is about to delete, which
        costs the member a planned week and the daemon's record of what they
        were working on."""
        moved: dict[str, int] = {}
        rows = (*member_row_collections(self._db), ("absence_requests", self.absence_requests))
        for name, collection in rows:
            result = await collection.update_many(
                {"project_id": source_id}, {"$set": {"project_id": target_id}}
            )
            moved[name] = result.modified_count
        moved.update(await self._repoint_references(source_id, target_id))
        return moved

    async def _repoint_references(self, source_id: str, target_id: str) -> dict[str, int]:
        """The two places a member names a project that is not a row of
        theirs: a weekly plan's per-project budget, and the project a flow
        window was recorded against."""
        plans = await self._db.weekly_plans.update_many(
            {"budgets.project_id": source_id},
            {"$set": {"budgets.$[b].project_id": target_id}},
            array_filters=[{"b.project_id": source_id}],
        )
        windows = await self._db.flow_windows.update_many(
            {"active_project_id": source_id}, {"$set": {"active_project_id": target_id}}
        )
        return {"plan_budgets": plans.modified_count, "flow_windows": windows.modified_count}

    async def delete_assignment(self, organisation_id: str, project_id: str, user_id: str) -> bool:
        """One assignment, gone — the deletion's hand-back taking the
        member's half of a project with the project (decision 29)."""
        result = await self.assignments.delete_one(
            {"organisation_id": organisation_id, "project_id": project_id, "user_id": user_id}
        )
        return result.deleted_count == 1

    async def delete_assignments(self, organisation_id: str, project_id: str) -> int:
        result = await self.assignments.delete_many(
            {"organisation_id": organisation_id, "project_id": project_id}
        )
        return result.deleted_count

    async def delete_unapproved_timesheets(self, organisation_id: str, project_id: str) -> int:
        result = await self.timesheets.delete_many(
            {
                "organisation_id": organisation_id,
                "project_id": project_id,
                "status": {"$ne": TimesheetStatus.APPROVED.value},
            }
        )
        return result.deleted_count

    async def delete_project(self, organisation_id: str, project_id: str) -> bool:
        oid = oid_or_none(project_id)
        if oid is None:
            return False
        result = await self.projects.delete_one({"_id": oid, "organisation_id": organisation_id})
        return result.deleted_count == 1

    # --- deleting the organisation (#347) ----------------------------------------

    async def row_owner_ids(self, project_id: str) -> set[str]:
        """Who holds rows on this project — tombstones left out, since a
        deleted account has nobody to hand anything back to."""
        owners: set[str] = set()
        for _, collection in member_row_collections(self._db):
            owners.update(await collection.distinct("user_id", {"project_id": project_id}))
        return {o for o in owners if not o.startswith("erased:")}

    async def hand_back_project(
        self, project: OrgProject, user_id: str, assignment: OrgAssignment | None, archived: bool
    ) -> str:
        """The connect, run backwards for one member: a personal project
        carrying the organisation's fields as they stood and the member's
        own half off their assignment — the contract among them, whoever
        held the pen; with the organisation gone, it is the member's again."""
        doc: dict[str, Any] = {
            "user_id": user_id,
            "name": project.name,
            "kind": project.kind.value,
            "archived": archived,
        }
        for field in ("description", "color", "github_repo", "category"):
            value = getattr(project, field)
            if value is not None:
                doc[field] = value
        if assignment is not None:
            personal = serialize_to_document(
                assignment.model_dump(mode="json", include=set(PERSONAL_FIELDS), exclude_none=True)
            )
            doc.update(personal)
        result = await self.projects.insert_one(doc)
        return str(result.inserted_id)

    async def repoint_member_rows(
        self, project_id: str, user_id: str, new_project_id: str
    ) -> dict[str, int]:
        """One member's rows move to their handed-back project and stop
        being anyone's record: the stamp goes with the organisation. Their
        weekly-plan budgets and flow windows on it move too, for the reason
        they do in a merge — the document they name is about to go."""
        moved: dict[str, int] = {}
        for name, collection in member_row_collections(self._db):
            result = await collection.update_many(
                {"project_id": project_id, "user_id": user_id},
                {"$set": {"project_id": new_project_id}, "$unset": {"organisation_id": ""}},
            )
            moved[name] = result.modified_count
        plans = await self._db.weekly_plans.update_many(
            {"user_id": user_id, "budgets.project_id": project_id},
            {"$set": {"budgets.$[b].project_id": new_project_id}},
            array_filters=[{"b.project_id": project_id}],
        )
        windows = await self._db.flow_windows.update_many(
            {"user_id": user_id, "active_project_id": project_id},
            {"$set": {"active_project_id": new_project_id}},
        )
        moved["plan_budgets"] = plans.modified_count
        moved["flow_windows"] = windows.modified_count
        return moved

    async def delete_organisation_rows(
        self, organisation_id: str, project_ids: list[str]
    ) -> dict[str, int]:
        """Everything that was the organisation's goes: its tombstoned rows
        (the record they served is being destroyed by its keeper), its
        project documents, and every collection of its own. Run last, after
        the hand-backs, so a crash midway strands nothing of a member's."""
        deleted: dict[str, int] = {}
        for name, collection in member_row_collections(self._db):
            result = await collection.delete_many(
                {"project_id": {"$in": project_ids}, "user_id": {"$regex": "^erased:"}}
            )
            deleted[f"tombstoned_{name}"] = result.deleted_count
        oids = [oid for pid in project_ids if (oid := oid_or_none(pid)) is not None]
        deleted["projects"] = (
            await self.projects.delete_many(
                {"_id": {"$in": oids}, "organisation_id": organisation_id}
            )
        ).deleted_count
        for name, collection in (
            ("members", self.members),
            ("invites", self.invites),
            ("requests", self.requests),
            ("assignments", self.assignments),
            ("teams", self.teams),
            ("absence_requests", self.absence_requests),
            ("timesheets", self.timesheets),
            ("audit", self.audit),
        ):
            result = await collection.delete_many({"organisation_id": organisation_id})
            deleted[name] = result.deleted_count
        org_oid = oid_or_none(organisation_id)
        if org_oid is not None:
            await self.organisations.delete_one({"_id": org_oid})
        return deleted

    # --- teams (stage 4) --------------------------------------------------------

    async def create_team(self, team: OrgTeam) -> OrgTeam:
        data = _dump(team)
        result = await self.teams.insert_one(data)
        return _load(OrgTeam, {**data, "_id": result.inserted_id})

    async def list_teams(self, organisation_id: str) -> list[OrgTeam]:
        docs = (
            await self.teams.find({"organisation_id": organisation_id})
            .sort("name", 1)
            .to_list(length=None)
        )
        return [_load(OrgTeam, doc) for doc in docs]

    async def get_team(self, organisation_id: str, team_id: str) -> OrgTeam | None:
        oid = oid_or_none(team_id)
        if oid is None:
            return None
        doc = await self.teams.find_one({"_id": oid, "organisation_id": organisation_id})
        return _load(OrgTeam, doc) if doc else None

    async def update_team(self, organisation_id: str, team: OrgTeam) -> OrgTeam | None:
        oid = oid_or_none(team.id or "")
        if oid is None:
            return None
        data = _dump(team)
        data.pop("_id", None)
        doc = await self.teams.find_one_and_update(
            {"_id": oid, "organisation_id": organisation_id},
            {"$set": data},
            return_document=ReturnDocument.AFTER,
        )
        return _load(OrgTeam, doc) if doc else None

    async def delete_team(self, organisation_id: str, team_id: str) -> bool:
        oid = oid_or_none(team_id)
        if oid is None:
            return False
        result = await self.teams.delete_one({"_id": oid, "organisation_id": organisation_id})
        return result.deleted_count > 0

    async def manager_scope(self, organisation_id: str, user_id: str) -> set[str]:
        """The members a manager may decide and read for: everyone in a team
        the manager is in, themselves included. A manager in no team has an
        empty scope and sees nothing."""
        docs = await self.teams.find(
            {"organisation_id": organisation_id, "member_ids": user_id}, {"member_ids": 1}
        ).to_list(length=None)
        scope: set[str] = set()
        for doc in docs:
            scope.update(doc.get("member_ids", []))
        return scope

    async def remove_from_teams(self, organisation_id: str, user_id: str) -> None:
        """Take a person out of every team — when they leave, are removed, or
        are erased (then under their tombstone id nothing matches anyway)."""
        await self.teams.update_many(
            {"organisation_id": organisation_id}, {"$pull": {"member_ids": user_id}}
        )

    # --- absence requests (stage 3) ---------------------------------------------

    async def create_absence_request(self, request: OrgAbsenceRequest) -> OrgAbsenceRequest:
        data = _dump(request)
        result = await self.absence_requests.insert_one(data)
        return _load(OrgAbsenceRequest, {**data, "_id": result.inserted_id})

    async def get_absence_request(
        self, organisation_id: str, request_id: str
    ) -> OrgAbsenceRequest | None:
        oid = oid_or_none(request_id)
        if oid is None:
            return None
        doc = await self.absence_requests.find_one({"_id": oid, "organisation_id": organisation_id})
        return _load(OrgAbsenceRequest, doc) if doc else None

    async def list_absence_requests(
        self,
        organisation_id: str,
        *,
        user_id: str | None = None,
        pending_only: bool = False,
    ) -> list[OrgAbsenceRequest]:
        query: dict[str, Any] = {"organisation_id": organisation_id}
        if user_id is not None:
            query["user_id"] = user_id
        if pending_only:
            query["status"] = RequestStatus.PENDING.value
        docs = await self.absence_requests.find(query).sort("requested_at", -1).to_list(length=None)
        return [_load(OrgAbsenceRequest, doc) for doc in docs]

    async def decide_absence_request(
        self,
        organisation_id: str,
        request_id: str,
        status: RequestStatus,
        decided_by: str,
        at: datetime,
        comment: str | None,
    ) -> OrgAbsenceRequest | None:
        """Decide a pending request; one already decided resolves to None, so
        two deciders racing cannot both write the absence."""
        oid = oid_or_none(request_id)
        if oid is None:
            return None
        doc = await self.absence_requests.find_one_and_update(
            {
                "_id": oid,
                "organisation_id": organisation_id,
                "status": RequestStatus.PENDING.value,
            },
            {
                "$set": {
                    "status": status.value,
                    "decided_at": at.isoformat(),
                    "decided_by": decided_by,
                    "comment": comment,
                }
            },
            return_document=ReturnDocument.AFTER,
        )
        return _load(OrgAbsenceRequest, doc) if doc else None

    async def withdraw_absence_request(
        self, organisation_id: str, request_id: str, user_id: str
    ) -> bool:
        """The asker takes a pending request back; a decided one stays."""
        oid = oid_or_none(request_id)
        if oid is None:
            return False
        result = await self.absence_requests.delete_one(
            {
                "_id": oid,
                "organisation_id": organisation_id,
                "user_id": user_id,
                "status": RequestStatus.PENDING.value,
            }
        )
        return result.deleted_count > 0

    # --- timesheets (stage 3) ------------------------------------------------------

    async def upsert_timesheet(self, sheet: OrgTimesheet) -> OrgTimesheet:
        """Submit, or resubmit: one document per (project, member, month),
        its history appended to. Never touches an approved sheet — the
        filter excludes it, so a resubmission racing an approval loses."""
        data = _dump(sheet)
        data.pop("_id", None)
        history = data.pop("history", [])
        doc = await self.timesheets.find_one_and_update(
            {
                "project_id": sheet.project_id,
                "user_id": sheet.user_id,
                "month": data["month"],
                "status": {"$ne": TimesheetStatus.APPROVED.value},
            },
            {"$set": data, "$push": {"history": {"$each": history}}},
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        if doc is None:
            raise RuntimeError("upsert of OrgTimesheet returned no document")
        return _load(OrgTimesheet, doc)

    async def get_timesheet(self, organisation_id: str, sheet_id: str) -> OrgTimesheet | None:
        oid = oid_or_none(sheet_id)
        if oid is None:
            return None
        doc = await self.timesheets.find_one({"_id": oid, "organisation_id": organisation_id})
        return _load(OrgTimesheet, doc) if doc else None

    async def find_timesheet(
        self, project_id: str, user_id: str, month: date
    ) -> OrgTimesheet | None:
        doc = await self.timesheets.find_one(
            {"project_id": project_id, "user_id": user_id, "month": month.isoformat()}
        )
        return _load(OrgTimesheet, doc) if doc else None

    async def list_timesheets(
        self,
        organisation_id: str,
        *,
        user_id: str | None = None,
        month: date | None = None,
        project_id: str | None = None,
    ) -> list[OrgTimesheet]:
        query: dict[str, Any] = {"organisation_id": organisation_id}
        if user_id is not None:
            query["user_id"] = user_id
        if month is not None:
            query["month"] = month.isoformat()
        if project_id is not None:
            query["project_id"] = project_id
        docs = await self.timesheets.find(query).sort("month", -1).to_list(length=None)
        return [_load(OrgTimesheet, doc) for doc in docs]

    async def set_timesheet_state(
        self,
        organisation_id: str,
        sheet_id: str,
        *,
        status: TimesheetStatus,
        only_from: Iterable[TimesheetStatus],
        decided_by: str,
        at: datetime,
        comment: str | None,
        frozen: dict[str, Any] | None,
    ) -> OrgTimesheet | None:
        """Move a sheet between states, only from the states named — so an
        approval cannot land on a sheet approved by someone else a moment
        before, and a reopen only opens what is approved."""
        oid = oid_or_none(sheet_id)
        if oid is None:
            return None
        sets: dict[str, Any] = {
            "status": status.value,
            "decided_at": at.isoformat(),
            "decided_by": decided_by,
            "comment": comment,
        }
        if frozen is not None:
            sets["frozen"] = frozen
        changes: dict[str, Any] = {
            "$set": sets,
            "$push": {
                "history": {
                    "at": at.isoformat(),
                    "by": decided_by,
                    "action": status.value,
                    "comment": comment,
                }
            },
        }
        if frozen is None and status is not TimesheetStatus.APPROVED:
            changes["$unset"] = {"frozen": ""}
        doc = await self.timesheets.find_one_and_update(
            {
                "_id": oid,
                "organisation_id": organisation_id,
                "status": {"$in": [state.value for state in only_from]},
            },
            changes,
            return_document=ReturnDocument.AFTER,
        )
        return _load(OrgTimesheet, doc) if doc else None

    # --- audit -------------------------------------------------------------------

    async def record(self, event: OrgAuditEvent) -> None:
        await self.audit.insert_one(_dump(event))

    async def list_audit(
        self, organisation_id: str, *, before: datetime | None = None, limit: int = 100
    ) -> list[OrgAuditEvent]:
        """The log, newest first, paged by instant: written since stage 2,
        read from stage 4 on."""
        query: dict[str, Any] = {"organisation_id": organisation_id}
        if before is not None:
            query["at"] = {"$lt": before.isoformat()}
        docs = (
            await self.audit.find(query)
            .sort("at", -1)
            .limit(max(1, min(limit, 500)))
            .to_list(length=None)
        )
        return [_load(OrgAuditEvent, doc) for doc in docs]


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

    async def running_in(
        self, organisation_id: str, project_id: str, user_id: str, start: datetime, end: datetime
    ) -> bool:
        """Whether a stamped timer is still running in [start, end) — what
        makes an approval wait: a running beat is in no figure yet, and
        freezing around it would guarantee a drift."""
        doc = await self.beats.find_one(
            {
                "organisation_id": organisation_id,
                "project_id": project_id,
                "user_id": user_id,
                "end": None,
                "start": {"$gte": start, "$lt": end},
            },
            {"_id": 1},
        )
        return doc is not None

    async def has_unshared(
        self,
        organisation_id: str,
        project_id: str,
        user_id: str,
        *,
        private_before: datetime | None,
        private_before_day: date | None,
        expired_before: date,
    ) -> bool:
        """Whether the member has an entry or an absence on the project that
        is not this organisation's record — one dated before the day they
        chose to share from. Read to withhold a balance, never to show
        anything: the answer is a yes or a no.

        A row the retention purge unstamped is not one of those. The purge
        takes the stamp off a living member's rows older than the cutoff
        (decision 30) and leaves the rows theirs; asking only whether an
        unstamped row exists then answers yes for every long-standing
        member, and the organisation loses the balance on its own record
        for good (#409). So a row dated in the shared window and already
        past the cutoff is read as expired, not as withheld: it was shared
        once. Every row a purge unstamped is older than the cutoff it ran
        with, which is never later than today's.

        The window opens at `private_before` — what a connect kept back —
        and at the beginning of time where a connect kept back nothing.
        """
        unstamped: dict[str, Any] = {"organisation_id": {"$ne": organisation_id}}
        expired_at = datetime(
            expired_before.year, expired_before.month, expired_before.day, tzinfo=UTC
        )
        kept_back_or_expired: list[dict[str, Any]] = [{"start": {"$gte": expired_at}}]
        if private_before is not None:
            kept_back_or_expired.append({"start": {"$lt": normalize_tz(private_before)}})
        beat = await self.beats.find_one(
            {
                "project_id": project_id,
                "user_id": user_id,
                **unstamped,
                "$or": kept_back_or_expired,
            },
            {"_id": 1},
        )
        if beat is not None:
            return True
        by_day: list[dict[str, Any]] = [{"date": {"$gte": expired_before.isoformat()}}]
        if private_before_day is not None:
            by_day.append({"date": {"$lt": private_before_day.isoformat()}})
        absence = await self.absences.find_one(
            {"project_id": project_id, "user_id": user_id, **unstamped, "$or": by_day},
            {"_id": 1},
        )
        return absence is not None

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
