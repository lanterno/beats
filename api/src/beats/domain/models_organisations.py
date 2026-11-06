"""Organisations and employment (docs/organisations.md).

Split out of `models.py` at the ceiling in roadmaps/file-sizes.md and
re-exported from it, so every import site still names `beats.domain.models`.
"""

from datetime import UTC, datetime
from datetime import date as date_type
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    Field,
    StringConstraints,
    model_validator,
)

from beats.domain.models_contracts import (
    AbsenceType,
    Contract,
    GoalOverride,
    GoalType,
    ProjectKind,
)
from beats.domain.utils import TzNormalizedModel, normalize_tz

# Who kind of actor wrote an organisation's audit row. A plain alias so the
# writers (`_audit`, `record_org_audit`) and the model agree by construction.
ActorKind = Literal["member", "system", "operator"]


# --- Organisations (docs/organisations.md) ---------------------------------


class OrgRole(StrEnum):
    """What a member may do in an organisation.

    Owner and admin run it; a **manager** decides absences and timesheets
    for the members of their teams and reads their slice of the record; a
    **viewer** (an accountant, a works council seat) reads the whole record
    and changes nothing; a member tracks. The ladder (`at_least`) orders
    them for the owner/admin checks; what the middle roles may do is the
    three capabilities below, not the ladder.
    """

    OWNER = "owner"
    ADMIN = "admin"
    MANAGER = "manager"
    VIEWER = "viewer"
    MEMBER = "member"

    @property
    def rank(self) -> int:
        return _ROLE_RANK[self]

    def at_least(self, other: OrgRole) -> bool:
        return self.rank >= other.rank

    @property
    def administers(self) -> bool:
        """Members, invites, projects, assignments, settings, teams, audit."""
        return self in (OrgRole.OWNER, OrgRole.ADMIN)

    @property
    def decides(self) -> bool:
        """Absence requests, timesheets, admin-entered time, managed
        contracts — an owner or admin for anyone, a manager for the members
        of their teams."""
        return self in (OrgRole.OWNER, OrgRole.ADMIN, OrgRole.MANAGER)

    @property
    def reads_record(self) -> bool:
        """The record, the compliance record and the report CSVs — a manager
        for their teams, a viewer for everyone."""
        return self is not OrgRole.MEMBER


_ROLE_RANK = {
    OrgRole.MEMBER: 0,
    OrgRole.VIEWER: 1,
    OrgRole.MANAGER: 2,
    OrgRole.ADMIN: 3,
    OrgRole.OWNER: 4,
}


class WeekStart(StrEnum):
    """Which day an organisation's week begins on, for its own reports."""

    MONDAY = "monday"
    SATURDAY = "saturday"
    SUNDAY = "sunday"


_OrgName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]


class OrganisationFields(BaseModel):
    """What an organisation is set up with: the fields its admins write."""

    name: _OrgName
    logo_url: Annotated[str, StringConstraints(max_length=2000)] | None = None
    week_start: WeekStart = WeekStart.MONDAY
    # The region whose public holidays a contract under it defaults to; checked
    # against the calendar library at write time, as a contract's region is.
    holiday_country: str | None = None
    holiday_subdivision: str | None = None
    timezone: str = "UTC"
    # Years the working-time record is kept, counted from each record's
    # date; None reads as the default (domain/retention.py). Checked on
    # write against the statutory floor of `holiday_country` — a setting
    # below it is RETENTION_BELOW_FLOOR. Stored only: the enforcement is
    # the operator-run purge, never a background job during the beta.
    retention_years: int | None = Field(default=None, ge=1, le=99)


class Organisation(OrganisationFields, TzNormalizedModel):
    """A party that owns projects and reads the hours on them. Not a user,
    and not scoped by one: `user_id` is a column of no document here."""

    id: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    created_by: str
    # The closing state (#347): set by an owner with notice, shown to every
    # member in-app, and the gate deletion waits behind. Not a settings
    # field — the settings PUT replaces OrganisationFields and leaves this.
    closes_on: date_type | None = None


class MembershipEnd(StrEnum):
    """Why a membership ended."""

    LEFT = "left"
    REMOVED = "removed"
    ERASED = "erased"  # the account was deleted; the record stays (decision 3)


class OrgMembership(TzNormalizedModel):
    """One person in one organisation, once: a membership that ends keeps its
    document, with `left_at`, and joining again reopens it.

    `name` and `email` are what the organisation knew the person by, taken
    from the account when they joined. They stay when the account is erased
    and `user_id` becomes a tombstone (`erased:<membership id>`, which no
    account ever has) — the one place a name outlives its account, as the
    employer's record (docs/organisations.md, decision 3).
    """

    id: str | None = None
    organisation_id: str
    user_id: str
    role: OrgRole
    name: str
    email: str
    joined_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    left_at: datetime | None = None
    left_reason: MembershipEnd | None = None

    @property
    def active(self) -> bool:
        return self.left_at is None


class OrgInvite(TzNormalizedModel):
    """A way in. With `email`, an invitation to one address, taken once; with
    none, a link anyone may use until it expires or is revoked, which with
    `requires_approval` makes a join request rather than a member. The
    token is the whole of what the joiner presents."""

    id: str | None = None
    organisation_id: str
    token: str
    email: str | None = None
    role: OrgRole = OrgRole.MEMBER
    requires_approval: bool = False
    created_by: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime
    accepted_at: datetime | None = None
    accepted_by: str | None = None
    revoked_at: datetime | None = None

    def open_at(self, now: datetime) -> bool:
        """Still usable: not revoked, not expired, and — for an invitation to
        one address — not yet taken."""
        if self.revoked_at is not None or normalize_tz(self.expires_at) <= normalize_tz(now):
            return False
        return self.email is None or self.accepted_at is None


class JoinDecision(StrEnum):
    APPROVED = "approved"
    DECLINED = "declined"


class OrgJoinRequest(TzNormalizedModel):
    """Someone who used an invite link with an approval step, waiting."""

    id: str | None = None
    organisation_id: str
    user_id: str
    invite_id: str
    name: str
    email: str
    requested_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    decided_at: datetime | None = None
    decision: JoinDecision | None = None
    decided_by: str | None = None


class OrgAssignment(TzNormalizedModel):
    """One member on one of the organisation's projects, and the personal
    half of that project for them (`PERSONAL_FIELDS`).

    `shared_from` is the instant from which the member's hours on the
    project are the organisation's: the moment of assignment, or on a
    connected project the local midnight of the day the member chose. An
    assignment that ends keeps its document with `ended_at`; assigning
    again reopens it, from that day.

    `private_before` is the other half of that, and only a connect writes
    it: the instant before which the member's rows on this project are
    theirs alone, whatever a later assignment moves `shared_from` to. See
    `ProjectOrganisation`.
    """

    id: str | None = None
    organisation_id: str
    project_id: str
    user_id: str
    shared_from: datetime
    private_before: datetime | None = None
    private_before_day: date_type | None = None
    assigned_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    assigned_by: str | None = None
    ended_at: datetime | None = None
    weekly_goal: float | None = None
    goal_type: GoalType = GoalType.TARGET
    goal_overrides: list[GoalOverride] = Field(default_factory=list)
    autostart_repos: list[str] = Field(default_factory=list)
    contract: Contract | None = None
    # Stage 3: the contract on this assignment is the employer's to write.
    contract_managed: bool = False

    @property
    def active(self) -> bool:
        return self.ended_at is None


class OrgAuditEvent(TzNormalizedModel):
    """One thing that happened in an organisation, written as it happens:
    membership, roles, projects, assignments, a connected project, an erased
    account, and from stage 3 on contracts, requests, timesheets, entered
    time, teams, merges, closing and retention. Kept from stage 2, before
    anything read it, because it is cheap to write and impossible to
    backfill; owners and admins read it (`GET /{id}/audit`)."""

    id: str | None = None
    organisation_id: str
    at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    actor_user_id: str | None
    # Who kind of actor it was: a member of the organisation, the system
    # (erasure's tombstoning, the retention purge run by hand), or the
    # platform's operator. The operator's id is never in the organisation's
    # log; the kind is enough for an admin to tell an act of ours from an act
    # of theirs. Derived for rows that predate the field: an actor meant a
    # member, none meant the system.
    actor_kind: ActorKind | None = None
    event: str
    subject_user_id: str | None = None
    project_id: str | None = None
    details: dict[str, object] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _derive_actor_kind(self) -> OrgAuditEvent:
        if self.actor_kind is None:
            object.__setattr__(self, "actor_kind", "member" if self.actor_user_id else "system")
        return self


class OrgProject(BaseModel):
    """An organisation's project as the organisation sees it: the document's
    fields (`ORGANISATION_FIELDS`) and nothing personal, since the personal
    half is each member's own."""

    id: str
    name: str
    description: str | None = None
    color: str | None = None
    archived: bool = False
    kind: ProjectKind = ProjectKind.SIDE_PROJECT
    github_repo: str | None = None
    category: str | None = None


class MemberTotals(TzNormalizedModel):
    """What one member's finished entries on one project add up to, all time.
    Mongo hands the instants back naive; this makes them UTC like every other."""

    entries: int = 0
    hours: float = 0.0
    first: datetime | None = None
    last: datetime | None = None


class OrgTeam(TzNormalizedModel):
    """A team inside an organisation: a name and who is in it. What gives a
    manager their scope — a manager decides and reads for the members of
    the teams they are in, and for nobody else (docs/organisations.md,
    stage 4)."""

    id: str | None = None
    organisation_id: str
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
    member_ids: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class RequestStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    DECLINED = "declined"


class OrgAbsenceRequest(TzNormalizedModel):
    """A day off asked for on a managed assignment (docs/organisations.md,
    stage 3): the employee asks, a decider approves — which writes the
    absence, stamped as the organisation's — or declines with a comment.
    The note travels to the absence; the organisation's record never shows
    it (rule 3), but the decider sees it here: it is addressed to them."""

    id: str | None = None
    organisation_id: str
    project_id: str
    user_id: str
    date: date_type
    type: AbsenceType
    half_day: bool = False
    note: str | None = None
    status: RequestStatus = RequestStatus.PENDING
    requested_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    decided_at: datetime | None = None
    decided_by: str | None = None
    comment: str | None = None


class TimesheetStatus(StrEnum):
    SUBMITTED = "submitted"
    APPROVED = "approved"
    CHANGES_REQUESTED = "changes_requested"
    REOPENED = "reopened"


class FrozenMonth(BaseModel):
    """What approval freezes (docs/organisations.md, stage 3): the figures
    as they stood, stored for the first time anywhere in the system. The
    live arithmetic goes on; an approved month's edits are refused, so the
    two cannot drift silently, and a reopen is the recorded way to change
    one. `balance_end` is None where the record withholds the balance
    (decision 16) or no term owes hours."""

    worked: float
    expected: float | None
    balance_end: float | None
    entries: int
    absence_days: float


class TimesheetAction(StrEnum):
    """A step in a timesheet's history. The four states a sheet can be in are
    steps too, and keep their strings, so stored history keeps reading; the
    fifth is a thing that happened to an approved sheet without changing its
    state — the terms behind it moved (docs/organisations.md, decision 23).
    A state and an event are different sets, which is why this is not
    `TimesheetStatus`."""

    SUBMITTED = "submitted"
    APPROVED = "approved"
    CHANGES_REQUESTED = "changes_requested"
    REOPENED = "reopened"
    TERMS_CHANGED = "terms_changed"


class TimesheetEvent(BaseModel):
    """One step of a timesheet's history: submitted, approved, changes
    requested, reopened, or the contract's terms changed under an approval
    — each with who and, where one was given, why."""

    at: datetime
    by: str
    action: TimesheetAction
    comment: str | None = None


class OrgTimesheet(TzNormalizedModel):
    """One member's month on one organisation project, submitted and
    decided (docs/organisations.md, stage 3). One per (project, member,
    month); resubmission reuses the document and appends to `history`.
    While `status` is `approved`, the month is locked: the member's writes
    dated inside it are refused (409 PERIOD_APPROVED), and `frozen` holds
    the figures approval saw. Months are the organisation's own timezone's.
    """

    id: str | None = None
    organisation_id: str
    project_id: str
    user_id: str
    month: date_type  # the 1st, in the organisation's timezone
    status: TimesheetStatus = TimesheetStatus.SUBMITTED
    submitted_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    decided_at: datetime | None = None
    decided_by: str | None = None
    comment: str | None = None
    frozen: FrozenMonth | None = None
    # When the contract behind an approved month last moved, and who moved
    # it (decision 23). `status` stays `approved` — the month is still
    # locked and `frozen` is still the record — but a decider would not
    # necessarily approve the same figures today. A reopen clears both, and
    # the re-approval freezes against the terms now in force. Null on a
    # sheet whose terms still stand.
    superseded_at: datetime | None = None
    superseded_by: str | None = None
    history: list[TimesheetEvent] = Field(default_factory=list)
