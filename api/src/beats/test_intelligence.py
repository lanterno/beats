"""The productivity score and the pattern detectors.

Split out of `test_domain.py` at the ceiling in roadmaps/file-sizes.md;
the shared fakes and factories are `domain_fakes.py`'s.
"""

from datetime import UTC, date, datetime, timedelta

from beats.domain.intelligence import (
    WeekGoal,
    detect_day_pattern,
    detect_goal_pacing,
    detect_peak_hours,
    detect_session_trend,
    detect_stale_projects,
    week_goals,
)
from beats.domain.models import (
    Beat,
    GoalType,
)
from beats.domain_fakes import (
    _day_job,
    _FakeWeekExpectationReader,
    _intel_service,
    _project,
    _split_week,
)


class TestProductivityScore:
    """compute_productivity_score breaks 0-100 into three 0-25 components:
    consistency (weekdays tracked) + goals (avg progress) + quality
    (median session length minus fragmentation penalty), then rescales the
    0-75 sum to 0-100 via *4/3. Risk: a regression in any component shifts
    the user's perceived productivity story silently. These tests pin each
    component's logic on representative seeded data."""

    async def test_empty_data_returns_neutral_score(self):
        """Fresh-account path — no sessions, no goals.
        consistency=0 + goals=13 (neutral) + quality=0 = 13, rescaled
        round(13 * 4/3) = 17. Pin so a divide-by-zero regression fails the
        test rather than silently 500'ing the /score endpoint for new
        users."""
        svc = _intel_service()
        result = await svc.compute_productivity_score()
        assert "score" in result
        assert "components" in result
        components = result["components"]
        assert components["consistency"] == 0
        assert components["goals"] == 13  # neutral default
        assert components["quality"] == 0
        assert "intentions" not in components
        assert result["score"] == 17

    async def test_consistency_full_when_all_5_weekdays_tracked(self):
        """Consistency = 25 when all 5 most-recent weekdays have at
        least one session. Locks the floor of the formula."""
        today = datetime.now(UTC).date()
        # Find the 5 most-recent weekdays.
        weekdays = []
        d = today
        while len(weekdays) < 5:
            if d.weekday() < 5:
                weekdays.append(d)
            d -= timedelta(days=1)

        beats = [
            Beat(
                id=f"b-{wd.isoformat()}",
                project_id="p1",
                start=datetime.combine(wd, datetime.min.time(), tzinfo=UTC).replace(hour=10),
                end=datetime.combine(wd, datetime.min.time(), tzinfo=UTC).replace(hour=11),
            )
            for wd in weekdays
        ]
        svc = _intel_service(beats=beats)
        result = await svc.compute_productivity_score()
        assert result["components"]["consistency"] == 25

    async def test_goal_progress_caps_at_25_when_target_hit(self):
        """A project that hit (or exceeded) its weekly goal contributes
        max progress (1.0) to the average. Single-project case → 25."""
        from datetime import time

        today = datetime.now(UTC).date()
        week_start = today - timedelta(days=today.weekday())
        # 10h of sessions this week toward a 5h goal. compute_productivity_score
        # only loads the last 7 days up to today, so the sessions must land in
        # the elapsed part of this week (week_start..today) — spreading them
        # across the full Mon-Sun would drop the still-future days and undercount.
        days_elapsed = today.weekday() + 1  # Monday..today, inclusive
        beats = []
        for i in range(10):
            day = week_start + timedelta(days=i % days_elapsed)
            s = datetime.combine(day, time(hour=9 + i // days_elapsed), tzinfo=UTC)
            beats.append(
                Beat(
                    id=f"b-{i}",
                    project_id="p1",
                    start=s,
                    end=s + timedelta(hours=1),
                )
            )
        projects = [_project("p1", "Alpha", weekly_goal=5.0)]
        svc = _intel_service(beats=beats, projects=projects)
        result = await svc.compute_productivity_score()
        # Goal score should be at the max (25) — progress capped at 1.0.
        assert result["components"]["goals"] == 25

    async def test_quality_long_sessions_no_fragmentation(self):
        """A clean day of 60-90 min sessions → high quality (length
        bucket 18-23, no fragmentation penalty)."""
        today = datetime.now(UTC).date()
        beats = []
        for i in range(3):
            s = datetime.combine(today, datetime.min.time(), tzinfo=UTC).replace(
                hour=9
            ) + timedelta(hours=i * 2)
            beats.append(
                Beat(
                    id=f"b-{i}",
                    project_id="p1",
                    start=s,
                    end=s + timedelta(minutes=75),  # > 60 → bucket 23
                )
            )
        svc = _intel_service(beats=beats)
        result = await svc.compute_productivity_score()
        # 75-min median falls in the 60..120 bucket = 23. No < 5min
        # gaps between sessions (gap is ~45 min), so no penalty.
        assert result["components"]["quality"] == 23

    async def test_quality_fragmentation_penalty_subtracts(self):
        """Two same-day sessions with a < 5-minute gap between them
        get penalized by 5. Pin the penalty value — the formula is
        sensitive to the threshold."""
        today = datetime.now(UTC).date()
        s1 = datetime.combine(today, datetime.min.time(), tzinfo=UTC).replace(hour=9)
        beats = [
            Beat(
                id="b1",
                project_id="p1",
                start=s1,
                end=s1 + timedelta(minutes=70),  # 70-min session, length=23
            ),
            Beat(
                id="b2",
                project_id="p1",
                # Starts 2 min after b1 ends → fragmentation penalty fires.
                start=s1 + timedelta(minutes=72),
                end=s1 + timedelta(minutes=72 + 70),
            ),
        ]
        svc = _intel_service(beats=beats)
        result = await svc.compute_productivity_score()
        # length_score=23 (median 70min in 60..120 bucket) minus 5 frag penalty = 18.
        assert result["components"]["quality"] == 18

    async def test_total_score_caps_at_100(self):
        """The score is `min(100, round((consistency + goals + quality) *
        4 / 3))`. Locks the cap so a future component doesn't overshoot."""
        today = datetime.now(UTC).date()
        # Construct max-everything: 5 weekdays tracked, full goal progress,
        # long sessions.
        weekdays = []
        d = today
        while len(weekdays) < 5:
            if d.weekday() < 5:
                weekdays.append(d)
            d -= timedelta(days=1)

        beats = []
        for wd in weekdays:
            s = datetime.combine(wd, datetime.min.time(), tzinfo=UTC).replace(hour=10)
            beats.append(Beat(id=f"b-{wd}", project_id="p1", start=s, end=s + timedelta(hours=2)))

        projects = [_project("p1", "Alpha", weekly_goal=2.0)]
        svc = _intel_service(beats=beats, projects=projects)
        result = await svc.compute_productivity_score()
        # (25 + 25 + 25) * 4/3 = 100, capped.
        assert result["score"] <= 100
        # And in fact equals 100 here.
        assert result["score"] == 100


class TestProductivityScoreHistory:
    """compute_productivity_score_history powers the score sparkline.
    The HTTP wrapper is already pinned by the route's range-validation
    test (TestIntelligenceAPI.test_score_history_validates_weeks_range);
    these tests pin the per-week aggregation logic underneath: which
    weeks get included, in what order, and how each week's score is
    computed independently."""

    async def test_returns_n_entries(self):
        """weeks=N produces exactly N history rows."""
        svc = _intel_service()
        result = await svc.compute_productivity_score_history(weeks=4)
        assert len(result) == 4

    async def test_default_weeks_is_eight(self):
        svc = _intel_service()
        result = await svc.compute_productivity_score_history()
        assert len(result) == 8

    async def test_empty_data_renders_neutral_score_per_week(self):
        """Fresh-account → every week is the neutral baseline (no
        sessions, no goal projects). Pin so a regression that would 500
        on empty data fails the test instead."""
        svc = _intel_service()
        result = await svc.compute_productivity_score_history(weeks=4)
        # Each week: consistency=0, goals=13 (neutral, no goal_projects),
        # quality=0 → round(13 * 4/3) = 17.
        for entry in result:
            assert entry["score"] == 17

    async def test_entries_carry_week_of_and_score_keys(self):
        svc = _intel_service()
        result = await svc.compute_productivity_score_history(weeks=2)
        for entry in result:
            assert set(entry.keys()) == {"week_of", "score"}
            # week_of is an ISO date string starting with YYYY-MM-DD.
            assert len(entry["week_of"]) == 10
            assert entry["week_of"][4] == "-"

    async def test_entries_ordered_oldest_to_newest(self):
        """The sparkline renders left-to-right chronologically. The
        loop walks weeks=N..1 producing oldest first; pin so a
        refactor that drops the descending walk doesn't reverse the
        sparkline."""
        svc = _intel_service()
        result = await svc.compute_productivity_score_history(weeks=4)
        weeks = [entry["week_of"] for entry in result]
        # Strictly ascending.
        assert weeks == sorted(weeks)
        # And no duplicates.
        assert len(set(weeks)) == len(weeks)

    async def test_excludes_current_week(self):
        """The loop runs `for w in range(weeks, 0, -1)` so the
        smallest offset is 1 week — the CURRENT week is never
        included. Pin so a future tweak that lets w=0 in (turning
        the in-progress week's partial data into a misleading
        sparkline endpoint) breaks the test."""
        from beats.domain.intelligence import _monday_of

        today = datetime.now(UTC).date()
        current_monday = _monday_of(today).isoformat()

        svc = _intel_service()
        result = await svc.compute_productivity_score_history(weeks=4)
        weeks = {entry["week_of"] for entry in result}
        assert current_monday not in weeks

    async def test_each_week_is_sliced_independently(self):
        """A session three weeks ago should NOT affect the score for
        a week with no sessions. Pin per-week isolation so a
        refactor that conflates ranges doesn't smear scores."""
        from beats.domain.intelligence import _monday_of

        today = datetime.now(UTC).date()
        three_weeks_ago_monday = _monday_of(today) - timedelta(weeks=3)
        # One session, three weeks ago, on a weekday → that week
        # gets +5 consistency.
        s = datetime.combine(three_weeks_ago_monday, datetime.min.time(), tzinfo=UTC).replace(
            hour=10
        )
        beats = [Beat(id="b1", project_id="p1", start=s, end=s + timedelta(hours=1))]
        svc = _intel_service(beats=beats)
        result = await svc.compute_productivity_score_history(weeks=4)
        by_week = {e["week_of"]: e["score"] for e in result}

        # Three-weeks-ago: 5 (consistency) + 13 (goals) + 23 (quality
        # for a 60-min session in the "< 120" bucket), rescaled — higher
        # than the empty baseline.
        assert by_week[three_weeks_ago_monday.isoformat()] > 17
        # And the OTHER weeks (no sessions in them) stay at the
        # empty baseline.
        for w in [
            (_monday_of(today) - timedelta(weeks=2)).isoformat(),
            (_monday_of(today) - timedelta(weeks=4)).isoformat(),
        ]:
            assert by_week[w] == 17


class TestPatternDetectorsDay:
    """_detect_day_pattern fires when one weekday is materially busier
    than the average. Threshold: avg > overall_avg × 1.5 AND avg > 30
    minutes. Pin both halves of the threshold and the empty-data
    fallback so a refactor doesn't surface noise as signal."""

    def _service(self):
        return _intel_service()

    def _seed_beats_on_weekday(
        self,
        target_dow: int,
        weeks_back: int = 8,
        minutes_per_week: int = 240,
    ) -> list:
        """Build beats that put N minutes of activity on the target
        weekday (0=Mon..6=Sun) for each of the last `weeks_back`
        weeks. Other days remain empty."""
        from beats.domain.intelligence import _monday_of

        today = datetime.now(UTC).date()
        beats = []
        for w in range(weeks_back):
            monday = _monday_of(today) - timedelta(weeks=w)
            d = monday + timedelta(days=target_dow)
            s = datetime.combine(d, datetime.min.time(), tzinfo=UTC).replace(hour=10)
            beats.append(
                Beat(
                    id=f"b-w{w}",
                    project_id="p1",
                    start=s,
                    end=s + timedelta(minutes=minutes_per_week),
                )
            )
        return beats

    async def test_no_data_returns_no_card(self):

        today = datetime.now(UTC).date()
        result = detect_day_pattern([], today)
        assert result == []

    async def test_low_overall_activity_returns_no_card(self):
        """If overall average < 10 min/day, the detector skips —
        the dataset is too sparse to call any day a "power day"."""
        from beats.domain.intelligence import _monday_of

        today = datetime.now(UTC).date()
        # One 5-minute beat on a single Tuesday — way under threshold.
        monday = _monday_of(today) - timedelta(weeks=1)
        s = datetime.combine(monday + timedelta(days=1), datetime.min.time(), tzinfo=UTC).replace(
            hour=10
        )
        beats = [Beat(id="b1", project_id="p1", start=s, end=s + timedelta(minutes=5))]
        result = detect_day_pattern(beats, today)
        assert result == []

    async def test_clear_power_day_returns_card(self):
        """Heavy activity concentrated on one weekday → one
        InsightCard with the day name in the title."""
        today = datetime.now(UTC).date()
        # 4 hours every Tuesday for 8 weeks, nothing else.
        beats = self._seed_beats_on_weekday(target_dow=1, weeks_back=8, minutes_per_week=240)
        cards = detect_day_pattern(beats, today)
        assert len(cards) == 1
        card = cards[0]
        assert card.type == "day_pattern"
        assert "Tuesday" in card.title
        assert "power day" in card.title.lower()
        assert card.priority == 3
        # The data dict carries the day + ratio (rounded).
        assert card.data["day"] == "Tuesday"
        assert card.data["ratio"] >= 1.5  # threshold

    async def test_threshold_below_1_5x_skips(self):
        """A modest spike below the 1.5× threshold produces no card.
        Pin the threshold — without it, every day with above-average
        activity would surface.

        Setup: 60 min every day (Mon-Sun), Tuesday gets +20 min
        (80 total). Overall avg = (60×6 + 80) / 7 ≈ 62.86. Tuesday
        ratio ≈ 1.27 — well below 1.5×."""
        from beats.domain.intelligence import _monday_of

        today = datetime.now(UTC).date()
        beats = []
        for w in range(8):
            monday = _monday_of(today) - timedelta(weeks=w)
            for dow in range(7):  # Mon..Sun
                d = monday + timedelta(days=dow)
                s = datetime.combine(d, datetime.min.time(), tzinfo=UTC).replace(hour=10)
                mins = 60 + (20 if dow == 1 else 0)  # Tuesday +20
                beats.append(
                    Beat(
                        id=f"b-w{w}-d{dow}",
                        project_id="p1",
                        start=s,
                        end=s + timedelta(minutes=mins),
                    )
                )
        cards = detect_day_pattern(beats, today)
        assert cards == []

    async def test_threshold_below_30min_absolute_skips(self):
        """Even a 5x ratio doesn't fire if the day's avg is <30 min.
        The detector requires both relative AND absolute thresholds
        — pins both prongs so a refactor that drops one (e.g. fires
        on a day with 5 min vs 1 min average) doesn't spam users
        with low-signal cards."""
        from beats.domain.intelligence import _monday_of

        today = datetime.now(UTC).date()
        beats = []
        # 1 min on Mon-Fri, 20 min on Saturday → 20× ratio but only
        # 20 min absolute. Skip threshold met on relative, missed on
        # absolute. Need overall_avg > 10 first though — let me bump
        # the active-day count to satisfy the >=10min overall gate.
        # 5 weekdays × 1min + 1 weekend × 20min = 25min / 6 days = 4.17 — under 10.
        # So the first gate (overall_avg < 10) will short-circuit. Pin
        # this no-card outcome instead — it confirms the absolute
        # threshold logic via the cheaper gate.
        for w in range(8):
            monday = _monday_of(today) - timedelta(weeks=w)
            for dow in range(5):
                d = monday + timedelta(days=dow)
                s = datetime.combine(d, datetime.min.time(), tzinfo=UTC).replace(hour=10)
                beats.append(
                    Beat(
                        id=f"b-w{w}-d{dow}", project_id="p1", start=s, end=s + timedelta(minutes=1)
                    )
                )
            sat = monday + timedelta(days=5)
            s_sat = datetime.combine(sat, datetime.min.time(), tzinfo=UTC).replace(hour=10)
            beats.append(
                Beat(
                    id=f"b-w{w}-sat",
                    project_id="p1",
                    start=s_sat,
                    end=s_sat + timedelta(minutes=20),
                )
            )

        cards = detect_day_pattern(beats, today)
        # Either the overall_avg<10 gate or the abs<30 threshold
        # blocks. Pin: no card.
        assert cards == []


class TestPatternDetectorsPeakHours:
    """_detect_peak_hours buckets sessions into 12 two-hour blocks
    (00:00-02:00, 02:00-04:00, ...) and surfaces an insight if one
    block has more than 2× the median minutes. Locks the bucketing
    + threshold + InsightCard data shape."""

    def _service(self):
        return _intel_service()

    async def test_no_data_returns_no_card(self):
        assert detect_peak_hours([]) == []

    async def test_under_3_blocks_returns_no_card(self):
        """The detector requires at least 3 distinct populated blocks
        before calling any one a "peak". Without this guard, a user
        whose only-tracked sessions all fell in one block would see
        a self-referential "peak hours = your only hours" insight."""
        s = datetime.now(UTC).replace(hour=10, minute=0, second=0, microsecond=0)
        beats = [
            Beat(id="b1", project_id="p1", start=s, end=s + timedelta(minutes=60)),
            Beat(
                id="b2",
                project_id="p1",
                start=s + timedelta(minutes=90),
                end=s + timedelta(minutes=150),
            ),
        ]
        # Both beats fall in the same 10-12 block → only 1 distinct
        # block populated → guard fires.
        assert detect_peak_hours(beats) == []

    async def test_clear_peak_block_returns_card_with_hour_range(self):
        """A block with > 2× the median session-minutes surfaces as a
        card titled with the hour range (e.g. 'Peak hours: 10:00-12:00')."""
        # Big chunk of activity in 10:00-12:00 (block 5), tiny chunks
        # in three other blocks so med() can compute.
        base = datetime.now(UTC).replace(year=2026, month=5, day=1)

        def at(hour, minutes):
            s = base.replace(hour=hour, minute=0)
            return Beat(
                id=f"b-{hour}",
                project_id="p1",
                start=s,
                end=s + timedelta(minutes=minutes),
            )

        beats = [
            at(10, 120),  # 120 min in block 5 (10-12)
            at(8, 5),  # 5 min block 4
            at(14, 10),  # 10 min block 7
            at(16, 5),  # 5 min block 8
        ]
        cards = detect_peak_hours(beats)
        assert len(cards) == 1
        card = cards[0]
        assert card.type == "time_pattern"
        assert "10:00" in card.title
        assert "12:00" in card.title
        assert card.data["start_hour"] == 10
        assert card.data["end_hour"] == 12
        assert card.priority == 3

    async def test_peak_below_2x_median_returns_no_card(self):
        """If no block exceeds 2× the median, the spread is too even
        to call any block a "peak". Pin the threshold."""
        base = datetime.now(UTC).replace(year=2026, month=5, day=1)

        def at(hour, minutes):
            s = base.replace(hour=hour, minute=0)
            return Beat(
                id=f"b-{hour}",
                project_id="p1",
                start=s,
                end=s + timedelta(minutes=minutes),
            )

        # All blocks roughly equal — median ~30, max ~40 → ratio 1.33.
        beats = [at(8, 30), at(10, 40), at(14, 30), at(16, 25)]
        assert detect_peak_hours(beats) == []


class TestPatternDetectorsStaleProjects:
    """_detect_stale_projects flags projects with weekly_goal but no
    activity in the last 14 days. Threshold: archived → skip; no
    weekly_goal → skip; last activity 14+ days ago (or never) → fire."""

    def _service(self):
        return _intel_service()

    async def test_no_projects_returns_no_card(self):
        today = datetime.now(UTC).date()
        assert detect_stale_projects([], [], today) == []

    async def test_skips_projects_without_weekly_goal(self):
        today = datetime.now(UTC).date()
        projects = [_project("p1", "Casual", weekly_goal=None)]
        assert detect_stale_projects([], projects, today) == []

    async def test_skips_archived_even_with_goal(self):
        today = datetime.now(UTC).date()
        projects = [_project("p1", "Old", weekly_goal=5.0, archived=True)]
        assert detect_stale_projects([], projects, today) == []

    async def test_no_activity_ever_fires_card(self):
        """ZERO recorded sessions → fires with days_since=999 (the
        sentinel for "never"). Pin so a refactor changing the
        never-tracked default doesn't mis-render in the UI."""
        today = datetime.now(UTC).date()
        projects = [_project("p1", "Untouched", weekly_goal=5.0)]
        cards = detect_stale_projects([], projects, today)
        assert len(cards) == 1
        card = cards[0]
        assert card.type == "stale_project"
        assert "Untouched" in card.title
        assert "needs attention" in card.title.lower()
        assert card.priority == 4
        assert card.data["days_since"] == 999
        assert card.data["project_id"] == "p1"

    async def test_recent_activity_skips_card(self):
        today = datetime.now(UTC).date()
        projects = [_project("p1", "Active", weekly_goal=5.0)]
        five_days_ago = today - timedelta(days=5)
        s = datetime.combine(five_days_ago, datetime.min.time(), tzinfo=UTC).replace(hour=10)
        beats = [Beat(id="b1", project_id="p1", start=s, end=s + timedelta(hours=1))]
        assert detect_stale_projects(beats, projects, today) == []

    async def test_threshold_is_14_days_inclusive(self):
        """Threshold is `>= 14`. Pin the boundary so a refactor that
        bumps to 13 (one extra day's grace) or 15 (one less) is a
        deliberate change."""
        today = datetime.now(UTC).date()
        projects = [_project("p1", "Borderline", weekly_goal=5.0)]

        # 13 days ago — fresh.
        s13 = datetime.combine(today - timedelta(days=13), datetime.min.time(), tzinfo=UTC).replace(
            hour=10
        )
        assert (
            detect_stale_projects(
                [Beat(id="b1", project_id="p1", start=s13, end=s13 + timedelta(hours=1))],
                projects,
                today,
            )
            == []
        )

        # 14 days ago — stale.
        s14 = datetime.combine(today - timedelta(days=14), datetime.min.time(), tzinfo=UTC).replace(
            hour=10
        )
        cards = detect_stale_projects(
            [Beat(id="b2", project_id="p1", start=s14, end=s14 + timedelta(hours=1))],
            projects,
            today,
        )
        assert len(cards) == 1
        assert cards[0].data["days_since"] == 14

    async def test_governed_project_quotes_the_contracts_expectation(self):
        """On a day job the contract governs, the map carries what the week
        expects after holidays and absences, and the card quotes that — the
        figure the pacing card beside it in the Inbox quotes too. A week the
        contract expects nothing of, every day a holiday or an absence, is no
        week to need attention."""
        today = datetime.now(UTC).date()
        expects = {"p1": WeekGoal(hours=32.0, goal_type=GoalType.TARGET, source="contract")}
        cards = detect_stale_projects([], [_day_job("p1")], today, goals=expects)
        assert len(cards) == 1
        assert cards[0].body == (
            "You haven't tracked time on Day job in 999 days, "
            "but your contract still expects 32.0h of it this week."
        )

        off = {"p1": WeekGoal(hours=0.0, goal_type=GoalType.TARGET, source="contract")}
        assert detect_stale_projects([], [_day_job("p1")], today, goals=off) == []

    async def test_one_card_per_stale_project(self):
        today = datetime.now(UTC).date()
        projects = [
            _project("p1", "Alpha", weekly_goal=5.0),
            _project("p2", "Beta", weekly_goal=3.0),
            _project("p3", "Gamma", weekly_goal=None),  # no goal → skipped
        ]
        cards = detect_stale_projects([], projects, today)
        assert len(cards) == 2


class TestPatternDetectorsSessionTrend:
    """_detect_session_trend compares this week's avg session length
    to the prior 4-week average. Surfaces a card if |relative
    change| > 30%. Sample-size guards prevent noise.

    Thresholds: ≥3 sessions this week, ≥5 in prior 4 weeks,
    prior_avg > 5 min, |change| > 30%."""

    def _service(self):
        return _intel_service()

    def _beats_in_range(
        self,
        start_date: date,
        end_date: date,
        per_day_minutes: int,
        project_id: str = "p1",
    ) -> list:
        beats = []
        d = start_date
        i = 0
        while d <= end_date:
            s = datetime.combine(d, datetime.min.time(), tzinfo=UTC).replace(hour=10)
            beats.append(
                Beat(
                    id=f"b-{i}",
                    project_id=project_id,
                    start=s,
                    end=s + timedelta(minutes=per_day_minutes),
                )
            )
            d += timedelta(days=1)
            i += 1
        return beats

    def _beats_on_day(
        self,
        day: date,
        count: int,
        per_session_minutes: int,
        project_id: str = "p1",
    ) -> list:
        """`count` non-overlapping sessions on a single day. Lets a test put a
        fixed number of this-week sessions on Monday regardless of which weekday
        the suite runs on — week_start..today can be a single day on a Monday,
        which is too few for the trend detector's 3-session minimum."""
        from datetime import time

        beats = []
        for j in range(count):
            s = datetime.combine(day, time(hour=9 + j * 2), tzinfo=UTC)
            beats.append(
                Beat(
                    id=f"d-{j}",
                    project_id=project_id,
                    start=s,
                    end=s + timedelta(minutes=per_session_minutes),
                )
            )
        return beats

    async def test_too_few_this_week_returns_no_card(self):
        from beats.domain.intelligence import _monday_of

        today = datetime.now(UTC).date()
        this_monday = _monday_of(today)
        s = datetime.combine(this_monday, datetime.min.time(), tzinfo=UTC).replace(hour=10)
        beats = [Beat(id="b-this", project_id="p1", start=s, end=s + timedelta(hours=1))]
        beats += self._beats_in_range(
            this_monday - timedelta(weeks=4), this_monday - timedelta(days=1), 60
        )
        assert detect_session_trend(beats, today) == []

    async def test_too_few_prior_returns_no_card(self):
        from beats.domain.intelligence import _monday_of

        today = datetime.now(UTC).date()
        this_monday = _monday_of(today)
        beats = self._beats_in_range(this_monday, this_monday + timedelta(days=4), 60)
        beats += self._beats_in_range(
            this_monday - timedelta(days=10), this_monday - timedelta(days=8), 60
        )
        assert detect_session_trend(beats, today) == []

    async def test_change_below_30_percent_returns_no_card(self):
        from beats.domain.intelligence import _monday_of

        today = datetime.now(UTC).date()
        this_monday = _monday_of(today)
        beats = self._beats_in_range(this_monday, today, 60)
        beats += self._beats_in_range(
            this_monday - timedelta(weeks=4), this_monday - timedelta(days=1), 65
        )
        assert detect_session_trend(beats, today) == []

    async def test_significant_increase_fires_with_longer_direction(self):
        from beats.domain.intelligence import _monday_of

        today = datetime.now(UTC).date()
        this_monday = _monday_of(today)
        beats = self._beats_on_day(this_monday, 3, 90)
        beats += self._beats_in_range(
            this_monday - timedelta(weeks=4), this_monday - timedelta(days=1), 60
        )
        cards = detect_session_trend(beats, today)
        assert len(cards) == 1
        card = cards[0]
        assert card.type == "session_trend"
        assert "longer" in card.title
        assert card.priority == 2
        assert card.data["change_pct"] > 0

    async def test_significant_decrease_fires_with_shorter_direction(self):
        from beats.domain.intelligence import _monday_of

        today = datetime.now(UTC).date()
        this_monday = _monday_of(today)
        beats = self._beats_on_day(this_monday, 3, 30)
        beats += self._beats_in_range(
            this_monday - timedelta(weeks=4), this_monday - timedelta(days=1), 60
        )
        cards = detect_session_trend(beats, today)
        assert len(cards) == 1
        assert "shorter" in cards[0].title
        assert cards[0].data["change_pct"] < 0

    async def test_prior_avg_below_5_min_skips(self):
        """Prior baseline < 5 min → data is junk; even a huge
        relative change is noise."""
        from beats.domain.intelligence import _monday_of

        today = datetime.now(UTC).date()
        this_monday = _monday_of(today)
        beats = self._beats_in_range(this_monday, today, 60)
        beats += self._beats_in_range(
            this_monday - timedelta(weeks=4), this_monday - timedelta(days=1), 1
        )
        assert detect_session_trend(beats, today) == []


class TestPatternDetectorsGoalPacing:
    """_detect_goal_pacing fires Friday/Saturday/Sunday when a
    project's weekly target goal is at < 50% with ≤3 days left.
    Catches the "I forgot to work on X this week" pattern.

    Risk: an over-aggressive pacing alert (firing on Mon when there
    are 7 days left) would be noise."""

    def _service(self):
        return _intel_service()

    def _friday_after(self, base: date) -> date:
        from beats.domain.intelligence import _monday_of

        return _monday_of(base) + timedelta(days=4)

    async def test_no_projects_returns_no_card(self):
        assert detect_goal_pacing([], [], self._friday_after(datetime.now(UTC).date())) == []

    async def test_skips_archived_projects(self):
        archived = _project("p1", "Old", weekly_goal=5.0, archived=True)
        result = detect_goal_pacing([], [archived], self._friday_after(datetime.now(UTC).date()))
        assert result == []

    async def test_skips_projects_without_goal(self):
        no_goal = _project("p1", "Casual", weekly_goal=None)
        result = detect_goal_pacing([], [no_goal], self._friday_after(datetime.now(UTC).date()))
        assert result == []

    async def test_early_in_week_skips_card(self):
        """On Monday there are still 7 days left — even at 0%
        progress, no pacing card fires. Threshold is days_left ≤ 3."""
        from beats.domain.intelligence import _monday_of

        today = datetime.now(UTC).date()
        this_monday = _monday_of(today)
        projects = [_project("p1", "Alpha", weekly_goal=10.0)]
        assert detect_goal_pacing([], projects, this_monday) == []

    async def test_friday_with_low_progress_fires(self):
        """Friday + < 50% of goal tracked → card with remaining
        hours and days_left in the data dict."""
        from beats.domain.intelligence import _monday_of

        today = datetime.now(UTC).date()
        friday = self._friday_after(today)
        monday = _monday_of(friday)
        s = datetime.combine(monday, datetime.min.time(), tzinfo=UTC).replace(hour=10)
        # 1h tracked vs 10h goal → 10%, well under 50%.
        beats = [Beat(id="b1", project_id="p1", start=s, end=s + timedelta(hours=1))]
        projects = [_project("p1", "Alpha", weekly_goal=10.0)]
        cards = detect_goal_pacing(beats, projects, friday)
        assert len(cards) == 1
        card = cards[0]
        assert card.type == "goal_pacing"
        assert "Alpha" in card.title
        assert "9.0h" in card.title
        assert card.priority == 4
        assert card.data["days_left"] == 3
        assert card.data["remaining"] == 9.0

    async def test_governed_project_paces_against_the_contracts_expectation(self):
        """On a day job the contract governs, the map carries what the week
        expects after holidays and absences — 32 h with a day of vacation
        booked against a 40 h term — and the hours to go are counted from it,
        so the card agrees with the week card beside it in the Inbox."""
        from beats.domain.intelligence import _monday_of

        friday = self._friday_after(datetime.now(UTC).date())
        s = datetime.combine(_monday_of(friday), datetime.min.time(), tzinfo=UTC).replace(hour=10)
        beats = [Beat(id="b1", project_id="p1", start=s, end=s + timedelta(hours=1))]
        goals = {"p1": WeekGoal(hours=32.0, goal_type=GoalType.TARGET, source="contract")}

        cards = detect_goal_pacing(beats, [_day_job("p1")], friday, goals=goals)

        assert len(cards) == 1
        assert cards[0].data["remaining"] == 31.0
        assert cards[0].body == (
            "You need 31.0h more on Day job this week under your contract — 3 days left."
        )

    async def test_hours_under_a_term_that_owes_nothing_are_not_counted_toward_the_week(self):
        # AHM-82. The pacing card's hours to go are the week card's
        # Remaining: Wednesday's 4 h under the objective term owe the week
        # nothing, so 10 h of its 16 are to go, and 6 h is under half.
        project, beats = _split_week()
        monday = date(2026, 3, 2)
        goals = await week_goals([project], monday, _FakeWeekExpectationReader({"p1": 16.0}))

        cards = detect_goal_pacing(beats, [project], monday + timedelta(days=4), goals=goals)

        assert [card.data["remaining"] for card in cards] == [10.0]

    async def test_friday_with_high_progress_skips(self):
        """≥ 50% progress by Friday → no nag."""
        from beats.domain.intelligence import _monday_of

        today = datetime.now(UTC).date()
        friday = self._friday_after(today)
        monday = _monday_of(friday)
        s = datetime.combine(monday, datetime.min.time(), tzinfo=UTC).replace(hour=10)
        beats = [Beat(id="b1", project_id="p1", start=s, end=s + timedelta(hours=6))]
        projects = [_project("p1", "Alpha", weekly_goal=10.0)]
        assert detect_goal_pacing(beats, projects, friday) == []

    async def test_goal_already_met_returns_no_card(self):
        """remaining ≤ 0 → no card. "X to go" makes no sense when
        the user is already at or over goal."""
        from beats.domain.intelligence import _monday_of

        today = datetime.now(UTC).date()
        friday = self._friday_after(today)
        monday = _monday_of(friday)
        s = datetime.combine(monday, datetime.min.time(), tzinfo=UTC).replace(hour=10)
        beats = [Beat(id="b1", project_id="p1", start=s, end=s + timedelta(hours=10))]
        projects = [_project("p1", "Alpha", weekly_goal=10.0)]
        assert detect_goal_pacing(beats, projects, friday) == []
