"""Smart daily plan — what to work on today, from what the last weeks looked like."""

from collections import defaultdict
from collections.abc import Mapping
from datetime import date, timedelta
from zoneinfo import ZoneInfo

from beats.domain.models import Beat, Project
from beats.domain.utils import local_date

from ._support import UTC_TZ, _format_hours, _monday_of
from .goals import WeekGoal, nominal_week_goals


def suggest_daily_plan(
    beats: list[Beat],
    projects: list[Project],
    target_date: date,
    tz: ZoneInfo = UTC_TZ,
    goals: Mapping[str, WeekGoal] | None = None,
) -> list[dict]:
    """Suggest up to 3 projects and durations to focus on today.

    Pure: `beats` are the completed beats of the eight weeks up to
    `target_date` (`_beats_covering`), and `goals` is what each project's
    week asks for (`week_goals`) — on a day job the contract governs, the
    week's expectation after holidays and absences, so the remaining hours
    quoted here are the week card's, not the nominal term's. Left out, the
    nominal goals are used.
    """
    dow = target_date.weekday()
    monday = _monday_of(target_date)
    if goals is None:
        goals = nominal_week_goals(projects, monday)

    # Keyed by a non-None id: `Project.id` is Optional on the model (the
    # standard post-Mongo shape) but populated for every row the repo
    # returns, and the day-of-week buckets below index by that key.
    project_map = {p.id: p for p in projects if p.id}

    # Day-of-week averages per project
    dow_minutes: dict[str, list[float]] = defaultdict(list)
    for w in range(1, 9):
        d = target_date - timedelta(weeks=w)
        if d.weekday() != dow:
            continue
        project_day_mins: dict[str, float] = defaultdict(float)
        for b in beats:
            if local_date(b.start, tz) == d:
                project_day_mins[b.project_id] += b.duration.total_seconds() / 60
        for pid in project_map:
            dow_minutes[pid].append(project_day_mins.get(pid, 0))

    day_avgs = {
        pid: sum(mins) / len(mins) for pid, mins in dow_minutes.items() if mins and sum(mins) > 0
    }

    # Weekly goal remaining
    week_beats = [b for b in beats if local_date(b.start, tz) >= monday]
    week_hours: dict[str, float] = defaultdict(float)
    for b in week_beats:
        week_hours[b.project_id] += b.duration.total_seconds() / 3600

    # Recency (worked yesterday?)
    yesterday = target_date - timedelta(days=1)
    yesterday_projects = {b.project_id for b in beats if local_date(b.start, tz) == yesterday}

    # Score each project
    scores: list[tuple[str, float, int, str]] = []
    day_names = [
        "Mondays",
        "Tuesdays",
        "Wednesdays",
        "Thursdays",
        "Fridays",
        "Saturdays",
        "Sundays",
    ]

    for p in projects:
        if p.archived:
            continue
        pid = p.id or ""
        avg = day_avgs.get(pid, 0)

        # Unmet goal weight
        week_goal = goals.get(pid)
        goal = week_goal.hours if week_goal is not None else None
        unmet_weight = 0.0
        remaining_reason = ""
        if goal and goal > 0:
            remaining = goal - week_hours.get(pid, 0)
            if remaining > 0:
                unmet_weight = min(remaining / goal, 1.0)
                remaining_reason = (
                    f"You need {remaining:.1f}h more this week under your contract"
                    if week_goal is not None and week_goal.source == "contract"
                    else f"You need {remaining:.1f}h more to hit your weekly goal"
                )

        recency = 1.0 if pid in yesterday_projects else 0.0

        score = (avg / 60 * 0.4) + (unmet_weight * 0.4) + (recency * 0.2)
        if score < 0.05:
            continue

        # Suggested minutes
        suggested = round(avg / 15) * 15 if avg > 10 else 60
        suggested = max(15, min(suggested, 240))
        if goal and goal > 0:
            remaining_min = max(0, (goal - week_hours.get(pid, 0)) * 60)
            suggested = min(suggested, round(remaining_min / 15) * 15)
            suggested = max(15, suggested)

        # Reasoning
        if remaining_reason:
            reasoning = remaining_reason
        elif avg > 10:
            reasoning = f"On {day_names[dow]} you usually spend {_format_hours(avg)}"
        elif pid in yesterday_projects:
            reasoning = "You worked on this yesterday — keep the momentum"
        else:
            reasoning = "Based on your recent activity"

        scores.append((pid, score, suggested, reasoning))

    scores.sort(key=lambda x: -x[1])
    return [
        {
            "project_id": pid,
            "project_name": project_map[pid].name if pid in project_map else "Unknown",
            "suggested_minutes": mins,
            "reasoning": reason,
        }
        for pid, _, mins, reason in scores[:3]
    ]
