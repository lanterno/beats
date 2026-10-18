"""Report links API router — making, listing and turning off the links a
client's report is opened with, no sign-in needed (docs/billing.md, phase 1c).

Under /api/billing, so no device token reaches it (`DEVICE_ALLOWED_PREFIXES`
in `server.py`), and every route needs a session. A link or a client that is
not the caller's is not found (404), never forbidden, a malformed id
included. The create answers with the link's token once; nothing else ever
does, and the database holds only its HMAC. The report itself is opened
under /api/public (`public_reports.py`).
"""

import http

from fastapi import APIRouter, Query, Response

from beats.api.dependencies import ReportLinkServiceDep, RequiredTimezoneDep
from beats.api.schemas import (
    ReportLinkCreatedResponse,
    ReportLinkProjectResponse,
    ReportLinkResponse,
    ReportLinksTurnOffRequest,
    ReportLinksTurnOffResponse,
)
from beats.domain.models import ReportLink, ReportLinkFields

router = APIRouter(
    prefix="/api/billing/report-links",
    tags=["Report links"],
    responses={404: {"description": "Not found"}},
)


def _response(link: ReportLink, names: dict[str, str], *, live: bool) -> ReportLinkResponse:
    return ReportLinkResponse(
        id=link.id or "",
        client_id=link.client_id,
        label=link.label,
        first=link.first,
        last=link.last,
        tz=link.tz,
        show_amounts=link.show_amounts,
        show_notes=link.show_notes,
        projects=[
            ReportLinkProjectResponse(id=project_id, name=names[project_id])
            for project_id in link.project_ids
            if project_id in names
        ],
        expires_on=link.expires_on,
        created_at=link.created_at,
        state="live" if live else "ended",
    )


@router.get("", response_model=list[ReportLinkResponse])
async def list_report_links(
    service: ReportLinkServiceDep,
    client_id: str | None = Query(None, description="One client's links; all of them without."),
):
    """The caller's report links, newest first, live and ended: an ended
    link stays listed until it is removed. Never a token."""
    links = await service.list(client_id)
    names = await service.project_names(links)
    return [_response(link, names, live=service.live(link)) for link in links]


@router.post("", status_code=http.HTTPStatus.CREATED, response_model=ReportLinkCreatedResponse)
async def create_report_link(
    request: ReportLinkFields, service: ReportLinkServiceDep, tz: RequiredTimezoneDep
):
    """Make a report link for one client, some of its billed projects and a
    stretch of finished days, counted in `tz`. Every key is required, null
    where it may be. Answers with `token`, once: it is stored only as a hash.

    404 CLIENT_NOT_FOUND for a client that is not the caller's (archived
    ones take links); 409 PROJECT_NOT_BILLED_TO_CLIENT, naming
    `project_ids.N`, for a project not billed to it now; 409 RANGE_NOT_OVER
    when `last` is not before today in `tz`; 422 when `expires_on` is not
    from today to 366 days ahead; 400 INVALID_TIMEZONE."""
    made = await service.create(request, tz)
    names = await service.project_names([made.link])
    response = _response(made.link, names, live=service.live(made.link))
    return ReportLinkCreatedResponse(**response.model_dump(), token=made.token)


@router.post("/turn-off", response_model=ReportLinksTurnOffResponse)
async def turn_off_report_links(request: ReportLinksTurnOffRequest, service: ReportLinkServiceDep):
    """Turn off one client's report links, or with `client_id: null` every
    one, for a session that may have been someone else's. Each is deleted,
    and answers as a link that never existed."""
    return ReportLinksTurnOffResponse(turned_off=await service.turn_off(request.client_id))


@router.delete("/{link_id}", status_code=http.HTTPStatus.NO_CONTENT)
async def delete_report_link(link_id: str, service: ReportLinkServiceDep) -> Response:
    """Turn a link off, or remove an ended one: it is deleted, can't be
    turned back on, and answers as a link that never existed. 404
    REPORT_LINK_NOT_FOUND when it is not the caller's, or is already gone."""
    await service.delete(link_id)
    return Response(status_code=http.HTTPStatus.NO_CONTENT)
