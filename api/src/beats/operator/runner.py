"""The one coordinator every operator mutation goes through.

1. check the role; 2. check the typed confirmation; 3. describe(); 4. run —
inline, or (with a window) enqueue as a job; 5. write `operator_audit` with
before and after. Four properties fall out of one place rather than ten:
nothing is unaudited, destructive work routes itself to the queue,
confirmation is declared rather than remembered per handler, and step 4's
job runner is trivial — load the command and run this same function, which
executes it rather than queueing it again.

There is deliberately no OperatorService: this resolves, authorises, audits
and delegates. If a rule ever starts living here or in a command, that is
the signal it was put in the wrong place (roadmaps/backoffice.md § Commands
are objects).
"""

from typing import Any

from pydantic import ValidationError

from beats.domain.exceptions import DomainException
from beats.infrastructure.operator_store import MongoOperatorAudit
from beats.operator.commands import COMMANDS, CommandContext


class UnknownCommand(DomainException):
    status_code = 404
    message = "No such command"
    code = "UNKNOWN_COMMAND"


class ViewerCannotAct(DomainException):
    """Two roles from day one, so a second person can look without acting."""

    status_code = 403
    message = "A viewer runs no command"
    code = "VIEWER_CANNOT_ACT"


class InvalidCommandArgs(DomainException):
    status_code = 422
    code = "INVALID_COMMAND_ARGS"


class ConfirmationMismatch(DomainException):
    """The typed confirmation is the operator proving they are acting on the
    thing they think they are — the account's email, the organisation's name
    — never a defence against cross-site requests, which the Origin check
    holds (a forging page sends it as easily as the operator types it)."""

    status_code = 409
    message = "The confirmation does not name the subject"
    code = "CONFIRMATION_MISMATCH"


async def run_command(
    ctx: CommandContext,
    name: str,
    args: dict[str, Any],
    confirmation: str | None,
    *,
    enqueue_only: bool = False,
) -> dict[str, Any]:
    """Execute (or, for a windowed command, enqueue) one command, and answer
    the audit entry. `enqueue_only` is unused until step 4's queue exists;
    the registry holds only inline commands today."""
    command = COMMANDS.get(name)
    if command is None:
        raise UnknownCommand()
    if ctx.operator.role != "operator":
        raise ViewerCannotAct()

    try:
        parsed = command.args_model.model_validate(args)
    except ValidationError as e:
        raise InvalidCommandArgs(str(e)) from None

    expected = await command.confirmation(ctx, parsed)
    if expected is not None and confirmation != expected:
        raise ConfirmationMismatch()

    before = await command.describe(ctx, parsed)
    after = await command.execute(ctx, parsed)

    return await MongoOperatorAudit(ctx.db).record(
        command=command.name,
        operator_sub=ctx.operator.sub,
        operator_email=ctx.operator.email,
        subject_kind=command.subject_kind,
        subject_id=command.subject_id(parsed),
        before=before,
        after=after,
    )
