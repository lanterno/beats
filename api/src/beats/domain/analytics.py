"""Analytics service — cross-project insights and aggregations."""

from collections import defaultdict
from datetime import UTC, date, datetime, timedelta

from beats.infrastructure.repositories import BeatRepository


class AnalyticsService:
    """Service for computing analytics across all projects."""

    def __init__(self, beat_repo: BeatRepository):
        self.beat_repo = beat_repo

    async def get_heatmap(
        self, year: int, project_id: str | None = None, tag: str | None = None
    ) -> list[dict]:
        """Get daily activity heatmap for a given year.

        Returns a list of dicts with date, total_minutes, session_count, project_count
        for each day that has at least one session.
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
            beat_date = beat.start.date()
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
        self, period: str = "all", project_id: str | None = None, tag: str | None = None
    ) -> list[dict]:
        """Get average activity by time of day in half-hour slots.

        Args:
            period: "week" (current week), "month" (current month), or "all"
            project_id: Optional project filter.
            tag: Optional tag filter.

        Returns list of 48 slots with average minutes per slot.
        """
        beats = await self.beat_repo.list_all_completed()
        if project_id:
            beats = [b for b in beats if b.project_id == project_id]
        if tag:
            beats = [b for b in beats if tag in b.tags]

        today = date.today()
        if period == "week":
            start_of_week = today - timedelta(days=today.weekday())
            filtered = [b for b in beats if b.start.date() >= start_of_week]
            num_days = (today - start_of_week).days + 1
        elif period == "month":
            start_of_month = today.replace(day=1)
            filtered = [b for b in beats if b.start.date() >= start_of_month]
            num_days = (today - start_of_month).days + 1
        else:
            filtered = beats
            if filtered:
                earliest = min(b.start.date() for b in filtered)
                num_days = (today - earliest).days + 1
            else:
                num_days = 1

        # Distribute each session's minutes into half-hour slots
        slots = [0.0] * 48
        for beat in filtered:
            start = beat.start.replace(tzinfo=None) if beat.start.tzinfo else beat.start
            end = beat.end.replace(tzinfo=None) if beat.end and beat.end.tzinfo else beat.end
            if not end:
                continue
            self._distribute_to_slots(slots, start, end)

        # Average by number of days in the period
        num_days = max(num_days, 1)
        return [
            {"slot": i, "minutes": round(slots[i] / num_days, 1)}
            for i in range(48)
        ]

    @staticmethod
    def _distribute_to_slots(slots: list[float], start: datetime, end: datetime) -> None:
        """Distribute a session's minutes into half-hour slots (0-47)."""
        # Clamp to same day for simplicity (sessions spanning midnight split at midnight)
        cursor = start
        while cursor < end:
            slot_index = cursor.hour * 2 + (1 if cursor.minute >= 30 else 0)
            # End of this slot
            slot_end_minute = 30 if cursor.minute < 30 else 60
            slot_boundary = cursor.replace(minute=slot_end_minute % 60, second=0, microsecond=0)
            if slot_end_minute == 60:
                slot_boundary = slot_boundary.replace(hour=cursor.hour + 1, minute=0)
                if slot_boundary.hour == 0 and cursor.hour == 23:
                    # Crossed midnight, stop here
                    slot_boundary = cursor.replace(hour=23, minute=59, second=59)

            chunk_end = min(end, slot_boundary)
            minutes = (chunk_end - cursor).total_seconds() / 60
            if 0 <= slot_index < 48:
                slots[slot_index] += minutes
            cursor = chunk_end
            if cursor == end:
                break
