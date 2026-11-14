"""The operator's commands — small objects, so the audit can't be forgotten.

An audit each handler must remember to write will be missing from the one
action anybody cares about, so a mutation is never a function call in a
route: it is one of these, executed only by the runner
(docs/backoffice.md § Commands). **No rule lives here.**
Each command resolves ids, declares its confirmation, describes its subject
before and after, and delegates to whatever already owns the rule — the
account service, the device repository, the organisation service's operator
twins. A guard written here would disagree with the one the member-facing
route enforces.

A command with a `window` is destructive and enqueues instead of executing
(the job runner); every command today needs the `operator` role — a
`viewer` runs none.
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field, model_validator
from pymongo.asynchronous.database import AsyncDatabase

from beats.domain.accounts import ERASURE_WINDOW_DAYS, AccountNotFound, AccountService
from beats.domain.exceptions import DomainException, OrganisationNotFound
from beats.domain.models import AccountLimits, SuspensionKind
from beats.domain.organisations import OrganisationService
from beats.infrastructure.operator_store import MongoPlatformControlsStore
from beats.infrastructure.repositories import MongoDeviceRegistrationRepository
from beats.operator.settings import OperatorIdentity
from beats.platform_controls import LIMITS, MAX_PAUSE, ControlName, control_from_doc


@dataclass
class CommandContext:
    operator: OperatorIdentity
    db: AsyncDatabase
    accounts: AccountService
    organisations: OrganisationService
    devices: MongoDeviceRegistrationRepository


class OperatorCommand(Protocol):
    name: str
    subject_kind: str
    # None: execute inline. Else: enqueue, run after the window.
    window: timedelta | None
    args_model: type[BaseModel]

    def subject_id(self, args: Any) -> str: ...
    async def confirmation(self, ctx: CommandContext, args: Any) -> str | None: ...
    async def describe(self, ctx: CommandContext, args: Any) -> dict[str, Any]: ...
    async def execute(self, ctx: CommandContext, args: Any) -> dict[str, Any]: ...
    # What queueing itself does, for a windowed command: an erasure suspends
    # the account the moment it is queued, so the window is visible to the
    # person whose address may have been impersonated.
    async def on_queued(self, ctx: CommandContext, args: Any) -> None: ...


# ── accounts ─────────────────────────────────────────────────────────


class AccountArgs(BaseModel):
    user_id: str = Field(min_length=1, max_length=64)


class SuspendArgs(AccountArgs):
    # Erasure suspensions belong to the erasure job, never to this command:
    # the erasure wording falsely promises a deletion date, and job.cancel
    # lifts only that kind. Literal, so "erasure" is refused at validation.
    kind: Literal[SuspensionKind.ABUSE, SuspensionKind.OTHER] = SuspensionKind.ABUSE
    reason: str = Field(min_length=1, max_length=2000)


async def _account_email(ctx: CommandContext, user_id: str) -> str:
    """The typed confirmation for an account command. Compared, never
    stored: operator_audit holds ids, and the audit outlives the account.
    A subject that doesn't resolve is a refusal here, at queue time — never
    a waived confirmation: the check's whole purpose is proving the operator
    is acting on the thing they think they are, and a mistyped id is the
    case it exists for."""
    user = await ctx.accounts.find(user_id)
    if user is None:
        raise AccountNotFound()
    return user.email


async def _suspension_state(ctx: CommandContext, user_id: str) -> dict[str, Any]:
    user = await ctx.accounts.find(user_id)
    if user is None:
        return {"exists": False}
    return {
        "suspended": user.suspended,
        "suspended_kind": user.suspended_kind.value if user.suspended_kind else None,
        "sessions_valid_after": user.sessions_valid_after.isoformat()
        if user.sessions_valid_after
        else None,
    }


class _AccountCommand:
    subject_kind = "account"
    window: timedelta | None = None
    args_model: type[BaseModel] = AccountArgs

    def subject_id(self, args: Any) -> str:
        return args.user_id

    async def confirmation(self, ctx: CommandContext, args: Any) -> str | None:
        return None

    async def describe(self, ctx: CommandContext, args: Any) -> dict[str, Any]:
        return await _suspension_state(ctx, args.user_id)

    async def execute(self, ctx: CommandContext, args: Any) -> dict[str, Any]:
        raise NotImplementedError

    async def on_queued(self, ctx: CommandContext, args: Any) -> None:
        return None


class SuspendAccount(_AccountCommand):
    name = "account.suspend"
    args_model = SuspendArgs

    async def confirmation(self, ctx: CommandContext, args: SuspendArgs) -> str | None:
        return await _account_email(ctx, args.user_id)

    async def execute(self, ctx: CommandContext, args: SuspendArgs) -> dict[str, Any]:
        await ctx.accounts.suspend(
            args.user_id, kind=args.kind, reason=args.reason, by=ctx.operator.sub
        )
        return await _suspension_state(ctx, args.user_id)


class ErasureQueued(DomainException):
    """An account with a queued erasure is unsuspended only by cancelling the
    erasure (`job.cancel`, which lifts the suspension itself): unsuspending
    around it would leave the account working normally, showing none of the
    window's warning, and still erased on schedule. A control-plane rule, so
    it lives with the control plane's own state rather than in
    AccountService, which knows nothing of jobs."""

    status_code = 409
    message = "An erasure is queued for this account; cancel the job instead"
    code = "ERASURE_QUEUED"


class UnsuspendAccount(_AccountCommand):
    name = "account.unsuspend"

    async def execute(self, ctx: CommandContext, args: AccountArgs) -> dict[str, Any]:
        from beats.infrastructure.operator_jobs import MongoOperatorJobs

        if await MongoOperatorJobs(ctx.db).find_queued("account.erase", args.user_id):
            raise ErasureQueued()
        await ctx.accounts.unsuspend(args.user_id)
        return await _suspension_state(ctx, args.user_id)


class SignOutEverywhere(_AccountCommand):
    name = "account.sign_out_everywhere"

    async def execute(self, ctx: CommandContext, args: AccountArgs) -> dict[str, Any]:
        await ctx.accounts.sign_out_everywhere(args.user_id)
        return await _suspension_state(ctx, args.user_id)


class SetLimitsArgs(AccountArgs):
    coach_monthly_budget_usd: float | None = None
    writes_per_minute_beats: int | None = Field(default=None, ge=1)
    writes_per_minute_signals: int | None = Field(default=None, ge=1)
    imports_per_hour: int | None = Field(default=None, ge=1)
    webhooks_disabled: bool = False


async def _limits_state(ctx: CommandContext, user_id: str) -> dict[str, Any]:
    doc = await ctx.db.account_limits.find_one({"user_id": user_id})
    if doc is None:
        return {"overridden": False}
    doc.pop("_id", None)
    doc.pop("user_id", None)
    return {"overridden": True, **doc}


class SetLimits(_AccountCommand):
    name = "account.set_limits"
    args_model = SetLimitsArgs

    async def describe(self, ctx: CommandContext, args: SetLimitsArgs) -> dict[str, Any]:
        return await _limits_state(ctx, args.user_id)

    async def execute(self, ctx: CommandContext, args: SetLimitsArgs) -> dict[str, Any]:
        await ctx.accounts.set_limits(
            AccountLimits(
                user_id=args.user_id,
                coach_monthly_budget_usd=args.coach_monthly_budget_usd,
                writes_per_minute_beats=args.writes_per_minute_beats,
                writes_per_minute_signals=args.writes_per_minute_signals,
                imports_per_hour=args.imports_per_hour,
                webhooks_disabled=args.webhooks_disabled,
                set_by=ctx.operator.sub,
            )
        )
        return await _limits_state(ctx, args.user_id)


class ClearLimits(_AccountCommand):
    name = "account.clear_limits"

    async def describe(self, ctx: CommandContext, args: AccountArgs) -> dict[str, Any]:
        return await _limits_state(ctx, args.user_id)

    async def execute(self, ctx: CommandContext, args: AccountArgs) -> dict[str, Any]:
        await ctx.accounts.clear_limits(args.user_id)
        return await _limits_state(ctx, args.user_id)


class RevokeDeviceArgs(AccountArgs):
    device_id: str = Field(min_length=1, max_length=64)


class RevokeDevice(_AccountCommand):
    """The narrow answer to one broken daemon or one stolen laptop:
    revocation ends one device; sign-out ends sessions; suspension ends
    both. The public API's instances see it when their device-cache entry
    expires (30 seconds) — the operator deployment cannot drop it, and
    doesn't need to."""

    name = "device.revoke"
    args_model = RevokeDeviceArgs

    async def describe(self, ctx: CommandContext, args: RevokeDeviceArgs) -> dict[str, Any]:
        reg = await ctx.devices.get_by_device_id(args.device_id)
        return {"device_id": args.device_id, "revoked": reg.revoked if reg else None}

    async def execute(self, ctx: CommandContext, args: RevokeDeviceArgs) -> dict[str, Any]:
        revoked = await ctx.devices.revoke(args.device_id, args.user_id)
        return {"device_id": args.device_id, "revoked": bool(revoked) or None}


# ── organisations ────────────────────────────────────────────────────


class OrganisationArgs(BaseModel):
    organisation_id: str = Field(min_length=1, max_length=64)


async def _organisation_name(ctx: CommandContext, organisation_id: str) -> str:
    """Resolves or refuses, like _account_email: an unknown organisation is a
    404 at queue time, never a waived confirmation."""
    org = await ctx.organisations.store.get_organisation(organisation_id)
    if org is None:
        raise OrganisationNotFound()
    return org.name


async def _organisation_state(ctx: CommandContext, organisation_id: str) -> dict[str, Any]:
    org = await ctx.organisations.store.get_organisation(organisation_id)
    if org is None:
        return {"exists": False}
    return {
        "owners": await ctx.organisations.store.count_owners(organisation_id),
        "closes_on": org.closes_on.isoformat() if org.closes_on else None,
    }


class _OrganisationCommand:
    subject_kind = "organisation"
    window: timedelta | None = None
    args_model: type[BaseModel] = OrganisationArgs

    def subject_id(self, args: Any) -> str:
        return args.organisation_id

    async def confirmation(self, ctx: CommandContext, args: Any) -> str | None:
        return await _organisation_name(ctx, args.organisation_id)

    async def describe(self, ctx: CommandContext, args: Any) -> dict[str, Any]:
        return await _organisation_state(ctx, args.organisation_id)

    async def execute(self, ctx: CommandContext, args: Any) -> dict[str, Any]:
        raise NotImplementedError

    async def on_queued(self, ctx: CommandContext, args: Any) -> None:
        return None


class GrantOwnerArgs(OrganisationArgs):
    user_id: str = Field(min_length=1, max_length=64)


class GrantOwner(_OrganisationCommand):
    name = "organisation.grant_owner"
    args_model = GrantOwnerArgs

    async def execute(self, ctx: CommandContext, args: GrantOwnerArgs) -> dict[str, Any]:
        updated = await ctx.organisations.operator_grant_owner(args.organisation_id, args.user_id)
        state = await _organisation_state(ctx, args.organisation_id)
        return {**state, "granted_to": args.user_id, "role": updated.role.value}


class BeginClosingArgs(OrganisationArgs):
    closes_on: date | None = None


class BeginClosing(_OrganisationCommand):
    name = "organisation.begin_closing"
    args_model = BeginClosingArgs

    async def execute(self, ctx: CommandContext, args: BeginClosingArgs) -> dict[str, Any]:
        await ctx.organisations.operator_begin_closing(args.organisation_id, args.closes_on)
        return await _organisation_state(ctx, args.organisation_id)


class CancelClosing(_OrganisationCommand):
    name = "organisation.cancel_closing"

    async def confirmation(self, ctx: CommandContext, args: OrganisationArgs) -> str | None:
        return None

    async def execute(self, ctx: CommandContext, args: OrganisationArgs) -> dict[str, Any]:
        await ctx.organisations.operator_cancel_closing(args.organisation_id)
        return await _organisation_state(ctx, args.organisation_id)


# ── the platform's switches and limits ───────────────────────────────


class ControlArgs(BaseModel):
    name: ControlName


class SetControlArgs(ControlArgs):
    """A pause needs `until` (inside MAX_PAUSE) and a `reason` for the
    operator's own page; a limit needs a `value` and takes neither. `signups`
    may carry a `value` too — a ceiling an hour — and is then slowed rather
    than paused, until `until`. The sentence a user sees is fixed text; the
    reason never reaches them."""

    until: datetime | None = None
    value: int | None = Field(default=None, ge=1)
    reason: str | None = Field(default=None, min_length=1, max_length=2000)

    @model_validator(mode="after")
    def _shape(self) -> SetControlArgs:
        if self.name in LIMITS:
            if self.value is None:
                raise ValueError("a limit needs a value")
            if self.until is not None or self.reason is not None:
                raise ValueError("a limit is a setting: it takes no until and no reason")
            return self
        if self.until is None:
            raise ValueError("a pause needs an until: every pause expires")
        if self.reason is None:
            raise ValueError("a pause needs a reason, for your own record")
        now = datetime.now(UTC)
        until = self.until if self.until.tzinfo else self.until.replace(tzinfo=UTC)
        if until <= now:
            raise ValueError("until is already past")
        if until > now + MAX_PAUSE:
            raise ValueError(f"a pause lasts at most {MAX_PAUSE.days} days; set it again after")
        if self.value is not None and self.name != "signups":
            raise ValueError("only signups can be slowed to a value; the rest pause")
        self.until = until
        return self


async def _control_state(ctx: CommandContext, name: str) -> dict[str, Any]:
    doc = await MongoPlatformControlsStore(ctx.db).get(name)
    if doc is None:
        return {"set": False}
    control = control_from_doc(doc)
    return {
        "set": True,
        "in_force": control.in_force(datetime.now(UTC)),
        "until": control.until.isoformat() if control.until else None,
        "value": control.value,
        "set_by": control.set_by,
    }


class _ControlCommand:
    """Inline, no window, no typed confirmation: a switch is thrown in an
    incident and is reversible by the twin command."""

    subject_kind = "control"
    window: timedelta | None = None
    args_model: type[BaseModel] = ControlArgs

    def subject_id(self, args: Any) -> str:
        return args.name

    async def confirmation(self, ctx: CommandContext, args: Any) -> str | None:
        return None

    async def describe(self, ctx: CommandContext, args: Any) -> dict[str, Any]:
        return await _control_state(ctx, args.name)

    async def execute(self, ctx: CommandContext, args: Any) -> dict[str, Any]:
        raise NotImplementedError

    async def on_queued(self, ctx: CommandContext, args: Any) -> None:
        return None


class SetControl(_ControlCommand):
    name = "control.set"
    args_model = SetControlArgs

    async def execute(self, ctx: CommandContext, args: SetControlArgs) -> dict[str, Any]:
        await MongoPlatformControlsStore(ctx.db).set(
            args.name,
            until=args.until,
            value=args.value,
            reason=args.reason,
            set_by=ctx.operator.sub,
        )
        return await _control_state(ctx, args.name)


class ClearControl(_ControlCommand):
    name = "control.clear"

    async def execute(self, ctx: CommandContext, args: ControlArgs) -> dict[str, Any]:
        await MongoPlatformControlsStore(ctx.db).clear(args.name)
        return await _control_state(ctx, args.name)


# ── the irreversible work: jobs with a window ────────────────────────


class EraseAccount(_AccountCommand):
    """Queued with a 7-day window — the operator's second thoughts and the
    person's. Queueing suspends the account with the erasure's own wording,
    which names the day the window ends, so an account holder whose address
    was impersonated in a deletion mail finds out the moment they next open
    the app. Its rules run when it runs: erase_account tombstones before it
    deletes, so a re-run after a death midway is safe."""

    name = "account.erase"
    window: timedelta | None = timedelta(days=ERASURE_WINDOW_DAYS)

    async def confirmation(self, ctx: CommandContext, args: Any) -> str | None:
        return await _account_email(ctx, args.user_id)

    async def on_queued(self, ctx: CommandContext, args: Any) -> None:
        # Only an account not already suspended: an abuse suspension must
        # keep its kind, or cancelling the erasure (which lifts only the
        # erasure's kind) would open the abuse door. The already-suspended
        # person is refused either way; they just keep the stricter wording.
        user = await ctx.accounts.find(args.user_id)
        if user is not None and user.suspended:
            return
        await ctx.accounts.suspend(
            args.user_id,
            kind=SuspensionKind.ERASURE,
            reason="erasure queued",
            by=ctx.operator.sub,
        )

    async def execute(self, ctx: CommandContext, args: Any) -> dict[str, Any]:
        from beats.infrastructure.erasure import erase_account

        report = await erase_account(ctx.db, args.user_id, actor_kind="operator")
        return {
            "deleted": sum(report.deleted.values()),
            "retained": sum(report.retained.values()),
        }


class DeleteOrganisation(_OrganisationCommand):
    """Queued with a 1-day window. The notice was the request, so no second
    one is needed; the twin's rules run when the job does, so an organisation
    given an owner while it waited is refused then."""

    name = "organisation.delete"
    window: timedelta | None = timedelta(days=1)

    async def execute(self, ctx: CommandContext, args: Any) -> dict[str, Any]:
        counts = await ctx.organisations.operator_delete_organisation(args.organisation_id)
        return dict(counts)


class RetentionPurgeArgs(BaseModel):
    # None purges every organisation; the confirmation is then the word
    # "all", typed.
    organisation_id: str | None = Field(default=None, max_length=64)


class RetentionPurge:
    """Still an act the operator starts, never scheduled (decision 30 —
    PRIVACY.md and the DPA both promise it); now from a page rather than a
    shell, with a day to think."""

    name = "retention.purge"
    subject_kind = "organisation"
    window: timedelta | None = timedelta(days=1)
    args_model: type[BaseModel] = RetentionPurgeArgs

    def subject_id(self, args: Any) -> str:
        return args.organisation_id or "all"

    async def confirmation(self, ctx: CommandContext, args: Any) -> str | None:
        if args.organisation_id is None:
            return "all"
        return await _organisation_name(ctx, args.organisation_id)

    async def describe(self, ctx: CommandContext, args: Any) -> dict[str, Any]:
        from beats.infrastructure.retention import purge_expired_records

        report = await purge_expired_records(
            ctx.db, apply=False, organisation_id=args.organisation_id
        )
        return {"would_touch_organisations": len(report.organisations)}

    async def execute(self, ctx: CommandContext, args: Any) -> dict[str, Any]:
        from beats.infrastructure.retention import purge_expired_records

        report = await purge_expired_records(
            ctx.db, apply=True, actor_kind="operator", organisation_id=args.organisation_id
        )
        return {"purged_organisations": len(report.organisations)}

    async def on_queued(self, ctx: CommandContext, args: Any) -> None:
        return None


class JobNotFound(DomainException):
    status_code = 404
    message = "No queued job with that id"
    code = "JOB_NOT_FOUND"


class CancelJobArgs(BaseModel):
    job_id: str = Field(min_length=1, max_length=64)


class CancelJob:
    """Second thoughts inside the window. Cancelling an erasure lifts the
    suspension the queueing placed — and only that kind: a suspension for
    abuse is not lifted by cancelling an erasure."""

    name = "job.cancel"
    subject_kind = "job"
    window: timedelta | None = None
    args_model: type[BaseModel] = CancelJobArgs

    def subject_id(self, args: Any) -> str:
        return args.job_id

    async def confirmation(self, ctx: CommandContext, args: Any) -> str | None:
        return None

    async def describe(self, ctx: CommandContext, args: Any) -> dict[str, Any]:
        from beats.infrastructure.operator_jobs import MongoOperatorJobs

        job = await MongoOperatorJobs(ctx.db).get(args.job_id)
        if job is None:
            raise JobNotFound()
        return {"command": job["command"], "state": job["state"]}

    async def execute(self, ctx: CommandContext, args: Any) -> dict[str, Any]:
        from beats.infrastructure.operator_jobs import MongoOperatorJobs

        jobs = MongoOperatorJobs(ctx.db)
        cancelled = await jobs.cancel(args.job_id)
        if cancelled is None:
            job = await jobs.get(args.job_id)
            if job is None:
                raise JobNotFound()
            return {"command": job["command"], "state": job["state"], "cancelled": False}
        if cancelled["command"] == "account.erase":
            user = await ctx.accounts.find(cancelled["subject_id"])
            if user is not None and user.suspended_kind is SuspensionKind.ERASURE:
                await ctx.accounts.unsuspend(cancelled["subject_id"])
        return {"command": cancelled["command"], "state": "cancelled", "cancelled": True}

    async def on_queued(self, ctx: CommandContext, args: Any) -> None:
        return None


# The runner resolves names here and nowhere else: the registry is the one
# list of what an operator can do, so a command absent from it does not
# exist.
COMMANDS: dict[str, OperatorCommand] = {
    command.name: command
    for command in (
        SuspendAccount(),
        UnsuspendAccount(),
        SignOutEverywhere(),
        SetLimits(),
        ClearLimits(),
        RevokeDevice(),
        SetControl(),
        ClearControl(),
        GrantOwner(),
        BeginClosing(),
        CancelClosing(),
        EraseAccount(),
        DeleteOrganisation(),
        RetentionPurge(),
        CancelJob(),
    )
}
