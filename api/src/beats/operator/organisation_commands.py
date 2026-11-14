"""The operator's organisation acts (docs/backoffice.md § The operator's
organisation acts): grant the requester ownership, start, move or cancel the
closing, and delete it once the closing day has come — each delegating to an
operator twin in `OrganisationService`, which refuses every one while the
organisation has an owner. Commands like the rest in `commands.py`, whose
registry lists them; here only so that file stays one a reader can hold.
"""

from datetime import date, timedelta
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

from beats.domain.exceptions import OrganisationNotFound
from beats.operator.ids import DocumentId

if TYPE_CHECKING:
    # Annotations only: commands.py imports this module for its registry.
    from beats.operator.commands import CommandContext


class OrganisationArgs(BaseModel):
    organisation_id: DocumentId


async def organisation_name(ctx: CommandContext, organisation_id: str) -> str:
    """Resolves or refuses, like an account's email: an unknown organisation is a
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
        return await organisation_name(ctx, args.organisation_id)

    async def describe(self, ctx: CommandContext, args: Any) -> dict[str, Any]:
        return await _organisation_state(ctx, args.organisation_id)

    async def execute(self, ctx: CommandContext, args: Any) -> dict[str, Any]:
        raise NotImplementedError

    async def on_queued(self, ctx: CommandContext, args: Any) -> None:
        return None


class GrantOwnerArgs(OrganisationArgs):
    user_id: DocumentId


class GrantOwner(_OrganisationCommand):
    name = "organisation.grant_owner"
    args_model = GrantOwnerArgs

    async def describe(self, ctx: CommandContext, args: GrantOwnerArgs) -> dict[str, Any]:
        """Where the requester stands: their role, or None when they are not
        an active member, beside the highest role any active member holds."""
        state = await _organisation_state(ctx, args.organisation_id)
        members = await ctx.organisations.store.list_members(args.organisation_id)
        mine = next((m.role.value for m in members if m.user_id == args.user_id), None)
        top = max((m.role for m in members), key=lambda role: role.rank, default=None)
        return {**state, "requester_role": mine, "highest_role": top.value if top else None}

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


class DeleteOrganisation(_OrganisationCommand):
    """Queued with a 1-day window. The notice was the request, so no second
    one is needed; the twin's rules run when the job does, so an organisation
    given an owner while it waited is refused then."""

    name = "organisation.delete"
    window: timedelta | None = timedelta(days=1)

    async def describe(self, ctx: CommandContext, args: Any) -> dict[str, Any]:
        """What a deletion hands back and removes: its projects, each copied
        to the members who hold rows on it, and its active members."""
        state = await _organisation_state(ctx, args.organisation_id)
        store = ctx.organisations.store
        return {
            **state,
            "projects": len(await store.list_projects(args.organisation_id)),
            "members": len(await store.list_members(args.organisation_id)),
        }

    async def execute(self, ctx: CommandContext, args: Any) -> dict[str, Any]:
        counts = await ctx.organisations.operator_delete_organisation(args.organisation_id)
        return dict(counts)
