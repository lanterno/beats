"""Pattern detection — the insight cards shown on the dashboard.

Each detector is a pure function of the beats it is handed, so they can be
tested directly rather than through a service that only exists to hold repos.
"""

import uuid
from collections import defaultdict
from datetime import date, datetime, timedelta
from statistics import median
from zoneinfo import ZoneInfo

from beats.domain.models import Beat, FlowWindow, InsightCard
from beats.domain.ports import ProjectLister, RangeBeatReader
from beats.domain.utils import local_date, local_dt

from ._support import UTC_TZ, _beats_covering, _format_hours, _monday_of


async def detect_patterns(
    beat_repo: RangeBeatReader, project_repo: ProjectLister, tz: ZoneInfo = UTC_TZ
) -> list[InsightCard]:
    """Detect non-obvious patterns in the user's data."""
    today = datetime.now(tz).date()
    insights: list[InsightCard] = []

    beats = await _beats_covering(beat_repo, today - timedelta(days=60), today)
    projects = await project_repo.list(archived=False)

    insights.extend(detect_day_pattern(beats, today, tz))
    insights.extend(detect_peak_hours(beats, tz))
    insights.extend(detect_stale_projects(beats, projects, today, tz))
    insights.extend(detect_session_trend(beats, today, tz))
    insights.extend(detect_goal_pacing(beats, projects, today, tz))

    insights.sort(key=lambda x: -x.priority)
    return insights


def detect_day_pattern(beats: list[Beat], today: date, tz: ZoneInfo = UTC_TZ) -> list[InsightCard]:
    """Check if any day of week is significantly more productive."""
    # Aggregate hours per weekday over the last 8 weeks
    day_hours: dict[int, list[float]] = defaultdict(list)
    for w in range(8):
        monday = _monday_of(today) - timedelta(weeks=w)
        for dow in range(7):
            d = monday + timedelta(days=dow)
            mins = sum(
                b.duration.total_seconds() / 60 for b in beats if local_date(b.start, tz) == d
            )
            day_hours[dow].append(mins)

    day_avgs = {dow: sum(hrs) / len(hrs) for dow, hrs in day_hours.items() if hrs}
    if not day_avgs:
        return []

    overall_avg = sum(day_avgs.values()) / len(day_avgs)
    if overall_avg < 10:  # Less than 10 min avg per day — not enough data
        return []

    day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    for dow, avg in day_avgs.items():
        if avg > overall_avg * 1.5 and avg > 30:
            ratio = avg / overall_avg
            return [
                InsightCard(
                    id=str(uuid.uuid4()),
                    type="day_pattern",
                    title=f"{day_names[dow]}s are your power day",
                    body=f"You average {ratio:.1f}x more tracked time on {day_names[dow]}s "
                    f"({_format_hours(avg)} vs {_format_hours(overall_avg)} overall).",
                    data={"day": day_names[dow], "ratio": round(ratio, 1)},
                    priority=3,
                )
            ]
    return []


def detect_peak_hours(beats: list[Beat], tz: ZoneInfo = UTC_TZ) -> list[InsightCard]:
    """Find peak productivity time blocks."""
    blocks: dict[int, float] = defaultdict(float)  # 2-hour blocks: 0=0-2, 1=2-4, etc.
    for b in beats:
        block = local_dt(b.start, tz).hour // 2
        blocks[block] += b.duration.total_seconds() / 60

    if len(blocks) < 3:
        return []

    values = list(blocks.values())
    med = median(values)
    if med < 1:
        return []

    peak_block = max(blocks, key=lambda b: blocks[b])
    if blocks[peak_block] > med * 2:
        start_h = peak_block * 2
        end_h = start_h + 2
        return [
            InsightCard(
                id=str(uuid.uuid4()),
                type="time_pattern",
                title=f"Peak hours: {start_h}:00–{end_h}:00",
                body=f"Your longest and most frequent sessions happen between "
                f"{start_h}:00 and {end_h}:00. Consider protecting this time for deep work.",
                data={"start_hour": start_h, "end_hour": end_h},
                priority=3,
            )
        ]
    return []


def detect_stale_projects(
    beats: list[Beat], projects: list, today: date, tz: ZoneInfo = UTC_TZ
) -> list[InsightCard]:
    """Alert on projects with goals but no recent activity."""
    last_beat: dict[str, date] = {}
    for b in beats:
        pid = b.project_id
        d = local_date(b.start, tz)
        if pid not in last_beat or d > last_beat[pid]:
            last_beat[pid] = d

    results = []
    for p in projects:
        if p.archived or not p.weekly_goal:
            continue
        last = last_beat.get(p.id or "")
        if last is None or (today - last).days >= 14:
            days = (today - last).days if last else 999
            results.append(
                InsightCard(
                    id=str(uuid.uuid4()),
                    type="stale_project",
                    title=f"{p.name} needs attention",
                    body=f"You haven't tracked time on {p.name} in {days} days, "
                    f"but it still has a weekly goal of {p.weekly_goal}h.",
                    data={"project_id": p.id, "days_since": days},
                    priority=4,
                )
            )
    return results


def detect_session_trend(
    beats: list[Beat], today: date, tz: ZoneInfo = UTC_TZ
) -> list[InsightCard]:
    """Compare this week's avg session length to 4-week average."""
    this_monday = _monday_of(today)
    four_weeks_ago = this_monday - timedelta(weeks=4)

    this_week = [b for b in beats if local_date(b.start, tz) >= this_monday]
    prev_weeks = [b for b in beats if four_weeks_ago <= local_date(b.start, tz) < this_monday]

    if len(this_week) < 3 or len(prev_weeks) < 5:
        return []

    this_avg = sum(b.duration.total_seconds() / 60 for b in this_week) / len(this_week)
    prev_avg = sum(b.duration.total_seconds() / 60 for b in prev_weeks) / len(prev_weeks)

    if prev_avg < 5:
        return []

    change = (this_avg - prev_avg) / prev_avg * 100
    if abs(change) < 30:
        return []

    direction = "longer" if change > 0 else "shorter"
    return [
        InsightCard(
            id=str(uuid.uuid4()),
            type="session_trend",
            title=f"Sessions are {abs(change):.0f}% {direction}",
            body=f"Your average session is {_format_hours(this_avg)} this week vs "
            f"{_format_hours(prev_avg)} over the last 4 weeks.",
            data={"change_pct": round(change, 1), "this_week_avg": round(this_avg, 1)},
            priority=2,
        )
    ]


def detect_goal_pacing(
    beats: list[Beat], projects: list, today: date, tz: ZoneInfo = UTC_TZ
) -> list[InsightCard]:
    """Warn about weekly goals that need attention."""
    monday = _monday_of(today)
    days_left = 7 - (today - monday).days
    if days_left <= 0:
        return []

    week_beats = [b for b in beats if local_date(b.start, tz) >= monday]
    project_hours: dict[str, float] = defaultdict(float)
    for b in week_beats:
        project_hours[b.project_id] += b.duration.total_seconds() / 3600

    results = []
    for p in projects:
        if p.archived:
            continue
        goal, goal_type = p.effective_goal(monday)
        if not goal or goal_type != "target":
            continue
        tracked = project_hours.get(p.id or "", 0)
        remaining = goal - tracked
        if remaining > 0 and tracked < goal * 0.5 and days_left <= 3:
            results.append(
                InsightCard(
                    id=str(uuid.uuid4()),
                    type="goal_pacing",
                    title=f"{p.name}: {remaining:.1f}h to go",
                    body=(
                        f"You need {remaining:.1f}h more on {p.name} to hit "
                        f"your {goal}h weekly goal — {days_left} "
                        f"day{'s' if days_left > 1 else ''} left."
                    ),
                    data={
                        "project_id": p.id,
                        "remaining": round(remaining, 1),
                        "days_left": days_left,
                    },
                    priority=4,
                )
            )
    return results


CHRONOTYPE_LABELS = {
    "early": (6, 10),
    "midday": (10, 14),
    "afternoon": (14, 18),
    "evening": (18, 22),
    "night": (22, 26),  # wraps: 22-2 AM
}


def detect_chronotype(flow_windows: list[FlowWindow]) -> list[InsightCard]:
    """Detect the user's chronotype from Flow Score × time-of-day data.

    Requires at least 14 days of flow window data.
    """
    if len(flow_windows) < 50:  # ~14 days × ~4 windows/day minimum
        return []

    # Bin flow scores by hour of day
    hour_scores: dict[int, list[float]] = defaultdict(list)
    for w in flow_windows:
        hour = w.window_start.hour
        hour_scores[hour].append(w.flow_score)

    if len(hour_scores) < 4:
        return []

    # Compute hourly medians
    hourly_medians = {h: median(scores) for h, scores in hour_scores.items() if scores}

    # 3-hour rolling average (smoothing)
    smoothed: dict[int, float] = {}
    for h in range(24):
        neighbors = [hourly_medians.get((h + d) % 24, 0) for d in [-1, 0, 1]]
        valid = [v for v in neighbors if v > 0]
        smoothed[h] = sum(valid) / len(valid) if valid else 0

    if not any(v > 0 for v in smoothed.values()):
        return []

    # Find peak: hours where smoothed >= 75th percentile
    all_values = [v for v in smoothed.values() if v > 0]
    if not all_values:
        return []
    p75 = sorted(all_values)[int(len(all_values) * 0.75)]

    peak_hours = sorted(h for h, v in smoothed.items() if v >= p75)
    if not peak_hours:
        return []

    # Label chronotype by where the peak center falls
    peak_center = sum(peak_hours) / len(peak_hours)
    label = "midday"
    for name, (start, end) in CHRONOTYPE_LABELS.items():
        is_night = name == "night" and (peak_center >= 22 or peak_center < 2)
        if start <= peak_center < end or is_night:
            label = name
            break

    peak_start = min(peak_hours)
    peak_end = max(peak_hours) + 1  # inclusive hour

    return [
        InsightCard(
            id=str(uuid.uuid4()),
            type="chronotype",
            title=f"You're a {label} person",
            body=(
                f"Your Flow Score peaks between {peak_start}:00–{peak_end}:00. "
                f"Protect this window for deep work — it's when you're naturally most focused."
            ),
            data={
                "label": label,
                "peak_hours": peak_hours,
                "peak_start": peak_start,
                "peak_end": peak_end,
            },
            priority=4,
        )
    ]
