"""The goal a project's week is measured against, for the readers that quote the week's figure.

`Project.effective_goal` is nominal by decision (docs/work-contracts.md,
"The goal"): on a day job the contract governs it is the term's plain weekly
hours, before holidays and absences, and the score, the health rail and the
coach want exactly that. Three readers quote the week's figure — the Inbox's
planning line, the pacing card and the stale-project card — and there it must
be what the week actually expects, or the Inbox contradicts the week card
beside it on a week with a vacation booked. Those three take a map built here:
for a governed week the contract's adjusted expectation, read through
`WeekExpectationReader`; for every other project the nominal goal, exactly as
before.

The hours counted against a governed week's figure are the ones the week card
subtracts for its Remaining: worked on a day the balance counts
(`counts_worked`), inside the contract's dates under a term that owes hours.
On a week a term that owes nothing begins or ends, the hours worked under it
are tracked, and owe the week's figure nothing.
"""

from collections.abc import Iterable
from dataclasses import dataclass, replace
from datetime import date, timedelta
from typing import Literal

from beats.domain.contracts import counts_worked
from beats.domain.models import GoalType, Project
from beats.domain.ports import WeekExpectationReader


@dataclass(frozen=True)
class WeekGoal:
    """Hours a project's week asks for — None when nothing sets a goal — and
    whose figure it is, which decides the wording: a contract is not "hit".

    `counted_days` are the days of the week whose hours count against
    `hours`, or None for every day: on a governed week, the days the balance
    counts (`counts_worked`), so the hours to go are the week card's
    Remaining."""

    hours: float | None
    goal_type: GoalType
    source: Literal["contract", "personal"]
    counted_days: frozenset[date] | None = None

    def counts(self, day: date) -> bool:
        """Whether hours worked on `day` count against the week's figure."""
        return self.counted_days is None or day in self.counted_days


def nominal_week_goals(projects: Iterable[Project], monday: date) -> dict[str, WeekGoal]:
    """`effective_goal` per project id: the contract's plain hours on a week it
    governs, with the days whose hours count against them, the personal goal
    as overridden everywhere else."""
    goals: dict[str, WeekGoal] = {}
    for project in projects:
        if not project.id:
            continue
        hours, goal_type = project.effective_goal(monday)
        contract = project.contract
        if project.goal_term(monday) is not None and contract is not None:
            week = (monday + timedelta(days=offset) for offset in range(7))
            counted = frozenset(day for day in week if counts_worked(contract, day))
            goals[project.id] = WeekGoal(hours, goal_type, "contract", counted)
        else:
            goals[project.id] = WeekGoal(hours=hours, goal_type=goal_type, source="personal")
    return goals


async def week_goals(
    projects: Iterable[Project], monday: date, contracts: WeekExpectationReader | None
) -> dict[str, WeekGoal]:
    """`nominal_week_goals`, with each governed week's hours replaced by what
    the contract expects of it after holidays and absences. Without a reader
    — the coach builds the service without one and never asks for a
    remaining figure — the nominal map is the answer."""
    projects = list(projects)
    goals = nominal_week_goals(projects, monday)
    if contracts is None:
        return goals
    for project in projects:
        if project.id and goals[project.id].source == "contract":
            expected = await contracts.expected_for_week(project, monday)
            goals[project.id] = replace(goals[project.id], hours=expected)
    return goals
