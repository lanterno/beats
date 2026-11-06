"""The one coordinator every operator mutation goes through.

1. check the role; 2. check the typed confirmation; 3. describe(); 4. run —
inline, or (with a window) enqueue as a job; 5. write `operator_audit` with
before and after. Four properties fall out of one place rather than ten:
nothing is unaudited, destructive work routes itself to the queue,
confirmation is declared rather than remembered per handler, and the
job runner is trivial — load the command and run this same function, which
executes it rather than queueing it again.

There is deliberately no OperatorService: this resolves, authorises, audits
and delegates. If a rule ever starts living here or in a command, that is
the signal it was put in the wrong place (docs/backoffice.md § Commands).
"""

from typing import Any

from pydantic import ValidationError

from beats.domain.exceptions import DomainException
from beats.infrastructure.operator_jobs import MongoOperatorJobs
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


class JobAlreadyQueued(DomainException):
    """One queued job per command and subject: a double-submitted erasure
    would otherwise make two jobs behind one suspension, and cancelling
    either would lift it while the other ran on schedule."""

    status_code = 409
    message = "This command is already queued for this subject"
    code = "JOB_ALREADY_QUEUED"


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
    from_queue: bool = False,
) -> dict[str, Any]:
    """Execute one command — or, for a windowed command arriving from a
    request, enqueue it — and answer the audit entry (with the job under
    `job` when one was queued; the queueing itself is kept by the job row's
    `queued_by`, and the execution writes the audit when it runs).

    `from_queue` is the job runner's path: the role and the typed
    confirmation were checked once, by the request that queued it; the job
    sees no request and holds no allowlist, so it checks neither again, and
    the audit is written under the operator the command carries."""
    command = COMMANDS.get(name)
    if command is None:
        raise UnknownCommand()
    if not from_queue and ctx.operator.role != "operator":
        raise ViewerCannotAct()

    try:
        parsed = command.args_model.model_validate(args)
    except ValidationError as e:
        raise InvalidCommandArgs(str(e)) from None

    if not from_queue:
        expected = await command.confirmation(ctx, parsed)
        if expected is not None and confirmation != expected:
            raise ConfirmationMismatch()

    if command.window is not None and not from_queue:
        # Destructive work routes itself: it cannot accidentally run in a
        # request handler holding the wrong credential. A queued job is a
        # serialised command — one abstraction, not two mechanisms.
        jobs = MongoOperatorJobs(ctx.db)
        if await jobs.find_queued(command.name, command.subject_id(parsed)):
            raise JobAlreadyQueued()
        job = await jobs.enqueue(
            command=command.name,
            args=parsed.model_dump(mode="json"),
            subject_kind=command.subject_kind,
            subject_id=command.subject_id(parsed),
            queued_by_sub=ctx.operator.sub,
            queued_by_email=ctx.operator.email,
            window=command.window,
        )
        try:
            await command.on_queued(ctx, parsed)
        except Exception:
            # The queueing's side effect failed (an erasure that could not
            # suspend). A job standing with no suspension would wait out an
            # invisible window the person never sees, while the operator —
            # who got an error — believes nothing was queued. On failure,
            # nothing stands.
            await jobs.cancel(job["id"])
            raise
        return {"queued": True, "job": job}

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
