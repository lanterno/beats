"""The weekly digest and the one-line observation that heads it."""

from collections import defaultdict
from datetime import date, timedelta
from statistics import median
from zoneinfo import ZoneInfo

from beats.domain.models import ProjectBreakdownEntry, WeeklyDigest
from beats.domain.ports import ProjectLister, RangeBeatReader
from beats.domain.utils import local_date

from ._support import UTC_TZ, _beats_in_local_range, _format_hours, _rescale_score


async def generate_weekly_digest(
    beat_repo: RangeBeatReader,
    project_repo: ProjectLister,
    week_monday: date,
    tz: ZoneInfo = UTC_TZ,
) -> WeeklyDigest:
    """Generate a weekly summary digest for the given week."""
    sunday = week_monday + timedelta(days=6)
    prev_monday = week_monday - timedelta(days=7)
    prev_sunday = prev_monday + timedelta(days=6)

    beats = await _beats_in_local_range(beat_repo, week_monday, sunday, tz)
    prev_beats = await _beats_in_local_range(beat_repo, prev_monday, prev_sunday, tz)
    projects = await project_repo.list(archived=False)
    project_map = {p.id: p for p in projects}

    # Totals
    total_minutes = sum(b.duration.total_seconds() / 60 for b in beats)
    total_hours = total_minutes / 60
    session_count = len(beats)
    active_dates = {local_date(b.start, tz) for b in beats}
    active_days = len(active_dates)

    # Project breakdown
    proj_minutes: dict[str, float] = defaultdict(float)
    for b in beats:
        proj_minutes[b.project_id] += b.duration.total_seconds() / 60
    breakdown = []
    for pid, mins in sorted(proj_minutes.items(), key=lambda x: -x[1]):
        p = project_map.get(pid)
        breakdown.append(
            ProjectBreakdownEntry(
                project_id=pid,
                name=p.name if p else "Unknown",
                hours=round(mins / 60, 2),
            )
        )

    # Top project
    top = breakdown[0] if breakdown else None

    # Longest day
    day_minutes: dict[date, float] = defaultdict(float)
    for b in beats:
        day_minutes[local_date(b.start, tz)] += b.duration.total_seconds() / 60
    if day_minutes:
        # `max(d, key=d.get)` is the idiomatic shape but ty can't
        # follow the bound-method's signature past the dict's
        # variance. Lambda has the same runtime cost and types
        # cleanly.
        longest_date = max(day_minutes, key=lambda d: day_minutes[d])
        longest_day = longest_date.strftime("%A")
        longest_day_hours = day_minutes[longest_date] / 60
    else:
        longest_day = None
        longest_day_hours = 0

    # Vs last week
    prev_minutes = sum(b.duration.total_seconds() / 60 for b in prev_beats)
    if prev_minutes > 0:
        vs_last_week_pct = round((total_minutes - prev_minutes) / prev_minutes * 100, 1)
    else:
        vs_last_week_pct = None

    # Streak (consecutive days ending on sunday)
    streak = 0
    d = sunday
    all_dates = active_dates
    while d >= week_monday - timedelta(days=30):
        if d in all_dates:
            streak += 1
            d -= timedelta(days=1)
        else:
            break

    # Previous weeks data for observation
    prev_proj_minutes: dict[str, float] = defaultdict(float)
    for b in prev_beats:
        prev_proj_minutes[b.project_id] += b.duration.total_seconds() / 60

    observation = generate_observation(
        proj_minutes, prev_proj_minutes, project_map, day_minutes, total_hours, session_count
    )

    # Compute productivity score for the week
    # Simplified: use the session data we already have
    durs = [b.duration.total_seconds() / 60 for b in beats]
    weekday_dates = {d for d in active_dates if d.weekday() < 5}
    possible_weekdays = sum(1 for i in range(5) if week_monday + timedelta(days=i) <= sunday)
    consistency = round(len(weekday_dates) / max(possible_weekdays, 1) * 25)
    quality = 0
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
    # Simplified digest score: goals held at a neutral 13 (unlike the live
    # productivity score, which computes real weekly goal progress),
    # consistency + quality from this week's sessions, rescaled to 0-100.
    score = _rescale_score(consistency, 13, quality)

    return WeeklyDigest(
        week_of=week_monday,
        total_hours=round(total_hours, 2),
        session_count=session_count,
        active_days=active_days,
        top_project_id=top.project_id if top else None,
        top_project_name=top.name if top else None,
        top_project_hours=top.hours if top else 0,
        vs_last_week_pct=vs_last_week_pct,
        longest_day=longest_day,
        longest_day_hours=round(longest_day_hours, 2),
        best_streak=streak,
        observation=observation,
        project_breakdown=breakdown,
        productivity_score=score,
    )


def generate_observation(
    proj_minutes: dict[str, float],
    prev_proj_minutes: dict[str, float],
    project_map: dict,
    day_minutes: dict[date, float],
    total_hours: float,
    session_count: int,
) -> str:
    """Generate a single-sentence observation about the week."""
    # 1. New project this week
    for pid, mins in proj_minutes.items():
        if pid not in prev_proj_minutes and mins > 30:
            p = project_map.get(pid)
            name = p.name if p else "a project"
            return f"You started working on {name} this week — {_format_hours(mins)} logged."

    # 2. Big delta project (>50% change)
    for pid, mins in proj_minutes.items():
        prev = prev_proj_minutes.get(pid, 0)
        if prev > 30 and mins > 30:
            change = (mins - prev) / prev * 100
            if abs(change) > 50:
                p = project_map.get(pid)
                name = p.name if p else "a project"
                direction = "more" if change > 0 else "less"
                return (
                    f"You spent {abs(change):.0f}% {direction} time on "
                    f"{name} compared to last week."
                )

    # 3. Day pattern
    if day_minutes:
        longest_date = max(day_minutes, key=lambda d: day_minutes[d])
        day_name = longest_date.strftime("%A")
        hrs = day_minutes[longest_date] / 60
        return f"Your most productive day was {day_name} with {hrs:.1f}h tracked."

    # 4. Fallback
    return f"You tracked {total_hours:.1f}h across {session_count} sessions this week."
