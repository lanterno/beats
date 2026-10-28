"""The retention purge: what expiry of an organisation's record actually does.

The decided shape (docs/organisations.md, stage 4 — retention): expiry
removes **the organisation's record, not the person's data**. For each
organisation, every stamped row dated before the cutoff —
`retention_cutoff(today, retention_years)` — is handled by whose it is:

- a **living member's** entries and absences lose the stamp and stay
  theirs (rule 1: the data is the person's; what expires is the
  organisation's right to read it);
- a **tombstoned ex-member's** rows (`erased:` user ids) are deleted —
  they existed only for the record;
- the organisation's **timesheets** for months wholly before the cutoff
  go, frozen figures with them, and **audit events** older than the cutoff
  go too — the log lives as long as the records it explains.

The purge is run by the operator (`scripts/retention_purge.py`), dry by
default, and is itself an audit event per organisation — counts and the
cutoff, no data. Nothing schedules it: during the beta nothing
auto-deletes, and a stored setting nothing enforces is exactly what the
decision refused, which is why this module ships with the setting.
"""

from datetime import UTC, date, datetime
from typing import Any, NamedTuple

from pymongo.asynchronous.database import AsyncDatabase

from beats.domain.retention import retention_cutoff, retention_years

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
        years = retention_years(org.get("retention_years"))
        cutoff = retention_cutoff(today, years)
        # Beats store `start` as BSON datetimes (the beat repository's
        # dump_mode is "python"); absences, timesheet months and audit
        # instants are ISO strings. Each side gets the type it compares.
        day = cutoff.isoformat()
        instant = datetime(cutoff.year, cutoff.month, cutoff.day, tzinfo=UTC)
        counts: dict[str, int] = {}

        expired: list[tuple[str, Any, dict[str, Any], str]] = [
            # (action, collection, filter, mode) — tombstones delete, the living unstamp.
            (
                "beats_deleted",
                db.timeLogs,
                {"user_id": _TOMBSTONE, "start": {"$lt": instant}},
                "delete",
            ),
            (
                "absences_deleted",
                db.absences,
                {"user_id": _TOMBSTONE, "date": {"$lt": day}},
                "delete",
            ),
            (
                "adjustments_deleted",
                db.balance_adjustments,
                {"user_id": _TOMBSTONE, "date": {"$lt": day}},
                "delete",
            ),
            (
                "beats_unstamped",
                db.timeLogs,
                {"user_id": {"$not": _TOMBSTONE}, "start": {"$lt": instant}},
                "unstamp",
            ),
            (
                "absences_unstamped",
                db.absences,
                {"user_id": {"$not": _TOMBSTONE}, "date": {"$lt": day}},
                "unstamp",
            ),
        ]
        for action, collection, query, mode in expired:
            query = {"organisation_id": org_id, **query}
            if not apply:
                counts[action] = await collection.count_documents(query)
            elif mode == "delete":
                counts[action] = (await collection.delete_many(query)).deleted_count
            else:
                counts[action] = (
                    await collection.update_many(query, {"$unset": {"organisation_id": ""}})
                ).modified_count

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
