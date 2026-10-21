"""Public reports API router — a client's report, opened with a report link's
token and no session (docs/billing.md, phase 1c).

The one route under /api/public/, which the auth middleware lets through
without a session (`PUBLIC_PREFIXES` in `server.py`). A handler here never
reads `request.state.user_id` and takes no session dependency: the
middleware still sets the id for a valid session on a public path, and the
report must be the link owner's whoever sends it. The owner is whoever the
link's token resolves to, and every store is built for them.

The token travels in the body, never the path or the query, so no request
log keeps it; nothing here logs it or its hash either. Every dead link —
unknown, malformed, turned off, ended, its client gone, its stored zone no
longer known — answers the same 404 bytes, returned rather than raised.
"""

from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from beats.api import report_rate
from beats.api.dependencies import ReportLinkKeyDep, ReportLinkResolverDep, public_report_reader
from beats.api.errors import envelope
from beats.domain.exceptions import ClientNotFound
from beats.domain.report_links import (
    TOKEN_MAX_LENGTH,
    HoursReport,
    PricedReport,
    is_live,
    token_hash,
    well_formed,
)

router = APIRouter(prefix="/api/public", tags=["Public"])


class PublicReportRequest(BaseModel):
    """A report link's token, as the page read it after the `#`."""

    model_config = ConfigDict(extra="forbid")

    token: str = Field(strict=True, max_length=TOKEN_MAX_LENGTH)


class PublicReportError(BaseModel):
    detail: str
    code: str


# One body for every dead link, so none can be told from another.
_NOT_FOUND = {"detail": "This report link isn't valid.", "code": "REPORT_NOT_FOUND"}


def _dead() -> JSONResponse:
    return JSONResponse(_NOT_FOUND, status_code=404)


@router.post(
    "/reports",
    response_model=PricedReport | HoursReport,
    responses={
        404: {"model": PublicReportError, "description": "REPORT_NOT_FOUND"},
        429: {"model": PublicReportError, "description": "REPORT_RATE_LIMITED"},
    },
)
async def open_report(
    body: PublicReportRequest, resolver: ReportLinkResolverDep, key: ReportLinkKeyDep
) -> Response:
    """The report a link shows: one client's billable hours over the link's
    finished days, by month and by day, with the amounts and the session
    notes only if the link was made to show them. No session; one sent
    along is ignored.

    404 REPORT_NOT_FOUND, the same bytes for every dead link; 429
    REPORT_RATE_LIMITED past 60 opens of one link in a minute; 422 for a
    body that is not `{"token": "<at most 64 characters>"}`."""
    if not well_formed(body.token):
        return _dead()
    found = await resolver.find(token_hash(body.token, key))
    if found is None:
        return _dead()
    user_id, link = found
    try:
        tz = ZoneInfo(link.tz)
    except ZoneInfoNotFoundError, ValueError:
        return _dead()
    if not is_live(link, datetime.now(tz).date()):
        return _dead()
    if not report_rate.allow(link.token_hash):
        return envelope(
            status_code=429,
            detail="Too many requests for this report just now.",
            code="REPORT_RATE_LIMITED",
        )
    try:
        report = await public_report_reader(user_id).read(link, tz)
    except ClientNotFound:
        return _dead()
    # Written from the built shape, not re-serialised through
    # `response_model`, which is there for the OpenAPI document: the bytes
    # are what `public_report` built, and the preview's are the same.
    return JSONResponse(report.model_dump(mode="json"))
