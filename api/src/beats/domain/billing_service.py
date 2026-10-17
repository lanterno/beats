"""Clients, project billing and billable overrides: the writes and their
rules, and the report the arithmetic in `domain/billing.py` makes of them.

Every store here is user-scoped, so someone else's client, project or beat
is not found (404) rather than forbidden. The rules a write must satisfy
beyond the models' own validators are checked here, not on the models: a
model is re-validated on every read, and a rule that later started failing
there would make every stored record unreadable (`_check_contract` and
`check_region` keep a contract's the same way).

A write that would change billable figures before the current month, in
the request's timezone, needs `rewrite_past` (`past_change`, `link_change`):
those months may have been invoiced. Attaching a project for the first
time is not gated, since no figure existed, and neither is an override —
editing a past entry is itself the consent.
"""

from collections.abc import Callable, Iterable
from datetime import date, datetime
from typing import NamedTuple
from zoneinfo import ZoneInfo

from beats.domain.billing import (
    BillingPeriod,
    assemble_billing,
    link_change,
    month_range,
    past_change,
    utc_range,
)
from beats.domain.currencies import check_currency
from beats.domain.exceptions import (
    BeatNotFound,
    ClientHasProjects,
    CurrencyInUse,
    CurrencyMismatch,
    NotFreelance,
    ProjectNotBilled,
    RetroactiveChange,
)
from beats.domain.models import (
    BillableOverride,
    BillingTerm,
    Client,
    ClientFields,
    ProjectBilling,
    ProjectKind,
)
from beats.domain.ports import (
    BillableOverrideStore,
    BillingBeatReader,
    BillingProjectReader,
    ClientStore,
    ProjectBillingStore,
)


class ClientRecord(NamedTuple):
    client: Client
    # Something is priced in its currency — a rate of its own, or of one of
    # its projects' — so the currency can no longer change (CURRENCY_IN_USE).
    currency_locked: bool


class BilledProject(NamedTuple):
    billing: ProjectBilling
    client: Client  # for the currency the terms' rates are in


def _priced(billings: Iterable[ProjectBilling]) -> bool:
    return any(term.rate_minor is not None for billing in billings for term in billing.terms)


class BillingService:
    """Clients and what is billed to them.

    The clock is read for one thing, "the 1st of this month in the request's
    timezone", which is where the closed past ends and where a report's
    current month stops; a test hands in a fixed instant, as it does to
    `ContractService`.
    """

    def __init__(
        self,
        clients: ClientStore,
        billings: ProjectBillingStore,
        overrides: BillableOverrideStore,
        projects: BillingProjectReader,
        beats: BillingBeatReader,
        now: Callable[[ZoneInfo], datetime] = datetime.now,
    ):
        self.clients = clients
        self.billings = billings
        self.overrides = overrides
        self.projects = projects
        self.beats = beats
        self._now = now

    def _month_start(self, tz: ZoneInfo) -> date:
        return self._now(tz).date().replace(day=1)

    # ------------------------------------------------------------------ #
    # Clients
    # ------------------------------------------------------------------ #

    async def list_clients(self, archived: bool = False) -> list[ClientRecord]:
        """The active clients, or with `archived` the archived ones, by name."""
        clients = await self.clients.list(archived=archived)
        billings = await self.billings.list_all()
        records = [
            ClientRecord(
                client,
                bool(client.rates)
                or _priced(billing for billing in billings if billing.client_id == client.id),
            )
            for client in clients
        ]
        return sorted(records, key=lambda r: (r.client.name.casefold(), r.client.id or ""))

    async def get_client(self, client_id: str) -> ClientRecord:
        return await self._record(await self.clients.get_by_id(client_id))

    async def create_client(self, fields: ClientFields) -> ClientRecord:
        """A new client, in a currency the table knows (400 UNKNOWN_CURRENCY)."""
        check_currency(fields.currency)
        created = await self.clients.create(Client(**fields.model_dump()))
        return ClientRecord(created, bool(created.rates))

    async def update_client(
        self, client_id: str, fields: ClientFields, *, rewrite_past: bool, tz: ZoneInfo
    ) -> ClientRecord:
        """Replace a client's name, contact, currency and rates; the archive
        flag and the creation date stay as stored.

        - A new currency must be one the table knows (400). The stored one is
          not checked again: a code withdrawn since must not lock its client
          out of a rename.
        - The currency cannot change once something is priced in it (409
          CURRENCY_IN_USE). Before that, a typo made at creation can still
          be fixed.
        - A rate change dated before the current month needs `rewrite_past`
          (409 RETROACTIVE_CHANGE).
        """
        record = await self.get_client(client_id)
        stored = record.client
        if fields.currency != stored.currency:
            check_currency(fields.currency)
            if record.currency_locked:
                raise CurrencyInUse()
        self._gate(past_change(stored.rates, fields.rates, self._month_start(tz)), rewrite_past)
        client = Client(
            **fields.model_dump(),
            id=stored.id,
            archived=stored.archived,
            created_at=stored.created_at,
        )
        return await self._record(await self.clients.update(client))

    async def set_archived(self, client_id: str, archived: bool) -> ClientRecord:
        """Archive a client, or bring one back. Archived, it is kept, appears
        in the reports of months it has hours in, and is left out of
        pickers; it can still be billed to, so a restored backup's billing
        on it is valid."""
        client = await self.clients.get_by_id(client_id)
        client.archived = archived
        return await self._record(await self.clients.update(client))

    async def delete_client(self, client_id: str) -> None:
        """Delete a client no project is billed to; while one is, 409
        CLIENT_HAS_PROJECTS — archive it instead."""
        await self.clients.get_by_id(client_id)
        if await self.billings.list_by_client(client_id):
            raise ClientHasProjects()
        await self.clients.delete(client_id)

    async def _record(self, client: Client) -> ClientRecord:
        if client.rates or client.id is None:
            return ClientRecord(client, bool(client.rates))
        return ClientRecord(client, _priced(await self.billings.list_by_client(client.id)))

    # ------------------------------------------------------------------ #
    # Project billing
    # ------------------------------------------------------------------ #

    async def list_project_billings(self) -> list[BilledProject]:
        """Every project's billing, with its client. A small set: one per
        billed project."""
        clients = {client.id: client for client in await self.clients.list_all()}
        return [
            BilledProject(billing, clients[billing.client_id])
            for billing in await self.billings.list_all()
            if billing.client_id in clients
        ]

    async def set_project_billing(
        self,
        project_id: str,
        client_id: str,
        terms: list[BillingTerm],
        *,
        rewrite_past: bool,
        tz: ZoneInfo,
    ) -> BilledProject:
        """Bill a freelance project to a client under `terms`, replacing what
        it had.

        - The project must be the caller's (404) and freelance (409
          NOT_FREELANCE); the client must be the caller's (404
          CLIENT_NOT_FOUND), archived or not.
        - Moving it to a client in another currency is refused (409
          CURRENCY_MISMATCH) while the terms it would have there carry a
          rate of their own, or a billable term dated before the current
          month: the rate was entered in the old currency, and the past
          hours were billed in it. Terms that drop both move nothing.
        - Attaching it the first time is not gated. Otherwise a change to the
          terms dated before the current month, or any move to another
          client while a term is dated there, needs `rewrite_past` (409
          RETROACTIVE_CHANGE).
        """
        project = await self.projects.get_by_id(project_id)
        if project.kind is not ProjectKind.FREELANCE:
            raise NotFreelance()
        client = await self.clients.get_by_id(client_id)
        stored = await self.billings.get(project_id)
        month_start = self._month_start(tz)
        if stored is not None:
            changes = [past_change(stored.terms, terms, month_start)]
            if stored.client_id != client_id:
                previous = await self.clients.get_by_id(stored.client_id)
                if previous.currency != client.currency and any(
                    term.rate_minor is not None
                    or (term.billable and term.effective_from < month_start)
                    for term in terms
                ):
                    raise CurrencyMismatch()
                changes.append(link_change([*stored.terms, *terms], month_start))
            self._gate(min((day for day in changes if day is not None), default=None), rewrite_past)
        billing = await self.billings.upsert(
            ProjectBilling(project_id=project_id, client_id=client_id, terms=terms)
        )
        return BilledProject(billing, client)

    async def remove_project_billing(
        self, project_id: str, *, rewrite_past: bool, tz: ZoneInfo
    ) -> None:
        """Stop billing a project: its hours are in no client's figures from
        then on, in every month. 404 when it is not billed; a term dated
        before the current month needs `rewrite_past` (409
        RETROACTIVE_CHANGE)."""
        stored = await self.billings.get(project_id)
        if stored is None:
            raise ProjectNotBilled()
        self._gate(link_change(stored.terms, self._month_start(tz)), rewrite_past)
        await self.billings.delete(project_id)

    @staticmethod
    def _gate(first_day: date | None, rewrite_past: bool) -> None:
        if first_day is not None and not rewrite_past:
            raise RetroactiveChange(first_day)

    # ------------------------------------------------------------------ #
    # Billable overrides
    # ------------------------------------------------------------------ #

    async def list_overrides(self) -> list[BillableOverride]:
        """Every override: they are exceptions, so the list is small."""
        return await self.overrides.list_all()

    async def set_override(self, beat_id: str, billable: bool) -> BillableOverride:
        """Mark one of the caller's beats billable or not, against its
        project's term (404 for a beat that is not theirs). Allowed on any
        beat: it counts only while the beat's project is billed."""
        if not await self.beats.exists(beat_id):
            raise BeatNotFound(beat_id)
        return await self.overrides.upsert(BillableOverride(beat_id=beat_id, billable=billable))

    async def clear_override(self, beat_id: str) -> None:
        """Return a beat to its project's rule. Idempotent: whether or not
        there was an override, or a beat, the answer is the same."""
        await self.overrides.delete(beat_id)

    # ------------------------------------------------------------------ #
    # Reports
    # ------------------------------------------------------------------ #

    async def period(self, first: date, last: date, tz: ZoneInfo) -> BillingPeriod:
        """Every client's figures for the days `first` through `last` in `tz`
        (`assemble_billing`). One read each of the clients, the billings,
        the projects (archived ones too), the beats started in the range and
        their overrides. The beats read are those of every billed or
        freelance project, so the freelance hours no client is billed for
        can be listed as `unattached`."""
        clients = await self.clients.list_all()
        projects = {
            project.id: project
            for project in [
                *await self.projects.list(archived=False),
                *await self.projects.list(archived=True),
            ]
            if project.id is not None
        }
        # A billing whose project has gone has no name to report under.
        billings = [b for b in await self.billings.list_all() if b.project_id in projects]
        wanted = {billing.project_id for billing in billings} | {
            project_id
            for project_id, project in projects.items()
            if project.kind is ProjectKind.FREELANCE
        }
        start, end = utc_range(first, last, tz)
        beats = await self.beats.list_started_between(sorted(wanted), start, end)
        overrides = await self.overrides.list_for(beat.id for beat in beats if beat.id is not None)
        return assemble_billing(
            clients,
            billings,
            projects,
            beats,
            {override.beat_id: override.billable for override in overrides},
            first,
            last,
            tz,
        )

    async def month(self, month: date, tz: ZoneInfo) -> BillingPeriod:
        """`period` over `month` (its 1st): the whole month once it has
        ended, through today in `tz` while it runs, 409 MONTH_NOT_STARTED
        after that."""
        first, last = month_range(month, self._now(tz).date())
        return await self.period(first, last, tz)

    # ------------------------------------------------------------------ #
    # Restore, for import: every rule was checked before the first write
    # ------------------------------------------------------------------ #

    async def restore_client(self, client: Client) -> None:
        """Write a client read from a backup, keeping its id and its archive
        flag. Not gated: a restore puts back what was."""
        await self.clients.restore(client)

    async def restore_project_billing(self, billing: ProjectBilling) -> None:
        """Write a project's billing read from a backup. Not gated, and the
        client may be archived."""
        await self.billings.upsert(billing)

    async def restore_override(self, override: BillableOverride) -> None:
        """Write a billable override read from a backup."""
        await self.overrides.upsert(override)
