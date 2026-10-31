"""The retention purge: what expiry of an organisation's record actually does.

The decided shape (docs/organisations.md, stage 4 — retention): expiry
removes **the organisation's record, not the person's data**. For each
organisation, every stamped row dated before the cutoff —
`retention_cutoff(today, effective_retention_years)` — the setting, or the
default, never below the country's floor — is handled by whose it is:

- a **living member's** entries and absences lose the stamp and stay
  theirs (rule 1: the data is the person's; what expires is the
  organisation's right to read it);
- a **tombstoned ex-member's** rows (`erased:` user ids) are deleted —
  they existed only for the record;
- the organisation's **timesheets** for months wholly before the cutoff
  go, frozen figures with them, and **audit events** older than the cutoff
  go too — the log lives as long as the records it explains;
- a **tombstoned membership**, with the name and address the organisation
  knew the person by, and its assignments with the contract, go once no
  tombstoned entry, absence, adjustment or timesheet of that tombstone is
  left in the organisation (#408): they were kept to group the record, and
  with the record gone they are the most personal data left;
- **decided absence requests** dated before the cutoff go — a living
  member's too, since the request was only ever the organisation's.

The purge is run by the operator (`scripts/retention_purge.py`), dry by
default, and is itself an audit event per organisation — counts and the
cutoff, no data. Nothing schedules it: during the beta nothing
auto-deletes, and a stored setting nothing enforces is exactly what the
decision refused, which is why this module ships with the setting.
"""

from datetime import UTC, date, datetime
from typing import Any, NamedTuple

from pymongo.asynchronous.database import AsyncDatabase

from beats.domain.models import RequestStatus
from beats.domain.retention import effective_retention_years, retention_cutoff
from beats.infrastructure.organisations import member_row_collections

_TOMBSTONE = {"$regex": "^erased:"}


class OrganisationPurge(NamedTuple):
    organisation_id: str
    name: str
    years: int
    cutoff: date
    counts: dict[str, int]  # action -> rows


class PurgeReport(NamedTuple):
    today: date
    applied: bool
    organisations: list[OrganisationPurge]


async def purge_expired_records(
    db: AsyncDatabase, *, today: date | None = None, apply: bool = False
) -> PurgeReport:
    """One pass over every organisation. Dry by default: counts what would
    go without touching a row; with `apply`, deletes tombstoned rows first
    and unstamps living members' after, so a crash midway never leaves an
    ex-member's rows outliving a current member's stamp."""
    today = today or datetime.now(UTC).date()
    report: list[OrganisationPurge] = []

    async for org in db.organisations.find({}):
        org_id = str(org["_id"])
        years = effective_retention_years(org.get("retention_years"), org.get("holiday_country"))
        cutoff = retention_cutoff(today, years)
        # Beats store `start` as BSON datetimes (the beat repository's
        # dump_mode is "python"); absences, adjustments, timesheet months
        # and audit instants are ISO strings. Each gets the type it compares.
        day = cutoff.isoformat()
        instant = datetime(cutoff.year, cutoff.month, cutoff.day, tzinfo=UTC)
        counts: dict[str, int] = {}
        project_ids = [
            str(doc["_id"])
            async for doc in db.projects.find({"organisation_id": org_id}, {"_id": 1})
        ]

        # Adjustments carry no stamp — they are read by project and member —
        # so the organisation's are found through its projects, as erasure
        # finds them.
        expired: dict[str, dict[str, Any]] = {
            "beats": {"organisation_id": org_id, "start": {"$lt": instant}},
            "absences": {"organisation_id": org_id, "date": {"$lt": day}},
            "adjustments": {"project_id": {"$in": project_ids}, "date": {"$lt": day}},
        }

        # Tombstoned rows go first, living members' stamps after, so a crash
        # midway never leaves an ex-member's rows outliving a current
        # member's stamp.
        for name, collection in member_row_collections(db):
            query = {**expired[name], "user_id": _TOMBSTONE}
            counts[f"{name}_deleted"] = (
                (await collection.delete_many(query)).deleted_count
                if apply
                else await collection.count_documents(query)
            )
        for name, collection in member_row_collections(db):
            if name == "adjustments":
                continue  # stampless: nothing of a living member's to take back
            query = {**expired[name], "user_id": {"$not": _TOMBSTONE}}
            counts[f"{name}_unstamped"] = (
                (
                    await collection.update_many(query, {"$unset": {"organisation_id": ""}})
                ).modified_count
                if apply
                else await collection.count_documents(query)
            )

        # A sheet goes only when its whole month is out: the month holding
        # the cutoff still has retained days, so the comparison is against
        # the cutoff's own month start, not the cutoff day.
        month_start = cutoff.replace(day=1).isoformat()
        sheets = {"organisation_id": org_id, "month": {"$lt": month_start}}
        audit = {"organisation_id": org_id, "at": {"$lt": f"{day}T00:00:00"}}
        requests = {
            "organisation_id": org_id,
            "status": {"$ne": RequestStatus.PENDING.value},
            "date": {"$lt": day},
        }
        if apply:
            counts["timesheets_deleted"] = (
                await db.org_timesheets.delete_many(sheets)
            ).deleted_count
            counts["audit_deleted"] = (await db.org_audit.delete_many(audit)).deleted_count
            counts["absence_requests_deleted"] = (
                await db.org_absence_requests.delete_many(requests)
            ).deleted_count
        else:
            counts["timesheets_deleted"] = await db.org_timesheets.count_documents(sheets)
            counts["audit_deleted"] = await db.org_audit.count_documents(audit)
            counts["absence_requests_deleted"] = await db.org_absence_requests.count_documents(
                requests
            )

        # A tombstone goes once nothing of its record is left: the rows it
        # grouped are what justified keeping a name and an address. What is
        # left is read as "dated on or after the cutoff", which in a dry run
        # is what the purge would leave and after one is all there is.
        counts["memberships_deleted"] = 0
        counts["assignments_deleted"] = 0
        stones = await db.org_members.find(
            {"organisation_id": org_id, "user_id": _TOMBSTONE}, {"user_id": 1}
        ).to_list(length=None)
        for membership in stones:
            stone = membership["user_id"]
            left = (
                await db.timeLogs.count_documents(
                    {"organisation_id": org_id, "user_id": stone, "start": {"$gte": instant}}
                )
                + await db.absences.count_documents(
                    {"organisation_id": org_id, "user_id": stone, "date": {"$gte": day}}
                )
                + await db.balance_adjustments.count_documents(
                    {"project_id": {"$in": project_ids}, "user_id": stone, "date": {"$gte": day}}
                )
                + await db.org_timesheets.count_documents(
                    {"organisation_id": org_id, "user_id": stone, "month": {"$gte": month_start}}
                )
            )
            if left:
                continue
            its_assignments = {"organisation_id": org_id, "user_id": stone}
            if apply:
                counts["assignments_deleted"] += (
                    await db.org_assignments.delete_many(its_assignments)
                ).deleted_count
                counts["memberships_deleted"] += (
                    await db.org_members.delete_one({"_id": membership["_id"]})
                ).deleted_count
            else:
                counts["assignments_deleted"] += await db.org_assignments.count_documents(
                    its_assignments
                )
                counts["memberships_deleted"] += 1

        if apply and any(counts.values()):
            await db.org_audit.insert_one(
                {
                    "organisation_id": org_id,
                    "at": datetime.now(UTC).isoformat(),
                    "actor_user_id": None,
                    "event": "retention.purged",
                    "subject_user_id": None,
                    "project_id": None,
                    "details": {"cutoff": day, "years": years, **counts},
                }
            )
        report.append(OrganisationPurge(org_id, org.get("name", "?"), years, cutoff, counts))

    return PurgeReport(today=today, applied=apply, organisations=report)
