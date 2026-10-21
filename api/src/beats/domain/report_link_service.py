"""Report links: making, listing and turning off the links a client's report
is opened with (docs/billing.md, phase 1c).

Every store here is the caller's, so someone else's client, project or link
is not found (404), never forbidden. The rules that read the clock or other
records — the client is the caller's, each project is billed to it now, the
range is over, the expiry is ahead — are checked here when a link is made,
not on the models: a stored link is re-validated on every read, and must not
become unreadable when a project moves or a day passes.

The token is minted here and handed back once, in `ReportLinkMade`; only its
HMAC under `REPORT_LINK_KEY` is stored.

`PublicReportReader` builds the report a link shows, for the public route
and the preview alike. It is built for the link's owner, never for whoever
is asking, and from ports that reach one client's billed projects and
nothing else: no `list_all`, no project list, no budget, no coach.
"""

import builtins
from collections.abc import Callable, Iterable
from datetime import date, datetime
from typing import NamedTuple
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from beats.domain.billing import utc_range
from beats.domain.exceptions import ProjectNotBilledToClient, ReportLinkNotFound
from beats.domain.models import Project, ReportLink, ReportLinkFields, ReportScope
from beats.domain.ports import (
    BillingsByClient,
    ClientById,
    OverridesFor,
    ProjectNames,
    ReportBeatReader,
    ReportLinkStore,
)
from beats.domain.report_links import (
    HoursReport,
    PricedReport,
    check_expiry,
    check_range_over,
    is_live,
    key_id,
    new_token,
    public_report,
    report_months,
)


class PublicReportReader:
    """What a report link shows, read for its owner from narrow ports: one
    client, the billings of the projects billed to it now, those projects'
    names, their finished beats in the range and those beats' overrides.

    The projects read are the link's own that are still billed to its
    client, so a project moved there after the link was made, or named by a
    link it was never on, is never read. The beat read leaves tags in Mongo,
    and notes unless the link shows them."""

    def __init__(
        self,
        clients: ClientById,
        billings: BillingsByClient,
        projects: ProjectNames,
        beats: ReportBeatReader,
        overrides: OverridesFor,
    ):
        self.clients = clients
        self.billings = billings
        self.projects = projects
        self.beats = beats
        self.overrides = overrides

    async def read(self, scope: ReportScope, tz: ZoneInfo) -> PricedReport | HoursReport:
        """The report over `scope`, its days in `tz`. `ClientNotFound` when
        the client has gone; a billing whose project has gone is skipped, as
        `BillingService.period` skips it."""
        client = await self.clients.get_by_id(scope.client_id)
        wanted = set(scope.project_ids)
        billings = [
            billing
            for billing in await self.billings.list_by_client(scope.client_id)
            if billing.project_id in wanted
        ]
        names = await self.projects.names_of(billing.project_id for billing in billings)
        billings = [billing for billing in billings if billing.project_id in names]
        start, end = utc_range(scope.first, scope.last, tz)
        beats = await self.beats.list_finished_between(
            [billing.project_id for billing in billings], start, end, notes=scope.show_notes
        )
        overrides = await self.overrides.list_for(beat.id for beat in beats if beat.id is not None)
        months = report_months(
            client,
            billings,
            # `assemble_client` takes projects; it reads their names alone.
            {project_id: Project(id=project_id, name=name) for project_id, name in names.items()},
            beats,
            {override.beat_id: override.billable for override in overrides},
            scope.first,
            scope.last,
            tz,
        )
        notes = (
            {beat.id: beat.note for beat in beats if beat.id is not None and beat.note}
            if scope.show_notes
            else None
        )
        return public_report(scope, client, names, months, notes)


class ReportLinkMade(NamedTuple):
    link: ReportLink
    token: str  # the only place the plaintext lives, once


class ReportLinkService:
    """The caller's report links.

    The clock is read for one thing, "today in the link's time zone": the
    day a range must be over by, the day an expiry runs from, and the day
    a link is live on. A test hands in a fixed instant, as it does to
    `BillingService`.
    """

    def __init__(
        self,
        links: ReportLinkStore,
        clients: ClientById,
        billings: BillingsByClient,
        projects: ProjectNames,
        key: bytes,
        now: Callable[[ZoneInfo], datetime] = datetime.now,
    ):
        self.links = links
        self.clients = clients
        self.billings = billings
        self.projects = projects
        self._key = key
        self._now = now

    async def create(self, fields: ReportLinkFields, tz: ZoneInfo) -> ReportLinkMade:
        """A new link over `fields`, its days counted in `tz`, and its token,
        which nothing else ever returns.

        - the client must be the caller's, archived or not (404
          CLIENT_NOT_FOUND);
        - each project must be billed to it now (409
          PROJECT_NOT_BILLED_TO_CLIENT, naming the first that is not);
        - the last day must be before today in `tz` (409 RANGE_NOT_OVER);
        - it works from today to at most a year and a day ahead (422 on
          `expires_on`).
        """
        today = self._now(tz).date()
        await self.check_scope(fields, today)
        check_expiry(fields.expires_on, today)
        token, hashed = new_token(self._key)
        link = await self.links.create(
            ReportLink(
                **fields.model_dump(), token_hash=hashed, key_id=key_id(self._key), tz=tz.key
            )
        )
        return ReportLinkMade(link, token)

    async def list(self, client_id: str | None) -> builtins.list[ReportLink]:
        """One client's links, or every client's, newest first: live and
        ended alike, since an ended link stays listed until it is removed."""
        return await self.links.list(client_id)

    async def delete(self, link_id: str) -> None:
        """Turn a link off, or remove an ended one: the document goes, so no
        read can forget a flag. 404 when it is not the caller's, or is gone."""
        if not await self.links.delete(link_id):
            raise ReportLinkNotFound()

    async def turn_off(self, client_id: str | None) -> int:
        """Turn off one client's live links, or with None every live one:
        how many. An ended link stays listed until it is removed on its own,
        as the question that asks for this counts only the live ones."""
        turned_off = 0
        for link in await self.links.list(client_id):
            if link.id is not None and self.live(link) and await self.links.delete(link.id):
                turned_off += 1
        return turned_off

    async def project_names(self, links: Iterable[ReportLink]) -> dict[str, str]:
        """The current names of the projects these links show, by id."""
        return await self.projects.names_of(
            {project_id for link in links for project_id in link.project_ids}
        )

    def live(self, link: ReportLink) -> bool:
        """Whether a link still opens: it was made under the key the API runs
        with, and today in its zone is no later than its last day. A link
        made before `REPORT_LINK_KEY` was rotated never opens again, nor does
        one whose stored zone no longer resolves."""
        if link.key_id != key_id(self._key):
            return False
        try:
            zone = ZoneInfo(link.tz)
        except ZoneInfoNotFoundError, ValueError:
            return False
        return is_live(link, self._now(zone).date())

    async def preview(
        self, scope: ReportScope, tz: ZoneInfo, reader: PublicReportReader
    ) -> PricedReport | HoursReport:
        """The report a link over `scope` would show, by the public read
        itself, with nothing stored: refused as a create would be, but for
        the expiry, so the caller can only preview their own client's billed
        projects over finished days."""
        await self.check_scope(scope, self._now(tz).date())
        return await reader.read(scope, tz)

    async def check_scope(self, scope: ReportScope, today: date) -> None:
        """What a report may cover, `today` in its zone: the caller's client
        (404 CLIENT_NOT_FOUND), projects billed to it now that exist (409
        PROJECT_NOT_BILLED_TO_CLIENT, naming the first that is not), and
        finished days (409 RANGE_NOT_OVER)."""
        await self.clients.get_by_id(scope.client_id)
        billed = {
            billing.project_id for billing in await self.billings.list_by_client(scope.client_id)
        }
        named = await self.projects.names_of(scope.project_ids)
        for index, project_id in enumerate(scope.project_ids):
            if project_id not in billed or project_id not in named:
                raise ProjectNotBilledToClient(index)
        check_range_over(scope.last, today)
