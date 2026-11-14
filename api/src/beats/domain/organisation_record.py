"""The organisation's record, as a shape and as an assembly.

The result types and the two reads that fill them — one month over a set
of projects, and one person's own archive of what they shared — split out
of `organisations.py` at the size ceiling (CLAUDE.md § Conventions). They take
the store and the record reader as arguments rather than a service, in
the same spirit as `ledger.py` and `timesheet.py`: the assembly is a
function of what it was given. Who may ask is still the service's
question (`OrganisationService.record`, `.visible`, `.archive`).
"""

import csv
import io
from datetime import date, datetime
from typing import NamedTuple
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from beats.domain.billing import utc_range
from beats.domain.contracts import balance_terms
from beats.domain.exceptions import (
    UnknownHolidayRegion,
)
from beats.domain.holidays import contract_holidays
from beats.domain.models import (
    Beat,
    MemberTotals,
    Organisation,
    OrgAssignment,
    OrgMembership,
    OrgProject,
)
from beats.domain.ports import (
    OrganisationAbsenceReader,
    OrganisationBeatReader,
    OrganisationRecords,
    OrganisationStore,
)
from beats.domain.retention import (
    effective_retention_years,
    retention_cutoff,
)
from beats.domain.services import worked_by_local_day
from beats.domain.timesheet import month_end
from beats.domain.utils import local_date, normalize_tz


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


def organisation_zone(organisation: Organisation) -> ZoneInfo:
    """The organisation's own timezone, UTC when it names one that is not
    a zone. Every reading of its record buckets days by this, never by the
    caller's (#415)."""
    try:
        return ZoneInfo(organisation.timezone)
    except ZoneInfoNotFoundError, ValueError:
        return ZoneInfo("UTC")


async def member_balance(
    records: OrganisationRecords,
    organisation_id: str,
    assignment: OrgAssignment,
    today: date,
    tz: ZoneInfo,
    expired_before: date,
) -> MemberBalance | None:
    contract = assignment.contract
    if contract is None or assignment.project_id is None:
        return None
    # A balance sums every hour since the contract began. On a connected
    # project with hours before the day the member chose to share from,
    # that sum would carry what rule 4 keeps back — so it is withheld,
    # and shown only when every entry and absence on the project is the
    # organisation's, where it equals the member's own figure. Rows the
    # retention purge unstamped are not withheld: they were shared once
    # and have only expired (#409).
    if await records.has_unshared(
        organisation_id,
        assignment.project_id,
        assignment.user_id,
        private_before=assignment.private_before,
        private_before_day=assignment.private_before_day,
        expired_before=expired_before,
    ):
        return None
    start = contract.starts_on
    beats = await records.beats_of_member(
        organisation_id, assignment.project_id, assignment.user_id
    )
    absences = [
        a
        for _, a in await records.absences_between(
            organisation_id, [assignment.project_id], start, today, user_id=assignment.user_id
        )
    ]
    adjustments = await records.adjustments_of_member(
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


async def assemble_record(
    store: OrganisationStore,
    records: OrganisationRecords,
    now: datetime,
    organisation: Organisation,
    projects: list[OrgProject],
    month: date,
    *,
    user_id: str | None,
) -> Record:
    """One month of the organisation's record over `projects`: per
    project, per member assigned (now or before), the finished entries
    started in the month in the organisation's timezone, the absences,
    the all-time totals and the balance of a contract if there is one.
    With `user_id`, that member's slice alone — the same queries,
    narrowed."""
    if organisation.id is None:
        raise ValueError("a stored organisation has an id")
    organisation_id = organisation.id
    tz = organisation_zone(organisation)
    today = local_date(now, tz)
    # The day the organisation's own retention reaches back to: a row
    # older than it has expired, which is why an unstamped one there
    # does not withhold a balance (#409).
    expired_before = retention_cutoff(
        today,
        effective_retention_years(organisation.retention_years, organisation.holiday_country),
    )
    first, last = month, month_end(month)
    start, end = utc_range(first, last, tz)
    project_ids = [p.id for p in projects]
    assignments = await store.list_assignments(organisation_id, user_id=user_id, active_only=False)
    members = {m.user_id: m for m in await store.list_members(organisation_id, active_only=False)}
    beats = await records.beats_between(organisation_id, project_ids, start, end, user_id=user_id)
    absences = await records.absences_between(
        organisation_id, project_ids, first, last, user_id=user_id
    )
    totals = await records.totals(organisation_id, project_ids, user_id=user_id)

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
                    balance=await member_balance(
                        records, organisation_id, a, today, tz, expired_before
                    ),
                    totals=totals.get(key, MemberTotals()),
                )
            )
        out.append(ProjectRecord(project, member_records))
    return Record(organisation, month, first, last, out)


async def assemble_archive(
    store: OrganisationStore,
    organisation: Organisation,
    membership: OrgMembership,
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
    own = await beats.list_for_organisation(organisation_id)
    days_off = await absences.list_for_organisation(organisation_id)
    project_ids = {b.project_id for b in own} | {a.project_id for a in days_off}
    names = await store.project_names(organisation_id, project_ids)
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
