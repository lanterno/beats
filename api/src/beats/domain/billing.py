"""The billing arithmetic: what each client is owed for a stretch of days.

Pure functions over what the service has already fetched — the clients,
their projects' billing, the projects, the beats in the range and the
overrides on them. Nothing here reads a clock: the range arrives as `first`
through `last`, and the closed past as `month_start`. The rules are
docs/billing.md's:

    for a finished beat b on a billed project, d = the local day b started on:
        term     = the project's term in force on d       (none before the first)
        billable = the override on b if there is one, else term.billable,
                   else False
        rate     = term.rate_minor if the term has one     source "project"
                   else the client's rate in force on d    source "client"
                   else unpriced                           no rate, no source

    a line   = a run of consecutive days of one project over which (rate,
               source) holds, kept when billable entries fall in it
    hours    = Σ (end − start) of its billable entries, to 0.01 h, half-up
    amount   = hours × rate, to a whole minor unit, half-up; None unpriced

Neither level reaches back before its first term. A beat belongs whole to
the day it started on in the request's timezone, and that day picks both its
month and its rate. A running beat is left out — a billed figure must not
move between two reads with no edit between them — and sets `running`
instead; the ledger counts it up to now on purpose, and billing differs.

Money is integer minor units, worked in `Decimal` and rounded once per line,
so a line's printed hours times its printed rate is its printed amount, and
every total is a sum of lines: a report adds up to the minor unit, as an
invoice does.
"""

from collections import defaultdict
from collections.abc import Container, Iterable, Iterator, Mapping, Sequence
from datetime import UTC, date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum
from itertools import groupby
from typing import NamedTuple, Protocol
from zoneinfo import ZoneInfo

from beats.domain.currencies import minor_units
from beats.domain.exceptions import MonthNotStarted
from beats.domain.models import Beat, Client, Project, ProjectBilling, ProjectKind
from beats.domain.timesheet import month_end
from beats.domain.utils import local_date

_MICROSECOND = timedelta(microseconds=1)
_MICROSECONDS_PER_HOUR = 3_600_000_000
_HUNDREDTH = Decimal("0.01")
_ZERO_HOURS = Decimal("0.00")


class RateSource(StrEnum):
    """Which level a line's rate comes from."""

    PROJECT = "project"  # the project term's own rate
    CLIENT = "client"  # the client's default rate in force that day


class _Dated(Protocol):
    @property
    def effective_from(self) -> date: ...


def in_force_on[T: _Dated](terms: Sequence[T], day: date) -> T | None:
    """The term in force on `day`: the latest whose `effective_from` is not
    after it, as `Contract.term_on`. None before the first."""
    current: T | None = None
    for term in terms:  # the validators keep these ascending
        if term.effective_from > day:
            break
        current = term
    return current


class DayRate(NamedTuple):
    rate_minor: int | None  # None: unpriced
    source: RateSource | None


_UNPRICED = DayRate(None, None)


def rate_on(client: Client, billing: ProjectBilling, day: date) -> DayRate:
    """What a billable hour of `billing`'s project earns on `day` — whether
    or not that day's term is billable, since an override can bill an entry
    its term does not."""
    term = in_force_on(billing.terms, day)
    if term is not None and term.rate_minor is not None:
        return DayRate(term.rate_minor, RateSource.PROJECT)
    rate = in_force_on(client.rates, day)
    if rate is not None:
        return DayRate(rate.rate_minor, RateSource.CLIENT)
    return _UNPRICED


class Resolved(NamedTuple):
    billable: bool
    rate_minor: int | None  # None when not billable, or unpriced
    source: RateSource | None


def resolve_entry(
    client: Client, billing: ProjectBilling, day: date, override: bool | None
) -> Resolved:
    """An entry started on local day `day`: the override if there is one,
    else the project's term in force, else not billable; and when billable,
    the rate it earns."""
    if override is None:
        term = in_force_on(billing.terms, day)
        billable = term is not None and term.billable
    else:
        billable = override
    if not billable:
        return Resolved(False, None, None)
    rate = rate_on(client, billing, day)
    return Resolved(True, rate.rate_minor, rate.source)


def hours_of(microseconds: int) -> Decimal:
    """An exact duration as hours to the hundredth, half-up: 18 s is 0.01 h,
    where `round`, half to even, would make it 0."""
    return (Decimal(microseconds) / _MICROSECONDS_PER_HOUR).quantize(_HUNDREDTH, ROUND_HALF_UP)


def amount_of(hours: Decimal, rate_minor: int) -> int:
    """Rounded hours at a rate, to a whole minor unit, half-up."""
    return int((hours * rate_minor).quantize(Decimal(1), ROUND_HALF_UP))


def _microseconds(start: datetime, end: datetime) -> int:
    # In UTC: two datetimes in one zone subtract on the wall clock, which
    # would lose or gain the hour the clocks change by. Negative for an end
    # before its start, which POST /api/beats/ and a restore both take: the
    # callers leave such a beat out, so it cannot take time, and money, off
    # the beats beside it.
    return (end.astimezone(UTC) - start.astimezone(UTC)) // _MICROSECOND


def month_range(month: date, today: date) -> tuple[date, date]:
    """The days of `month` a report covers: the 1st through its last day, or
    through `today` in the current month. `MonthNotStarted` after that."""
    if month > today.replace(day=1):
        raise MonthNotStarted(month)
    return month, min(month_end(month), today)


def utc_midnight(day: date, tz: ZoneInfo) -> datetime:
    """The instant `day` starts in `tz`, in UTC. East of Greenwich, 1 January
    of year 1 starts before the first instant UTC can hold, and nothing
    started before that, so it is that instant (`MonthQuery` takes 0001-01)."""
    try:
        return datetime.combine(day, time(), tz).astimezone(UTC)
    except OverflowError:
        return datetime.min.replace(tzinfo=UTC)


def utc_range(first: date, last: date, tz: ZoneInfo) -> tuple[datetime, datetime]:
    """The instants the days `first` through `last` span in `tz`, as
    [start, end) in UTC: local midnight to local midnight, whatever the
    offset did between."""
    return utc_midnight(first, tz), utc_midnight(last + timedelta(days=1), tz)


class BillingLine(NamedTuple):
    """A run of consecutive days of one project at one rate from one source."""

    project_id: str
    project_name: str
    rate_minor: int | None  # None: unpriced
    source: RateSource | None
    first: date  # the run's days within the range
    last: date
    hours: Decimal
    amount_minor: int | None  # None with the rate


class BillingEntry(NamedTuple):
    """A finished beat of a billed project, billable or not."""

    beat_id: str | None
    project_id: str
    day: date  # the local day it started on, which decides its month and rate
    start: datetime
    end: datetime
    hours: Decimal  # for display only: the lines are the figures
    billable: bool
    overridden: bool  # an override decides it, not the project's term
    rate_minor: int | None  # None when not billable, or unpriced


class ClientBilling(NamedTuple):
    """One client's figures for a range, in its one currency."""

    client_id: str | None
    name: str
    archived: bool
    currency: str
    minor_units: int
    running: bool  # a billable timer is running; it counts once stopped
    billable_hours: Decimal  # Σ line hours, priced or not
    non_billable_hours: Decimal  # rounded once, from its own exact sum
    unpriced_hours: Decimal  # Σ unpriced line hours: a part of billable_hours
    amount_minor: int  # Σ priced line amounts
    lines: list[BillingLine]
    entries: list[BillingEntry]


class CurrencyTotal(NamedTuple):
    """Every listed client in one currency, summed. There is no exchange rate,
    so no figure ever holds two currencies."""

    currency: str
    minor_units: int
    billable_hours: Decimal
    unpriced_hours: Decimal
    amount_minor: int


class UnattachedHours(NamedTuple):
    """A freelance project with finished hours in the range and no client:
    hours in no figure of the report."""

    project_id: str
    name: str
    hours: Decimal


class BillingPeriod(NamedTuple):
    first: date
    last: date
    totals: list[CurrencyTotal]  # by currency code
    clients: list[ClientBilling]  # by name
    unattached: list[UnattachedHours]  # by name


def assemble_client(
    client: Client,
    billings: Iterable[ProjectBilling],
    projects: Mapping[str, Project],
    beats: Iterable[Beat],
    overrides: Mapping[str, bool],
    first: date,
    last: date,
    tz: ZoneInfo,
) -> ClientBilling:
    """One client's figures for the days `first` through `last` in `tz`.

    Given only that client's inputs — its billings, their projects by id,
    their beats and those beats' overrides by beat id — so a reader of one
    client (1c's report link) cannot reach another's. A beat of a project not
    billed here, or started outside the range, is ignored: the range is read
    in UTC, and the local day is checked here, so the bucketing rule lives in
    one place.
    """
    by_project = {billing.project_id: billing for billing in billings}
    running = False
    entries: list[BillingEntry] = []
    billable: dict[tuple[str, date], int] = defaultdict(int)  # (project, day) -> µs
    non_billable = 0
    for beat in sorted(beats, key=lambda beat: beat.start):
        billing = by_project.get(beat.project_id)
        day = local_date(beat.start, tz)
        if billing is None or not first <= day <= last:
            continue
        override = overrides.get(beat.id) if beat.id is not None else None
        resolved = resolve_entry(client, billing, day, override)
        if beat.end is None:
            running = running or resolved.billable
            continue
        length = _microseconds(beat.start, beat.end)
        if length < 0:
            continue  # an end before its start: no time worked (`_microseconds`)
        if resolved.billable:
            billable[beat.project_id, day] += length
        else:
            non_billable += length
        entries.append(
            BillingEntry(
                beat_id=beat.id,
                project_id=beat.project_id,
                day=day,
                start=beat.start,
                end=beat.end,
                hours=hours_of(length),
                billable=resolved.billable,
                overridden=override is not None,
                rate_minor=resolved.rate_minor,
            )
        )

    days = [first + timedelta(days=n) for n in range((last - first).days + 1)]
    lines = [
        line
        for billing in by_project.values()
        for line in _lines(client, billing, projects[billing.project_id].name, days, billable)
    ]
    lines.sort(key=lambda line: (line.project_name.casefold(), line.first, line.project_id))
    return ClientBilling(
        client_id=client.id,
        name=client.name,
        archived=client.archived,
        currency=client.currency,
        minor_units=minor_units(client.currency),
        running=running,
        billable_hours=sum((line.hours for line in lines), _ZERO_HOURS),
        non_billable_hours=hours_of(non_billable),
        unpriced_hours=sum((line.hours for line in lines if line.rate_minor is None), _ZERO_HOURS),
        amount_minor=sum(line.amount_minor for line in lines if line.amount_minor is not None),
        lines=lines,
        entries=entries,
    )


def _lines(
    client: Client,
    billing: ProjectBilling,
    name: str,
    days: list[date],
    billable: Mapping[tuple[str, date], int],
) -> Iterator[BillingLine]:
    """The project's runs of days at one (rate, source) — 85, 95, then 85
    again is three lines — keeping those with billable entries."""
    project_id = billing.project_id
    for rate, run in groupby(days, key=lambda day: rate_on(client, billing, day)):
        run_days = list(run)
        worked = [billable[project_id, day] for day in run_days if (project_id, day) in billable]
        if not worked:
            continue
        hours = hours_of(sum(worked))
        yield BillingLine(
            project_id=project_id,
            project_name=name,
            rate_minor=rate.rate_minor,
            source=rate.source,
            first=run_days[0],
            last=run_days[-1],
            hours=hours,
            amount_minor=amount_of(hours, rate.rate_minor) if rate.rate_minor is not None else None,
        )


def assemble_billing(
    clients: Iterable[Client],
    billings: Iterable[ProjectBilling],
    projects: Mapping[str, Project],
    beats: Iterable[Beat],
    overrides: Mapping[str, bool],
    first: date,
    last: date,
    tz: ZoneInfo,
) -> BillingPeriod:
    """Every client's figures for the days `first` through `last` in `tz`, one
    `assemble_client` each, with per-currency totals and the freelance hours
    no client is billed for.

    Listed: every active client, with hours or without, and an archived one
    with entries in the range. A currency has a totals row when a listed
    client in it has a line. `projects` (by id, archived ones included) and
    `beats` must cover every freelance project, billed or not, for
    `unattached` to be whole.
    """
    billings = list(billings)
    beats = list(beats)
    billings_of: dict[str | None, list[ProjectBilling]] = defaultdict(list)
    for billing in billings:
        billings_of[billing.client_id].append(billing)
    beats_of: dict[str, list[Beat]] = defaultdict(list)
    for beat in beats:
        beats_of[beat.project_id].append(beat)

    reports: list[ClientBilling] = []
    for client in clients:
        own = billings_of.get(client.id, [])
        own_beats = [beat for billing in own for beat in beats_of.get(billing.project_id, [])]
        report = assemble_client(
            client,
            own,
            {billing.project_id: projects[billing.project_id] for billing in own},
            own_beats,
            {
                beat.id: overrides[beat.id]
                for beat in own_beats
                if beat.id is not None and beat.id in overrides
            },
            first,
            last,
            tz,
        )
        if report.entries or not client.archived:
            reports.append(report)
    reports.sort(key=lambda report: (report.name.casefold(), report.client_id or ""))

    by_currency: dict[str, list[ClientBilling]] = defaultdict(list)
    for report in reports:
        if report.lines:
            by_currency[report.currency].append(report)
    totals = [
        CurrencyTotal(
            currency=currency,
            minor_units=rows[0].minor_units,
            billable_hours=sum((row.billable_hours for row in rows), _ZERO_HOURS),
            unpriced_hours=sum((row.unpriced_hours for row in rows), _ZERO_HOURS),
            amount_minor=sum(row.amount_minor for row in rows),
        )
        for currency, rows in sorted(by_currency.items())
    ]

    billed = {billing.project_id for billing in billings}
    unbilled: dict[str, int] = defaultdict(int)
    for beat in beats:
        project = projects.get(beat.project_id)
        if (
            beat.end is None
            or beat.project_id in billed
            or project is None
            or project.kind is not ProjectKind.FREELANCE
            or not first <= local_date(beat.start, tz) <= last
        ):
            continue
        unbilled[beat.project_id] += max(_microseconds(beat.start, beat.end), 0)
    unattached = sorted(
        (
            UnattachedHours(project_id, projects[project_id].name, hours_of(length))
            for project_id, length in unbilled.items()
            if length
        ),
        key=lambda row: (row.name.casefold(), row.project_id),
    )
    return BillingPeriod(first, last, totals, reports, unattached)


def past_change[T: _Dated](old: Sequence[T], new: Sequence[T], month_start: date) -> date | None:
    """The first day before `month_start` whose figures going from the `old`
    terms to the `new` ones can move; None when it moves none.

    It compares the term lists alone and reads no beats: a term added,
    removed, or changed in its rate, its flag or its date counts from its
    date. A term dated in the current month never counts — that month has
    not been invoiced. False positives are accepted: a past term may differ
    with no hours under it, and what that costs is one confirmation.
    """
    before = {term.effective_from: term for term in old if term.effective_from < month_start}
    after = {term.effective_from: term for term in new if term.effective_from < month_start}
    return min(
        (day for day in before.keys() | after.keys() if before.get(day) != after.get(day)),
        default=None,
    )


def link_change(terms: Sequence[_Dated], month_start: date) -> date | None:
    """`past_change` for a write that moves every term at once — a project
    moved to another client, or its billing stopped: from the earliest term
    dated before `month_start`, None when there is none. `marked_change` is
    the other half of what such a write moves."""
    return min(
        (term.effective_from for term in terms if term.effective_from < month_start), default=None
    )


def marked_change(
    beats: Iterable[Beat], marked: Container[str | None], month_start: date, tz: ZoneInfo
) -> date | None:
    """The earliest local day before `month_start` that a finished beat in
    `beats` whose id is `marked` (billable by an override) started on; None
    when there is none.

    An override bills its entry whatever the terms say, before the first
    one too, so a project billed from this month on can have past figures
    that no term is dated under: a write that moves every term at once moves
    those as well.
    """
    return min(
        (
            day
            for beat in beats
            if beat.id in marked
            and beat.end is not None
            and _microseconds(beat.start, beat.end) >= 0
            and (day := local_date(beat.start, tz)) < month_start
        ),
        default=None,
    )
