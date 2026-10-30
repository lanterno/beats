"""The public report endpoint — a client reads its own hours with no login.

This is the only route in the API that serves a user's data to a caller with
no session, so the rules it follows are worth stating in one place
(docs/billing.md, *Report links (phase 1c)*):

- **The token is the whole of the authorisation.** It resolves to a stored
  link, which names the account, the client and the range. Nothing else about
  the request is trusted: not another header, not a query parameter, not a
  timezone the reader asks for.
- **The token rides a header (`X-Report-Token`), never the URL.** Request
  logs keep every URL (path and query string) for 30 days; headers stay out
  of them. The shared `/r/<token>` link is the SPA's own route and never
  reaches this API as a path.
- **The read is as user-scoped as any other.** `billing_service_for` builds
  the same repositories a signed-in route is given, bound to the owner the
  token resolved to. The only question this route answers differently from
  the rest of the API is *which* account, and a 32-byte token answers it.
- **One client, assembled alone.** `client_period` reads that client's
  billings, their projects, their beats and those beats' overrides — never
  `period`, which assembles every client.
- **The response is written field by field** (`ReportResponse`), so what a
  client sees cannot grow by inheritance when the private month report does.
- **Every failure is one 404.** No such token, a mistyped one, a revoked one,
  a deleted client: `REPORT_NOT_FOUND` for all of them, so a reader with no
  session learns nothing from the difference.
"""

from typing import Annotated

from fastapi import APIRouter, Header, Request, Response

from beats.api.dependencies import ReportLinkLookupDep, billing_service_for
from beats.api.routers.auth import limiter
from beats.api.schemas import ReportEntryResponse, ReportLineResponse, ReportResponse
from beats.domain.billing import ClientBilling
from beats.domain.exceptions import ReportNotFound
from beats.domain.models import ReportLink

router = APIRouter(
    prefix="/api/reports",
    tags=["Reports"],
    responses={404: {"description": "Not found"}},
)


def _report(link: ReportLink, billing: ClientBilling) -> ReportResponse:
    """`assemble_client`'s answer, narrowed to what the link says it shows.

    The narrowing is done here rather than in the assembler so that one
    arithmetic serves the owner's page and the client's, and only the shape
    differs. Hiding amounts nulls them; it never changes an hour.
    """
    money = link.show_amounts
    return ReportResponse(
        client_name=billing.name,
        first=link.first,
        last=link.last,
        show_amounts=link.show_amounts,
        show_entries=link.show_entries,
        currency=billing.currency if money else None,
        minor_units=billing.minor_units if money else None,
        billable_hours=float(billing.billable_hours),
        unpriced_hours=float(billing.unpriced_hours) if money else None,
        amount_minor=billing.amount_minor if money else None,
        lines=[
            ReportLineResponse(
                project_name=line.project_name,
                first=line.first,
                last=line.last,
                hours=float(line.hours),
                rate_minor=line.rate_minor if money else None,
                amount_minor=line.amount_minor if money else None,
            )
            for line in billing.lines
        ],
        entries=[
            ReportEntryResponse(
                day=entry.day,
                start=entry.start,
                end=entry.end,
                hours=float(entry.hours),
            )
            # Only the billable ones: a client sees what they are being asked
            # to pay for, and hours they are not billed for are the
            # freelancer's business.
            for entry in (billing.entries if link.show_entries else [])
            if entry.billable
        ],
    )


@router.get("", response_model=ReportResponse)
@limiter.limit("30/minute")
async def read_report(
    request: Request,
    response: Response,
    lookup: ReportLinkLookupDep,
    token: Annotated[str | None, Header(alias="X-Report-Token")] = None,
) -> ReportResponse:
    """One client's billable work over a report link's frozen range.

    Public: no bearer token, and a device token is still refused before this
    runs (`device_may_reach` in `server.py`). Rate-limited less against
    guessing — 32 bytes are not guessed — than against a leaked link being
    hammered. 404 REPORT_NOT_FOUND for every way the token fails to resolve.

    The token rides the X-Report-Token header, not the path: Cloud Run's
    request log keeps every requestUrl for 30 days, and a URL that *is* the
    authorisation must not be readable there (the `/r/<token>` link people
    share is the SPA's route; only this call changes).
    """
    owned = await lookup.find_by_token(token) if token else None
    if owned is None:
        raise ReportNotFound()
    # The one place in the API where a request's account comes from a stored
    # record rather than a token the caller proved. Everything below it is
    # scoped to that account exactly as a signed-in request would be.
    service = billing_service_for(owned.user_id)
    billing = await service.report_period(owned.link)
    # No shared cache may keep a copy, and nothing that crawls may index one.
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    return _report(owned.link, billing)
