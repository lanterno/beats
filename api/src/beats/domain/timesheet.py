"""The monthly timesheet: one month of a day job, a row per day, as an
employer reads it — and downloads it, as a CSV (docs/work-contracts.md,
"The timesheet").

Pure assembly over what the service has already fetched: the contract, its
absences, its holidays by name, the hours worked by local day and its
balance adjustments. Nothing here reads a clock; `today` reaches only
`timesheet_range`, which clips the month. Every figure comes from the same
functions as the ledger and the week — `expected_on`, `owes`, one
`running_balance` pass, `round_hours` — so the sheet agrees with the project
page on the day it is downloaded.

What a sheet covers: the finished days of the month inside the contract,
`first` through `last` — from the first term (or the 1st), through
`ended_on`, yesterday or the month's end, whichever comes first. A day's row:

    expected     `expected_on`; None when the day's term sets no expectation
                 (`owes`: an objective or 0 h term), so a day it owed nothing
                 by circumstance — a weekend, a holiday, a day off — is 0
    worked       the hours of that local day; every day of the sheet is
                 inside the contract, so every hour counts
    difference   worked − expected, None with expected
    adjustment   the kind of the balance adjustment dated that day, if any
    adjusted     what it moved the balance by (`applied`), at the start of
                 the day, against the close of the day before
    holiday      the holiday's name, weekdays only: a weekend owes nothing
                 under any term, so a holiday there changed nothing
    absence      the absence's type and `half_day`, weekdays only; never its
                 note, which can be medical and is the user's own text
    balance_end  the day's close off the one pass; None with expected

`brought_forward` is the opening balance on the sheet that starts on the
contract's first day, otherwise the close of the day before `first`, None
when that day's term sets no expectation — the row's own rule. So one
month's `carried_forward` (the last row's close) is the next month's
`brought_forward`, and whenever both are set

    brought_forward + worked − expected + adjusted = carried_forward

within 0.025: the identity is exact on the raw figures, and each of the
five is rounded on its own from a raw sum, 0.005 at most apiece, as the
ledger's totals are. Hours worked under an objective stretch inside the
month count in `worked` and move the balance, as they do on the ledger;
their days expect nothing.

`holidays` counts the weekday holidays of the sheet. `absence_days` counts
the weekday absences that are not on a holiday — the holiday already gave
that day — a half day as ½.
"""

import calendar
from collections.abc import Iterable, Mapping
from datetime import date, timedelta
from typing import NamedTuple

from beats.domain.contracts import (
    absences_by_day,
    adjustments_by_day,
    expected_on,
    owes,
    round_hours,
    running_balance,
    term_on,
)
from beats.domain.models import (
    Absence,
    AbsenceType,
    AdjustmentKind,
    BalanceAdjustment,
    Contract,
)

# What a company holiday is called on the sheet. Its own name is what the
# user typed on the contract; the file goes to the employer, so it carries
# the employer's fact — a day the company gave — and nothing typed.
COMPANY_HOLIDAY = "company holiday"


class TimesheetDay(NamedTuple):
    """One day of the sheet. Not `ContractDay`: `expected` is nullable here,
    holidays and absences are named on weekdays only, and there is no note."""

    date: date
    expected: float | None
    worked: float
    difference: float | None
    adjustment: AdjustmentKind | None
    adjusted: float | None
    holiday: str | None
    absence: AbsenceType | None
    half_day: bool  # False without an absence
    balance_end: float | None


class Timesheet(NamedTuple):
    """A month of the contract, with the figures its total row carries."""

    month: date  # the 1st
    first: date
    last: date
    brought_forward: float | None
    expected: float | None  # Σ of the days with an expectation; None when none has one
    worked: float
    difference: float | None  # worked − expected, None with it
    adjusted: float  # Σ applied
    holidays: int
    absence_days: float
    carried_forward: float | None  # the last row's balance_end
    days: list[TimesheetDay]


def month_end(month: date) -> date:
    """The last day of `month`'s month, off the calendar — never "the 1st of
    the next month less a day", which has no answer for December 9999."""
    return date(month.year, month.month, calendar.monthrange(month.year, month.month)[1])


def timesheet_range(contract: Contract, month: date, today: date) -> tuple[date, date] | None:
    """The finished days of `month` inside the contract, as (first, last);
    None when there are none — a month wholly before the first term or after
    `ended_on`, a month still to come, the current month on its 1st."""
    first = max(month.replace(day=1), contract.starts_on)
    last = min(month_end(month), today - timedelta(days=1))
    if contract.ended_on is not None:
        last = min(last, contract.ended_on)
    return (first, last) if first <= last else None


def assemble_timesheet(
    contract: Contract,
    absences: Iterable[Absence],
    holidays: Mapping[date, str],
    worked: Mapping[date, float],
    adjustments: Iterable[BalanceAdjustment],
    first: date,
    last: date,
) -> Timesheet:
    """The sheet for the days `first` through `last`, a range
    `timesheet_range` gave. The absences, the holidays, the hours and the
    adjustments must cover the contract's life through `last`, not only the
    month: every close is read off the pass from the first day."""
    by_day = absences_by_day(absences)
    by_adjustment = adjustments_by_day(adjustments)
    holiday_days = set(holidays)
    days = [first + timedelta(days=n) for n in range((last - first).days + 1)]
    # The sheet that opens on the contract's first day brings the opening
    # balance forward; any other brings the close of the day before.
    before = first - timedelta(days=1) if first > contract.starts_on else None
    running = running_balance(
        contract,
        by_day.values(),
        holiday_days,
        worked,
        by_adjustment.values(),
        last,
        [*days, before] if before is not None else days,
    )
    if before is None:
        brought_forward: float | None = contract.opening_balance_hours
    elif owes(term_on(contract, before)):
        brought_forward = running.closes[before]
    else:
        brought_forward = None

    rows: list[TimesheetDay] = []
    expected_raw = worked_raw = adjusted_raw = absence_days = 0.0
    owed_any = False
    holiday_count = 0
    for day in days:
        owed = owes(term_on(contract, day))
        weekday = day.weekday() < 5
        holiday = holidays.get(day) if weekday else None
        absence = by_day.get(day) if weekday else None
        due = expected_on(contract, day, holiday_days, by_day)
        hours = worked.get(day, 0.0)
        applied = running.applied.get(day)
        adjustment = by_adjustment.get(day) if applied is not None else None
        worked_raw += hours
        adjusted_raw += applied or 0.0
        if owed:
            owed_any = True
            expected_raw += due
        if holiday is not None:
            holiday_count += 1
        elif absence is not None:
            absence_days += 0.5 if absence.half_day else 1.0
        rows.append(
            TimesheetDay(
                date=day,
                expected=round_hours(due) if owed else None,
                worked=round_hours(hours),
                difference=round_hours(hours - due) if owed else None,
                adjustment=adjustment.kind if adjustment is not None else None,
                adjusted=round_hours(applied) if applied is not None else None,
                holiday=holiday,
                absence=absence.type if absence is not None else None,
                half_day=absence is not None and absence.half_day,
                balance_end=round_hours(running.closes[day]) if owed else None,
            )
        )
    return Timesheet(
        month=first.replace(day=1),
        first=first,
        last=last,
        brought_forward=round_hours(brought_forward) if brought_forward is not None else None,
        expected=round_hours(expected_raw) if owed_any else None,
        worked=round_hours(worked_raw),
        difference=round_hours(worked_raw - expected_raw) if owed_any else None,
        adjusted=round_hours(adjusted_raw),
        holidays=holiday_count,
        absence_days=absence_days,
        carried_forward=rows[-1].balance_end,
        days=rows,
    )
