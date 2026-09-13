"""The ledger: a project's last N weeks, newest first, with the balance at the
close of each — every week figure on the project page, from one read.

Pure assembly over what the service has already fetched: the project (for the
goal it resolves per Monday), the contract that governs it or None, the
absences, the region's holidays by name, the hours worked by local day, and
`today`. Nothing here reads a clock, so every row is a plain function of its
inputs, and every figure goes through the same rounding (`round_hours`) as the
week route's, so the two cannot disagree on a week they both show.

What a week carries, and when a figure is None:

    worked            Σ of the seven days, request tz, a running beat included
    days              Mon..Sun hours, each rounded on its own
    effective_goal    `Project.effective_goal` for the Monday: the term's
                      nominal hours on a governed week, else the personal
                      goal / override
    contract_expected `week_expectation`: what the contract expects after
                      holidays and absences; None when nothing time-based
                      governs the week (before the first term, an objective
                      or 0 h term, no contract), 0 when it owed nothing by
                      circumstance (a full vacation week, after `ended_on`)
    balance_end       the balance at the close of the week — `closing_balances`
                      at the week's Sunday: the opening balance plus the
                      hours worked through Sunday minus the hours expected
                      through it, the Monday-morning figure before that
                      day's work. None for the current week (it has not
                      closed; the standing has today's figure), on a week
                      with no `contract_expected` — one null rule for the
                      row, so the expectation and the balance go blank
                      together; a term starting on a Saturday leaves its
                      week before the contract on both counts, and its
                      weekend hours move the next week's close — and on any
                      project the contract does not govern. A week entirely
                      after `ended_on` gets the final balance, unchanged:
                      both sides freeze on that day, so the ledger repeats
                      the frozen figure rather than going blank — the
                      closing balance is still what the reader asked for,
                      and it is the same on every row after the end.
    notes             the absences and named public holidays on the week's
                      weekdays, by date; an absence carries `half_day`, a
                      holiday its `name`. Weekends are left out: they owe
                      nothing under any term, so a holiday or absence there
                      changed nothing.

`worked` is every hour logged in the week; the balance counts only the hours
from the contract's first day through `ended_on`. On the week a contract
starts or ends mid-week the row's worked − contract_expected is therefore not
the balance's move: the hours before the first day or after the last are
shown, and charged nothing.

`since` is the contract's first day, or None. `totals` is the balance as of
today with the two terms that move it, or None when there is no balance today
— the same rule as the week route's `balance`.
"""

from collections.abc import Iterable, Mapping
from datetime import date, timedelta

from beats.domain.contracts import (
    absences_by_day,
    balance_terms,
    closing_balances,
    owes,
    round_hours,
    term_on,
    week_expectation,
)
from beats.domain.models import (
    Absence,
    Contract,
    Ledger,
    LedgerNote,
    LedgerNoteKind,
    LedgerTotals,
    LedgerWeek,
    Project,
)

_SUNDAY = timedelta(days=6)


def assemble_ledger(
    project: Project,
    contract: Contract | None,
    absences: Iterable[Absence],
    holidays: Mapping[date, str],
    worked: Mapping[date, float],
    today: date,
    weeks: int,
) -> Ledger:
    """The last `weeks` weeks ending with the one `today` is in, newest first."""
    monday = today - timedelta(days=today.weekday())
    mondays = [monday - timedelta(weeks=n) for n in range(weeks)]
    by_day = absences_by_day(absences)
    holiday_days = set(holidays)
    expected: dict[date, float | None] = {}
    closes: dict[date, float] = {}
    totals = None
    if contract is not None:
        expected = {
            week_of: week_expectation(contract, by_day.values(), holiday_days, week_of)
            for week_of in mondays
        }
        # The current week is first and has not closed — the standing shows
        # today's balance instead — and a week with no expectation has no
        # balance to close.
        closes = closing_balances(
            contract,
            by_day.values(),
            holiday_days,
            worked,
            [week_of + _SUNDAY for week_of in mondays[1:] if expected[week_of] is not None],
        )
        if owes(term_on(contract, today)):
            terms = balance_terms(contract, by_day.values(), holiday_days, worked, today)
            totals = LedgerTotals(
                expected=round_hours(terms.expected_through),
                worked=round_hours(terms.worked),
                balance=round_hours(terms.balance),
            )
    rows = [
        _week(
            project,
            contract,
            by_day,
            holidays,
            worked,
            week_of,
            expected.get(week_of),
            closes.get(week_of + _SUNDAY),
        )
        for week_of in mondays
    ]
    return Ledger(
        weeks=rows,
        since=contract.starts_on if contract is not None else None,
        totals=totals,
    )


def _week(
    project: Project,
    contract: Contract | None,
    by_day: Mapping[date, Absence],
    holidays: Mapping[date, str],
    worked: Mapping[date, float],
    week_of: date,
    expected: float | None,
    closing: float | None,
) -> LedgerWeek:
    days = [week_of + timedelta(days=offset) for offset in range(7)]
    hours = [worked.get(day, 0.0) for day in days]
    goal, goal_type = project.effective_goal(week_of)
    notes: list[LedgerNote] = []
    if contract is not None:
        for day in days[:5]:
            if day in holidays:
                notes.append(LedgerNote(date=day, kind=LedgerNoteKind.HOLIDAY, name=holidays[day]))
            absence = by_day.get(day)
            if absence is not None:
                notes.append(
                    LedgerNote(
                        date=day, kind=LedgerNoteKind(absence.type), half_day=absence.half_day
                    )
                )
    return LedgerWeek(
        week_of=week_of,
        worked=round_hours(sum(hours)),
        days=[round_hours(h) for h in hours],
        effective_goal=goal,
        effective_goal_type=goal_type,
        effective_goal_overridden=project.goal_overridden(week_of),
        contract_expected=expected,
        balance_end=round_hours(closing) if closing is not None else None,
        notes=notes,
    )
