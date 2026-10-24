"""Clients, project billing, billable overrides and billing budgets: the
writes and their rules, and the reports the arithmetic in
`domain/billing.py` and `domain/billing_budgets.py` makes of them.

Every store here is user-scoped, so someone else's client, project or beat
is not found (404) rather than forbidden. The rules a write must satisfy
beyond the models' own validators are checked here, not on the models: a
model is re-validated on every read, and a rule that later started failing
there would make every stored record unreadable (`_check_contract` and
`check_region` keep a contract's the same way).

A write that would change billable figures before the current month, in
the request's timezone, needs `rewrite_past` (`past_change`, `link_change`,
`marked_change`): those months may have been invoiced. Attaching a project
for the first time is not gated, since no figure existed, and neither is an
override — editing a past entry is itself the consent. Nor is a billing
budget: it changes no billable figure, and only its current period is read.
"""

import secrets
from collections.abc import Callable, Generator, Iterable, Sequence
from contextlib import contextmanager
from datetime import UTC, date, datetime, timedelta
from typing import NamedTuple
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from beats.domain.billing import (
    BillingPeriod,
    ClientBilling,
    assemble_billing,
    assemble_client,
    link_change,
    marked_change,
    month_range,
    past_change,
    utc_midnight,
    utc_range,
)
from beats.domain.billing_budgets import (
    BillingBudgetStatus,
    billing_budget_days,
    billing_budget_status,
)
from beats.domain.currencies import check_currency
from beats.domain.exceptions import (
    BeatNotFound,
    BillingBudgetCurrencyMismatch,
    BillingBudgetNeedsBilling,
    ClientHasProjects,
    ClientNotFound,
    CurrencyInUse,
    CurrencyMismatch,
    DomainException,
    NotFreelance,
    OrganisationProject,
    ProjectHasBilling,
    ProjectHasBillingBudget,
    ProjectNotBilled,
    ReportNotFound,
    RetroactiveChange,
    UnknownTimezone,
)
from beats.domain.models import (
    Beat,
    BillableOverride,
    BillingBudget,
    BillingBudgetFields,
    BillingBudgetScope,
    BillingBudgetUnit,
    BillingTerm,
    Client,
    ClientFields,
    Project,
    ProjectBilling,
    ProjectKind,
    ReportLink,
    ReportLinkFields,
)
from beats.domain.ports import (
    BillableOverrideStore,
    BillingBeatReader,
    BillingBudgetStore,
    BillingProjectReader,
    ClientStore,
    ProjectBillingStore,
    ReportLinkStore,
)


class ClientRecord(NamedTuple):
    client: Client
    # Something is priced in its currency — a rate of its own, or of one of
    # its projects' — or a money billing budget on it or one of its projects
    # is in it, so the currency can no longer change (CURRENCY_IN_USE).
    currency_locked: bool


class BilledProject(NamedTuple):
    billing: ProjectBilling
    client: Client  # for the currency the terms' rates are in


class BillingBudgetRecord(NamedTuple):
    budget: BillingBudget
    client: Client  # the scope's, for the currency a money limit is in


def _priced(billings: Iterable[ProjectBilling]) -> bool:
    return any(term.rate_minor is not None for billing in billings for term in billing.terms)


def _money_billing_budget(budget: BillingBudget | None) -> bool:
    return budget is not None and budget.unit is BillingBudgetUnit.MONEY


def _locked(
    client: Client, billings: Iterable[ProjectBilling], budgets: Iterable[BillingBudget]
) -> bool:
    """Whether something is priced in `client`'s currency, among `billings`,
    or a money budget among `budgets` is in it: one on the client, or on a
    project billed to it."""
    own = [billing for billing in billings if billing.client_id == client.id]
    billed = {billing.project_id for billing in own}
    return (
        bool(client.rates)
        or _priced(own)
        or any(
            _money_billing_budget(budget)
            and (
                budget.scope_id == client.id
                if budget.scope is BillingBudgetScope.CLIENT
                else budget.scope_id in billed
            )
            for budget in budgets
        )
    )


def _check_move(
    previous: Client,
    client: Client,
    terms: Iterable[BillingTerm],
    month_start: date,
    *,
    marked: bool,
    money_billing_budget: bool,
) -> None:
    """CURRENCY_MISMATCH for a project's billing moved from `previous` to
    `client` in another currency, while the project has a money billing
    budget (`money_billing_budget`: checked first, so the 409 names it), or
    the terms it would have there carry a rate of their own, or a billable
    term dated before `month_start`, or while an entry before it is marked
    billable (`marked`)."""
    if previous.currency == client.currency:
        return
    if money_billing_budget:
        raise BillingBudgetCurrencyMismatch(previous.currency)
    if marked or any(
        term.rate_minor is not None or (term.billable and term.effective_from < month_start)
        for term in terms
    ):
        raise CurrencyMismatch()


def _earliest(*days: date | None) -> date | None:
    return min((day for day in days if day is not None), default=None)


@contextmanager
def _naming(record: str) -> Generator[None]:
    """A refusal raised inside, its detail prefixed with the backup record it
    is about (`project_billing.0: …`), as a 422 names a field."""
    try:
        yield
    except DomainException as exc:
        exc.message = f"{record}: {exc.message}"
        exc.args = (exc.message,)
        raise


class BillingService:
    """Clients and what is billed to them.

    The clock is read for one thing, "today in the request's timezone":
    its month's 1st is where the closed past ends and where a report's
    current month stops, and it is the day a billing budget is read on; a
    test hands in a fixed instant, as it does to `ContractService`.
    """

    def __init__(
        self,
        clients: ClientStore,
        billings: ProjectBillingStore,
        overrides: BillableOverrideStore,
        projects: BillingProjectReader,
        beats: BillingBeatReader,
        budgets: BillingBudgetStore,
        links: ReportLinkStore,
        now: Callable[[ZoneInfo], datetime] = datetime.now,
    ):
        self.clients = clients
        self.billings = billings
        self.overrides = overrides
        self.projects = projects
        self.beats = beats
        self.budgets = budgets
        self.links = links
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
        budgets = await self.budgets.list_all()
        records = [ClientRecord(client, _locked(client, billings, budgets)) for client in clients]
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
        - The currency cannot change once something is priced in it, or a
          money billing budget is in it (409 CURRENCY_IN_USE). Before that, a
          typo made at creation can still be fixed.
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
        CLIENT_HAS_PROJECTS — archive it instead. Its billing budget and its
        report links go with it: with nothing billed the budget counts
        nothing, and a link whose client has gone must not linger as a live
        URL. Both are deleted first, so a failure between leaves a client
        without them, never either without its client."""
        await self.clients.get_by_id(client_id)
        if await self.billings.list_by_client(client_id):
            raise ClientHasProjects()
        await self.budgets.delete(BillingBudgetScope.CLIENT, client_id)
        await self.links.delete_for_client(client_id)
        await self.clients.delete(client_id)

    async def _record(self, client: Client) -> ClientRecord:
        if client.rates or client.id is None:
            return ClientRecord(client, bool(client.rates))
        billings = await self.billings.list_by_client(client.id)
        return ClientRecord(client, _locked(client, billings, await self.budgets.list_all()))

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
          CURRENCY_MISMATCH) while it has a money billing budget, or the
          terms it would have there carry a rate of their own, or a billable
          term dated before the current month, or while an entry before it
          is marked billable: the limit and the rate were entered in the old
          currency, and the past hours were billed in it. Terms that drop
          both, with no such mark or budget, move nothing.
        - Attaching it the first time is not gated. Otherwise a change to the
          terms dated before the current month, or any move to another
          client while a term is dated there or an entry there is marked
          billable, needs `rewrite_past` (409 RETROACTIVE_CHANGE).
        """
        project = await self.projects.get_by_id(project_id)
        if project.kind is not ProjectKind.FREELANCE:
            raise NotFreelance()
        if project.organisation is not None:
            # Billing is the person's own; an organisation's project is
            # billed by nobody here (docs/organisations.md).
            raise OrganisationProject()
        client = await self.clients.get_by_id(client_id)
        stored = await self.billings.get(project_id)
        month_start = self._month_start(tz)
        if stored is not None:
            changes = [past_change(stored.terms, terms, month_start)]
            if stored.client_id != client_id:
                previous = await self.clients.get_by_id(stored.client_id)
                marked = await self._marked_change(project_id, month_start, tz)
                budget = await self.budgets.get(BillingBudgetScope.PROJECT, project_id)
                _check_move(
                    previous,
                    client,
                    terms,
                    month_start,
                    marked=marked is not None,
                    money_billing_budget=_money_billing_budget(budget),
                )
                changes += [link_change([*stored.terms, *terms], month_start), marked]
            self._gate(_earliest(*changes), rewrite_past)
        billing = await self.billings.upsert(
            ProjectBilling(project_id=project_id, client_id=client_id, terms=terms)
        )
        return BilledProject(billing, client)

    async def remove_project_billing(
        self, project_id: str, *, rewrite_past: bool, remove_billing_budget: bool, tz: ZoneInfo
    ) -> None:
        """Stop billing a project: its hours are in no client's figures from
        then on, in every month. Checked in this order, so a refusal leaves
        both records in place:

        - 404 when it is not billed;
        - with a billing budget, 409 PROJECT_HAS_BILLING_BUDGET unless
          `remove_billing_budget`: the budget goes with the billing, and is
          never lost without being named;
        - a term dated before the current month, or an entry there marked
          billable, needs `rewrite_past` (409 RETROACTIVE_CHANGE).

        The budget is deleted before the billing, so a failure between the
        two leaves a billed project without its budget, never a budget on a
        project that is not billed."""
        stored = await self.billings.get(project_id)
        if stored is None:
            raise ProjectNotBilled()
        budget = await self.budgets.get(BillingBudgetScope.PROJECT, project_id)
        if budget is not None and not remove_billing_budget:
            raise ProjectHasBillingBudget((await self.projects.get_by_id(project_id)).name)
        month_start = self._month_start(tz)
        self._gate(
            _earliest(
                link_change(stored.terms, month_start),
                await self._marked_change(project_id, month_start, tz),
            ),
            rewrite_past,
        )
        if budget is not None:
            await self.budgets.delete(BillingBudgetScope.PROJECT, project_id)
        await self.billings.delete(project_id)

    async def _marked_change(
        self,
        project_id: str,
        month_start: date,
        tz: ZoneInfo,
        beats: Sequence[Beat] = (),
        overrides: Sequence[BillableOverride] = (),
    ) -> date | None:
        """`marked_change` for one project: the earliest day before
        `month_start` with an entry of it marked billable, None when there
        is none. A backup's `beats` and `overrides` are laid over the
        account's, as its restore would leave them. The overrides are read
        first, a small set; the project's beats before the month only when
        one of them marks an entry billable."""
        marks = {
            override.beat_id: override.billable for override in await self.overrides.list_all()
        }
        marks.update((override.beat_id, override.billable) for override in overrides)
        marked = {beat_id for beat_id, billable in marks.items() if billable}
        if not marked:
            return None
        stored = await self.beats.list_started_between(
            [project_id], datetime.min.replace(tzinfo=UTC), utc_midnight(month_start, tz)
        )
        merged = {beat.id: beat for beat in [*stored, *beats]}
        return marked_change(
            (beat for beat in merged.values() if beat.project_id == project_id),
            marked,
            month_start,
            tz,
        )

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

    async def client_period(
        self, client: Client, first: date, last: date, tz: ZoneInfo
    ) -> ClientBilling:
        """One client's figures for `first` through `last` in `tz`, from that
        client's inputs alone (`assemble_client`).

        What a report link is served by, so what it reads is the whole of its
        privacy story. It never calls `period`, which assembles every client
        and would leave the public route filtering a list it should never
        have been handed: a reader of one client cannot reach another's
        because the query for another's is never made. The projects are
        narrowed to this client's billed ones before the assembler sees them,
        so no other project's name is in reach either.

        The client is passed in rather than fetched by id: the public caller
        has already resolved it, and a service method that took an id could
        be called with one the reader never named.
        """
        billings = await self.billings.list_by_client(client.id or "")
        wanted = {billing.project_id for billing in billings}
        projects = {
            project.id: project
            for project in [
                *await self.projects.list(archived=False),
                *await self.projects.list(archived=True),
            ]
            if project.id is not None and project.id in wanted
        }
        # A billing whose project has gone has no name to report under.
        billings = [billing for billing in billings if billing.project_id in projects]
        start, end = utc_range(first, last, tz)
        beats = (
            await self.beats.list_started_between(sorted(projects), start, end) if projects else []
        )
        overrides = await self.overrides.list_for(beat.id for beat in beats if beat.id is not None)
        return assemble_client(
            client,
            billings,
            projects,
            beats,
            {override.beat_id: override.billable for override in overrides},
            first,
            last,
            tz,
        )

    # ------------------------------------------------------------------ #
    # Report links
    # ------------------------------------------------------------------ #

    async def report_period(self, link: ReportLink) -> ClientBilling:
        """What a resolved report link serves: its client's figures over its
        frozen range, in its frozen zone.

        The link's own client is the only one fetched, and a client deleted
        since the link was minted is `ReportNotFound` — the same answer an
        unknown token gets, because the reader has no session and must not
        learn from the difference.
        """
        try:
            client = await self.clients.get_by_id(link.client_id)
        except ClientNotFound:
            raise ReportNotFound() from None
        return await self.client_period(client, link.first, link.last, ZoneInfo(link.tz))

    async def list_report_links(self, client_id: str) -> list[ReportLink]:
        """One client's links, newest first. 404 for a client that is not the
        caller's, a malformed id included."""
        await self.clients.get_by_id(client_id)
        return await self.links.list_for_client(client_id)

    async def create_report_link(self, client_id: str, fields: ReportLinkFields) -> ReportLink:
        """Mint a link over a fixed range for one of the caller's clients.

        The range and its timezone are frozen here and never read again from
        the request: the days are bucketed in the owner's zone, because those
        are the days the owner invoices on. The zone is checked now rather
        than on the model, as a client's currency is — a zone leaving the tz
        database must not make a stored link unreadable.
        """
        await self.clients.get_by_id(client_id)
        try:
            ZoneInfo(fields.tz)
        except ZoneInfoNotFoundError, ValueError:
            raise UnknownTimezone(fields.tz) from None
        return await self.links.create(
            ReportLink(
                **fields.model_dump(),
                client_id=client_id,
                # 32 bytes, URL-safe. The whole secret of the link, stored as
                # it is read (docs/billing.md, 1c decision 1).
                token=secrets.token_urlsafe(32),
            )
        )

    async def delete_report_link(self, client_id: str, link_id: str) -> None:
        """Revoke a link: the record goes, and the URL is dead from the next
        read. 404 only for a client that is not the caller's — with no such
        link there is nothing left to clear."""
        await self.clients.get_by_id(client_id)
        await self.links.delete(client_id, link_id)

    # ------------------------------------------------------------------ #
    # Billing budgets
    # ------------------------------------------------------------------ #

    async def billing_budget_statuses(self, tz: ZoneInfo) -> list[BillingBudgetStatus]:
        """Every billing budget, read as of today in `tz`
        (`billing_budget_status`), by client name: a client's own budget
        first, then its projects' by project name.

        The budgets are read first, and with none nothing else is, so the
        read costs nothing for someone who never set one. Otherwise one read
        each of the clients, the billings, the projects (archived ones too),
        the beats of every project in a scope — over the union of the
        periods, running ones included — and their overrides. A budget whose
        client, project or billing has gone, which only a crash between two
        writes could leave, is skipped, as `period` skips such a billing.
        """
        budgets = await self.budgets.list_all()
        if not budgets:
            return []
        today = self._now(tz).date()
        clients = {client.id: client for client in await self.clients.list_all()}
        projects = {
            project.id: project
            for project in [
                *await self.projects.list(archived=False),
                *await self.projects.list(archived=True),
            ]
            if project.id is not None
        }
        billings = [
            billing
            for billing in await self.billings.list_all()
            if billing.project_id in projects and billing.client_id in clients
        ]
        billing_of = {billing.project_id: billing for billing in billings}

        # Each budget with its client and the billings in its scope.
        scoped: list[tuple[BillingBudget, Client, list[ProjectBilling]]] = []
        for budget in budgets:
            if budget.scope is BillingBudgetScope.CLIENT:
                client = clients.get(budget.scope_id)
                if client is None:
                    continue
                scope_billings = [b for b in billings if b.client_id == client.id]
            else:
                billing = billing_of.get(budget.scope_id)
                if billing is None:
                    continue
                client, scope_billings = clients[billing.client_id], [billing]
            scoped.append((budget, client, scope_billings))

        firsts = [
            days.first
            for days in (billing_budget_days(budget, today) for budget, _, _ in scoped)
            if not days.upcoming
        ]
        beats: list[Beat] = []
        if firsts:
            wanted = {b.project_id for _, _, scope_billings in scoped for b in scope_billings}
            beats = await self.beats.list_started_between(
                sorted(wanted),
                utc_midnight(min(firsts), tz),
                utc_midnight(today + timedelta(days=1), tz),
            )
        overrides = {
            override.beat_id: override.billable
            for override in await self.overrides.list_for(
                beat.id for beat in beats if beat.id is not None
            )
        }

        statuses: list[tuple[tuple[str, str, int, str, str], BillingBudgetStatus]] = []
        for budget, client, scope_billings in scoped:
            # An archived client, or an archived project with a budget, is
            # read but never alerts. An archived project still counts toward
            # its client's budget: it is billed.
            active = not client.archived and (
                budget.scope is BillingBudgetScope.CLIENT or not projects[budget.scope_id].archived
            )
            status = billing_budget_status(
                budget, client, scope_billings, projects, beats, overrides, today, tz, active
            )
            project_first = budget.scope is BillingBudgetScope.PROJECT
            key = (
                client.name.casefold(),
                client.id or "",
                int(project_first),
                status.name.casefold() if project_first else "",
                budget.scope_id,
            )
            statuses.append((key, status))
        return [status for _, status in sorted(statuses, key=lambda pair: pair[0])]

    async def set_billing_budget(
        self, scope: BillingBudgetScope, scope_id: str, fields: BillingBudgetFields
    ) -> BillingBudgetRecord:
        """Give a client, or a billed project, its billing budget, replacing
        the one it had.

        - The client, or the project, must be the caller's (404, the
          client's CLIENT_NOT_FOUND), a malformed id included. An archived
          client is allowed, as it is billed to: a restore may carry it.
        - A project must be billed (409 BILLING_BUDGET_NEEDS_BILLING): no
          figure on an unbilled one could spend it.

        Not gated: a budget changes no billable figure, and only the current
        period is ever read against it.
        """
        if scope is BillingBudgetScope.CLIENT:
            client = await self.clients.get_by_id(scope_id)
        else:
            await self.projects.get_by_id(scope_id)
            billing = await self.billings.get(scope_id)
            if billing is None:
                raise BillingBudgetNeedsBilling()
            client = await self.clients.get_by_id(billing.client_id)
        budget = await self.budgets.upsert(
            BillingBudget(**fields.model_dump(), scope=scope, scope_id=scope_id)
        )
        return BillingBudgetRecord(budget, client)

    async def remove_billing_budget(self, scope: BillingBudgetScope, scope_id: str) -> None:
        """Take a scope's billing budget away. Idempotent: whether or not
        there was one, or a scope, the answer is the same."""
        await self.budgets.delete(scope, scope_id)

    # ------------------------------------------------------------------ #
    # Restore, for import: every rule was checked before the first write
    # ------------------------------------------------------------------ #

    async def check_restore(
        self,
        projects: Sequence[Project],
        clients: Sequence[Client],
        billings: Sequence[ProjectBilling],
        budgets: Sequence[BillingBudget],
        beats: Sequence[Beat],
        overrides: Sequence[BillableOverride],
        tz: ZoneInfo,
    ) -> None:
        """The rules the client, billing and billing budget writes apply, run
        over what a backup would leave — its records over the account's —
        before any of it is written, so a file one of them refuses writes
        nothing. The first refusal is raised as its route raises it, its
        detail naming the record (`project_billing.0: …`).

        - A client's currency is one the table knows, when the client is new
          or its currency changes; as on `update_client`, a stored one is not
          checked again. It cannot change once something in the account is
          priced in it, or a money billing budget of the account's that the
          file does not replace is in it (CURRENCY_IN_USE).
        - A project the file moves away from freelance while the account
          bills it, and the file does not bill it anew, is
          PROJECT_HAS_BILLING, as `restore_project` would answer it.
        - Billing is on a project that is freelance as the file leaves it
          (NOT_FREELANCE), and billing the file moves to a client in another
          currency is held to `set_project_billing`'s rule (CURRENCY_MISMATCH),
          the file's beats and billable marks laid over the account's, and
          the account's money billing budget on the project counted unless
          the file carries the project's budget: a restore never deletes one.
          A file's own money budget was set under the file's client, so it
          agrees with the billing the file restores.
        - A billing budget on a project is on one the file or the account
          bills (BILLING_BUDGET_NEEDS_BILLING).

        That each billing's project and client, and each budget's scope, is
        in the file or the account is the import's to check first. The
        retroactive gate is not applied: a restore puts back what was.
        """
        stored_clients = {client.id: client for client in await self.clients.list_all()}
        stored_billings = {
            billing.project_id: billing for billing in await self.billings.list_all()
        }
        # The account's budgets the file leaves in place: an upsert by scope
        # replaces the rest.
        replaced = {(budget.scope, budget.scope_id) for budget in budgets}
        surviving = [
            budget
            for budget in await self.budgets.list_all()
            if (budget.scope, budget.scope_id) not in replaced
        ]
        kinds = {
            project.id: project.kind
            for project in [
                *await self.projects.list(archived=False),
                *await self.projects.list(archived=True),
                *projects,
            ]
        }
        merged = {**stored_clients, **{client.id: client for client in clients}}
        billed = {billing.project_id for billing in billings}
        month_start = self._month_start(tz)

        for i, client in enumerate(clients):
            with _naming(f"clients.{i}"):
                stored = stored_clients.get(client.id)
                if stored is None or client.currency != stored.currency:
                    check_currency(client.currency)
                if (
                    stored is not None
                    and client.currency != stored.currency
                    and _locked(stored, stored_billings.values(), surviving)
                ):
                    raise CurrencyInUse()

        for i, project in enumerate(projects):
            with _naming(f"projects.{i}"):
                if (
                    project.kind is not ProjectKind.FREELANCE
                    and project.id in stored_billings
                    and project.id not in billed
                ):
                    raise ProjectHasBilling()

        for i, billing in enumerate(billings):
            with _naming(f"project_billing.{i}"):
                if kinds.get(billing.project_id) is not ProjectKind.FREELANCE:
                    raise NotFreelance()
                before = stored_billings.get(billing.project_id)
                if before is not None and before.client_id != billing.client_id:
                    previous = stored_clients.get(before.client_id)
                    moved_to = merged.get(billing.client_id)
                    if (
                        previous is not None
                        and moved_to is not None
                        and previous.currency != moved_to.currency
                    ):
                        marked = await self._marked_change(
                            billing.project_id, month_start, tz, beats, overrides
                        )
                        _check_move(
                            previous,
                            moved_to,
                            billing.terms,
                            month_start,
                            marked=marked is not None,
                            money_billing_budget=any(
                                _money_billing_budget(budget)
                                and budget.scope is BillingBudgetScope.PROJECT
                                and budget.scope_id == billing.project_id
                                for budget in surviving
                            ),
                        )

        for i, budget in enumerate(budgets):
            with _naming(f"billing_budgets.{i}"):
                if (
                    budget.scope is BillingBudgetScope.PROJECT
                    and budget.scope_id not in billed
                    and budget.scope_id not in stored_billings
                ):
                    raise BillingBudgetNeedsBilling()

    async def restore_client(self, client: Client) -> None:
        """Write a client read from a backup, keeping its id and its archive
        flag. Not gated: a restore puts back what was."""
        await self.clients.restore(client)

    async def restore_project_billing(self, billing: ProjectBilling) -> None:
        """Write a project's billing read from a backup. Not gated, and the
        client may be archived."""
        await self.billings.upsert(billing)

    async def restore_billing_budget(self, budget: BillingBudget) -> None:
        """Write a billing budget read from a backup, replacing the one on its
        scope. Not gated, as no budget write is."""
        await self.budgets.upsert(budget)

    async def restore_override(self, override: BillableOverride) -> None:
        """Write a billable override read from a backup."""
        await self.overrides.upsert(override)
