"""Domain services - business logic that coordinates multiple entities."""

import logging
from collections import defaultdict
from collections.abc import Iterable
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from beats.domain.contracts import (
    contract_diverges_from,
    within_contract,
)
from beats.domain.exceptions import (
    AdjustmentBeforeStart,
    BeatChanged,
    BeatNotFound,
    ContractManaged,
    DomainException,
    InvalidEndTime,
    NoActiveTimer,
    NoObjectMatched,
    NotADayJob,
    OrganisationProject,
    PeriodApproved,
    ProjectHasBilling,
    ProjectNotFound,
    TimerAlreadyRunning,
    TimerChanged,
    VacationOpeningOutsideContract,
)
from beats.domain.holidays import (
    check_region,
)
from beats.domain.models import (
    ORGANISATION_FIELDS,
    Beat,
    Contract,
    ExpectedBeat,
    Project,
    ProjectKind,
)
from beats.domain.ports import (
    ApprovalMarks,
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
from beats.domain.utils import local_date, normalize_tz

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


def organisation_of(project: Project) -> str | None:
    """The organisation that owns `project`, or None."""
    return project.organisation.id if project.organisation is not None else None


def organisation_stamp(project: Project, start: datetime) -> str | None:
    """The organisation whose record a session starting at `start` is.

    Rule 4: connecting a project shares its history only from the day the
    member chose, so a session before `private_before` stays theirs alone
    however it is written — a back-dated create, a timer started in the
    past, or an edit that moves a shared session back out of the range,
    which clears the stamp it had. Owning the project is not enough on its
    own: that was #404, where editing a pre-share entry's note handed it
    over.

    On a project the organisation has owned all along, `private_before` is
    null and a back-dated entry is its record like any other: the member
    could not have tracked on it before they were assigned, so a date
    before the assignment is late work and not history. Decision 7 draws
    the line in the same place — the stamp is withheld "before a
    *connected* project's `shared_from`".
    """
    owner = project.organisation
    if owner is None:
        return None
    if owner.private_before is not None and normalize_tz(start) < normalize_tz(
        owner.private_before
    ):
        return None
    return owner.id


def organisation_stamp_for_day(project: Project, day: date) -> str | None:
    """The same rule for an absence, which is a day and not an instant.

    The day the member chose is kept beside the instant, because
    `private_before` is that day's local midnight and reading the day back
    off it would need the timezone it was taken in. An assignment carrying
    the instant and not the day falls back to the instant's own date.
    """
    owner = project.organisation
    if owner is None:
        return None
    if owner.private_before is None:
        return owner.id
    private = owner.private_before_day or normalize_tz(owner.private_before).date()
    return None if day < private else owner.id


async def reconcile_adjustments(
    adjustments: ContractAdjustments,
    project_id: str | None,
    previous: Contract | None,
    new: Contract | None,
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

    A free function, not a method, because the employer writes contracts
    too (`EmploymentService.set_contract`) and decision 21 says one set of
    rules validates a contract whoever writes it. It takes the adjustment
    port, which each side binds to the member whose balance it is.
    """
    if project_id is None:
        return False
    if previous is not None and new is None:
        return True
    if previous is None and new is not None:
        await adjustments.delete_by_project(project_id)
    elif previous is not None and new is not None and new.starts_on > previous.starts_on:
        earliest = await adjustments.earliest(project_id, previous.starts_on)
        if earliest is not None and earliest < new.starts_on:
            raise AdjustmentBeforeStart()
    return False


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
        # project is an organisation's and the start is on or after the day
        # the member shares from (docs/organisations.md).
        start = start_time or datetime.now(UTC)
        await refuse_locked(self.locks, project, start)
        beat = Beat(
            project_id=project_id, start=start, organisation_id=organisation_stamp(project, start)
        )
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
        beat.organisation_id = organisation_stamp(project, beat.start)
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
        marks: ApprovalMarks | None = None,
    ):
        self.project_repo = project_repo
        self.beat_repo = beat_repo
        self.adjustments = adjustments
        self.billing = billing
        # Stage 3: a contract write on an organisation's project marks the
        # approved months it moves (decision 23). Without one (the tests'
        # bare service, a one-off script) nothing is marked.
        self.marks = marks

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
        await self._mark_moved_approvals(updated, previous_contract)
        return updated

    async def _mark_moved_approvals(self, project: Project, previous: Contract | None) -> None:
        """A contract write is never refused for an approved month; the
        approvals whose figures it moves are marked instead (decision 23).
        Only on an organisation's project — a personal day job has no
        approvals — and only from the day the two contracts diverge, so a
        term added for next year marks nothing already approved."""
        if self.marks is None or project.id is None or project.organisation is None:
            return
        from_day = contract_diverges_from(previous, project.contract)
        if from_day is not None:
            await self.marks.mark_terms_changed(project.id, from_day, datetime.now(UTC))

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
        return await reconcile_adjustments(self.adjustments, project_id, previous, new)

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
    # in test_project_aggregations.py guard the drift. `_this_week_from_beats` has none:
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
