"""Organisations — the rules (docs/organisations.md).

An organisation exists, has members with roles, owns projects that appear on
each member's own timeline, and reads the hours on those projects and
nothing else. `OrganisationService` is where every one of those rules is
checked; the routes under `/api/organisations` are thin over it.

The two readers the organisation gets — `record` for its admins and
`visible` for one member looking at their own slice — are the same
assembly over the same queries, with `user_id` the only difference. That is
what makes the "what Acme can see" page honest: it is not a description of
the read, it is the read.
"""

import csv
import io
import secrets
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from typing import Any, NamedTuple
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from beats.domain.billing import utc_midnight, utc_range
from beats.domain.contracts import balance_terms
from beats.domain.exceptions import (
    AlreadyAMember,
    InviteExpired,
    InviteNotFound,
    JoinRequestNotFound,
    JoinRequestPending,
    LastOwner,
    MemberNotFound,
    MergeIntoItself,
    NotAssigned,
    OrganisationNotFound,
    OrganisationProject,
    OrganisationRoleRequired,
    OwnerRoleReserved,
    PeriodApproved,
    ProjectHasBilling,
    ProjectNotFound,
    ShareFromInFuture,
    UnknownHolidayRegion,
    UnknownTimezone,
)
from beats.domain.holidays import check_region, contract_holidays
from beats.domain.models import (
    PERSONAL_FIELDS,
    Beat,
    JoinDecision,
    MembershipEnd,
    MemberTotals,
    Organisation,
    OrganisationFields,
    OrgAssignment,
    OrgAuditEvent,
    OrgInvite,
    OrgJoinRequest,
    OrgMembership,
    OrgProject,
    OrgRole,
    TimesheetStatus,
)
from beats.domain.ports import (
    BillingPresence,
    OrganisationAbsenceReader,
    OrganisationBeatReader,
    OrganisationRecords,
    OrganisationStamper,
    OrganisationStore,
    UserDirectory,
)
from beats.domain.services import worked_by_local_day
from beats.domain.timesheet import month_end
from beats.domain.utils import local_date, normalize_tz

INVITE_DAYS_MAX = 90


class Member(NamedTuple):
    membership: OrgMembership
    organisation: Organisation


class ProjectMembers(NamedTuple):
    project: OrgProject
    assignments: list[tuple[OrgAssignment, OrgMembership | None]]


class OrgLabels(NamedTuple):
    """The names a row is read by: projects by id, members by user id. The
    members include those who have left, because a decided request, an
    approved sheet and an audit line all outlive the membership they name."""

    projects: dict[str, str]
    members: dict[str, str]


class RecordEntry(NamedTuple):
    id: str
    day: date
    start: datetime
    end: datetime
    hours: float
    note: str | None


class RecordAbsence(NamedTuple):
    date: date
    type: str
    half_day: bool


class MemberBalance(NamedTuple):
    as_of: date
    balance: float
    opening: float
    worked: float
    expected_through: float
    adjusted: float


class MemberRecord(NamedTuple):
    """One member's slice of one project, as the organisation reads it."""

    user_id: str
    name: str
    shared_from: datetime
    active: bool
    hours: float  # the month's
    entries: list[RecordEntry]
    absences: list[RecordAbsence]
    has_contract: bool
    balance: MemberBalance | None
    totals: MemberTotals


class ProjectRecord(NamedTuple):
    project: OrgProject
    members: list[MemberRecord]


class Record(NamedTuple):
    organisation: Organisation
    month: date
    first: date
    last: date
    projects: list[ProjectRecord]


class ArchiveProject(NamedTuple):
    project_id: str
    name: str
    color: str | None
    hours: float
    entries: list[RecordEntry]
    absences: list[RecordAbsence]


class Archive(NamedTuple):
    organisation: Organisation
    membership: OrgMembership
    hours: float
    projects: list[ArchiveProject]


def _entry(beat: Beat, tz: ZoneInfo) -> RecordEntry:
    """One finished beat as the record lists it. The readers hand over
    finished beats only (`end` set), so a running one here is a bug."""
    if beat.end is None or beat.id is None:
        raise ValueError("the record lists finished, stored beats only")
    return RecordEntry(
        id=beat.id,
        day=local_date(beat.start, tz),
        start=normalize_tz(beat.start),
        end=normalize_tz(beat.end),
        hours=round(beat.duration.total_seconds() / 3600, 2),
        note=beat.note,
    )


class OrganisationService:
    def __init__(
        self,
        store: OrganisationStore,
        records: OrganisationRecords,
        users: UserDirectory,
        billing: BillingPresence,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ):
        self.store = store
        self.records = records
        self.users = users
        self.billing = billing
        self._now = now

    # --- helpers ---------------------------------------------------------------

    async def _member(
        self, organisation_id: str, user_id: str, role: OrgRole = OrgRole.MEMBER
    ) -> Member:
        """The caller's active membership, at `role` or above. A non-member
        and an unknown organisation read the same (404); a member without
        the role is a 403."""
        membership = await self.store.membership(organisation_id, user_id)
        if membership is None or not membership.active:
            raise OrganisationNotFound()
        organisation = await self.store.get_organisation(organisation_id)
        if organisation is None:
            raise OrganisationNotFound()
        if not membership.role.at_least(role):
            raise OrganisationRoleRequired(role.value)
        return Member(membership, organisation)

    async def _identity(self, user_id: str) -> tuple[str, str]:
        user = await self.users.get_by_id(user_id)
        if user is None:
            raise OrganisationNotFound()
        return (user.display_name or user.email, user.email)

    async def _audit(
        self, organisation_id: str, actor: str | None, event: str, **details: Any
    ) -> None:
        subject = details.pop("subject_user_id", None)
        project_id = details.pop("project_id", None)
        await self.store.record(
            OrgAuditEvent(
                organisation_id=organisation_id,
                at=self._now(),
                actor_user_id=actor,
                event=event,
                subject_user_id=subject,
                project_id=project_id,
                details=details,
            )
        )

    @staticmethod
    def _check_fields(fields: OrganisationFields) -> None:
        if fields.holiday_country is not None:
            check_region(fields.holiday_country, fields.holiday_subdivision)
        try:
            ZoneInfo(fields.timezone)
        except ZoneInfoNotFoundError, ValueError:
            raise UnknownTimezone(fields.timezone) from None

    # --- organisations -------------------------------------------------------------

    async def create(self, user_id: str, fields: OrganisationFields) -> Member:
        self._check_fields(fields)
        name, email = await self._identity(user_id)
        organisation = await self.store.create_organisation(
            Organisation(**fields.model_dump(), created_by=user_id, created_at=self._now())
        )
        if organisation.id is None:
            raise RuntimeError("the store returned an organisation without an id")
        membership = await self.store.open_membership(
            OrgMembership(
                organisation_id=organisation.id,
                user_id=user_id,
                role=OrgRole.OWNER,
                name=name,
                email=email,
                joined_at=self._now(),
            )
        )
        await self._audit(organisation.id, user_id, "organisation.created")
        return Member(membership, organisation)

    async def mine(self, user_id: str) -> list[Member]:
        """Every organisation the person is or was in, with their membership
        — the ones left included, so the archive of each can be reached."""
        memberships = await self.store.memberships_of(user_id)
        organisations = await self.store.get_organisations(m.organisation_id for m in memberships)
        return [
            Member(m, organisations[m.organisation_id])
            for m in memberships
            if m.organisation_id in organisations
        ]

    async def get(self, organisation_id: str, user_id: str) -> Member:
        return await self._member(organisation_id, user_id)

    async def update(
        self, organisation_id: str, user_id: str, fields: OrganisationFields
    ) -> Organisation:
        member = await self._member(organisation_id, user_id, OrgRole.ADMIN)
        self._check_fields(fields)
        organisation = member.organisation.model_copy(update=fields.model_dump())
        await self.store.update_organisation(organisation)
        await self._audit(
            organisation_id, user_id, "organisation.updated", fields=fields.model_dump()
        )
        return organisation

    # --- members ---------------------------------------------------------------------

    async def members(self, organisation_id: str, user_id: str) -> list[OrgMembership]:
        await self._member(organisation_id, user_id)
        return await self.store.list_members(organisation_id)

    async def set_role(
        self, organisation_id: str, actor: str, user_id: str, role: OrgRole
    ) -> OrgMembership:
        """Change a member's role. The owner role is given and taken by owners
        only, and the last owner keeps it."""
        me = await self._member(organisation_id, actor, OrgRole.ADMIN)
        target = await self.store.membership(organisation_id, user_id)
        if target is None or not target.active:
            raise MemberNotFound()
        touches_owner = OrgRole.OWNER in (role, target.role)
        if touches_owner and me.membership.role is not OrgRole.OWNER:
            raise OwnerRoleReserved()
        if (
            target.role is OrgRole.OWNER
            and role is not OrgRole.OWNER
            and await self.store.count_owners(organisation_id) <= 1
        ):
            raise LastOwner()
        updated = await self.store.set_role(organisation_id, user_id, role)
        if updated is None:
            raise MemberNotFound()
        if target.role is OrgRole.OWNER and not await self._an_owner_remains(organisation_id):
            await self.store.set_role(organisation_id, user_id, OrgRole.OWNER)
            raise LastOwner()
        await self._audit(
            organisation_id,
            actor,
            "member.role_changed",
            subject_user_id=user_id,
            role=role.value,
            was=target.role.value,
        )
        return updated

    async def _end_membership(
        self, organisation_id: str, user_id: str, reason: MembershipEnd
    ) -> OrgMembership:
        """What leaving and removal share: the membership ends, every active
        assignment ends with it, so tracking to the organisation's projects
        stops and they leave the member's list. The stamped records stay
        where they are — the organisation keeps its working-time record, the
        person keeps their archive of it."""
        at = self._now()
        ended = await self.store.end_membership(organisation_id, user_id, reason, at)
        if ended is None:
            raise MemberNotFound()
        if ended.role is OrgRole.OWNER and not await self._an_owner_remains(organisation_id):
            # Two owners leaving at once each saw the other: the write is
            # undone and refused, as the check before it would have.
            await self.store.open_membership(ended.model_copy(update={"left_at": None}))
            raise LastOwner()
        await self.store.end_assignments(organisation_id, user_id, at)
        return ended

    async def _an_owner_remains(self, organisation_id: str) -> bool:
        """Re-read after a write that may have taken the last owner away. The
        check before the write is not atomic with it, so the write is made
        and undone if it left no owner (`count_owners` is a plain count)."""
        return await self.store.count_owners(organisation_id) >= 1

    async def leave(self, organisation_id: str, user_id: str) -> Member:
        me = await self._member(organisation_id, user_id)
        if (
            me.membership.role is OrgRole.OWNER
            and await self.store.count_owners(organisation_id) <= 1
        ):
            raise LastOwner()
        ended = await self._end_membership(organisation_id, user_id, MembershipEnd.LEFT)
        await self._audit(organisation_id, user_id, "member.left", subject_user_id=user_id)
        return Member(ended, me.organisation)

    async def remove_member(self, organisation_id: str, actor: str, user_id: str) -> OrgMembership:
        me = await self._member(organisation_id, actor, OrgRole.ADMIN)
        target = await self.store.membership(organisation_id, user_id)
        if target is None or not target.active:
            raise MemberNotFound()
        if target.role is OrgRole.OWNER:
            if me.membership.role is not OrgRole.OWNER:
                raise OwnerRoleReserved()
            if await self.store.count_owners(organisation_id) <= 1:
                raise LastOwner()
        ended = await self._end_membership(organisation_id, user_id, MembershipEnd.REMOVED)
        await self._audit(organisation_id, actor, "member.removed", subject_user_id=user_id)
        return ended

    # --- invites ---------------------------------------------------------------------

    async def invite(
        self,
        organisation_id: str,
        actor: str,
        *,
        email: str | None,
        role: OrgRole,
        requires_approval: bool,
        expires_in_days: int,
    ) -> OrgInvite:
        """An invitation to one address, or with none an invite link. No
        invite carries the owner role; an admin is made one afterwards."""
        await self._member(organisation_id, actor, OrgRole.ADMIN)
        if role is OrgRole.OWNER:
            raise OwnerRoleReserved()
        now = self._now()
        invite = await self.store.create_invite(
            OrgInvite(
                organisation_id=organisation_id,
                token=secrets.token_urlsafe(32),
                email=email.strip().lower() if email else None,
                role=role,
                requires_approval=requires_approval and email is None,
                created_by=actor,
                created_at=now,
                expires_at=now + timedelta(days=min(max(expires_in_days, 1), INVITE_DAYS_MAX)),
            )
        )
        await self._audit(
            organisation_id,
            actor,
            "member.invited",
            email=invite.email,
            role=role.value,
            link=invite.email is None,
        )
        return invite

    async def invites(self, organisation_id: str, actor: str) -> list[OrgInvite]:
        await self._member(organisation_id, actor, OrgRole.ADMIN)
        now = self._now()
        return [i for i in await self.store.list_invites(organisation_id) if i.open_at(now)]

    async def revoke_invite(self, organisation_id: str, actor: str, invite_id: str) -> None:
        await self._member(organisation_id, actor, OrgRole.ADMIN)
        if not await self.store.revoke_invite(organisation_id, invite_id, self._now()):
            raise InviteNotFound()
        await self._audit(organisation_id, actor, "invite.revoked", invite_id=invite_id)

    async def my_invitations(self, user_id: str) -> list[tuple[OrgInvite, Organisation]]:
        """The open invitations addressed to the account's own address — to
        say who has invited them and as what. The route strips the token:
        an address is not verified at sign-up, so whoever registered it
        first must not be handed the way in. Joining takes the token the
        inviter passed on *and* the address (`_open_invite`)."""
        _, email = await self._identity(user_id)
        now = self._now()
        invites = [i for i in await self.store.invites_for_email(email.lower()) if i.open_at(now)]
        organisations = await self.store.get_organisations(i.organisation_id for i in invites)
        return [
            (i, organisations[i.organisation_id])
            for i in invites
            if i.organisation_id in organisations
        ]

    async def _open_invite(self, token: str, user_id: str) -> tuple[OrgInvite, Organisation]:
        """Resolve a token for this account: unknown, or addressed to another
        address, is 404; real but closed is 410."""
        invite = await self.store.invite_by_token(token)
        if invite is None:
            raise InviteNotFound()
        if invite.email is not None:
            _, email = await self._identity(user_id)
            if invite.email != email.lower():
                raise InviteNotFound()
        if not invite.open_at(self._now()):
            raise InviteExpired()
        organisation = await self.store.get_organisation(invite.organisation_id)
        if organisation is None:
            raise InviteNotFound()
        return invite, organisation

    async def preview_invite(
        self, token: str, user_id: str
    ) -> tuple[OrgInvite, Organisation, OrgMembership | None]:
        invite, organisation = await self._open_invite(token, user_id)
        membership = await self.store.membership(invite.organisation_id, user_id)
        return invite, organisation, membership if membership and membership.active else None

    async def join(self, token: str, user_id: str) -> tuple[Member | None, OrgJoinRequest | None]:
        """Take an invite: a membership, or on a link with an approval step a
        join request. Joining never creates a second account or moves any
        data (rule 1): it is one document in `org_members`."""
        invite, organisation = await self._open_invite(token, user_id)
        organisation_id = invite.organisation_id
        existing = await self.store.membership(organisation_id, user_id)
        if existing is not None and existing.active:
            raise AlreadyAMember()
        name, email = await self._identity(user_id)
        now = self._now()
        if invite.requires_approval:
            if await self.store.pending_request(organisation_id, user_id) is not None:
                raise JoinRequestPending()
            request = await self.store.create_request(
                OrgJoinRequest(
                    organisation_id=organisation_id,
                    user_id=user_id,
                    invite_id=invite.id or "",
                    name=name,
                    email=email,
                    requested_at=now,
                )
            )
            await self._audit(organisation_id, user_id, "member.requested", subject_user_id=user_id)
            return None, request
        membership = await self.store.open_membership(
            OrgMembership(
                organisation_id=organisation_id,
                user_id=user_id,
                role=invite.role,
                name=name,
                email=email,
                joined_at=now,
            )
        )
        if invite.email is not None and invite.id is not None:
            await self.store.mark_invite_accepted(invite.id, user_id, now)
        await self._audit(
            organisation_id,
            user_id,
            "member.joined",
            subject_user_id=user_id,
            role=invite.role.value,
            invite_id=invite.id,
        )
        return Member(membership, organisation), None

    # --- join requests ---------------------------------------------------------------

    async def requests(
        self, organisation_id: str, actor: str
    ) -> list[tuple[OrgJoinRequest, OrgRole]]:
        """Each waiting request with the role approving it would grant — the
        invite's, the same rule `decide_request` applies — so the decision is
        made knowing it, not discovered after."""
        await self._member(organisation_id, actor, OrgRole.ADMIN)
        requests = await self.store.list_requests(organisation_id)
        return [(r, await self._requested_role(organisation_id, r)) for r in requests]

    async def _requested_role(self, organisation_id: str, request: OrgJoinRequest) -> OrgRole:
        invite = await self.store.get_invite(organisation_id, request.invite_id)
        return invite.role if invite is not None else OrgRole.MEMBER

    async def decide_request(
        self, organisation_id: str, actor: str, request_id: str, decision: JoinDecision
    ) -> tuple[OrgJoinRequest, OrgRole]:
        await self._member(organisation_id, actor, OrgRole.ADMIN)
        decided = await self.store.decide_request(
            organisation_id, request_id, decision, actor, self._now()
        )
        if decided is None:
            raise JoinRequestNotFound()
        role = await self._requested_role(organisation_id, decided)
        if decision is JoinDecision.APPROVED:
            await self.store.open_membership(
                OrgMembership(
                    organisation_id=organisation_id,
                    user_id=decided.user_id,
                    role=role,
                    name=decided.name,
                    email=decided.email,
                    joined_at=self._now(),
                )
            )
        await self._audit(
            organisation_id, actor, f"request.{decision.value}", subject_user_id=decided.user_id
        )
        return decided, role

    # --- projects ----------------------------------------------------------------------

    async def _with_members(
        self, organisation_id: str, projects: list[OrgProject]
    ) -> list[ProjectMembers]:
        assignments = await self.store.list_assignments(organisation_id)
        members = {
            m.user_id: m for m in await self.store.list_members(organisation_id, active_only=False)
        }
        by_project: dict[str, list[tuple[OrgAssignment, OrgMembership | None]]] = {
            p.id: [] for p in projects
        }
        for a in assignments:
            by_project.setdefault(a.project_id, []).append((a, members.get(a.user_id)))
        return [ProjectMembers(p, by_project.get(p.id, [])) for p in projects]

    async def projects(
        self, organisation_id: str, actor: str, archived: bool | None = None
    ) -> list[ProjectMembers]:
        await self._member(organisation_id, actor, OrgRole.ADMIN)
        return await self._with_members(
            organisation_id, await self.store.list_projects(organisation_id, archived)
        )

    async def create_project(
        self, organisation_id: str, actor: str, fields: dict[str, Any]
    ) -> ProjectMembers:
        await self._member(organisation_id, actor, OrgRole.ADMIN)
        project = await self.store.create_project(organisation_id, fields)
        await self._audit(
            organisation_id, actor, "project.created", project_id=project.id, name=project.name
        )
        return ProjectMembers(project, [])

    async def update_project(
        self, organisation_id: str, actor: str, project_id: str, fields: dict[str, Any]
    ) -> ProjectMembers:
        await self._member(organisation_id, actor, OrgRole.ADMIN)
        project = await self.store.update_project(organisation_id, project_id, fields)
        if project is None:
            raise ProjectNotFound(project_id)
        await self._audit(
            organisation_id,
            actor,
            "project.updated",
            project_id=project_id,
            fields=dict(fields.items()),
        )
        [with_members] = await self._with_members(organisation_id, [project])
        return with_members

    async def assign(
        self, organisation_id: str, actor: str, project_id: str, user_id: str
    ) -> OrgAssignment:
        """Put an active member on one of the organisation's projects. Their
        hours on it are the organisation's from now; nothing before is."""
        await self._member(organisation_id, actor, OrgRole.ADMIN)
        if await self.store.get_project(organisation_id, project_id) is None:
            raise ProjectNotFound(project_id)
        target = await self.store.membership(organisation_id, user_id)
        if target is None or not target.active:
            raise MemberNotFound()
        existing = await self.store.assignment(organisation_id, project_id, user_id)
        if existing is not None and existing.active:
            return existing
        now = self._now()
        # Reopening an ended assignment keeps its personal half — the goal,
        # the repo paths and the contract behind a balance the organisation
        # read; only a connect replaces them.
        assignment = await self.store.open_assignment(
            OrgAssignment(
                organisation_id=organisation_id,
                project_id=project_id,
                user_id=user_id,
                shared_from=now,
                assigned_at=now,
                assigned_by=actor,
            ),
            keep_personal=True,
        )
        await self._audit(
            organisation_id,
            actor,
            "project.assigned",
            project_id=project_id,
            subject_user_id=user_id,
        )
        return assignment

    async def member_name(self, organisation_id: str, user_id: str) -> str | None:
        """The name a member joined under, for a response that lists them."""
        membership = await self.store.membership(organisation_id, user_id)
        return membership.name if membership else None

    async def labels(self, organisation_id: str) -> OrgLabels:
        """The names of the organisation's projects and members, for a
        response that names a row the reader is already being shown. Like
        `member_name` it checks nothing itself — the route resolved the
        caller before it had a row to name — and it is how a decider reads a
        project's name without the admin-only project list."""
        projects = await self.store.list_projects(organisation_id)
        members = await self.store.list_members(organisation_id, active_only=False)
        return OrgLabels(
            projects={p.id: p.name for p in projects if p.id is not None},
            members={m.user_id: m.name for m in members},
        )

    async def unassign(
        self, organisation_id: str, actor: str, project_id: str, user_id: str
    ) -> None:
        await self._member(organisation_id, actor, OrgRole.ADMIN)
        ended = await self.store.end_assignments(organisation_id, user_id, self._now(), project_id)
        if not ended:
            raise NotAssigned()
        await self._audit(
            organisation_id,
            actor,
            "project.unassigned",
            project_id=project_id,
            subject_user_id=user_id,
        )

    async def connect_project(
        self,
        organisation_id: str,
        user_id: str,
        project_id: str,
        share_from: date | None,
        tz: ZoneInfo,
        beats: OrganisationStamper,
        absences: OrganisationStamper,
    ) -> OrgAssignment:
        """Connect one of the member's own projects to the organisation
        (rule 4): the document changes hands, the personal fields move to
        the member's assignment, and the member's hours and absences from
        the day they chose — or from now, to start fresh — become the
        organisation's record. Nothing moves and nothing before that day is
        touched. A project billed to a client stays personal (409)."""
        member = await self._member(organisation_id, user_id)
        project = await self.store.personal_project(project_id, user_id)
        if project is None:
            # Not theirs to connect: an organisation's already, or nobody's.
            if await self.store.get_project(organisation_id, project_id) is not None:
                raise OrganisationProject()
            raise ProjectNotFound(project_id)
        if await self.billing.exists(project_id):
            raise ProjectHasBilling()
        now = self._now()
        today = local_date(now, tz)
        if share_from is not None and share_from > today:
            raise ShareFromInFuture()
        shared_from = utc_midnight(share_from, tz) if share_from is not None else now
        personal = {field: getattr(project, field) for field in PERSONAL_FIELDS}
        assignment = await self.store.open_assignment(
            OrgAssignment(
                organisation_id=organisation_id,
                project_id=project_id,
                user_id=user_id,
                shared_from=shared_from,
                assigned_at=now,
                assigned_by=user_id,
                **personal,
            ),
            keep_personal=False,
        )
        if not await self.store.hand_project_to_organisation(project_id, user_id, organisation_id):
            # The project left the member's hands between the read above and
            # now — another tab connected it, or a backup import replaced it.
            # The assignment just opened would point at a document this
            # organisation does not own and resolve to nothing; end it rather
            # than leave it to be found later.
            await self.store.end_assignments(organisation_id, user_id, now, project_id)
            raise ProjectNotFound(project_id)
        if share_from is not None:
            await beats.stamp_organisation(project_id, organisation_id, shared_from)
            await absences.stamp_organisation(project_id, organisation_id, share_from)
        else:
            # Nothing before now is shared, but a day off already booked for
            # a day to come is part of the record from here on.
            await absences.stamp_organisation(project_id, organisation_id, today)
        await self._audit(
            organisation_id,
            user_id,
            "project.connected",
            project_id=project_id,
            subject_user_id=user_id,
            shared_from=shared_from.isoformat(),
            name=project.name,
            organisation=member.organisation.name,
        )
        return assignment

    async def merge_project(
        self, organisation_id: str, actor: str, source_id: str, target_id: str
    ) -> ProjectMembers:
        """Fold one of the organisation's projects into another (decision
        28) — the way out of the duplicate a connect leaves when the
        organisation already had a project for the same work. Admins.

        Every row keyed by the source moves to the target with its stamp
        untouched, so rule 4 holds without being re-decided: what the
        member chose to share stays shared from that instant, and what was
        private stays private, now under the surviving project on their
        own timeline. Each active assignment folds into the target's,
        which survives as it stands (decision 17's spirit) — the earlier
        `shared_from`, and the source's contract only where the target's
        assignment has none. Refused while an approved timesheet exists on
        either side (409 PERIOD_APPROVED): a frozen figure must not gain
        or lose rows silently; reopen first. A sheet submitted over the
        source alone is dropped — its month no longer stands apart — and
        is resubmitted over the merged project. The source document is
        then deleted, and the audit log holds the whole act."""
        await self._member(organisation_id, actor, OrgRole.ADMIN)
        if source_id == target_id:
            raise MergeIntoItself()
        source = await self.store.get_project(organisation_id, source_id)
        if source is None:
            raise ProjectNotFound(source_id)
        target = await self.store.get_project(organisation_id, target_id)
        if target is None:
            raise ProjectNotFound(target_id)
        approved = [
            sheet.month
            for project_id in (source_id, target_id)
            for sheet in await self.store.list_timesheets(organisation_id, project_id=project_id)
            if sheet.status is TimesheetStatus.APPROVED
        ]
        if approved:
            raise PeriodApproved(min(approved))
        for a in await self.store.list_assignments(organisation_id, project_id=source_id):
            existing = await self.store.assignment(organisation_id, target_id, a.user_id)
            if existing is None:
                folded = a.model_copy(update={"project_id": target_id})
            else:
                update: dict[str, Any] = {"shared_from": min(existing.shared_from, a.shared_from)}
                if existing.contract is None and a.contract is not None:
                    update["contract"] = a.contract
                    update["contract_managed"] = a.contract_managed
                folded = existing.model_copy(update=update)
            await self.store.open_assignment(folded, keep_personal=False)
        await self.store.delete_assignments(organisation_id, source_id)
        moved = await self.store.repoint_project_rows(source_id, target_id)
        dropped = await self.store.delete_unapproved_timesheets(organisation_id, source_id)
        await self.store.delete_project(organisation_id, source_id)
        await self._audit(
            organisation_id,
            actor,
            "project.merged",
            project_id=target_id,
            source=source.name,
            target=target.name,
            moved=moved,
            dropped_timesheets=dropped,
        )
        [with_members] = await self._with_members(organisation_id, [target])
        return with_members

    # --- the record --------------------------------------------------------------------

    async def _balance(
        self, organisation_id: str, assignment: OrgAssignment, today: date, tz: ZoneInfo
    ) -> MemberBalance | None:
        contract = assignment.contract
        if contract is None or assignment.project_id is None:
            return None
        # A balance sums every hour since the contract began. On a connected
        # project with hours before the day the member chose to share from,
        # that sum would carry what rule 4 keeps back — so it is withheld,
        # and shown only when every entry and absence on the project is the
        # organisation's, where it equals the member's own figure.
        if await self.records.has_unshared(
            organisation_id, assignment.project_id, assignment.user_id
        ):
            return None
        start = contract.starts_on
        beats = await self.records.beats_of_member(
            organisation_id, assignment.project_id, assignment.user_id
        )
        absences = [
            a
            for _, a in await self.records.absences_between(
                organisation_id, [assignment.project_id], start, today, user_id=assignment.user_id
            )
        ]
        adjustments = await self.records.adjustments_of_member(
            assignment.project_id, assignment.user_id, start, today
        )
        try:
            holidays = set(contract_holidays(contract, start, today))
        except UnknownHolidayRegion:
            return None
        terms = balance_terms(
            contract, absences, holidays, worked_by_local_day(beats, tz), adjustments, today
        )
        return MemberBalance(
            as_of=today,
            balance=round(terms.balance, 2),
            opening=round(terms.opening, 2),
            worked=round(terms.worked, 2),
            expected_through=round(terms.expected_through, 2),
            adjusted=round(terms.adjusted, 2),
        )

    async def _record(
        self,
        organisation: Organisation,
        projects: list[OrgProject],
        month: date,
        tz: ZoneInfo,
        *,
        user_id: str | None,
    ) -> Record:
        """One month of the organisation's record over `projects`: per
        project, per member assigned (now or before), the finished entries
        started in the month in `tz`, the absences, the all-time totals and
        the balance of a contract if there is one. With `user_id`, that
        member's slice alone — the same queries, narrowed."""
        if organisation.id is None:
            raise ValueError("a stored organisation has an id")
        organisation_id = organisation.id
        today = local_date(self._now(), tz)
        first, last = month, month_end(month)
        start, end = utc_range(first, last, tz)
        project_ids = [p.id for p in projects]
        assignments = await self.store.list_assignments(
            organisation_id, user_id=user_id, active_only=False
        )
        members = {
            m.user_id: m for m in await self.store.list_members(organisation_id, active_only=False)
        }
        beats = await self.records.beats_between(
            organisation_id, project_ids, start, end, user_id=user_id
        )
        absences = await self.records.absences_between(
            organisation_id, project_ids, first, last, user_id=user_id
        )
        totals = await self.records.totals(organisation_id, project_ids, user_id=user_id)

        entries: dict[tuple[str, str], list[RecordEntry]] = {}
        for uid, beat in beats:
            entries.setdefault((beat.project_id, uid), []).append(_entry(beat, tz))
        offs: dict[tuple[str, str], list[RecordAbsence]] = {}
        for uid, absence in absences:
            offs.setdefault((absence.project_id, uid), []).append(
                RecordAbsence(date=absence.date, type=absence.type.value, half_day=absence.half_day)
            )

        out: list[ProjectRecord] = []
        for project in projects:
            member_records: list[MemberRecord] = []
            for a in (x for x in assignments if x.project_id == project.id):
                key = (project.id, a.user_id)
                own = entries.get(key, [])
                membership = members.get(a.user_id)
                member_records.append(
                    MemberRecord(
                        user_id=a.user_id,
                        name=membership.name if membership else "a former member",
                        shared_from=a.shared_from,
                        active=a.active,
                        hours=round(sum(e.hours for e in own), 2),
                        entries=own,
                        absences=offs.get(key, []),
                        has_contract=a.contract is not None,
                        balance=await self._balance(organisation_id, a, today, tz),
                        totals=totals.get(key, MemberTotals()),
                    )
                )
            out.append(ProjectRecord(project, member_records))
        return Record(organisation, month, first, last, out)

    async def record(self, organisation_id: str, actor: str, month: date, tz: ZoneInfo) -> Record:
        """What the organisation sees: an admin's read of every project."""
        member = await self._member(organisation_id, actor, OrgRole.ADMIN)
        projects = await self.store.list_projects(organisation_id)
        return await self._record(member.organisation, projects, month, tz, user_id=None)

    async def visible(
        self, organisation_id: str, user_id: str, month: date, tz: ZoneInfo
    ) -> Record:
        """What the organisation sees of one member — `record` with the
        member's own id, over the projects they are or were assigned to.
        Members and former members alike may ask."""
        membership = await self.store.membership(organisation_id, user_id)
        organisation = await self.store.get_organisation(organisation_id)
        if membership is None or organisation is None:
            raise OrganisationNotFound()
        assignments = await self.store.list_assignments(
            organisation_id, user_id=user_id, active_only=False
        )
        named = await self.store.project_names(organisation_id, (a.project_id for a in assignments))
        projects = sorted(named.values(), key=lambda p: p.name)
        return await self._record(organisation, projects, month, tz, user_id=user_id)

    async def archive(
        self,
        organisation_id: str,
        user_id: str,
        beats: OrganisationBeatReader,
        absences: OrganisationAbsenceReader,
        tz: ZoneInfo,
    ) -> Archive:
        """The person's own hours and days off stamped as this organisation's
        record, grouped by project — read-only, kept after leaving,
        exportable. Read through the person's own user-scoped repositories:
        it is their view."""
        membership = await self.store.membership(organisation_id, user_id)
        organisation = await self.store.get_organisation(organisation_id)
        if membership is None or organisation is None:
            raise OrganisationNotFound()
        own = await beats.list_for_organisation(organisation_id)
        days_off = await absences.list_for_organisation(organisation_id)
        project_ids = {b.project_id for b in own} | {a.project_id for a in days_off}
        names = await self.store.project_names(organisation_id, project_ids)
        entries: dict[str, list[RecordEntry]] = {pid: [] for pid in project_ids}
        offs: dict[str, list[RecordAbsence]] = {pid: [] for pid in project_ids}
        for beat in own:
            entries[beat.project_id].append(_entry(beat, tz))
        for absence in days_off:
            offs[absence.project_id].append(
                RecordAbsence(date=absence.date, type=absence.type.value, half_day=absence.half_day)
            )
        projects = [
            ArchiveProject(
                project_id=pid,
                name=names[pid].name if pid in names else "a project since removed",
                color=names[pid].color if pid in names else None,
                hours=round(sum(e.hours for e in entries[pid]), 2),
                entries=entries[pid],
                absences=offs[pid],
            )
            for pid in sorted(project_ids)
        ]
        return Archive(
            organisation=organisation,
            membership=membership,
            hours=round(sum(p.hours for p in projects), 2),
            projects=projects,
        )


def archive_csv(archive: Archive) -> str:
    """The archive as RFC 4180 CSV: a row per entry and per absence —
    project, local day, kind (`entry`, or the absence's type), start, end,
    hours and the note; an absence's start, end and hours are blank, and a
    half day says so in the note's place."""
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["project", "day", "kind", "start", "end", "hours", "note"])
    for project in archive.projects:
        for e in project.entries:
            writer.writerow(
                [
                    project.name,
                    e.day.isoformat(),
                    "entry",
                    e.start.isoformat(),
                    e.end.isoformat(),
                    f"{e.hours:.2f}",
                    e.note or "",
                ]
            )
        for a in project.absences:
            writer.writerow(
                [
                    project.name,
                    a.date.isoformat(),
                    a.type,
                    "",
                    "",
                    "",
                    "half day" if a.half_day else "",
                ]
            )
    return out.getvalue()
