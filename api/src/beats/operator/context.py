"""Building a CommandContext outside a request.

Shared by the app's provider (`dependencies.get_command_context`) and the job
runner (`beats.operator.jobs`), so the services a command delegates to are
wired one way however it arrives.
"""

from pymongo.asynchronous.database import AsyncDatabase

from beats.domain.accounts import AccountService
from beats.domain.organisations import OrganisationService
from beats.infrastructure.operator_store import MongoAccountLimitsStore
from beats.infrastructure.organisation_records import MongoOrganisationRecords
from beats.infrastructure.organisations import MongoOrganisationStore
from beats.infrastructure.repositories import (
    MongoDeviceRegistrationRepository,
    MongoUserRepository,
)
from beats.operator.commands import CommandContext
from beats.operator.deploy_freeze import DeployFreeze
from beats.operator.settings import OperatorIdentity


class RefusingBillingPresence:
    """The operator never reads billing. Only `connect_project` asks a
    `BillingPresence`, which is a member's act the operator cannot perform,
    and a stand-in that answered would be a guess about somebody's billing."""

    async def exists(self, project_id: str) -> bool:
        raise RuntimeError("the operator's organisation service never reads billing")


def build_command_context(
    db: AsyncDatabase, operator: OperatorIdentity, *, freeze: DeployFreeze | None = None
) -> CommandContext:
    """The services a command delegates to — each owning the rule the command
    invokes, so the rule never lives in two places."""
    users = MongoUserRepository(db.users)
    return CommandContext(
        operator=operator,
        db=db,
        accounts=AccountService(users, MongoAccountLimitsStore(db)),
        organisations=OrganisationService(
            store=MongoOrganisationStore(db),
            records=MongoOrganisationRecords(db),
            users=users,
            billing=RefusingBillingPresence(),
        ),
        devices=MongoDeviceRegistrationRepository(db.device_registrations),
        freeze=freeze,
    )
