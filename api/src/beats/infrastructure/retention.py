"""The retention purge: what expiry of an organisation's record actually does.

The decided shape (docs/organisations.md, stage 4 — retention): expiry
removes **the organisation's record, not the person's data**. For each
organisation, every stamped row dated before the cutoff —
`retention_cutoff(today, effective_retention_years(…))`, the setting or the
country's floor, whichever keeps longer — is handled by whose it is:

- a **living member's** entries and absences lose the stamp and stay
  theirs (rule 1: the data is the person's; what expires is the
  organisation's right to read it);
- a **tombstoned ex-member's** rows (`erased:` user ids) are deleted —
  they existed only for the record;
- the organisation's **timesheets** for months wholly before the cutoff
  go, frozen figures with them, **decided absence requests** dated before
  it go (the absence is the record; the request was a note to a decider),
  and **audit events** older than the cutoff go too — the log lives as
  long as the records it explains;
- a **tombstone whose last row has expired** goes whole: the membership
  holding the name and address the organisation knew the person by, and
  the assignment holding the contract behind a balance it read. Those are
  the most personal data erasure leaves, and a period that never reached
  them would not be a period at all (#408).

The purge is run by the operator (`scripts/retention_purge.py`), dry by
default, and is itself an audit event per organisation — counts and the
cutoff, no data. Nothing schedules it: during the beta nothing
auto-deletes, and a stored setting nothing enforces is exactly what the
decision refused, which is why this module ships with the setting.
"""

from datetime import UTC, date, datetime
from typing import Any, NamedTuple

from pymongo.asynchronous.database import AsyncDatabase

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
        sheets = {"organisation_id": org_id, "month": {"$lt": cutoff.replace(day=1).isoformat()}}
        audit = {"organisation_id": org_id, "at": {"$lt": f"{day}T00:00:00"}}
        if apply:
            counts["timesheets_deleted"] = (
                await db.org_timesheets.delete_many(sheets)
            ).deleted_count
            counts["audit_deleted"] = (await db.org_audit.delete_many(audit)).deleted_count
        else:
            counts["timesheets_deleted"] = await db.org_timesheets.count_documents(sheets)
            counts["audit_deleted"] = await db.org_audit.count_documents(audit)

        # A decided absence request is spent: the absence it asked for is
        # the record, and the request carries a note addressed to a decider.
        # Decision 30 does not name them, so they expire on the same cutoff
        # as everything else they explain.
        requests = {
            "organisation_id": org_id,
            "decided_at": {"$ne": None},
            "date": {"$lt": day},
        }
        if apply:
            counts["absence_requests_deleted"] = (
                await db.org_absence_requests.delete_many(requests)
            ).deleted_count
        else:
            counts["absence_requests_deleted"] = await db.org_absence_requests.count_documents(
                requests
            )

        # What erasure kept of a deleted account goes once nothing of theirs
        # is left to explain: the tombstoned membership, which holds the name
        # and address the organisation knew them by, and their assignments,
        # which hold the contract behind a balance it read (decision 3).
        # These are the most personal data in the organisation, and until
        # #408 the purge kept them for ever.
        retained: dict[str, dict[str, Any]] = {
            "beats": {"organisation_id": org_id, "start": {"$gte": instant}},
            "absences": {"organisation_id": org_id, "date": {"$gte": day}},
            "adjustments": {"project_id": {"$in": project_ids}, "date": {"$gte": day}},
            "timesheets": {
                "organisation_id": org_id,
                "month": {"$gte": cutoff.replace(day=1).isoformat()},
            },
        }
        counts["tombstones_deleted"] = await _purge_spent_tombstones(
            db, org_id, project_ids, retained=retained, apply=apply
        )

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


async def _purge_spent_tombstones(
    db: AsyncDatabase,
    org_id: str,
    project_ids: list[str],
    *,
    retained: dict[str, dict[str, Any]],
    apply: bool,
) -> int:
    """Delete the memberships erasure left behind that explain nothing any
    more, with their assignments. How many went, applied or not.

    A tombstone (`erased:<membership id>`) exists only to group one former
    member's rows in the organisation's record. Once the last of those rows
    has expired — beats, absences, adjustments and timesheets alike — the
    membership is a name and an email address kept for a record that no
    longer exists, so it goes, and the assignment holding the contract
    behind a balance nobody can read goes with it. Until #408 the purge
    kept both for ever, which is the opposite of what the setting promises.

    A tombstone with one row still inside the period keeps everything: the
    record has to stay readable while any of it is owed. The test is for a
    *retained* row rather than for no row at all, so a dry run counts what
    an applied one would take, having deleted nothing yet.
    """
    gone = 0
    async for membership in db.org_members.find(
        {"organisation_id": org_id, "user_id": _TOMBSTONE}, {"user_id": 1}
    ):
        stone = membership["user_id"]
        owed = False
        for name, collection in (*member_row_collections(db), ("timesheets", db.org_timesheets)):
            if await collection.find_one({**retained[name], "user_id": stone}, {"_id": 1}):
                owed = True
                break
        if owed:
            continue
        gone += 1
        if apply:
            await db.org_assignments.delete_many({"organisation_id": org_id, "user_id": stone})
            await db.org_members.delete_one({"_id": membership["_id"]})
    return gone
