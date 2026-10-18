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
"""

import builtins
from collections.abc import Callable, Iterable
from datetime import date, datetime
from typing import NamedTuple
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from beats.domain.exceptions import ProjectNotBilledToClient, ReportLinkNotFound
from beats.domain.models import ReportLink, ReportLinkFields, ReportScope
from beats.domain.ports import BillingsByClient, ClientById, ProjectNames, ReportLinkStore
from beats.domain.report_links import check_expiry, check_range_over, is_live, new_token


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
            ReportLink(**fields.model_dump(), token_hash=hashed, tz=tz.key)
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
        """Turn off one client's links, or with None every one: how many."""
        return await self.links.delete_all(client_id)

    async def project_names(self, links: Iterable[ReportLink]) -> dict[str, str]:
        """The current names of the projects these links show, by id."""
        return await self.projects.names_of(
            {project_id for link in links for project_id in link.project_ids}
        )

    def live(self, link: ReportLink) -> bool:
        """Whether a link still opens: today in its zone is no later than its
        last day. A stored zone that no longer resolves never does."""
        try:
            zone = ZoneInfo(link.tz)
        except ZoneInfoNotFoundError, ValueError:
            return False
        return is_live(link, self._now(zone).date())

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
