"""Organisation schemas (docs/organisations.md).

Split out of `schemas.py` at the ceiling in roadmaps/file-sizes.md and
re-exported from it, so every router still imports `beats.api.schemas`.
"""

from datetime import date as date_type
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from beats.domain.models import (
    JoinDecision,
    MembershipEnd,
    MemberTotals,
    OrganisationFields,
    OrgProject,
    OrgRole,
    ProjectKind,
)

# --- Organisations (docs/organisations.md) ------------------------------------


class OrganisationResponse(OrganisationFields):
    id: str
    created_at: datetime
    # The closing state (#347): every member's banner reads it.
    closes_on: date_type | None = None


class MembershipResponse(BaseModel):
    """One of the caller's organisations, with their standing in it. A
    membership that ended (`left_at`) is listed too: the archive of the
    person's own hours there is reached through it.

    `user_id` is the caller's own, so a client can tell which row of
    `/members` or which timesheet is theirs without matching on the address
    they joined under — which an account that changed its email, or signed
    in through a provider, no longer has."""

    user_id: str
    organisation: OrganisationResponse
    role: OrgRole
    joined_at: datetime
    left_at: datetime | None
    left_reason: MembershipEnd | None


class MemberResponse(BaseModel):
    """A member as the organisation lists them: the name and address they
    joined under. `user_id` is a tombstone once the account has been erased."""

    user_id: str
    name: str
    email: str
    role: OrgRole
    joined_at: datetime
    left_at: datetime | None


class RoleRequest(BaseModel):
    role: OrgRole


class InviteRequest(BaseModel):
    """An invitation to one address, or with `email` null an invite link.
    `requires_approval` is read on a link alone; no invite carries the
    owner role (403 OWNER_ROLE_RESERVED)."""

    email: str | None = Field(default=None, max_length=254)
    role: OrgRole = OrgRole.MEMBER
    requires_approval: bool = False
    expires_in_days: int = Field(default=14, ge=1, le=90)


class InviteResponse(BaseModel):
    id: str
    email: str | None
    role: OrgRole
    requires_approval: bool
    token: str
    created_at: datetime
    expires_at: datetime
    accepted_at: datetime | None


class OrganisationCardResponse(BaseModel):
    """An organisation as a joiner sees it before joining: the name and logo."""

    id: str
    name: str
    logo_url: str | None


class InvitationResponse(BaseModel):
    """An open invitation addressed to the caller's own address: who, and as
    what. Not the token — an address is not verified at sign-up, so the way
    in is the link the inviter passed on, which the join route then checks
    against the address too."""

    role: OrgRole
    expires_at: datetime
    organisation: OrganisationCardResponse


class InvitePreviewResponse(BaseModel):
    organisation: OrganisationCardResponse
    role: OrgRole
    requires_approval: bool
    addressed: bool  # to the caller's address, as opposed to a link
    already_member: bool


class JoinResponse(BaseModel):
    """`joined`, with the membership; or `pending`, when the link has an
    approval step and a request is now waiting."""

    status: Literal["joined", "pending"]
    membership: MembershipResponse | None = None


class JoinRequestResponse(BaseModel):
    """A join request with the role approving it grants — the invite's, so
    the admin decides knowing what they are handing over."""

    id: str
    user_id: str
    name: str
    email: str
    role: OrgRole
    requested_at: datetime


class DecideRequest(BaseModel):
    decision: JoinDecision


class OrgProjectRequest(BaseModel):
    """The organisation's fields of one of its projects. On an update a
    field left out is kept and `null` clears a nullable one."""

    name: str = Field(min_length=1, max_length=120)
    description: str | None = None
    color: str | None = None
    kind: ProjectKind = ProjectKind.SIDE_PROJECT
    github_repo: str | None = None
    category: str | None = None
    archived: bool = False


class MergeProjectRequest(BaseModel):
    """Which project the merged one folds into."""

    into: str = Field(min_length=1)


class CloseOrganisationRequest(BaseModel):
    """When the organisation closes; left out, the default notice runs."""

    closes_on: date_type | None = None


class AssignmentResponse(BaseModel):
    user_id: str
    name: str | None
    shared_from: datetime
    assigned_at: datetime
    ended_at: datetime | None
    has_contract: bool


class OrgProjectResponse(OrgProject):
    members: list[AssignmentResponse]


class ConnectProjectRequest(BaseModel):
    """Connect one of the caller's own projects: from `share_from` (a local
    day in `tz`) the hours and absences on it are the organisation's; null
    starts fresh from now."""

    project_id: str
    share_from: date_type | None = None


class RecordEntryResponse(BaseModel):
    """One finished entry as the organisation reads it: when, how long, and
    the note (decision 1). Nothing about the person beyond that."""

    id: str
    day: date_type
    start: datetime
    end: datetime
    hours: float
    note: str | None


class RecordAbsenceResponse(BaseModel):
    date: date_type
    type: str
    half_day: bool


class MemberBalanceResponse(BaseModel):
    as_of: date_type
    balance: float
    opening: float
    worked: float
    expected_through: float
    adjusted: float


class MemberRecordResponse(BaseModel):
    user_id: str
    name: str
    shared_from: datetime
    active: bool
    hours: float
    entries: list[RecordEntryResponse]
    absences: list[RecordAbsenceResponse]
    has_contract: bool
    balance: MemberBalanceResponse | None
    totals: MemberTotals


class ProjectRecordResponse(BaseModel):
    project: OrgProject
    members: list[MemberRecordResponse]


class RecordResponse(BaseModel):
    """What the organisation sees (`GET /{id}/record`), and what it sees of
    one member (`GET /{id}/visible`) — the same shape from the same read,
    narrowed to one person. Written field by field, as the public report
    is, so what crosses cannot grow by inheritance."""

    organisation: OrganisationCardResponse
    month: str
    first: date_type
    last: date_type
    projects: list[ProjectRecordResponse]


class ArchiveProjectResponse(BaseModel):
    project_id: str
    name: str
    color: str | None
    hours: float
    entries: list[RecordEntryResponse]
    absences: list[RecordAbsenceResponse]


class ArchiveResponse(BaseModel):
    """The person's own hours stamped as one organisation's record, after
    leaving or before: read-only, grouped by project."""

    organisation: OrganisationCardResponse
    role: OrgRole
    joined_at: datetime
    left_at: datetime | None
    hours: float
    projects: list[ArchiveProjectResponse]
