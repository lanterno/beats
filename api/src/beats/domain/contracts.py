"""The contract arithmetic: what a day job expected, and the running balance.

Pure functions over a `Contract`, its absences, and its holidays as a
`set[date]`. Nothing here reads a clock or a calendar library — `today` is
a parameter and the holidays are injected — so every rule is a plain function
of its inputs. The set's one source is `holidays.contract_holidays`: the
region's holidays, less the ones the employer does not give, plus the
company's. The rules are docs/work-contracts.md's ("The arithmetic"):

    expected(d) for a weekday d:
        term  = the term with the latest effective_from <= d     (none -> 0)
        base  = term.hours_per_day                                (objective -> 0)
        if d is before the first term or after ended_on:          0
        if d is a holiday of the contract:                        0
        if an absence exists on d:                                0, or base/2 if half_day
        else                                                      base
    expected(d) for Saturday / Sunday:                            0

    balance(today) = opening_balance_hours
                   + counted(start .. min(today, ended_on))
                   - expected(start .. yesterday)
                   + adjusted(start .. today)

    counted(d) = worked(d) when the term in force on d owes hours (`owes`),
                 else 0 — an objective or 0-hour term expects nothing, so
                 the hours worked under it are not overtime either

    adjusted(d), at the start of d, against b = the close of d - 1:
        delta  -> hours
        reset  -> hours - b                    (the balance becomes hours)
        cap    -> min(0, hours - b)            (no higher than hours)

Worked time arrives already bucketed by local day: only the caller knows the
request timezone, and a beat that crosses midnight belongs to whichever day
the caller says it does. A reset or a cap makes that choice visible: a beat
late on the eve of a reset is absorbed by it in one timezone and counted
after it in another, so the balance after a reset depends on the timezone it
is read in.

Two things beside the arithmetic live here because every reader of a figure
goes through them: the week's null rule (`week_expectation`, `owes` — when a
week has no expectation at all, as distinct from one of 0 h) and the rounding
every hour figure gets on the wire (`round_hours`).
"""

from collections.abc import Iterable, Iterator, Mapping
from datetime import date, timedelta
from typing import NamedTuple

from beats.domain.models import (
    Absence,
    AdjustmentKind,
    BalanceAdjustment,
    Contract,
    ContractTerm,
)


def term_on(contract: Contract, day: date) -> ContractTerm | None:
    """The term in force on `day`: the latest whose `effective_from` is not after it.

    None before the first term. `ended_on` is not consulted here — a term is
    still the term that applied, it just stops owing anything. The lookup
    itself lives on `Contract`, where `Project.effective_goal` can reach it
    without importing this module; this is the arithmetic's name for it.
    """
    return contract.term_on(day)


def absences_by_day(absences: Iterable[Absence]) -> dict[date, Absence]:
    """Index absences by date. Two on one day are one; a full day beats a half."""
    by_day: dict[date, Absence] = {}
    for absence in absences:
        current = by_day.get(absence.date)
        if current is None or (current.half_day and not absence.half_day):
            by_day[absence.date] = absence
    return by_day


def expected_on(
    contract: Contract,
    day: date,
    holidays: set[date],
    absences: Mapping[date, Absence],
) -> float:
    """Hours the contract expects on one day — the per-day rule, in order."""
    if day.weekday() >= 5:
        return 0.0
    if contract.ended_on is not None and day > contract.ended_on:
        return 0.0
    term = term_on(contract, day)
    base = term.hours_per_day if term is not None else None
    if base is None:  # before the first term, or an objective term
        return 0.0
    if day in holidays:
        return 0.0
    absence = absences.get(day)
    if absence is None:
        return base
    return base / 2 if absence.half_day else 0.0


def expected_hours(
    contract: Contract,
    absences: Iterable[Absence],
    holidays: set[date],
    start: date,
    end: date,
) -> float:
    """Σ expected(d) for every day in [start, end]; zero when end is before start."""
    by_day = absences_by_day(absences)
    return sum(expected_on(contract, day, holidays, by_day) for day in _days(start, end))


class BalanceTerms(NamedTuple):
    """The balance as of a day, and the four terms that make it — what the
    standing shows under the figure so a reader can check the sum."""

    opening: float
    worked: float
    expected_through: float  # Σ expected(start .. yesterday)
    adjusted: float  # Σ applied, for the adjustments dated start .. today
    balance: float  # opening + worked - expected_through + adjusted


class Running(NamedTuple):
    """One pass over a contract's days: the balance as of today with its
    terms, the close of each day asked for, and what each adjustment the
    pass reached moved the balance by, keyed by its date."""

    terms: BalanceTerms
    closes: dict[date, float]
    applied: dict[date, float]


def within_contract(contract: Contract, day: date) -> bool:
    """Whether `day` falls inside the contract's dates: from its first term
    through `ended_on`, whatever the term in force."""
    return day >= contract.starts_on and (contract.ended_on is None or day <= contract.ended_on)


def counts_worked(contract: Contract, day: date) -> bool:
    """Whether hours worked on `day` count toward the balance: inside the
    contract's dates (`within_contract`), under a term that owes hours
    (`owes`). An objective or 0-hour term expects nothing of its days, so
    what is worked on them is not overtime either — the hours stay in the
    week's `worked` and move no balance. The balance and the week's
    remaining both ask this, so on a week a contract starts or ends, or a
    term that owes nothing begins or ends, the two agree on what counted."""
    return within_contract(contract, day) and owes(term_on(contract, day))


def adjustments_by_day(adjustments: Iterable[BalanceAdjustment]) -> dict[date, BalanceAdjustment]:
    """Index adjustments by date. The store keeps one per day; were there two,
    the later in the iterable would be the one on record."""
    return {adjustment.date: adjustment for adjustment in adjustments}


def applied_hours(adjustment: BalanceAdjustment, before: float) -> float:
    """What `adjustment` moves a balance of `before` by, at the start of its day."""
    match adjustment.kind:
        case AdjustmentKind.DELTA:
            return adjustment.hours
        case AdjustmentKind.RESET:
            return adjustment.hours - before
        case AdjustmentKind.CAP:
            return min(0.0, adjustment.hours - before)


def _daily(
    contract: Contract,
    by_day: Mapping[date, Absence],
    holidays: set[date],
    worked: Mapping[date, float],
    adjustments: Mapping[date, BalanceAdjustment],
    through: date,
) -> Iterator[tuple[date, float, float, float]]:
    """Every day from the contract's first through `through`, with the hours
    worked on it that the balance counts (`counts_worked`: none after
    `ended_on`, none under a term that owes nothing), the hours
    it expected, and what the day's adjustment moved the balance by (0
    without one). The running sums under every balance figure come from
    here and nowhere else.

    An adjustment takes effect as its day starts, against the close of the
    day before; the day's work and expectation come after it. That is why
    the running total is kept here: a reset or a cap moves the balance by
    whatever it takes to reach its target that morning.
    """
    running = contract.opening_balance_hours
    for day in _days(contract.starts_on, through):
        adjustment = adjustments.get(day)
        moved = applied_hours(adjustment, running) if adjustment is not None else 0.0
        counted = worked.get(day, 0.0) if counts_worked(contract, day) else 0.0
        due = expected_on(contract, day, holidays, by_day)
        running += moved + counted - due
        yield day, counted, due, moved


def running_balance(
    contract: Contract,
    absences: Iterable[Absence],
    holidays: set[date],
    worked: Mapping[date, float],
    adjustments: Iterable[BalanceAdjustment],
    today: date,
    closes_on: Iterable[date] = (),
) -> Running:
    """The balance as of `today`, the close of each of `closes_on`, and the
    hours each adjustment moved it by — in one pass, so the three cannot
    disagree. A ledger of a hundred weeks costs what one does.

    Today's work counts as soon as it happens; today's expectation is charged
    tomorrow, so the balance does not read −8 h every morning. Today's
    adjustment counts from the start of today. `ended_on` freezes work and
    expectation: nothing is expected after it, and time tracked on the
    project after it does not count as overtime either. Nor does time
    tracked under an objective or 0-hour term, which expects nothing: a
    time-based term after it starts from the balance the last one left,
    not from the hours worked in between. Adjustments count
    from the contract's first day on, whatever `ended_on` says, so a payout
    after the end settles the frozen balance; one dated before the first day
    falls outside the pass and is ignored.

    A close is the balance at the end of its day — the opening balance, plus
    the work, less the expectation, plus the adjustments through it — and so
    before the next day's adjustment. A day before the contract's first
    closes at the opening balance.

    The pass runs through the latest of `today`, the last close asked for
    and the last adjustment, so every adjustment from the first day on gets
    its `applied`, one dated after today included. The terms count only the
    adjustments dated through today.
    """
    wanted = set(closes_on)
    starts_on = contract.starts_on
    by_adjustment = {
        day: adj for day, adj in adjustments_by_day(adjustments).items() if day >= starts_on
    }
    by_day = absences_by_day(absences)
    opening = contract.opening_balance_hours
    closes = {day: opening for day in wanted if day < contract.starts_on}
    applied: dict[date, float] = {}
    terms = BalanceTerms(opening, 0.0, 0.0, 0.0, opening)
    worked_hours = expected = adjusted = 0.0
    through = max([today, *wanted, *by_adjustment])
    for day, counted, due, moved in _daily(
        contract, by_day, holidays, worked, by_adjustment, through
    ):
        if day in by_adjustment:
            applied[day] = moved
        worked_hours += counted
        adjusted += moved
        if day == today:
            balance_today = opening + worked_hours - expected + adjusted
            terms = BalanceTerms(opening, worked_hours, expected, adjusted, balance_today)
        expected += due
        if day in wanted:
            closes[day] = opening + worked_hours - expected + adjusted
    return Running(terms, closes, applied)


def balance_terms(
    contract: Contract,
    absences: Iterable[Absence],
    holidays: set[date],
    worked: Mapping[date, float],
    adjustments: Iterable[BalanceAdjustment],
    today: date,
) -> BalanceTerms:
    """Hours over (positive) or owed (negative) as of `today`, with its terms
    — `running_balance`'s, for a reader that wants nothing else of the pass.
    For any `today` past `ended_on` this is the final balance, moved only by
    the adjustments dated after the end."""
    return running_balance(contract, absences, holidays, worked, adjustments, today).terms


def balance(
    contract: Contract,
    absences: Iterable[Absence],
    holidays: set[date],
    worked: Mapping[date, float],
    adjustments: Iterable[BalanceAdjustment],
    today: date,
) -> float:
    """Hours over (positive) or owed (negative) as of `today` — `balance_terms`'s sum."""
    return balance_terms(contract, absences, holidays, worked, adjustments, today).balance


def owes(term: ContractTerm | None) -> bool:
    """Whether a term sets an expectation: time-based, and for more than 0
    hours. Before the first term and under an objective term there is no
    expectation to report, only work. A term of 0 hours — a sabbatical, or
    the migration's reading of an override that said "no goal from here" —
    governs the week, so the personal goal does not resurface under it, but
    expects nothing of it by nature: null, as `Project.effective_goal`
    already reads it, not a 0 the header would show as "12.0/0.0h"."""
    return term is not None and bool(term.hours_per_week)


def round_hours(value: float) -> float:
    """Every hour figure on the wire, to two decimals."""
    return round(value, 2)


def week_expectation(
    contract: Contract, absences: Iterable[Absence], holidays: set[date], week_of: date
) -> float | None:
    """Hours the contract expects of the week starting `week_of`, after its
    holidays and absences — the week route's `expected`, on its own.

    None under the null rule: no weekday of the week has a term that sets an
    expectation (before the first term, an objective term, a term of 0
    hours). Weekdays only, since Saturday and Sunday owe nothing under any
    term and so say nothing about whether the week has one. 0 is distinct: a
    week the contract owed nothing by circumstance — every weekday a holiday
    or an absence, or after `ended_on`.
    """
    weekdays = (week_of + timedelta(days=offset) for offset in range(5))
    if not any(owes(term_on(contract, day)) for day in weekdays):
        return None
    sunday = week_of + timedelta(days=6)
    return round_hours(expected_hours(contract, absences, holidays, week_of, sunday))


def _days(start: date, end: date) -> Iterator[date]:
    day = start
    while day <= end:
        yield day
        day += timedelta(days=1)
