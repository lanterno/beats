"""The persistence shapes the domain asks for, declared where they are used.

Two things follow from putting them here rather than importing repository
interfaces from `beats.infrastructure`. The dependency points inward — domain
code no longer reaches out to the layer that is supposed to implement it — and
each protocol lists only the methods its consumer actually calls, so a service
that reads completed beats cannot quietly start writing them.

That narrowness is also what lets the test suite's in-memory fakes stand in.
`AnalyticsService` needs two methods; asking for a whole `BeatRepository` meant
every fake either implemented twelve or lied about its type.

`MongoBeatRepository` and `MongoProjectRepository` satisfy these structurally —
there is nothing to register.
"""

import builtins
from collections.abc import Collection, Iterable
from datetime import date, datetime
from typing import Protocol
from zoneinfo import ZoneInfo

from beats.domain.models import (
    Absence,
    BalanceAdjustment,
    Beat,
    BillableOverride,
    BillingBudget,
    BillingBudgetScope,
    Client,
    ContractWeek,
    FlowWindow,
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
    ProjectBilling,
    ReportLink,
    RequestStatus,
    TimesheetStatus,
    User,
)


class CompletedBeatReader(Protocol):
    """Read access to finished beats. Used by analytics and intelligence."""

    async def list_all_completed(self) -> list[Beat]: ...
    async def list_completed_in_range(self, start: date, end: date) -> list[Beat]: ...


class RangeBeatReader(Protocol):
    """Just the date-range read — all the intelligence services need."""

    async def list_completed_in_range(self, start: date, end: date) -> list[Beat]: ...


class ProjectLister(Protocol):
    """Read access to the project list."""

    # builtins.list because this class defines a method called `list`, which
    # would otherwise shadow the builtin in the annotation.
    async def list(self, archived: bool = False) -> builtins.list[Project]: ...


class FlowWindowReader(Protocol):
    """Flow windows over a time range."""

    async def list_by_range(self, start: datetime, end: datetime) -> list[FlowWindow]: ...


class TimerBeatStore(Protocol):
    """The four beat operations running a timer needs: open one, find the
    open one, find the last one, close it. `update` writes only the fields
    named, as `BeatStore.update` does."""

    async def create(self, beat: Beat) -> Beat: ...
    async def get_active(self) -> Beat | None: ...
    async def get_last(self) -> Beat: ...
    async def update(self, beat: Beat, fields: Collection[str]) -> Beat: ...


class TimerProjectReader(Protocol):
    """What the timer asks about a project before starting against it."""

    async def exists(self, project_id: str) -> bool: ...
    async def get_by_id(self, project_id: str) -> Project: ...


class BeatStore(Protocol):
    """CRUD over beats — what `BeatService` needs, not the twelve methods
    the Mongo repository happens to offer.

    `update` writes the named `fields` of `beat` onto the stored beat with its
    id and nothing else, and returns the beat as stored: a field the write
    does not name (the note an import brought) is never rebuilt from a
    partial model, nor reverted to what was read before an await. It raises
    `BeatNotFound` when the user has no beat with that id.

    `get_active` is here for the one rule a write shares with the timer: at
    most one session may be open at a time, so a create or an edit that
    leaves `end` unset has to look for the open one first."""

    async def get_by_id(self, beat_id: str) -> Beat: ...
    async def get_active(self) -> Beat | None: ...
    async def create(self, beat: Beat) -> Beat: ...
    async def update(self, beat: Beat, fields: Collection[str]) -> Beat: ...
    async def delete(self, beat_id: str) -> bool: ...
    # builtins.list because this class defines a method called `list`.
    async def list(
        self, project_id: str | None = None, date_filter: date | None = None
    ) -> builtins.list[Beat]: ...


class ProjectStore(Protocol):
    """CRUD over projects, plus the list read `ProjectLister` also offers."""

    async def get_by_id(self, project_id: str) -> Project: ...
    async def create(self, project: Project) -> Project: ...
    async def update(self, project: Project) -> Project: ...
    async def list(self, archived: bool = False) -> builtins.list[Project]: ...


class ProjectBeatReader(Protocol):
    """One project's beats, optionally only those from an instant on. All
    `ProjectService` asks of beat storage."""

    async def list_by_project(
        self, project_id: str, since: datetime | None = None
    ) -> list[Beat]: ...


class ProjectReader(Protocol):
    """One project by id. What the contract service asks before doing anything
    to a project: it reads the kind and the contract, and never writes."""

    async def get_by_id(self, project_id: str) -> Project: ...


class AbsenceStore(Protocol):
    """Absences on one project: the range read the arithmetic needs, and the
    two writes a calendar makes. Upsert is keyed on (project, date) — a
    second absence on a day replaces the first. Delete is by id within the
    project, so False means "not on this project". `day_of` is the one
    field a delete has to read first: the day, to judge it against an
    approved month."""

    async def list_by_project(self, project_id: str, start: date, end: date) -> list[Absence]: ...
    async def upsert(self, absence: Absence) -> Absence: ...
    async def delete(self, project_id: str, absence_id: str) -> bool: ...
    async def day_of(self, project_id: str, absence_id: str) -> date | None: ...


class AdjustmentStore(Protocol):
    """Balance adjustments on one project: the range read the balance needs,
    and the two writes the ledger makes. Upsert is keyed on (project, date),
    as an absence's is — a second adjustment on a day replaces the first.
    Delete is by id within the project, so False means "not on this
    project", and `day_of` reads the day it would delete, to judge it
    against an approved month."""

    async def list_by_project(
        self, project_id: str, start: date, end: date
    ) -> list[BalanceAdjustment]: ...
    async def upsert(self, adjustment: BalanceAdjustment) -> BalanceAdjustment: ...
    async def delete(self, project_id: str, adjustment_id: str) -> bool: ...
    async def day_of(self, project_id: str, adjustment_id: str) -> date | None: ...


class ContractAdjustments(Protocol):
    """What a contract write asks of the balance adjustments: whether one
    sits at or after a day — so moving the first day later past it is
    refused rather than silently dropping it from the balance — and the
    purge when the contract goes, since an adjustment only means something
    against the balance of the contract it was made on."""

    async def earliest(self, project_id: str, on_or_after: date) -> date | None: ...
    async def delete_by_project(self, project_id: str) -> int: ...


class WeekExpectationReader(Protocol):
    """What a reader that quotes a week's figure needs of the contract: the
    hours it expects of that week after holidays and absences, or None when
    it expects nothing by nature (`ContractService.expected_for_week`). The
    Inbox's readers — the planning line, the pacing card, the stale-project
    card — read this and nothing else of a contract, and so, through
    `CoachContractReader`, does the coach's pattern tool."""

    async def expected_for_week(self, project: Project, week_of: date) -> float | None: ...


class ContractWeeksReader(Protocol):
    """What the coach's day context reads of a contract: the current week of
    each day job among `projects`, by project id, the same figures the page shows
    — and nothing unless `as_of` is today in `tz` by the reader's own clock
    (`ContractService.current_weeks`)."""

    async def current_weeks(
        self, projects: Iterable[Project], tz: ZoneInfo, as_of: date
    ) -> dict[str, ContractWeek]: ...


class CoachContractReader(ContractWeeksReader, WeekExpectationReader, Protocol):
    """Both of what the coach reads of a contract: the current weeks for the
    day context, and each week's adjusted expectation for the pattern tool,
    whose pacing and stale-project cards quote it as the Inbox's do.
    `ContractService` is both."""


class BillingPresence(Protocol):
    """Whether a project is billed — all `ProjectService` asks of billing,
    so a kind change away from freelance is refused while it is, rather than
    leaving money dormant on a project that cannot read it."""

    async def exists(self, project_id: str) -> bool: ...


class BillableOverrideRemover(Protocol):
    """The one billing write a beat's own deletion makes: its override goes
    with it. True when there was one."""

    async def delete(self, beat_id: str) -> bool: ...


class BillingBeatReader(Protocol):
    """What billing reads of beats: those of some projects started in a span
    of instants, running ones included, and whether a beat is the caller's
    at all. Nothing that writes one."""

    async def list_started_between(
        self, project_ids: Iterable[str], start: datetime, end: datetime
    ) -> list[Beat]: ...
    async def exists(self, beat_id: str) -> bool: ...


class BillingProjectReader(ProjectReader, ProjectLister, Protocol):
    """One project by id, for a billing write's kind check, and the list, for
    a report: archived projects included, since an archived project's hours
    in a month are still billed."""


class ClientStore(Protocol):
    """Clients: one by id, the list, and the writes the client routes make.
    `get_by_id` raises `ClientNotFound` for one that is not the caller's, a
    malformed id included."""

    async def get_by_id(self, client_id: str) -> Client: ...
    # builtins.list because this class defines a method called `list`.
    async def list(self, archived: bool = False) -> builtins.list[Client]: ...
    async def list_all(self) -> builtins.list[Client]: ...
    async def create(self, client: Client) -> Client: ...
    async def update(self, client: Client) -> Client: ...
    async def delete(self, client_id: str) -> bool: ...
    async def restore(self, client: Client) -> None: ...


class ProjectBillingStore(Protocol):
    """Project billing, one per project: upsert is keyed on the project, so
    a second write replaces the first."""

    async def get(self, project_id: str) -> ProjectBilling | None: ...
    async def list_all(self) -> list[ProjectBilling]: ...
    async def list_by_client(self, client_id: str) -> list[ProjectBilling]: ...
    async def upsert(self, billing: ProjectBilling) -> ProjectBilling: ...
    async def delete(self, project_id: str) -> bool: ...


class BillingBudgetStore(Protocol):
    """Billing budgets, one per scope: upsert is keyed on the scope, so a
    second write replaces the first. `list_all` is a small set, at most one
    per client and billed project."""

    async def list_all(self) -> list[BillingBudget]: ...
    async def get(self, scope: BillingBudgetScope, scope_id: str) -> BillingBudget | None: ...
    async def upsert(self, budget: BillingBudget) -> BillingBudget: ...
    async def delete(self, scope: BillingBudgetScope, scope_id: str) -> bool: ...


class BillableOverrideStore(Protocol):
    """Billable overrides, one per beat: upsert is keyed on the beat."""

    async def list_all(self) -> list[BillableOverride]: ...
    async def list_for(self, beat_ids: Iterable[str]) -> list[BillableOverride]: ...
    async def upsert(self, override: BillableOverride) -> BillableOverride: ...
    async def delete(self, beat_id: str) -> bool: ...


class ReportLinkStore(Protocol):
    """Report links, the owner's side only: list, mint and revoke, each
    keyed on the client the link is for.

    Resolving a token is deliberately absent. That read crosses users — the
    reader has no session — so it lives on its own unscoped lookup in the
    infrastructure layer, and the route hands the resolved link's owner in.
    A service that mints links cannot use one.
    """

    async def list_for_client(self, client_id: str) -> list[ReportLink]: ...
    async def create(self, link: ReportLink) -> ReportLink: ...
    async def delete(self, client_id: str, link_id: str) -> bool: ...
    async def delete_for_client(self, client_id: str) -> int: ...


class UserDirectory(Protocol):
    """What the organisation service asks of accounts: one by id, to take
    the name and address a member joins under. Nothing is ever matched by
    email — an invitation to an address is accepted by the account signed
    in, whose address it must be."""

    async def get_by_id(self, user_id: str) -> User | None: ...


class OrganisationStamper(Protocol):
    """The two writes connecting a project makes to the member's own
    records, through their own user-scoped repositories: the beats and the
    absences from the day they chose become the organisation's record."""

    async def stamp_organisation(self, project_id: str, organisation_id: str, since) -> int: ...


class OrganisationBeatReader(Protocol):
    """A person's own finished beats stamped as one organisation's — the
    archive they keep after leaving."""

    async def list_for_organisation(self, organisation_id: str) -> list[Beat]: ...


class OrganisationAbsenceReader(Protocol):
    """A person's own absences stamped as one organisation's, for the same archive."""

    async def list_for_organisation(self, organisation_id: str) -> list[Absence]: ...


class OrganisationStore(Protocol):
    """Organisations, members, invites, join requests, projects, assignments
    and the audit log — every read and write `OrganisationService` makes,
    each scoped by organisation except the two that are a person's own
    (`memberships_of`) or a token's (`invite_by_token`)."""

    async def create_organisation(self, organisation: Organisation) -> Organisation: ...
    async def get_organisation(self, organisation_id: str) -> Organisation | None: ...
    async def get_organisations(self, ids: Iterable[str]) -> dict[str, Organisation]: ...
    async def update_organisation(self, organisation: Organisation) -> Organisation: ...
    async def membership(self, organisation_id: str, user_id: str) -> OrgMembership | None: ...
    async def memberships_of(self, user_id: str) -> list[OrgMembership]: ...
    async def list_members(
        self, organisation_id: str, *, active_only: bool = True
    ) -> list[OrgMembership]: ...
    async def count_owners(self, organisation_id: str) -> int: ...
    async def open_membership(self, membership: OrgMembership) -> OrgMembership: ...
    async def set_role(
        self, organisation_id: str, user_id: str, role: OrgRole
    ) -> OrgMembership | None: ...
    async def end_membership(
        self, organisation_id: str, user_id: str, reason: MembershipEnd, at: datetime
    ) -> OrgMembership | None: ...
    async def create_invite(self, invite: OrgInvite) -> OrgInvite: ...
    async def list_invites(self, organisation_id: str) -> list[OrgInvite]: ...
    async def invite_by_token(self, token: str) -> OrgInvite | None: ...
    async def invites_for_email(self, email: str) -> list[OrgInvite]: ...
    async def get_invite(self, organisation_id: str, invite_id: str) -> OrgInvite | None: ...
    async def mark_invite_accepted(self, invite_id: str, user_id: str, at: datetime) -> None: ...
    async def revoke_invite(self, organisation_id: str, invite_id: str, at: datetime) -> bool: ...
    async def create_request(self, request: OrgJoinRequest) -> OrgJoinRequest: ...
    async def pending_request(
        self, organisation_id: str, user_id: str
    ) -> OrgJoinRequest | None: ...
    async def list_requests(self, organisation_id: str) -> list[OrgJoinRequest]: ...
    async def decide_request(
        self,
        organisation_id: str,
        request_id: str,
        decision: JoinDecision,
        decided_by: str,
        at: datetime,
    ) -> OrgJoinRequest | None: ...
    async def create_project(self, organisation_id: str, fields: dict) -> OrgProject: ...
    async def list_projects(
        self, organisation_id: str, archived: bool | None = None
    ) -> list[OrgProject]: ...
    async def get_project(self, organisation_id: str, project_id: str) -> OrgProject | None: ...
    async def update_project(
        self, organisation_id: str, project_id: str, fields: dict
    ) -> OrgProject | None: ...
    async def personal_project(self, project_id: str, user_id: str) -> Project | None: ...
    async def hand_project_to_organisation(
        self, project_id: str, user_id: str, organisation_id: str
    ) -> bool: ...
    async def project_names(
        self, organisation_id: str, project_ids: Iterable[str]
    ) -> dict[str, OrgProject]: ...
    async def assignment(
        self, organisation_id: str, project_id: str, user_id: str
    ) -> OrgAssignment | None: ...
    async def list_assignments(
        self,
        organisation_id: str,
        *,
        project_id: str | None = None,
        user_id: str | None = None,
        active_only: bool = True,
    ) -> list[OrgAssignment]: ...
    async def open_assignment(
        self, assignment: OrgAssignment, *, keep_personal: bool, reopen: bool = True
    ) -> OrgAssignment: ...
    async def end_assignments(
        self, organisation_id: str, user_id: str, at: datetime, project_id: str | None = None
    ) -> int: ...
    async def repoint_project_rows(self, source_id: str, target_id: str) -> dict[str, int]: ...
    async def delete_assignments(self, organisation_id: str, project_id: str) -> int: ...
    async def delete_unapproved_timesheets(self, organisation_id: str, project_id: str) -> int: ...
    async def delete_project(self, organisation_id: str, project_id: str) -> bool: ...
    async def row_owner_ids(self, project_id: str) -> set[str]: ...
    async def hand_back_project(
        self, project: OrgProject, user_id: str, assignment: OrgAssignment | None, archived: bool
    ) -> str: ...
    async def repoint_member_rows(
        self, project_id: str, user_id: str, new_project_id: str
    ) -> dict[str, int]: ...
    async def delete_organisation_rows(
        self, organisation_id: str, project_ids: list[str]
    ) -> dict[str, int]: ...
    async def record(self, event: OrgAuditEvent) -> None: ...
    async def list_audit(
        self, organisation_id: str, *, before: datetime | None = None, limit: int = 100
    ) -> list[OrgAuditEvent]: ...
    async def create_team(self, team: OrgTeam) -> OrgTeam: ...
    async def list_teams(self, organisation_id: str) -> list[OrgTeam]: ...
    async def get_team(self, organisation_id: str, team_id: str) -> OrgTeam | None: ...
    async def update_team(self, organisation_id: str, team: OrgTeam) -> OrgTeam | None: ...
    async def delete_team(self, organisation_id: str, team_id: str) -> bool: ...
    async def manager_scope(self, organisation_id: str, user_id: str) -> set[str]: ...
    async def remove_from_teams(self, organisation_id: str, user_id: str) -> None: ...
    async def create_absence_request(self, request: OrgAbsenceRequest) -> OrgAbsenceRequest: ...
    async def get_absence_request(
        self, organisation_id: str, request_id: str
    ) -> OrgAbsenceRequest | None: ...
    async def list_absence_requests(
        self,
        organisation_id: str,
        *,
        user_id: str | None = None,
        pending_only: bool = False,
    ) -> list[OrgAbsenceRequest]: ...
    async def decide_absence_request(
        self,
        organisation_id: str,
        request_id: str,
        status: RequestStatus,
        decided_by: str,
        at: datetime,
        comment: str | None,
    ) -> OrgAbsenceRequest | None: ...
    async def withdraw_absence_request(
        self, organisation_id: str, request_id: str, user_id: str
    ) -> bool: ...
    async def upsert_timesheet(self, sheet: OrgTimesheet) -> OrgTimesheet: ...
    async def get_timesheet(self, organisation_id: str, sheet_id: str) -> OrgTimesheet | None: ...
    async def find_timesheet(
        self, project_id: str, user_id: str, month: date
    ) -> OrgTimesheet | None: ...
    async def list_timesheets(
        self,
        organisation_id: str,
        *,
        user_id: str | None = None,
        month: date | None = None,
        project_id: str | None = None,
    ) -> list[OrgTimesheet]: ...
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
        frozen: dict | None,
    ) -> OrgTimesheet | None: ...


class OrganisationRecords(Protocol):
    """The organisation's read of its working-time record: finished beats
    and absences by the organisation's own stamp over its project ids, and
    one member's adjustments for the balance. Nothing else is reachable
    through it, which is the point (docs/organisations.md, rule 3)."""

    async def beats_between(
        self,
        organisation_id: str,
        project_ids: Iterable[str],
        start: datetime,
        end: datetime,
        *,
        user_id: str | None = None,
    ) -> list[tuple[str, Beat]]: ...
    async def beats_of_member(
        self, organisation_id: str, project_id: str, user_id: str
    ) -> list[Beat]: ...
    async def has_unshared(self, organisation_id: str, project_id: str, user_id: str) -> bool: ...
    async def running_in(
        self, organisation_id: str, project_id: str, user_id: str, start: datetime, end: datetime
    ) -> bool: ...
    async def totals(
        self, organisation_id: str, project_ids: Iterable[str], *, user_id: str | None = None
    ) -> dict[tuple[str, str], MemberTotals]: ...
    async def absences_between(
        self,
        organisation_id: str,
        project_ids: Iterable[str],
        start: date,
        end: date,
        *,
        user_id: str | None = None,
    ) -> list[tuple[str, Absence]]: ...
    async def adjustments_of_member(
        self, project_id: str, user_id: str, start: date, end: date
    ) -> list[BalanceAdjustment]: ...


class PeriodLocks(Protocol):
    """Whether an approved timesheet month covers a day or an instant of the
    caller's, on a project (docs/organisations.md, stage 3). What the
    member-side services ask before a write that would move a frozen figure;
    returns the month, so the refusal can name it."""

    async def locked_day(self, project_id: str, day: date) -> date | None: ...
    async def locked_instant(self, project_id: str, instant: datetime) -> date | None: ...
