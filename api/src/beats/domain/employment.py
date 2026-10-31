"""Employment — stage 3 of organisations, and stage 4's scale pieces
(docs/organisations.md).

Stage 2 built the wall; this turns the day-job contract into something two
parties agree on. `EmploymentService` extends `OrganisationService` — same
membership resolution, same audit, same record reads — and adds:

- **Managed contracts.** The employer writes the contract on an assignment
  (`contract_managed`); the member reads their week and balance as ever,
  and their own writes to the contract, the absences and the balance
  adjustments answer 409 `CONTRACT_MANAGED`.
- **Absence requests.** On a managed assignment the member asks; a decider
  approves — which writes the absence, stamped — or declines with a comment.
- **Timesheets.** A member submits a month once it has ended; a decider
  approves, or asks for changes with a comment. Approval **freezes** the
  figures as they stood (`FrozenMonth`) — the first stored derived figure in
  the system — and from then on every write dated inside the month is
  refused (409 `PERIOD_APPROVED`), so the live arithmetic cannot silently
  leave the frozen number behind. Reopening needs a reason and is recorded;
  it lifts the lock and drops the frozen figures until re-approval.
- **Admin-entered time**, stamped and marked with who entered it, on the
  member's own timeline.
- **The compliance record**: per person, per day — first start, last end,
  breaks, total, and the warnings a working-time authority would raise
  (a day over 10 hours, rest under 11) — as CSV, derived on every read.
- **Teams and scope** (stage 4): a manager decides and reads for the
  members of the teams they are in; a viewer reads everything and changes
  nothing; both through the same reads the record already has.

Months are the organisation's own timezone's: the lock, the freeze and the
compliance day all bucket by it, so two deciders in two countries agree on
what "September" was.
"""

from datetime import date, datetime, timedelta
from typing import Any

from beats.domain.billing import utc_range
from beats.domain.contracts import absences_by_day, expected_on
from beats.domain.exceptions import (
    AbsenceRequestNotFound,
    MonthNotEnded,
    NotADayJob,
    NotAssigned,
    NotManaged,
    OrganisationRoleRequired,
    OutsideManagerScope,
    PeriodApproved,
    ProjectNotFound,
    RequestAlreadyDecided,
    TeamNotFound,
    TimesheetAlreadyApproved,
    TimesheetNotFound,
)
from beats.domain.holidays import contract_holidays
from beats.domain.models import (
    Absence,
    Beat,
    Contract,
    FrozenMonth,
    OrgAbsenceRequest,
    OrgAssignment,
    OrgAuditEvent,
    OrgRole,
    OrgTeam,
    OrgTimesheet,
    ProjectKind,
    RequestStatus,
    TimesheetEvent,
    TimesheetStatus,
)
from beats.domain.organisations import Member, OrganisationService
from beats.domain.ports import ContractAdjustments
from beats.domain.retention import effective_retention_years, retention_cutoff
from beats.domain.services import (
    _check_contract as check_contract_rules,
)
from beats.domain.services import (
    keep_unsent_contract_fields,
    reconcile_adjustments,
    worked_by_local_day,
)
from beats.domain.timesheet import month_end
from beats.domain.utils import local_date


def month_of(day: date) -> date:
    return day.replace(day=1)


def next_month(month: date) -> date:
    return (month.replace(day=28) + timedelta(days=7)).replace(day=1)


class EmploymentService(OrganisationService):
    """Stage 3 and 4 on top of the stage 2 service: same store, same record
    reads, same audit trail."""

    # --- who may act on whom -------------------------------------------------

    async def _decider(self, organisation_id: str, actor: str, target: str) -> Member:
        """The actor's membership, provided they decide for `target`: an
        owner or admin for anyone, a manager for the members of their teams.
        A viewer or member is 403 whoever the target is."""
        member = await self._member(organisation_id, actor)
        role = member.membership.role
        if not role.decides:
            raise OrganisationRoleRequired(OrgRole.MANAGER.value)
        if role is OrgRole.MANAGER:
            scope = await self.store.manager_scope(organisation_id, actor)
            if target not in scope:
                raise OutsideManagerScope()
        return member

    async def _reader_scope(self, organisation_id: str, actor: str) -> set[str] | None:
        """Who the actor may read in the record: None for everyone (owner,
        admin, viewer), a set for a manager, 403 for a member."""
        member = await self._member(organisation_id, actor)
        role = member.membership.role
        if not role.reads_record:
            raise OrganisationRoleRequired(OrgRole.VIEWER.value)
        if role is OrgRole.MANAGER:
            return await self.store.manager_scope(organisation_id, actor)
        return None

    async def _active_assignment(
        self, organisation_id: str, project_id: str, user_id: str
    ) -> OrgAssignment:
        if await self.store.get_project(organisation_id, project_id) is None:
            raise ProjectNotFound(project_id)
        assignment = await self.store.assignment(organisation_id, project_id, user_id)
        if assignment is None or not assignment.active:
            raise NotAssigned()
        return assignment

    # --- teams (stage 4) ------------------------------------------------------

    async def teams(self, organisation_id: str, actor: str) -> list[OrgTeam]:
        """The teams. Anyone who reads the record may see them — a manager
        has to be able to see their own scope."""
        member = await self._member(organisation_id, actor)
        if not member.membership.role.reads_record:
            raise OrganisationRoleRequired(OrgRole.VIEWER.value)
        return await self.store.list_teams(organisation_id)

    async def _team_members(self, organisation_id: str, member_ids: list[str]) -> list[str]:
        """The given ids, narrowed to active members, deduplicated in order."""
        active = {m.user_id for m in await self.store.list_members(organisation_id) if m.user_id}
        seen: set[str] = set()
        kept: list[str] = []
        for member_id in member_ids:
            if member_id in active and member_id not in seen:
                seen.add(member_id)
                kept.append(member_id)
        return kept

    async def create_team(
        self, organisation_id: str, actor: str, name: str, member_ids: list[str]
    ) -> OrgTeam:
        await self._member(organisation_id, actor, OrgRole.ADMIN)
        team = await self.store.create_team(
            OrgTeam(
                organisation_id=organisation_id,
                name=name,
                member_ids=await self._team_members(organisation_id, member_ids),
                created_at=self._now(),
            )
        )
        await self._audit(organisation_id, actor, "team.created", name=name, team_id=team.id)
        return team

    async def update_team(
        self, organisation_id: str, actor: str, team_id: str, name: str, member_ids: list[str]
    ) -> OrgTeam:
        await self._member(organisation_id, actor, OrgRole.ADMIN)
        existing = await self.store.get_team(organisation_id, team_id)
        if existing is None:
            raise TeamNotFound()
        updated = await self.store.update_team(
            organisation_id,
            existing.model_copy(
                update={
                    "name": name,
                    "member_ids": await self._team_members(organisation_id, member_ids),
                }
            ),
        )
        if updated is None:
            raise TeamNotFound()
        await self._audit(organisation_id, actor, "team.updated", name=name, team_id=team_id)
        return updated

    async def delete_team(self, organisation_id: str, actor: str, team_id: str) -> None:
        await self._member(organisation_id, actor, OrgRole.ADMIN)
        if not await self.store.delete_team(organisation_id, team_id):
            raise TeamNotFound()
        await self._audit(organisation_id, actor, "team.deleted", team_id=team_id)

    # --- managed contracts (stage 3) -----------------------------------------------

    async def read_contract(
        self, organisation_id: str, actor: str, project_id: str, user_id: str
    ) -> OrgAssignment:
        """The assignment with its contract, for the decider editing it."""
        await self._decider(organisation_id, actor, user_id)
        return await self._active_assignment(organisation_id, project_id, user_id)

    async def set_contract(
        self,
        organisation_id: str,
        actor: str,
        project_id: str,
        user_id: str,
        contract: Contract | None,
        managed: bool,
        adjustments: ContractAdjustments,
    ) -> OrgAssignment:
        """Write the employer's contract on an assignment, or hand it back.

        With `managed`, the terms are the employer's from here: the member's
        own contract, absence and adjustment writes on the project answer
        409 CONTRACT_MANAGED, and absences go through requests. The contract
        replaces what the assignment had — taking one under management starts
        from the terms the member recorded, so nothing is rewritten silently
        (the roadmap's "contract disagreement": the employer's terms arrive
        as an audited act, never as a surprise recomputation). A holiday
        list or vacation entitlement the body leaves out is kept, as on the
        member's own route. With `managed` false the contract stays as sent
        (or as it was, when None) and the member resumes writing it.

        Decision 21: one set of rules validates a contract whoever writes
        it. Both of the ones this used to skip are here (#412) — only a day
        job carries a contract, and a first day moved later past a balance
        adjustment is refused rather than dropping it from the balance.
        """
        await self._decider(organisation_id, actor, user_id)
        assignment = await self._active_assignment(organisation_id, project_id, user_id)
        project = await self.store.get_project(organisation_id, project_id)
        if project is None:
            raise ProjectNotFound(project_id)
        if project.kind is not ProjectKind.DAY_JOB:
            # `check_contract_rules_for` validates through a shell day job,
            # so without this the employer could put a contract on a
            # freelance or side project the member's own route refuses.
            raise NotADayJob()
        if contract is not None:
            contract = keep_unsent_contract_fields(contract, assignment.contract)
            check_contract_rules_for(contract)
        written_contract = contract if contract is not None else assignment.contract
        purge_after = await reconcile_adjustments(
            adjustments, project_id, assignment.contract, written_contract
        )
        updated = assignment.model_copy(
            update={"contract": written_contract, "contract_managed": managed}
        )
        saved = await self.store.open_assignment(updated, keep_personal=False)
        if purge_after:
            await adjustments.delete_by_project(project_id)
        written = contract or assignment.contract
        await self._audit(
            organisation_id,
            actor,
            "contract.managed" if managed else "contract.released",
            project_id=project_id,
            subject_user_id=user_id,
            terms=len(written.terms) if written is not None else 0,
        )
        return saved

    async def enter_adjustment(
        self,
        organisation_id: str,
        actor: str,
        project_id: str,
        user_id: str,
        adjustments,  # AdjustmentStore bound to the target, built by the router
        adjustment,
    ):
        """A balance adjustment on a managed assignment — a payout, a reset —
        is the employer's act (the member's own route answers 409 there).
        The same date rule as the member's route: the contract's first day
        through today, here today in the organisation's zone."""
        member = await self._decider(organisation_id, actor, user_id)
        assignment = await self._active_assignment(organisation_id, project_id, user_id)
        if not assignment.contract_managed or assignment.contract is None:
            raise NotManaged()
        today = local_date(self._now(), self._zone(member.organisation))  # the organisation's today
        if not assignment.contract.starts_on <= adjustment.date <= today:
            from beats.domain.exceptions import AdjustmentOutsideBalance

            raise AdjustmentOutsideBalance()
        await self._refuse_locked_day(project_id, user_id, adjustment.date, member)
        saved = await adjustments.upsert(adjustment)
        await self._audit(
            organisation_id,
            actor,
            "adjustment.entered",
            project_id=project_id,
            subject_user_id=user_id,
            date=adjustment.date.isoformat(),
            kind=adjustment.kind.value,
            hours=adjustment.hours,
        )
        return saved

    # --- admin-entered time (stage 3) -----------------------------------------------

    async def enter_time(
        self,
        organisation_id: str,
        actor: str,
        project_id: str,
        user_id: str,
        beats,  # a BeatStore bound to the target, built by the router
        start: datetime,
        end: datetime,
        note: str | None,
    ) -> Beat:
        """Enter a finished session for a member — a forgotten day, a
        correction the member asked for aloud. The beat is the member's own
        document on their own timeline, stamped as the organisation's record
        and marked with who entered it, and the act is audited. Refused
        inside an approved month."""
        member = await self._decider(organisation_id, actor, user_id)
        await self._active_assignment(organisation_id, project_id, user_id)
        if end <= start:
            from beats.domain.exceptions import InvalidEndTime

            raise InvalidEndTime()
        await self._refuse_locked_instant(project_id, user_id, start, member)
        beat = await beats.create(
            Beat(
                project_id=project_id,
                start=start,
                end=end,
                note=note,
                entered_by=actor,
                organisation_id=organisation_id,
            )
        )
        await self._audit(
            organisation_id,
            actor,
            "time.entered",
            project_id=project_id,
            subject_user_id=user_id,
            start=start.isoformat(),
            end=end.isoformat(),
        )
        return beat

    # --- absence requests (stage 3) ---------------------------------------------------

    async def request_absence(
        self,
        organisation_id: str,
        user_id: str,
        project_id: str,
        day: date,
        type_,
        half_day: bool,
        note: str | None,
    ) -> OrgAbsenceRequest:
        """Ask for a day off on a managed assignment. On an unmanaged one the
        member books it directly, as before (409 NOT_MANAGED here)."""
        member = await self._member(organisation_id, user_id)
        assignment = await self._active_assignment(organisation_id, project_id, user_id)
        if not assignment.contract_managed:
            raise NotManaged()
        await self._refuse_locked_day(project_id, user_id, day, member)
        request = await self.store.create_absence_request(
            OrgAbsenceRequest(
                organisation_id=organisation_id,
                project_id=project_id,
                user_id=user_id,
                date=day,
                type=type_,
                half_day=half_day,
                note=note,
                requested_at=self._now(),
            )
        )
        await self._audit(
            organisation_id,
            user_id,
            "absence.requested",
            project_id=project_id,
            subject_user_id=user_id,
            date=day.isoformat(),
        )
        return request

    async def absence_requests(
        self, organisation_id: str, actor: str, *, pending_only: bool
    ) -> list[OrgAbsenceRequest]:
        """A member's own requests; for a decider, everyone in their scope."""
        member = await self._member(organisation_id, actor)
        role = member.membership.role
        if not role.decides:
            return await self.store.list_absence_requests(
                organisation_id, user_id=actor, pending_only=pending_only
            )
        requests = await self.store.list_absence_requests(
            organisation_id, pending_only=pending_only
        )
        if role is OrgRole.MANAGER:
            scope = await self.store.manager_scope(organisation_id, actor)
            requests = [r for r in requests if r.user_id in scope]
        return requests

    async def decide_absence(
        self,
        organisation_id: str,
        actor: str,
        request_id: str,
        absences_for,  # user id -> AbsenceStore, built by the router
        *,
        approve: bool,
        comment: str | None,
    ) -> OrgAbsenceRequest:
        """Approve — which books the absence, stamped, through the asker's
        own repository — or decline. Two deciders racing: the store decides
        a pending request once."""
        request = await self.store.get_absence_request(organisation_id, request_id)
        if request is None:
            raise AbsenceRequestNotFound()
        member = await self._decider(organisation_id, actor, request.user_id)
        if request.status is not RequestStatus.PENDING:
            raise RequestAlreadyDecided()
        if approve:
            await self._refuse_locked_day(request.project_id, request.user_id, request.date, member)
        decided = await self.store.decide_absence_request(
            organisation_id,
            request_id,
            RequestStatus.APPROVED if approve else RequestStatus.DECLINED,
            actor,
            self._now(),
            comment,
        )
        if decided is None:
            raise RequestAlreadyDecided()
        if approve:
            await absences_for(request.user_id).upsert(
                Absence(
                    project_id=request.project_id,
                    date=request.date,
                    type=request.type,
                    half_day=request.half_day,
                    note=request.note,
                    organisation_id=organisation_id,
                )
            )
        await self._audit(
            organisation_id,
            actor,
            "absence.approved" if approve else "absence.declined",
            project_id=request.project_id,
            subject_user_id=request.user_id,
            date=request.date.isoformat(),
        )
        return decided

    async def withdraw_absence(self, organisation_id: str, user_id: str, request_id: str) -> None:
        """Take back a request nobody has decided. Audited like every other
        step of a request: a decider who saw it waiting and then does not
        should be able to find out where it went."""
        await self._member(organisation_id, user_id)
        if not await self.store.withdraw_absence_request(organisation_id, request_id, user_id):
            raise AbsenceRequestNotFound()
        await self._audit(organisation_id, user_id, "absence.withdrawn", subject_user_id=user_id)

    # --- timesheets (stage 3) ---------------------------------------------------------

    async def submit_timesheet(
        self, organisation_id: str, user_id: str, project_id: str, month: date
    ) -> OrgTimesheet:
        """Submit a month, once it has ended in the organisation's zone. A
        sheet sent back or reopened is resubmitted the same way; an approved
        one is refused until reopened."""
        member = await self._member(organisation_id, user_id)
        await self._active_assignment(organisation_id, project_id, user_id)
        month = month_of(month)
        today = local_date(self._now(), self._zone(member.organisation))
        if next_month(month) > today:
            raise MonthNotEnded()
        existing = await self.store.find_timesheet(project_id, user_id, month)
        if existing is not None and existing.status is TimesheetStatus.APPROVED:
            raise TimesheetAlreadyApproved()
        now = self._now()
        sheet = await self.store.upsert_timesheet(
            OrgTimesheet(
                organisation_id=organisation_id,
                project_id=project_id,
                user_id=user_id,
                month=month,
                status=TimesheetStatus.SUBMITTED,
                submitted_at=now,
                decided_at=None,
                decided_by=None,
                comment=None,
                frozen=None,
                history=[TimesheetEvent(at=now, by=user_id, action=TimesheetStatus.SUBMITTED)],
            )
        )
        await self._audit(
            organisation_id,
            user_id,
            "timesheet.submitted",
            project_id=project_id,
            subject_user_id=user_id,
            month=month.isoformat(),
        )
        return sheet

    async def timesheets(
        self, organisation_id: str, actor: str, *, month: date | None
    ) -> list[OrgTimesheet]:
        member = await self._member(organisation_id, actor)
        role = member.membership.role
        if not (role.decides or role is OrgRole.VIEWER):
            return await self.store.list_timesheets(organisation_id, user_id=actor, month=month)
        sheets = await self.store.list_timesheets(organisation_id, month=month)
        if role is OrgRole.MANAGER:
            scope = await self.store.manager_scope(organisation_id, actor)
            sheets = [s for s in sheets if s.user_id in scope]
        return sheets

    async def decide_timesheet(
        self,
        organisation_id: str,
        actor: str,
        sheet_id: str,
        *,
        approve: bool,
        comment: str | None,
    ) -> OrgTimesheet:
        """Approve, freezing the month's figures as they stand, or send it
        back with a comment. Approval is refused while a stamped timer still
        runs inside the month — its hours are in no figure yet, and freezing
        around it would guarantee a drift."""
        sheet = await self.store.get_timesheet(organisation_id, sheet_id)
        if sheet is None:
            raise TimesheetNotFound()
        member = await self._decider(organisation_id, actor, sheet.user_id)
        if sheet.status is TimesheetStatus.APPROVED:
            raise TimesheetAlreadyApproved()
        frozen: dict[str, Any] | None = None
        if approve:
            frozen = (await self._freeze(member, sheet)).model_dump(mode="json")
        decided = await self.store.set_timesheet_state(
            organisation_id,
            sheet_id,
            status=TimesheetStatus.APPROVED if approve else TimesheetStatus.CHANGES_REQUESTED,
            only_from=(
                TimesheetStatus.SUBMITTED,
                TimesheetStatus.CHANGES_REQUESTED,
                TimesheetStatus.REOPENED,
            ),
            decided_by=actor,
            at=self._now(),
            comment=comment,
            frozen=frozen,
        )
        if decided is None:
            raise TimesheetAlreadyApproved()
        await self._audit(
            organisation_id,
            actor,
            "timesheet.approved" if approve else "timesheet.changes_requested",
            project_id=sheet.project_id,
            subject_user_id=sheet.user_id,
            month=sheet.month.isoformat(),
        )
        return decided

    async def reopen_timesheet(
        self, organisation_id: str, actor: str, sheet_id: str, reason: str
    ) -> OrgTimesheet:
        """Lift an approved month's lock, with a reason, recorded. The frozen
        figures go with it; re-approval freezes afresh."""
        sheet = await self.store.get_timesheet(organisation_id, sheet_id)
        if sheet is None:
            raise TimesheetNotFound()
        await self._decider(organisation_id, actor, sheet.user_id)
        reopened = await self.store.set_timesheet_state(
            organisation_id,
            sheet_id,
            status=TimesheetStatus.REOPENED,
            only_from=(TimesheetStatus.APPROVED,),
            decided_by=actor,
            at=self._now(),
            comment=reason,
            frozen=None,
        )
        if reopened is None:
            raise TimesheetNotFound()
        await self._audit(
            organisation_id,
            actor,
            "timesheet.reopened",
            project_id=sheet.project_id,
            subject_user_id=sheet.user_id,
            month=sheet.month.isoformat(),
            reason=reason,
        )
        return reopened

    async def _freeze(self, member: Member, sheet: OrgTimesheet) -> FrozenMonth:
        """The month's figures as approval sees them, from the organisation's
        own record reads: the stamped finished entries, the stamped
        absences, and — when the assignment carries a contract — the
        expectation over the month and the balance at its close. The balance
        follows decision 16: withheld (None) while any entry or absence on
        the project is not the organisation's."""
        tz = self._zone(member.organisation)
        organisation_id = member.organisation.id or ""
        first, last = sheet.month, month_end(sheet.month)
        start, end = utc_range(first, last, tz)
        if await self.records.running_in(
            organisation_id, sheet.project_id, sheet.user_id, start, end
        ):
            raise PeriodApproved(sheet.month)
        beats = [
            beat
            for _, beat in await self.records.beats_between(
                organisation_id, [sheet.project_id], start, end, user_id=sheet.user_id
            )
        ]
        absences = [
            a
            for _, a in await self.records.absences_between(
                organisation_id, [sheet.project_id], first, last, user_id=sheet.user_id
            )
        ]
        worked_map = worked_by_local_day(beats, tz)
        worked = round(sum(worked_map.values()), 2)
        assignment = await self.store.assignment(organisation_id, sheet.project_id, sheet.user_id)
        expected: float | None = None
        balance_end: float | None = None
        contract = assignment.contract if assignment else None
        if contract is not None:
            holidays = contract_holidays(contract, first, last)
            by_day = absences_by_day(absences)
            total = 0.0
            day = first
            while day <= last:
                total += expected_on(contract, day, set(holidays), by_day)
                day += timedelta(days=1)
            expected = round(total, 2)
            if assignment is not None:
                expired_before = retention_cutoff(
                    self._today(member.organisation),
                    effective_retention_years(
                        member.organisation.retention_years,
                        member.organisation.holiday_country,
                    ),
                )
                balance = await self._balance(organisation_id, assignment, last, tz, expired_before)
                balance_end = balance.balance if balance else None
        return FrozenMonth(
            worked=worked,
            expected=expected,
            balance_end=balance_end,
            entries=len(beats),
            absence_days=sum(0.5 if a.half_day else 1.0 for a in absences),
        )

    # --- locks -------------------------------------------------------------------

    async def _refuse_locked_day(
        self, project_id: str, user_id: str, day: date, member: Member
    ) -> None:
        month = month_of(day)
        sheet = await self.store.find_timesheet(project_id, user_id, month)
        if sheet is not None and sheet.status is TimesheetStatus.APPROVED:
            raise PeriodApproved(month)

    async def _refuse_locked_instant(
        self, project_id: str, user_id: str, instant: datetime, member: Member
    ) -> None:
        day = local_date(instant, self._zone(member.organisation))
        await self._refuse_locked_day(project_id, user_id, day, member)

    # --- the audit log, read (stage 4) ----------------------------------------------

    async def audit_log(
        self, organisation_id: str, actor: str, *, before: datetime | None, limit: int
    ) -> list[OrgAuditEvent]:
        await self._member(organisation_id, actor, OrgRole.ADMIN)
        return await self.store.list_audit(organisation_id, before=before, limit=limit)

    # --- the record, scoped (stage 4) -------------------------------------------------

    async def scoped_record(self, organisation_id: str, actor: str, month: date):
        """The record for whoever reads it: whole for an owner, admin or
        viewer, a manager's narrowed to the members of their teams. The
        narrowing drops rows after the one read the record already makes —
        the reader is the organisation's own staff, and what is dropped is
        other members' slices of the same record, not anything outside it.

        The month is the organisation's own timezone's, not the caller's:
        two deciders must not download two different legal records."""
        scope = await self._reader_scope(organisation_id, actor)
        organisation = await self.store.get_organisation(organisation_id)
        if organisation is None:
            from beats.domain.exceptions import OrganisationNotFound

            raise OrganisationNotFound()
        projects = await self.store.list_projects(organisation_id)
        record = await self._record(organisation, projects, month, user_id=None)
        if scope is None:
            return record
        return record._replace(
            projects=[
                p._replace(members=[m for m in p.members if m.user_id in scope])
                for p in record.projects
            ]
        )


def check_contract_rules_for(contract: Contract) -> None:
    """The member's own contract checks, on the employer's write: a region
    the calendar knows, a vacation opening inside the contract's dates."""
    from beats.domain.holidays import check_region
    from beats.domain.models import Project, ProjectKind

    # Reuse the project write's checks through a shell project: the rules are
    # the contract's own, not the shell's.
    check_contract_rules(Project(name="-", kind=ProjectKind.DAY_JOB, contract=contract))
    if contract.holiday_country is not None:
        check_region(contract.holiday_country, contract.holiday_subdivision)


def record_csv(record) -> str:
    """The month's record as RFC 4180 CSV, a row per entry: project, member,
    day, start, end, hours, note — the report an accountant files."""
    import csv
    import io

    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["project", "member", "day", "start", "end", "hours", "note"])
    for project in record.projects:
        for member in project.members:
            for e in member.entries:
                writer.writerow(
                    [
                        project.project.name,
                        member.name,
                        e.day.isoformat(),
                        e.start.isoformat(),
                        e.end.isoformat(),
                        f"{e.hours:.2f}",
                        e.note or "",
                    ]
                )
    return out.getvalue()


# The compliance warnings' thresholds (docs/organisations.md, decision 26).
# The 11 hours' rest between working days is Directive 2003/88/EC art. 3,
# EU-wide; the 10-hour daily ceiling is Germany's §3 ArbZG, the strictest
# concrete one among the markets this sells to — and still current law: the
# June 2026 reform draft keeps the daily ceiling and moves to a weekly
# maximum only where a collective agreement says so. A warning is a line of
# text derived on every read, never a stored flag: an edit that repairs the
# day repairs the record.
MAX_DAILY_HOURS = 10.0
MIN_REST_HOURS = 11.0

_EPSILON = 1e-9  # exactly 10 h worked, or exactly 11 h rest, is within the law


def compliance_warnings(record) -> dict[tuple[str, date], list[str]]:
    """Per member and day, what a working-time authority would flag.

    The law binds the employer per person, not per project: a day split
    over two projects is one working day, and the night between two
    projects' entries is one rest period. So totals and rests are taken
    over every entry the organisation holds for the member, and the same
    warnings attach to each of that day's rows. Rest is judged against the
    nearest earlier day with entries in the month read — the first such day
    gets no rest warning, since what came before the rows is not in them.
    """
    from collections import defaultdict

    by_member: dict[str, dict[date, list]] = defaultdict(lambda: defaultdict(list))
    for project in record.projects:
        for member in project.members:
            for e in member.entries:
                by_member[member.user_id][e.day].append(e)

    warnings: dict[tuple[str, date], list[str]] = {}
    for user_id, days in by_member.items():
        previous_end: datetime | None = None
        previous_day: date | None = None
        for day in sorted(days):
            entries = sorted(days[day], key=lambda e: e.start)
            found: list[str] = []
            total = sum(e.hours for e in entries)
            if total > MAX_DAILY_HOURS + _EPSILON:
                found.append(f"day over {MAX_DAILY_HOURS:g} h ({total:.2f} h)")
            if previous_end is not None:
                rest = (entries[0].start - previous_end).total_seconds() / 3600
                if rest < MIN_REST_HOURS - _EPSILON:
                    found.append(
                        f"rest under {MIN_REST_HOURS:g} h ({rest:.2f} h after {previous_day})"
                    )
            if found:
                warnings[(user_id, day)] = found
            last_end = max(e.end for e in entries)
            previous_end = last_end if previous_end is None else max(previous_end, last_end)
            previous_day = day
    return warnings


def compliance_csv(record) -> str:
    """The compliance record as RFC 4180 CSV (docs/organisations.md, stage
    3): per member, per project, per day — first start, last end, the breaks
    between entries, the total, and the warnings a working-time authority
    would raise (`compliance_warnings`), derived from the same rows."""
    import csv
    import io
    from collections import defaultdict

    warnings = compliance_warnings(record)
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(
        [
            "member",
            "project",
            "day",
            "first_start",
            "last_end",
            "break_minutes",
            "worked_hours",
            "warnings",
        ]
    )
    for project in record.projects:
        for member in project.members:
            by_day: dict[date, list] = defaultdict(list)
            for e in member.entries:
                by_day[e.day].append(e)
            for day in sorted(by_day):
                entries = sorted(by_day[day], key=lambda e: e.start)
                breaks = sum(
                    max(
                        0.0,
                        (entries[i + 1].start - entries[i].end).total_seconds() / 60,
                    )
                    for i in range(len(entries) - 1)
                )
                writer.writerow(
                    [
                        member.name,
                        project.project.name,
                        day.isoformat(),
                        entries[0].start.isoformat(),
                        entries[-1].end.isoformat(),
                        f"{breaks:.0f}",
                        f"{sum(e.hours for e in entries):.2f}",
                        "; ".join(warnings.get((member.user_id, day), [])),
                    ]
                )
    return out.getvalue()
