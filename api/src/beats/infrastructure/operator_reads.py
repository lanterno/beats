"""The operator's aggregates — `MongoOperatorReads`.

A named cross-tenant class in the shape of `MongoOrganisationRecords`: the one
other reader not scoped by `user_id`, never a widened `MongoStore._q`. Every
pipeline here returns ids, counts, dates, states and domains — the left-hand
column of docs/backoffice.md § The line — and the wall test in
`test_operator.py` plants a sentinel in everything on the right-hand column
and greps every response for it.

A pipeline per request is fine at this size (§ *What is deliberately not
here*): no pre-computed aggregates, and the account page's storage estimate
is computed for one account on that page only, never for a list.
"""

from datetime import UTC, datetime, timedelta
from urllib.parse import urlparse

from bson import ObjectId
from bson.errors import InvalidId
from pydantic import TypeAdapter
from pymongo.asynchronous.database import AsyncDatabase

from beats.operator.reads import (
    ABSENCE_REQUEST_ATTENTION_DAYS,
    ACCOUNT_COACH_SPEND_DAYS,
    COACH_CAP_ATTENTION_FRACTION,
    ERASURE_REQUEST_ATTENTION_DAYS,
    SIGNUP_BASELINE_WEEKS,
    SIGNUP_NETWORK_MIN_GROUP,
    SUPERSEDED_ATTENTION_DAYS,
    AbuseReport,
    AccountDetail,
    AccountFigure,
    AccountMatch,
    AttentionCounts,
    CapacityReport,
    CoachCostDay,
    CollectionSize,
    ControlState,
    DayFigure,
    DeviceSummary,
    DomainFigure,
    ErasureRequestState,
    MembershipSummary,
    OrganisationDetail,
    OrganisationSummary,
    OrgAuditRow,
    QueueKind,
    QueueRow,
    SignupWave,
    queue_due,
)
from beats.platform_controls import COLLECTION as CONTROLS_COLLECTION
from beats.platform_controls import PAUSES, SIGNUP_NETWORK_COUNTS, control_from_doc, hour_key

# The collections the storage estimate sums, each keyed on `user_id` and led
# by an index on it. What the account stores, never what it says.
USER_COLLECTIONS = (
    "projects",
    "timeLogs",
    "absences",
    "balance_adjustments",
    "clients",
    "project_billing",
    "billable_overrides",
    "billing_budgets",
    "report_links",
    "webhooks",
    "flow_windows",
    "signal_summaries",
    "biometric_days",
    "credentials",
    "device_registrations",
    "llm_usage",
    "coach_memory",
    "coach_conversations",
    "daily_briefs",
    "weekly_plans",
)

# Which integrations an account has connected — existence only, never a token
# or anything fetched through one.
INTEGRATION_COLLECTIONS = {
    "github": "github_integrations",
    "calendar": "calendar_integrations",
    "fitbit": "fitbit_integrations",
    "oura": "oura_integrations",
}

_TOP = 20


def _as_datetime(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None
    return None


def _as_date(value: object):
    dt = _as_datetime(value)
    if dt is not None:
        return dt.date()
    return None


def url_domain(url: str) -> str:
    """The destination a webhook posts to, as its host alone: the path and
    query are the owner's own business."""
    try:
        return urlparse(url).hostname or "(unparsable)"
    except ValueError:
        return "(unparsable)"


class MongoOperatorReads:
    def __init__(self, db: AsyncDatabase, *, coach_default_budget: float):
        self._db = db
        self._coach_default_budget = coach_default_budget

    # ── helpers ─────────────────────────────────────────────────────

    async def _owners_by_org(self) -> dict[str, list[str]]:
        """Active owner user ids per organisation."""
        cursor = self._db.org_members.find(
            {"role": "owner", "left_at": None}, projection=["organisation_id", "user_id"]
        )
        owners: dict[str, list[str]] = {}
        async for doc in cursor:
            owners.setdefault(doc["organisation_id"], []).append(doc["user_id"])
        return owners

    async def _suspended_of(self, user_ids: list[str]) -> set[str]:
        oids = []
        for uid in user_ids:
            try:
                oids.append(ObjectId(uid))
            except InvalidId:
                continue
        cursor = self._db.users.find(
            {"_id": {"$in": oids}, "suspended_at": {"$ne": None}}, projection=[]
        )
        return {str(doc["_id"]) async for doc in cursor}

    async def _coach_spend_by_user(self, since: datetime) -> dict[str, float]:
        pipeline = [
            {"$match": {"ts": {"$gte": since}}},
            {"$group": {"_id": "$user_id", "total": {"$sum": "$cost_usd"}}},
        ]
        cursor = await self._db.llm_usage.aggregate(pipeline)
        return {doc["_id"]: float(doc["total"]) async for doc in cursor}

    async def _coach_budgets(self) -> dict[str, float]:
        """Per-account coach ceilings where one is set."""
        cursor = self._db.account_limits.find(
            {"coach_monthly_budget_usd": {"$ne": None}},
            projection=["user_id", "coach_monthly_budget_usd"],
        )
        return {doc["user_id"]: float(doc["coach_monthly_budget_usd"]) async for doc in cursor}

    # ── the landing page ────────────────────────────────────────────

    async def attention(self) -> AttentionCounts:
        now = datetime.now(UTC)
        owners = await self._owners_by_org()
        org_ids = [str(doc["_id"]) async for doc in self._db.organisations.find({}, projection=[])]
        without_owner = sum(1 for org in org_ids if not owners.get(org))

        every_owner_user = sorted({uid for ids in owners.values() for uid in ids})
        suspended = await self._suspended_of(every_owner_user)
        all_suspended = sum(
            1 for org in org_ids if owners.get(org) and all(u in suspended for u in owners[org])
        )

        jobs_queued = await self._db.operator_jobs.count_documents({"state": "queued"})
        jobs_failed = await self._db.operator_jobs.count_documents({"state": "failed"})

        superseded_before = now - timedelta(days=SUPERSEDED_ATTENTION_DAYS)
        superseded = await self._db.org_timesheets.count_documents(
            {
                "status": "approved",
                "superseded_at": {"$ne": None, "$lt": superseded_before.isoformat()},
            }
        )

        pending_before = now - timedelta(days=ABSENCE_REQUEST_ATTENTION_DAYS)
        pending = await self._db.org_absence_requests.count_documents(
            {"status": "pending", "requested_at": {"$lt": pending_before.isoformat()}}
        )

        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        spend = await self._coach_spend_by_user(month_start)
        budgets = await self._coach_budgets()
        near_cap = 0
        for uid, spent in spend.items():
            budget = budgets.get(uid, self._coach_default_budget)
            if budget > 0 and spent >= COACH_CAP_ATTENTION_FRACTION * budget:
                near_cap += 1

        paused = sum(1 for c in await self._controls_in_force() if c.name in PAUSES)

        overdue_before = (now - timedelta(days=ERASURE_REQUEST_ATTENTION_DAYS)).date()
        erasure_overdue = sum(
            1
            for r in await self.erasure_requests()
            if r.status == "open" and r.received_on <= overdue_before
        )

        return AttentionCounts(
            organisations_without_owner=without_owner,
            controls_paused=paused,
            organisations_all_owners_suspended=all_suspended,
            jobs_queued=jobs_queued,
            jobs_failed=jobs_failed,
            approvals_superseded_over_30d=superseded,
            absence_requests_pending_over_14d=pending,
            accounts_near_coach_cap=near_cap,
            erasure_requests_overdue=erasure_overdue,
        )

    async def _controls_in_force(self):
        now = datetime.now(UTC)
        docs = await self._db[CONTROLS_COLLECTION].find({}, projection={"_id": False}).to_list()
        return [c for c in map(control_from_doc, docs) if c.in_force(now)]

    async def controls(self) -> list[ControlState]:
        """Every control document, in force or expired: an expired pause is
        open to the public API and still shown here as what it was, until
        it is cleared or set again."""
        now = datetime.now(UTC)
        docs = await self._db[CONTROLS_COLLECTION].find({}, projection={"_id": False}).to_list()
        return [
            ControlState(
                name=c.name,
                in_force=c.in_force(now),
                until=c.until,
                value=c.value,
                reason=c.reason,
                set_by=c.set_by,
                set_at=c.set_at,
            )
            for c in sorted(map(control_from_doc, docs), key=lambda c: c.name)
        ]

    async def erasure_requests(self) -> list[ErasureRequestState]:
        """Every logged request, newest first, with its state read off the
        job queue: an erasure queued or run for its account is a fact the
        queue holds, so the log never repeats it."""
        from beats.infrastructure.operator_store import MongoErasureRequests

        docs = await MongoErasureRequests(self._db).all()
        subjects = sorted({d["subject_id"] for d in docs if d.get("subject_id")})
        jobs: dict[str, str] = {}
        if subjects:
            cursor = self._db.operator_jobs.find(
                {"command": "account.erase", "subject_id": {"$in": subjects}},
                projection=["subject_id", "state"],
            )
            async for job in cursor:
                # done outranks a later queued one, queued outranks nothing
                state = jobs.get(job["subject_id"])
                if job["state"] == "done" or (
                    state is None and job["state"] in ("queued", "running")
                ):
                    jobs[job["subject_id"]] = job["state"]
        out = []
        for d in docs:
            if d.get("closed_at"):
                status = "closed"
            else:
                job_state = jobs.get(d.get("subject_id") or "")
                status = (
                    "erasure_ran"
                    if job_state == "done"
                    else "erasure_queued"
                    if job_state in ("queued", "running")
                    else "open"
                )
            received = _as_date(d.get("received_on"))
            if received is None:
                continue
            out.append(
                ErasureRequestState(
                    id=d["id"],
                    reference=str(d.get("reference", "")),
                    received_on=received,
                    subject_id=d.get("subject_id"),
                    status=status,
                    closed_at=_as_datetime(d.get("closed_at")),
                    closed_reason=d.get("closed_reason"),
                )
            )
        return out

    async def queue(self) -> list[QueueRow]:
        """The rows behind the Attention counts, soonest due first. Ids and
        dates only; a row is the condition itself, so nothing here is stored
        and a row leaves when its condition clears.

        Superseded approvals and pending absence requests are read whatever
        their age, so the queue can show them before they are due; they are
        grouped per organisation, with no member named."""
        now = datetime.now(UTC)
        rows: list[QueueRow] = []

        def row(kind: QueueKind, subject: str, since: datetime | None, count: int = 1) -> None:
            rows.append(QueueRow(kind, subject, since, queue_due(kind, since, now), count))

        owners = await self._owners_by_org()
        org_ids = [str(doc["_id"]) async for doc in self._db.organisations.find({}, projection=[])]
        suspended = await self._suspended_of(sorted({u for ids in owners.values() for u in ids}))
        for org in org_ids:
            if not owners.get(org):
                row("organisation_without_owner", org, None)
            elif all(u in suspended for u in owners[org]):
                row("organisation_all_owners_suspended", org, None)

        cursor = self._db.operator_jobs.find(
            {"state": {"$in": ["queued", "failed"]}},
            projection=["state", "run_after", "finished_at"],
        )
        async for doc in cursor:
            if doc["state"] == "failed":
                row("job_failed", str(doc["_id"]), _as_datetime(doc.get("finished_at")))
            else:
                row("job_queued", str(doc["_id"]), _as_datetime(doc.get("run_after")))

        for kind, collection, match, date_field in (
            (
                "approvals_superseded",
                "org_timesheets",
                {"status": "approved", "superseded_at": {"$ne": None}},
                "superseded_at",
            ),
            (
                "absence_requests_pending",
                "org_absence_requests",
                {"status": "pending"},
                "requested_at",
            ),
        ):
            grouped = await self._db[collection].aggregate(
                [
                    {"$match": match},
                    {
                        "$group": {
                            "_id": "$organisation_id",
                            "oldest": {"$min": f"${date_field}"},
                            "count": {"$sum": 1},
                        }
                    },
                ]
            )
            async for doc in grouped:
                row(kind, str(doc["_id"]), _as_datetime(doc["oldest"]), int(doc["count"]))

        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        spend = await self._coach_spend_by_user(month_start)
        budgets = await self._coach_budgets()
        for uid, spent in spend.items():
            budget = budgets.get(uid, self._coach_default_budget)
            if budget > 0 and spent >= COACH_CAP_ATTENTION_FRACTION * budget:
                row("account_near_coach_cap", uid, None)

        for control in await self._controls_in_force():
            if control.name in PAUSES:
                row("control_paused", control.name, control.until)

        for request in await self.erasure_requests():
            if request.status == "open":
                received = datetime.combine(request.received_on, datetime.min.time(), tzinfo=UTC)
                row("erasure_request_open", request.id, received)

        rows.sort(key=lambda r: r.due)
        return rows

    async def _completed_between(self, start: datetime, end: datetime) -> list[str]:
        """Ids of accounts created in the window that finished signing up —
        a credential or a provider identity — so abandoned starts do not
        inflate the figure. `created_at` is the model's JSON form."""
        bound = TypeAdapter(datetime)
        cursor = self._db.users.find(
            {
                "created_at": {
                    "$gte": bound.dump_python(start, mode="json"),
                    "$lt": bound.dump_python(end, mode="json"),
                }
            },
            projection=["identities"],
        )
        created = {str(d["_id"]): bool(d.get("identities")) async for d in cursor}
        if not created:
            return []
        with_credential = set(
            await self._db.credentials.distinct("user_id", {"user_id": {"$in": list(created)}})
        )
        return [uid for uid, sso in created.items() if sso or uid in with_credential]

    async def _signup_wave(self, now: datetime) -> SignupWave:
        """This hour against the median of the same hour of the week over
        the last weeks, and the largest network's share of the hour, shown
        only at or above the minimum group size."""
        start = now.replace(minute=0, second=0, microsecond=0)
        end = start + timedelta(hours=1)
        this_hour = await self._completed_between(start, end)
        same_hours = sorted(
            [
                len(
                    await self._completed_between(
                        start - timedelta(weeks=w), end - timedelta(weeks=w)
                    )
                )
                for w in range(1, SIGNUP_BASELINE_WEEKS + 1)
            ]
        )
        mid = len(same_hours) // 2
        usual = (
            float(same_hours[mid])
            if len(same_hours) % 2
            else (same_hours[mid - 1] + same_hours[mid]) / 2
        )
        with_writes = 0
        if this_hour:
            with_writes = len(
                await self._db.timeLogs.distinct("user_id", {"user_id": {"$in": this_hour}})
            )
        groups = (
            await self._db[SIGNUP_NETWORK_COUNTS]
            .find({"hour": hour_key(now)}, projection=["key", "completed"])
            .sort("completed", -1)
            .to_list()
        )
        largest = groups[0] if groups else None
        size = int(largest.get("completed", 0)) if largest else 0
        shown = largest is not None and size >= SIGNUP_NETWORK_MIN_GROUP
        return SignupWave(
            hour=hour_key(now),
            completed=len(this_hour),
            usual=usual,
            accounts_with_writes=with_writes,
            largest_group=size if shown else None,
            largest_key=str(largest["key"]) if shown and largest else None,
            groups=len(groups),
        )

    # ── the operator's own records ──────────────────────────────────

    async def _own_rows(
        self, collection: str, sort_field: str, limit: int, where: dict | None = None
    ) -> list[dict]:
        """operator_audit / operator_jobs, newest first. Only the control
        plane writes them, and it writes ids, never addresses or content
        (§ Jobs), so returning the documents whole is inside the line."""
        cursor = self._db[collection].find(where or {}).sort(sort_field, -1).limit(limit)
        out = []
        async for doc in cursor:
            doc["id"] = str(doc.pop("_id"))
            out.append(doc)
        return out

    async def audit_log(self, limit: int = 200, subject_id: str | None = None) -> list[dict]:
        """Every command the runner carried out, newest first, or only those
        against one subject — what the account and organisation pages ask
        for. `subject_id` is matched whole: it is an id the operator already
        holds, and a prefix match here would be a way to browse."""
        where = {} if subject_id is None else {"subject_id": subject_id}
        return await self._own_rows("operator_audit", "at", limit, where)

    async def jobs(self, limit: int = 200) -> list[dict]:
        return await self._own_rows("operator_jobs", "queued_at", limit)

    # ── accounts ────────────────────────────────────────────────────

    async def find_accounts(self, email: str) -> list[AccountMatch]:
        """Exact, but not case-sensitive: sign-up stores an address as typed
        under a unique index with no collation, so `Ana@` and `ana@` can be
        two accounts and a mail from either spelling must find both. The
        unique index can't serve this query, so it reads `users` whole —
        acceptable for the page it serves, never for a list."""
        cursor = self._db.users.find(
            {"email": email},
            projection=["email", "created_at", "last_seen_on", "suspended_at"],
            collation={"locale": "en", "strength": 2},
        )
        return [
            AccountMatch(
                id=str(doc["_id"]),
                email=doc.get("email", ""),
                created_at=_as_datetime(doc.get("created_at")),
                last_seen_on=_as_date(doc.get("last_seen_on")),
                suspended=doc.get("suspended_at") is not None,
            )
            async for doc in cursor
        ]

    async def account_coach_spend(
        self, user_id: str, days: int = ACCOUNT_COACH_SPEND_DAYS
    ) -> list[DayFigure]:
        """One account's coach cost a day, oldest first, for the page's bars.

        Only the days it spent something: a gap is a day with no call, and
        the page draws the calendar. The money is the platform's cost, which
        is operational metadata — what was said to the coach is not here and
        is not in `llm_usage` to begin with."""
        try:
            ObjectId(user_id)
        except InvalidId:
            return []
        since = datetime.now(UTC) - timedelta(days=days)
        pipeline = [
            {"$match": {"user_id": user_id, "ts": {"$gte": since}}},
            {
                "$group": {
                    "_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$ts"}},
                    "total": {"$sum": "$cost_usd"},
                }
            },
            {"$sort": {"_id": 1}},
        ]
        cursor = await self._db.llm_usage.aggregate(pipeline)
        return [DayFigure(day=d["_id"], value=round(float(d["total"]), 4)) async for d in cursor]

    async def account(self, user_id: str) -> AccountDetail | None:
        try:
            oid = ObjectId(user_id)
        except InvalidId:
            return None
        doc = await self._db.users.find_one(
            {"_id": oid},
            projection=[
                "email",
                "created_at",
                "last_seen_on",
                "suspended_at",
                "suspended_kind",
                "suspended_by",
                "sessions_valid_after",
                "identities.provider",
            ],
        )
        if doc is None:
            return None

        passkeys = await self._db.credentials.count_documents({"user_id": user_id})
        devices = [
            DeviceSummary(
                device_id=d.get("device_id", ""),
                created_at=_as_datetime(d.get("created_at")),
                last_seen=_as_datetime(d.get("last_seen")),
                revoked=bool(d.get("revoked", False)),
            )
            async for d in self._db.device_registrations.find(
                {"user_id": user_id},
                projection=["device_id", "created_at", "last_seen", "revoked"],
            )
        ]

        org_names = {
            str(o["_id"]): o.get("name", "")
            async for o in self._db.organisations.find({}, projection=["name"])
        }
        memberships = [
            MembershipSummary(
                organisation_id=m["organisation_id"],
                organisation_name=org_names.get(m["organisation_id"], ""),
                role=m.get("role", ""),
                active=m.get("left_at") is None,
            )
            async for m in self._db.org_members.find(
                {"user_id": user_id}, projection=["organisation_id", "role", "left_at"]
            )
        ]

        projects = await self._db.projects.count_documents({"user_id": user_id})
        sessions = await self._db.timeLogs.count_documents({"user_id": user_id})
        biometric_rows = await self._db.biometric_days.count_documents({"user_id": user_id})

        # The sum of $bsonSize over the account's documents, collection by
        # collection, each through the user_id index it leads with. Read on
        # this page only, for one account.
        storage = 0
        for name in USER_COLLECTIONS:
            pipeline = [
                {"$match": {"user_id": user_id}},
                {"$group": {"_id": None, "bytes": {"$sum": {"$bsonSize": "$$ROOT"}}}},
            ]
            cursor = await self._db[name].aggregate(pipeline)
            rows = await cursor.to_list(1)
            if rows:
                storage += int(rows[0]["bytes"])

        month_start = datetime.now(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        spend = (await self._coach_spend_by_user(month_start)).get(user_id, 0.0)
        limits = await self._db.account_limits.find_one({"user_id": user_id})
        budget = None
        if limits is not None and limits.get("coach_monthly_budget_usd") is not None:
            budget = float(limits["coach_monthly_budget_usd"])

        integrations = []
        for label, collection in INTEGRATION_COLLECTIONS.items():
            if await self._db[collection].count_documents({"user_id": user_id}, limit=1):
                integrations.append(label)

        return AccountDetail(
            id=user_id,
            email=doc.get("email", ""),
            created_at=_as_datetime(doc.get("created_at")),
            last_seen_on=_as_date(doc.get("last_seen_on")),
            suspended_at=_as_datetime(doc.get("suspended_at")),
            suspended_kind=doc.get("suspended_kind"),
            suspended_by=doc.get("suspended_by"),
            sessions_valid_after=_as_datetime(doc.get("sessions_valid_after")),
            passkeys=passkeys,
            sso_providers=[
                i.get("provider", "") for i in doc.get("identities", []) if isinstance(i, dict)
            ],
            devices=devices,
            organisations=memberships,
            projects=projects,
            sessions=sessions,
            biometric_rows=biometric_rows,
            storage_bytes=storage,
            coach_spend_usd=spend,
            coach_budget_usd=budget if budget is not None else self._coach_default_budget,
            integrations=integrations,
            limits_overridden=limits is not None,
        )

    # ── organisations ───────────────────────────────────────────────

    async def _summaries(self, match: dict | None = None) -> list[OrganisationSummary]:
        orgs = [
            doc
            async for doc in self._db.organisations.find(
                match or {}, projection=["name", "created_at", "retention_years", "closes_on"]
            )
        ]
        members: dict[str, dict[str, int]] = {}
        member_cursor = await self._db.org_members.aggregate(
            [
                {"$match": {"left_at": None}},
                {
                    "$group": {
                        "_id": {"org": "$organisation_id", "role": "$role"},
                        "n": {"$sum": 1},
                    }
                },
            ]
        )
        async for doc in member_cursor:
            members.setdefault(doc["_id"]["org"], {})[doc["_id"]["role"]] = doc["n"]
        assignments: dict[str, int] = {}
        assignment_cursor = await self._db.org_assignments.aggregate(
            [
                {"$match": {"ended_at": None}},
                {"$group": {"_id": "$organisation_id", "n": {"$sum": 1}}},
            ]
        )
        async for doc in assignment_cursor:
            assignments[doc["_id"]] = doc["n"]

        owners = await self._owners_by_org()
        every_owner = sorted({uid for ids in owners.values() for uid in ids})
        suspended = await self._suspended_of(every_owner)

        out = []
        for org in orgs:
            org_id = str(org["_id"])
            org_owners = owners.get(org_id, [])
            out.append(
                OrganisationSummary(
                    id=org_id,
                    name=org.get("name", ""),
                    created_at=_as_datetime(org.get("created_at")),
                    members_by_role=members.get(org_id, {}),
                    active_assignments=assignments.get(org_id, 0),
                    retention_years=org.get("retention_years"),
                    closes_on=_as_date(org.get("closes_on")),
                    owners=len(org_owners),
                    all_owners_suspended=bool(org_owners)
                    and all(u in suspended for u in org_owners),
                )
            )
        return out

    async def organisations(self) -> list[OrganisationSummary]:
        return await self._summaries()

    async def organisation(self, organisation_id: str) -> OrganisationDetail | None:
        try:
            match = {"_id": ObjectId(organisation_id)}
        except InvalidId:
            return None
        summaries = await self._summaries(match)
        if not summaries:
            return None
        projects = await self._db.projects.count_documents({"organisation_id": organisation_id})
        connected = len(
            await self._db.org_assignments.distinct(
                "project_id",
                {"organisation_id": organisation_id, "private_before": {"$ne": None}},
            )
        )
        by_status: dict[str, int] = {}
        status_cursor = await self._db.org_timesheets.aggregate(
            [
                {"$match": {"organisation_id": organisation_id}},
                {"$group": {"_id": "$status", "n": {"$sum": 1}}},
            ]
        )
        async for doc in status_cursor:
            by_status[doc["_id"]] = doc["n"]
        return OrganisationDetail(
            summary=summaries[0],
            projects=projects,
            connected_projects=connected,
            timesheets_by_status=by_status,
        )

    async def organisation_audit(self, organisation_id: str, limit: int = 200) -> list[OrgAuditRow]:
        """The log without each event's `details`, which carry what the
        organisation wrote — a reopen's reason, a project's or a team's
        name. The projection is the wall here, and the wall test plants a
        sentinel in a details field to hold it."""
        cursor = (
            self._db.org_audit.find(
                {"organisation_id": organisation_id},
                projection=[
                    "at",
                    "event",
                    "actor_user_id",
                    "actor_kind",
                    "subject_user_id",
                    "project_id",
                ],
            )
            .sort("at", -1)
            .limit(limit)
        )
        return [
            OrgAuditRow(
                at=_as_datetime(doc.get("at")) or datetime.now(UTC),
                event=doc.get("event", ""),
                actor_user_id=doc.get("actor_user_id"),
                actor_kind=doc.get("actor_kind")
                or ("member" if doc.get("actor_user_id") else "system"),
                subject_user_id=doc.get("subject_user_id"),
                project_id=doc.get("project_id"),
            )
            async for doc in cursor
        ]

    # ── abuse and capacity ──────────────────────────────────────────

    async def _top_counts(self, collection: str, match: dict) -> list[AccountFigure]:
        pipeline = [
            {"$match": match},
            {"$group": {"_id": "$user_id", "n": {"$sum": 1}}},
            {"$sort": {"n": -1}},
            {"$limit": _TOP},
        ]
        cursor = await self._db[collection].aggregate(pipeline)
        return [AccountFigure(user_id=str(d["_id"]), value=float(d["n"])) async for d in cursor]

    async def abuse(self) -> AbuseReport:
        now = datetime.now(UTC)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        today_start = datetime(now.year, now.month, now.day, tzinfo=UTC)

        spend = await self._coach_spend_by_user(month_start)
        top_spend = [
            AccountFigure(user_id=uid, value=round(v, 4))
            for uid, v in sorted(spend.items(), key=lambda kv: -kv[1])[:_TOP]
        ]

        # Webhook destinations by domain: the host alone, never the URL.
        domains: dict[str, int] = {}
        async for doc in self._db.webhooks.find({}, projection=["url"]):
            d = url_domain(doc.get("url", ""))
            domains[d] = domains.get(d, 0) + 1

        # Signups per day, last 90 days. created_at is stored as an ISO
        # string by the repository and as a BSON date by older rows, so the
        # bucketing is done here rather than in a pipeline that would choke
        # on the mixture. users is small at this platform's scale.
        signups: dict[str, int] = {}
        cutoff = now - timedelta(days=90)
        async for doc in self._db.users.find({}, projection=["created_at"]):
            created = _as_datetime(doc.get("created_at"))
            if created is None or created < cutoff:
                continue
            day = created.date().isoformat()
            signups[day] = signups.get(day, 0) + 1

        return AbuseReport(
            coach_spend_per_account=top_spend,
            flow_windows_per_account_today=await self._top_counts(
                "flow_windows", {"window_start": {"$gte": today_start.isoformat()}}
            ),
            sessions_created_7d_per_account=await self._top_counts(
                "timeLogs", {"start": {"$gte": now - timedelta(days=7)}}
            ),
            report_links_per_account=await self._top_counts("report_links", {}),
            webhook_domains=sorted(
                (DomainFigure(domain=d, value=n) for d, n in domains.items()),
                key=lambda f: -f.value,
            ),
            devices_per_account=await self._top_counts("device_registrations", {"revoked": False}),
            signups_per_day=[DayFigure(day=d, value=float(n)) for d, n in sorted(signups.items())],
            signup_wave=await self._signup_wave(now),
        )

    async def capacity(self) -> CapacityReport:
        collections = []
        for name in sorted(await self._db.list_collection_names()):
            cursor = await self._db[name].aggregate([{"$collStats": {"storageStats": {}}}])
            rows = await cursor.to_list(1)
            stats = rows[0].get("storageStats", {}) if rows else {}
            collections.append(
                CollectionSize(
                    name=name,
                    documents=int(stats.get("count", 0)),
                    storage_bytes=int(stats.get("storageSize", 0)),
                )
            )

        # The platform's coach cost by day and model, with what one account's
        # /api/coach/usage cannot say: the cache-hit ratio across everyone.
        pipeline = [
            {
                "$group": {
                    "_id": {
                        "day": {"$dateToString": {"format": "%Y-%m-%d", "date": "$ts"}},
                        "model": "$model",
                    },
                    "cost_usd": {"$sum": "$cost_usd"},
                    "input_tokens": {"$sum": "$input_tokens"},
                    "cache_read": {"$sum": "$cache_read_input_tokens"},
                    "calls": {"$sum": 1},
                }
            },
            {"$sort": {"_id.day": 1}},
        ]
        cursor = await self._db.llm_usage.aggregate(pipeline)
        coach_cost = [
            CoachCostDay(
                day=d["_id"]["day"],
                model=d["_id"]["model"],
                cost_usd=round(float(d["cost_usd"]), 4),
                input_tokens=int(d["input_tokens"]),
                cache_read_tokens=int(d["cache_read"]),
                calls=int(d["calls"]),
            )
            async for d in cursor
        ]
        return CapacityReport(collections=collections, coach_cost=coach_cost)
