"""Analytics service — cross-project insights and aggregations."""

from collections import defaultdict
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from beats.domain.utils import local_date, local_dt
from beats.infrastructure.repositories import BeatRepository

UTC_TZ = ZoneInfo("UTC")


class AnalyticsService:
    """Service for computing analytics across all projects."""

    def __init__(self, beat_repo: BeatRepository):
        self.beat_repo = beat_repo

    async def get_heatmap(
        self,
        year: int,
        project_id: str | None = None,
        tag: str | None = None,
        tz: ZoneInfo = UTC_TZ,
    ) -> list[dict]:
        """Get daily activity heatmap for a given year.

        Returns a list of dicts with date, total_minutes, session_count, project_count
        for each day that has at least one session. Days are bucketed by the
        session's local calendar date in ``tz``.
        """
        beats = await self.beat_repo.list_all_completed()

        day_data: dict[date, dict] = defaultdict(
            lambda: {"total_seconds": 0, "session_count": 0, "projects": set()}
        )

        for beat in beats:
            if project_id and beat.project_id != project_id:
                continue
            if tag and tag not in beat.tags:
                continue
            beat_date = local_date(beat.start, tz)
            if beat_date.year != year:
                continue
            entry = day_data[beat_date]
            entry["total_seconds"] += beat.duration.total_seconds()
            entry["session_count"] += 1
            entry["projects"].add(beat.project_id)

        return [
            {
                "date": str(d),
                "total_minutes": round(data["total_seconds"] / 60),
                "session_count": data["session_count"],
                "project_count": len(data["projects"]),
            }
            for d, data in sorted(day_data.items())
        ]

    async def get_daily_rhythm(
        self,
        period: str = "all",
        project_id: str | None = None,
        tag: str | None = None,
        tz: ZoneInfo = UTC_TZ,
    ) -> list[dict]:
        """Get average activity by time of day in half-hour slots.

        Args:
            period: "week" (current week), "month" (current month), or "all"
            project_id: Optional project filter.
            tag: Optional tag filter.
            tz: Timezone for day-bucketing and slot math (defaults to UTC).

        Returns list of 48 slots with average minutes per slot.
        """
        beats = await self.beat_repo.list_all_completed()
        if project_id:
            beats = [b for b in beats if b.project_id == project_id]
        if tag:
            beats = [b for b in beats if tag in b.tags]

        today = datetime.now(tz).date()
        if period == "week":
            start_of_week = today - timedelta(days=today.weekday())
            filtered = [b for b in beats if local_date(b.start, tz) >= start_of_week]
            num_days = (today - start_of_week).days + 1
        elif period == "month":
            start_of_month = today.replace(day=1)
            filtered = [b for b in beats if local_date(b.start, tz) >= start_of_month]
            num_days = (today - start_of_month).days + 1
        else:
            filtered = beats
            if filtered:
                earliest = min(local_date(b.start, tz) for b in filtered)
                num_days = (today - earliest).days + 1
            else:
                num_days = 1

        # Distribute each session's minutes into half-hour slots, using the
        # local wall clock so slot indices and cross-midnight splits are correct.
        slots = [0.0] * 48
        for beat in filtered:
            if not beat.end:
                continue
            start = local_dt(beat.start, tz).replace(tzinfo=None)
            end = local_dt(beat.end, tz).replace(tzinfo=None)
            self._distribute_to_slots(slots, start, end)

        # Average by number of days in the period
        num_days = max(num_days, 1)
        return [{"slot": i, "minutes": round(slots[i] / num_days, 1)} for i in range(48)]

    async def get_untracked_gaps(
        self, target_date: date, min_gap_minutes: int = 15, tz: ZoneInfo = UTC_TZ
    ) -> list[dict]:
        """Find gaps between sessions on a given local date.

        Returns list of dicts with start, end, duration_minutes for gaps
        longer than min_gap_minutes. Sessions are scoped to ``target_date``
        in the caller's local timezone.
        """
        # Widen the repo query by a day on each side so sessions whose UTC
        # date differs from their local date are still considered, then filter
        # precisely by local date below.
        beats = await self.beat_repo.list_completed_in_range(
            target_date - timedelta(days=1), target_date + timedelta(days=1)
        )
        beats = [b for b in beats if local_date(b.start, tz) == target_date]
        if not beats:
            return []

        sorted_beats = sorted(beats, key=lambda b: b.start)
        gaps = []
        for i in range(len(sorted_beats) - 1):
            current_end = sorted_beats[i].end
            next_start = sorted_beats[i + 1].start
            if current_end and next_start > current_end:
                gap_seconds = (next_start - current_end).total_seconds()
                gap_minutes = round(gap_seconds / 60)
                if gap_minutes >= min_gap_minutes:
                    gaps.append(
                        {
                            "start": current_end.isoformat(),
                            "end": next_start.isoformat(),
                            "duration_minutes": gap_minutes,
                        }
                    )
        return gaps

    @staticmethod
    def _distribute_to_slots(slots: list[float], start: datetime, end: datetime) -> None:
        """Distribute a session's minutes into half-hour slots (0-47).

        Slots are indexed by time-of-day, so a session that crosses midnight
        has its after-midnight minutes attributed to the next day's slots
        (which wrap back to slot 0). The minutes are never dropped.
        """
        cursor = start
        while cursor < end:
            slot_index = (cursor.hour * 2 + (1 if cursor.minute >= 30 else 0)) % 48
            # Next half-hour boundary
            next_min = 30 if cursor.minute < 30 else 0
            next_half = cursor.replace(minute=next_min, second=0, microsecond=0)
            if cursor.minute >= 30:
                next_half += timedelta(hours=1)

            chunk_end = min(end, next_half)
            minutes = (chunk_end - cursor).total_seconds() / 60
            slots[slot_index] += minutes
            cursor = chunk_end
