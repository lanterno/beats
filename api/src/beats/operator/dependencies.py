"""The operator app's providers.

Deliberately not `beats.api.dependencies`, which the operator root must never
import: that module — and the routers built on it — loads `beats.settings`,
and with it the API's secrets. Everything here reads the Mongo client
`operator_server`'s lifespan put on `app.state` and the `OperatorIdentity`
its middleware resolved from the IAP assertion.
"""

from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from pymongo.asynchronous.database import AsyncDatabase

from beats.domain.accounts import AccountService
from beats.domain.organisations import OrganisationService
from beats.infrastructure.operator_reads import MongoOperatorReads
from beats.infrastructure.operator_store import MongoAccountLimitsStore
from beats.infrastructure.organisations import MongoOrganisationRecords, MongoOrganisationStore
from beats.infrastructure.repositories import (
    MongoDeviceRegistrationRepository,
    MongoUserRepository,
)
from beats.operator.commands import CommandContext
from beats.operator.reads import OperatorReads
from beats.operator.settings import OperatorIdentity


def get_operator_db(request: Request) -> AsyncDatabase:
    """The operator app's own client, from `app.state` — never the public
    API's `Database` class attribute, which two apps in one process (the
    test suite) would otherwise share and tear down under each other."""
    return request.app.state.operator_db


def get_current_operator(request: Request) -> OperatorIdentity:
    """The identity the middleware resolved. `request.state.user_id` is never
    set in this app — a user-scoped dependency imported by mistake fails
    loudly on the missing attribute rather than quietly scoping to the
    operator."""
    identity = getattr(request.state, "operator", None)
    if identity is None:
        # The middleware refuses before any route runs; reaching this is a
        # wiring bug, answered as unauthenticated rather than crashing.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No operator identity on this request",
        )
    return identity


OperatorDbDep = Annotated[AsyncDatabase, Depends(get_operator_db)]
CurrentOperator = Annotated[OperatorIdentity, Depends(get_current_operator)]


def get_operator_reads(request: Request, db: OperatorDbDep) -> OperatorReads:
    return MongoOperatorReads(
        db, coach_default_budget=request.app.state.operator_settings.coach_monthly_budget_usd
    )


OperatorReadsDep = Annotated[OperatorReads, Depends(get_operator_reads)]


class RefusingBillingPresence:
    """The operator never reads billing. Only `connect_project` asks a
    `BillingPresence`, which is a member's act the operator cannot perform,
    and a stand-in that answered would be a guess about somebody's billing."""

    async def exists(self, project_id: str) -> bool:
        raise RuntimeError("the operator's organisation service never reads billing")


def get_command_context(db: OperatorDbDep, operator: CurrentOperator) -> CommandContext:
    """The services a command delegates to — each built on the operator's own
    client, each owning the rule the command invokes, so the rule never lives
    in two places."""
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
    )


CommandContextDep = Annotated[CommandContext, Depends(get_command_context)]
