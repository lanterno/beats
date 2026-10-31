"""Organisations API router (docs/organisations.md).

The one prefix in the API whose reads cross users, and so the rules it keeps
are worth stating where they apply:

- **An organisation is reached by membership, not by id.** Every route under
  `/{id}` resolves the caller's active membership first; a non-member and an
  unknown organisation both read as 404 (ORGANISATION_NOT_FOUND), and a
  member without the role as 403 (ORGANISATION_ROLE_REQUIRED).
- **The organisation reads its own stamp and nothing else.** `/record` and
  `/visible` are served by `OrganisationService._record` over
  `MongoOrganisationRecords`, whose queries name the organisation's stamp and
  its project ids. Flow scores, tags, biometrics, the coach and a member's
  personal projects are in no query here — proven in `TestOrganisationWall`.
- **Nothing here says anything about now.** Only finished entries are read,
  and no response carries a running flag (decision 2).
- **No device reaches this prefix.** It is not in `DEVICE_ALLOWED_PREFIXES`,
  and connecting a project lives here rather than under `/api/projects` for
  that reason: a paired device must not be able to hand a project over.
- **An invite token is sent in a header, never in the path.** Cloud Run's
  request log records every request's full URL and the project's `_Default`
  bucket keeps it 30 days, so a token in the path is an unused invitation
  sitting in the logs for anyone who can read them (#376). Headers are not
  logged. The link people share is unchanged — it is
  `/organisations/join/<token>` on the web app, which reads the token out of
  its own URL and puts it here.
"""

import http
from typing import Annotated, Any

from fastapi import APIRouter, Header, Query, Response

from beats.api.dependencies import (
    AbsenceRepoDep,
    BeatRepoDep,
    CurrentUserId,
    OrganisationServiceDep,
    RequiredTimezoneDep,
    TimezoneDep,
)
from beats.api.params import MonthQuery
from beats.api.schemas import (
    ArchiveProjectResponse,
    ArchiveResponse,
    AssignmentResponse,
    CloseOrganisationRequest,
    ConnectProjectRequest,
    DecideRequest,
    InvitationResponse,
    InvitePreviewResponse,
    InviteRequest,
    InviteResponse,
    JoinRequestResponse,
    JoinResponse,
    MemberBalanceResponse,
    MemberRecordResponse,
    MemberResponse,
    MembershipResponse,
    MergeProjectRequest,
    OrganisationCardResponse,
    OrganisationResponse,
    OrgProjectRequest,
    OrgProjectResponse,
    ProjectRecordResponse,
    RecordAbsenceResponse,
    RecordEntryResponse,
    RecordResponse,
    RoleRequest,
)
from beats.domain.models import Organisation, OrganisationFields, OrgMembership
from beats.domain.organisations import (
    Archive,
    Member,
    ProjectMembers,
    Record,
    RecordEntry,
    archive_csv,
)

router = APIRouter(
    prefix="/api/organisations",
    tags=["Organisations"],
    responses={404: {"description": "Not found"}},
)

# The invite token, out of the URL and into a header it is not logged from.
# A missing one is a 422: the request is malformed, which is not the same
# answer as a token that failed to resolve.
INVITE_TOKEN_HEADER = "X-Invite-Token"


def _organisation(organisation: Organisation) -> OrganisationResponse:
    assert organisation.id is not None
    return OrganisationResponse(**organisation.model_dump())


def _card(organisation: Organisation) -> OrganisationCardResponse:
    assert organisation.id is not None
    return OrganisationCardResponse(
        id=organisation.id, name=organisation.name, logo_url=organisation.logo_url
    )


def _membership(member: Member) -> MembershipResponse:
    m = member.membership
    return MembershipResponse(
        user_id=m.user_id,
        organisation=_organisation(member.organisation),
        role=m.role,
        joined_at=m.joined_at,
        left_at=m.left_at,
        left_reason=m.left_reason,
    )


def _member(m: OrgMembership) -> MemberResponse:
    return MemberResponse(
        user_id=m.user_id,
        name=m.name,
        email=m.email,
        role=m.role,
        joined_at=m.joined_at,
        left_at=m.left_at,
    )


def _project(pm: ProjectMembers) -> OrgProjectResponse:
    return OrgProjectResponse(
        **pm.project.model_dump(),
        members=[
            AssignmentResponse(
                user_id=a.user_id,
                name=m.name if m else None,
                shared_from=a.shared_from,
                assigned_at=a.assigned_at,
                ended_at=a.ended_at,
                has_contract=a.contract is not None,
            )
            for a, m in pm.assignments
        ],
    )


def _entries(entries: list[RecordEntry]) -> list[RecordEntryResponse]:
    return [RecordEntryResponse(**e._asdict()) for e in entries]


def _record(record: Record) -> RecordResponse:
    return RecordResponse(
        organisation=_card(record.organisation),
        month=record.month.strftime("%Y-%m"),
        first=record.first,
        last=record.last,
        projects=[
            ProjectRecordResponse(
                project=p.project,
                members=[
                    MemberRecordResponse(
                        user_id=m.user_id,
                        name=m.name,
                        shared_from=m.shared_from,
                        active=m.active,
                        hours=m.hours,
                        entries=_entries(m.entries),
                        absences=[RecordAbsenceResponse(**a._asdict()) for a in m.absences],
                        has_contract=m.has_contract,
                        balance=MemberBalanceResponse(**m.balance._asdict()) if m.balance else None,
                        totals=m.totals,
                    )
                    for m in p.members
                ],
            )
            for p in record.projects
        ],
    )


def _archive(archive: Archive) -> ArchiveResponse:
    m = archive.membership
    return ArchiveResponse(
        organisation=_card(archive.organisation),
        role=m.role,
        joined_at=m.joined_at,
        left_at=m.left_at,
        hours=archive.hours,
        projects=[
            ArchiveProjectResponse(
                project_id=p.project_id,
                name=p.name,
                color=p.color,
                hours=p.hours,
                entries=_entries(p.entries),
                absences=[RecordAbsenceResponse(**a._asdict()) for a in p.absences],
            )
            for p in archive.projects
        ],
    )


# --- mine --------------------------------------------------------------------


@router.get("/", response_model=list[MembershipResponse])
async def list_mine(user_id: CurrentUserId, service: OrganisationServiceDep):
    """Every organisation the caller is or was a member of, with their role
    and, for one they left, when and how."""
    return [_membership(m) for m in await service.mine(user_id)]


@router.post("/", status_code=http.HTTPStatus.CREATED, response_model=MembershipResponse)
async def create_organisation(
    fields: OrganisationFields, user_id: CurrentUserId, service: OrganisationServiceDep
):
    """Create an organisation; the caller is its first owner. 400 for a
    holiday region the calendar does not know (UNKNOWN_HOLIDAY_REGION) or a
    timezone the database does not (INVALID_TIMEZONE)."""
    return _membership(await service.create(user_id, fields))


@router.get("/invitations", response_model=list[InvitationResponse])
async def list_invitations(user_id: CurrentUserId, service: OrganisationServiceDep):
    """The open invitations addressed to the caller's own email address —
    who has invited them, and as what. Without the token: an address is
    not verified at sign-up, so the way in stays the link the inviter passed
    on, and `POST /join` checks it against the address as well."""
    return [
        InvitationResponse(
            role=invite.role,
            expires_at=invite.expires_at,
            organisation=_card(organisation),
        )
        for invite, organisation in await service.my_invitations(user_id)
    ]


@router.get("/join", response_model=InvitePreviewResponse)
async def preview_invite(
    user_id: CurrentUserId,
    service: OrganisationServiceDep,
    token: Annotated[str, Header(alias=INVITE_TOKEN_HEADER)],
):
    """What an invite token opens: the organisation's name and the role it
    gives. 404 for a token that is unknown or addressed to another address
    (INVITE_NOT_FOUND), 410 for one that was real and is closed
    (INVITE_EXPIRED)."""
    invite, organisation, membership = await service.preview_invite(token, user_id)
    return InvitePreviewResponse(
        organisation=_card(organisation),
        role=invite.role,
        requires_approval=invite.requires_approval,
        addressed=invite.email is not None,
        already_member=membership is not None,
    )


@router.post("/join", response_model=JoinResponse)
async def join(
    user_id: CurrentUserId,
    service: OrganisationServiceDep,
    token: Annotated[str, Header(alias=INVITE_TOKEN_HEADER)],
):
    """Take an invite. Joining makes one membership document and nothing
    else: no second account, no moved data (rule 1). A link with an approval
    step answers `pending` and leaves a request for an admin. 409 when
    already a member (ALREADY_A_MEMBER) or already waiting
    (JOIN_REQUEST_PENDING)."""
    member, _request = await service.join(token, user_id)
    if member is not None:
        return JoinResponse(status="joined", membership=_membership(member))
    return JoinResponse(status="pending")


# --- one organisation ------------------------------------------------------------


@router.get("/{organisation_id}", response_model=MembershipResponse)
async def get_organisation(
    organisation_id: str, user_id: CurrentUserId, service: OrganisationServiceDep
):
    """The organisation and the caller's standing in it. Members only."""
    return _membership(await service.get(organisation_id, user_id))


@router.put("/{organisation_id}", response_model=OrganisationResponse)
async def update_organisation(
    organisation_id: str,
    fields: OrganisationFields,
    user_id: CurrentUserId,
    service: OrganisationServiceDep,
):
    """Replace the organisation's settings. Admins."""
    return _organisation(await service.update(organisation_id, user_id, fields))


@router.post("/{organisation_id}/close", response_model=OrganisationResponse)
async def begin_closing(
    organisation_id: str,
    request: CloseOrganisationRequest,
    user_id: CurrentUserId,
    service: OrganisationServiceDep,
):
    """Start the organisation's notice (#347): it closes on the day given —
    at least 30 days out, 60 by default — shown to every member in-app so
    they export on their own clock. Tracking carries on until the day.
    Owners."""
    return _organisation(await service.begin_closing(organisation_id, user_id, request.closes_on))


@router.delete("/{organisation_id}/close", response_model=OrganisationResponse)
async def cancel_closing(
    organisation_id: str, user_id: CurrentUserId, service: OrganisationServiceDep
):
    """Call the closing off. Owners."""
    return _organisation(await service.cancel_closing(organisation_id, user_id))


@router.delete("/{organisation_id}", status_code=http.HTTPStatus.NO_CONTENT)
async def delete_organisation(
    organisation_id: str, user_id: CurrentUserId, service: OrganisationServiceDep
):
    """Delete the organisation, once its notice has run out (#347). Every
    member is handed back a personal copy of each project they hold rows or
    a contract on — their rows repointed and unstamped, theirs as ever —
    and everything that was the organisation's goes, its working-time
    record with it: the final record.csv and compliance.csv were the notice
    period's job. Owners; 409 before `closes_on`."""
    await service.delete_organisation(organisation_id, user_id)


@router.get("/{organisation_id}/members", response_model=list[MemberResponse])
async def list_members(
    organisation_id: str, user_id: CurrentUserId, service: OrganisationServiceDep
):
    """The active members, by the name and address each joined under."""
    return [_member(m) for m in await service.members(organisation_id, user_id)]


@router.patch("/{organisation_id}/members/{member_user_id}", response_model=MemberResponse)
async def set_role(
    organisation_id: str,
    member_user_id: str,
    request: RoleRequest,
    user_id: CurrentUserId,
    service: OrganisationServiceDep,
):
    """Change a member's role. Admins; the owner role is given and taken by
    owners alone (403 OWNER_ROLE_RESERVED), and the last owner keeps it
    (409 LAST_OWNER)."""
    return _member(await service.set_role(organisation_id, user_id, member_user_id, request.role))


@router.delete(
    "/{organisation_id}/members/{member_user_id}", status_code=http.HTTPStatus.NO_CONTENT
)
async def remove_member(
    organisation_id: str,
    member_user_id: str,
    user_id: CurrentUserId,
    service: OrganisationServiceDep,
) -> Response:
    """Remove a member: their assignments end, tracking to the
    organisation's projects stops, and the organisation keeps its record of
    their hours. Admins; an owner only by an owner, never the last."""
    await service.remove_member(organisation_id, user_id, member_user_id)
    return Response(status_code=http.HTTPStatus.NO_CONTENT)


@router.post("/{organisation_id}/leave", response_model=MembershipResponse)
async def leave(organisation_id: str, user_id: CurrentUserId, service: OrganisationServiceDep):
    """Leave. Every assignment ends, the organisation's projects leave the
    caller's list, the organisation keeps its working-time record, and the
    caller keeps `/archive`. 409 LAST_OWNER for the only owner."""
    return _membership(await service.leave(organisation_id, user_id))


# --- invites and requests -------------------------------------------------------


@router.post(
    "/{organisation_id}/invites", status_code=http.HTTPStatus.CREATED, response_model=InviteResponse
)
async def create_invite(
    organisation_id: str,
    request: InviteRequest,
    user_id: CurrentUserId,
    service: OrganisationServiceDep,
):
    """An invitation to one address, taken once by the account that holds
    it, or with no address an invite link anyone may use until it expires.
    The token is returned here and nowhere else: the API sends no email, the
    inviter passes it on. Admins."""
    invite = await service.invite(
        organisation_id,
        user_id,
        email=request.email,
        role=request.role,
        requires_approval=request.requires_approval,
        expires_in_days=request.expires_in_days,
    )
    return InviteResponse(**invite.model_dump(exclude={"organisation_id", "created_by"}))


@router.get("/{organisation_id}/invites", response_model=list[InviteResponse])
async def list_invites(
    organisation_id: str, user_id: CurrentUserId, service: OrganisationServiceDep
):
    """The open invites. Admins."""
    return [
        InviteResponse(**i.model_dump(exclude={"organisation_id", "created_by"}))
        for i in await service.invites(organisation_id, user_id)
    ]


@router.delete("/{organisation_id}/invites/{invite_id}", status_code=http.HTTPStatus.NO_CONTENT)
async def revoke_invite(
    organisation_id: str, invite_id: str, user_id: CurrentUserId, service: OrganisationServiceDep
) -> Response:
    """Revoke an invite: its token stops working at once. Admins."""
    await service.revoke_invite(organisation_id, user_id, invite_id)
    return Response(status_code=http.HTTPStatus.NO_CONTENT)


@router.get("/{organisation_id}/requests", response_model=list[JoinRequestResponse])
async def list_requests(
    organisation_id: str, user_id: CurrentUserId, service: OrganisationServiceDep
):
    """The join requests waiting on an invite link with an approval step,
    each with the role approving it would grant. Admins."""
    return [
        JoinRequestResponse(
            **r.model_dump(include={"id", "user_id", "name", "email", "requested_at"}),
            role=role,
        )
        for r, role in await service.requests(organisation_id, user_id)
    ]


@router.post("/{organisation_id}/requests/{request_id}", response_model=JoinRequestResponse)
async def decide_request(
    organisation_id: str,
    request_id: str,
    request: DecideRequest,
    user_id: CurrentUserId,
    service: OrganisationServiceDep,
):
    """Approve or decline a join request; approving makes the member. Admins."""
    decided, role = await service.decide_request(
        organisation_id, user_id, request_id, request.decision
    )
    return JoinRequestResponse(
        **decided.model_dump(include={"id", "user_id", "name", "email", "requested_at"}),
        role=role,
    )


# --- projects -------------------------------------------------------------------


@router.get("/{organisation_id}/projects", response_model=list[OrgProjectResponse])
async def list_projects(
    organisation_id: str,
    user_id: CurrentUserId,
    service: OrganisationServiceDep,
    archived: Annotated[bool | None, Query()] = None,
):
    """The organisation's projects with who is on each. Admins."""
    return [_project(pm) for pm in await service.projects(organisation_id, user_id, archived)]


@router.post(
    "/{organisation_id}/projects",
    status_code=http.HTTPStatus.CREATED,
    response_model=OrgProjectResponse,
)
async def create_project(
    organisation_id: str,
    request: OrgProjectRequest,
    user_id: CurrentUserId,
    service: OrganisationServiceDep,
):
    """A project the organisation owns: it appears on a member's list once
    they are assigned. Admins."""
    return _project(await service.create_project(organisation_id, user_id, request.model_dump()))


@router.put("/{organisation_id}/projects/{project_id}", response_model=OrgProjectResponse)
async def update_project(
    organisation_id: str,
    project_id: str,
    request: OrgProjectRequest,
    user_id: CurrentUserId,
    service: OrganisationServiceDep,
):
    """Write the organisation's fields of one of its projects — name,
    colour, kind, description, repository, category, archived. A field left
    out keeps its value. Admins."""
    sent: dict[str, Any] = {k: getattr(request, k) for k in request.model_fields_set}
    return _project(await service.update_project(organisation_id, user_id, project_id, sent))


@router.post(
    "/{organisation_id}/projects/{project_id}/merge",
    response_model=OrgProjectResponse,
)
async def merge_project(
    organisation_id: str,
    project_id: str,
    request: MergeProjectRequest,
    user_id: CurrentUserId,
    service: OrganisationServiceDep,
):
    """Fold this project into another of the organisation's — the way out
    of the duplicate a connect leaves when the organisation already had a
    project for the same work. Every row moves with its stamp untouched,
    assignments fold (the earlier shared-from; the target's contract
    stands), and the merged project is deleted. Refused while an approved
    timesheet exists on either side (409 PERIOD_APPROVED). Admins."""
    return _project(await service.merge_project(organisation_id, user_id, project_id, request.into))


@router.put(
    "/{organisation_id}/projects/{project_id}/members/{member_user_id}",
    response_model=AssignmentResponse,
)
async def assign(
    organisation_id: str,
    project_id: str,
    member_user_id: str,
    user_id: CurrentUserId,
    service: OrganisationServiceDep,
):
    """Put a member on a project: it appears on their list, and their hours
    on it are the organisation's from now. Admins."""
    a = await service.assign(organisation_id, user_id, project_id, member_user_id)
    return AssignmentResponse(
        user_id=a.user_id,
        name=await service.member_name(organisation_id, member_user_id),
        shared_from=a.shared_from,
        assigned_at=a.assigned_at,
        ended_at=a.ended_at,
        has_contract=a.contract is not None,
    )


@router.delete(
    "/{organisation_id}/projects/{project_id}/members/{member_user_id}",
    status_code=http.HTTPStatus.NO_CONTENT,
)
async def unassign(
    organisation_id: str,
    project_id: str,
    member_user_id: str,
    user_id: CurrentUserId,
    service: OrganisationServiceDep,
) -> Response:
    """Take a member off a project: it leaves their list and their tracking
    to it stops; the hours already on it stay the organisation's. Admins."""
    await service.unassign(organisation_id, user_id, project_id, member_user_id)
    return Response(status_code=http.HTTPStatus.NO_CONTENT)


@router.post("/{organisation_id}/connect", response_model=AssignmentResponse)
async def connect_project(
    organisation_id: str,
    request: ConnectProjectRequest,
    user_id: CurrentUserId,
    service: OrganisationServiceDep,
    beats: BeatRepoDep,
    absences: AbsenceRepoDep,
    tz: RequiredTimezoneDep,
):
    """Connect one of the caller's own projects to the organisation (rule 4):
    the project becomes the organisation's, its goal, local repo paths and
    contract stay the caller's, and the caller's hours and absences on it
    from `share_from` — a local day in `tz`, which is required — are the
    organisation's record; null shares nothing before now. Any member.
    409 on a project billed to a client (PROJECT_HAS_BILLING), one already
    an organisation's (ORGANISATION_PROJECT), or a day after today
    (SHARE_FROM_IN_FUTURE)."""
    a = await service.connect_project(
        organisation_id, user_id, request.project_id, request.share_from, tz, beats, absences
    )
    return AssignmentResponse(
        user_id=a.user_id,
        name=await service.member_name(organisation_id, user_id),
        shared_from=a.shared_from,
        assigned_at=a.assigned_at,
        ended_at=a.ended_at,
        has_contract=a.contract is not None,
    )


# --- the record -------------------------------------------------------------------


@router.get("/{organisation_id}/record", response_model=RecordResponse)
async def read_record(
    organisation_id: str,
    month: MonthQuery,
    user_id: CurrentUserId,
    service: OrganisationServiceDep,
):
    """What the organisation sees: per project, per member, the finished
    entries started in `month` in the organisation's timezone (start, end,
    hours, note), the absences (date, type, half day), the all-time totals,
    and where the member has a contract its balance as of today. Nothing
    else, and nothing about now. Owners, admins and viewers whole; a manager
    their teams'. The month is the organisation's timezone's, never the
    caller's: a `tz` sent by an older client is ignored."""
    return _record(await service.scoped_record(organisation_id, user_id, month))


@router.get("/{organisation_id}/visible", response_model=RecordResponse)
async def read_visible(
    organisation_id: str,
    month: MonthQuery,
    user_id: CurrentUserId,
    service: OrganisationServiceDep,
):
    """What the organisation sees of the caller — the "what Acme can see"
    page: `/record` narrowed to one member by the same read, so it shows
    the data actually held, not a description of it, in the organisation's
    timezone as the record is. Members and former members."""
    return _record(await service.visible(organisation_id, user_id, month))


@router.get("/{organisation_id}/archive", response_model=ArchiveResponse)
async def read_archive(
    organisation_id: str,
    user_id: CurrentUserId,
    service: OrganisationServiceDep,
    beats: BeatRepoDep,
    absences: AbsenceRepoDep,
    tz: TimezoneDep,
):
    """The caller's own hours that are this organisation's record, by
    project: the read-only "Acme (left)" archive, kept after leaving. Read
    through the caller's own repository. Members and former members."""
    return _archive(await service.archive(organisation_id, user_id, beats, absences, tz))


@router.get(
    "/{organisation_id}/archive.csv",
    response_class=Response,
    responses={200: {"description": "The archive as CSV.", "content": {"text/csv": {}}}},
)
async def read_archive_csv(
    organisation_id: str,
    user_id: CurrentUserId,
    service: OrganisationServiceDep,
    beats: BeatRepoDep,
    absences: AbsenceRepoDep,
    tz: TimezoneDep,
) -> Response:
    """`/archive` as CSV, a row per entry, for the person to keep."""
    archive = await service.archive(organisation_id, user_id, beats, absences, tz)
    return Response(
        content=archive_csv(archive),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment"},
    )
