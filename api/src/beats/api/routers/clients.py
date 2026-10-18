"""Clients API router — who you bill, in what currency, at what default rate.

A client is a record in your own account (docs/billing.md). Every route
answers 404 for a client that is not the caller's, a malformed id included,
never 403: the repository is user-scoped, so someone else's client simply
does not exist here. Deliberately outside every device-token prefix
(`DEVICE_ALLOWED_PREFIXES` in `server.py`): a paired device sees no money.
"""

import http

from fastapi import APIRouter, Response

from beats.api.dependencies import BillingServiceDep, RequiredTimezoneDep
from beats.api.schemas import ClientResponse, ClientUpdateRequest, ClientWriteRequest
from beats.domain.billing_service import ClientRecord
from beats.domain.currencies import minor_units
from beats.domain.models import ClientFields

router = APIRouter(
    prefix="/api/clients",
    tags=["Clients"],
    responses={404: {"description": "Not found"}},
)


def _response(record: ClientRecord) -> ClientResponse:
    client = record.client
    return ClientResponse(
        **client.model_dump(),
        minor_units=minor_units(client.currency),
        currency_locked=record.currency_locked,
    )


@router.get("/", response_model=list[ClientResponse])
async def list_clients(service: BillingServiceDep, archived: bool = False):
    """The active clients, or with `archived` the archived ones, by name."""
    return [_response(record) for record in await service.list_clients(archived=archived)]


@router.post("/", status_code=http.HTTPStatus.CREATED, response_model=ClientResponse)
async def create_client(request: ClientWriteRequest, service: BillingServiceDep):
    """Add a client. Every key is required, null where it may be. 400
    UNKNOWN_CURRENCY for a code the API's table does not know."""
    return _response(await service.create_client(request))


@router.get("/{client_id}", response_model=ClientResponse)
async def get_client(client_id: str, service: BillingServiceDep):
    """One client. 404 CLIENT_NOT_FOUND when it is not the caller's."""
    return _response(await service.get_client(client_id))


@router.put("/{client_id}", response_model=ClientResponse)
async def update_client(
    client_id: str,
    request: ClientUpdateRequest,
    service: BillingServiceDep,
    tz: RequiredTimezoneDep,
):
    """Replace a client's name, contact, currency and default rates.

    409 CURRENCY_IN_USE when the currency changes once something is priced
    in it, or a money billing budget is in it (`currency_locked`). A rate
    change dated before the current month in `tz` may change figures
    already invoiced: without `rewrite_past: true` it is a 409
    RETROACTIVE_CHANGE naming the first month touched.
    `tz` and `rewrite_past` are both required."""
    fields = ClientFields.model_validate(request.model_dump(exclude={"rewrite_past"}))
    record = await service.update_client(
        client_id, fields, rewrite_past=request.rewrite_past, tz=tz
    )
    return _response(record)


@router.post("/{client_id}/archive", response_model=ClientResponse)
async def archive_client(client_id: str, service: BillingServiceDep):
    """Archive a client: kept, in the reports of months it has hours in, and
    out of the pickers."""
    return _response(await service.set_archived(client_id, True))


@router.post("/{client_id}/unarchive", response_model=ClientResponse)
async def unarchive_client(client_id: str, service: BillingServiceDep):
    """Bring an archived client back."""
    return _response(await service.set_archived(client_id, False))


@router.delete("/{client_id}", status_code=http.HTTPStatus.NO_CONTENT)
async def delete_client(client_id: str, service: BillingServiceDep) -> Response:
    """Delete a client, and its billing budget with it. 409
    CLIENT_HAS_PROJECTS while a project is billed to it: archive it instead,
    so past reports keep its name and currency."""
    await service.delete_client(client_id)
    return Response(status_code=http.HTTPStatus.NO_CONTENT)
