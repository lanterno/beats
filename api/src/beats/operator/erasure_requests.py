"""The erasure request log's two commands (docs/backoffice.md § The pages,
Privacy and compliance): a request that arrived by mail gets a date, and is
closed with a reason. Carved from commands.py at the size ceiling (CLAUDE.md
§ Conventions) and registered in its `COMMANDS` like every other command.

commands.py imports this module for that registry, so this one imports
nothing from it as it loads: `CommandContext` is named for the type checker
alone, and `InvalidCommandArgs` is imported where it is raised.
"""

import re
from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING, Annotated, Any, Literal

from bson import ObjectId
from pydantic import AfterValidator, BaseModel, Field, PrivateAttr, model_validator

from beats.domain.exceptions import DomainException
from beats.infrastructure.operator_store import MongoErasureRequests
from beats.operator.ids import DocumentId

if TYPE_CHECKING:
    from beats.operator.commands import CommandContext


# A reference is a ticket number or the mail's date — T-1234, #42,
# 2026-11-14-2: a few letters at most, then digits. Never free text: the row
# is kept a year after it closes and names the account by id, so neither a
# name nor an address has anywhere to go.
_REFERENCE = re.compile(r"[A-Za-z]{0,8}[-#]?[0-9][0-9-]*")


def _a_reference(value: str) -> str:
    value = value.strip()
    if not _REFERENCE.fullmatch(value):
        raise ValueError(
            "a ticket number or the mail's date, like T-1234 or 2026-11-14: a few letters"
            " at most, then digits — never a name or an address"
        )
    return value


class LogErasureRequestArgs(BaseModel):
    reference: Annotated[str, AfterValidator(_a_reference)] = Field(min_length=1, max_length=40)
    received_on: date
    user_id: DocumentId | None = None
    # The request's own id, made before it is written, so the audit can name
    # a request with no account by an id too. Never sent by the client.
    _request_id: str = PrivateAttr(default_factory=lambda: str(ObjectId()))

    @model_validator(mode="after")
    def _not_in_the_future(self) -> LogErasureRequestArgs:
        if self.received_on > datetime.now(UTC).date():
            raise ValueError("received_on is in the future")
        return self


class LogErasureRequest:
    """A request that arrived by mail gets a date, so the deadline is
    visible before anything is queued (docs/backoffice.md § The pages,
    Compliance). The audit's subject is an id — the account's when one is
    named, else the request's own — and never the reference: the audit is
    kept four years and names its subject the way it outlives it, by id."""

    name = "erasure_request.log"
    subject_kind = "erasure_request"
    window: timedelta | None = None
    args_model: type[BaseModel] = LogErasureRequestArgs

    def subject_id(self, args: Any) -> str:
        return args.user_id or args._request_id

    async def confirmation(self, ctx: CommandContext, args: Any) -> str | None:
        return None

    async def describe(self, ctx: CommandContext, args: Any) -> dict[str, Any]:
        if args.user_id is None:
            return {"account": None}
        user = await ctx.accounts.find(args.user_id)
        if user is None:
            # The account is a box on the form, not the subject in the route:
            # name the box, so the review keeps the form and says what is
            # wrong with it, rather than failing as a 404 would.
            from beats.operator.commands import InvalidCommandArgs

            raise InvalidCommandArgs(
                [{"path": "user_id", "message": "No account has this id", "type": "not_found"}]
            )
        return {"account": "exists", "suspended": user.suspended}

    async def execute(self, ctx: CommandContext, args: Any) -> dict[str, Any]:
        row = await MongoErasureRequests(ctx.db).log(
            request_id=args._request_id,
            reference=args.reference,
            received_on=args.received_on.isoformat(),
            subject_id=args.user_id,
            logged_by=ctx.operator.sub,
        )
        return {"request_id": row["id"], "received_on": row["received_on"]}

    async def on_queued(self, ctx: CommandContext, args: Any) -> None:
        return None


class ErasureRequestNotFound(DomainException):
    status_code = 404
    message = "No open erasure request with that id"
    code = "ERASURE_REQUEST_NOT_FOUND"


class CloseErasureRequestArgs(BaseModel):
    request_id: DocumentId
    # erased: the job ran. no_account: nothing to erase. withdrawn: they
    # asked again, the other way.
    reason: Literal["erased", "no_account", "withdrawn"]


class CloseErasureRequest:
    name = "erasure_request.close"
    subject_kind = "erasure_request"
    window: timedelta | None = None
    args_model: type[BaseModel] = CloseErasureRequestArgs

    def subject_id(self, args: Any) -> str:
        return args.request_id

    async def confirmation(self, ctx: CommandContext, args: Any) -> str | None:
        return None

    async def describe(self, ctx: CommandContext, args: Any) -> dict[str, Any]:
        row = await MongoErasureRequests(ctx.db).get(args.request_id)
        if row is None or row.get("closed_at"):
            raise ErasureRequestNotFound()
        return {"received_on": row["received_on"], "closed": False}

    async def execute(self, ctx: CommandContext, args: Any) -> dict[str, Any]:
        row = await MongoErasureRequests(ctx.db).close(
            args.request_id, reason=args.reason, closed_by=ctx.operator.sub
        )
        if row is None:
            raise ErasureRequestNotFound()
        return {"received_on": row["received_on"], "closed": True, "reason": args.reason}

    async def on_queued(self, ctx: CommandContext, args: Any) -> None:
        return None
