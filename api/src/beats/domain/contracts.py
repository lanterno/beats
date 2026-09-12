"""The contract arithmetic: what a day job expected, and the running balance.

Pure functions over a `Contract`, its absences, and the region's holidays as
a `set[date]`. Nothing here reads a clock or a calendar library — `today` is
a parameter and the holidays are injected — so every rule is a plain function
of its inputs. The rules themselves are the roadmap's:

    expected(d) for a weekday d:
        term  = the term with the latest effective_from <= d     (none -> 0)
        base  = term.hours_per_day                                (objective -> 0)
        if d is before the first term or after ended_on:          0
        if d is a public holiday in the contract's region:        0
        if an absence exists on d:                                0, or base/2 if half_day
        else                                                      base
    expected(d) for Saturday / Sunday:                            0

    balance(today) = opening_balance_hours
                   + worked(start .. min(today, ended_on))
                   - expected(start .. yesterday)

Worked time arrives already bucketed by local day: only the caller knows the
request timezone, and a beat that crosses midnight belongs to whichever day
the caller says it does.

Two things beside the arithmetic live here because every reader of a figure
goes through them: the week's null rule (`week_expectation`, `owes` — when a
week has no expectation at all, as distinct from one of 0 h) and the rounding
every hour figure gets on the wire (`round_hours`).
"""

from collections.abc import Iterable, Iterator, Mapping
from datetime import date, timedelta
from typing import NamedTuple

from beats.domain.models import Absence, Contract, ContractTerm


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
    """The balance as of a day, and the three terms that make it — what the
    standing shows under the figure so a reader can check the sum."""

    opening: float
    worked: float
    expected_through: float  # Σ expected(start .. yesterday)
    balance: float  # opening + worked - expected_through


def _daily(
    contract: Contract,
    by_day: Mapping[date, Absence],
    holidays: set[date],
    worked: Mapping[date, float],
    through: date,
) -> Iterator[tuple[date, float, float]]:
    """Every day from the contract's first through `through`, with the hours
    worked on it that the balance counts — none after `ended_on` — and the
    hours it expected. The two running sums under every balance figure come
    from here and nowhere else."""
    for day in _days(contract.starts_on, through):
        ended = contract.ended_on is not None and day > contract.ended_on
        counted = 0.0 if ended else worked.get(day, 0.0)
        yield day, counted, expected_on(contract, day, holidays, by_day)


def balance_terms(
    contract: Contract,
    absences: Iterable[Absence],
    holidays: set[date],
    worked: Mapping[date, float],
    today: date,
) -> BalanceTerms:
    """Hours over (positive) or owed (negative) as of `today`, with its terms.

    Today's work counts as soon as it happens; today's expectation is charged
    tomorrow, so the balance does not read −8 h every morning. `ended_on`
    freezes the balance on both sides: nothing is expected after it, and time
    tracked on the project after it does not count as overtime either — so
    for any `today` past `ended_on` this is the final balance, unchanged.
    """
    by_day = absences_by_day(absences)
    worked_hours = expected = 0.0
    for day, counted, due in _daily(contract, by_day, holidays, worked, today):
        worked_hours += counted
        if day < today:
            expected += due
    opening = contract.opening_balance_hours
    return BalanceTerms(opening, worked_hours, expected, opening + worked_hours - expected)


def closing_balances(
    contract: Contract,
    absences: Iterable[Absence],
    holidays: set[date],
    worked: Mapping[date, float],
    days: Iterable[date],
) -> dict[date, float]:
    """The balance at the close of each of `days`: the opening balance, plus
    the hours worked through the day, minus the hours expected through it —
    the figure `balance_terms` gives the next morning, before that day's
    work. One pass over the contract's days however many closes are asked
    for, so a ledger of a hundred weeks costs what one does. A day before
    the contract's first closes at the opening balance.
    """
    wanted = set(days)
    if not wanted:
        return {}
    opening = contract.opening_balance_hours
    closes = {day: opening for day in wanted if day < contract.starts_on}
    by_day = absences_by_day(absences)
    worked_hours = expected = 0.0
    for day, counted, due in _daily(contract, by_day, holidays, worked, max(wanted)):
        worked_hours += counted
        expected += due
        if day in wanted:
            closes[day] = opening + worked_hours - expected
    return closes


def balance(
    contract: Contract,
    absences: Iterable[Absence],
    holidays: set[date],
    worked: Mapping[date, float],
    today: date,
) -> float:
    """Hours over (positive) or owed (negative) as of `today` — `balance_terms`'s sum."""
    return balance_terms(contract, absences, holidays, worked, today).balance


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
