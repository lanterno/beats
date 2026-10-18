"""The persistence shapes the domain asks for, declared where they are used.

Two things follow from putting them here rather than importing repository
interfaces from `beats.infrastructure`. The dependency points inward — domain
code no longer reaches out to the layer that is supposed to implement it — and
each protocol lists only the methods its consumer actually calls, so a service
that reads completed beats cannot quietly start writing them.

That narrowness is also what lets the test suite's in-memory fakes stand in.
`AnalyticsService` needs two methods; asking for a whole `BeatRepository` meant
every fake either implemented twelve or lied about its type.

`MongoBeatRepository` and `MongoProjectRepository` satisfy these structurally —
there is nothing to register.
"""

import builtins
from collections.abc import Collection, Iterable
from datetime import date, datetime
from typing import Protocol
from zoneinfo import ZoneInfo

from beats.domain.models import (
    Absence,
    BalanceAdjustment,
    Beat,
    BillableOverride,
    BillingBudget,
    BillingBudgetScope,
    Client,
    ContractWeek,
    FlowWindow,
    Project,
    ProjectBilling,
)


class CompletedBeatReader(Protocol):
    """Read access to finished beats. Used by analytics and intelligence."""

    async def list_all_completed(self) -> list[Beat]: ...
    async def list_completed_in_range(self, start: date, end: date) -> list[Beat]: ...


class RangeBeatReader(Protocol):
    """Just the date-range read — all the intelligence services need."""

    async def list_completed_in_range(self, start: date, end: date) -> list[Beat]: ...


class ProjectLister(Protocol):
    """Read access to the project list."""

    # builtins.list because this class defines a method called `list`, which
    # would otherwise shadow the builtin in the annotation.
    async def list(self, archived: bool = False) -> builtins.list[Project]: ...


class FlowWindowReader(Protocol):
    """Flow windows over a time range."""

    async def list_by_range(self, start: datetime, end: datetime) -> list[FlowWindow]: ...


class TimerBeatStore(Protocol):
    """The four beat operations running a timer needs: open one, find the
    open one, find the last one, close it. `update` writes only the fields
    named, as `BeatStore.update` does."""

    async def create(self, beat: Beat) -> Beat: ...
    async def get_active(self) -> Beat | None: ...
    async def get_last(self) -> Beat: ...
    async def update(self, beat: Beat, fields: Collection[str]) -> Beat: ...


class TimerProjectReader(Protocol):
    """What the timer asks about a project before starting against it."""

    async def exists(self, project_id: str) -> bool: ...
    async def get_by_id(self, project_id: str) -> Project: ...


class BeatStore(Protocol):
    """CRUD over beats — what `BeatService` needs, not the twelve methods
    the Mongo repository happens to offer.

    `update` writes the named `fields` of `beat` onto the stored beat with its
    id and nothing else, and returns the beat as stored: a field the write
    does not name (the note an import brought) is never rebuilt from a
    partial model, nor reverted to what was read before an await. It raises
    `BeatNotFound` when the user has no beat with that id."""

    async def get_by_id(self, beat_id: str) -> Beat: ...
    async def create(self, beat: Beat) -> Beat: ...
    async def update(self, beat: Beat, fields: Collection[str]) -> Beat: ...
    async def delete(self, beat_id: str) -> bool: ...
    # builtins.list because this class defines a method called `list`.
    async def list(
        self, project_id: str | None = None, date_filter: date | None = None
    ) -> builtins.list[Beat]: ...


class ProjectStore(Protocol):
    """CRUD over projects, plus the list read `ProjectLister` also offers."""

    async def get_by_id(self, project_id: str) -> Project: ...
    async def create(self, project: Project) -> Project: ...
    async def update(self, project: Project) -> Project: ...
    async def list(self, archived: bool = False) -> builtins.list[Project]: ...


class ProjectBeatReader(Protocol):
    """One project's beats. All `ProjectService` asks of beat storage."""

    async def list_by_project(self, project_id: str) -> list[Beat]: ...


class ProjectReader(Protocol):
    """One project by id. What the contract service asks before doing anything
    to a project: it reads the kind and the contract, and never writes."""

    async def get_by_id(self, project_id: str) -> Project: ...


class AbsenceStore(Protocol):
    """Absences on one project: the range read the arithmetic needs, and the
    two writes a calendar makes. Upsert is keyed on (project, date) — a
    second absence on a day replaces the first. Delete is by id within the
    project, so False means "not on this project"."""

    async def list_by_project(self, project_id: str, start: date, end: date) -> list[Absence]: ...
    async def upsert(self, absence: Absence) -> Absence: ...
    async def delete(self, project_id: str, absence_id: str) -> bool: ...


class AdjustmentStore(Protocol):
    """Balance adjustments on one project: the range read the balance needs,
    and the two writes the ledger makes. Upsert is keyed on (project, date),
    as an absence's is — a second adjustment on a day replaces the first.
    Delete is by id within the project, so False means "not on this
    project"."""

    async def list_by_project(
        self, project_id: str, start: date, end: date
    ) -> list[BalanceAdjustment]: ...
    async def upsert(self, adjustment: BalanceAdjustment) -> BalanceAdjustment: ...
    async def delete(self, project_id: str, adjustment_id: str) -> bool: ...


class ContractAdjustments(Protocol):
    """What a contract write asks of the balance adjustments: whether one
    sits at or after a day — so moving the first day later past it is
    refused rather than silently dropping it from the balance — and the
    purge when the contract goes, since an adjustment only means something
    against the balance of the contract it was made on."""

    async def earliest(self, project_id: str, on_or_after: date) -> date | None: ...
    async def delete_by_project(self, project_id: str) -> int: ...


class WeekExpectationReader(Protocol):
    """What a reader that quotes a week's figure needs of the contract: the
    hours it expects of that week after holidays and absences, or None when
    it expects nothing by nature (`ContractService.expected_for_week`). The
    Inbox's readers — the planning line, the pacing card, the stale-project
    card — read this and nothing else of a contract, and so, through
    `CoachContractReader`, does the coach's pattern tool."""

    async def expected_for_week(self, project: Project, week_of: date) -> float | None: ...


class ContractWeeksReader(Protocol):
    """What the coach's day context reads of a contract: the current week of
    each day job among `projects`, by project id, the same figures the page shows
    — and nothing unless `as_of` is today in `tz` by the reader's own clock
    (`ContractService.current_weeks`)."""

    async def current_weeks(
        self, projects: Iterable[Project], tz: ZoneInfo, as_of: date
    ) -> dict[str, ContractWeek]: ...


class CoachContractReader(ContractWeeksReader, WeekExpectationReader, Protocol):
    """Both of what the coach reads of a contract: the current weeks for the
    day context, and each week's adjusted expectation for the pattern tool,
    whose pacing and stale-project cards quote it as the Inbox's do.
    `ContractService` is both."""


class BillingPresence(Protocol):
    """Whether a project is billed — all `ProjectService` asks of billing,
    so a kind change away from freelance is refused while it is, rather than
    leaving money dormant on a project that cannot read it."""

    async def exists(self, project_id: str) -> bool: ...


class BillableOverrideRemover(Protocol):
    """The one billing write a beat's own deletion makes: its override goes
    with it. True when there was one."""

    async def delete(self, beat_id: str) -> bool: ...


class BillingBeatReader(Protocol):
    """What billing reads of beats: those of some projects started in a span
    of instants, running ones included, and whether a beat is the caller's
    at all. Nothing that writes one."""

    async def list_started_between(
        self, project_ids: Iterable[str], start: datetime, end: datetime
    ) -> list[Beat]: ...
    async def exists(self, beat_id: str) -> bool: ...


class BillingProjectReader(ProjectReader, ProjectLister, Protocol):
    """One project by id, for a billing write's kind check, and the list, for
    a report: archived projects included, since an archived project's hours
    in a month are still billed."""


class ClientStore(Protocol):
    """Clients: one by id, the list, and the writes the client routes make.
    `get_by_id` raises `ClientNotFound` for one that is not the caller's, a
    malformed id included."""

    async def get_by_id(self, client_id: str) -> Client: ...
    # builtins.list because this class defines a method called `list`.
    async def list(self, archived: bool = False) -> builtins.list[Client]: ...
    async def list_all(self) -> builtins.list[Client]: ...
    async def create(self, client: Client) -> Client: ...
    async def update(self, client: Client) -> Client: ...
    async def delete(self, client_id: str) -> bool: ...
    async def restore(self, client: Client) -> None: ...


class ProjectBillingStore(Protocol):
    """Project billing, one per project: upsert is keyed on the project, so
    a second write replaces the first."""

    async def get(self, project_id: str) -> ProjectBilling | None: ...
    async def list_all(self) -> list[ProjectBilling]: ...
    async def list_by_client(self, client_id: str) -> list[ProjectBilling]: ...
    async def upsert(self, billing: ProjectBilling) -> ProjectBilling: ...
    async def delete(self, project_id: str) -> bool: ...


class BillingBudgetStore(Protocol):
    """Billing budgets, one per scope: upsert is keyed on the scope, so a
    second write replaces the first. `list_all` is a small set, at most one
    per client and billed project."""

    async def list_all(self) -> list[BillingBudget]: ...
    async def get(self, scope: BillingBudgetScope, scope_id: str) -> BillingBudget | None: ...
    async def upsert(self, budget: BillingBudget) -> BillingBudget: ...
    async def delete(self, scope: BillingBudgetScope, scope_id: str) -> bool: ...


class BillableOverrideStore(Protocol):
    """Billable overrides, one per beat: upsert is keyed on the beat."""

    async def list_all(self) -> list[BillableOverride]: ...
    async def list_for(self, beat_ids: Iterable[str]) -> list[BillableOverride]: ...
    async def upsert(self, override: BillableOverride) -> BillableOverride: ...
    async def delete(self, beat_id: str) -> bool: ...
