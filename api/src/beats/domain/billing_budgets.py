"""The billing budget arithmetic: how much of a limit is spent, what is left,
and when it is about to run out (docs/billing.md, phase 1b).

Pure functions over what the service has already fetched, beside
`domain/billing.py` and made of it. Nothing here reads a clock: the day a
budget is read on arrives as `today`, in the request's timezone. The only
thing stored is the limit; everything below is worked out again on every
read, and none of it is stored, sent or acknowledged.

    the period    monthly: the calendar month that holds today, read
                  through today. total: from `starts_on` through today,
                  with no end; upcoming, with no figures, before it starts
    spent         Σ over the calendar months of the period of
                  `assemble_client` over that month's days in it — the
                  hours its lines bill (an hours budget) or their priced
                  amount (a money budget). Month by month and never as one
                  range, so a total agrees with the months invoiced to the
                  minor unit: a line is rounded once per month, as an
                  invoice rounds it
    state         used up at spent ≥ limit, near at spent × 100 ≥ warn ×
                  limit, else under; in integers — hundredths of an hour,
                  or minor units — never floats
    runs out on   today + ⌈remaining ÷ the pace of the last min(28, elapsed)
                  days⌉, when the guards in `runs_out_on` allow one

A running beat is in no figure, as in 1a: a budget agrees with the Clients
page line for line, and two reads with no edit between them agree. It is
answered with two instants instead (`running_crossings`), the moments at
which it alone would cross the warning and the limit, so the SPA only ever
compares a clock with an instant it was sent.
"""

from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from fractions import Fraction
from math import ceil
from typing import NamedTuple
from zoneinfo import ZoneInfo

from beats.domain.billing import assemble_client, resolve_entry
from beats.domain.currencies import minor_units
from beats.domain.models import (
    Beat,
    BillingBudget,
    BillingBudgetPeriod,
    BillingBudgetScope,
    BillingBudgetUnit,
    Client,
    Project,
    ProjectBilling,
)
from beats.domain.timesheet import month_end
from beats.domain.utils import local_date

_ZERO_HOURS = Decimal("0.00")
_MICROSECONDS_PER_HOUR = 3_600_000_000

# The pace is read over the last min(_PACE_DAYS, elapsed) days, and only
# once _PACE_FIRST_DAY days of the period have passed: a monthly budget
# first projects on the 7th. A date further out than _PROJECTION_DAYS is
# not a projection worth showing.
_PACE_DAYS = 28
_PACE_FIRST_DAY = 7
_PROJECTION_DAYS = 365


class BillingBudgetState(StrEnum):
    UNDER = "under"
    NEAR = "near"  # at or past the warning
    USED_UP = "used_up"  # at or past the limit; over is a negative remaining


class BillingBudgetDays(NamedTuple):
    first: date  # the period's first day
    last: date | None  # its last: a month's end, None on a total
    through: date | None  # the last day counted so far: today; None while upcoming
    upcoming: bool  # a total that starts after today


class BillingBudgetSpend(NamedTuple):
    billable_hours: Decimal  # Σ line hours, priced or not
    unpriced_hours: Decimal  # the part of them with no rate
    amount_minor: int  # Σ priced line amounts


class BillingBudgetRunning(NamedTuple):
    """A running beat that counts on the budget, and when it alone would
    cross each threshold. In UTC, off stored data only, so a DST change is
    just elapsed time and the instants do not move between reads."""

    project_id: str
    since: datetime
    priced: bool  # it has a rate on its start day
    near_at: datetime | None  # None once crossed, or unpriced under money
    over_at: datetime | None


class BillingBudgetStatus(NamedTuple):
    """One billing budget, read as of today."""

    scope: BillingBudgetScope
    scope_id: str
    client_id: str | None
    name: str  # the client's, or the project's
    active: bool  # its client, and its project, are not archived: only then does it alert
    currency: str
    minor_units: int
    unit: BillingBudgetUnit
    period: BillingBudgetPeriod
    limit_hours: Decimal | None
    limit_minor: int | None
    starts_on: date | None
    warn_at_percent: int
    upcoming: bool
    first: date
    last: date | None
    through: date | None
    billable_hours: Decimal  # all three whatever the unit
    unpriced_hours: Decimal
    amount_minor: int
    remaining_hours: Decimal | None  # in the budget's unit only; negative when over
    remaining_minor: int | None
    percent_used: int  # rounded down, not capped
    state: BillingBudgetState
    runs_out_on: date | None
    running: BillingBudgetRunning | None


def billing_budget_days(budget: BillingBudget, today: date) -> BillingBudgetDays:
    """The budget's current period as of `today`: only that one is ever
    read, since the limit is not dated."""
    if budget.period is BillingBudgetPeriod.MONTHLY:
        return BillingBudgetDays(today.replace(day=1), month_end(today), today, False)
    first = budget.starts_on
    assert first is not None  # BillingBudgetFields.a_start_only_on_a_total
    if first > today:
        return BillingBudgetDays(first, None, None, True)
    return BillingBudgetDays(first, None, today, False)


def month_slices(first: date, last: date) -> list[tuple[date, date]]:
    """The days `first` through `last`, cut at each 1st of a month."""
    slices: list[tuple[date, date]] = []
    while first <= last:
        end = min(month_end(first), last)
        slices.append((first, end))
        if end == date.max:
            break
        first = end + timedelta(days=1)
    return slices


def scope_spend(
    client: Client,
    billings: Iterable[ProjectBilling],
    projects: Mapping[str, Project],
    beats: Iterable[Beat],
    overrides: Mapping[str, bool],
    first: date,
    through: date,
    tz: ZoneInfo,
) -> BillingBudgetSpend:
    """What the days `first` through `through` bill on the scope: one
    `assemble_client` per calendar month. `billings` is already narrowed to
    the scope — the client's, or the one project's."""
    billings = list(billings)
    # Each month is given only its own beats; `assemble_client` checks the
    # local day again, so the bucketing rule stays in one place.
    beats_of: dict[date, list[Beat]] = defaultdict(list)
    for beat in beats:
        beats_of[local_date(beat.start, tz).replace(day=1)].append(beat)
    billable_hours, unpriced_hours, amount_minor = _ZERO_HOURS, _ZERO_HOURS, 0
    for slice_first, slice_last in month_slices(first, through):
        month_beats = beats_of.get(slice_first.replace(day=1))
        if not month_beats:
            # A month with no beats bills nothing, and a total started long
            # ago is mostly such months: each assemble walks every day.
            continue
        month = assemble_client(
            client,
            billings,
            projects,
            month_beats,
            overrides,
            slice_first,
            slice_last,
            tz,
        )
        billable_hours += month.billable_hours
        unpriced_hours += month.unpriced_hours
        amount_minor += month.amount_minor
    return BillingBudgetSpend(billable_hours, unpriced_hours, amount_minor)


def _hundredths(hours: Decimal) -> int:
    return int(hours * 100)  # exact: every hour figure is to the hundredth


def billing_budget_state(limit: int, spent: int, warn: int) -> BillingBudgetState:
    """`spent` against `limit`, both in hundredths of an hour or both in
    minor units, with the warning at `warn` %."""
    if spent >= limit:
        return BillingBudgetState.USED_UP
    if spent * 100 >= warn * limit:
        return BillingBudgetState.NEAR
    return BillingBudgetState.UNDER


def percent_used(limit: int, spent: int) -> int:
    """Rounded down, so it never reads 100 before the budget is used up, and
    not capped: over reads more."""
    return spent * 100 // limit


def _instant(since: datetime, hours: Fraction) -> datetime | None:
    """`hours` after `since`, in UTC, rounded up to the whole second; None
    past the last instant a datetime holds, which no timer reaches. The sum
    is what is rounded, not `hours` alone: a timer's start is stamped to
    the microsecond."""
    try:
        instant = since.astimezone(UTC) + timedelta(
            microseconds=ceil(hours * _MICROSECONDS_PER_HOUR)
        )
        if instant.microsecond:
            instant = instant.replace(microsecond=0) + timedelta(seconds=1)
    except OverflowError:
        return None
    return instant


def running_crossings(
    client: Client,
    billings: Iterable[ProjectBilling],
    beats: Iterable[Beat],
    overrides: Mapping[str, bool],
    first: date,
    through: date,
    tz: ZoneInfo,
    spent: int,
    limit: int,
    warn: int,
    unit: BillingBudgetUnit,
) -> BillingBudgetRunning | None:
    """The running beat that counts on the scope, and the instants at which
    it alone would cross the warning and the limit; None when none counts.

    A running beat counts when its project is in `billings`, it would be
    billable — its override, else its start day's term — and its local
    start day falls in `first` through `through`. A beat belongs whole to
    its start day, so that day's rate holds for all of it: a timer started
    at 23:00 on the 31st is the 31st's, and leaves a new month's reading at
    midnight. More than one counts only through `POST /api/beats/` or a
    restore; then the earliest is named and neither instant is given.

    The real crossing can sit up to 18 s (0.005 h) or a minor unit from the
    instant, since a stopped beat joins a line and is rounded with it: the
    copy says "around".
    """
    by_project = {billing.project_id: billing for billing in billings}
    counted: list[tuple[Beat, int | None]] = []
    for beat in beats:
        billing = by_project.get(beat.project_id)
        day = local_date(beat.start, tz)
        if beat.end is not None or billing is None or not first <= day <= through:
            continue
        override = overrides.get(beat.id) if beat.id is not None else None
        resolved = resolve_entry(client, billing, day, override)
        if resolved.billable:
            counted.append((beat, resolved.rate_minor))
    if not counted:
        return None
    counted.sort(key=lambda pair: pair[0].start)
    beat, rate = counted[0]
    since = beat.start.astimezone(UTC)
    running = BillingBudgetRunning(beat.project_id, since, rate is not None, None, None)
    if len(counted) > 1:
        return running
    # What an hour of this beat spends, in the budget's integer unit.
    if unit is BillingBudgetUnit.HOURS:
        per_hour = 100
    elif rate is not None:
        per_hour = rate
    else:
        return running  # unpriced hours spend no money yet
    near_at = over_at = None
    if spent * 100 < warn * limit:
        near_at = _instant(since, Fraction(warn * limit - spent * 100, 100 * per_hour))
    if spent < limit:
        over_at = _instant(since, Fraction(limit - spent, per_hour))
    return running._replace(near_at=near_at, over_at=over_at)


def runs_out_on(
    window_spend: int,
    window_days: int,
    remaining: int,
    today: date,
    period_last: date | None,
    days_elapsed: int,
    incomplete: bool,
) -> date | None:
    """When the budget runs out at the pace of the last `window_days` days,
    which spent `window_spend` (in the budget's integer unit); None when
    there is no projection worth giving:

    - fewer than 7 days of the period have passed, today counted — and so
      while a total is upcoming, with none;
    - nothing was spent in the window;
    - the budget is used up already;
    - `incomplete`: a money budget with hours that have no rate yet would
      forecast a figure known to be short;
    - the day falls after the period's last (a monthly budget that lasts
      the month says nothing more), or more than 365 days away.

    The pace is per calendar day, weekends and all — crude, but it can be
    explained, so the copy says "around".
    """
    if days_elapsed < _PACE_FIRST_DAY or window_spend <= 0 or remaining <= 0 or incomplete:
        return None
    days = -(-remaining * window_days // window_spend)
    if days > _PROJECTION_DAYS:
        return None
    day = today + timedelta(days=days)
    if period_last is not None and day > period_last:
        return None
    return day


def billing_budget_status(
    budget: BillingBudget,
    client: Client,
    scope_billings: Sequence[ProjectBilling],
    projects: Mapping[str, Project],
    beats: Sequence[Beat],
    overrides: Mapping[str, bool],
    today: date,
    tz: ZoneInfo,
    active: bool,
) -> BillingBudgetStatus:
    """`budget` read as of `today` in `tz`: its period, what it has spent,
    what is left, its state, its projection and its running timer.

    `client` is the scope's — for a project, the one its billing names —
    and `scope_billings` the billing of every project in the scope.
    `projects` (by id, archived ones too) covers them, and `beats` their
    beats from the period's first day on, running ones included; a beat of
    another project, or another day, is left out here.
    """
    days = billing_budget_days(budget, today)
    hours_unit = budget.unit is BillingBudgetUnit.HOURS
    if hours_unit:
        assert budget.limit_hours is not None  # BillingBudgetFields.a_limit_in_hours_only_in_hours
        limit = _hundredths(budget.limit_hours)
    else:
        assert budget.limit_minor is not None  # BillingBudgetFields.a_limit_in_money_only_in_money
        limit = budget.limit_minor
    if budget.scope is BillingBudgetScope.CLIENT:
        name = client.name
    else:
        name = projects[budget.scope_id].name

    spend = BillingBudgetSpend(_ZERO_HOURS, _ZERO_HOURS, 0)
    projection = running = None
    if days.through is not None:
        spend = scope_spend(
            client, scope_billings, projects, beats, overrides, days.first, days.through, tz
        )
    spent = _hundredths(spend.billable_hours) if hours_unit else spend.amount_minor
    remaining = limit - spent
    if days.through is not None:
        elapsed = (days.through - days.first).days + 1
        window_days = min(_PACE_DAYS, elapsed)
        window = scope_spend(
            client,
            scope_billings,
            projects,
            beats,
            overrides,
            days.through - timedelta(days=window_days - 1),
            days.through,
            tz,
        )
        projection = runs_out_on(
            _hundredths(window.billable_hours) if hours_unit else window.amount_minor,
            window_days,
            remaining,
            days.through,
            days.last,
            elapsed,
            incomplete=not hours_unit and spend.unpriced_hours > 0,
        )
        running = running_crossings(
            client,
            scope_billings,
            beats,
            overrides,
            days.first,
            days.through,
            tz,
            spent,
            limit,
            budget.warn_at_percent,
            budget.unit,
        )

    return BillingBudgetStatus(
        scope=budget.scope,
        scope_id=budget.scope_id,
        client_id=client.id,
        name=name,
        active=active,
        currency=client.currency,
        minor_units=minor_units(client.currency),
        unit=budget.unit,
        period=budget.period,
        limit_hours=budget.limit_hours,
        limit_minor=budget.limit_minor,
        starts_on=budget.starts_on,
        warn_at_percent=budget.warn_at_percent,
        upcoming=days.upcoming,
        first=days.first,
        last=days.last,
        through=days.through,
        billable_hours=spend.billable_hours,
        unpriced_hours=spend.unpriced_hours,
        amount_minor=spend.amount_minor,
        remaining_hours=Decimal(remaining).scaleb(-2) if hours_unit else None,
        remaining_minor=None if hours_unit else remaining,
        percent_used=percent_used(limit, spent),
        state=billing_budget_state(limit, spent, budget.warn_at_percent),
        runs_out_on=projection,
        running=running,
    )
