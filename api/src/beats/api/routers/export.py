"""Export API router — CSV and JSON data export/import."""

import csv
import io
import json
from datetime import UTC, datetime
from typing import Annotated, Literal

from bson import ObjectId
from fastapi import APIRouter, Query, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import StreamingResponse
from pydantic import AfterValidator, BaseModel, Field, ValidationError

from beats.api.dependencies import (
    AbsenceRepoDep,
    AdjustmentRepoDep,
    BeatRepoDep,
    BillableOverrideRepoDep,
    BillingBudgetRepoDep,
    BillingServiceDep,
    ClientRepoDep,
    ContractServiceDep,
    ProjectBillingRepoDep,
    ProjectRepoDep,
    ProjectServiceDep,
    TimezoneDep,
)
from beats.api.errors import error_code
from beats.api.schemas import ImportCounts, ImportResponse, ImportSkip
from beats.domain.exceptions import (
    BackupOfAnotherAccount,
    BeatNotFound,
    DomainException,
    PeriodApproved,
    ProjectNotFound,
)
from beats.domain.models import (
    PERSONAL_FIELDS,
    Absence,
    BalanceAdjustment,
    Beat,
    BillableOverride,
    BillingBudget,
    BillingBudgetScope,
    Client,
    Project,
    ProjectBilling,
)
from beats.domain.services import refuse_locked
from beats.domain.utils import normalize_tz
from beats.infrastructure.repositories import (
    BeatRepository,
    ClientRepository,
    ProjectRepository,
)

router = APIRouter(prefix="/api/export", tags=["export"])


@router.get("/csv/sessions")
async def export_sessions_csv(
    beat_repo: BeatRepoDep,
    project_repo: ProjectRepoDep,
    project_id: str | None = Query(default=None),
):
    """Export sessions as CSV."""
    if project_id:
        beats = await beat_repo.list_by_project(project_id)
    else:
        beats = await beat_repo.list_all_completed()

    # Archived too, as in `/full`: a finished day job's sessions are still
    # written, and must not come out under "Unknown".
    projects = await project_repo.list(archived=False) + await project_repo.list(archived=True)
    project_map = {p.id: p.name for p in projects}

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["date", "project", "start", "end", "duration_minutes", "note", "tags"])

    for beat in sorted(beats, key=lambda b: b.start):
        if beat.end is None:
            continue
        duration_min = int(beat.duration.total_seconds() / 60)
        writer.writerow(
            [
                beat.day.isoformat(),
                project_map.get(beat.project_id, "Unknown"),
                beat.start.isoformat(),
                beat.end.isoformat(),
                duration_min,
                beat.note or "",
                ";".join(beat.tags) if beat.tags else "",
            ]
        )

    output.seek(0)
    filename = f"beats_sessions_{datetime.now(UTC).strftime('%Y%m%d')}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# The backup's format. 1.1 added `absences` and `balance_adjustments`, 1.2
# `clients`, `project_billing` and `billable_overrides`, 1.3 `billing_budgets`;
# an older file, which lacks them, still imports, as a backup with none of them.
_BACKUP_VERSION = "1.3"


@router.get("/full")
async def export_full_json(
    beat_repo: BeatRepoDep,
    project_repo: ProjectRepoDep,
    absence_repo: AbsenceRepoDep,
    adjustment_repo: AdjustmentRepoDep,
    client_repo: ClientRepoDep,
    billing_repo: ProjectBillingRepoDep,
    override_repo: BillableOverrideRepoDep,
    billing_budget_repo: BillingBudgetRepoDep,
):
    """Export everything a balance and a bill are made of, as JSON for
    backup: the projects (contract included), the sessions, the absences and
    the balance adjustments; the clients, each project's billing, the
    entries marked billable or not, and the billing budgets."""
    beats = await beat_repo.list()
    # Archived too: archiving is how a finished day job leaves the readers,
    # and its final balance, settlement included, is still the user's.
    projects = await project_repo.list(archived=False) + await project_repo.list(archived=True)
    absences = await absence_repo.list_all()
    adjustments = await adjustment_repo.list_all()
    # Archived clients too, for the same reason: their months are still billed.
    clients = await client_repo.list_all()
    billings = await billing_repo.list_all()
    overrides = await override_repo.list_all()
    # A budget whose scope has gone, which only a crash between two writes
    # could leave, is left out, as its read skips it: a client, or a project
    # still billed. The file it would be in could not be imported.
    scopes = {
        BillingBudgetScope.CLIENT: {c.id for c in clients},
        BillingBudgetScope.PROJECT: {b.project_id for b in billings} & {p.id for p in projects},
    }
    billing_budgets = [
        budget
        for budget in await billing_budget_repo.list_all()
        if budget.scope_id in scopes[budget.scope]
    ]
    data = {
        "exported_at": datetime.now(UTC).isoformat(),
        "version": _BACKUP_VERSION,
        "projects": [p.model_dump(mode="json") for p in projects],
        "beats": [b.model_dump(mode="json") for b in beats],
        "absences": [a.model_dump(mode="json") for a in absences],
        "balance_adjustments": [a.model_dump(mode="json") for a in adjustments],
        "clients": [c.model_dump(mode="json") for c in clients],
        "project_billing": [b.model_dump(mode="json") for b in billings],
        "billable_overrides": [o.model_dump(mode="json") for o in overrides],
        "billing_budgets": [b.model_dump(mode="json") for b in billing_budgets],
    }

    output = json.dumps(data, indent=2, default=str)
    filename = f"beats_backup_{datetime.now(UTC).strftime('%Y%m%d')}.json"
    return StreamingResponse(
        iter([output]),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _object_id(value: str | None) -> str | None:
    if value is not None and not ObjectId.is_valid(value):
        raise ValueError("an id in a backup is one this API issued: 24 hexadecimal digits")
    return value


# A project's, a beat's and a client's id are kept on restore, so each has to
# be one Mongo can store as an `_id`. An absence's and an adjustment's are not
# read: their project and date are their identity, as a billing's project and
# an override's beat are theirs.
_KeptId = Annotated[str | None, AfterValidator(_object_id)]


class _BackupProject(Project):
    id: _KeptId = None


class _BackupBeat(Beat):
    id: _KeptId = None


class _BackupClient(Client):
    id: _KeptId = None


class _Backup(BaseModel):
    """A backup file as the import reads it. Every list may be missing, so a
    1.0 file, made before absences and adjustments were exported, a 1.1 one,
    made before billing, or a 1.2 one, made before billing budgets, reads as
    a backup with none of them. A beat's
    derived fields (`is_active`, `duration`, `day`) are in the file but not
    read back."""

    projects: list[_BackupProject] = Field(default_factory=list)
    beats: list[_BackupBeat] = Field(default_factory=list)
    absences: list[Absence] = Field(default_factory=list)
    balance_adjustments: list[BalanceAdjustment] = Field(default_factory=list)
    clients: list[_BackupClient] = Field(default_factory=list)
    project_billing: list[ProjectBilling] = Field(default_factory=list)
    billable_overrides: list[BillableOverride] = Field(default_factory=list)
    billing_budgets: list[BillingBudget] = Field(default_factory=list)


async def _split_organisation_projects(
    backup: _Backup, project_repo: ProjectRepository, skipped: list[ImportSkip]
) -> tuple[list[_BackupProject], _Backup]:
    """Take the organisation-owned projects out of the file. Those the
    account still sees (assigned, in that organisation) are returned to be
    written as their personal half; the rest, and every session, absence and
    adjustment on them, go to `skipped`, each with ORGANISATION_PROJECT."""
    held: list[_BackupProject] = []
    dropped: set[str] = set()
    personal: list[_BackupProject] = []
    for project in backup.projects:
        if project.organisation is None:
            personal.append(project)
            continue
        current = None
        if project.id is not None:
            try:
                current = await project_repo.get_by_id(project.id)
            except ProjectNotFound:
                current = None
        if (
            current is not None
            and current.organisation is not None
            and current.organisation.id == project.organisation.id
        ):
            held.append(project)
            continue
        dropped.add(project.id or "")
        skipped.append(
            ImportSkip(
                collection="projects",
                project_id=project.id or "",
                date=None,
                code="ORGANISATION_PROJECT",
                detail=(
                    f"{project.organisation.name} owns this project; a backup does not "
                    "restore it, nor the sessions, absences and adjustments on it"
                ),
            )
        )
    if not dropped:
        return held, backup.model_copy(update={"projects": personal})

    def keep[T: Beat | Absence | BalanceAdjustment](
        records: list[T], collection: Literal["beats", "absences", "balance_adjustments"]
    ) -> list[T]:
        kept: list[T] = []
        for record in records:
            if record.project_id in dropped:
                skipped.append(
                    ImportSkip(
                        collection=collection,
                        project_id=record.project_id,
                        date=getattr(record, "date", None) or getattr(record, "day", None),
                        code="ORGANISATION_PROJECT",
                        detail="on an organisation's project the backup does not restore",
                    )
                )
            else:
                kept.append(record)
        return kept

    return held, backup.model_copy(
        update={
            "projects": personal,
            "beats": keep(backup.beats, "beats"),
            "absences": keep(backup.absences, "absences"),
            "balance_adjustments": keep(backup.balance_adjustments, "balance_adjustments"),
        }
    )


async def _check_references(
    backup: _Backup,
    project_repo: ProjectRepository,
    client_repo: ClientRepository,
    beat_repo: BeatRepository,
) -> None:
    """Each billing's project and client, each override's beat and each
    billing budget's client or project must be one the file or the account
    holds: a 422 naming every one that is not, as a malformed record is,
    since the record cannot be restored as it is. The account is read only
    when the file has billing to check."""
    if not backup.project_billing and not backup.billable_overrides and not backup.billing_budgets:
        return
    stored = await project_repo.list(archived=False) + await project_repo.list(archived=True)
    projects = {p.id for p in [*stored, *backup.projects]}
    clients = {c.id for c in [*await client_repo.list_all(), *backup.clients]}
    beats = {b.id for b in backup.beats}
    errors: list[dict] = []

    def missing(loc: tuple[str | int, ...], what: str, value: str) -> None:
        errors.append(
            {
                "type": "not_found",
                "loc": loc,
                "msg": f"no {what} with this id in the backup or the account",
                "input": value,
            }
        )

    for i, billing in enumerate(backup.project_billing):
        if billing.project_id not in projects:
            missing(("project_billing", i, "project_id"), "project", billing.project_id)
        if billing.client_id not in clients:
            missing(("project_billing", i, "client_id"), "client", billing.client_id)
    for i, override in enumerate(backup.billable_overrides):
        if override.beat_id not in beats and not await beat_repo.exists(override.beat_id):
            missing(("billable_overrides", i, "beat_id"), "session", override.beat_id)
    for i, budget in enumerate(backup.billing_budgets):
        if budget.scope is BillingBudgetScope.CLIENT and budget.scope_id not in clients:
            missing(("billing_budgets", i, "scope_id"), "client", budget.scope_id)
        if budget.scope is BillingBudgetScope.PROJECT and budget.scope_id not in projects:
            missing(("billing_budgets", i, "scope_id"), "project", budget.scope_id)
    if errors:
        raise RequestValidationError(errors)


def _skip(
    collection: Literal["absences", "balance_adjustments"],
    record: Absence | BalanceAdjustment,
    exc: DomainException,
) -> ImportSkip:
    return ImportSkip(
        collection=collection,
        project_id=record.project_id,
        date=record.date,
        code=error_code(exc.status_code, exc.code),
        detail=exc.message,
    )


@router.post("/import", response_model=ImportResponse)
async def import_full_json(
    file: UploadFile,
    beat_repo: BeatRepoDep,
    project_repo: ProjectRepoDep,
    project_service: ProjectServiceDep,
    contract_service: ContractServiceDep,
    client_repo: ClientRepoDep,
    billing_service: BillingServiceDep,
    tz: TimezoneDep,
):
    """Import a full JSON backup, version 1.0 to 1.3, into the caller's
    account. Safe to re-import: projects, beats and clients are written by
    id, a project's billing replaces the one on its project, a billing
    budget the one on its scope and an override the one on its beat, and an
    absence or an adjustment replaces the one on its project and date, as
    its own route does. Nothing is deleted: the account's own budgets
    survive a file without them.

    The whole file is checked first, and a file that fails writes nothing:

    - a malformed record, a project's, a session's or a client's id
      included, is a 422 that names it;
    - a file holding a project, a session or a client whose id is another
      account's is a 409 `BACKUP_OF_ANOTHER_ACCOUNT`;
    - a billing whose project or client, an override whose session, or a
      billing budget whose client or project is in neither the file nor the
      account is a 422 that names it;
    - a client, a billing or a billing budget that its route would refuse,
      against the file over the account (a currency the API does not know,
      or one changed once priced or under a money budget; billing on a
      project that is not freelance, or a billed project moved away from
      freelance; billing moved to a client in another currency; a budget on
      a project billed nowhere), is that route's error, its detail naming
      the record. The retroactive gate is not applied: a restore puts back
      what was.

    Clients are written first, then projects as a project write is: the
    contract's checks, and the reconcile against the contract it replaces.
    A refusal there is that write's error and stops the import, with no
    transaction: the clients and the projects before it in the file stay
    written, and nothing after them is. Then each project's billing, the
    billing budgets, the beats and the overrides. Absences and adjustments go last, through their
    own routes' rules, against the projects as restored, and one those rules
    refuse (an absence on a project that is no longer a day job; an
    adjustment outside the contract's first day through today in `tz`) is
    left out and listed under `skipped` with the code its route would
    answer. Billing, budgets included, is never skipped: its rules ran
    before the first write."""
    try:
        backup = _Backup.model_validate_json(await file.read())
    except ValidationError as exc:
        raise RequestValidationError(exc.errors(include_url=False)) from None

    # An organisation's project in the file is restored only as the personal
    # half of one the account still sees — the organisation owns the rest —
    # and is otherwise left out with everything on it (docs/organisations.md,
    # *Backups*). Settled first, because such a project reads as another
    # account's to the ownership check below.
    skipped: list[ImportSkip] = []
    organisation_projects, backup = await _split_organisation_projects(
        backup, project_repo, skipped
    )

    # Every write is scoped to the caller, so a record of someone else's
    # would not move across but collide with theirs, partway through.
    foreign_projects = await project_repo.ids_held_elsewhere(
        p.id for p in backup.projects if p.id is not None
    )
    foreign_beats = await beat_repo.ids_held_elsewhere(
        b.id for b in backup.beats if b.id is not None
    )
    foreign_clients = await client_repo.ids_held_elsewhere(
        c.id for c in backup.clients if c.id is not None
    )
    if foreign_projects or foreign_beats or foreign_clients:
        raise BackupOfAnotherAccount(
            len(foreign_projects), len(foreign_beats), len(foreign_clients)
        )
    await _check_references(backup, project_repo, client_repo, beat_repo)
    await billing_service.check_restore(
        backup.projects,
        backup.clients,
        backup.project_billing,
        backup.billing_budgets,
        backup.beats,
        backup.billable_overrides,
        tz,
    )

    counts = ImportCounts(
        projects=0,
        beats=0,
        absences=0,
        balance_adjustments=0,
        clients=0,
        project_billing=0,
        billable_overrides=0,
        billing_budgets=0,
    )

    # Clients before the billing that names them; projects before their
    # billing too, so the kind guard reads the billing the account had.
    for client in backup.clients:
        await billing_service.restore_client(client)
        counts.clients += 1

    for project in backup.projects:
        await project_service.restore_project(project)
        counts.projects += 1

    # The personal half of an organisation project the account still holds:
    # the organisation's fields are read from what the organisation has, so
    # a rename since the backup is not undone, and the write is a project
    # write like any other.
    for project in organisation_projects:
        assert project.id is not None
        current = await project_repo.get_by_id(project.id)
        restored = current.model_copy(
            update={field: getattr(project, field) for field in PERSONAL_FIELDS}
        )
        await project_service.update_project(restored, previous_contract=current.contract)
        counts.projects += 1

    for billing in backup.project_billing:
        await billing_service.restore_project_billing(billing)
        counts.project_billing += 1

    # After the billing a project's budget needs, before the sessions.
    for budget in backup.billing_budgets:
        await billing_service.restore_billing_budget(budget)
        counts.billing_budgets += 1

    # A beat's stamp is never the file's. One the account already holds keeps
    # the stamp it has — so a backup from before a connect does not strip the
    # record, and one edited by hand cannot plant it. One new to the account
    # takes the stamp the project as it stands gives: an organisation's, and
    # started on or after the member's `shared_from` (decision 18).
    #
    # That is a stricter line than a live write keeps (`organisation_stamp`,
    # which withholds the stamp only before a *connected* project's
    # `private_before`), and deliberately so: a back-dated entry typed into
    # the app is the member's own late work on the organisation's project,
    # while a back-dated entry in a file is whatever the file says. The two
    # rules guard different things, so they are written twice on purpose.
    #
    # An approved month is closed to a file as it is to a route (decision
    # 23): a session dated inside one is left out and said so, and so is one
    # that would be moved out of an approved month by overwriting it. The
    # restore writes beats straight through `beat_repo.restore`, so the
    # check the member-side services make has to be made here too.
    owners: dict[str, Project | None] = {}

    async def _owner_of(project_id: str) -> Project | None:
        if project_id not in owners:
            try:
                owners[project_id] = await project_repo.get_by_id(project_id)
            except ProjectNotFound:
                owners[project_id] = None
        return owners[project_id]

    for beat in backup.beats:
        stored = None
        if beat.id is not None:
            try:
                stored = await beat_repo.get_by_id(beat.id)
            except BeatNotFound:
                stored = None
        project = await _owner_of(beat.project_id)
        try:
            if project is not None:
                await refuse_locked(contract_service.locks, project, beat.start)
            if stored is not None and stored.organisation_id is not None:
                held = await _owner_of(stored.project_id)
                if held is not None:
                    await refuse_locked(contract_service.locks, held, stored.start)
        except PeriodApproved as exc:
            skipped.append(
                ImportSkip(
                    collection="beats",
                    project_id=beat.project_id,
                    date=normalize_tz(beat.start).date(),
                    code=error_code(exc.status_code, exc.code),
                    detail=exc.message,
                )
            )
            continue
        if stored is not None:
            beat.organisation_id = stored.organisation_id
        else:
            owner = project.organisation if project is not None else None
            beat.organisation_id = (
                owner.id
                if owner is not None and normalize_tz(beat.start) >= normalize_tz(owner.shared_from)
                else None
            )
        await beat_repo.restore(beat)
        counts.beats += 1

    for override in backup.billable_overrides:
        await billing_service.restore_override(override)
        counts.billable_overrides += 1

    # The id is not the record's identity, its project and date are: the
    # write keeps the stored one's id, or makes a new one.
    for absence in backup.absences:
        try:
            await contract_service.record_absence(absence.model_copy(update={"id": None}))
        except DomainException as exc:
            skipped.append(_skip("absences", absence, exc))
        else:
            counts.absences += 1

    for adjustment in backup.balance_adjustments:
        try:
            await contract_service.record_adjustment(adjustment.model_copy(update={"id": None}), tz)
        except DomainException as exc:
            skipped.append(_skip("balance_adjustments", adjustment, exc))
        else:
            counts.balance_adjustments += 1

    return ImportResponse(status="ok", imported=counts, skipped=skipped)
