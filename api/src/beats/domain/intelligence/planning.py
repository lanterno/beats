"""Smart daily plan — what to work on today, from what the last weeks looked like."""

from collections import defaultdict
from datetime import date, timedelta
from zoneinfo import ZoneInfo

from beats.domain.ports import ProjectLister, RangeBeatReader
from beats.domain.utils import local_date

from ._support import UTC_TZ, _beats_covering, _format_hours, _monday_of


async def suggest_daily_plan(
    beat_repo: RangeBeatReader,
    project_repo: ProjectLister,
    target_date: date,
    tz: ZoneInfo = UTC_TZ,
) -> list[dict]:
    """Suggest up to 3 projects and durations to focus on today."""
    dow = target_date.weekday()
    monday = _monday_of(target_date)

    beats = await _beats_covering(beat_repo, target_date - timedelta(weeks=8), target_date)
    projects = await project_repo.list(archived=False)
    project_map = {p.id: p for p in projects}

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
        goal, _ = p.effective_goal(monday)
        unmet_weight = 0.0
        remaining_reason = ""
        if goal and goal > 0:
            remaining = goal - week_hours.get(pid, 0)
            if remaining > 0:
                unmet_weight = min(remaining / goal, 1.0)
                remaining_reason = f"You need {remaining:.1f}h more to hit your weekly goal"

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
