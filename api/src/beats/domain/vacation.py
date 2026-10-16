"""The vacation arithmetic: what a day job's entitlement leaves in a year.

Pure functions over a `Contract` with a `VacationEntitlement`, its absences,
and its holidays as a `set[date]` (from `holidays.contract_holidays`, so a
company day costs no leave either). No clock, no calendar library. The rules
are docs/work-contracts.md's ("Vacation"):

    the opening year (opening_on's):
        available = opening_days                  (taken as typed)
    every later year y:
        accrued   = days_per_year, pro-rated by calendar days in the year
                    of ended_on, to the half day (half up)
        carried   = what y - 1 left, after the carry-over rule
                    (a deficit carries whole, whatever the rule)
        available = accrued + carried
    remaining     = available - booked

    a day costs leave when it is a `vacation` absence (1, or ½ for a half
    day) on a weekday from opening_on through ended_on, inside the
    contract's dates, that is not a holiday of the contract — whatever the
    term in force.

Everything is counted in days for a five-day week (decision 3): a week off
is five days whatever the percentage, so a part-time job's figure is not
scaled again here.
"""

from calendar import isleap
from collections.abc import Iterable
from datetime import date
from fractions import Fraction
from math import floor

from beats.domain.contracts import absences_by_day, counts_worked
from beats.domain.models import (
    Absence,
    AbsenceType,
    CarryOver,
    Contract,
    VacationEntitlement,
    VacationYear,
)


def round_half(value: Fraction) -> float:
    """To the nearest half day, a quarter rounding up: 12.25 is 12.5, where
    `round` would go to the even 12. Exact, so a quarter is a quarter."""
    return floor(value * 2 + Fraction(1, 2)) / 2


def vacation_cost(
    entitlement: VacationEntitlement,
    contract: Contract,
    day: date,
    holidays: set[date],
    absence: Absence | None,
) -> float:
    """What the absence on `day` costs the entitlement: 1, ½ for a half day,
    or 0.

    Deliberately not `expected_on`: leave is part of the employment, not of
    the schedule. A day under an objective or a 0-hour term owes no hours,
    yet a vacation booked on it is still a day of leave taken. What frees a
    day is what frees it for everyone — a weekend or a holiday of the
    contract — or its falling outside what is counted: before the opening,
    before the first term, after `ended_on`.
    """
    if absence is None or absence.type is not AbsenceType.VACATION:
        return 0.0
    if day < entitlement.opening_on or day.weekday() >= 5 or day in holidays:
        return 0.0
    if not counts_worked(contract, day):
        return 0.0
    return 0.5 if absence.half_day else 1.0


def accrued_days(entitlement: VacationEntitlement, contract: Contract, year: int) -> float:
    """The days `year` gives: the whole `days_per_year`, or in the year of
    `ended_on` its share by calendar days (a leap year has 366), to the half
    day."""
    first, last = date(year, 1, 1), date(year, 12, 31)
    if contract.ended_on is not None and contract.ended_on < last:
        last = contract.ended_on
    covered = max(0, (last - first).days + 1)
    # Not `date(year + 1, 1, 1) - first`: the route accepts 9999, the last
    # year `date` can hold, and an open-ended contract chains up to it.
    days_in_year = 366 if isleap(year) else 365
    return round_half(Fraction(entitlement.days_per_year) * covered / days_in_year)


def carry(left: float, entitlement: VacationEntitlement) -> float:
    """What a year that ended with `left` days hands the next. A deficit
    carries whole — the rule limits what is kept, not what is owed."""
    if left <= 0 or entitlement.carry_over is CarryOver.ALL:
        return left
    if entitlement.carry_over is CarryOver.NONE:
        return 0.0
    cap = entitlement.carry_over_max_days
    assert cap is not None  # `capped` requires one: VacationEntitlement.cap_only_when_capped
    return min(left, cap)


def vacation_year(
    contract: Contract, absences: Iterable[Absence], holidays: set[date], year: int
) -> VacationYear:
    """`year` of the contract's entitlement, chained from the opening year.

    `absences` must reach from the opening through the end of `year` (or
    `ended_on`), and `holidays` must hold every holiday on a vacation day in
    that span. The caller refuses a year outside [the opening's, ended_on's].
    """
    entitlement = contract.vacation
    if entitlement is None:
        msg = "the contract has no vacation entitlement"
        raise ValueError(msg)
    first_year = entitlement.opening_on.year
    if year < first_year or (contract.ended_on is not None and year > contract.ended_on.year):
        msg = f"{year} is outside the years the entitlement counts"
        raise ValueError(msg)

    booked: dict[int, float] = {}
    for day, absence in absences_by_day(absences).items():
        cost = vacation_cost(entitlement, contract, day, holidays, absence)
        if cost:
            booked[day.year] = booked.get(day.year, 0.0) + cost

    accrued: float | None = None
    carried_in = 0.0
    available = entitlement.opening_days
    remaining = available - booked.get(first_year, 0.0)
    for y in range(first_year + 1, year + 1):
        carried_in = carry(remaining, entitlement)
        accrued = accrued_days(entitlement, contract, y)
        available = accrued + carried_in
        remaining = available - booked.get(y, 0.0)
    return VacationYear(
        year=year,
        accrued=accrued,
        carried_in=carried_in,
        available=available,
        booked=booked.get(year, 0.0),
        remaining=remaining,
    )
