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

from beats.infrastructure.operator_reads import MongoOperatorReads
from beats.operator.commands import CommandContext
from beats.operator.context import build_command_context
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


def get_command_context(
    request: Request, db: OperatorDbDep, operator: CurrentOperator
) -> CommandContext:
    return build_command_context(
        db,
        operator,
        freeze=getattr(request.app.state, "deploy_freeze", None),
        status=getattr(request.app.state, "status_store", None),
    )


CommandContextDep = Annotated[CommandContext, Depends(get_command_context)]
