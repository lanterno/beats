"""The operator's commands — small objects, so the audit can't be forgotten.

An audit each handler must remember to write will be missing from the one
action anybody cares about, so a mutation is never a function call in a
route: it is one of these, executed only by the runner
(roadmaps/backoffice.md § Commands are objects). **No rule lives here.**
Each command resolves ids, declares its confirmation, describes its subject
before and after, and delegates to whatever already owns the rule — the
account service, the device repository, the organisation service's operator
twins. A guard written here would disagree with the one the member-facing
route enforces.

A command with a `window` is destructive and enqueues instead of executing
(step 4's job runner); every command today needs the `operator` role — a
`viewer` runs none.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Protocol

from pydantic import BaseModel, Field
from pymongo.asynchronous.database import AsyncDatabase

from beats.domain.accounts import AccountService
from beats.domain.models import AccountLimits, SuspensionKind
from beats.domain.organisations import OrganisationService
from beats.infrastructure.repositories import MongoDeviceRegistrationRepository
from beats.operator.settings import OperatorIdentity


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
    # None: execute inline. Else: enqueue, run after the window (step 4).
    window: timedelta | None
    args_model: type[BaseModel]

    def subject_id(self, args: Any) -> str: ...
    async def confirmation(self, ctx: CommandContext, args: Any) -> str | None: ...
    async def describe(self, ctx: CommandContext, args: Any) -> dict[str, Any]: ...
    async def execute(self, ctx: CommandContext, args: Any) -> dict[str, Any]: ...


# ── accounts ─────────────────────────────────────────────────────────


class AccountArgs(BaseModel):
    user_id: str = Field(min_length=1, max_length=64)


class SuspendArgs(AccountArgs):
    # Erasure suspensions belong to the erasure job (step 4), never to this
    # command: job.cancel lifts only that kind.
    kind: SuspensionKind = SuspensionKind.ABUSE
    reason: str = Field(min_length=1, max_length=2000)


async def _account_email(ctx: CommandContext, user_id: str) -> str | None:
    """The typed confirmation for an account command. Compared, never
    stored: operator_audit holds ids, and the audit outlives the account."""
    user = await ctx.accounts.find(user_id)
    return user.email if user else None


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


class UnsuspendAccount(_AccountCommand):
    name = "account.unsuspend"

    async def execute(self, ctx: CommandContext, args: AccountArgs) -> dict[str, Any]:
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


async def _organisation_name(ctx: CommandContext, organisation_id: str) -> str | None:
    org = await ctx.organisations.store.get_organisation(organisation_id)
    return org.name if org else None


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
        GrantOwner(),
        BeginClosing(),
        CancelClosing(),
    )
}
