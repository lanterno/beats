"""Intelligence service — productivity scoring, pattern detection, and smart suggestions."""

import math
import uuid
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from statistics import median

from beats.domain.models import Beat, BiometricDay, FlowWindow, InsightCard, WeeklyDigest
from beats.infrastructure.repositories import (
    BeatRepository,
    DailyNoteRepository,
    IntentionRepository,
    ProjectRepository,
)


def _monday_of(d: date) -> date:
    """Get the Monday of the week containing the given date."""
    return d - timedelta(days=d.weekday())


def _format_hours(minutes: float) -> str:
    h = minutes / 60
    if h >= 1:
        return f"{h:.1f}h"
    return f"{int(minutes)}m"


class IntelligenceService:
    """Service for computing productivity insights and patterns."""

    def __init__(
        self,
        beat_repo: BeatRepository,
        project_repo: ProjectRepository,
        intention_repo: IntentionRepository,
        daily_note_repo: DailyNoteRepository,
    ):
        self.beat_repo = beat_repo
        self.project_repo = project_repo
        self.intention_repo = intention_repo
        self.daily_note_repo = daily_note_repo

    # =========================================================================
    # Productivity Score
    # =========================================================================

    async def compute_productivity_score(self) -> dict:
        """Compute current productivity score (0-100) with component breakdown."""
        today = datetime.now(UTC).date()
        week_start = _monday_of(today)

        # Load data for the last 7 days
        range_start = today - timedelta(days=6)
        beats = await self.beat_repo.list_completed_in_range(range_start, today)
        intentions = await self.intention_repo.list_by_date_range(range_start, today)
        projects = await self.project_repo.list(archived=False)

        # 1. Consistency (0-25): weekdays tracked in last 5 weekdays
        tracked_dates = {b.start.date() for b in beats}
        weekdays = []
        for i in range(7):
            d = today - timedelta(days=i)
            if d.weekday() < 5:  # Mon-Fri
                weekdays.append(d)
            if len(weekdays) == 5:
                break
        weekdays_tracked = sum(1 for d in weekdays if d in tracked_dates)
        consistency = round(weekdays_tracked / max(len(weekdays), 1) * 25)

        # 2. Intention completion (0-25)
        if intentions:
            completed = sum(1 for i in intentions if i.completed)
            intention_score = round(completed / len(intentions) * 25)
        else:
            intention_score = 13  # neutral

        # 3. Goal progress (0-25)
        goal_projects = [p for p in projects if p.weekly_goal]
        if goal_projects:
            # Sum hours per project this week
            week_beats = [b for b in beats if b.start.date() >= week_start]
            project_hours: dict[str, float] = defaultdict(float)
            for b in week_beats:
                project_hours[b.project_id] += b.duration.total_seconds() / 3600

            progresses = []
            for p in goal_projects:
                goal, _ = p.effective_goal(week_start)
                if goal and goal > 0:
                    progress = min(project_hours.get(p.id or "", 0) / goal, 1.0)
                    progresses.append(progress)
            goal_score = round((sum(progresses) / len(progresses) * 25) if progresses else 12.5)
        else:
            goal_score = 13  # neutral

        # 4. Session quality (0-25)
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
                day_beats[b.start.date()].append(b)
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

        total = min(100, consistency + intention_score + goal_score + quality_score)
        return {
            "score": total,
            "components": {
                "consistency": consistency,
                "intentions": intention_score,
                "goals": goal_score,
                "quality": quality_score,
            },
        }

    async def compute_productivity_score_history(self, weeks: int = 8) -> list[dict]:
        """Compute weekly productivity scores for the last N weeks."""
        today = datetime.now(UTC).date()
        current_monday = _monday_of(today)
        history = []

        # Load all data for the full range
        range_start = current_monday - timedelta(weeks=weeks)
        all_beats = await self.beat_repo.list_completed_in_range(range_start, today)
        all_intentions = await self.intention_repo.list_by_date_range(range_start, today)
        projects = await self.project_repo.list(archived=False)
        goal_projects = [p for p in projects if p.weekly_goal]

        for w in range(weeks, 0, -1):
            monday = current_monday - timedelta(weeks=w)
            sunday = monday + timedelta(days=6)

            week_beats = [b for b in all_beats if monday <= b.start.date() <= sunday]
            week_intentions = [i for i in all_intentions if monday <= i.date <= sunday]

            # Simplified score for history
            tracked_dates = {b.start.date() for b in week_beats}
            weekdays = [monday + timedelta(days=d) for d in range(5)]
            consistency = round(sum(1 for d in weekdays if d in tracked_dates) / 5 * 25)

            if week_intentions:
                completed = sum(1 for i in week_intentions if i.completed)
                intent_score = round(completed / len(week_intentions) * 25)
            else:
                intent_score = 13

            project_hours: dict[str, float] = defaultdict(float)
            for b in week_beats:
                project_hours[b.project_id] += b.duration.total_seconds() / 3600
            if goal_projects:
                progresses = []
                for p in goal_projects:
                    goal, _ = p.effective_goal(monday)
                    if goal and goal > 0:
                        progresses.append(min(project_hours.get(p.id or "", 0) / goal, 1.0))
                goal_s = round((sum(progresses) / len(progresses) * 25) if progresses else 12.5)
            else:
                goal_s = 13

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

            score = min(100, consistency + intent_score + goal_s + quality)
            history.append({"week_of": monday.isoformat(), "score": score})

        return history

    # =========================================================================
    # Weekly Digest
    # =========================================================================

    async def generate_weekly_digest(self, week_monday: date) -> WeeklyDigest:
        """Generate a weekly summary digest for the given week."""
        sunday = week_monday + timedelta(days=6)
        prev_monday = week_monday - timedelta(days=7)
        prev_sunday = prev_monday + timedelta(days=6)

        beats = await self.beat_repo.list_completed_in_range(week_monday, sunday)
        prev_beats = await self.beat_repo.list_completed_in_range(prev_monday, prev_sunday)
        projects = await self.project_repo.list(archived=False)
        project_map = {p.id: p for p in projects}

        # Totals
        total_minutes = sum(b.duration.total_seconds() / 60 for b in beats)
        total_hours = total_minutes / 60
        session_count = len(beats)
        active_dates = {b.start.date() for b in beats}
        active_days = len(active_dates)

        # Project breakdown
        proj_minutes: dict[str, float] = defaultdict(float)
        for b in beats:
            proj_minutes[b.project_id] += b.duration.total_seconds() / 60
        breakdown = []
        for pid, mins in sorted(proj_minutes.items(), key=lambda x: -x[1]):
            p = project_map.get(pid)
            breakdown.append(
                {
                    "project_id": pid,
                    "name": p.name if p else "Unknown",
                    "hours": round(mins / 60, 2),
                }
            )

        # Top project
        top = breakdown[0] if breakdown else None

        # Longest day
        day_minutes: dict[date, float] = defaultdict(float)
        for b in beats:
            day_minutes[b.start.date()] += b.duration.total_seconds() / 60
        if day_minutes:
            longest_date = max(day_minutes, key=day_minutes.get)  # type: ignore[arg-type]
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

        observation = self._generate_observation(
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
        score = min(100, consistency + 13 + 13 + quality)  # neutral for intentions/goals

        return WeeklyDigest(
            week_of=week_monday,
            total_hours=round(total_hours, 2),
            session_count=session_count,
            active_days=active_days,
            top_project_id=top["project_id"] if top else None,
            top_project_name=top["name"] if top else None,
            top_project_hours=top["hours"] if top else 0,
            vs_last_week_pct=vs_last_week_pct,
            longest_day=longest_day,
            longest_day_hours=round(longest_day_hours, 2),
            best_streak=streak,
            observation=observation,
            project_breakdown=breakdown,
            productivity_score=score,
        )

    def _generate_observation(
        self,
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
            longest_date = max(day_minutes, key=day_minutes.get)  # type: ignore[arg-type]
            day_name = longest_date.strftime("%A")
            hrs = day_minutes[longest_date] / 60
            return f"Your most productive day was {day_name} with {hrs:.1f}h tracked."

        # 4. Fallback
        return f"You tracked {total_hours:.1f}h across {session_count} sessions this week."

    # =========================================================================
    # Pattern Detection
    # =========================================================================

    async def detect_patterns(self) -> list[InsightCard]:
        """Detect non-obvious patterns in the user's data."""
        today = datetime.now(UTC).date()
        insights: list[InsightCard] = []

        # Load data
        range_start = today - timedelta(days=60)
        beats = await self.beat_repo.list_completed_in_range(range_start, today)
        projects = await self.project_repo.list(archived=False)
        project_map = {p.id: p for p in projects}
        notes = await self.daily_note_repo.list_by_date_range(range_start, today)
        intentions = await self.intention_repo.list_by_date_range(range_start, today)

        insights.extend(self._detect_day_pattern(beats, today))
        insights.extend(self._detect_peak_hours(beats))
        insights.extend(self._detect_stale_projects(beats, projects, today))
        insights.extend(self._detect_mood_correlation(beats, notes))
        insights.extend(self._detect_session_trend(beats, today))
        insights.extend(self._detect_estimation_bias(beats, intentions, project_map))
        insights.extend(self._detect_goal_pacing(beats, projects, today))

        insights.sort(key=lambda x: -x.priority)
        return insights

    def _detect_day_pattern(self, beats: list[Beat], today: date) -> list[InsightCard]:
        """Check if any day of week is significantly more productive."""
        # Aggregate hours per weekday over the last 8 weeks
        day_hours: dict[int, list[float]] = defaultdict(list)
        for w in range(8):
            monday = _monday_of(today) - timedelta(weeks=w)
            for dow in range(7):
                d = monday + timedelta(days=dow)
                mins = sum(b.duration.total_seconds() / 60 for b in beats if b.start.date() == d)
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

    def _detect_peak_hours(self, beats: list[Beat]) -> list[InsightCard]:
        """Find peak productivity time blocks."""
        blocks: dict[int, float] = defaultdict(float)  # 2-hour blocks: 0=0-2, 1=2-4, etc.
        for b in beats:
            block = b.start.hour // 2
            blocks[block] += b.duration.total_seconds() / 60

        if len(blocks) < 3:
            return []

        values = list(blocks.values())
        med = median(values)
        if med < 1:
            return []

        peak_block = max(blocks, key=blocks.get)  # type: ignore[arg-type]
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

    def _detect_stale_projects(
        self, beats: list[Beat], projects: list, today: date
    ) -> list[InsightCard]:
        """Alert on projects with goals but no recent activity."""
        last_beat: dict[str, date] = {}
        for b in beats:
            pid = b.project_id
            d = b.start.date()
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

    def _detect_mood_correlation(self, beats: list[Beat], notes: list) -> list[InsightCard]:
        """Correlate mood scores with daily tracked hours."""
        mood_data = [n for n in notes if n.mood is not None]
        if len(mood_data) < 10:
            return []

        date_hours: dict[date, float] = defaultdict(float)
        for b in beats:
            date_hours[b.start.date()] += b.duration.total_seconds() / 3600

        pairs = []
        for n in mood_data:
            hrs = date_hours.get(n.date, 0)
            pairs.append((n.mood, hrs))

        if len(pairs) < 10:
            return []

        # Pearson correlation
        n_pairs = len(pairs)
        sum_x = sum(p[0] for p in pairs)
        sum_y = sum(p[1] for p in pairs)
        sum_xy = sum(p[0] * p[1] for p in pairs)
        sum_x2 = sum(p[0] ** 2 for p in pairs)
        sum_y2 = sum(p[1] ** 2 for p in pairs)
        denom = math.sqrt((n_pairs * sum_x2 - sum_x**2) * (n_pairs * sum_y2 - sum_y**2))
        if denom == 0:
            return []
        r = (n_pairs * sum_xy - sum_x * sum_y) / denom

        if abs(r) < 0.3:
            return []

        # Compute averages for high vs low mood
        high = [h for m, h in pairs if m >= 4]
        low = [h for m, h in pairs if m <= 2]
        high_avg = sum(high) / len(high) if high else 0
        low_avg = sum(low) / len(low) if low else 0

        if r > 0:
            body = (
                f"On days you rate mood 4+, you average {high_avg:.1f}h tracked "
                f"vs {low_avg:.1f}h on mood 2 or below. More work, better mood — or vice versa."
            )
        else:
            body = (
                f"On lighter days ({low_avg:.1f}h), your mood tends higher. "
                f"Heavy days ({high_avg:.1f}h) correlate with lower mood scores."
            )

        return [
            InsightCard(
                id=str(uuid.uuid4()),
                type="mood_correlation",
                title="Mood and productivity are linked",
                body=body,
                data={
                    "r": round(r, 2),
                    "high_mood_avg_hours": round(high_avg, 1),
                    "low_mood_avg_hours": round(low_avg, 1),
                },
                priority=2,
            )
        ]

    def _detect_session_trend(self, beats: list[Beat], today: date) -> list[InsightCard]:
        """Compare this week's avg session length to 4-week average."""
        this_monday = _monday_of(today)
        four_weeks_ago = this_monday - timedelta(weeks=4)

        this_week = [b for b in beats if b.start.date() >= this_monday]
        prev_weeks = [b for b in beats if four_weeks_ago <= b.start.date() < this_monday]

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

    def _detect_estimation_bias(
        self, beats: list[Beat], intentions: list, project_map: dict
    ) -> list[InsightCard]:
        """Check if planned vs actual shows consistent bias."""
        # Group intentions and beats by (project, date)
        planned: dict[tuple[str, date], int] = {}
        for i in intentions:
            key = (i.project_id, i.date)
            planned[key] = planned.get(key, 0) + i.planned_minutes

        actual: dict[tuple[str, date], float] = defaultdict(float)
        for b in beats:
            key = (b.project_id, b.start.date())
            if key in planned:
                actual[key] += b.duration.total_seconds() / 60

        # Per-project accuracy
        project_ratios: dict[str, list[float]] = defaultdict(list)
        for key, plan_min in planned.items():
            if plan_min > 0:
                act_min = actual.get(key, 0)
                project_ratios[key[0]].append(act_min / plan_min)

        results = []
        for pid, ratios in project_ratios.items():
            if len(ratios) < 3:
                continue
            avg_ratio = sum(ratios) / len(ratios)
            if avg_ratio < 0.8 or avg_ratio > 1.2:
                p = project_map.get(pid)
                name = p.name if p else "a project"
                if avg_ratio > 1.2:
                    pct = round((avg_ratio - 1) * 100)
                    results.append(
                        InsightCard(
                            id=str(uuid.uuid4()),
                            type="estimation_accuracy",
                            title=f"You underestimate {name}",
                            body=f"You consistently spend {pct}% more time on {name} than planned. "
                            f"Consider budgeting more time.",
                            data={"project_id": pid, "avg_ratio": round(avg_ratio, 2)},
                            priority=3,
                        )
                    )
                else:
                    pct = round((1 - avg_ratio) * 100)
                    results.append(
                        InsightCard(
                            id=str(uuid.uuid4()),
                            type="estimation_accuracy",
                            title=f"You overestimate {name}",
                            body=f"You typically use only {100 - pct}% of planned time on {name}.",
                            data={"project_id": pid, "avg_ratio": round(avg_ratio, 2)},
                            priority=2,
                        )
                    )
        return results

    def _detect_goal_pacing(
        self, beats: list[Beat], projects: list, today: date
    ) -> list[InsightCard]:
        """Warn about weekly goals that need attention."""
        monday = _monday_of(today)
        days_left = 7 - (today - monday).days
        if days_left <= 0:
            return []

        week_beats = [b for b in beats if b.start.date() >= monday]
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

    # =========================================================================
    # Smart Daily Plan Suggestions
    # =========================================================================

    async def suggest_daily_plan(self, target_date: date) -> list[dict]:
        """Suggest up to 3 projects and durations for today's intentions."""
        dow = target_date.weekday()
        monday = _monday_of(target_date)

        # Load 8 weeks of history for this day of week
        range_start = target_date - timedelta(weeks=8)
        beats = await self.beat_repo.list_completed_in_range(range_start, target_date)
        projects = await self.project_repo.list(archived=False)
        project_map = {p.id: p for p in projects}

        # Day-of-week averages per project
        dow_minutes: dict[str, list[float]] = defaultdict(list)
        for w in range(1, 9):
            d = target_date - timedelta(weeks=w)
            if d.weekday() != dow:
                continue
            project_day_mins: dict[str, float] = defaultdict(float)
            for b in beats:
                if b.start.date() == d:
                    project_day_mins[b.project_id] += b.duration.total_seconds() / 60
            for pid in project_map:
                dow_minutes[pid].append(project_day_mins.get(pid, 0))

        day_avgs = {
            pid: sum(mins) / len(mins)
            for pid, mins in dow_minutes.items()
            if mins and sum(mins) > 0
        }

        # Weekly goal remaining
        week_beats = [b for b in beats if b.start.date() >= monday]
        week_hours: dict[str, float] = defaultdict(float)
        for b in week_beats:
            week_hours[b.project_id] += b.duration.total_seconds() / 3600

        # Recency (worked yesterday?)
        yesterday = target_date - timedelta(days=1)
        yesterday_projects = {b.project_id for b in beats if b.start.date() == yesterday}

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

    # =========================================================================
    # Focus Quality Score
    # =========================================================================

    async def compute_focus_scores(self, target_date: date) -> list[dict]:
        """Compute focus quality scores for all sessions on a given date."""
        beats = await self.beat_repo.list_completed_in_range(target_date, target_date)
        if not beats:
            return []

        # Compute user's peak hours from recent data
        recent_start = target_date - timedelta(days=30)
        recent_beats = await self.beat_repo.list_completed_in_range(recent_start, target_date)
        peak_block = self._find_peak_block(recent_beats)

        sorted_beats = sorted(beats, key=lambda b: b.start)
        results = []
        for i, b in enumerate(sorted_beats):
            score = self._focus_score_for_beat(b, sorted_beats, i, peak_block)
            results.append(
                {
                    "beat_id": b.id,
                    "score": score["score"],
                    "components": score["components"],
                }
            )
        return results

    def _find_peak_block(self, beats: list[Beat]) -> int:
        """Find the 2-hour block with the most total minutes."""
        blocks: dict[int, float] = defaultdict(float)
        for b in beats:
            block = b.start.hour // 2
            blocks[block] += b.duration.total_seconds() / 60
        if not blocks:
            return 4  # default: 8-10 AM
        return max(blocks, key=blocks.get)  # type: ignore[arg-type]

    def _focus_score_for_beat(
        self, beat: Beat, day_beats: list[Beat], index: int, peak_block: int
    ) -> dict:
        """Compute focus score for a single beat."""
        dur_min = beat.duration.total_seconds() / 60

        # Length component (0-40)
        if dur_min < 10:
            length = 5
        elif dur_min < 25:
            length = 15
        elif dur_min < 45:
            length = 25
        elif dur_min < 90:
            length = 35
        else:
            length = 40

        # Peak hours component (0-30)
        beat_block = beat.start.hour // 2
        if beat_block == peak_block:
            peak = 30
        elif abs(beat_block - peak_block) == 1:
            peak = 20
        else:
            peak = 10

        # Fragmentation penalty (start at 30, subtract for close gaps)
        frag = 30
        if index > 0:
            prev = day_beats[index - 1]
            if prev.end:
                gap = (beat.start - prev.end).total_seconds() / 60
                if 0 < gap < 5:
                    frag -= 15
        if index < len(day_beats) - 1:
            nxt = day_beats[index + 1]
            if beat.end:
                gap = (nxt.start - beat.end).total_seconds() / 60
                if 0 < gap < 5:
                    frag -= 15

        total = max(0, min(100, length + peak + frag))
        return {
            "score": total,
            "components": {"length": length, "peak_hours": peak, "fragmentation": frag},
        }

    # =========================================================================
    # Mood-Productivity Correlation
    # =========================================================================

    async def get_mood_correlation(self) -> dict:
        """Compute mood trend and correlation with daily hours."""
        today = datetime.now(UTC).date()
        range_start = today - timedelta(days=90)
        notes = await self.daily_note_repo.list_by_date_range(range_start, today)
        beats = await self.beat_repo.list_completed_in_range(range_start, today)

        mood_notes = sorted([n for n in notes if n.mood is not None], key=lambda n: n.date)

        date_hours: dict[date, float] = defaultdict(float)
        date_sessions: dict[date, int] = defaultdict(int)
        for b in beats:
            d = b.start.date()
            date_hours[d] += b.duration.total_seconds() / 3600
            date_sessions[d] += 1

        # Mood trend (7-day rolling average)
        mood_trend = []
        for i, n in enumerate(mood_notes):
            window = mood_notes[max(0, i - 6) : i + 1]
            avg = sum(w.mood for w in window if w.mood) / len(window)
            mood_trend.append({"date": n.date.isoformat(), "mood_avg": round(avg, 2)})

        # Correlation
        pairs = [(n.mood, date_hours.get(n.date, 0)) for n in mood_notes]

        high = [h for m, h in pairs if m and m >= 4]
        low = [h for m, h in pairs if m and m <= 2]

        high_avg_hours = round(sum(high) / len(high), 1) if high else 0
        low_avg_hours = round(sum(low) / len(low), 1) if low else 0

        high_sessions = [date_sessions.get(n.date, 0) for n in mood_notes if n.mood and n.mood >= 4]
        low_sessions = [date_sessions.get(n.date, 0) for n in mood_notes if n.mood and n.mood <= 2]

        # Pearson r
        r = 0.0
        if len(pairs) >= 10:
            n_p = len(pairs)
            sx = sum(p[0] for p in pairs if p[0])
            sy = sum(p[1] for p in pairs)
            sxy = sum(p[0] * p[1] for p in pairs if p[0])
            sx2 = sum(p[0] ** 2 for p in pairs if p[0])
            sy2 = sum(p[1] ** 2 for p in pairs)
            denom = math.sqrt((n_p * sx2 - sx**2) * (n_p * sy2 - sy**2))
            if denom > 0:
                r = (n_p * sxy - sx * sy) / denom

        description = "positive" if r > 0.3 else "negative" if r < -0.3 else "neutral"

        return {
            "mood_trend": mood_trend,
            "correlation": {"r": round(r, 2), "description": description},
            "high_mood_avg_hours": high_avg_hours,
            "low_mood_avg_hours": low_avg_hours,
            "high_mood_avg_sessions": (
                round(sum(high_sessions) / len(high_sessions), 1) if high_sessions else 0
            ),
            "low_mood_avg_sessions": (
                round(sum(low_sessions) / len(low_sessions), 1) if low_sessions else 0
            ),
        }

    # =========================================================================
    # Estimation Accuracy
    # =========================================================================

    async def get_estimation_accuracy(self) -> list[dict]:
        """Compute per-project estimation accuracy from intentions vs actual time."""
        today = datetime.now(UTC).date()
        range_start = today - timedelta(days=90)
        intentions = await self.intention_repo.list_by_date_range(range_start, today)
        beats = await self.beat_repo.list_completed_in_range(range_start, today)
        projects = await self.project_repo.list(archived=False)
        project_map = {p.id: p for p in projects}

        # Planned per (project, date)
        planned: dict[tuple[str, date], int] = defaultdict(int)
        for i in intentions:
            planned[(i.project_id, i.date)] += i.planned_minutes

        # Actual per (project, date)
        actual: dict[tuple[str, date], float] = defaultdict(float)
        for b in beats:
            key = (b.project_id, b.start.date())
            if key in planned:
                actual[key] += b.duration.total_seconds() / 60

        # Per-project aggregation
        project_data: dict[str, dict] = defaultdict(lambda: {"planned": [], "actual": []})
        for key, plan_min in planned.items():
            pid = key[0]
            act_min = actual.get(key, 0)
            project_data[pid]["planned"].append(plan_min)
            project_data[pid]["actual"].append(act_min)

        results = []
        for pid, data in project_data.items():
            if len(data["planned"]) < 2:
                continue
            avg_planned = sum(data["planned"]) / len(data["planned"])
            avg_actual = sum(data["actual"]) / len(data["actual"])
            accuracy = round(avg_actual / avg_planned * 100, 1) if avg_planned > 0 else 0
            if accuracy > 110:
                bias = "underestimate"
            elif accuracy < 90:
                bias = "overestimate"
            else:
                bias = "accurate"
            p = project_map.get(pid)
            results.append(
                {
                    "project_id": pid,
                    "project_name": p.name if p else "Unknown",
                    "avg_planned_min": round(avg_planned, 1),
                    "avg_actual_min": round(avg_actual, 1),
                    "accuracy_pct": accuracy,
                    "bias": bias,
                }
            )

        results.sort(key=lambda x: abs(x["accuracy_pct"] - 100), reverse=True)
        return results

    # =========================================================================
    # Project Health
    # =========================================================================

    async def get_project_health(self) -> list[dict]:
        """Compute health metrics for each active project."""
        today = datetime.now(UTC).date()
        range_start = today - timedelta(weeks=4)
        beats = await self.beat_repo.list_completed_in_range(range_start, today)
        projects = await self.project_repo.list(archived=False)

        # Last beat date per project
        last_beat: dict[str, date] = {}
        for b in beats:
            pid = b.project_id
            d = b.start.date()
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
                week_b = [b for b in proj_beats if monday <= b.start.date() <= sunday]
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
                    weekly_hours[i] < weekly_hours[i - 1]
                    for i in range(1, min(3, len(weekly_hours)))
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


# =========================================================================
# Chronotype Detection (Stage 4)
# =========================================================================

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


# =========================================================================
# Biometric × Mood Correlation (Stage 4)
# =========================================================================


def _pearson_r(pairs: list[tuple[float, float]]) -> float:
    """Compute Pearson correlation coefficient for a list of (x, y) pairs."""
    n = len(pairs)
    if n < 7:
        return 0.0
    sx = sum(p[0] for p in pairs)
    sy = sum(p[1] for p in pairs)
    sxy = sum(p[0] * p[1] for p in pairs)
    sx2 = sum(p[0] ** 2 for p in pairs)
    sy2 = sum(p[1] ** 2 for p in pairs)
    denom = math.sqrt((n * sx2 - sx**2) * (n * sy2 - sy**2))
    if denom == 0:
        return 0.0
    return (n * sxy - sx * sy) / denom


def detect_biometric_correlations(
    bio_days: list[BiometricDay], notes: list,
) -> list[InsightCard]:
    """Detect correlations between biometric data and mood scores."""
    insights: list[InsightCard] = []
    mood_by_date = {n.date: n.mood for n in notes if n.mood is not None}

    # HRV × mood
    hrv_mood_pairs = [
        (b.hrv_ms, float(mood_by_date[b.date]))
        for b in bio_days
        if b.hrv_ms is not None and b.date in mood_by_date
    ]
    r = _pearson_r(hrv_mood_pairs)
    if abs(r) >= 0.4:
        direction = "higher" if r > 0 else "lower"
        insights.append(InsightCard(
            id=str(uuid.uuid4()),
            type="hrv_mood_correlation",
            title="HRV and mood are linked",
            body=(
                f"Days with {direction} HRV tend to come with better mood scores (r={r:.2f}). "
                f"Your heart rate variability may be a useful recovery signal."
            ),
            data={"r": round(r, 2), "n": len(hrv_mood_pairs)},
            priority=3,
        ))

    # Sleep × mood
    sleep_mood_pairs = [
        (float(b.sleep_minutes), float(mood_by_date[b.date]))
        for b in bio_days
        if b.sleep_minutes is not None and b.date in mood_by_date
    ]
    r = _pearson_r(sleep_mood_pairs)
    if abs(r) >= 0.4:
        direction = "more" if r > 0 else "less"
        insights.append(InsightCard(
            id=str(uuid.uuid4()),
            type="sleep_mood_correlation",
            title="Sleep and mood are connected",
            body=(
                f"On days after {direction} sleep, your mood tends higher (r={r:.2f}). "
                f"Prioritizing sleep may directly improve how you feel."
            ),
            data={"r": round(r, 2), "n": len(sleep_mood_pairs)},
            priority=3,
        ))

    return insights
