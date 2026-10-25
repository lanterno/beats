"""Erasing an account (PRIVACY.md, *Export and deletion*; docs/organisations.md,
decision 3).

Deletion used to be total and simple: every document keyed to the user, in
every collection, gone. Organisations make one exception, and this module is
where it is drawn. An entry tracked on an organisation's project is that
organisation's working-time record, which an employer may be legally bound to
keep; it is stamped as such on the document itself (`organisation_id`), so the
question is answered per row without joining through anything that is itself
being deleted.

What survives, and in what shape:

- **Beats** stamped with an organisation: start, end, project and note. The
  tags go — they are derived from how the person worked, not what on
  (decision 1) — and `user_id` becomes a tombstone no account ever has.
- **Absences** stamped the same way: date, type, half day. The note goes.
- **Balance adjustments** on the organisation's projects: date, kind, hours.
  The note goes. They are kept because the balance the employer read is made
  of them.
- **The assignment**: the contract stays — the terms the hours were worked
  under are part of the record — and the personal goal and local repo paths
  go.
- **The membership**: the name and address the organisation knew the person
  by stay, as the employer's record; the membership ends with reason
  `erased`.
- **The audit log**, and every other column in the organisation that names
  the person — who created it, who made an invite, who assigned, who decided
  a request: the organisation's, so they stay; the id becomes the tombstone.

Everything else keyed to the user — personal projects and their beats, flow
windows, biometrics, the coach and its memory, clients and billing, devices,
credentials, the account — is deleted. The tombstone is `erased:<membership
id>`, one per organisation, so the organisation's record still groups one
former member's rows together and nothing else in the system can ever be
scoped to it.
"""

import logging
from datetime import UTC, datetime
from typing import Any, NamedTuple

from bson import ObjectId
from pymongo.asynchronous.database import AsyncDatabase

from beats.domain.models import MembershipEnd

logger = logging.getLogger(__name__)

# Personal fields on a retained row, by collection.
_BEAT_PERSONAL = ("tags",)
_ABSENCE_PERSONAL = ("note",)
_ADJUSTMENT_PERSONAL = ("note",)
_ASSIGNMENT_PERSONAL = ("weekly_goal", "goal_type", "goal_overrides", "autostart_repos")


class ErasureReport(NamedTuple):
    deleted: dict[str, int]  # collection -> documents deleted
    retained: dict[str, int]  # collection -> documents kept under a tombstone
    organisations: list[str]  # the organisations whose record kept rows


def tombstone(membership_id: str) -> str:
    return f"erased:{membership_id}"


async def erase_account(db: AsyncDatabase, user_id: str) -> ErasureReport:
    """Erase one account, keeping each organisation's working-time record.

    Not reversible. The organisation rows are rewritten first, so a crash
    midway leaves the record kept and the rest still to delete, never the
    reverse.
    """
    now = datetime.now(UTC).isoformat()
    retained: dict[str, int] = {}
    organisations: list[str] = []

    def keep(collection: str, count: int) -> None:
        if count:
            retained[collection] = retained.get(collection, 0) + count

    memberships = await db.org_members.find({"user_id": user_id}).to_list(length=None)
    for membership in memberships:
        org_id: str = membership["organisation_id"]
        stone = tombstone(str(membership["_id"]))
        organisations.append(org_id)

        project_ids = [
            a["project_id"]
            for a in await db.org_assignments.find(
                {"organisation_id": org_id, "user_id": user_id}, {"project_id": 1}
            ).to_list(length=None)
        ]

        beats = await db.timeLogs.update_many(
            {"user_id": user_id, "organisation_id": org_id},
            {"$set": {"user_id": stone}, "$unset": dict.fromkeys(_BEAT_PERSONAL, "")},
        )
        keep("timeLogs", beats.modified_count)

        absences = await db.absences.update_many(
            {"user_id": user_id, "organisation_id": org_id},
            {"$set": {"user_id": stone}, "$unset": dict.fromkeys(_ABSENCE_PERSONAL, "")},
        )
        keep("absences", absences.modified_count)

        if project_ids:
            adjustments = await db.balance_adjustments.update_many(
                {"user_id": user_id, "project_id": {"$in": project_ids}},
                {"$set": {"user_id": stone}, "$unset": dict.fromkeys(_ADJUSTMENT_PERSONAL, "")},
            )
            keep("balance_adjustments", adjustments.modified_count)

        # The timesheets are the employer's record of the approvals; the
        # absence requests are not — the absence itself is kept, the request
        # (whose note was addressed to a decider) goes with the account.
        sheets = await db.org_timesheets.update_many(
            {"organisation_id": org_id, "user_id": user_id}, {"$set": {"user_id": stone}}
        )
        keep("org_timesheets", sheets.modified_count)
        await db.org_timesheets.update_many(
            {"organisation_id": org_id, "decided_by": user_id}, {"$set": {"decided_by": stone}}
        )
        await db.org_absence_requests.update_many(
            {"organisation_id": org_id, "decided_by": user_id}, {"$set": {"decided_by": stone}}
        )
        await db.org_teams.update_many(
            {"organisation_id": org_id}, {"$pull": {"member_ids": user_id}}
        )

        assignments = await db.org_assignments.update_many(
            {"organisation_id": org_id, "user_id": user_id},
            [
                {
                    "$set": {
                        "user_id": stone,
                        "ended_at": {"$ifNull": ["$ended_at", now]},
                    }
                },
                {"$unset": list(_ASSIGNMENT_PERSONAL)},
            ],
        )
        keep("org_assignments", assignments.modified_count)

        await db.org_members.update_one(
            {"_id": membership["_id"]},
            [
                {
                    "$set": {
                        "user_id": stone,
                        "left_at": {"$ifNull": ["$left_at", now]},
                        "left_reason": {"$ifNull": ["$left_reason", MembershipEnd.ERASED.value]},
                    }
                }
            ],
        )
        keep("org_members", 1)

        # Every other column that names the person inside this organisation.
        await db.organisations.update_one(
            {"_id": ObjectId(org_id), "created_by": user_id}, {"$set": {"created_by": stone}}
        )
        await db.org_invites.update_many(
            {"organisation_id": org_id, "created_by": user_id}, {"$set": {"created_by": stone}}
        )
        await db.org_assignments.update_many(
            {"organisation_id": org_id, "assigned_by": user_id}, {"$set": {"assigned_by": stone}}
        )
        await db.org_join_requests.update_many(
            {"organisation_id": org_id, "decided_by": user_id}, {"$set": {"decided_by": stone}}
        )
        await db.org_audit.update_many(
            {"organisation_id": org_id, "actor_user_id": user_id},
            {"$set": {"actor_user_id": stone}},
        )
        await db.org_audit.update_many(
            {"organisation_id": org_id, "subject_user_id": user_id},
            {"$set": {"subject_user_id": stone}},
        )
        await db.org_audit.insert_one(
            {
                "organisation_id": org_id,
                "at": now,
                "actor_user_id": None,
                "event": "account.erased",
                "subject_user_id": stone,
                "project_id": None,
                "details": {},
            }
        )

    # Now everything else keyed to the user, in every collection there is.
    deleted: dict[str, int] = {}
    for name in await db.list_collection_names():
        result = await db[name].delete_many({"user_id": user_id})
        if result.deleted_count:
            deleted[name] = result.deleted_count
    # Join requests and invites name the person under other keys.
    requests = await db.org_join_requests.delete_many({"user_id": user_id})
    if requests.deleted_count:
        deleted["org_join_requests"] = deleted.get("org_join_requests", 0) + requests.deleted_count
    await db.org_invites.update_many({"accepted_by": user_id}, {"$unset": {"accepted_by": ""}})
    user: dict[str, Any] | None = None
    if ObjectId.is_valid(user_id):
        user = await db.users.find_one_and_delete({"_id": ObjectId(user_id)})
    if user is not None:
        deleted["users"] = 1
    logger.info(
        "erased account %s: deleted %s, retained %s for %s",
        user_id,
        deleted,
        retained,
        organisations,
    )
    return ErasureReport(deleted=deleted, retained=retained, organisations=organisations)
