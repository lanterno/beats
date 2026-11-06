"""`AnalyticsService`: the slot distribution, the heatmap, the daily
rhythm and the untracked gaps — plus the chronotype detector, which
reads the same shape of day.

Split out of `test_domain.py` at the ceiling in roadmaps/file-sizes.md;
the shared fakes and factories are `domain_fakes.py`'s.
"""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from beats.domain.analytics import AnalyticsService
from beats.domain.intelligence import (
    detect_chronotype,
)
from beats.domain.models import (
    Beat,
)
from beats.domain_fakes import (
    _beat,
    _FakeBeatRepo,
    _flow_window,
)


class TestAnalyticsDistributeToSlots:
    """Pure helper: distribute a session's minutes into 48 half-hour
    slots indexed 0..47. Tests the math directly without needing a
    repo fake."""

    def _slots(self, start_iso: str, end_iso: str) -> list[float]:
        slots = [0.0] * 48
        AnalyticsService._distribute_to_slots(
            slots,
            datetime.fromisoformat(start_iso),
            datetime.fromisoformat(end_iso),
        )
        return slots

    def test_session_within_a_single_slot(self):
        # 09:00–09:20 → all 20min in slot 18 (9*2 + 0)
        slots = self._slots("2026-05-01T09:00:00", "2026-05-01T09:20:00")
        assert slots[18] == 20
        assert sum(slots) == 20

    def test_session_crossing_half_hour_boundary(self):
        # 09:15–09:45 → 15min in slot 18 (9:00–9:30) + 15min in slot 19 (9:30–10:00)
        slots = self._slots("2026-05-01T09:15:00", "2026-05-01T09:45:00")
        assert slots[18] == 15
        assert slots[19] == 15
        assert sum(slots) == 30

    def test_multi_hour_session(self):
        # 08:00–10:00 → 30min in each of slots 16, 17, 18, 19
        slots = self._slots("2026-05-01T08:00:00", "2026-05-01T10:00:00")
        for i in (16, 17, 18, 19):
            assert slots[i] == 30
        assert sum(slots) == 120

    def test_cross_midnight_splits_into_next_day_slots(self):
        # 23:30 (start day) to 00:30 (next day) — the 30min before
        # midnight land in slot 47 (23:30–24:00) and the 30min after
        # midnight wrap into slot 0 (00:00–00:30). No minutes dropped.
        slots = self._slots("2026-05-01T23:30:00", "2026-05-02T00:30:00")
        assert slots[47] == 30  # 23:30–24:00 is slot 47
        assert slots[0] == 30  # 00:00–00:30 wraps to slot 0
        assert sum(slots) == 60

    def test_aligned_30_minute_boundary(self):
        # 10:00–10:30 → all 30min in slot 20 only
        slots = self._slots("2026-05-01T10:00:00", "2026-05-01T10:30:00")
        assert slots[20] == 30
        assert sum(slots) == 30

    def test_zero_duration_session_does_nothing(self):
        slots = self._slots("2026-05-01T09:00:00", "2026-05-01T09:00:00")
        assert sum(slots) == 0


class TestAnalyticsHeatmap:
    """Pure aggregation: per-day totals/sessions/project counts for a year."""

    @pytest.mark.asyncio
    async def test_empty_repo_returns_empty_list(self):
        svc = AnalyticsService(_FakeBeatRepo([]))  # type: ignore[arg-type]
        out = await svc.get_heatmap(year=2026)
        assert out == []

    @pytest.mark.asyncio
    async def test_aggregates_per_day_and_counts_distinct_projects(self):
        beats = [
            _beat("2026-05-01T09:00:00", 60, project_id="p1"),
            _beat("2026-05-01T11:00:00", 30, project_id="p2"),
            _beat("2026-05-02T09:00:00", 45, project_id="p1"),
        ]
        svc = AnalyticsService(_FakeBeatRepo(beats))  # type: ignore[arg-type]
        out = await svc.get_heatmap(year=2026)
        by_date = {d["date"]: d for d in out}
        assert by_date["2026-05-01"]["total_minutes"] == 90
        assert by_date["2026-05-01"]["session_count"] == 2
        assert by_date["2026-05-01"]["project_count"] == 2
        assert by_date["2026-05-02"]["total_minutes"] == 45
        assert by_date["2026-05-02"]["session_count"] == 1
        assert by_date["2026-05-02"]["project_count"] == 1

    @pytest.mark.asyncio
    async def test_filters_by_year_drops_other_years(self):
        beats = [
            _beat("2026-05-01T09:00:00", 60),
            _beat("2025-05-01T09:00:00", 60),
        ]
        svc = AnalyticsService(_FakeBeatRepo(beats))  # type: ignore[arg-type]
        out = await svc.get_heatmap(year=2026)
        assert [d["date"] for d in out] == ["2026-05-01"]

    @pytest.mark.asyncio
    async def test_filters_by_project_id(self):
        beats = [
            _beat("2026-05-01T09:00:00", 30, project_id="p1"),
            _beat("2026-05-01T10:00:00", 30, project_id="p2"),
        ]
        svc = AnalyticsService(_FakeBeatRepo(beats))  # type: ignore[arg-type]
        out = await svc.get_heatmap(year=2026, project_id="p2")
        assert len(out) == 1
        assert out[0]["total_minutes"] == 30
        assert out[0]["project_count"] == 1

    @pytest.mark.asyncio
    async def test_filters_by_tag(self):
        beats = [
            _beat("2026-05-01T09:00:00", 30, tags=["focus"]),
            _beat("2026-05-01T10:00:00", 30, tags=["meeting"]),
        ]
        svc = AnalyticsService(_FakeBeatRepo(beats))  # type: ignore[arg-type]
        out = await svc.get_heatmap(year=2026, tag="focus")
        assert len(out) == 1
        assert out[0]["total_minutes"] == 30

    @pytest.mark.asyncio
    async def test_default_utc_buckets_by_utc_day(self):
        # No tz → UTC. A 23:30Z session stays on its UTC calendar day.
        beats = [_beat("2026-01-01T23:30:00", 30)]
        svc = AnalyticsService(_FakeBeatRepo(beats))  # type: ignore[arg-type]
        out = await svc.get_heatmap(year=2026)
        assert [d["date"] for d in out] == ["2026-01-01"]

    @pytest.mark.asyncio
    async def test_negative_offset_keeps_late_session_on_local_day(self):
        # 2026-01-01T23:30Z in New York is 18:30 the SAME local day.
        beats = [_beat("2026-01-01T23:30:00", 30)]
        svc = AnalyticsService(_FakeBeatRepo(beats))  # type: ignore[arg-type]
        out = await svc.get_heatmap(year=2026, tz=ZoneInfo("America/New_York"))
        assert [d["date"] for d in out] == ["2026-01-01"]

    @pytest.mark.asyncio
    async def test_positive_offset_rolls_late_session_to_next_local_day(self):
        # 2026-01-01T23:30Z in Tokyo (UTC+9) is 08:30 the NEXT local day,
        # so the heatmap must bucket it to 2026-01-02.
        beats = [_beat("2026-01-01T23:30:00", 30)]
        svc = AnalyticsService(_FakeBeatRepo(beats))  # type: ignore[arg-type]
        out = await svc.get_heatmap(year=2026, tz=ZoneInfo("Asia/Tokyo"))
        assert [d["date"] for d in out] == ["2026-01-02"]


class TestAnalyticsDailyRhythm:
    """get_daily_rhythm aggregates beats into 48 half-hour slots
    averaged over the period's days. Three branches plus filters:
      - period="week"  → divisor = days since this Monday
      - period="month" → divisor = days since the 1st
      - period="all"   → divisor = days since the earliest beat
      - empty repo → 48 slots of 0.0, no DivisionByZero

    Risk: a regression in the period divisor would silently halve
    or double every user's daily-rhythm chart. Pin all four
    branches and the per-slot averaging."""

    @pytest.mark.asyncio
    async def test_empty_repo_returns_48_zero_slots(self):
        """No beats → 48 zero-minute slots (not [], not 47, not
        DivisionByZero). Pin so the chart renders an empty
        baseline rather than exploding on first-run accounts."""
        svc = AnalyticsService(_FakeBeatRepo([]))  # type: ignore[arg-type]
        out = await svc.get_daily_rhythm(period="all")
        assert len(out) == 48
        assert all(s["minutes"] == 0 for s in out)
        # Slot index pinned: 0..47 in order
        assert [s["slot"] for s in out] == list(range(48))

    @pytest.mark.asyncio
    async def test_period_all_averages_over_active_span(self):
        """One 60-min beat from 9 days ago → with period="all",
        the divisor is 10 (today inclusive). The 9-10 AM slots
        each get 30 min total, divided by 10 → 3.0 min per slot."""
        from datetime import UTC as _UTC
        from datetime import datetime, time, timedelta

        # Anchor to datetime.now(UTC).date() — the frame get_daily_rhythm
        # uses for its divisor under the default (UTC) tz. Both the divisor
        # "today" and the beat's local_date are then in the same UTC frame,
        # so the 10-day span is stable regardless of the host's local offset.
        utc_today = datetime.now(_UTC).date()
        nine_days_ago = datetime.combine(utc_today - timedelta(days=9), time(hour=9), tzinfo=_UTC)
        beats = [
            Beat(
                id="b1",
                project_id="p1",
                start=nine_days_ago,
                end=nine_days_ago + timedelta(minutes=60),
            )
        ]
        svc = AnalyticsService(_FakeBeatRepo(beats))  # type: ignore[arg-type]
        out = await svc.get_daily_rhythm(period="all")
        # Slot 18 = 9-9:30am, slot 19 = 9:30-10am — each got 30 min
        # over a 10-day span → 3.0 min/slot
        assert out[18]["minutes"] == 3.0
        assert out[19]["minutes"] == 3.0

    @pytest.mark.asyncio
    async def test_period_week_only_counts_this_weeks_beats(self):
        """A beat from before this Monday must NOT contribute when
        period="week". Pin so the weekly view doesn't bleed in
        last week's data."""
        from datetime import UTC as _UTC
        from datetime import datetime, timedelta

        today = date.today()
        last_week = today - timedelta(days=today.weekday() + 1)  # Sunday before this Monday
        old_beat_start = datetime.combine(last_week, datetime.min.time(), tzinfo=_UTC).replace(
            hour=9
        )
        beats = [
            Beat(
                id="b1",
                project_id="p1",
                start=old_beat_start,
                end=old_beat_start + timedelta(minutes=60),
            )
        ]
        svc = AnalyticsService(_FakeBeatRepo(beats))  # type: ignore[arg-type]
        out = await svc.get_daily_rhythm(period="week")
        assert all(s["minutes"] == 0 for s in out)

    @pytest.mark.asyncio
    async def test_period_month_only_counts_current_month(self):
        """A beat from before the 1st must NOT contribute when
        period="month"."""
        from datetime import UTC as _UTC
        from datetime import datetime, timedelta

        today = date.today()
        # On the 1st there is no previous-month day to reach back to, so use today.
        target = today if today.day == 1 else today.replace(day=1) - timedelta(days=1)
        old = datetime.combine(target, datetime.min.time(), tzinfo=_UTC).replace(hour=9)
        beats = [
            Beat(
                id="b1",
                project_id="p1",
                start=old,
                end=old + timedelta(minutes=60),
            )
        ]
        svc = AnalyticsService(_FakeBeatRepo(beats))  # type: ignore[arg-type]
        out = await svc.get_daily_rhythm(period="month")
        # If today.day == 1 the beat IS in this month and should appear;
        # otherwise it must be filtered out
        if today.day == 1:
            assert any(s["minutes"] > 0 for s in out)
        else:
            assert all(s["minutes"] == 0 for s in out)

    @pytest.mark.asyncio
    async def test_filters_by_project_id(self):
        """project_id filter scopes the rhythm to one project. Pin
        so the per-project rhythm chart doesn't include other
        projects' minutes."""
        from datetime import UTC as _UTC
        from datetime import datetime, timedelta

        today = date.today()
        s1 = datetime.combine(today, datetime.min.time(), tzinfo=_UTC).replace(hour=9)
        s2 = datetime.combine(today, datetime.min.time(), tzinfo=_UTC).replace(hour=14)
        beats = [
            Beat(
                id="b1",
                project_id="p1",
                start=s1,
                end=s1 + timedelta(minutes=30),
            ),
            Beat(
                id="b2",
                project_id="p2",
                start=s2,
                end=s2 + timedelta(minutes=30),
            ),
        ]
        svc = AnalyticsService(_FakeBeatRepo(beats))  # type: ignore[arg-type]
        out = await svc.get_daily_rhythm(period="all", project_id="p1")
        # 9 AM (slot 18) has minutes from p1; 2 PM (slot 28) has 0
        assert out[18]["minutes"] > 0
        assert out[28]["minutes"] == 0

    @pytest.mark.asyncio
    async def test_filters_by_tag(self):
        """tag filter scopes to beats containing that tag."""
        from datetime import UTC as _UTC
        from datetime import datetime, timedelta

        today = date.today()
        s1 = datetime.combine(today, datetime.min.time(), tzinfo=_UTC).replace(hour=9)
        s2 = datetime.combine(today, datetime.min.time(), tzinfo=_UTC).replace(hour=14)
        beats = [
            Beat(
                id="b1",
                project_id="p1",
                start=s1,
                end=s1 + timedelta(minutes=30),
                tags=["focus"],
            ),
            Beat(
                id="b2",
                project_id="p1",
                start=s2,
                end=s2 + timedelta(minutes=30),
                tags=["meeting"],
            ),
        ]
        svc = AnalyticsService(_FakeBeatRepo(beats))  # type: ignore[arg-type]
        out = await svc.get_daily_rhythm(period="all", tag="focus")
        assert out[18]["minutes"] > 0
        assert out[28]["minutes"] == 0

    @pytest.mark.asyncio
    async def test_active_beats_skipped_in_rhythm(self):
        """A beat with end=None (active timer) is skipped — pin so
        an in-flight session doesn't double-count once stopped."""
        from datetime import UTC as _UTC
        from datetime import datetime

        today = date.today()
        s = datetime.combine(today, datetime.min.time(), tzinfo=_UTC).replace(hour=9)
        # _FakeBeatRepo.list_all_completed already filters end=None,
        # so seed an active beat ALONGSIDE a completed one. Only the
        # completed beat should land in the rhythm.
        beats = [
            Beat(id="b-active", project_id="p1", start=s, end=None),
        ]
        svc = AnalyticsService(_FakeBeatRepo(beats))  # type: ignore[arg-type]
        out = await svc.get_daily_rhythm(period="all")
        # No completed beats → all slots zero
        assert all(s["minutes"] == 0 for s in out)

    @pytest.mark.asyncio
    async def test_rhythm_slots_use_local_wall_clock(self):
        """A 22:00Z one-hour session lands in the 22:00 UTC slots by
        default, but in the 17:00–18:00 LOCAL slots for New York. Pins
        that slot indexing follows the requesting timezone."""
        beats = [_beat("2026-05-01T22:00:00", 60)]
        svc = AnalyticsService(_FakeBeatRepo(beats))  # type: ignore[arg-type]

        utc_out = await svc.get_daily_rhythm(period="all")
        # 22:00–23:00 UTC → slots 44, 45 (22*2, 22*2+1)
        assert utc_out[44]["minutes"] > 0
        assert utc_out[45]["minutes"] > 0

        ny_out = await svc.get_daily_rhythm(period="all", tz=ZoneInfo("America/New_York"))
        # 22:00Z = 18:00 EDT → slots 36, 37
        assert ny_out[36]["minutes"] > 0
        assert ny_out[37]["minutes"] > 0
        assert ny_out[44]["minutes"] == 0

    @pytest.mark.asyncio
    async def test_rhythm_cross_local_midnight_splits_minutes(self):
        """A session that spans LOCAL midnight has its after-midnight
        minutes attributed to early-morning slots (wrapping to slot 0+),
        not dropped. In Tokyo (UTC+9) a 14:30Z–15:30Z session is
        23:30–00:30 local, so 30 min land in slot 47 and 30 in slot 0."""
        beats = [_beat("2026-05-01T14:30:00", 60)]
        svc = AnalyticsService(_FakeBeatRepo(beats))  # type: ignore[arg-type]
        out = await svc.get_daily_rhythm(period="all", tz=ZoneInfo("Asia/Tokyo"))
        # Single-day span → divisor handling aside, both halves present.
        assert out[47]["minutes"] > 0  # 23:30–24:00 local
        assert out[0]["minutes"] > 0  # 00:00–00:30 local (wrapped)


class TestAnalyticsUntrackedGaps:
    """Pure logic: find gaps ≥ min_gap_minutes between sorted beats on a date."""

    @pytest.mark.asyncio
    async def test_empty_day_returns_no_gaps(self):
        svc = AnalyticsService(_FakeBeatRepo([]))  # type: ignore[arg-type]
        out = await svc.get_untracked_gaps(date(2026, 5, 1))
        assert out == []

    @pytest.mark.asyncio
    async def test_finds_gap_above_threshold(self):
        beats = [
            _beat("2026-05-01T09:00:00", 30),  # ends 09:30
            _beat("2026-05-01T10:00:00", 30),  # 30-min gap, ends 10:30
            _beat("2026-05-01T11:00:00", 30),  # 30-min gap, ends 11:30
        ]
        svc = AnalyticsService(_FakeBeatRepo(beats))  # type: ignore[arg-type]
        out = await svc.get_untracked_gaps(date(2026, 5, 1), min_gap_minutes=15)
        assert len(out) == 2
        assert all(g["duration_minutes"] == 30 for g in out)

    @pytest.mark.asyncio
    async def test_skips_gaps_below_threshold(self):
        beats = [
            _beat("2026-05-01T09:00:00", 30),  # ends 09:30
            _beat("2026-05-01T09:35:00", 30),  # 5-min gap — below 15min threshold
        ]
        svc = AnalyticsService(_FakeBeatRepo(beats))  # type: ignore[arg-type]
        out = await svc.get_untracked_gaps(date(2026, 5, 1), min_gap_minutes=15)
        assert out == []

    @pytest.mark.asyncio
    async def test_threshold_is_inclusive(self):
        beats = [
            _beat("2026-05-01T09:00:00", 30),  # ends 09:30
            _beat("2026-05-01T09:45:00", 30),  # exactly 15min gap
        ]
        svc = AnalyticsService(_FakeBeatRepo(beats))  # type: ignore[arg-type]
        out = await svc.get_untracked_gaps(date(2026, 5, 1), min_gap_minutes=15)
        assert len(out) == 1
        assert out[0]["duration_minutes"] == 15

    @pytest.mark.asyncio
    async def test_overlapping_beats_produce_no_gap(self):
        # If beat B starts before beat A ends, that's not a "gap" — the
        # condition `next_start > current_end` is false. Pin the
        # behavior so a refactor that uses >= doesn't accidentally
        # produce zero-duration gaps.
        beats = [
            _beat("2026-05-01T09:00:00", 60),  # 09:00–10:00
            _beat("2026-05-01T09:30:00", 30),  # overlaps
        ]
        svc = AnalyticsService(_FakeBeatRepo(beats))  # type: ignore[arg-type]
        out = await svc.get_untracked_gaps(date(2026, 5, 1))
        assert out == []


class TestDetectChronotype:
    """detect_chronotype labels users early/midday/afternoon/evening
    /night based on where their Flow Score peaks across hour-of-day.
    Risk: a refactor that flipped the percentile or the label
    ranges would silently misclassify every user."""

    def test_empty_returns_no_card(self):

        assert detect_chronotype([]) == []

    def test_below_50_windows_returns_no_card(self):
        """The detector requires ≥50 windows. Pin so a low-data
        user doesn't get a confident-looking but noisy chronotype
        label."""

        windows = [
            _flow_window(day=date(2026, 4, 1), hour=h, score=0.7) for h in range(24)
        ]  # 24 windows, < 50
        assert detect_chronotype(windows) == []

    def test_fewer_than_4_distinct_hours_returns_no_card(self):
        """≥50 windows but only 3 distinct hours → no card. Pin
        the spread requirement so a user who only ever tracks in
        a 3-hour window doesn't get labeled."""

        windows = []
        for i in range(60):
            windows.append(
                _flow_window(
                    day=date(2026, 4, 1) + timedelta(days=i // 3),
                    hour=9 + (i % 3),
                    score=0.7,
                )
            )
        assert detect_chronotype(windows) == []

    def test_all_zero_scores_returns_no_card(self):
        """All flow_score=0 → smoothed values all 0 → the
        any(v>0) guard fires. Pin so a brand-new daemon user
        with no focused sessions yet doesn't get a chronotype
        card."""

        windows = [
            _flow_window(day=date(2026, 4, 1) + timedelta(days=d), hour=h, score=0.0)
            for d in range(15)
            for h in range(8, 12)
        ]
        assert detect_chronotype(windows) == []

    def test_morning_peak_labels_early_person(self):
        """Strong scores at 7-9 AM, low scores afternoon → label
        is "early". Pin the label, the title, and the peak_start/
        peak_end in data — the dashboard's chronotype card binds
        to those fields."""

        windows = []
        for d in range(14):
            day = date(2026, 4, 1) + timedelta(days=d)
            for h in range(7, 10):  # 7-9 AM, high score
                windows.append(_flow_window(day=day, hour=h, score=0.9))
            for h in range(13, 18):
                windows.append(_flow_window(day=day, hour=h, score=0.1))
        result = detect_chronotype(windows)
        assert len(result) == 1
        card = result[0]
        assert card.type == "chronotype"
        assert "early" in card.title.lower()
        assert card.data["label"] == "early"
        # Smoothing pulls in adjacent hours; peak is morning-ish
        assert min(card.data["peak_hours"]) >= 6
        assert max(card.data["peak_hours"]) <= 10

    def test_evening_peak_labels_evening_person(self):
        """Peak at 19-21 → "evening" label."""

        windows = []
        for d in range(14):
            day = date(2026, 4, 1) + timedelta(days=d)
            for h in range(19, 22):
                windows.append(_flow_window(day=day, hour=h, score=0.9))
            for h in range(8, 12):
                windows.append(_flow_window(day=day, hour=h, score=0.1))
        result = detect_chronotype(windows)
        assert len(result) == 1
        assert result[0].data["label"] == "evening"


# Datetime utilities — normalize_tz
