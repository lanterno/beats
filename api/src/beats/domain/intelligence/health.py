"""Project health — which projects are thriving, drifting, or stalled."""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from beats.domain.ports import ProjectLister, RangeBeatReader
from beats.domain.utils import local_date

from ._support import UTC_TZ, _monday_of


async def get_project_health(
    beat_repo: RangeBeatReader, project_repo: ProjectLister, tz: ZoneInfo = UTC_TZ
) -> list[dict]:
    """Compute health metrics for each active project."""
    today = datetime.now(tz).date()
    range_start = today - timedelta(weeks=4)
    beats = await beat_repo.list_completed_in_range(range_start, today)
    projects = await project_repo.list(archived=False)

    # Last beat date per project
    last_beat: dict[str, date] = {}
    for b in beats:
        pid = b.project_id
        d = local_date(b.start, tz)
        if pid not in last_beat or d > last_beat[pid]:
            last_beat[pid] = d

    # Weekly hours and session lengths per project (last 4 weeks)
    results = []
    for p in projects:
        pid = p.id or ""
        proj_beats = [b for b in beats if b.project_id == pid]

        # Weekly goal trend (4 weeks)
        weekly_hours = []
        weekly_avg_session = []
        for w in range(4, 0, -1):
            monday = _monday_of(today) - timedelta(weeks=w)
            sunday = monday + timedelta(days=6)
            week_b = [b for b in proj_beats if monday <= local_date(b.start, tz) <= sunday]
            total = sum(b.duration.total_seconds() / 3600 for b in week_b)
            weekly_hours.append(round(total, 2))
            if week_b:
                avg_len = sum(b.duration.total_seconds() / 60 for b in week_b) / len(week_b)
                weekly_avg_session.append(round(avg_len, 1))
            else:
                weekly_avg_session.append(0)

        last = last_beat.get(pid)
        days_since = (today - last).days if last else None

        # Alert logic
        alert = None
        goal, _ = p.effective_goal(_monday_of(today))
        if goal and days_since is not None and days_since >= 14:
            alert = f"No activity in {days_since} days despite {goal}h weekly goal"
        elif goal and len(weekly_hours) >= 3:
            trending_down = all(
                weekly_hours[i] < weekly_hours[i - 1] for i in range(1, min(3, len(weekly_hours)))
            )
            if trending_down:
                alert = "Goal completion trending down for 3 consecutive weeks"

        results.append(
            {
                "project_id": pid,
                "project_name": p.name,
                "days_since_last": days_since,
                "weekly_goal_trend": weekly_hours,
                "avg_session_length_trend": weekly_avg_session,
                "alert": alert,
            }
        )

    # Sort: projects with alerts first
    results.sort(key=lambda x: (x["alert"] is None, x["project_name"]))
    return results
