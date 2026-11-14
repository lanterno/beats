"""The focus figures: the peak block, a beat's focus score, the day's
scores and a project's health.

Split out of `test_domain.py` at the size ceiling (CLAUDE.md § Conventions);
the shared fakes and factories are `domain_fakes.py`'s.
"""

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from beats.domain.intelligence import find_peak_block, focus_score_for_beat
from beats.domain.models import (
    Beat,
)
from beats.domain_fakes import (
    _intel_service,
    _project,
)


class TestFindPeakBlock:
    """_find_peak_block buckets beats into 12 two-hour blocks and
    returns the block with the most total minutes. The default of
    block 4 (8-10 AM) when there's no data is intentional — pin it
    so a refactor doesn't accidentally promote midnight."""

    def _svc(self):
        return _intel_service()

    @staticmethod
    def _beat_at(hour: int, minutes: int, *, day: date | None = None) -> Beat:
        d = day or date(2026, 4, 1)
        s = datetime.combine(d, datetime.min.time(), tzinfo=UTC).replace(hour=hour)
        return Beat(
            id=f"b-{hour}-{minutes}", project_id="p1", start=s, end=s + timedelta(minutes=minutes)
        )

    def test_empty_returns_default_block_4(self):
        """No beats → block 4 (8-10 AM). Pin so the default never
        becomes block 0 (midnight) — a midnight peak would mislabel
        every user's "you usually work at" sentence."""
        assert find_peak_block([]) == 4

    def test_picks_block_with_most_total_minutes(self):
        """Three beats: 30 min in block 4 (9 AM), 90 min in
        block 7 (14:00), 30 min in block 9 (18:00). Block 7 wins."""
        beats = [
            self._beat_at(9, 30),
            self._beat_at(14, 90),
            self._beat_at(18, 30),
        ]
        assert find_peak_block(beats) == 7

    def test_buckets_by_two_hour_window(self):
        """Beats at 8 AM and 9 AM both land in block 4 (hour//2);
        their minutes accumulate before being compared to other
        blocks. Pin the //2 floor."""
        beats = [
            self._beat_at(8, 30),  # block 4
            self._beat_at(9, 30),  # block 4
            self._beat_at(14, 45),  # block 7
        ]
        # Block 4: 60 min, block 7: 45 min → 4 wins
        assert find_peak_block(beats) == 4


class TestFocusScoreForBeat:
    """_focus_score_for_beat = length(0-40) + peak(0-30) + frag(0-30),
    clamped to [0, 100]. Each component is bucketed; the boundaries
    matter for downstream rendering ("deep work" vs "shallow")."""

    def _svc(self):
        return _intel_service()

    @staticmethod
    def _beat(hour: int, minutes: int, *, id_: str = "b") -> Beat:
        s = datetime(2026, 4, 1, hour, 0, tzinfo=UTC)
        return Beat(id=id_, project_id="p1", start=s, end=s + timedelta(minutes=minutes))

    def test_length_buckets_pin_each_threshold(self):
        """Length component buckets: <10→5, <25→15, <45→25, <90→35, ≥90→40."""
        cases = [(8, 5), (20, 15), (30, 25), (60, 35), (120, 40)]
        for mins, expected in cases:
            b = self._beat(9, mins)
            r = focus_score_for_beat(b, [b], 0, peak_block=4)
            assert r["components"]["length"] == expected, (
                f"{mins}min should map to length={expected}"
            )

    def test_peak_component_same_block_full_credit(self):
        """Beat in the user's peak 2-hour block → peak component=30."""
        b = self._beat(9, 60)  # 9 AM = block 4
        r = focus_score_for_beat(b, [b], 0, peak_block=4)
        assert r["components"]["peak_hours"] == 30

    def test_peak_component_adjacent_block_partial(self):
        """One block away from peak → 20."""
        b = self._beat(11, 60)  # block 5; peak=4
        r = focus_score_for_beat(b, [b], 0, peak_block=4)
        assert r["components"]["peak_hours"] == 20

    def test_peak_component_far_block_minimum(self):
        """Two or more blocks away from peak → 10."""
        b = self._beat(20, 60)  # block 10; peak=4
        r = focus_score_for_beat(b, [b], 0, peak_block=4)
        assert r["components"]["peak_hours"] == 10

    def test_no_neighbors_no_fragmentation_penalty(self):
        """A solo beat (only one on the day) has frag=30 — no
        adjacent gap to check. Pin so a refactor doesn't apply
        the penalty unconditionally."""
        b = self._beat(9, 60)
        r = focus_score_for_beat(b, [b], 0, peak_block=4)
        assert r["components"]["fragmentation"] == 30

    def test_fragmentation_penalty_when_close_to_prev(self):
        """Gap to previous beat < 5 min → frag drops by 15.
        Pattern: prev ends 9:30, this starts 9:33 → 3 min gap → penalty."""
        prev = self._beat(9, 30, id_="prev")  # 9:00-9:30
        s = datetime(2026, 4, 1, 9, 33, tzinfo=UTC)
        cur = Beat(id="cur", project_id="p1", start=s, end=s + timedelta(minutes=20))
        r = focus_score_for_beat(cur, [prev, cur], 1, peak_block=4)
        assert r["components"]["fragmentation"] == 15  # 30 - 15

    def test_fragmentation_penalty_double_when_both_neighbors_close(self):
        """Sandwiched between two close neighbors → 30 - 15 - 15 = 0.
        Pin so the two penalties stack; the floor is min=0 from the
        component itself, not a clamp."""
        prev = self._beat(9, 30, id_="prev")  # 9:00-9:30
        cur_s = datetime(2026, 4, 1, 9, 33, tzinfo=UTC)
        cur = Beat(id="cur", project_id="p1", start=cur_s, end=cur_s + timedelta(minutes=10))
        # cur ends 9:43. Next starts 9:46 → 3 min gap.
        nxt_s = datetime(2026, 4, 1, 9, 46, tzinfo=UTC)
        nxt = Beat(id="nxt", project_id="p1", start=nxt_s, end=nxt_s + timedelta(minutes=20))
        r = focus_score_for_beat(cur, [prev, cur, nxt], 1, peak_block=4)
        assert r["components"]["fragmentation"] == 0

    def test_no_penalty_when_gap_at_least_5min(self):
        """Gap of exactly 5 min → no penalty (the boundary is `< 5`)."""
        prev = self._beat(9, 30, id_="prev")  # ends 9:30
        cur_s = datetime(2026, 4, 1, 9, 35, tzinfo=UTC)  # exactly 5 min gap
        cur = Beat(id="cur", project_id="p1", start=cur_s, end=cur_s + timedelta(minutes=20))
        r = focus_score_for_beat(cur, [prev, cur], 1, peak_block=4)
        assert r["components"]["fragmentation"] == 30

    def test_total_score_sums_components(self):
        """Total = length + peak + frag, clamped to [0, 100]. A 90+
        minute beat in the peak block with no close neighbors hits
        the 100 ceiling: 40 + 30 + 30 = 100."""
        b = self._beat(9, 120)
        r = focus_score_for_beat(b, [b], 0, peak_block=4)
        assert r["score"] == 100


class TestComputeFocusScores:
    """compute_focus_scores threads three pieces together: load the
    range's beats, derive each day's peak_block from its own 30 days of
    recent activity, and score each beat in chronological order."""

    ZURICH = ZoneInfo("Europe/Zurich")

    @classmethod
    def _beat(cls, id_: str, d: date, hour: int, minute: int, minutes: int) -> Beat:
        """A beat starting at local `hour:minute` on `d` in Zurich, stored in UTC."""
        s = datetime(d.year, d.month, d.day, hour, minute, tzinfo=cls.ZURICH).astimezone(UTC)
        return Beat(id=id_, project_id="p1", start=s, end=s + timedelta(minutes=minutes))

    async def test_empty_day_returns_empty(self):
        target = date(2026, 5, 1)
        svc = _intel_service()
        assert await svc.compute_focus_scores(target, target) == []

    async def test_returns_one_row_per_beat_with_components(self):
        """One beat on the target day → one row with score and
        component dict. Pin the response shape — the UI binds to
        `score` + `components.length/peak_hours/fragmentation`."""
        target = date(2026, 5, 1)
        s = datetime.combine(target, datetime.min.time(), tzinfo=UTC).replace(hour=9)
        beats = [Beat(id="b1", project_id="p1", start=s, end=s + timedelta(minutes=60))]
        svc = _intel_service(beats=beats)
        result = await svc.compute_focus_scores(target, target)
        assert len(result) == 1
        assert result[0]["beat_id"] == "b1"
        assert "score" in result[0]
        comps = result[0]["components"]
        assert set(comps.keys()) == {"length", "peak_hours", "fragmentation"}

    async def test_sorts_beats_chronologically_for_fragmentation(self):
        """Two beats inserted out of order in the repo are still
        scored in chronological order, so fragmentation gaps are
        computed correctly. Pin so a regression that removed the
        sort would silently break frag scoring on disordered data."""
        target = date(2026, 5, 1)
        early_s = datetime.combine(target, datetime.min.time(), tzinfo=UTC).replace(hour=9)
        late_s = datetime.combine(target, datetime.min.time(), tzinfo=UTC).replace(
            hour=9, minute=33
        )
        early = Beat(
            id="early",
            project_id="p1",
            start=early_s,
            end=early_s + timedelta(minutes=30),
        )
        late = Beat(
            id="late",
            project_id="p1",
            start=late_s,
            end=late_s + timedelta(minutes=20),
        )
        # Repo returns them out of order
        svc = _intel_service(beats=[late, early])
        result = await svc.compute_focus_scores(target, target)
        # Result is sorted: early first, then late
        assert [r["beat_id"] for r in result] == ["early", "late"]
        # Late has a 3-min gap from early → frag penalty
        assert result[1]["components"]["fragmentation"] == 15

    async def test_peak_window_is_thirty_local_days(self):
        """The peak block's 30 days are local days. In Zurich (UTC+2 in
        May), two hours at 00:30 local on the window's first day, May 1, are
        stored on April 30 in UTC. They outweigh the afternoon block, so the
        peak is midnight and the afternoon session on the target day scores
        10 for peak hours. A window read by UTC date dropped them, made the
        afternoon the peak, and scored the same session 30."""
        tz = ZoneInfo("Europe/Zurich")
        target = date(2026, 5, 31)

        def at(d: date, hour: int, minute: int = 0) -> datetime:
            return datetime(d.year, d.month, d.day, hour, minute, tzinfo=tz).astimezone(UTC)

        edge = at(date(2026, 5, 1), 0, 30)
        assert edge.date() == date(2026, 4, 30)  # the UTC day before the window
        mid = at(date(2026, 5, 15), 14)
        today = at(target, 14, 30)
        beats = [
            Beat(id="edge", project_id="p1", start=edge, end=edge + timedelta(minutes=120)),
            Beat(id="mid", project_id="p1", start=mid, end=mid + timedelta(minutes=60)),
            Beat(id="today", project_id="p1", start=today, end=today + timedelta(minutes=30)),
        ]
        result = await _intel_service(beats=beats).compute_focus_scores(target, target, tz=tz)
        assert [r["beat_id"] for r in result] == ["today"]
        assert result[0]["components"]["peak_hours"] == 10

    async def test_a_week_scores_each_day_as_it_would_alone(self):
        """The project page asks for a week and the Today feed for a day; the
        two must agree on every session. Ten hours at 08:00 on August 8 sit
        in Monday's 30-day window and leave Tuesday's, so Monday's peak is
        the morning and Tuesday's the afternoon. One peak block shared by the
        whole week would score both the same."""
        monday = date(2026, 9, 7)
        beats = [self._beat("history", date(2026, 8, 8), 8, 0, 600)]
        for offset in range(7):
            d = monday + timedelta(days=offset)
            beats.append(self._beat(f"pm-{offset}", d, 14, 0, 60))
            beats.append(self._beat(f"pm2-{offset}", d, 15, 3, 25))
        svc = _intel_service(beats=beats)

        week = await svc.compute_focus_scores(monday, monday + timedelta(days=6), tz=self.ZURICH)
        days = []
        for offset in range(7):
            d = monday + timedelta(days=offset)
            days.extend(await svc.compute_focus_scores(d, d, tz=self.ZURICH))

        assert week == days
        peak = {r["beat_id"]: r["components"]["peak_hours"] for r in week}
        assert (peak["pm-0"], peak["pm-1"]) == (10, 30)

    async def test_fragmentation_stops_at_midnight(self):
        """Three minutes between sessions is a fragmentation penalty within a
        day, and none across local midnight: each day is scored on its own."""
        monday = date(2026, 9, 7)
        tuesday, wednesday = monday + timedelta(days=1), monday + timedelta(days=2)
        beats = [
            self._beat("late", monday, 23, 28, 30),  # ends 23:58
            self._beat("early", tuesday, 0, 1, 30),
            self._beat("first", wednesday, 10, 0, 30),  # ends 10:30
            self._beat("second", wednesday, 10, 33, 30),
        ]
        result = await _intel_service(beats=beats).compute_focus_scores(
            monday, monday + timedelta(days=6), tz=self.ZURICH
        )
        frag = {r["beat_id"]: r["components"]["fragmentation"] for r in result}
        assert frag == {"late": 30, "early": 30, "first": 15, "second": 15}

    async def test_a_week_is_bucketed_by_local_day_at_both_ends(self):
        """Zurich is ahead of UTC, so 00:30 on a Monday is stored under the
        Sunday before. The week's own Monday-morning session belongs to it;
        the next Monday's, stored under this week's Sunday, does not."""
        monday = date(2026, 9, 7)
        next_monday = monday + timedelta(days=7)
        first = self._beat("first", monday, 0, 30, 30)
        last = self._beat("last", next_monday - timedelta(days=1), 23, 0, 30)
        after = self._beat("after", next_monday, 0, 30, 30)
        assert first.start.date() == monday - timedelta(days=1)
        assert after.start.date() == next_monday - timedelta(days=1)

        result = await _intel_service(beats=[after, last, first]).compute_focus_scores(
            monday, monday + timedelta(days=6), tz=self.ZURICH
        )
        assert [r["beat_id"] for r in result] == ["first", "last"]

    async def test_a_week_behind_utc_keeps_its_sunday_evening(self):
        """New York is behind UTC, so 23:30 on a Sunday is stored under the
        Monday after the week. It belongs to the week; 00:30 on that Monday,
        stored on the same UTC day, does not."""
        tz = ZoneInfo("America/New_York")
        monday = date(2026, 9, 7)
        sunday, next_monday = monday + timedelta(days=6), monday + timedelta(days=7)

        def beat(id_: str, d: date, hour: int, minute: int) -> Beat:
            s = datetime(d.year, d.month, d.day, hour, minute, tzinfo=tz).astimezone(UTC)
            return Beat(id=id_, project_id="p1", start=s, end=s + timedelta(minutes=20))

        late = beat("late", sunday, 23, 30)
        after = beat("after", next_monday, 0, 30)
        assert late.start.date() == after.start.date() == next_monday

        result = await _intel_service(beats=[after, late]).compute_focus_scores(
            monday, sunday, tz=tz
        )
        assert [r["beat_id"] for r in result] == ["late"]

    async def test_a_week_is_ordered_by_day_then_start(self):
        monday = date(2026, 9, 7)
        tuesday, wednesday = monday + timedelta(days=1), monday + timedelta(days=2)
        beats = [
            self._beat("wed-9", wednesday, 9, 0, 30),
            self._beat("mon-15", monday, 15, 0, 30),
            self._beat("mon-9", monday, 9, 0, 30),
            self._beat("tue-12", tuesday, 12, 0, 30),
        ]
        result = await _intel_service(beats=beats).compute_focus_scores(
            monday, monday + timedelta(days=6), tz=self.ZURICH
        )
        assert [r["beat_id"] for r in result] == ["mon-9", "mon-15", "tue-12", "wed-9"]


class TestGetProjectHealth:
    """get_project_health surfaces stale projects and downward
    weekly trends. Two alert paths:
      - No activity in ≥14 days despite a weekly goal
      - 3 consecutive weeks of declining hours

    Risk: silent regressions here would let a fading project go
    unnoticed for weeks before the user picks up on it."""

    @staticmethod
    def _at(d: date, hour: int) -> datetime:
        return datetime.combine(d, datetime.min.time(), tzinfo=UTC).replace(hour=hour)

    async def test_empty_projects_returns_empty(self):
        svc = _intel_service()
        assert await svc.get_project_health() == []

    async def test_days_since_last_none_when_no_beats(self):
        """A project with no recent beats has days_since_last=None
        (not 0, not "never"). Pin so the UI can branch on null
        rather than parse a sentinel."""
        projects = [_project("p1", "Cold")]
        svc = _intel_service(projects=projects)
        result = await svc.get_project_health()
        assert len(result) == 1
        assert result[0]["days_since_last"] is None

    async def test_stale_with_goal_emits_alert(self):
        """Last beat 14+ days ago AND project has a weekly goal →
        alert. Below the threshold, no alert. Pin both sides so
        a reminder can't accidentally fire on a fresh project."""
        today = datetime.now(UTC).date()
        old = today - timedelta(days=20)
        beats = [
            Beat(
                id="b1",
                project_id="p1",
                start=self._at(old, 9),
                end=self._at(old, 11),
            )
        ]
        projects = [_project("p1", "Stale", weekly_goal=5.0)]
        svc = _intel_service(beats=beats, projects=projects)
        result = await svc.get_project_health()
        assert result[0]["days_since_last"] == 20
        assert result[0]["alert"] is not None
        assert "20 days" in result[0]["alert"]

    async def test_stale_without_goal_no_alert(self):
        """No weekly goal → no stale alert even after a long gap.
        A casual project the user works on intermittently shouldn't
        nag."""
        today = datetime.now(UTC).date()
        old = today - timedelta(days=20)
        beats = [
            Beat(
                id="b1",
                project_id="p1",
                start=self._at(old, 9),
                end=self._at(old, 10),
            )
        ]
        projects = [_project("p1", "Casual", weekly_goal=None)]
        svc = _intel_service(beats=beats, projects=projects)
        result = await svc.get_project_health()
        assert result[0]["alert"] is None

    async def test_alerted_projects_sorted_first(self):
        """Sort key: (alert is None, project_name). Projects WITH
        alerts come first; within the alerted/clean groups, sorted
        alphabetically. Pin so the UI always shows the urgent
        items at the top of the list."""
        today = datetime.now(UTC).date()
        # Stale beat must be inside the 4-week query window
        # (today - 28 days) but past the 14-day stale threshold.
        old = today - timedelta(days=20)
        recent = today - timedelta(days=2)
        beats = [
            Beat(
                id="b_old",
                project_id="p1",
                start=self._at(old, 9),
                end=self._at(old, 10),
            ),
            Beat(
                id="b_recent",
                project_id="p2",
                start=self._at(recent, 9),
                end=self._at(recent, 10),
            ),
        ]
        projects = [
            _project("p2", "Beta", weekly_goal=5.0),  # active, no alert
            _project("p1", "Alpha", weekly_goal=5.0),  # stale, alert
        ]
        svc = _intel_service(beats=beats, projects=projects)
        result = await svc.get_project_health()
        # Alpha (alerted) first, Beta (no alert) second
        assert [r["project_name"] for r in result] == ["Alpha", "Beta"]
        assert result[0]["alert"] is not None
        assert result[1]["alert"] is None


# Domain Services — TimerService, BeatService, ProjectService
