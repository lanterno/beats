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
"""

from collections.abc import Iterable, Iterator, Mapping
from datetime import date, timedelta

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


def balance(
    contract: Contract,
    absences: Iterable[Absence],
    holidays: set[date],
    worked: Mapping[date, float],
    today: date,
) -> float:
    """Hours over (positive) or owed (negative) as of `today`.

    Today's work counts as soon as it happens; today's expectation is charged
    tomorrow, so the balance does not read −8 h every morning. `ended_on`
    freezes the balance on both sides: nothing is expected after it, and time
    tracked on the project after it does not count as overtime either.
    """
    start = contract.starts_on
    worked_until = today if contract.ended_on is None else min(today, contract.ended_on)
    worked_hours = sum(hours for day, hours in worked.items() if start <= day <= worked_until)
    expected = expected_hours(contract, absences, holidays, start, today - timedelta(days=1))
    return contract.opening_balance_hours + worked_hours - expected


def _days(start: date, end: date) -> Iterator[date]:
    day = start
    while day <= end:
        yield day
        day += timedelta(days=1)
