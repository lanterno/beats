"""The goal a project's week is measured against, for the readers that quote the week's figure.

`Project.effective_goal` is nominal by decision (docs/work-contracts-roadmap.md,
Phase 5): on a day job the contract governs it is the term's plain weekly
hours, before holidays and absences, and the score, the health rail and the
coach want exactly that. Three readers quote the week's figure — the Inbox's
planning line, the pacing card and the stale-project card — and there it must
be what the week actually expects, or the Inbox contradicts the week card
beside it on a week with a vacation booked. Those three take a map built here:
for a governed week the contract's adjusted expectation, read through
`WeekExpectationReader`; for every other project the nominal goal, exactly as
before.
"""

from collections.abc import Iterable
from dataclasses import dataclass, replace
from datetime import date
from typing import Literal

from beats.domain.models import GoalType, Project
from beats.domain.ports import WeekExpectationReader


@dataclass(frozen=True)
class WeekGoal:
    """Hours a project's week asks for — None when nothing sets a goal — and
    whose figure it is, which decides the wording: a contract is not "hit"."""

    hours: float | None
    goal_type: GoalType
    source: Literal["contract", "personal"]


def nominal_week_goals(projects: Iterable[Project], monday: date) -> dict[str, WeekGoal]:
    """`effective_goal` per project id: the contract's plain hours on a week it
    governs, the personal goal as overridden everywhere else."""
    goals: dict[str, WeekGoal] = {}
    for project in projects:
        if not project.id:
            continue
        hours, goal_type = project.effective_goal(monday)
        source = "contract" if project.goal_term(monday) is not None else "personal"
        goals[project.id] = WeekGoal(hours=hours, goal_type=goal_type, source=source)
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
