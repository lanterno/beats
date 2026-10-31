"""Domain services - business logic that coordinates multiple entities."""

import logging
from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from beats.domain.contracts import (
    absences_by_day,
    balance_terms,
    counts_worked,
    expected_on,
    owes,
    round_hours,
    term_on,
    week_expectation,
    within_contract,
)
from beats.domain.exceptions import (
    AbsenceNotFound,
    AdjustmentBeforeStart,
    AdjustmentNotFound,
    AdjustmentOutsideBalance,
    BeatChanged,
    BeatNotFound,
    ContractManaged,
    DomainException,
    InvalidEndTime,
    MonthOutsideContract,
    NoActiveTimer,
    NoContract,
    NoObjectMatched,
    NotADayJob,
    NoVacationEntitlement,
    OrganisationProject,
    PeriodApproved,
    ProjectHasBilling,
    ProjectNotFound,
    TimerAlreadyRunning,
    TimerChanged,
    UnknownHolidayRegion,
    VacationOpeningOutsideContract,
    VacationYearOutOfRange,
)
from beats.domain.holidays import (
    Holiday,
    check_region,
    contract_calendar,
    contract_holidays,
)
from beats.domain.ledger import assemble_ledger
from beats.domain.models import (
    ORGANISATION_FIELDS,
    Absence,
    AbsenceType,
    BalanceAdjustment,
    Beat,
    Contract,
    ContractDay,
    ContractWeek,
    DayAbsence,
    ExpectedBeat,
    Ledger,
    Project,
    ProjectKind,
    VacationYear,
)
from beats.domain.ports import (
    AbsenceStore,
    AdjustmentStore,
    BeatStore,
    BillableOverrideRemover,
    BillingPresence,
    ContractAdjustments,
    FlowWindowReader,
    PeriodLocks,
    ProjectBeatReader,
    ProjectReader,
    ProjectStore,
    TimerBeatStore,
    TimerProjectReader,
)
from beats.domain.timesheet import (
    COMPANY_HOLIDAY,
    Timesheet,
    assemble_timesheet,
    timesheet_range,
)
from beats.domain.utils import local_date, normalize_tz
from beats.domain.vacation import vacation_year

logger = logging.getLogger(__name__)

# Cap on auto-derived tags per session — enough to capture the repos + languages
# a focused session touches without turning the tag cloud into noise.
_MAX_FLOW_TAGS = 6


async def derive_flow_tags(
    flow_repo: FlowWindowReader, start: datetime, end: datetime | None
) -> list[str]:
    """Derive session tags from the ambient daemon's flow-window signals.

    Replaces manual tagging (the app takes no free-text input): tags are the
    distinct repos and editor languages the daemon observed while the session
    ran, over [start, end]. Repos come first (more specific), then languages.
    Best-effort — returns [] when the session has no end yet or no windows
    overlap (e.g. the daemon wasn't running).
    """
    if end is None:
        return []
    windows = await flow_repo.list_by_range(start, end)
    repos = [w.editor_repo.rstrip("/").split("/")[-1] for w in windows if w.editor_repo]
    langs = [w.editor_language.strip().lower() for w in windows if w.editor_language]
    seen: set[str] = set()
    tags: list[str] = []
    for tag in (*repos, *langs):
        if tag and tag not in seen:
            seen.add(tag)
            tags.append(tag)
    return tags[:_MAX_FLOW_TAGS]


def stamp_for(project: Project, start: datetime) -> str | None:
    """The organisation whose record a beat on `project` started at `start`
    is, or None. A project the member connected stamps only from the
    instant they chose to share it (rule 4, docs/organisations.md decision
    7): a beat before that — created back-dated, edited, or moved there —
    stays the member's own, and an edit that moves a stamped beat before it
    clears the stamp. A project the organisation assigned has no such
    boundary (`shared_from_day` is None): nothing of the member's on it
    predates the organisation, and a back-dated entry is work for it."""
    org = project.organisation
    if org is None:
        return None
    if org.shared_from_day is not None and normalize_tz(start) < normalize_tz(org.shared_from):
        return None
    return org.id


def stamp_for_day(project: Project, day: date) -> str | None:
    """`stamp_for` for a row that is dated rather than timed: an absence on
    the day the member chose to share from is the organisation's, one the
    day before is not."""
    org = project.organisation
    if org is None:
        return None
    if org.shared_from_day is not None and day < org.shared_from_day:
        return None
    return org.id


def _refuse_managed(project: Project) -> None:
    """The member's write to a contract the employer manages (stage 3): the
    contract, the absences and the adjustments are the organisation's to
    change, and an absence is asked for through a request."""
    if project.organisation is not None and project.organisation.contract_managed:
        raise ContractManaged()


async def refuse_locked(
    locks: PeriodLocks | None, project: Project, instant: datetime | None, day: date | None = None
) -> None:
    """Refuse a write dated inside an approved timesheet month on an
    organisation's project (docs/organisations.md, stage 3). Personal
    projects, and services built without the locks (the tests' bare fakes),
    pass through."""
    if locks is None or project.organisation is None:
        return
    if project.id is None:
        return
    month = None
    if instant is not None:
        month = await locks.locked_instant(project.id, instant)
    if month is None and day is not None:
        month = await locks.locked_day(project.id, day)
    if month is not None:
        raise PeriodApproved(month)


def check_organisation_fields(existing: Project, project: Project) -> None:
    """What a member's write to an organisation's project must leave alone:
    every field in `ORGANISATION_FIELDS`, which only the organisation's admins
    write, through its own routes. The member keeps the personal fields —
    goal, overrides, local repo paths, and until stage 3 the contract — so a
    contract or goal edit passes, and a rename, a recolour, a kind change or
    an archive is a 409 (ORGANISATION_PROJECT) naming the field."""
    if existing.organisation is None:
        return
    for field in sorted(ORGANISATION_FIELDS):
        if getattr(existing, field) != getattr(project, field):
            raise OrganisationProject(
                f"{existing.organisation.name} owns this project's {field.replace('_', ' ')}"
            )


class TimerService:
    """Service for managing timer operations.

    Handles the business logic for starting and stopping timers,
    including validation that only one timer can run at a time.
    """

    def __init__(
        self,
        beat_repo: TimerBeatStore,
        project_repo: TimerProjectReader,
        flow_repo: FlowWindowReader | None = None,
        locks: PeriodLocks | None = None,
    ):
        self.beat_repo = beat_repo
        self.project_repo = project_repo
        self.flow_repo = flow_repo
        # Stage 3: a timer started with a back-dated time must not land in an
        # approved month (`refuse_locked`). Stopping is never checked — the
        # approval itself refuses to freeze around a running timer.
        self.locks = locks

    async def start_timer(self, project_id: str, start_time: datetime | None = None) -> Beat:
        """Start a new timer for a project.

        Args:
            project_id: The ID of the project to track time against.
            start_time: When the timer started. Defaults to now.

        Returns:
            The created Beat with an active timer.

        Raises:
            ProjectNotFound: If the project doesn't exist.
            TimerAlreadyRunning: If another timer is already active.
        """
        # Validate project exists — one the caller holds, their own or an
        # organisation's they are assigned to; an assignment that has ended
        # makes the project not found, which is how leaving stops tracking.
        project = await self.project_repo.get_by_id(project_id)

        # Check no active timer
        active = await self.beat_repo.get_active()
        if active:
            active_project = await self.project_repo.get_by_id(active.project_id)
            raise TimerAlreadyRunning(
                project_name=active_project.name,
                beat=active.model_dump(mode="json"),
            )

        # Create new beat, stamped as the organisation's record when the
        # project is an organisation's (docs/organisations.md).
        start = start_time or datetime.now(UTC)
        await refuse_locked(self.locks, project, start)
        beat = Beat(project_id=project_id, start=start, organisation_id=stamp_for(project, start))
        return await self.beat_repo.create(beat)

    async def stop_timer(
        self, end_time: datetime | None = None, expected: ExpectedBeat | None = None
    ) -> Beat:
        """Stop the currently running timer.

        Args:
            end_time: When the timer stopped. Defaults to now.
            expected: The running session the stop was made against, when the
                caller names it (an offline client replaying a queued stop).

        Returns:
            The updated Beat with end time set.

        Raises:
            NoActiveTimer: If no timer is currently running.
            TimerChanged: If `expected` is given and another session is running.
            InvalidEndTime: If end_time is before the start time.
        """
        active = await self.beat_repo.get_active()
        if not active:
            raise NoActiveTimer()
        if expected is not None and not expected.matches(active):
            raise TimerChanged()

        end = end_time or datetime.now(UTC)

        # Validate end time is after start
        start = normalize_tz(active.start)
        end_normalized = normalize_tz(end)
        if end_normalized < start:
            raise InvalidEndTime()

        # Only the end and the tags are written: the beat was read before the
        # flow-window await, and anything written to it meanwhile (a start
        # moved earlier, a note imported) must not be reverted to that read.
        active.end = end
        written = {"end"}
        if self.flow_repo is not None:
            active.tags = await derive_flow_tags(self.flow_repo, active.start, end)
            written.add("tags")
        return await self.beat_repo.update(active, written)

    async def get_status(self) -> dict:
        """Get the current timer status.

        Returns:
            Dict with timer status including whether a timer is running,
            the project, duration, etc.
        """
        try:
            active = await self.beat_repo.get_active()
            if active:
                project = await self.project_repo.get_by_id(active.project_id)
                return {
                    "isBeating": True,
                    "project": project.model_dump(),
                    "since": active.start.isoformat(),
                    "so_far": str(active.duration),
                }
        except NoObjectMatched, ProjectNotFound:
            pass

        # No active timer - try to get last beat info
        try:
            last_beat = await self.beat_repo.get_last()
            return {
                "isBeating": False,
                "last_beat": {
                    "id": last_beat.id,
                    "project_id": last_beat.project_id,
                    "end": last_beat.end.isoformat() if last_beat.end else None,
                },
            }
        except NoObjectMatched:
            return {"isBeating": False}


class BeatService:
    """Service for managing beat CRUD operations."""

    def __init__(
        self,
        beat_repo: BeatStore,
        overrides: BillableOverrideRemover,
        flow_repo: FlowWindowReader | None = None,
        projects: ProjectReader | None = None,
        locks: PeriodLocks | None = None,
    ):
        self.beat_repo = beat_repo
        self.overrides = overrides
        self.flow_repo = flow_repo
        # Stage 3: a create, edit or delete dated inside an approved
        # timesheet month on an organisation's project is refused.
        self.locks = locks
        # For the organisation stamp: a beat written against an
        # organisation's project is that organisation's record, and one
        # moved to a personal project is nobody's but the member's. Given
        # a reader, a beat on a project the caller does not hold is a 404,
        # as the timer's is; without one (the tests' bare service) the beat
        # is written as sent.
        self.projects = projects

    async def _stamped(self, beat: Beat) -> Beat:
        if self.projects is None:
            return beat
        project = await self.projects.get_by_id(beat.project_id)
        beat.organisation_id = stamp_for(project, beat.start)
        await refuse_locked(self.locks, project, beat.start)
        return beat

    async def _refuse_second_timer(self, beat: Beat) -> None:
        """One session open at a time, on the CRUD routes as on the timer.

        `start_timer` has always checked (TimerAlreadyRunning), but a beat
        written with no `end` is a running session too, whichever door it came
        through: a create that omits `end`, or an edit that reopens a finished
        session by clearing it. Without this check two timers run at once, and
        `get_active` then answers with whichever of them storage returns
        first.

        The open session the edit is itself editing is not a second one.
        """
        if beat.end is not None:
            return
        active = await self.beat_repo.get_active()
        if active is None or active.id == beat.id:
            return
        name: str | None = None
        if self.projects is not None:
            try:
                name = (await self.projects.get_by_id(active.project_id)).name
            except DomainException:
                # The open session is on a project this caller can no longer
                # read (an assignment that ended). It still blocks the write;
                # it just cannot be named.
                name = None
        raise TimerAlreadyRunning(project_name=name, beat=active.model_dump(mode="json"))

    async def create_beat(self, beat: Beat) -> Beat:
        """Create a new beat, auto-tagging it from daemon flow signals. A
        create that leaves `end` unset opens a session, and is refused while
        another is open."""
        await self._refuse_second_timer(beat)
        beat = await self._stamped(beat)
        if self.flow_repo is not None and beat.end is not None:
            beat.tags = await derive_flow_tags(self.flow_repo, beat.start, beat.end)
        return await self.beat_repo.create(beat)

    async def get_beat(self, beat_id: str) -> Beat:
        """Get a beat by ID."""
        return await self.beat_repo.get_by_id(beat_id)

    async def update_beat(
        self, beat: Beat, *, note: str | None = None, expected: ExpectedBeat | None = None
    ) -> Beat:
        """Write an edit's project, start and end onto the stored beat,
        re-deriving tags from daemon flow signals, and return the beat as
        stored. `note` is the one other field that writes, and only when
        sent (#348): a string sets it, an empty or blank one clears it, None
        leaves it as stored — so a client without a note input changes
        nothing by not having one. Every other stored field stays as it is,
        whatever `beat` carries for it.

        `expected`, when sent, is the session as the edit was made against
        it; a stored session that no longer matches is refused (BeatChanged)
        rather than overwritten.

        If the daemon has no windows for the (possibly edited) range we keep the
        beat's existing tags rather than wiping them — non-destructive for any
        tags captured before this range was last touched. A beat reopened
        (`end` None) keeps its tags too; the stop that closes it derives them,
        and the reopen is refused (TimerAlreadyRunning) while another session
        is open — reopening is a start by another name.
        """
        # Validate the beat can be stopped if end is being set
        if beat.end:
            start = normalize_tz(beat.start)
            end = normalize_tz(beat.end)
            if end < start:
                raise InvalidEndTime()
        else:
            # Clearing `end` reopens the session, which is a start by another
            # name; it is refused while another session is open.
            await self._refuse_second_timer(beat)
        stored: Beat | None = None
        if expected is not None and beat.id is not None:
            stored = await self.beat_repo.get_by_id(beat.id)
            if not expected.matches(stored):
                raise BeatChanged()
        written = {"project_id", "start", "end"}
        if note is not None:
            beat.note = note.strip() or None
            written.add("note")
        if self.projects is not None:
            # The stored beat's own month must be open too: moving an entry
            # out of an approved month changes the frozen figure as surely as
            # moving one in.
            if self.locks is not None and beat.id is not None:
                stored = stored or await self.beat_repo.get_by_id(beat.id)
                if stored.organisation_id is not None:
                    stored_project = await self.projects.get_by_id(stored.project_id)
                    await refuse_locked(self.locks, stored_project, stored.start)
            await self._stamped(beat)
            written.add("organisation_id")
        if self.flow_repo is not None and beat.end is not None:
            derived = await derive_flow_tags(self.flow_repo, beat.start, beat.end)
            if derived:
                beat.tags = derived
                written.add("tags")
        return await self.beat_repo.update(beat, written)

    async def delete_beat(self, beat_id: str) -> bool:
        """Delete a beat by ID, and its billable override with it. The
        override goes whether or not the beat was there: one left without
        its beat is a leftover either way. One inside an approved timesheet
        month is refused: the frozen figure was made of it."""
        if self.locks is not None and self.projects is not None:
            try:
                stored = await self.beat_repo.get_by_id(beat_id)
            except BeatNotFound:
                stored = None
            if stored is not None and stored.organisation_id is not None:
                project = await self.projects.get_by_id(stored.project_id)
                await refuse_locked(self.locks, project, stored.start)
        deleted = await self.beat_repo.delete(beat_id)
        await self.overrides.delete(beat_id)
        return deleted

    async def list_beats(
        self,
        project_id: str | None = None,
        date_filter: date | None = None,
    ) -> list[Beat]:
        """List beats with optional filters."""
        return await self.beat_repo.list(project_id=project_id, date_filter=date_filter)


def _check_contract(project: Project) -> None:
    """What a project write must satisfy beyond the model's own validators.

    A contract lives only on a day job: sent with any other kind it is refused
    (409), on the project routes as on `PUT /{id}/contract`, rather than kept
    dormant on a project that cannot read it. And its holiday region must be
    one the calendar library knows — deliberately not a validator on
    `Contract`: the model is re-validated on every read, and which codes the
    library knows moves with its version. A code it stops recognising must
    make one contract un-editable until it is fixed, not every project of the
    user unreadable.

    The vacation count's opening must fall inside the contract's dates, and
    is checked here for the same reason, and because it runs after the
    keep-unsent merge (`keep_unsent_contract_fields`): an older client that
    removes the first term, inserts an earlier one or moves `ended_on`
    sends no entitlement, keeps the stored one, and must be refused (409)
    rather than have the count's start silently fall outside the job.
    """
    contract = project.contract
    if contract is None:
        return
    if project.kind is not ProjectKind.DAY_JOB:
        raise NotADayJob()
    if contract.holiday_country is not None:
        check_region(contract.holiday_country, contract.holiday_subdivision)
    vacation = contract.vacation
    if vacation is not None and not within_contract(contract, vacation.opening_on):
        raise VacationOpeningOutsideContract(vacation.opening_on)


_KEPT_WHEN_UNSENT = ("company_holidays", "holidays_not_given", "vacation")


def keep_unsent_contract_fields(incoming: Contract, stored: Contract | None) -> Contract:
    """`incoming`, with each later-added field it left out taken from `stored`.

    Omitted is not cleared: a client that predates a field (an old SPA tab,
    which rebuilds the whole contract on every term edit) does not send it,
    and must not delete it; an explicit empty value clears. Which keys were
    sent is the model's `model_fields_set`.

    `model_copy` does not re-validate, and that is safe only because each
    kept field's rules are its own (see `Contract`): the stored value passed
    them on its way in and on every read since, so any incoming contract
    plus a stored value is valid. A model rule tying one to another field
    would need this merge to re-validate and turn a failure into a 422. The
    entitlement's one tie to the rest, its opening inside the contract's
    dates, is a write-time check after the merge instead (`_check_contract`).
    """
    if stored is None:
        return incoming
    unsent = {
        field: getattr(stored, field)
        for field in _KEPT_WHEN_UNSENT
        if field not in incoming.model_fields_set
    }
    return incoming.model_copy(update=unsent) if unsent else incoming


class ProjectService:
    """Service for managing project operations and analytics."""

    def __init__(
        self,
        project_repo: ProjectStore,
        beat_repo: ProjectBeatReader,
        adjustments: ContractAdjustments,
        billing: BillingPresence,
    ):
        self.project_repo = project_repo
        self.beat_repo = beat_repo
        self.adjustments = adjustments
        self.billing = billing

    async def create_project(self, project: Project) -> Project:
        """Create a new project. A new project has no balance adjustments, so
        there is nothing to reconcile."""
        _check_contract(project)
        return await self.project_repo.create(project)

    async def update_project(
        self, project: Project, *, previous_contract: Contract | None
    ) -> Project:
        """Update an existing project, reconciling its balance adjustments
        against the contract it had (`_reconcile_adjustments`). The previous
        contract is a required keyword so no caller skips that by accident;
        one that leaves the contract alone passes the one it read.

        A billed project keeps its kind: moving it away from freelance is
        refused (409 PROJECT_HAS_BILLING) until its billing is stopped, as a
        contract lives only on a day job. Asked only of a project that is not
        freelance after the write, so the colour picker on a freelance project
        reads nothing."""
        _check_contract(project)
        if project.id is not None:
            existing = await self.project_repo.get_by_id(project.id)
            check_organisation_fields(existing, project)
            if (
                existing.organisation is not None
                and existing.organisation.contract_managed
                and project.contract != existing.contract
            ):
                raise ContractManaged()
        if (
            project.kind is not ProjectKind.FREELANCE
            and project.id is not None
            and await self.billing.exists(project.id)
        ):
            raise ProjectHasBilling()
        purge_after = await self._reconcile_adjustments(
            project.id, previous_contract, project.contract
        )
        updated = await self.project_repo.update(project)
        if purge_after and project.id is not None:
            await self.adjustments.delete_by_project(project.id)
        return updated

    async def restore_project(self, project: Project) -> Project:
        """Write a project read from a backup, keeping its id: an update when
        the id is one of this user's projects, a create otherwise. Either way
        it is an ordinary project write — the contract's checks, the kind
        guard, and on an update the reconcile against the contract it
        replaces — so a backup cannot leave adjustments behind that a
        contract write would have purged or refused, nor billing on a
        project that is no longer freelance."""
        if project.id is not None:
            try:
                existing = await self.project_repo.get_by_id(project.id)
            except ProjectNotFound:
                pass
            else:
                return await self.update_project(project, previous_contract=existing.contract)
        return await self.create_project(project)

    async def _reconcile_adjustments(
        self, project_id: str | None, previous: Contract | None, new: Contract | None
    ) -> bool:
        """What a contract write does to the balance adjustments, before the
        write; True when they are to be purged after it.

        - The contract goes (a kind change, `contract: null`): they go with
          it, after the write, since they only mean something against its
          balance. Nothing dormant is kept for an undo.
        - A contract arrives where there was none: anything left over is
          purged first. No adjustment can be live without a contract, so
          this clears whatever a failed purge left.
        - The first day moves later past an adjustment: 409, rather than
          the adjustment silently dropping out of the balance.

        Anything else (a rename or a colour change resending the contract
        unchanged, a first day moved earlier) reads nothing.
        """
        if project_id is None:
            return False
        if previous is not None and new is None:
            return True
        if previous is None and new is not None:
            await self.adjustments.delete_by_project(project_id)
        elif previous is not None and new is not None and new.starts_on > previous.starts_on:
            earliest = await self.adjustments.earliest(project_id, previous.starts_on)
            if earliest is not None and earliest < new.starts_on:
                raise AdjustmentBeforeStart()
        return False

    async def replace_contract(self, project_id: str, contract: Contract) -> Project:
        """Replace a day job's whole contract — terms, region, opening balance, end.

        Whole rather than patched, like goal overrides: the terms are a history
        that only makes sense as one list. The holiday lists and the vacation
        entitlement are the exception: one the body leaves out is kept
        (`keep_unsent_contract_fields`); `[]` or `null` clears it. The
        kind is not touched here; a project that is not a day job has no
        contract to replace (409).
        """
        project = await self.project_repo.get_by_id(project_id)
        if project.kind is not ProjectKind.DAY_JOB:
            raise NotADayJob()
        previous = project.contract
        project.contract = keep_unsent_contract_fields(contract, previous)
        return await self.update_project(project, previous_contract=previous)

    async def archive_project(self, project_id: str) -> Project:
        """Archive a project."""
        project = await self.project_repo.get_by_id(project_id)
        if project.organisation is not None:
            # The organisation archives its own projects; a member leaves
            # one by leaving the organisation (docs/organisations.md).
            raise OrganisationProject(f"{project.organisation.name} owns this project")
        project.archived = True
        return await self.project_repo.update(project)

    async def unarchive_project(self, project_id: str) -> Project:
        """Restore an archived project — symmetric to archive_project.

        Using a dedicated endpoint (rather than PUT with archived=false)
        means callers can't silently wipe fields they don't yet know
        about: the UI Project type doesn't carry github_repo, category,
        or autostart_repos yet, so a generic update-based unarchive
        would drop them.
        """
        project = await self.project_repo.get_by_id(project_id)
        if project.organisation is not None:
            raise OrganisationProject(f"{project.organisation.name} owns this project")
        project.archived = False
        return await self.project_repo.update(project)

    async def list_projects(self, archived: bool = False) -> list[Project]:
        """List projects with optional archived filter."""
        return await self.project_repo.list(archived=archived)

    async def get_today_time(self, project_id: str) -> timedelta:
        """Get total time spent on project today."""
        beats = await self.beat_repo.list_by_project(project_id)
        today = date.today()
        today_beats = [b for b in beats if b.start.date() == today]
        return sum((b.duration for b in today_beats), timedelta())

    async def get_last_tracked_at(self, project_id: str) -> datetime | None:
        """The timestamp of the project's most recent activity.

        Used by the /projects index page's "last tracked" column (P3.0).
        Falls back to a beat's `start` when `end` is null (running beat) so
        an in-progress timer counts as "just now".
        """
        beats = await self.beat_repo.list_by_project(project_id)
        return self._last_tracked_from_beats(beats)

    # ------------------------------------------------------------------ #
    # FF.15: pure-Python helpers below. Each public method above fetches
    # beats per-project and delegates. The list_projects route (after
    # FF.15) fetches every displayed project's beats in ONE Mongo find and
    # calls these helpers directly, sharing the same in-memory list across
    # the three aggregations. A helper with a public method MUST stay
    # byte-for-byte equivalent to it — the `*_matches_public_method` tests
    # in test_domain.py guard the drift. `_this_week_from_beats` has none:
    # it is the index's alone.
    # ------------------------------------------------------------------ #

    @staticmethod
    def _last_tracked_from_beats(beats: list[Beat]) -> datetime | None:
        if not beats:
            return None
        return max(b.end or b.start for b in beats)

    @staticmethod
    def _this_week_from_beats(beats: list[Beat], project: Project) -> dict:
        """The index's `this_week` slots for one project: the minutes of its
        completed beats that started in the current week, by the server's
        date, and the goal `Project.effective_goal` resolves for that Monday
        — with whether an override is what resolved it."""
        today = date.today()
        monday = today - timedelta(days=today.weekday())
        sunday = monday + timedelta(days=6)
        worked = sum(
            (b.duration for b in beats if b.end is not None and monday <= b.start.date() <= sunday),
            timedelta(),
        )
        goal, goal_type = project.effective_goal(monday)
        return {
            # Hours to the hundredth first, as the index has always counted them.
            "weekly_minutes": round(worked.total_seconds() / 3600, 2) * 60,
            "effective_goal": goal,
            "effective_goal_type": goal_type.value if goal_type else None,
            # True iff an override resolves for the week — lets the UI tell
            # "override says no goal" (null + overridden) from "no override and
            # no project default" (null + not overridden).
            "effective_goal_overridden": project.goal_overridden(monday),
        }

    async def get_monthly_totals(self, project_id: str, tz: ZoneInfo) -> dict:
        """Get total time per month for a project.

        Returns:
            Dict with durations per month, total minutes, and any warnings.
        """
        beats = await self.beat_repo.list_by_project(project_id)
        return self._monthly_totals_from_beats(beats, tz)

    @staticmethod
    def _monthly_totals_from_beats(beats: list[Beat], tz: ZoneInfo) -> dict:
        """Hours per local month, keyed 'YYYY-MM', and the minutes of them all.
        A month's hours are the ledger's days that fall in it: each beat goes
        whole to the local date it started on, in `tz`, and a running timer
        counts up to now (`worked_by_local_day`)."""
        warnings = [
            f"Warning: Log {beat.id} has duration longer than 24 hours ({beat.duration})."
            for beat in beats
            if beat.duration > timedelta(hours=24)
        ]

        hours_per_month: dict[str, float] = defaultdict(float)
        for day, hours in worked_by_local_day(beats, tz).items():
            hours_per_month[day.strftime("%Y-%m")] += hours

        return {
            "durations_per_month": {
                month: round(hours, 2) for month, hours in sorted(hours_per_month.items())
            },
            "total_minutes": round(sum(hours_per_month.values()) * 60),
            "warnings": warnings,
        }

    async def get_daily_average(self, project_id: str, days: int = 30) -> dict:
        """Get average daily session time for a project over the last N days."""
        beats = await self.beat_repo.list_by_project(project_id)
        cutoff = date.today() - timedelta(days=days)
        completed = [b for b in beats if b.end is not None and b.start.date() >= cutoff]
        if not completed:
            return {"avg_minutes": 0, "days_tracked": 0}
        by_day: dict[date, timedelta] = defaultdict(timedelta)
        for b in completed:
            by_day[b.start.date()] += b.duration
        days_tracked = len(by_day)
        total = sum(by_day.values(), timedelta())
        avg_minutes = round(total.total_seconds() / 60 / days_tracked)
        return {"avg_minutes": avg_minutes, "days_tracked": days_tracked}

    async def get_daily_summary(self, project_id: str) -> dict[str, str]:
        """Get summary of time per day for a project."""
        beats = await self.beat_repo.list_by_project(project_id)

        by_day: dict[date, list[timedelta]] = {}
        for beat in beats:
            if beat.day not in by_day:
                by_day[beat.day] = []
            by_day[beat.day].append(beat.duration)

        return {str(day): str(sum(durations, timedelta())) for day, durations in by_day.items()}


def worked_by_local_day(beats: Iterable[Beat], tz: ZoneInfo) -> dict[date, float]:
    """Hours per local calendar day, by the day each beat *started*.

    A beat that crosses midnight belongs whole to the day it started on: the
    contract counts hours, not which side of twelve they fell, and one late
    session is one session. A running beat counts up to now (`Beat.duration`),
    so the week's `worked` moves while the timer runs.
    """
    hours: dict[date, float] = defaultdict(float)
    for beat in beats:
        hours[local_date(beat.start, tz)] += beat.duration.total_seconds() / 3600
    return hours


class ContractService:
    """A day job read against its contract, its absences and its balance
    adjustments.

    Writing the contract is `ProjectService.replace_contract`, a project write
    with the region check; this service only reads projects, through a
    user-scoped repository, so someone else's project is not found (404)
    rather than forbidden — the same answer as for a project that does not
    exist. Absences and balance adjustments are kept here because their only
    readers are the week, the ledger and the vacation year.
    """

    def __init__(
        self,
        project_repo: ProjectReader,
        beat_repo: ProjectBeatReader,
        absence_repo: AbsenceStore,
        adjustment_repo: AdjustmentStore,
        now: Callable[[ZoneInfo], datetime] = datetime.now,
        locks: PeriodLocks | None = None,
    ):
        self.project_repo = project_repo
        self.beat_repo = beat_repo
        self.absence_repo = absence_repo
        self.adjustment_repo = adjustment_repo
        # Stage 3: absence and adjustment writes dated inside an approved
        # timesheet month are refused, like a beat's.
        self.locks = locks
        # The one clock every read here uses: which week is open, which day
        # the balance is as of, which year the calendar defaults to are all
        # "today in the request timezone", and a test hands in a fixed instant
        # to pin that it is the request's and not the server's.
        self._now = now

    async def week(self, project_id: str, week_of: date | None, tz: ZoneInfo) -> ContractWeek:
        """The week starting `week_of` (a Monday; None for the current week in
        `tz`) against the contract, with the balance as of today in `tz`."""
        project = await self._day_job(project_id)
        beats = await self.beat_repo.list_by_project(project_id)
        return await self.week_for(project, beats, week_of, tz)

    async def week_for(
        self, project: Project, beats: list[Beat], week_of: date | None, tz: ZoneInfo
    ) -> ContractWeek:
        """`week` for a project whose beats the caller already holds — the
        project index loads every listed project's beats in one query and
        must not load them again per day job.

        One absence read, one adjustment read and one calendar build per
        call, over the union of the week and the contract's life so far: the
        week needs its own days, the balance needs every day since the
        contract started. Adjustments before the first day count for
        nothing, so they are not read.
        """
        if project.kind is not ProjectKind.DAY_JOB:
            raise NotADayJob()
        if project.contract is None:
            raise NoContract()
        if project.id is None:
            raise ProjectNotFound()
        contract = project.contract
        today = self._now(tz).date()
        if week_of is None:
            week_of = today - timedelta(days=today.weekday())
        start = min(contract.starts_on, week_of)
        end = max(today, week_of + timedelta(days=6))
        absences = await self.absence_repo.list_by_project(project.id, start, end)
        adjustments = await self.adjustment_repo.list_by_project(
            project.id, contract.starts_on, end
        )
        holidays = contract_holidays(contract, start, end)
        worked = worked_by_local_day(beats, tz)
        return self._assemble(contract, absences, holidays, worked, adjustments, week_of, today)

    async def ledger(self, project_id: str, weeks: int, tz: ZoneInfo) -> Ledger:
        """The last `weeks` weeks of any project, newest first, ending with the
        current week in `tz`, and the balance as of today in `tz` with the
        terms that make it — the project page's one read for every week
        figure (`domain/ledger.py`).

        One beats read, and on a day job with a contract one absence read,
        one adjustment read and one calendar build, over the union of the
        weeks shown and the contract's life so far: each week's closing
        balance needs every day since the contract started. A project of another kind, or a day job
        without a contract, gets its goal and its hours and nothing is read
        for a contract. A region the calendar library has stopped knowing is
        this project's own error (400), as it is on the week route.
        """
        project = await self.project_repo.get_by_id(project_id)
        today = self._now(tz).date()
        monday = today - timedelta(days=today.weekday())
        contract = project.contract if project.kind is ProjectKind.DAY_JOB else None
        # Only the sessions that can reach a day the ledger shows: from the
        # contract's first day, since every close needs every day since then,
        # or from the oldest week shown when nothing governs. A day before
        # that is in no figure, and reading every session a project ever had
        # was the API's slowest read (#376). The extra day is for the
        # timezone: a session is bucketed by its local start day, and a tz
        # behind UTC can pull a UTC instant back onto the day before.
        first_day = monday - timedelta(weeks=weeks - 1)
        if contract is not None:
            first_day = min(contract.starts_on, first_day)
        since = datetime.combine(first_day - timedelta(days=1), time.min, tzinfo=UTC)
        beats = await self.beat_repo.list_by_project(project_id, since)
        absences: list[Absence] = []
        adjustments: list[BalanceAdjustment] = []
        holidays: dict[date, str] = {}
        if contract is not None and project.id is not None:
            start = min(contract.starts_on, monday - timedelta(weeks=weeks - 1))
            end = max(today, monday + timedelta(days=6))
            absences = await self.absence_repo.list_by_project(project.id, start, end)
            adjustments = await self.adjustment_repo.list_by_project(
                project.id, contract.starts_on, end
            )
            holidays = contract_holidays(contract, start, end)
        worked = worked_by_local_day(beats, tz)
        return assemble_ledger(
            project, contract, absences, holidays, worked, adjustments, today, weeks
        )

    async def timesheet(self, project_id: str, month: date, tz: ZoneInfo) -> Timesheet:
        """The finished days of `month` (its 1st) inside the contract, a row
        each, with the balance brought forward and carried forward
        (`domain/timesheet.py`). Today is the request's, in `tz`: the sheet
        runs through yesterday, and a running timer counts up to now on the
        day it started, as on the ledger.

        One beats read, one absence read, one adjustment read and one
        calendar build, over the contract's life through the sheet's last
        day: every close needs every day since the contract started, not
        only the month's. A company holiday goes by `COMPANY_HOLIDAY`, not
        the name typed for it. 409 on a project that is not a day job
        (NOT_A_DAY_JOB), without a contract (NO_CONTRACT), or for a month
        with no finished day inside the contract (OUTSIDE_CONTRACT).
        """
        project = await self._day_job(project_id)
        contract = project.contract
        if contract is None:
            raise NoContract()
        span = timesheet_range(contract, month, self._now(tz).date())
        if span is None:
            raise MonthOutsideContract()
        first, last = span
        beats = await self.beat_repo.list_by_project(project_id)
        absences = await self.absence_repo.list_by_project(project_id, contract.starts_on, last)
        adjustments = await self.adjustment_repo.list_by_project(
            project_id, contract.starts_on, last
        )
        holidays = contract_holidays(
            contract, contract.starts_on, last, company_name=COMPANY_HOLIDAY
        )
        worked = worked_by_local_day(beats, tz)
        return assemble_timesheet(contract, absences, holidays, worked, adjustments, first, last)

    async def weeks_for(
        self, projects: Iterable[Project], beats_by_pid: Mapping[str, list[Beat]], tz: ZoneInfo
    ) -> dict[str, ContractWeek]:
        """The current week of every day job with a contract among `projects`,
        by project id — the project index's read, over beats it already holds.

        A project of another kind, or without a contract, is simply absent
        from the result. So is one whose region the calendar library has
        stopped knowing: that makes one contract unreadable — its own week
        route says so — not the whole project list, so it is logged and
        skipped.
        """
        weeks: dict[str, ContractWeek] = {}
        for project in projects:
            if not (project.id and project.kind is ProjectKind.DAY_JOB and project.contract):
                continue
            try:
                weeks[project.id] = await self.week_for(
                    project, beats_by_pid.get(project.id, []), None, tz
                )
            except UnknownHolidayRegion:
                logger.warning("project %s: contract region unknown, week skipped", project.id)
        return weeks

    async def current_weeks(
        self, projects: Iterable[Project], tz: ZoneInfo, as_of: date
    ) -> dict[str, ContractWeek]:
        """The current week of every day job with a contract among `projects`,
        by project id, provided `as_of` is today in `tz` — the coach's read,
        which holds no beats of its own.

        Empty for any other day: the figures are today's (the balance is as
        of today, the week is today's), and this service's clock is the one
        that says which day that is, so a backdated brief does not quote
        today's balance as its own and a test that fixes the clock fixes
        both sides. Otherwise one beats read per day job — a running beat
        counts, as on the project page — and then the index's read
        (`weeks_for`), so the figures are the week route's to the decimal
        and a region the library has stopped knowing skips that project.
        """
        if as_of != self._now(tz).date():
            return {}
        day_jobs = [p for p in projects if p.id and p.kind is ProjectKind.DAY_JOB and p.contract]
        beats_by_pid = {p.id: await self.beat_repo.list_by_project(p.id) for p in day_jobs if p.id}
        return await self.weeks_for(day_jobs, beats_by_pid, tz)

    async def expected_for_week(self, project: Project, week_of: date) -> float | None:
        """What the contract expects of the week starting `week_of` — the week
        route's `expected` on its own, for the readers that quote a figure
        beside it: the Inbox's planning line, the pacing card, the
        stale-project card. None on anything but a day job with a
        contract, and under the null rule (`week_expectation`).

        One absence read and one calendar build, over the week alone — the
        balance is not wanted here, so nothing before the week is. A region
        the calendar library has stopped knowing costs the figure, not the
        reader: logged and None, as the index does.
        """
        if not (project.id and project.kind is ProjectKind.DAY_JOB and project.contract):
            return None
        contract = project.contract
        end = week_of + timedelta(days=6)
        absences = await self.absence_repo.list_by_project(project.id, week_of, end)
        try:
            holidays = set(contract_holidays(contract, week_of, end))
        except UnknownHolidayRegion:
            logger.warning("project %s: contract region unknown, expectation skipped", project.id)
            return None
        return week_expectation(contract, absences, holidays, week_of)

    @staticmethod
    def _assemble(
        contract: Contract,
        absences: Iterable[Absence],
        holidays: Mapping[date, str],
        worked: Mapping[date, float],
        adjustments: Iterable[BalanceAdjustment],
        week_of: date,
        today: date,
    ) -> ContractWeek:
        by_day = absences_by_day(absences)
        holiday_days = set(holidays)
        days: list[ContractDay] = []
        expected_raw = 0.0
        worked_raw = 0.0
        counted_raw = 0.0  # worked as the balance counts it (`counts_worked`)
        for offset in range(7):
            day = week_of + timedelta(days=offset)
            expected_day = expected_on(contract, day, holiday_days, by_day)
            worked_day = worked.get(day, 0.0)
            expected_raw += expected_day
            worked_raw += worked_day
            if counts_worked(contract, day):
                counted_raw += worked_day
            absence = by_day.get(day)
            days.append(
                ContractDay(
                    date=day,
                    expected=round_hours(expected_day),
                    worked=round_hours(worked_day),
                    holiday=holidays.get(day),
                    absence=(
                        DayAbsence(type=absence.type, half_day=absence.half_day, note=absence.note)
                        if absence is not None
                        else None
                    ),
                )
            )
        # The same function every other reader of the figure goes through,
        # so the card, the history row and the planning line cannot drift.
        expected = week_expectation(contract, absences, holiday_days, week_of)
        # Rounded from the raw sums, as every other figure here is: 8.545 h
        # of a 40 h week reads 8.54 worked and 31.45 remaining, which the
        # page shows as 8.5 and 31.4 and the coach says as the page does.
        # The page's figures need not add up at the decimal it shows.
        remaining = round_hours(expected_raw - counted_raw) if expected is not None else None
        running = (
            balance_terms(contract, absences, holiday_days, worked, adjustments, today)
            if owes(term_on(contract, today))
            else None
        )
        return ContractWeek(
            week_of=week_of,
            expected=expected,
            worked=round_hours(worked_raw),
            remaining=remaining,
            balance=round_hours(running.balance) if running else None,
            days=days,
            balance_as_of=today if running else None,
            balance_opening=round_hours(running.opening) if running else None,
            balance_worked=round_hours(running.worked) if running else None,
            balance_expected_through=(round_hours(running.expected_through) if running else None),
            balance_adjusted=round_hours(running.adjusted) if running else None,
        )

    async def holidays(
        self, project_id: str, year: int | None, tz: ZoneInfo, *, include_not_given: bool = False
    ) -> list[Holiday]:
        """The contract's holidays in `year` (None for the current year in
        `tz`), by date, for the calendar: the region's the employer gives and
        the company's own, and with `include_not_given` the region's it does
        not give as well. Empty when there is no contract."""
        project = await self._day_job(project_id)
        contract = project.contract
        if contract is None:
            return []
        if year is None:
            year = self._now(tz).year
        return contract_calendar(
            contract, date(year, 1, 1), date(year, 12, 31), include_not_given=include_not_given
        )

    async def vacation(self, project_id: str, year: int | None, tz: ZoneInfo) -> VacationYear:
        """One year of the contract's vacation entitlement (None for the
        current year in `tz`, the only thing the clock is read for), from
        the opening on: `domain/vacation.py` chains every year before it.

        One absence read, from the opening through the end of `year` (or
        `ended_on`), and one calendar build over the span of the vacation
        days in it alone, so a chain of many years does not build a
        calendar for each. 409 without a contract, without an entitlement,
        or for a year before the opening's or after the one the contract
        ends in.
        """
        project = await self._day_job(project_id)
        contract = project.contract
        if contract is None:
            raise NoContract()
        entitlement = contract.vacation
        if entitlement is None:
            raise NoVacationEntitlement()
        if year is None:
            year = self._now(tz).year
        first = entitlement.opening_on.year
        last = contract.ended_on.year if contract.ended_on is not None else None
        if year < first or (last is not None and year > last):
            raise VacationYearOutOfRange(first, last)
        end = date(year, 12, 31)
        if contract.ended_on is not None:
            end = min(end, contract.ended_on)
        absences = await self.absence_repo.list_by_project(project_id, entitlement.opening_on, end)
        days_off = [a.date for a in absences if a.type is AbsenceType.VACATION]
        holidays = (
            set(contract_holidays(contract, min(days_off), max(days_off))) if days_off else set()
        )
        return vacation_year(contract, absences, holidays, year)

    async def list_absences(
        self, project_id: str, start: date | None, end: date | None, tz: ZoneInfo
    ) -> list[Absence]:
        """Absences in [start, end], by date; each bound left None defaults on
        its own to the current calendar year in `tz`."""
        await self._day_job(project_id)
        today = self._now(tz).date()
        return await self.absence_repo.list_by_project(
            project_id, start or date(today.year, 1, 1), end or date(today.year, 12, 31)
        )

    async def record_absence(self, absence: Absence) -> Absence:
        """Record an absence; one already on that date is replaced. On an
        organisation's project it is stamped as that organisation's record,
        as a beat there is. Where the employer manages the contract the
        member asks instead (409 CONTRACT_MANAGED), and a date inside an
        approved month is refused."""
        project = await self._day_job(absence.project_id)
        _refuse_managed(project)
        await refuse_locked(self.locks, project, None, absence.date)
        absence.organisation_id = stamp_for_day(project, absence.date)
        return await self.absence_repo.upsert(absence)

    async def remove_absence(self, project_id: str, absence_id: str) -> None:
        """Remove an absence; one that is not on this project is not found.
        On a managed assignment the days off are the employer's to change,
        and one dated inside an approved month is refused, as recording it
        would be (decision 23)."""
        project = await self._day_job(project_id)
        _refuse_managed(project)
        absence = await self.absence_repo.get(project_id, absence_id)
        if absence is None:
            raise AbsenceNotFound(absence_id)
        await refuse_locked(self.locks, project, None, absence.date)
        if not await self.absence_repo.delete(project_id, absence_id):
            raise AbsenceNotFound(absence_id)

    async def record_adjustment(
        self, adjustment: BalanceAdjustment, tz: ZoneInfo
    ) -> BalanceAdjustment:
        """Record a balance adjustment; one already on that date is replaced
        and keeps its id. It needs a contract (without one there is no
        balance to adjust) and a date from the contract's first day through
        today in `tz`: before the first day it would count for nothing, and a
        future one would move a balance nobody can see yet. After `ended_on`
        is allowed: that is how a final balance is paid out."""
        project = await self._day_job(adjustment.project_id)
        _refuse_managed(project)
        await refuse_locked(self.locks, project, None, adjustment.date)
        contract = project.contract
        if contract is None:
            raise NoContract()
        today = self._now(tz).date()
        if not contract.starts_on <= adjustment.date <= today:
            raise AdjustmentOutsideBalance()
        return await self.adjustment_repo.upsert(adjustment)

    async def remove_adjustment(self, project_id: str, adjustment_id: str) -> None:
        """Remove a balance adjustment; one that is not on this project is
        not found. On a managed assignment they are the employer's, and one
        dated inside an approved month is refused, as recording it would be
        (decision 23)."""
        project = await self._day_job(project_id)
        _refuse_managed(project)
        adjustment = await self.adjustment_repo.get(project_id, adjustment_id)
        if adjustment is None:
            raise AdjustmentNotFound(adjustment_id)
        await refuse_locked(self.locks, project, None, adjustment.date)
        if not await self.adjustment_repo.delete(project_id, adjustment_id):
            raise AdjustmentNotFound(adjustment_id)

    async def _day_job(self, project_id: str) -> Project:
        """The project, provided it is a day job — with or without a contract:
        leave can be recorded before the contract is written, and the holidays
        of a job without one are simply none. Only the week needs a contract."""
        project = await self.project_repo.get_by_id(project_id)
        if project.kind is not ProjectKind.DAY_JOB:
            raise NotADayJob()
        return project
