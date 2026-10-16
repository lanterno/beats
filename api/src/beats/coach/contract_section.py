"""The day context's contract section: each day job's week as the coach reads it.

The figures are the project page's (`ContractService.current_weeks`); this
module only words them, and decides what of them leaves Beats. PRIVACY.md
is the list, and a change to what is sent is made there first:

- the week's expected hours after holidays and days off, the hours worked
  under the contract (on its days only) and what is left;
- the dates of this week's holidays and days off that made it shorter —
  a public holiday by its name, which can name the region (Augsburg Peace
  Festival), a company holiday only as "company holiday" (its name is the
  user's own words), a day off only as "day off" or "half day off" (its
  type can be health data, its note is free text, and the arithmetic
  treats them all alike);
- today's expected hours, the running balance and its by-Sunday
  projection — or, once the contract has ended (earlier this week), only
  its final balance — and the end date when it falls in this week.

The balance is a sum, opening + worked − expected + adjusted, and only
the sum is sent; on a contract's first day it is the opening balance.
Never the region's codes, the opening balance or an adjustment as a
figure of its own, another week's days, or a contract that ended before
this week.

Two rules here are the SPA's too, and a change to either is made in both:
`describe_balance` is `describeBalance` (ui/client/entities/project/model/
contract.ts), and `_by_sunday` is `projection()` (…/model/standing.ts).
"""

from collections.abc import Iterable, Mapping
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from beats.coach.repos import fmt_contract_goal
from beats.domain.contracts import counts_worked, owes, round_hours, term_on
from beats.domain.holidays import HolidaySource, contract_calendar
from beats.domain.models import Contract, ContractDay, ContractWeek, Project

HEADER = "### Day-job contracts (this week, as of today)"

# Fixed, not strftime("%a"): the process locale must not rename the days.
_WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def _one_decimal(hours: float) -> Decimal:
    """`Number(hours.toFixed(1))`, as the SPA rounds a figure it shows.

    `toFixed` rounds the float's exact binary value, ties away from zero;
    `Decimal(hours)` is that exact value, so 0.25 h reads 0.3 on both sides
    where Python's `round` would say 0.2. A result of −0.0 is neither over
    nor owed.
    """
    return Decimal(hours).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


def _hours(hours: float) -> str:
    return f"{_one_decimal(hours)} h"


def _hundredths(hours: float) -> str:
    """A week figure as the wire carries it, to the hundredth — "40.0",
    "23.75", "6.4" — so the week's line adds up as printed: rounding
    23.75 h worked and 16.25 h to go to the tenth each would read 23.8
    and 16.3 against 40.0. The page's tenth is this figure rounded.
    """
    exact = Decimal(repr(round_hours(hours))).quantize(Decimal("0.01")) + 0  # −0.00 → 0.00
    text = f"{exact:.2f}"
    return text[:-1] if text.endswith("0") else text


def describe_balance(hours: float) -> str:
    """A balance with its sign made unmistakable: "+4.5 h over", "−2.0 h owed"
    (U+2212) or "even" — the twin of `describeBalance` in the SPA's
    `entities/project/model/contract.ts`. Rounded to the decimal shown before
    the sign is judged, so −0.04 h is "even", never "−0.0 h owed"."""
    rounded = _one_decimal(hours)
    if rounded > 0:
        return f"+{rounded} h over"
    if rounded < 0:
        return f"−{-rounded} h owed"
    return "even"


def _left(remaining: float) -> str:
    """What is left of the week: "6.4 h to go", "week met", "week done, 0.45 h
    over" — judged at the tenth, as the SPA's `doneSentence` is, and given to
    the hundredth, as the week's other figures are."""
    rounded = _one_decimal(remaining)
    if rounded > 0:
        return f"{_hundredths(remaining)} h to go"
    if rounded == 0:
        return "week met"
    return f"week done, {_hundredths(-remaining)} h over"


def _its_days_only(contract: Contract, week: ContractWeek) -> str:
    """A note that the worked figure leaves days out, on a week the contract
    starts or ends inside: the project page's Worked counts the whole week,
    so the coach's smaller figure is not a contradiction."""
    sunday = week.week_of + timedelta(days=6)
    starts_inside = contract.starts_on > week.week_of
    ends_inside = contract.ended_on is not None and contract.ended_on < sunday
    return " (its days this week only)" if starts_inside or ends_inside else ""


def _by_sunday(week: ContractWeek, today: date) -> tuple[float, float] | None:
    """The balance on Monday morning if no more hours are worked this week,
    and if the week's expectation is met — the twin of `projection()` in the
    SPA's `entities/project/model/standing.ts`.

    The balance counts today's hours already but charges today's expectation
    only tomorrow, so it reads high all day; stopping now charges every day
    from today through Sunday against it, and meeting the week adds back
    what is still to go. None without a balance or an expectation, or when
    `today` is not in the week.
    """
    if week.balance is None or week.expected is None:
        return None
    if not week.week_of <= today <= week.week_of + timedelta(days=6):
        return None
    ahead = sum(day.expected for day in week.days if day.date >= today)
    stop_now = week.balance - ahead
    remaining = week.remaining if week.remaining is not None else week.expected - week.worked
    return round_hours(stop_now), round_hours(stop_now + max(remaining, 0.0))


def _day_off(day: ContractDay, company_days: set[date]) -> str | None:
    """Why a day owed less, in the words that may leave Beats; the holiday
    wins over an absence on the same day, as `expected_on` decides."""
    if day.holiday is not None:
        return "company holiday" if day.date in company_days else f"public holiday ({day.holiday})"
    if day.absence is not None:
        return "half day off" if day.absence.half_day else "day off"
    return None


def _shortened(contract: Contract, day: ContractDay) -> bool:
    """Whether a holiday or an absence on `day` could have cost the week
    anything: a weekday inside the contract's dates, under a term that owes
    hours. A Saturday holiday, or a vacation before the contract began, owed
    nothing to start with and says nothing the coach needs."""
    return (
        day.date.weekday() < 5
        and counts_worked(contract, day.date)
        and owes(term_on(contract, day.date))
    )


def _project_lines(name: str, contract: Contract, week: ContractWeek, today: date) -> list[str]:
    sunday = week.week_of + timedelta(days=6)
    if contract.ended_on is not None and contract.ended_on < week.week_of:
        return []  # a finished job; its frozen balance is not live news
    # Ended earlier this week: nothing worked from here on counts, so the
    # balance is final and the week's figures, today's expectation and the
    # projection are left out, as the project page leaves them out. On the
    # last day itself the page already says "Final balance", but today's
    # hours still count and today's expectation is still charged tomorrow,
    # so here that day stays live and its projection is the true close.
    if contract.ended_on is not None and contract.ended_on < today:
        if week.balance is None or week.balance_as_of != today:
            return []
        return [
            f"  {name} final balance: {describe_balance(week.balance)}"
            f" (contract ended {contract.ended_on})"
        ]
    lines: list[str] = []

    # `expected` and `remaining` are None together (ContractWeek); both are
    # named so the type checker knows it.
    if week.expected is not None and week.remaining is not None:
        # Worked under the contract — on the days it covers, what "to go"
        # and the balance count — read back off the week's own figures, so
        # worked and to go add up to the expectation; all three are printed
        # to the hundredth, so they add up as printed too. Not summed from
        # the days: each is already rounded to the hundredth, and the sum
        # drifts (87 s on two days and an hour today sum to 1.04 h, where
        # the week counts 1.05 h with 30.95 h to go).
        worked = round_hours(week.expected - week.remaining)
        term = term_on(contract, max(today, contract.starts_on))
        label = fmt_contract_goal(term) if term is not None else "contract"
        lines.append(
            f"  {name} ({label}): this week expects {_hundredths(week.expected)} h after"
            f" holidays and days off — {_hundredths(worked)} h worked under the"
            f" contract{_its_days_only(contract, week)}, {_left(week.remaining)}"
        )
        # Which of this week's days off came from the employer's own list:
        # their names are the user's words, so only the fact is sent.
        company_days = {
            holiday.date
            for holiday in contract_calendar(contract, week.week_of, sunday)
            if holiday.source is HolidaySource.COMPANY
        }
        for day in week.days:
            reason = _day_off(day, company_days) if _shortened(contract, day) else None
            if reason is not None:
                lines.append(f"    {_WEEKDAYS[day.date.weekday()]} {day.date}: {reason}")

    if week.balance is not None and week.balance_as_of == today:
        today_day = next((day for day in week.days if day.date == today), None)
        if today_day is not None:
            lines.append(
                f"  {name} today: {_hours(today_day.expected)} expected"
                " (charged to the balance tomorrow)"
                if today_day.expected > 0
                else f"  {name} today: nothing expected"
            )
        lines.append(f"  {name} running balance: {describe_balance(week.balance)}")
        projected = _by_sunday(week, today)
        if projected is not None:
            stop_now, met = projected
            lines.append(
                f"  {name} by Sunday: {describe_balance(stop_now)} if you stop now,"
                f" {describe_balance(met)} if the rest of the week is met"
            )

    if lines and contract.ended_on is not None and contract.ended_on <= sunday:
        lines.append(f"  {name}: contract ends {contract.ended_on}")
    return lines


def contract_section(
    projects: Iterable[Project], weeks: Mapping[str, ContractWeek], today: date
) -> list[str]:
    """The section's lines, header first; empty when no day job has a week
    worth a line — then the day context leaves the header out too.

    `weeks` is `ContractService.current_weeks` for `today`: one entry per
    day job with a contract, the project page's figures. A project with
    neither an expectation this week nor a balance today is left out.
    """
    lines: list[str] = []
    for project in projects:
        week = weeks.get(project.id) if project.id else None
        if week is None or project.contract is None:
            continue
        lines += _project_lines(project.name, project.contract, week, today)
    return [HEADER, *lines] if lines else []
