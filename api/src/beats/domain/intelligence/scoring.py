"""Productivity score — one number, and its history."""

from collections import defaultdict
from datetime import date, datetime, timedelta
from statistics import median
from zoneinfo import ZoneInfo

from beats.domain.models import Beat, Project
from beats.domain.ports import ProjectLister, RangeBeatReader
from beats.domain.utils import local_date

from ._support import UTC_TZ, _beats_covering, _monday_of, _rescale_score

NEUTRAL_GOAL_SCORE = 13


def _goal_score(projects: list[Project], project_hours: dict[str, float], monday: date) -> int:
    """The goal component (0-25) for one week: mean progress towards each
    project's goal for that week, or the neutral 13 when no project's week has
    one — a project whose only goal is a contract that has not started, or an
    override saying "no goal", counts as none that week."""
    progresses = []
    for p in projects:
        goal, _ = p.effective_goal(monday)
        if goal and goal > 0:
            progresses.append(min(project_hours.get(p.id or "", 0) / goal, 1.0))
    if not progresses:
        return NEUTRAL_GOAL_SCORE
    return round(sum(progresses) / len(progresses) * 25)


async def compute_productivity_score(
    beat_repo: RangeBeatReader, project_repo: ProjectLister, tz: ZoneInfo = UTC_TZ
) -> dict:
    """Compute current productivity score (0-100) with component breakdown."""
    today = datetime.now(tz).date()
    week_start = _monday_of(today)

    beats = await _beats_covering(beat_repo, today - timedelta(days=6), today)
    projects = await project_repo.list(archived=False)

    # 1. Consistency (0-25): weekdays tracked in last 5 weekdays
    tracked_dates = {local_date(b.start, tz) for b in beats}
    weekdays = []
    for i in range(7):
        d = today - timedelta(days=i)
        if d.weekday() < 5:  # Mon-Fri
            weekdays.append(d)
        if len(weekdays) == 5:
            break
    weekdays_tracked = sum(1 for d in weekdays if d in tracked_dates)
    consistency = round(weekdays_tracked / max(len(weekdays), 1) * 25)

    # 2. Goal progress (0-25): mean progress over the projects whose week has
    # a goal (`effective_goal` — the contract's on a day job it governs, the
    # personal goal elsewhere); neutral when no project's week has one.
    week_beats = [b for b in beats if local_date(b.start, tz) >= week_start]
    project_hours: dict[str, float] = defaultdict(float)
    for b in week_beats:
        project_hours[b.project_id] += b.duration.total_seconds() / 3600
    goal_score = _goal_score(projects, project_hours, week_start)

    # 3. Session quality (0-25)
    durations = [b.duration.total_seconds() / 60 for b in beats]
    if durations:
        med = median(durations)
        if med < 15:
            length_score = 5
        elif med < 30:
            length_score = 10
        elif med < 60:
            length_score = 18
        elif med < 120:
            length_score = 23
        else:
            length_score = 25

        # Fragmentation penalty: check for gaps < 5 min between same-day sessions
        day_beats: dict[date, list[Beat]] = defaultdict(list)
        for b in beats:
            day_beats[local_date(b.start, tz)].append(b)
        frag_penalty = 0
        for day_b in day_beats.values():
            sorted_b = sorted(day_b, key=lambda x: x.start)
            for i in range(1, len(sorted_b)):
                prev_end = sorted_b[i - 1].end
                curr_start = sorted_b[i].start
                if prev_end:
                    gap = (curr_start - prev_end).total_seconds() / 60
                    if 0 < gap < 5:
                        frag_penalty += 5
        quality_score = max(0, min(25, length_score - frag_penalty))
    else:
        quality_score = 0

    total = _rescale_score(consistency, goal_score, quality_score)
    return {
        "score": total,
        "components": {
            "consistency": consistency,
            "goals": goal_score,
            "quality": quality_score,
        },
    }


async def compute_productivity_score_history(
    beat_repo: RangeBeatReader, project_repo: ProjectLister, weeks: int = 8, tz: ZoneInfo = UTC_TZ
) -> list[dict]:
    """Compute weekly productivity scores for the last N weeks."""
    today = datetime.now(tz).date()
    current_monday = _monday_of(today)
    history = []

    # Load all data for the full range
    range_start = current_monday - timedelta(weeks=weeks)
    all_beats = await beat_repo.list_completed_in_range(range_start, today)
    projects = await project_repo.list(archived=False)

    for w in range(weeks, 0, -1):
        monday = current_monday - timedelta(weeks=w)
        sunday = monday + timedelta(days=6)

        week_beats = [b for b in all_beats if monday <= local_date(b.start, tz) <= sunday]

        # Simplified score for history
        tracked_dates = {local_date(b.start, tz) for b in week_beats}
        weekdays = [monday + timedelta(days=d) for d in range(5)]
        consistency = round(sum(1 for d in weekdays if d in tracked_dates) / 5 * 25)

        project_hours: dict[str, float] = defaultdict(float)
        for b in week_beats:
            project_hours[b.project_id] += b.duration.total_seconds() / 3600
        goal_s = _goal_score(projects, project_hours, monday)

        durs = [b.duration.total_seconds() / 60 for b in week_beats]
        if durs:
            med = median(durs)
            if med < 15:
                quality = 5
            elif med < 30:
                quality = 10
            elif med < 60:
                quality = 18
            elif med < 120:
                quality = 23
            else:
                quality = 25
        else:
            quality = 0

        score = _rescale_score(consistency, goal_s, quality)
        history.append({"week_of": monday.isoformat(), "score": score})

    return history
