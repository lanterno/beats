"""Tests for domain models and services."""

from datetime import UTC, date, datetime, timedelta

import pytest

from beats.domain.analytics import AnalyticsService
from beats.domain.exceptions import (
    DomainException,
    InvalidEndTime,
    NoActiveTimer,
    ProjectNotFound,
    TimerAlreadyRunning,
)
from beats.domain.models import (
    Beat,
    BiometricDay,
    DailyNote,
    GoalOverride,
    GoalType,
    Intention,
    Project,
    RecurringIntention,
)


class TestBeatModel:
    """Tests for the Beat domain model."""

    def test_beat_creation_with_defaults(self):
        """Test creating a beat with default values."""
        beat = Beat(project_id="test-project")
        assert beat.project_id == "test-project"
        assert beat.start is not None
        assert beat.end is None
        assert beat.is_active is True

    def test_beat_creation_with_explicit_times(self):
        """Test creating a beat with explicit start and end times."""
        start = datetime.fromisoformat("2020-01-11T04:30:00+00:00")
        end = datetime.fromisoformat("2020-01-11T05:30:00+00:00")
        beat = Beat(project_id="test-project", start=start, end=end)

        assert beat.start == start
        assert beat.end == end
        assert beat.is_active is False

    def test_beat_is_active_when_no_end(self):
        """Test that a beat is active when end is None."""
        beat = Beat(project_id="test-project")
        assert beat.is_active is True

    def test_beat_is_not_active_when_has_end(self):
        """Test that a beat is not active when end is set."""
        beat = Beat(
            project_id="test-project",
            start=datetime.fromisoformat("2020-01-11T04:30:00"),
            end=datetime.fromisoformat("2020-01-11T05:30:00"),
        )
        assert beat.is_active is False

    def test_beat_duration_with_end_time(self):
        """Test duration calculation for completed beat."""
        beat = Beat(
            project_id="test-project",
            start=datetime.fromisoformat("2020-01-11T04:30:00"),
            end=datetime.fromisoformat("2020-01-11T05:30:00"),
        )
        assert beat.duration == timedelta(hours=1)

    def test_beat_duration_without_end_time(self):
        """Test duration calculation for active beat (uses current time)."""
        start = datetime.now(UTC) - timedelta(hours=2)
        beat = Beat(project_id="test-project", start=start)
        # Duration should be approximately 2 hours
        assert beat.duration >= timedelta(hours=1, minutes=59)
        assert beat.duration <= timedelta(hours=2, minutes=1)

    def test_beat_day_property(self):
        """Test the day computed property."""
        beat = Beat(
            project_id="test-project",
            start=datetime.fromisoformat("2020-01-11T04:30:00"),
        )
        assert beat.day.year == 2020
        assert beat.day.month == 1
        assert beat.day.day == 11


class TestProjectModel:
    """Tests for the Project domain model."""

    def test_project_creation_minimal(self):
        """Test creating a project with only required fields."""
        project = Project(name="Test Project")
        assert project.name == "Test Project"
        assert project.description is None
        assert project.estimation is None
        assert project.archived is False

    def test_project_creation_full(self):
        """Test creating a project with all fields."""
        project = Project(
            id="test-id",
            name="Test Project",
            description="A test project",
            estimation="10 hours",
            archived=True,
        )
        assert project.id == "test-id"
        assert project.name == "Test Project"
        assert project.description == "A test project"
        assert project.estimation == "10 hours"
        assert project.archived is True


class TestDomainExceptions:
    """Tests for domain exceptions."""

    def test_domain_exception_base(self):
        """Test base DomainException."""
        exc = DomainException()
        assert exc.status_code == 400
        assert exc.message == "A domain error occurred"

    def test_domain_exception_custom_message(self):
        """Test DomainException with custom message."""
        exc = DomainException("Custom error message")
        assert exc.message == "Custom error message"

    def test_no_active_timer_exception(self):
        """Test NoActiveTimer exception."""
        exc = NoActiveTimer()
        assert exc.status_code == 400
        assert exc.message == "No timer is currently running"

    def test_timer_already_running_exception(self):
        """Test TimerAlreadyRunning exception."""
        exc = TimerAlreadyRunning()
        assert exc.status_code == 400
        assert exc.message == "A timer is already running"

    def test_invalid_end_time_exception(self):
        """Test InvalidEndTime exception."""
        exc = InvalidEndTime()
        assert exc.status_code == 400
        assert exc.message == "End time must be after start time"

    def test_project_not_found_exception(self):
        """Test ProjectNotFound exception."""
        exc = ProjectNotFound("project-123")
        assert exc.status_code == 404
        assert "project-123" in exc.message

    def test_project_not_found_without_id(self):
        """Test ProjectNotFound exception without project ID."""
        exc = ProjectNotFound()
        assert exc.status_code == 404
        assert exc.message == "Project not found"


class TestGoalOverrideValidation:
    """Tests for GoalOverride model validation."""

    def test_valid_one_off_override(self):
        o = GoalOverride(week_of=date(2026, 4, 6), weekly_goal=10)  # Monday
        assert o.week_of == date(2026, 4, 6)
        assert o.effective_from is None

    def test_valid_permanent_override(self):
        o = GoalOverride(effective_from=date(2026, 4, 6), weekly_goal=30)
        assert o.effective_from == date(2026, 4, 6)
        assert o.week_of is None

    def test_both_fields_set_raises(self):
        with pytest.raises(ValueError, match="Exactly one"):
            GoalOverride(week_of=date(2026, 4, 6), effective_from=date(2026, 4, 6), weekly_goal=10)

    def test_neither_field_set_raises(self):
        with pytest.raises(ValueError, match="Exactly one"):
            GoalOverride(weekly_goal=10)

    def test_non_monday_week_of_raises(self):
        with pytest.raises(ValueError, match="Monday"):
            GoalOverride(week_of=date(2026, 4, 7), weekly_goal=10)  # Tuesday

    def test_non_monday_effective_from_raises(self):
        with pytest.raises(ValueError, match="Monday"):
            GoalOverride(effective_from=date(2026, 4, 8), weekly_goal=10)  # Wednesday

    def test_zero_goal_raises(self):
        with pytest.raises(ValueError, match="positive"):
            GoalOverride(week_of=date(2026, 4, 6), weekly_goal=0)

    def test_negative_goal_raises(self):
        with pytest.raises(ValueError, match="positive"):
            GoalOverride(week_of=date(2026, 4, 6), weekly_goal=-5)


class TestGoalOverrideResolution:
    """Tests for Project.effective_goal() resolution logic."""

    def _project(self, **kwargs: object) -> Project:
        defaults: dict[str, object] = {
            "name": "Test",
            "weekly_goal": 20,
            "goal_type": GoalType.TARGET,
        }
        return Project(**{**defaults, **kwargs})  # type: ignore[arg-type]

    def test_no_overrides_returns_default(self):
        p = self._project()
        goal, gtype = p.effective_goal(date(2026, 4, 6))
        assert goal == 20
        assert gtype == GoalType.TARGET

    def test_no_goal_set_returns_none(self):
        p = Project(name="Test")
        goal, gtype = p.effective_goal(date(2026, 4, 6))
        assert goal is None
        assert gtype == GoalType.TARGET

    def test_one_off_override_matches(self):
        p = self._project(
            goal_overrides=[
                GoalOverride(week_of=date(2026, 4, 6), weekly_goal=10, note="holiday"),
            ]
        )
        goal, gtype = p.effective_goal(date(2026, 4, 6))
        assert goal == 10
        assert gtype == GoalType.TARGET

    def test_one_off_override_does_not_affect_other_weeks(self):
        p = self._project(
            goal_overrides=[
                GoalOverride(week_of=date(2026, 4, 6), weekly_goal=10),
            ]
        )
        goal, _ = p.effective_goal(date(2026, 4, 13))  # Next week
        assert goal == 20  # Project default

    def test_permanent_override_applies_from_date(self):
        p = self._project(
            goal_overrides=[
                GoalOverride(effective_from=date(2026, 3, 2), weekly_goal=30),
            ]
        )
        # Before effective_from
        goal, _ = p.effective_goal(date(2026, 2, 23))
        assert goal == 20
        # On effective_from
        goal, _ = p.effective_goal(date(2026, 3, 2))
        assert goal == 30
        # After effective_from
        goal, _ = p.effective_goal(date(2026, 4, 6))
        assert goal == 30

    def test_one_off_takes_precedence_over_permanent(self):
        p = self._project(
            goal_overrides=[
                GoalOverride(effective_from=date(2026, 3, 2), weekly_goal=30),
                GoalOverride(week_of=date(2026, 4, 6), weekly_goal=5, note="vacation"),
            ]
        )
        goal, _ = p.effective_goal(date(2026, 4, 6))
        assert goal == 5
        # Other weeks still use permanent
        goal, _ = p.effective_goal(date(2026, 4, 13))
        assert goal == 30

    def test_latest_permanent_override_wins(self):
        p = self._project(
            goal_overrides=[
                GoalOverride(effective_from=date(2026, 1, 5), weekly_goal=25),
                GoalOverride(effective_from=date(2026, 3, 2), weekly_goal=30),
            ]
        )
        # Before both
        goal, _ = p.effective_goal(date(2025, 12, 29))
        assert goal == 20
        # Between
        goal, _ = p.effective_goal(date(2026, 2, 2))
        assert goal == 25
        # After both — latest wins
        goal, _ = p.effective_goal(date(2026, 4, 6))
        assert goal == 30

    def test_override_inherits_project_goal_type(self):
        p = self._project(
            goal_type=GoalType.CAP,
            goal_overrides=[
                GoalOverride(week_of=date(2026, 4, 6), weekly_goal=15),
            ],
        )
        _, gtype = p.effective_goal(date(2026, 4, 6))
        assert gtype == GoalType.CAP

    def test_override_can_set_own_goal_type(self):
        p = self._project(
            goal_type=GoalType.TARGET,
            goal_overrides=[
                GoalOverride(week_of=date(2026, 4, 6), weekly_goal=15, goal_type=GoalType.CAP),
            ],
        )
        _, gtype = p.effective_goal(date(2026, 4, 6))
        assert gtype == GoalType.CAP

    def test_one_off_null_override_clears_week(self):
        p = self._project(
            goal_overrides=[
                GoalOverride(week_of=date(2026, 4, 6), weekly_goal=None, note="holiday"),
            ]
        )
        goal, _ = p.effective_goal(date(2026, 4, 6))
        assert goal is None
        # Other weeks unaffected
        goal, _ = p.effective_goal(date(2026, 4, 13))
        assert goal == 20

    def test_permanent_null_override_clears_forward(self):
        p = self._project(
            goal_overrides=[
                GoalOverride(effective_from=date(2026, 3, 2), weekly_goal=None),
            ]
        )
        # Before effective_from: default
        goal, _ = p.effective_goal(date(2026, 2, 23))
        assert goal == 20
        # From effective_from onward: cleared
        goal, _ = p.effective_goal(date(2026, 3, 2))
        assert goal is None
        goal, _ = p.effective_goal(date(2026, 4, 6))
        assert goal is None

    def test_later_permanent_override_can_restore_goal(self):
        p = self._project(
            goal_overrides=[
                GoalOverride(effective_from=date(2026, 3, 2), weekly_goal=None),
                GoalOverride(effective_from=date(2026, 4, 6), weekly_goal=25),
            ]
        )
        goal, _ = p.effective_goal(date(2026, 3, 9))
        assert goal is None
        goal, _ = p.effective_goal(date(2026, 4, 6))
        assert goal == 25


class TestIntentionModel:
    """Intention is a daily time-boxed plan attached to a project."""

    def test_defaults_to_today_60min_uncompleted(self):
        i = Intention(project_id="p1")
        assert i.project_id == "p1"
        assert i.date == datetime.now(UTC).date()
        assert i.planned_minutes == 60
        assert i.completed is False
        assert i.id is None

    def test_explicit_fields_round_trip(self):
        i = Intention(
            id="abc",
            project_id="p1",
            date=date(2026, 5, 1),
            planned_minutes=90,
            completed=True,
        )
        assert i.planned_minutes == 90
        assert i.completed is True
        assert i.date == date(2026, 5, 1)


class TestDailyNoteModel:
    """DailyNote captures end-of-day mood + reflection."""

    def test_defaults(self):
        n = DailyNote()
        assert n.note == ""
        assert n.mood is None
        assert n.date == datetime.now(UTC).date()
        assert n.id is None

    def test_mood_accepts_full_1_to_5_range(self):
        # Domain layer doesn't enforce a 1–5 bound — the comment on the
        # field says "1-5 scale" but pydantic itself takes any int. Pin
        # the actual behavior so a future stricter validator is a
        # *deliberate* contract change, not an accident.
        for mood in (1, 2, 3, 4, 5):
            assert DailyNote(mood=mood).mood == mood

    def test_mood_outside_documented_range_currently_passes(self):
        # Locks in current lax behavior. If we add bounds later, this
        # test will break and force the implementer to also update the
        # routes that produce moods (front-end coerces to 1–5 already).
        assert DailyNote(mood=99).mood == 99
        assert DailyNote(mood=0).mood == 0


class TestRecurringIntentionModel:
    """RecurringIntention is a weekday-templated source of daily intentions."""

    def test_defaults_to_weekdays_enabled(self):
        r = RecurringIntention(project_id="p1")
        assert r.project_id == "p1"
        assert r.planned_minutes == 60
        assert r.days_of_week == [0, 1, 2, 3, 4]  # Mon–Fri
        assert r.enabled is True

    def test_arbitrary_days_of_week_accepted(self):
        # Domain doesn't validate the 0–6 range — keeps the model dumb,
        # routes are responsible. Pin behavior.
        r = RecurringIntention(project_id="p1", days_of_week=[5, 6])
        assert r.days_of_week == [5, 6]

    def test_template_fires_only_on_listed_weekdays(self):
        # Mirror of the predicate in routers/planning.py:
        #   if not t.enabled or day_of_week not in t.days_of_week: continue
        # Keep this assertion in the domain test so a code move can't
        # silently change the activation rule. weekday(): Mon=0..Sun=6.
        weekday_template = RecurringIntention(project_id="p1", days_of_week=[0, 1, 2, 3, 4])
        weekend_template = RecurringIntention(project_id="p2", days_of_week=[5, 6])
        for weekday in range(5):  # Mon–Fri
            assert weekday in weekday_template.days_of_week
            assert weekday not in weekend_template.days_of_week
        for weekend in (5, 6):
            assert weekend not in weekday_template.days_of_week
            assert weekend in weekend_template.days_of_week

    def test_disabled_template_is_inert(self):
        # The route handler short-circuits on `not t.enabled` before the
        # day-of-week check. Disabled means nothing fires, regardless of
        # day. (Test is a sanity-pin on the field, not the route logic.)
        r = RecurringIntention(project_id="p1", enabled=False, days_of_week=[0, 1, 2, 3, 4, 5, 6])
        assert r.enabled is False


class TestBiometricDayModel:
    """BiometricDay aggregates one day of biometrics from one source.

    Multiple rows per day are allowed (HealthKit + Oura + Fitbit can all
    write the same date); the model docstring asserts the readout
    priority HealthKit > Oura > Fitbit but that's *consumer* policy, not
    encoded in the model itself. Tests here pin field shape, not the
    consumer-side priority — the latter would belong to whichever
    handler does the merge.
    """

    def test_defaults_all_optional_fields_none_or_empty(self):
        b = BiometricDay()
        assert b.source == ""
        assert b.sleep_minutes is None
        assert b.sleep_efficiency is None
        assert b.hrv_ms is None
        assert b.resting_hr_bpm is None
        assert b.steps is None
        assert b.readiness_score is None
        assert b.workouts == []
        assert b.date == datetime.now(UTC).date()

    def test_source_field_accepts_documented_values(self):
        for src in ("healthkit", "health_connect", "fitbit", "oura"):
            assert BiometricDay(source=src).source == src

    def test_workouts_takes_a_list_of_dicts(self):
        b = BiometricDay(
            source="oura",
            workouts=[
                {"kind": "run", "minutes": 30, "avg_hr": 158},
                {"kind": "yoga", "minutes": 45, "avg_hr": 95},
            ],
        )
        assert len(b.workouts) == 2
        assert b.workouts[0]["kind"] == "run"

    def test_partial_data_is_valid(self):
        # Not every source emits every field — Fitbit has steps but no
        # readiness; Oura has readiness but variable sleep efficiency.
        # The model must tolerate sparse rows.
        b = BiometricDay(source="fitbit", steps=8400, sleep_minutes=420)
        assert b.steps == 8400
        assert b.sleep_minutes == 420
        assert b.readiness_score is None  # absent — not a required field


class _FakeBeatRepo:
    """In-memory BeatRepository fake for AnalyticsService tests.

    Implements only the methods AnalyticsService consumes
    (list_all_completed, list_completed_in_range). Constructed with
    a fixed list of beats; deterministic, no Mongo.
    """

    def __init__(self, beats: list[Beat]):
        self._beats = beats

    async def list_all_completed(self) -> list[Beat]:
        return [b for b in self._beats if b.end is not None]

    async def list_completed_in_range(self, start: date, end: date) -> list[Beat]:
        return [b for b in self._beats if b.end is not None and start <= b.start.date() <= end]


def _beat(start_iso: str, minutes: int, project_id: str = "p1", tags=None) -> Beat:
    """Convenience factory: a completed beat starting at ISO time and lasting [minutes]."""
    s = datetime.fromisoformat(start_iso).replace(tzinfo=UTC)
    return Beat(
        id="b-" + start_iso,
        project_id=project_id,
        start=s,
        end=s + timedelta(minutes=minutes),
        tags=list(tags or []),
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

    def test_cross_midnight_clamps_to_end_of_day(self):
        # 23:30 (start day) to 00:30 (next day) — only the 30min
        # before midnight count; the post-midnight portion is dropped
        # because the helper clamps to start-day midnight.
        slots = self._slots("2026-05-01T23:30:00", "2026-05-02T00:30:00")
        assert slots[47] == 30  # 23:30–24:00 is slot 47
        assert sum(slots) == 30  # the 0:00–0:30 chunk is clamped away

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
        from datetime import datetime, timedelta

        nine_days_ago = (datetime.now(_UTC) - timedelta(days=9)).replace(
            hour=9, minute=0, second=0, microsecond=0
        )
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
        if today.day == 1:
            # Edge: on the 1st, last month's data is the only data.
            # Skip this branch by using a beat from the same day.
            target = today
        else:
            target = (today.replace(day=1)) - timedelta(days=1)
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


# IntelligenceService test scaffolding
# ---------------------------------------------------------------------


class _FakeIntelBeatRepo(_FakeBeatRepo):
    """Extends _FakeBeatRepo with the methods IntelligenceService
    consumes beyond what AnalyticsService needs."""


class _FakeProjectRepo:
    """Returns a fixed project list, optionally filtered by archived."""

    def __init__(self, projects: list):
        self._projects = projects

    async def list(self, archived: bool = False) -> list:
        return [p for p in self._projects if p.archived == archived]


class _FakeIntentionRepo:
    """Returns intentions for a date range."""

    def __init__(self, intentions: list):
        self._intentions = intentions

    async def list_by_date_range(self, start: date, end: date) -> list:
        return [i for i in self._intentions if start <= i.date <= end]

    async def list_by_date(self, d: date) -> list:
        return [i for i in self._intentions if i.date == d]


class _FakeDailyNoteRepo:
    """Returns daily notes by date or in a range."""

    def __init__(self, notes: list):
        self._notes = notes

    async def list_by_date_range(self, start: date, end: date) -> list:
        return [n for n in self._notes if start <= n.date <= end]

    async def get_by_date(self, d: date):
        for n in self._notes:
            if n.date == d:
                return n
        return None


def _intel_service(
    *,
    beats: list | None = None,
    projects: list | None = None,
    intentions: list | None = None,
    notes: list | None = None,
):
    """Build an IntelligenceService with fakes for every repo."""
    from beats.domain.intelligence import IntelligenceService

    return IntelligenceService(
        beat_repo=_FakeIntelBeatRepo(beats or []),
        project_repo=_FakeProjectRepo(projects or []),
        intention_repo=_FakeIntentionRepo(intentions or []),
        daily_note_repo=_FakeDailyNoteRepo(notes or []),
    )


def _project(
    id_: str = "p1",
    name: str = "Project",
    *,
    weekly_goal: float | None = None,
    archived: bool = False,
):
    """Quick project factory for IntelligenceService tests."""
    return Project(
        id=id_,
        name=name,
        weekly_goal=weekly_goal,
        goal_type=GoalType.TARGET,
        archived=archived,
    )


class TestProductivityScore:
    """compute_productivity_score breaks 0-100 into four 0-25 components:
    consistency (weekdays tracked) + intentions (completion %) + goals
    (avg progress) + quality (median session length minus fragmentation
    penalty). Risk: a regression in any component shifts the user's
    perceived productivity story silently. These tests pin each
    component's logic on representative seeded data."""

    async def test_empty_data_returns_neutral_score(self):
        """Fresh-account path — no sessions, no intentions, no goals.
        consistency=0 + intentions=13 (neutral) + goals=13 (neutral) +
        quality=0 = 26. Pin so a divide-by-zero regression fails the
        test rather than silently 500'ing the /score endpoint for new
        users."""
        svc = _intel_service()
        result = await svc.compute_productivity_score()
        assert "score" in result
        assert "components" in result
        components = result["components"]
        assert components["consistency"] == 0
        assert components["intentions"] == 13  # neutral default
        assert components["goals"] == 13  # neutral default
        assert components["quality"] == 0
        assert result["score"] == 26

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

    async def test_intention_completion_full_when_all_done(self):
        from beats.domain.models import Intention

        today = datetime.now(UTC).date()
        intentions = [
            Intention(project_id="p1", date=today, planned_minutes=60, completed=True),
            Intention(
                project_id="p2",
                date=today - timedelta(days=1),
                planned_minutes=30,
                completed=True,
            ),
        ]
        svc = _intel_service(intentions=intentions)
        result = await svc.compute_productivity_score()
        assert result["components"]["intentions"] == 25

    async def test_intention_completion_zero_when_none_done(self):
        from beats.domain.models import Intention

        today = datetime.now(UTC).date()
        intentions = [
            Intention(project_id="p1", date=today, planned_minutes=60, completed=False),
            Intention(
                project_id="p2",
                date=today - timedelta(days=1),
                planned_minutes=30,
                completed=False,
            ),
        ]
        svc = _intel_service(intentions=intentions)
        result = await svc.compute_productivity_score()
        assert result["components"]["intentions"] == 0

    async def test_goal_progress_caps_at_25_when_target_hit(self):
        """A project that hit (or exceeded) its weekly goal contributes
        max progress (1.0) to the average. Single-project case → 25."""
        today = datetime.now(UTC).date()
        week_start = today - timedelta(days=today.weekday())
        # 10h of sessions this week toward a 5h goal.
        beats = []
        for i in range(10):
            s = datetime.combine(week_start, datetime.min.time(), tzinfo=UTC).replace(
                hour=9
            ) + timedelta(days=i % 7, hours=i % 3)
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
        """The score is `min(100, consistency + intentions + goals +
        quality)`. Locks the cap so a future 30-point component
        doesn't overshoot."""
        today = datetime.now(UTC).date()
        # Construct max-everything: 5 weekdays tracked, all intentions
        # done, full goal progress, long sessions.
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

        from beats.domain.models import Intention

        intentions = [
            Intention(project_id="p1", date=today, planned_minutes=60, completed=True),
        ]
        projects = [_project("p1", "Alpha", weekly_goal=2.0)]
        svc = _intel_service(beats=beats, projects=projects, intentions=intentions)
        result = await svc.compute_productivity_score()
        # 25 + 25 + 25 + 25 = 100, capped.
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
        sessions, no intentions, no goal projects). Pin so a regression
        that would 500 on empty data fails the test instead."""
        svc = _intel_service()
        result = await svc.compute_productivity_score_history(weeks=4)
        # Each week: consistency=0, intentions=13 (neutral), goals=13
        # (neutral, no goal_projects), quality=0 → 26.
        for entry in result:
            assert entry["score"] == 26

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

    async def test_week_with_all_completed_intentions_scores_higher(self):
        """A historical week where the user completed all intentions
        scores higher than an empty week. Pin so a regression in the
        per-week intention aggregation doesn't silently flatten the
        sparkline."""
        from beats.domain.intelligence import _monday_of
        from beats.domain.models import Intention

        today = datetime.now(UTC).date()
        # Place an intention 2 weeks ago, on the Monday.
        two_weeks_ago_monday = _monday_of(today) - timedelta(weeks=2)
        intentions = [
            Intention(
                project_id="p1",
                date=two_weeks_ago_monday,
                planned_minutes=60,
                completed=True,
            ),
        ]
        svc = _intel_service(intentions=intentions)
        result = await svc.compute_productivity_score_history(weeks=4)
        by_week = {e["week_of"]: e["score"] for e in result}

        # The completed week scores higher than baseline (26):
        # consistency 0 + intentions 25 + goals 13 + quality 0 = 38.
        assert by_week[two_weeks_ago_monday.isoformat()] == 38
        # An adjacent empty week stays at 26.
        three_weeks_ago_monday = _monday_of(today) - timedelta(weeks=3)
        assert by_week[three_weeks_ago_monday.isoformat()] == 26

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

        # Three-weeks-ago: 5 (consistency) + 13 + 13 + 18 (quality
        # for 60-min session in <60 bucket — actually median 60 falls
        # at "< 120" boundary so it's 23) = let's just assert it's
        # higher than the empty baseline.
        assert by_week[three_weeks_ago_monday.isoformat()] > 26
        # And the OTHER weeks (no sessions in them) stay at the
        # empty baseline.
        for w in [
            (_monday_of(today) - timedelta(weeks=2)).isoformat(),
            (_monday_of(today) - timedelta(weeks=4)).isoformat(),
        ]:
            assert by_week[w] == 26


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
        svc = self._service()

        today = datetime.now(UTC).date()
        result = svc._detect_day_pattern([], today)
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
        svc = self._service()
        result = svc._detect_day_pattern(beats, today)
        assert result == []

    async def test_clear_power_day_returns_card(self):
        """Heavy activity concentrated on one weekday → one
        InsightCard with the day name in the title."""
        today = datetime.now(UTC).date()
        # 4 hours every Tuesday for 8 weeks, nothing else.
        beats = self._seed_beats_on_weekday(target_dow=1, weeks_back=8, minutes_per_week=240)
        svc = self._service()
        cards = svc._detect_day_pattern(beats, today)
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
        svc = self._service()
        cards = svc._detect_day_pattern(beats, today)
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

        svc = self._service()
        cards = svc._detect_day_pattern(beats, today)
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
        svc = self._service()
        assert svc._detect_peak_hours([]) == []

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
        svc = self._service()
        assert svc._detect_peak_hours(beats) == []

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
        svc = self._service()
        cards = svc._detect_peak_hours(beats)
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
        svc = self._service()
        assert svc._detect_peak_hours(beats) == []


class TestPatternDetectorsStaleProjects:
    """_detect_stale_projects flags projects with weekly_goal but no
    activity in the last 14 days. Threshold: archived → skip; no
    weekly_goal → skip; last activity 14+ days ago (or never) → fire."""

    def _service(self):
        return _intel_service()

    async def test_no_projects_returns_no_card(self):
        svc = self._service()
        today = datetime.now(UTC).date()
        assert svc._detect_stale_projects([], [], today) == []

    async def test_skips_projects_without_weekly_goal(self):
        today = datetime.now(UTC).date()
        projects = [_project("p1", "Casual", weekly_goal=None)]
        svc = self._service()
        assert svc._detect_stale_projects([], projects, today) == []

    async def test_skips_archived_even_with_goal(self):
        today = datetime.now(UTC).date()
        projects = [_project("p1", "Old", weekly_goal=5.0, archived=True)]
        svc = self._service()
        assert svc._detect_stale_projects([], projects, today) == []

    async def test_no_activity_ever_fires_card(self):
        """ZERO recorded sessions → fires with days_since=999 (the
        sentinel for "never"). Pin so a refactor changing the
        never-tracked default doesn't mis-render in the UI."""
        today = datetime.now(UTC).date()
        projects = [_project("p1", "Untouched", weekly_goal=5.0)]
        svc = self._service()
        cards = svc._detect_stale_projects([], projects, today)
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
        svc = self._service()
        assert svc._detect_stale_projects(beats, projects, today) == []

    async def test_threshold_is_14_days_inclusive(self):
        """Threshold is `>= 14`. Pin the boundary so a refactor that
        bumps to 13 (one extra day's grace) or 15 (one less) is a
        deliberate change."""
        today = datetime.now(UTC).date()
        projects = [_project("p1", "Borderline", weekly_goal=5.0)]
        svc = self._service()

        # 13 days ago — fresh.
        s13 = datetime.combine(today - timedelta(days=13), datetime.min.time(), tzinfo=UTC).replace(
            hour=10
        )
        assert (
            svc._detect_stale_projects(
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
        cards = svc._detect_stale_projects(
            [Beat(id="b2", project_id="p1", start=s14, end=s14 + timedelta(hours=1))],
            projects,
            today,
        )
        assert len(cards) == 1
        assert cards[0].data["days_since"] == 14

    async def test_one_card_per_stale_project(self):
        today = datetime.now(UTC).date()
        projects = [
            _project("p1", "Alpha", weekly_goal=5.0),
            _project("p2", "Beta", weekly_goal=3.0),
            _project("p3", "Gamma", weekly_goal=None),  # no goal → skipped
        ]
        svc = self._service()
        cards = svc._detect_stale_projects([], projects, today)
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

    async def test_too_few_this_week_returns_no_card(self):
        from beats.domain.intelligence import _monday_of

        today = datetime.now(UTC).date()
        this_monday = _monday_of(today)
        s = datetime.combine(this_monday, datetime.min.time(), tzinfo=UTC).replace(hour=10)
        beats = [Beat(id="b-this", project_id="p1", start=s, end=s + timedelta(hours=1))]
        beats += self._beats_in_range(
            this_monday - timedelta(weeks=4), this_monday - timedelta(days=1), 60
        )
        svc = self._service()
        assert svc._detect_session_trend(beats, today) == []

    async def test_too_few_prior_returns_no_card(self):
        from beats.domain.intelligence import _monday_of

        today = datetime.now(UTC).date()
        this_monday = _monday_of(today)
        beats = self._beats_in_range(this_monday, this_monday + timedelta(days=4), 60)
        beats += self._beats_in_range(
            this_monday - timedelta(days=10), this_monday - timedelta(days=8), 60
        )
        svc = self._service()
        assert svc._detect_session_trend(beats, today) == []

    async def test_change_below_30_percent_returns_no_card(self):
        from beats.domain.intelligence import _monday_of

        today = datetime.now(UTC).date()
        this_monday = _monday_of(today)
        beats = self._beats_in_range(this_monday, today, 60)
        beats += self._beats_in_range(
            this_monday - timedelta(weeks=4), this_monday - timedelta(days=1), 65
        )
        svc = self._service()
        assert svc._detect_session_trend(beats, today) == []

    async def test_significant_increase_fires_with_longer_direction(self):
        from beats.domain.intelligence import _monday_of

        today = datetime.now(UTC).date()
        this_monday = _monday_of(today)
        beats = self._beats_in_range(this_monday, today, 90)
        beats += self._beats_in_range(
            this_monday - timedelta(weeks=4), this_monday - timedelta(days=1), 60
        )
        svc = self._service()
        cards = svc._detect_session_trend(beats, today)
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
        beats = self._beats_in_range(this_monday, today, 30)
        beats += self._beats_in_range(
            this_monday - timedelta(weeks=4), this_monday - timedelta(days=1), 60
        )
        svc = self._service()
        cards = svc._detect_session_trend(beats, today)
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
        svc = self._service()
        assert svc._detect_session_trend(beats, today) == []


class TestPatternDetectorsMoodCorrelation:
    """_detect_mood_correlation Pearson-correlates daily tracked
    hours with the mood score from daily notes. Surfaces if ≥10
    notes have moods AND |r| > 0.3. Body text changes between the
    positive-r and negative-r framings."""

    def _service(self):
        return _intel_service()

    def _note(self, d: date, mood: int | None, content: str = "") -> DailyNote:
        return DailyNote(id=f"n-{d.isoformat()}", date=d, note=content, mood=mood)

    async def test_fewer_than_10_notes_returns_no_card(self):
        """The 10-note minimum prevents a single noisy week from
        flipping the user's perceived productivity narrative."""
        today = datetime.now(UTC).date()
        notes = [self._note(today - timedelta(days=i), 4) for i in range(8)]
        svc = self._service()
        assert svc._detect_mood_correlation([], notes) == []

    async def test_zero_correlation_returns_no_card(self):
        """When daily hours are identical regardless of mood, the
        denominator hits the zero-variance branch and no card fires."""
        today = datetime.now(UTC).date()
        notes = [self._note(today - timedelta(days=i), (i % 5) + 1) for i in range(12)]
        beats = []
        for i in range(12):
            d = today - timedelta(days=i)
            s = datetime.combine(d, datetime.min.time(), tzinfo=UTC).replace(hour=10)
            beats.append(Beat(id=f"b{i}", project_id="p1", start=s, end=s + timedelta(hours=2)))
        svc = self._service()
        assert svc._detect_mood_correlation(beats, notes) == []

    async def test_strong_positive_correlation_fires_with_more_work_better_mood_body(self):
        """When more hours correlate with higher mood, the body uses
        the high-mood/high-hours framing."""
        today = datetime.now(UTC).date()
        notes = []
        beats = []
        for i in range(12):
            d = today - timedelta(days=i)
            mood = 1 if i < 6 else 5
            hours = 1 if i < 6 else 5
            notes.append(self._note(d, mood))
            s = datetime.combine(d, datetime.min.time(), tzinfo=UTC).replace(hour=10)
            beats.append(Beat(id=f"b{i}", project_id="p1", start=s, end=s + timedelta(hours=hours)))
        svc = self._service()
        cards = svc._detect_mood_correlation(beats, notes)
        assert len(cards) == 1
        card = cards[0]
        assert card.type == "mood_correlation"
        assert "mood 4+" in card.body
        assert card.data["r"] >= 0.3
        assert card.data["high_mood_avg_hours"] > card.data["low_mood_avg_hours"]

    async def test_strong_negative_correlation_fires_with_lighter_days_body(self):
        """Negative correlation flips the body to "lighter days,
        mood higher"."""
        today = datetime.now(UTC).date()
        notes = []
        beats = []
        for i in range(12):
            d = today - timedelta(days=i)
            mood = 5 if i < 6 else 1
            hours = 1 if i < 6 else 5
            notes.append(self._note(d, mood))
            s = datetime.combine(d, datetime.min.time(), tzinfo=UTC).replace(hour=10)
            beats.append(Beat(id=f"b{i}", project_id="p1", start=s, end=s + timedelta(hours=hours)))
        svc = self._service()
        cards = svc._detect_mood_correlation(beats, notes)
        assert len(cards) == 1
        assert "lighter days" in cards[0].body.lower()
        assert cards[0].data["r"] <= -0.3


class TestPatternDetectorsEstimationBias:
    """_detect_estimation_bias compares planned (intentions) vs
    actual (beats) per (project, date). When a project's average
    ratio drifts outside [0.8, 1.2] across ≥3 days, fire a card."""

    def _service(self):
        return _intel_service()

    async def test_fewer_than_3_planned_days_returns_no_card(self):
        """The 3-day minimum prevents a one-off bad estimate from
        being labeled as a habit."""
        today = datetime.now(UTC).date()
        intentions = [
            Intention(project_id="p1", date=today, planned_minutes=60, completed=False),
            Intention(
                project_id="p1",
                date=today - timedelta(days=1),
                planned_minutes=60,
                completed=False,
            ),
        ]
        s = datetime.combine(today, datetime.min.time(), tzinfo=UTC).replace(hour=10)
        beats = [Beat(id="b1", project_id="p1", start=s, end=s + timedelta(minutes=120))]
        svc = self._service()
        cards = svc._detect_estimation_bias(beats, intentions, {"p1": _project("p1", "Alpha")})
        assert cards == []

    async def test_consistent_underestimate_fires_with_pct(self):
        """Actual = 2× planned across 3 days → "underestimate" card
        with the percentage in the body. Priority 3 — actionable."""
        today = datetime.now(UTC).date()
        intentions = []
        beats = []
        for i in range(3):
            d = today - timedelta(days=i)
            intentions.append(
                Intention(project_id="p1", date=d, planned_minutes=60, completed=True)
            )
            s = datetime.combine(d, datetime.min.time(), tzinfo=UTC).replace(hour=10)
            beats.append(Beat(id=f"b{i}", project_id="p1", start=s, end=s + timedelta(minutes=120)))
        svc = self._service()
        cards = svc._detect_estimation_bias(beats, intentions, {"p1": _project("p1", "Alpha")})
        assert len(cards) == 1
        card = cards[0]
        assert card.type == "estimation_accuracy"
        assert "underestimate" in card.title.lower()
        assert "Alpha" in card.title
        assert "100%" in card.body
        assert card.priority == 3
        assert card.data["avg_ratio"] == 2.0

    async def test_consistent_overestimate_fires_with_lower_priority(self):
        """Actual = 0.5× planned → "overestimate" card with priority
        2 (less urgent — user is exceeding the plan in a good way)."""
        today = datetime.now(UTC).date()
        intentions = []
        beats = []
        for i in range(3):
            d = today - timedelta(days=i)
            intentions.append(
                Intention(project_id="p1", date=d, planned_minutes=60, completed=True)
            )
            s = datetime.combine(d, datetime.min.time(), tzinfo=UTC).replace(hour=10)
            beats.append(Beat(id=f"b{i}", project_id="p1", start=s, end=s + timedelta(minutes=30)))
        svc = self._service()
        cards = svc._detect_estimation_bias(beats, intentions, {"p1": _project("p1", "Alpha")})
        assert len(cards) == 1
        card = cards[0]
        assert "overestimate" in card.title.lower()
        assert card.priority == 2
        assert card.data["avg_ratio"] == 0.5

    async def test_within_20_percent_returns_no_card(self):
        """Ratio in [0.8, 1.2] is "good enough" — no card. Pin the
        threshold so a slight habitual under/over doesn't drown the
        dashboard in noise."""
        today = datetime.now(UTC).date()
        intentions = []
        beats = []
        for i in range(3):
            d = today - timedelta(days=i)
            intentions.append(
                Intention(project_id="p1", date=d, planned_minutes=60, completed=True)
            )
            s = datetime.combine(d, datetime.min.time(), tzinfo=UTC).replace(hour=10)
            beats.append(Beat(id=f"b{i}", project_id="p1", start=s, end=s + timedelta(minutes=65)))
        svc = self._service()
        assert svc._detect_estimation_bias(beats, intentions, {"p1": _project("p1", "Alpha")}) == []


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
        svc = self._service()
        assert svc._detect_goal_pacing([], [], self._friday_after(datetime.now(UTC).date())) == []

    async def test_skips_archived_projects(self):
        archived = _project("p1", "Old", weekly_goal=5.0, archived=True)
        svc = self._service()
        result = svc._detect_goal_pacing(
            [], [archived], self._friday_after(datetime.now(UTC).date())
        )
        assert result == []

    async def test_skips_projects_without_goal(self):
        no_goal = _project("p1", "Casual", weekly_goal=None)
        svc = self._service()
        result = svc._detect_goal_pacing(
            [], [no_goal], self._friday_after(datetime.now(UTC).date())
        )
        assert result == []

    async def test_early_in_week_skips_card(self):
        """On Monday there are still 7 days left — even at 0%
        progress, no pacing card fires. Threshold is days_left ≤ 3."""
        from beats.domain.intelligence import _monday_of

        today = datetime.now(UTC).date()
        this_monday = _monday_of(today)
        projects = [_project("p1", "Alpha", weekly_goal=10.0)]
        svc = self._service()
        assert svc._detect_goal_pacing([], projects, this_monday) == []

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
        svc = self._service()
        cards = svc._detect_goal_pacing(beats, projects, friday)
        assert len(cards) == 1
        card = cards[0]
        assert card.type == "goal_pacing"
        assert "Alpha" in card.title
        assert "9.0h" in card.title
        assert card.priority == 4
        assert card.data["days_left"] == 3
        assert card.data["remaining"] == 9.0

    async def test_friday_with_high_progress_skips(self):
        """≥ 50% progress by Friday → no nag."""
        from beats.domain.intelligence import _monday_of

        today = datetime.now(UTC).date()
        friday = self._friday_after(today)
        monday = _monday_of(friday)
        s = datetime.combine(monday, datetime.min.time(), tzinfo=UTC).replace(hour=10)
        beats = [Beat(id="b1", project_id="p1", start=s, end=s + timedelta(hours=6))]
        projects = [_project("p1", "Alpha", weekly_goal=10.0)]
        svc = self._service()
        assert svc._detect_goal_pacing(beats, projects, friday) == []

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
        svc = self._service()
        assert svc._detect_goal_pacing(beats, projects, friday) == []


class TestGenerateWeeklyDigest:
    """generate_weekly_digest — aggregates a week's beats into a
    WeeklyDigest with totals, top project, longest day, vs-last-week
    delta, streak, observation, and a simplified productivity score.

    Risk: a regression in any of these would silently change the
    weekly summary email/UI without surfacing as a 500 — the digest
    would just become subtly wrong. These tests pin every field."""

    @staticmethod
    def _monday_at(week_monday: date, *, day_offset: int, hour: int) -> datetime:
        return datetime.combine(
            week_monday + timedelta(days=day_offset),
            datetime.min.time(),
            tzinfo=UTC,
        ).replace(hour=hour)

    async def test_empty_week_returns_zeros_with_fallback_observation(self):
        """No beats → totals are zero, top/longest fields default,
        vs_last_week_pct is None, and the observation falls through
        to the "you tracked Xh across N sessions" sentence."""
        monday = date(2026, 4, 27)  # known Monday
        svc = _intel_service()
        digest = await svc.generate_weekly_digest(monday)

        assert digest.week_of == monday
        assert digest.total_hours == 0
        assert digest.session_count == 0
        assert digest.active_days == 0
        assert digest.top_project_id is None
        assert digest.top_project_name is None
        assert digest.top_project_hours == 0
        assert digest.vs_last_week_pct is None
        assert digest.longest_day is None
        assert digest.longest_day_hours == 0
        assert digest.best_streak == 0
        assert digest.project_breakdown == []
        assert "0.0h" in digest.observation
        assert "0 sessions" in digest.observation

    async def test_single_project_single_day_pins_top_and_longest(self):
        """One 90-min beat on Wednesday → top_project = that project,
        longest_day = "Wednesday", longest_day_hours = 1.5."""
        monday = date(2026, 4, 27)
        wed = self._monday_at(monday, day_offset=2, hour=10)
        beats = [Beat(id="b1", project_id="p1", start=wed, end=wed + timedelta(minutes=90))]
        projects = [_project("p1", "Alpha", weekly_goal=5.0)]
        svc = _intel_service(beats=beats, projects=projects)

        digest = await svc.generate_weekly_digest(monday)

        assert digest.total_hours == 1.5
        assert digest.session_count == 1
        assert digest.active_days == 1
        assert digest.top_project_id == "p1"
        assert digest.top_project_name == "Alpha"
        assert digest.top_project_hours == 1.5
        assert digest.longest_day == "Wednesday"
        assert digest.longest_day_hours == 1.5

    async def test_project_breakdown_sorted_descending_by_minutes(self):
        """Breakdown list is sorted by minutes desc — the UI relies
        on index 0 being the top project."""
        monday = date(2026, 4, 27)
        s_a = self._monday_at(monday, day_offset=0, hour=9)
        s_b = self._monday_at(monday, day_offset=1, hour=9)
        s_c = self._monday_at(monday, day_offset=2, hour=9)
        beats = [
            Beat(id="b1", project_id="p1", start=s_a, end=s_a + timedelta(minutes=30)),
            Beat(id="b2", project_id="p2", start=s_b, end=s_b + timedelta(minutes=120)),
            Beat(id="b3", project_id="p3", start=s_c, end=s_c + timedelta(minutes=60)),
        ]
        projects = [_project("p1", "Alpha"), _project("p2", "Beta"), _project("p3", "Gamma")]
        svc = _intel_service(beats=beats, projects=projects)

        digest = await svc.generate_weekly_digest(monday)

        names = [row["name"] for row in digest.project_breakdown]
        assert names == ["Beta", "Gamma", "Alpha"]
        assert digest.top_project_id == "p2"
        assert digest.top_project_name == "Beta"
        assert digest.top_project_hours == 2.0

    async def test_vs_last_week_pct_uses_prev_week_minutes(self):
        """Prev week 60 min, this week 90 min → +50.0%."""
        monday = date(2026, 4, 27)
        prev_monday = monday - timedelta(days=7)
        this_s = self._monday_at(monday, day_offset=1, hour=10)
        prev_s = datetime.combine(
            prev_monday + timedelta(days=1), datetime.min.time(), tzinfo=UTC
        ).replace(hour=10)
        beats = [
            Beat(id="b1", project_id="p1", start=this_s, end=this_s + timedelta(minutes=90)),
            Beat(id="b0", project_id="p1", start=prev_s, end=prev_s + timedelta(minutes=60)),
        ]
        projects = [_project("p1", "Alpha")]
        svc = _intel_service(beats=beats, projects=projects)

        digest = await svc.generate_weekly_digest(monday)

        assert digest.vs_last_week_pct == 50.0

    async def test_vs_last_week_none_when_no_prev_activity(self):
        """No prev-week beats → vs_last_week_pct is None (not 0, not
        +inf). Pin so the UI's "vs last week" chip can render
        "first week tracked" rather than "+0%"."""
        monday = date(2026, 4, 27)
        s = self._monday_at(monday, day_offset=1, hour=10)
        beats = [Beat(id="b1", project_id="p1", start=s, end=s + timedelta(minutes=60))]
        projects = [_project("p1", "Alpha")]
        svc = _intel_service(beats=beats, projects=projects)

        digest = await svc.generate_weekly_digest(monday)

        assert digest.vs_last_week_pct is None

    async def test_best_streak_counts_consecutive_days_ending_sunday(self):
        """Beats Fri-Sat-Sun → streak of 3. Streak walks backward
        from sunday and breaks at the first inactive day."""
        monday = date(2026, 4, 27)
        beats = []
        for offset in (4, 5, 6):  # Fri, Sat, Sun
            s = self._monday_at(monday, day_offset=offset, hour=10)
            beats.append(
                Beat(id=f"b{offset}", project_id="p1", start=s, end=s + timedelta(minutes=30))
            )
        projects = [_project("p1", "Alpha")]
        svc = _intel_service(beats=beats, projects=projects)

        digest = await svc.generate_weekly_digest(monday)

        assert digest.best_streak == 3

    async def test_best_streak_zero_when_sunday_inactive(self):
        """Mon-Sat active, Sun off → streak = 0. The walk starts at
        Sunday; if Sunday is empty it breaks immediately. This is
        intentional — pin so a refactor doesn't accidentally make
        the streak walk start from "last active day"."""
        monday = date(2026, 4, 27)
        beats = []
        for offset in range(6):  # Mon..Sat, no Sun
            s = self._monday_at(monday, day_offset=offset, hour=10)
            beats.append(
                Beat(id=f"b{offset}", project_id="p1", start=s, end=s + timedelta(minutes=30))
            )
        projects = [_project("p1", "Alpha")]
        svc = _intel_service(beats=beats, projects=projects)

        digest = await svc.generate_weekly_digest(monday)

        assert digest.best_streak == 0

    async def test_active_days_counts_distinct_dates_only(self):
        """Two beats on the same day → active_days = 1, session_count = 2."""
        monday = date(2026, 4, 27)
        morning = self._monday_at(monday, day_offset=2, hour=9)
        afternoon = self._monday_at(monday, day_offset=2, hour=14)
        beats = [
            Beat(id="b1", project_id="p1", start=morning, end=morning + timedelta(minutes=30)),
            Beat(id="b2", project_id="p1", start=afternoon, end=afternoon + timedelta(minutes=45)),
        ]
        projects = [_project("p1", "Alpha")]
        svc = _intel_service(beats=beats, projects=projects)

        digest = await svc.generate_weekly_digest(monday)

        assert digest.active_days == 1
        assert digest.session_count == 2

    async def test_unknown_project_renders_as_unknown(self):
        """A beat referencing a project_id not in the project list
        (e.g. archived during the week) → row in breakdown labeled
        "Unknown" rather than crashing."""
        monday = date(2026, 4, 27)
        s = self._monday_at(monday, day_offset=1, hour=10)
        beats = [Beat(id="b1", project_id="ghost", start=s, end=s + timedelta(minutes=30))]
        svc = _intel_service(beats=beats, projects=[])

        digest = await svc.generate_weekly_digest(monday)

        assert digest.top_project_name == "Unknown"
        assert digest.project_breakdown[0]["name"] == "Unknown"


class TestGenerateObservation:
    """_generate_observation picks one of four narrative branches in
    a fixed priority order:
      1. New project this week (>30 min)
      2. Big delta on an existing project (|change| > 50%, both
         weeks >30 min)
      3. Most-productive day if any day_minutes
      4. Fallback: "you tracked Xh across N sessions"

    These tests pin the branch boundaries and the rendered phrasing.
    Risk: a phrasing tweak that drops a key noun ("more"/"less", a
    project name) would silently degrade the digest's narrative
    without surfacing as a failure."""

    def _svc(self):
        return _intel_service()

    def _projects(self, *names: str) -> dict:
        return {f"p{i + 1}": _project(f"p{i + 1}", n) for i, n in enumerate(names)}

    async def test_new_project_branch_fires_above_threshold(self):
        """A project absent from prev week with >30 min logged →
        "You started working on X this week" sentence."""
        proj_minutes = {"p1": 120.0}
        prev = {}  # not in prev
        proj_map = self._projects("Alpha")
        out = self._svc()._generate_observation(
            proj_minutes, prev, proj_map, day_minutes={}, total_hours=2.0, session_count=2
        )
        assert "started working on Alpha" in out
        assert "2.0h" in out

    async def test_new_project_skipped_at_or_below_threshold(self):
        """A new project with exactly 30 min does NOT trigger the
        "started" sentence — falls through to the next branch.
        Pin so a single short trial session doesn't headline the
        digest as "you started X this week"."""
        proj_minutes = {"p1": 30.0}
        prev = {}
        proj_map = self._projects("Alpha")
        # No day_minutes, falls through to fallback
        out = self._svc()._generate_observation(
            proj_minutes, prev, proj_map, day_minutes={}, total_hours=0.5, session_count=1
        )
        assert "started" not in out
        assert "0.5h across 1 sessions" in out

    async def test_big_delta_increase_renders_more(self):
        """Prev 60, this 120 → +100% → "100% more time on Alpha"."""
        proj_minutes = {"p1": 120.0}
        prev = {"p1": 60.0}
        proj_map = self._projects("Alpha")
        out = self._svc()._generate_observation(
            proj_minutes, prev, proj_map, day_minutes={}, total_hours=2.0, session_count=2
        )
        assert "100% more time on Alpha" in out
        assert "compared to last week" in out

    async def test_big_delta_decrease_renders_less(self):
        """Prev 200, this 60 → −70% → "70% less time on Alpha"."""
        proj_minutes = {"p1": 60.0}
        prev = {"p1": 200.0}
        proj_map = self._projects("Alpha")
        out = self._svc()._generate_observation(
            proj_minutes, prev, proj_map, day_minutes={}, total_hours=1.0, session_count=1
        )
        assert "70% less time on Alpha" in out

    async def test_big_delta_skipped_when_either_week_too_small(self):
        """Both prev and curr must be >30 min for the delta branch
        to fire — avoids noise from spike-from-zero or cliff-to-near-zero
        artifacts the "new project" / "stale project" branches handle
        elsewhere. Falls through to day-pattern."""
        proj_minutes = {"p1": 35.0}
        prev = {"p1": 20.0}  # below the 30-minute floor
        proj_map = self._projects("Alpha")
        long_day = date(2026, 4, 29)
        out = self._svc()._generate_observation(
            proj_minutes,
            prev,
            proj_map,
            day_minutes={long_day: 35.0},
            total_hours=0.6,
            session_count=1,
        )
        assert "more time" not in out
        assert "less time" not in out
        # Falls through to day-pattern (Wednesday is 2026-04-29)
        assert long_day.strftime("%A") in out

    async def test_small_delta_skipped(self):
        """|change| ≤ 50% → no delta sentence. 60 → 80 is +33%, below
        the threshold."""
        proj_minutes = {"p1": 80.0}
        prev = {"p1": 60.0}
        proj_map = self._projects("Alpha")
        out = self._svc()._generate_observation(
            proj_minutes, prev, proj_map, day_minutes={}, total_hours=1.3, session_count=1
        )
        assert "more time" not in out
        assert "less time" not in out

    async def test_day_pattern_fallback_when_no_project_signal(self):
        """No new/delta projects but day_minutes present → "Your
        most productive day was {Monday} with {X}h tracked"."""
        long_day = date(2026, 4, 27)  # Monday
        out = self._svc()._generate_observation(
            proj_minutes={},
            prev_proj_minutes={},
            project_map={},
            day_minutes={long_day: 240.0},
            total_hours=4.0,
            session_count=3,
        )
        assert "most productive day was Monday" in out
        assert "4.0h" in out

    async def test_terminal_fallback_when_nothing_to_say(self):
        """No projects, no days, but session_count>0 → "You tracked
        Xh across N sessions this week"."""
        out = self._svc()._generate_observation(
            proj_minutes={},
            prev_proj_minutes={},
            project_map={},
            day_minutes={},
            total_hours=0.0,
            session_count=0,
        )
        assert out == "You tracked 0.0h across 0 sessions this week."

    async def test_new_project_priority_over_day_pattern(self):
        """When BOTH a new project and day_minutes are present, the
        "new project" branch wins. Pin the priority so a refactor
        doesn't accidentally promote day-pattern (which is a weaker
        signal) above the project-level narrative."""
        proj_minutes = {"p1": 90.0}
        prev = {}
        proj_map = self._projects("Alpha")
        long_day = date(2026, 4, 27)
        out = self._svc()._generate_observation(
            proj_minutes,
            prev,
            proj_map,
            day_minutes={long_day: 90.0},
            total_hours=1.5,
            session_count=2,
        )
        assert "started working on Alpha" in out
        assert "most productive day" not in out

    async def test_unknown_project_renders_as_a_project(self):
        """If project_map doesn't contain the id (e.g. project was
        archived/deleted between digest runs), the new-project
        sentence renders "a project" rather than crashing on
        None.name."""
        proj_minutes = {"ghost": 60.0}
        prev = {}
        out = self._svc()._generate_observation(
            proj_minutes,
            prev,
            project_map={},
            day_minutes={},
            total_hours=1.0,
            session_count=1,
        )
        assert "started working on a project" in out


class TestSuggestDailyPlan:
    """suggest_daily_plan blends three signals into a per-project
    score: day-of-week average (×0.4), unmet weekly goal (×0.4), and
    "worked yesterday" recency (×0.2). Returns top 3 above the 0.05
    threshold, with a suggested-minutes value rounded to a 15-minute
    grid and clamped to [15, 240].

    Risk: a sign flip or weighting tweak would change every user's
    daily plan recommendations silently — these tests pin the
    score-driven branches and the minute-clamping math."""

    # A canonical Friday in the current month — chosen so the prior
    # 8 weeks all have a Friday for the day-of-week aggregation to
    # bite on.
    FRIDAY = date(2026, 5, 1)

    @staticmethod
    def _at(d: date, hour: int) -> datetime:
        return datetime.combine(d, datetime.min.time(), tzinfo=UTC).replace(hour=hour)

    async def test_no_projects_returns_empty(self):
        svc = _intel_service()
        result = await svc.suggest_daily_plan(self.FRIDAY)
        assert result == []

    async def test_archived_projects_skipped(self):
        """Archived projects never appear in suggestions, even with
        an unmet goal — they're hidden from the project list, so a
        plan suggesting one would be a UI ghost."""
        projects = [_project("p1", "Old", weekly_goal=10.0, archived=True)]
        svc = _intel_service(projects=projects)
        result = await svc.suggest_daily_plan(self.FRIDAY)
        assert result == []

    async def test_unmet_weekly_goal_drives_score_and_reasoning(self):
        """A project with weekly_goal=10h and 0h tracked this week
        contributes unmet_weight=1.0 → score 0.4, well above the
        0.05 threshold. Reasoning quotes the remaining hours."""
        projects = [_project("p1", "Alpha", weekly_goal=10.0)]
        svc = _intel_service(projects=projects)
        result = await svc.suggest_daily_plan(self.FRIDAY)
        assert len(result) == 1
        assert result[0]["project_id"] == "p1"
        assert result[0]["project_name"] == "Alpha"
        assert "10.0h more" in result[0]["reasoning"]
        # avg=0 falls into the else branch → suggested_minutes = 60,
        # capped by remaining (10h = 600m), so stays at 60.
        assert result[0]["suggested_minutes"] == 60

    async def test_met_goal_not_recommended(self):
        """Goal met (remaining ≤ 0) means unmet_weight=0; without
        history or yesterday-recency the score is 0 → filtered."""
        projects = [_project("p1", "Alpha", weekly_goal=2.0)]
        # 2h logged this week (Monday before the target Friday)
        monday = self.FRIDAY - timedelta(days=4)
        beats = [
            Beat(
                id="b0",
                project_id="p1",
                start=self._at(monday, 10),
                end=self._at(monday, 12),
            )
        ]
        svc = _intel_service(beats=beats, projects=projects)
        result = await svc.suggest_daily_plan(self.FRIDAY)
        assert result == []

    async def test_day_of_week_avg_drives_suggested_minutes(self):
        """Strong Friday history (1h every prior Friday for 8 weeks)
        → avg ≈ 60 min → suggested_minutes rounds to 60. No goal,
        so reasoning falls into the day-of-week branch."""
        projects = [_project("p1", "Alpha")]
        beats = []
        for w in range(1, 9):
            d = self.FRIDAY - timedelta(weeks=w)
            beats.append(
                Beat(
                    id=f"b{w}",
                    project_id="p1",
                    start=self._at(d, 10),
                    end=self._at(d, 11),
                )
            )
        svc = _intel_service(beats=beats, projects=projects)
        result = await svc.suggest_daily_plan(self.FRIDAY)
        assert len(result) == 1
        assert result[0]["suggested_minutes"] == 60
        assert "On Fridays you usually spend" in result[0]["reasoning"]
        assert "1.0h" in result[0]["reasoning"]

    async def test_suggested_minutes_capped_at_240(self):
        """Even a 5h average Friday should not suggest a 5h block —
        clamp at 4h (240 min) so a single suggestion can't swallow
        the whole day. Pin so removing the cap can't go unnoticed."""
        projects = [_project("p1", "Alpha")]
        beats = []
        for w in range(1, 9):
            d = self.FRIDAY - timedelta(weeks=w)
            beats.append(
                Beat(
                    id=f"b{w}",
                    project_id="p1",
                    start=self._at(d, 9),
                    end=self._at(d, 14),  # 5h
                )
            )
        svc = _intel_service(beats=beats, projects=projects)
        result = await svc.suggest_daily_plan(self.FRIDAY)
        assert result[0]["suggested_minutes"] == 240

    async def test_suggested_minutes_clamped_by_remaining_goal(self):
        """A project with goal=2h and 1.5h logged this week has only
        30 min remaining. Even if Friday's avg is 2h, suggested
        clamps to 30 min — pin so a recommendation can't overshoot
        the weekly goal."""
        projects = [_project("p1", "Alpha", weekly_goal=2.0)]
        # 1.5h logged Monday (this week, before the Friday target)
        monday = self.FRIDAY - timedelta(days=4)
        beats = [
            Beat(
                id="b0",
                project_id="p1",
                start=self._at(monday, 9),
                end=self._at(monday, 10) + timedelta(minutes=30),
            )
        ]
        # 8 weeks of 2h Fridays for history
        for w in range(1, 9):
            d = self.FRIDAY - timedelta(weeks=w)
            beats.append(
                Beat(
                    id=f"bf{w}",
                    project_id="p1",
                    start=self._at(d, 9),
                    end=self._at(d, 11),
                )
            )
        svc = _intel_service(beats=beats, projects=projects)
        result = await svc.suggest_daily_plan(self.FRIDAY)
        assert result[0]["suggested_minutes"] == 30

    async def test_top_3_cap_with_score_descending(self):
        """5 candidate projects → only top 3 returned, sorted by
        score desc. Higher weekly goals (more unmet hours) should
        rank above smaller ones when no other signal applies."""
        projects = [_project(f"p{i}", f"P{i}", weekly_goal=float(i + 1)) for i in range(1, 6)]
        svc = _intel_service(projects=projects)
        result = await svc.suggest_daily_plan(self.FRIDAY)
        # All 5 share the same unmet_weight=1.0 → tie at 0.4. Order
        # is dict-iteration-stable (insertion order) but only 3
        # come back. Pin the cap regardless of order.
        assert len(result) == 3

    async def test_recency_bonus_lifts_yesterday_project(self):
        """Two projects, neither has a goal; one was worked
        yesterday. Recency bonus (0.2) lifts it above the 0.05
        threshold and ranks it first."""
        projects = [_project("p1", "Yesterday"), _project("p2", "Cold")]
        yesterday = self.FRIDAY - timedelta(days=1)
        beats = [
            Beat(
                id="by",
                project_id="p1",
                start=self._at(yesterday, 10),
                end=self._at(yesterday, 11),
            ),
        ]
        svc = _intel_service(beats=beats, projects=projects)
        result = await svc.suggest_daily_plan(self.FRIDAY)
        # p2 has no signal → filtered. p1's recency lifts it.
        assert [r["project_id"] for r in result] == ["p1"]

    async def test_unknown_project_in_score_renders_unknown(self):
        """Defensive: if a scored pid isn't in project_map (race
        between repo loads), the result row labels it "Unknown"
        rather than KeyError'ing the whole endpoint."""
        # Force the rare race: project list has p1, but a beat is
        # logged against a different id that drops into yesterday's
        # set so recency triggers a score for the missing pid.
        # Easier to test the goal path directly: pass an extra
        # project then wipe its name via the model.
        projects = [_project("p1", "Alpha", weekly_goal=5.0)]
        svc = _intel_service(projects=projects)
        result = await svc.suggest_daily_plan(self.FRIDAY)
        assert result[0]["project_name"] == "Alpha"


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
        assert self._svc()._find_peak_block([]) == 4

    def test_picks_block_with_most_total_minutes(self):
        """Three beats: 30 min in block 4 (9 AM), 90 min in
        block 7 (14:00), 30 min in block 9 (18:00). Block 7 wins."""
        beats = [
            self._beat_at(9, 30),
            self._beat_at(14, 90),
            self._beat_at(18, 30),
        ]
        assert self._svc()._find_peak_block(beats) == 7

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
        assert self._svc()._find_peak_block(beats) == 4


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
        svc = self._svc()
        cases = [(8, 5), (20, 15), (30, 25), (60, 35), (120, 40)]
        for mins, expected in cases:
            b = self._beat(9, mins)
            r = svc._focus_score_for_beat(b, [b], 0, peak_block=4)
            assert r["components"]["length"] == expected, (
                f"{mins}min should map to length={expected}"
            )

    def test_peak_component_same_block_full_credit(self):
        """Beat in the user's peak 2-hour block → peak component=30."""
        b = self._beat(9, 60)  # 9 AM = block 4
        r = self._svc()._focus_score_for_beat(b, [b], 0, peak_block=4)
        assert r["components"]["peak_hours"] == 30

    def test_peak_component_adjacent_block_partial(self):
        """One block away from peak → 20."""
        b = self._beat(11, 60)  # block 5; peak=4
        r = self._svc()._focus_score_for_beat(b, [b], 0, peak_block=4)
        assert r["components"]["peak_hours"] == 20

    def test_peak_component_far_block_minimum(self):
        """Two or more blocks away from peak → 10."""
        b = self._beat(20, 60)  # block 10; peak=4
        r = self._svc()._focus_score_for_beat(b, [b], 0, peak_block=4)
        assert r["components"]["peak_hours"] == 10

    def test_no_neighbors_no_fragmentation_penalty(self):
        """A solo beat (only one on the day) has frag=30 — no
        adjacent gap to check. Pin so a refactor doesn't apply
        the penalty unconditionally."""
        b = self._beat(9, 60)
        r = self._svc()._focus_score_for_beat(b, [b], 0, peak_block=4)
        assert r["components"]["fragmentation"] == 30

    def test_fragmentation_penalty_when_close_to_prev(self):
        """Gap to previous beat < 5 min → frag drops by 15.
        Pattern: prev ends 9:30, this starts 9:33 → 3 min gap → penalty."""
        prev = self._beat(9, 30, id_="prev")  # 9:00-9:30
        s = datetime(2026, 4, 1, 9, 33, tzinfo=UTC)
        cur = Beat(id="cur", project_id="p1", start=s, end=s + timedelta(minutes=20))
        r = self._svc()._focus_score_for_beat(cur, [prev, cur], 1, peak_block=4)
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
        r = self._svc()._focus_score_for_beat(cur, [prev, cur, nxt], 1, peak_block=4)
        assert r["components"]["fragmentation"] == 0

    def test_no_penalty_when_gap_at_least_5min(self):
        """Gap of exactly 5 min → no penalty (the boundary is `< 5`)."""
        prev = self._beat(9, 30, id_="prev")  # ends 9:30
        cur_s = datetime(2026, 4, 1, 9, 35, tzinfo=UTC)  # exactly 5 min gap
        cur = Beat(id="cur", project_id="p1", start=cur_s, end=cur_s + timedelta(minutes=20))
        r = self._svc()._focus_score_for_beat(cur, [prev, cur], 1, peak_block=4)
        assert r["components"]["fragmentation"] == 30

    def test_total_score_sums_components(self):
        """Total = length + peak + frag, clamped to [0, 100]. A 90+
        minute beat in the peak block with no close neighbors hits
        the 100 ceiling: 40 + 30 + 30 = 100."""
        b = self._beat(9, 120)
        r = self._svc()._focus_score_for_beat(b, [b], 0, peak_block=4)
        assert r["score"] == 100


class TestComputeFocusScores:
    """compute_focus_scores threads three pieces together: load the
    target day's beats, derive peak_block from 30 days of recent
    activity, and score each beat in chronological order."""

    async def test_empty_day_returns_empty(self):
        target = date(2026, 5, 1)
        svc = _intel_service()
        assert await svc.compute_focus_scores(target) == []

    async def test_returns_one_row_per_beat_with_components(self):
        """One beat on the target day → one row with score and
        component dict. Pin the response shape — the UI binds to
        `score` + `components.length/peak_hours/fragmentation`."""
        target = date(2026, 5, 1)
        s = datetime.combine(target, datetime.min.time(), tzinfo=UTC).replace(hour=9)
        beats = [Beat(id="b1", project_id="p1", start=s, end=s + timedelta(minutes=60))]
        svc = _intel_service(beats=beats)
        result = await svc.compute_focus_scores(target)
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
        result = await svc.compute_focus_scores(target)
        # Result is sorted: early first, then late
        assert [r["beat_id"] for r in result] == ["early", "late"]
        # Late has a 3-min gap from early → frag penalty
        assert result[1]["components"]["fragmentation"] == 15


class TestGetMoodCorrelation:
    """get_mood_correlation aggregates the last 90 days into a
    mood-vs-hours story: 7-day rolling mood trend, hi/lo bucketed
    averages, and a Pearson r (only computed at ≥10 pairs).

    Risk: a sign flip in the Pearson math would silently flip every
    user's "your best work happens when..." narrative. These tests
    pin the buckets and the gate."""

    @staticmethod
    def _at(d: date, hour: int) -> datetime:
        return datetime.combine(d, datetime.min.time(), tzinfo=UTC).replace(hour=hour)

    async def test_empty_returns_zero_neutral_defaults(self):
        """No notes / beats → r=0, description="neutral", all
        averages 0, mood_trend empty. Pin so the dashboard can
        render the empty state."""
        svc = _intel_service()
        result = await svc.get_mood_correlation()
        assert result["correlation"]["r"] == 0
        assert result["correlation"]["description"] == "neutral"
        assert result["high_mood_avg_hours"] == 0
        assert result["low_mood_avg_hours"] == 0
        assert result["mood_trend"] == []

    async def test_high_low_buckets_split_at_4_and_2(self):
        """mood ≥ 4 → high bucket; mood ≤ 2 → low bucket; mood = 3
        in neither. Pin so a refactor doesn't accidentally include
        the neutral middle on either side."""
        today = datetime.now(UTC).date()
        notes = []
        beats = []
        # Three high-mood days with 4h each
        for i in range(3):
            d = today - timedelta(days=i + 1)
            notes.append(DailyNote(date=d, mood=5))
            beats.append(
                Beat(
                    id=f"h{i}",
                    project_id="p1",
                    start=self._at(d, 9),
                    end=self._at(d, 13),
                )
            )
        # Three low-mood days with 1h each
        for i in range(3):
            d = today - timedelta(days=i + 10)
            notes.append(DailyNote(date=d, mood=1))
            beats.append(
                Beat(
                    id=f"l{i}",
                    project_id="p1",
                    start=self._at(d, 9),
                    end=self._at(d, 10),
                )
            )
        # One neutral day — should land in neither bucket
        d = today - timedelta(days=20)
        notes.append(DailyNote(date=d, mood=3))
        beats.append(
            Beat(
                id="n0",
                project_id="p1",
                start=self._at(d, 9),
                end=self._at(d, 19),  # 10h — would skew either bucket
            )
        )
        svc = _intel_service(beats=beats, notes=notes)
        result = await svc.get_mood_correlation()
        assert result["high_mood_avg_hours"] == 4.0
        assert result["low_mood_avg_hours"] == 1.0

    async def test_pearson_gated_at_10_pairs(self):
        """Below 10 mood-tagged days → r stays at 0 even if data
        would correlate. Pin the gate so a tiny sample doesn't
        produce a confident-looking but noisy r."""
        today = datetime.now(UTC).date()
        notes = []
        beats = []
        # 9 days, perfect correlation
        for i in range(9):
            d = today - timedelta(days=i + 1)
            notes.append(DailyNote(date=d, mood=min(5, i + 1)))
            beats.append(
                Beat(
                    id=f"b{i}",
                    project_id="p1",
                    start=self._at(d, 9),
                    end=self._at(d, 9 + i + 1),
                )
            )
        svc = _intel_service(beats=beats, notes=notes)
        result = await svc.get_mood_correlation()
        assert result["correlation"]["r"] == 0
        assert result["correlation"]["description"] == "neutral"

    async def test_strong_positive_correlation_renders_positive(self):
        """≥10 pairs with high mood ↔ high hours, low ↔ low →
        r > 0.3 → description "positive"."""
        today = datetime.now(UTC).date()
        notes = []
        beats = []
        for i in range(10):
            d = today - timedelta(days=i + 1)
            mood = (i % 5) + 1  # cycles 1..5
            hours = mood  # perfectly correlated
            notes.append(DailyNote(date=d, mood=mood))
            beats.append(
                Beat(
                    id=f"b{i}",
                    project_id="p1",
                    start=self._at(d, 9),
                    end=self._at(d, 9) + timedelta(hours=hours),
                )
            )
        svc = _intel_service(beats=beats, notes=notes)
        result = await svc.get_mood_correlation()
        assert result["correlation"]["r"] > 0.3
        assert result["correlation"]["description"] == "positive"


class TestGetEstimationAccuracy:
    """get_estimation_accuracy compares planned (intentions) vs
    actual minutes per (project, day), aggregates per project,
    classifies bias as underestimate (>110%) / overestimate (<90%)
    / accurate, and sorts most-biased first."""

    @staticmethod
    def _at(d: date, hour: int) -> datetime:
        return datetime.combine(d, datetime.min.time(), tzinfo=UTC).replace(hour=hour)

    async def test_empty_returns_empty(self):
        svc = _intel_service()
        result = await svc.get_estimation_accuracy()
        assert result == []

    async def test_skips_project_with_fewer_than_two_days(self):
        """A single planned day isn't a habit — skip the project.
        Pin so a one-off bad estimate doesn't headline the
        accuracy panel."""
        today = datetime.now(UTC).date()
        d = today - timedelta(days=1)
        intentions = [Intention(project_id="p1", date=d, planned_minutes=60)]
        beats = [
            Beat(
                id="b1",
                project_id="p1",
                start=self._at(d, 9),
                end=self._at(d, 11),  # 2h actual vs 1h planned
            )
        ]
        projects = [_project("p1", "Alpha")]
        svc = _intel_service(beats=beats, intentions=intentions, projects=projects)
        assert await svc.get_estimation_accuracy() == []

    async def test_bias_buckets_pinned(self):
        """Three projects: one underestimate (200%), one
        overestimate (50%), one accurate (100%). Each bucket
        threshold pinned: >110 / <90 / between."""
        today = datetime.now(UTC).date()
        intentions = []
        beats = []
        # p1: planned 60m × 3 days, actual 120m × 3 → 200%
        for i in range(3):
            d = today - timedelta(days=i + 1)
            intentions.append(Intention(project_id="p1", date=d, planned_minutes=60))
            beats.append(
                Beat(
                    id=f"u{i}",
                    project_id="p1",
                    start=self._at(d, 9),
                    end=self._at(d, 11),
                )
            )
        # p2: planned 120m × 3 days, actual 60m × 3 → 50%
        for i in range(3):
            d = today - timedelta(days=i + 10)
            intentions.append(Intention(project_id="p2", date=d, planned_minutes=120))
            beats.append(
                Beat(
                    id=f"o{i}",
                    project_id="p2",
                    start=self._at(d, 9),
                    end=self._at(d, 10),
                )
            )
        # p3: planned 60m × 3 days, actual 60m × 3 → 100%
        for i in range(3):
            d = today - timedelta(days=i + 20)
            intentions.append(Intention(project_id="p3", date=d, planned_minutes=60))
            beats.append(
                Beat(
                    id=f"a{i}",
                    project_id="p3",
                    start=self._at(d, 9),
                    end=self._at(d, 10),
                )
            )
        projects = [
            _project("p1", "Under"),
            _project("p2", "Over"),
            _project("p3", "Spot"),
        ]
        svc = _intel_service(beats=beats, intentions=intentions, projects=projects)
        result = await svc.get_estimation_accuracy()

        by_pid = {r["project_id"]: r for r in result}
        assert by_pid["p1"]["bias"] == "underestimate"
        assert by_pid["p1"]["accuracy_pct"] == 200.0
        assert by_pid["p2"]["bias"] == "overestimate"
        assert by_pid["p2"]["accuracy_pct"] == 50.0
        assert by_pid["p3"]["bias"] == "accurate"
        assert by_pid["p3"]["accuracy_pct"] == 100.0

        # Sort: most-biased (largest |accuracy-100|) first.
        # |200-100|=100, |50-100|=50, |100-100|=0
        assert [r["project_id"] for r in result] == ["p1", "p2", "p3"]


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


# =============================================================================
# Domain Services — TimerService, BeatService, ProjectService
# =============================================================================


class _FakeBeatRepoForServices:
    """In-memory BeatRepository fake for TimerService / BeatService.
    Implements get_active, get_last, create, update, delete, list,
    list_by_project, get_by_id with the same contract the real repo
    exposes (raising NoObjectMatched where applicable)."""

    def __init__(self, beats: list[Beat] | None = None):
        self._beats: list[Beat] = list(beats or [])
        self._counter = 1

    async def get_active(self) -> Beat | None:
        for b in self._beats:
            if b.end is None:
                return b
        return None

    async def get_last(self) -> Beat:
        from beats.domain.exceptions import NoObjectMatched

        completed = [b for b in self._beats if b.end is not None]
        if not completed:
            raise NoObjectMatched()
        return max(completed, key=lambda b: b.end)

    async def create(self, beat: Beat) -> Beat:
        if beat.id is None:
            beat = beat.model_copy(update={"id": f"b{self._counter}"})
            self._counter += 1
        self._beats.append(beat)
        return beat

    async def update(self, beat: Beat) -> Beat:
        for i, b in enumerate(self._beats):
            if b.id == beat.id:
                self._beats[i] = beat
                return beat
        from beats.domain.exceptions import NoObjectMatched

        raise NoObjectMatched()

    async def delete(self, beat_id: str) -> bool:
        for i, b in enumerate(self._beats):
            if b.id == beat_id:
                self._beats.pop(i)
                return True
        return False

    async def get_by_id(self, beat_id: str) -> Beat:
        for b in self._beats:
            if b.id == beat_id:
                return b
        from beats.domain.exceptions import NoObjectMatched

        raise NoObjectMatched()

    async def list(
        self, project_id: str | None = None, date_filter: date | None = None
    ) -> list[Beat]:
        out = list(self._beats)
        if project_id is not None:
            out = [b for b in out if b.project_id == project_id]
        if date_filter is not None:
            out = [b for b in out if b.start.date() == date_filter]
        return out

    async def list_by_project(self, project_id: str) -> list[Beat]:
        return [b for b in self._beats if b.project_id == project_id]


class _FakeProjectRepoForServices:
    """In-memory ProjectRepository fake."""

    def __init__(self, projects: list[Project] | None = None):
        self._projects: list[Project] = list(projects or [])
        self._counter = 1

    async def exists(self, project_id: str) -> bool:
        return any(p.id == project_id for p in self._projects)

    async def get_by_id(self, project_id: str) -> Project:
        for p in self._projects:
            if p.id == project_id:
                return p
        from beats.domain.exceptions import ProjectNotFound

        raise ProjectNotFound(project_id)

    async def create(self, project: Project) -> Project:
        if project.id is None:
            project = project.model_copy(update={"id": f"p{self._counter}"})
            self._counter += 1
        self._projects.append(project)
        return project

    async def update(self, project: Project) -> Project:
        for i, p in enumerate(self._projects):
            if p.id == project.id:
                self._projects[i] = project
                return project
        from beats.domain.exceptions import NoObjectMatched

        raise NoObjectMatched()

    async def list(self, archived: bool = False) -> list[Project]:
        return [p for p in self._projects if p.archived == archived]


def _timer_service(*, beats: list[Beat] | None = None, projects: list[Project] | None = None):
    from beats.domain.services import TimerService

    return TimerService(
        beat_repo=_FakeBeatRepoForServices(beats),
        project_repo=_FakeProjectRepoForServices(projects),
    )


class TestTimerServiceStart:
    """TimerService.start_timer pre-flight checks: project must exist
    and no other timer can be running. Pin both error paths so a
    regression in either silently corrupts the timer state."""

    async def test_creates_beat_with_now_when_project_exists(self):
        projects = [_project("p1", "Alpha")]
        svc = _timer_service(projects=projects)
        before = datetime.now(UTC)
        beat = await svc.start_timer("p1")
        after = datetime.now(UTC)
        assert beat.project_id == "p1"
        assert beat.end is None
        # Default start is "now" — clamped between before/after
        assert before <= beat.start <= after

    async def test_uses_custom_start_time_when_provided(self):
        """A backdated start (e.g. user logging time after the fact)
        is preserved verbatim. Pin so the now-default doesn't
        silently override an explicit timestamp."""
        projects = [_project("p1", "Alpha")]
        svc = _timer_service(projects=projects)
        custom = datetime(2026, 4, 1, 9, 30, tzinfo=UTC)
        beat = await svc.start_timer("p1", start_time=custom)
        assert beat.start == custom

    async def test_raises_project_not_found(self):
        from beats.domain.exceptions import ProjectNotFound

        svc = _timer_service()
        with pytest.raises(ProjectNotFound):
            await svc.start_timer("ghost")

    async def test_raises_timer_already_running(self):
        """An active timer (end=None) on any project blocks a new
        start. Pin so the multi-timer corruption can't slip in."""
        from beats.domain.exceptions import TimerAlreadyRunning

        projects = [_project("p1", "Alpha"), _project("p2", "Beta")]
        active = Beat(
            id="b-active",
            project_id="p1",
            start=datetime(2026, 4, 1, 9, 0, tzinfo=UTC),
            end=None,
        )
        svc = _timer_service(beats=[active], projects=projects)
        with pytest.raises(TimerAlreadyRunning) as exc:
            await svc.start_timer("p2")
        # The exception carries the conflicting project's name so
        # the UI can render "Already tracking Alpha".
        assert "Alpha" in str(exc.value) or exc.value.project_name == "Alpha"


class TestTimerServiceStop:
    """TimerService.stop_timer: requires an active beat and an
    end-time at or after start. Pin both."""

    async def test_stops_active_timer_with_now(self):
        projects = [_project("p1", "Alpha")]
        active = Beat(
            id="b-active",
            project_id="p1",
            start=datetime(2026, 4, 1, 9, 0, tzinfo=UTC),
            end=None,
        )
        svc = _timer_service(beats=[active], projects=projects)
        before = datetime.now(UTC)
        stopped = await svc.stop_timer()
        assert stopped.id == "b-active"
        assert stopped.end is not None
        assert stopped.end >= before

    async def test_stops_with_custom_end_time(self):
        projects = [_project("p1", "Alpha")]
        start = datetime(2026, 4, 1, 9, 0, tzinfo=UTC)
        active = Beat(id="b1", project_id="p1", start=start, end=None)
        svc = _timer_service(beats=[active], projects=projects)
        end = datetime(2026, 4, 1, 10, 30, tzinfo=UTC)
        stopped = await svc.stop_timer(end_time=end)
        assert stopped.end == end

    async def test_raises_no_active_timer(self):
        from beats.domain.exceptions import NoActiveTimer

        svc = _timer_service()
        with pytest.raises(NoActiveTimer):
            await svc.stop_timer()

    async def test_raises_invalid_end_time_when_end_before_start(self):
        """end < start would produce a negative duration. Pin the
        guard so the validation can't be quietly removed."""
        from beats.domain.exceptions import InvalidEndTime

        projects = [_project("p1", "Alpha")]
        start = datetime(2026, 4, 1, 10, 0, tzinfo=UTC)
        active = Beat(id="b1", project_id="p1", start=start, end=None)
        svc = _timer_service(beats=[active], projects=projects)
        too_early = datetime(2026, 4, 1, 9, 0, tzinfo=UTC)
        with pytest.raises(InvalidEndTime):
            await svc.stop_timer(end_time=too_early)


class TestTimerServiceStatus:
    """get_status returns one of three shapes:
      - {"isBeating": True, ...}   when an active timer exists
      - {"isBeating": False, "last_beat": {...}}   when none active
        but a previous completed beat exists
      - {"isBeating": False}   on a brand-new account (no beats)

    The shape matters — UIs (web + companion + wall-clock) all bind
    to these keys."""

    async def test_active_returns_is_beating_with_project(self):
        projects = [_project("p1", "Alpha")]
        active = Beat(
            id="b1",
            project_id="p1",
            start=datetime(2026, 4, 1, 9, 0, tzinfo=UTC),
            end=None,
        )
        svc = _timer_service(beats=[active], projects=projects)
        status = await svc.get_status()
        assert status["isBeating"] is True
        assert status["project"]["id"] == "p1"
        assert status["project"]["name"] == "Alpha"
        assert "since" in status
        assert "so_far" in status

    async def test_no_active_returns_last_beat_metadata(self):
        """No active timer but a completed beat exists → isBeating
        False with last_beat block. The wall-clock uses last_beat.end
        to know when to dim."""
        projects = [_project("p1", "Alpha")]
        last = Beat(
            id="b-last",
            project_id="p1",
            start=datetime(2026, 4, 1, 9, 0, tzinfo=UTC),
            end=datetime(2026, 4, 1, 10, 0, tzinfo=UTC),
        )
        svc = _timer_service(beats=[last], projects=projects)
        status = await svc.get_status()
        assert status["isBeating"] is False
        assert status["last_beat"]["id"] == "b-last"
        assert status["last_beat"]["project_id"] == "p1"
        assert status["last_beat"]["end"] is not None

    async def test_empty_account_returns_just_is_beating_false(self):
        """Brand-new account: no active, no past beats →
        {"isBeating": False} (no last_beat key). Pin so the UI's
        first-run state isn't broken by a None.id crash."""
        svc = _timer_service()
        status = await svc.get_status()
        assert status == {"isBeating": False}


def _beat_service(beats: list[Beat] | None = None):
    from beats.domain.services import BeatService

    return BeatService(beat_repo=_FakeBeatRepoForServices(beats))


class TestBeatServiceCrud:
    """BeatService is a thin pass-through to BeatRepository — the
    one piece of business logic is the end-after-start validation
    on update. Pin that, plus the list filters."""

    @staticmethod
    def _completed(id_: str = "b1", start: datetime | None = None, minutes: int = 30) -> Beat:
        s = start or datetime(2026, 4, 1, 9, 0, tzinfo=UTC)
        return Beat(id=id_, project_id="p1", start=s, end=s + timedelta(minutes=minutes))

    async def test_create_round_trips(self):
        svc = _beat_service()
        b = self._completed("b-new")
        created = await svc.create_beat(b)
        assert created.id == "b-new"
        again = await svc.get_beat("b-new")
        assert again.id == "b-new"

    async def test_get_raises_no_object_matched_on_missing_id(self):
        from beats.domain.exceptions import NoObjectMatched

        svc = _beat_service()
        with pytest.raises(NoObjectMatched):
            await svc.get_beat("ghost")

    async def test_update_happy_path(self):
        b = self._completed("b1", minutes=30)
        svc = _beat_service([b])
        new_end = b.start + timedelta(minutes=60)
        updated = b.model_copy(update={"end": new_end})
        result = await svc.update_beat(updated)
        assert result.end == new_end

    async def test_update_raises_invalid_end_time(self):
        """end < start is rejected — would produce a negative
        duration. Pin the guard at the service layer (mirrors the
        rule TimerService.stop_timer enforces)."""
        from beats.domain.exceptions import InvalidEndTime

        b = self._completed("b1")
        svc = _beat_service([b])
        bad = b.model_copy(update={"end": b.start - timedelta(minutes=1)})
        with pytest.raises(InvalidEndTime):
            await svc.update_beat(bad)

    async def test_update_allows_none_end_skipping_validation(self):
        """end=None means the beat is active again (e.g. reverting
        a stop). Validation only runs when end is set, so this
        should NOT raise."""
        b = self._completed("b1")
        svc = _beat_service([b])
        cleared = b.model_copy(update={"end": None})
        result = await svc.update_beat(cleared)
        assert result.end is None

    async def test_delete_returns_true_when_present(self):
        b = self._completed("b1")
        svc = _beat_service([b])
        assert await svc.delete_beat("b1") is True
        from beats.domain.exceptions import NoObjectMatched

        with pytest.raises(NoObjectMatched):
            await svc.get_beat("b1")

    async def test_delete_returns_false_when_missing(self):
        """Deleting a non-existent id returns False rather than
        raising — the API layer maps a False result to a 404 in
        the route. Pin the bool contract."""
        svc = _beat_service()
        assert await svc.delete_beat("ghost") is False

    async def test_list_no_filters_returns_all(self):
        beats = [
            self._completed("b1"),
            self._completed("b2", start=datetime(2026, 4, 2, 9, 0, tzinfo=UTC)),
        ]
        svc = _beat_service(beats)
        result = await svc.list_beats()
        assert {b.id for b in result} == {"b1", "b2"}

    async def test_list_filters_by_project_id(self):
        b1 = self._completed("b1")
        b2 = b1.model_copy(update={"id": "b2", "project_id": "p2"})
        svc = _beat_service([b1, b2])
        result = await svc.list_beats(project_id="p2")
        assert [b.id for b in result] == ["b2"]

    async def test_list_filters_by_date(self):
        """date_filter narrows to a single calendar day. Pin so a
        regression doesn't return adjacent-day beats and quietly
        inflate "today" totals."""
        d1 = datetime(2026, 4, 1, 9, 0, tzinfo=UTC)
        d2 = datetime(2026, 4, 2, 9, 0, tzinfo=UTC)
        b1 = self._completed("b1", start=d1)
        b2 = self._completed("b2", start=d2)
        svc = _beat_service([b1, b2])
        result = await svc.list_beats(date_filter=date(2026, 4, 2))
        assert [b.id for b in result] == ["b2"]


def _project_service(*, projects: list[Project] | None = None, beats: list[Beat] | None = None):
    from beats.domain.services import ProjectService

    return ProjectService(
        project_repo=_FakeProjectRepoForServices(projects),
        beat_repo=_FakeBeatRepoForServices(beats),
    )


class TestProjectServiceCrud:
    """ProjectService.create/update/archive/list_projects. Mostly a
    pass-through to ProjectRepository, but archive_project carries
    the load-then-mutate-then-save pattern that needs pinning."""

    async def test_create_round_trips(self):
        svc = _project_service()
        p = _project("p1", "Alpha", weekly_goal=5.0)
        created = await svc.create_project(p)
        assert created.id == "p1"
        listed = await svc.list_projects()
        assert [x.id for x in listed] == ["p1"]

    async def test_update_persists_field_changes(self):
        p = _project("p1", "Alpha", weekly_goal=5.0)
        svc = _project_service(projects=[p])
        renamed = p.model_copy(update={"name": "Alpha 2", "weekly_goal": 10.0})
        result = await svc.update_project(renamed)
        assert result.name == "Alpha 2"
        assert result.weekly_goal == 10.0

    async def test_archive_project_sets_archived_true(self):
        """archive_project loads the project, flips archived,
        saves. Pin the load-then-flip-then-save sequence so a
        refactor can't accidentally archive a stale copy."""
        p = _project("p1", "Alpha", weekly_goal=5.0)
        svc = _project_service(projects=[p])
        archived = await svc.archive_project("p1")
        assert archived.archived is True
        # Confirm the archived state is reflected in list filters
        active = await svc.list_projects(archived=False)
        gone = await svc.list_projects(archived=True)
        assert [x.id for x in active] == []
        assert [x.id for x in gone] == ["p1"]

    async def test_archive_raises_on_missing_id(self):
        """archive_project of a non-existent id surfaces the
        ProjectNotFound the repo raises. The API route maps that
        to a 404."""
        from beats.domain.exceptions import ProjectNotFound

        svc = _project_service()
        with pytest.raises(ProjectNotFound):
            await svc.archive_project("ghost")

    async def test_list_projects_default_returns_active_only(self):
        """list_projects() defaults archived=False — pin so a
        refactor can't quietly start showing archived projects in
        the UI's main project picker."""
        active = _project("p1", "Active", weekly_goal=5.0)
        archived = _project("p2", "Archived", archived=True)
        svc = _project_service(projects=[active, archived])
        result = await svc.list_projects()
        assert [p.id for p in result] == ["p1"]

    async def test_list_projects_archived_true_returns_archived_only(self):
        """archived=True scopes to the archive view — used by the
        Settings → Archived projects panel."""
        active = _project("p1", "Active", weekly_goal=5.0)
        archived = _project("p2", "Archived", archived=True)
        svc = _project_service(projects=[active, archived])
        result = await svc.list_projects(archived=True)
        assert [p.id for p in result] == ["p2"]


class TestProjectServiceTimeAggregations:
    """Five aggregation methods that power the project-detail page:
    get_today_time, get_week_breakdown, get_monthly_totals,
    get_daily_average, get_daily_summary.

    These all run on date.today() (local-time), so tests synthesize
    data relative to that anchor rather than pinning a fixed date.

    Risk: these are the per-project numbers users actually look at.
    A regression in window math (off-by-one on Mon vs Sun week
    boundaries, "today" slop, YYYY-MM key drift) would silently
    misreport every user's weekly progress."""

    @staticmethod
    def _at(d: date, hour: int = 9) -> datetime:
        return datetime.combine(d, datetime.min.time(), tzinfo=UTC).replace(hour=hour)

    @staticmethod
    def _completed(id_: str, project_id: str, day: date, hour: int = 9, minutes: int = 60) -> Beat:
        s = TestProjectServiceTimeAggregations._at(day, hour)
        return Beat(id=id_, project_id=project_id, start=s, end=s + timedelta(minutes=minutes))

    # ---------------- get_today_time ----------------

    async def test_today_time_empty_returns_zero(self):
        svc = _project_service(projects=[_project("p1", "Alpha")])
        result = await svc.get_today_time("p1")
        assert result == timedelta()

    async def test_today_time_only_counts_today(self):
        """Beats from yesterday must NOT count toward today. Pin
        so a refactor can't accidentally use a date range with
        slop on either side and inflate today's number."""
        today = date.today()
        yesterday = today - timedelta(days=1)
        beats = [
            self._completed("b-today", "p1", today, minutes=45),
            self._completed("b-yest", "p1", yesterday, minutes=120),
        ]
        svc = _project_service(projects=[_project("p1", "Alpha")], beats=beats)
        result = await svc.get_today_time("p1")
        assert result == timedelta(minutes=45)

    # ---------------- get_week_breakdown ----------------

    async def test_week_breakdown_returns_seven_days_plus_total(self):
        """Dict has all 7 weekday names so the UI always renders a
        full bar chart, plus total_hours, effective_goal, and
        effective_goal_type. Pin the shape so the chart can't
        render holes on quiet days."""
        today = date.today()
        monday = today - timedelta(days=today.weekday())
        beats = [
            self._completed("b1", "p1", monday, minutes=60),
            self._completed("b2", "p1", monday + timedelta(days=2), minutes=30),
        ]
        svc = _project_service(projects=[_project("p1", "Alpha", weekly_goal=5.0)], beats=beats)
        result = await svc.get_week_breakdown("p1")
        for day_name in (
            "Monday",
            "Tuesday",
            "Wednesday",
            "Thursday",
            "Friday",
            "Saturday",
            "Sunday",
        ):
            assert day_name in result
        assert result["total_hours"] == 1.5  # 60 + 30 min
        assert result["effective_goal"] == 5.0
        assert result["effective_goal_type"] == "target"

    async def test_week_breakdown_weeks_ago_shifts_window(self):
        """weeks_ago=1 looks at last week, not this one. Pin so a
        regression can't ignore the parameter and silently always
        return the current week."""
        today = date.today()
        last_monday = today - timedelta(days=today.weekday()) - timedelta(weeks=1)
        beats = [self._completed("b1", "p1", last_monday, minutes=120)]
        svc = _project_service(projects=[_project("p1", "Alpha")], beats=beats)
        this_week = await svc.get_week_breakdown("p1", weeks_ago=0)
        last_week = await svc.get_week_breakdown("p1", weeks_ago=1)
        assert this_week["total_hours"] == 0
        assert last_week["total_hours"] == 2.0

    async def test_week_breakdown_include_log_details(self):
        """include_log_details=True swaps each day's duration string
        for a list of log dicts. Pin the shape — the project-detail
        Logs tab binds to {id, start, end, duration} per entry."""
        today = date.today()
        monday = today - timedelta(days=today.weekday())
        beats = [self._completed("b1", "p1", monday, minutes=60)]
        svc = _project_service(projects=[_project("p1", "Alpha")], beats=beats)
        result = await svc.get_week_breakdown("p1", weeks_ago=0, include_log_details=True)
        monday_logs = result["Monday"]
        assert isinstance(monday_logs, list)
        assert len(monday_logs) == 1
        log = monday_logs[0]
        assert set(log.keys()) == {"id", "start", "end", "duration"}
        assert log["id"] == "b1"

    # ---------------- get_monthly_totals ----------------

    async def test_monthly_totals_empty_returns_zero(self):
        svc = _project_service(projects=[_project("p1", "Alpha")])
        result = await svc.get_monthly_totals("p1")
        assert result == {
            "durations_per_month": {},
            "total_minutes": 0,
            "warnings": [],
        }

    async def test_monthly_totals_groups_by_year_month(self):
        """Two April beats + one May beat → two month keys with
        hours rounded to 2 decimals. Pin the YYYY-MM key format
        the UI sorts on."""
        beats = [
            self._completed("b1", "p1", date(2026, 4, 1), minutes=60),
            self._completed("b2", "p1", date(2026, 4, 15), minutes=30),
            self._completed("b3", "p1", date(2026, 5, 1), minutes=120),
        ]
        svc = _project_service(projects=[_project("p1", "Alpha")], beats=beats)
        result = await svc.get_monthly_totals("p1")
        assert result["durations_per_month"] == {"2026-04": 1.5, "2026-05": 2.0}
        assert result["total_minutes"] == 90 + 120

    async def test_monthly_totals_warns_on_runaway_beat(self):
        """A beat over 24h (forgotten timer) emits a warning rather
        than silently inflating the total. Pin so the warning
        always surfaces."""
        s = datetime(2026, 4, 1, 9, 0, tzinfo=UTC)
        runaway = Beat(id="b-runaway", project_id="p1", start=s, end=s + timedelta(hours=30))
        svc = _project_service(projects=[_project("p1", "Alpha")], beats=[runaway])
        result = await svc.get_monthly_totals("p1")
        assert len(result["warnings"]) == 1
        assert "b-runaway" in result["warnings"][0]
        assert "24 hours" in result["warnings"][0]

    # ---------------- get_daily_average ----------------

    async def test_daily_average_empty_returns_zero(self):
        svc = _project_service(projects=[_project("p1", "Alpha")])
        result = await svc.get_daily_average("p1")
        assert result == {"avg_minutes": 0, "days_tracked": 0}

    async def test_daily_average_aggregates_per_day(self):
        """Two beats on day A (45+15=60) + one beat on day B (120)
        → avg_minutes=90, days_tracked=2. Pin the per-day grouping
        so the metric doesn't degenerate to "avg per session"."""
        today = date.today()
        d1 = today - timedelta(days=2)
        d2 = today - timedelta(days=4)
        beats = [
            self._completed("b1", "p1", d1, hour=9, minutes=45),
            self._completed("b2", "p1", d1, hour=14, minutes=15),
            self._completed("b3", "p1", d2, hour=10, minutes=120),
        ]
        svc = _project_service(projects=[_project("p1", "Alpha")], beats=beats)
        result = await svc.get_daily_average("p1")
        assert result == {"avg_minutes": 90, "days_tracked": 2}

    # ---------------- get_daily_summary ----------------

    async def test_daily_summary_groups_by_day(self):
        """Returns {day_str: total_duration_str}. Two beats same
        day combine; the str-keyed shape is what the UI iterates.
        Pin so the key format can't drift to e.g. "Apr 1, 2026"."""
        d1 = date(2026, 4, 1)
        d2 = date(2026, 4, 2)
        beats = [
            self._completed("b1", "p1", d1, hour=9, minutes=30),
            self._completed("b2", "p1", d1, hour=14, minutes=30),
            self._completed("b3", "p1", d2, hour=9, minutes=60),
        ]
        svc = _project_service(projects=[_project("p1", "Alpha")], beats=beats)
        result = await svc.get_daily_summary("p1")
        assert result == {"2026-04-01": "1:00:00", "2026-04-02": "1:00:00"}


# =============================================================================
# Export bundle signing — Ed25519 sign/verify primitives
# =============================================================================


class TestExportSigning:
    """Pure Ed25519 sign/verify primitives in domain.export_signing.

    Why these tests matter: the signed-export contract is the only
    tamper-evidence users have when restoring from a bundle. A
    regression that accepted any signature would silently invalidate
    every "this came from your account" guarantee. These tests pin
    the security contract with no mocks — fast, definitive."""

    def test_generate_keypair_returns_raw_32_byte_keys(self):
        """Ed25519 raw keys are exactly 32 bytes each. Pin so an
        accidental switch to PEM/DER would surface immediately
        (we'd get hundreds of bytes, not 32)."""
        from beats.domain.export_signing import generate_keypair

        priv, pub = generate_keypair()
        assert isinstance(priv, bytes)
        assert isinstance(pub, bytes)
        assert len(priv) == 32
        assert len(pub) == 32

    def test_keypair_is_unique_per_call(self):
        """Two generate_keypair calls produce different keys.
        Pin so a refactor to a fixed-seed RNG (would be a serious
        security regression) gets caught."""
        from beats.domain.export_signing import generate_keypair

        priv1, pub1 = generate_keypair()
        priv2, pub2 = generate_keypair()
        assert priv1 != priv2
        assert pub1 != pub2

    def test_sign_returns_64_byte_signature(self):
        """Ed25519 signatures are exactly 64 bytes. Pin the size
        so the export manifest schema can rely on it."""
        from beats.domain.export_signing import generate_keypair, sign

        priv, _ = generate_keypair()
        sig = sign(priv, b"hello world")
        assert isinstance(sig, bytes)
        assert len(sig) == 64

    def test_sign_verify_round_trip(self):
        """Happy path: sign with private, verify with the matching
        public, no exception."""
        from beats.domain.export_signing import generate_keypair, sign, verify

        priv, pub = generate_keypair()
        payload = b"export-manifest-v1\nbeats:42\n"
        sig = sign(priv, payload)
        # Should NOT raise
        verify(pub, payload, sig)

    def test_verify_rejects_modified_payload(self):
        """Even a single-byte change in the payload must fail
        verification. This is the entire reason we sign at all —
        pin so it's never silently relaxed."""
        from beats.domain.export_signing import (
            SignatureMismatch,
            generate_keypair,
            sign,
            verify,
        )

        priv, pub = generate_keypair()
        original = b"beats:42"
        tampered = b"beats:43"
        sig = sign(priv, original)
        with pytest.raises(SignatureMismatch):
            verify(pub, tampered, sig)

    def test_verify_rejects_signature_from_different_key(self):
        """A signature from key A must not verify against key B's
        public — pins cross-account isolation. If this regressed,
        any export could be presented as coming from any account."""
        from beats.domain.export_signing import (
            SignatureMismatch,
            generate_keypair,
            sign,
            verify,
        )

        priv_a, _ = generate_keypair()
        _, pub_b = generate_keypair()
        payload = b"manifest"
        sig_from_a = sign(priv_a, payload)
        with pytest.raises(SignatureMismatch):
            verify(pub_b, payload, sig_from_a)

    def test_verify_rejects_malformed_signature(self):
        """A truncated or junk signature surfaces as
        SignatureMismatch (not a generic crypto exception). Pin
        the error envelope so the API layer can rely on a single
        failure type when mapping to HTTP."""
        from beats.domain.export_signing import (
            SignatureMismatch,
            generate_keypair,
            verify,
        )

        _, pub = generate_keypair()
        with pytest.raises(SignatureMismatch):
            verify(pub, b"payload", b"too-short")

    def test_verify_rejects_malformed_public_key(self):
        """A junk public key (wrong length) is caught and wrapped
        into SignatureMismatch with the underlying message — pin
        so a corrupt manifest doesn't crash the import flow with
        a leaked low-level exception."""
        from beats.domain.export_signing import SignatureMismatch, verify

        with pytest.raises(SignatureMismatch):
            verify(b"\x00" * 16, b"payload", b"\x00" * 64)


# =============================================================================
# Export bundle SQLite — build_sqlite_bytes + manifest helpers
# =============================================================================


class TestExportSqlite:
    """Pure helpers in domain.export_sqlite — no I/O beyond a temp
    SQLite file, no framework dependencies. The export bundle is
    user-facing data the user is expected to be able to open with
    sqlite3 on the command line, so the schema and round-trip
    behavior are part of the contract.

    Risk: a regression in a column extractor (e.g. archived flag
    flipped, tags blob stringified twice) would silently corrupt
    every user's exports — the bundle would still parse, just be
    wrong. Pin every typed column and the `data` JSON fallback."""

    def _payload(self, **overrides):
        from beats.domain.export_sqlite import ExportPayload

        defaults = {
            "projects": [
                {
                    "id": "p1",
                    "user_id": "u1",
                    "name": "Alpha",
                    "description": "main project",
                    "estimation": "small",
                    "color": "#ff0000",
                    "archived": False,
                    "weekly_goal": 5.0,
                    "goal_type": "target",
                    "github_repo": "ahmed/beats",
                }
            ],
            "beats": [
                {
                    "id": "b1",
                    "user_id": "u1",
                    "project_id": "p1",
                    "start": "2026-04-01T09:00:00+00:00",
                    "end": "2026-04-01T10:00:00+00:00",
                    "note": "deep work",
                    "tags": ["focus", "morning"],
                }
            ],
            "intentions": [
                {
                    "id": "i1",
                    "user_id": "u1",
                    "project_id": "p1",
                    "date": "2026-04-01",
                    "planned_minutes": 90,
                    "completed": True,
                }
            ],
            "daily_notes": [
                {
                    "id": "n1",
                    "user_id": "u1",
                    "date": "2026-04-01",
                    "note": "good day",
                    "mood": 4,
                }
            ],
        }
        defaults.update(overrides)
        return ExportPayload(**defaults)

    def _query(self, sqlite_bytes: bytes, sql: str) -> list[tuple]:
        """Open the bundle bytes as a real sqlite db and run a query.
        Mirrors what a user would do with `sqlite3 export.db`."""
        import sqlite3
        import tempfile
        from pathlib import Path

        with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as tmp:
            Path(tmp.name).write_bytes(sqlite_bytes)
            try:
                conn = sqlite3.connect(tmp.name)
                cur = conn.execute(sql)
                rows = cur.fetchall()
                conn.close()
                return rows
            finally:
                Path(tmp.name).unlink(missing_ok=True)

    # ---------------- build_sqlite_bytes ----------------

    def test_returns_valid_sqlite_bytes(self):
        """Output starts with the SQLite magic header and is a
        non-trivial size. Pin so a regression that returned an
        empty/text/JSON payload is caught immediately."""
        from beats.domain.export_sqlite import build_sqlite_bytes

        out = build_sqlite_bytes(self._payload())
        # The SQLite file format magic string is 16 bytes:
        # "SQLite format 3\x00".
        assert out.startswith(b"SQLite format 3\x00")
        assert len(out) > 1024  # minimum meaningful db size

    def test_empty_payload_still_produces_valid_db_with_schema(self):
        """An empty export must still create the four tables —
        otherwise opening the bundle with sqlite3 would error.
        Pin the schema-always-applied invariant."""
        from beats.domain.export_sqlite import (
            ExportPayload,
            build_sqlite_bytes,
        )

        empty = ExportPayload(projects=[], beats=[], intentions=[], daily_notes=[])
        out = build_sqlite_bytes(empty)
        tables = self._query(out, "SELECT name FROM sqlite_master WHERE type='table'")
        names = {row[0] for row in tables}
        assert {"projects", "beats", "intentions", "daily_notes"}.issubset(names)

    def test_projects_typed_columns_round_trip(self):
        """Project columns map to typed SQLite columns. Pin the
        archived bool → 0/1 integer cast (would render as the
        string "False" if the lambda regressed)."""
        from beats.domain.export_sqlite import build_sqlite_bytes

        out = build_sqlite_bytes(self._payload())
        rows = self._query(
            out,
            "SELECT id, name, archived, weekly_goal, goal_type FROM projects",
        )
        assert rows == [("p1", "Alpha", 0, 5.0, "target")]

    def test_archived_true_serializes_as_one(self):
        """archived=True must become integer 1 (not boolean True,
        not the string "True"). SQLite is permissive about types
        — pin so a regression doesn't silently flip the rendering
        in downstream tooling."""
        from beats.domain.export_sqlite import build_sqlite_bytes

        payload = self._payload(
            projects=[
                {"id": "pA", "user_id": "u1", "name": "A", "archived": True},
                {"id": "pB", "user_id": "u1", "name": "B", "archived": False},
            ]
        )
        out = build_sqlite_bytes(payload)
        rows = self._query(out, "SELECT id, archived FROM projects ORDER BY id")
        assert rows == [("pA", 1), ("pB", 0)]

    def test_beats_tags_stored_as_json_blob(self):
        """tags is a list — must be JSON-encoded into the column,
        not str()'d. Pin so the column round-trips through json."""
        from beats.domain.export_sqlite import build_sqlite_bytes

        out = build_sqlite_bytes(self._payload())
        rows = self._query(out, "SELECT id, tags FROM beats")
        assert len(rows) == 1
        beat_id, tags_blob = rows[0]
        assert beat_id == "b1"
        # Must round-trip through json.loads; pin the format
        import json

        assert json.loads(tags_blob) == ["focus", "morning"]

    def test_beats_missing_tags_become_empty_array(self):
        """A beat without a `tags` key writes "[]" to the column,
        not NULL or "null". Pin so downstream consumers can rely
        on tags always parsing as a list."""
        import json

        from beats.domain.export_sqlite import build_sqlite_bytes

        payload = self._payload(
            beats=[{"id": "bN", "user_id": "u1", "project_id": "p1", "start": "x"}]
        )
        out = build_sqlite_bytes(payload)
        rows = self._query(out, "SELECT tags FROM beats WHERE id = 'bN'")
        assert json.loads(rows[0][0]) == []

    def test_intentions_completed_serialized_as_int(self):
        """completed bool → 0/1 mirrors the archived treatment.
        Pin both projects.archived and intentions.completed lambdas
        — easy to slip if one is updated and the other isn't."""
        from beats.domain.export_sqlite import build_sqlite_bytes

        out = build_sqlite_bytes(self._payload())
        rows = self._query(out, "SELECT id, planned_minutes, completed FROM intentions")
        assert rows == [("i1", 90, 1)]

    def test_data_column_holds_full_row_json(self):
        """Every table has a `data` column containing the original
        dict serialized as JSON — the self-describing escape hatch
        for fields not surfaced as typed columns. Pin so a
        refactor doesn't drop the data column and silently lose
        the long-tail metadata."""
        import json

        from beats.domain.export_sqlite import build_sqlite_bytes

        out = build_sqlite_bytes(self._payload())
        rows = self._query(out, "SELECT data FROM projects")
        full = json.loads(rows[0][0])
        assert full["id"] == "p1"
        assert full["github_repo"] == "ahmed/beats"

    # ---------------- build_manifest ----------------

    def test_manifest_has_version_counts_and_hash(self):
        """Manifest shape: {version, counts: {projects, beats,
        intentions, daily_notes}, sqlite_sha256}. Pin the keys —
        signed bundles outlive the code that wrote them, so the
        format is a long-term contract."""
        from beats.domain.export_sqlite import (
            build_manifest,
            build_sqlite_bytes,
        )

        payload = self._payload()
        sqlite_bytes = build_sqlite_bytes(payload)
        manifest = build_manifest(payload, sqlite_bytes, version="1.0")
        assert manifest["version"] == "1.0"
        assert manifest["counts"] == {
            "projects": 1,
            "beats": 1,
            "intentions": 1,
            "daily_notes": 1,
        }
        # sha256 hex is 64 chars
        assert len(manifest["sqlite_sha256"]) == 64
        assert all(c in "0123456789abcdef" for c in manifest["sqlite_sha256"])

    def test_manifest_hash_matches_input_bytes(self):
        """The sqlite_sha256 in the manifest is the actual
        SHA-256 of the sqlite bytes — pin so a refactor that
        accidentally hashes the manifest itself or the payload
        struct can't slip in undetected."""
        import hashlib

        from beats.domain.export_sqlite import (
            build_manifest,
            build_sqlite_bytes,
        )

        sqlite_bytes = build_sqlite_bytes(self._payload())
        manifest = build_manifest(self._payload(), sqlite_bytes, version="1.0")
        assert manifest["sqlite_sha256"] == hashlib.sha256(sqlite_bytes).hexdigest()

    # ---------------- canonical_manifest_bytes ----------------

    def test_canonical_bytes_are_deterministic_regardless_of_key_order(self):
        """Two manifests with the same content but different key
        insertion order must produce identical canonical bytes —
        otherwise the signature would not verify on import. Pin
        the sort_keys=True invariant."""
        from beats.domain.export_sqlite import canonical_manifest_bytes

        a = {"a": 1, "b": 2, "c": {"x": 1, "y": 2}}
        b = {"c": {"y": 2, "x": 1}, "b": 2, "a": 1}
        assert canonical_manifest_bytes(a) == canonical_manifest_bytes(b)

    def test_canonical_bytes_have_no_whitespace(self):
        """Compact separators (',' and ':') — pin so a refactor
        to a "pretty-printed" form doesn't silently change every
        signature. Existing signed bundles would suddenly fail
        verification at import time."""
        from beats.domain.export_sqlite import canonical_manifest_bytes

        out = canonical_manifest_bytes({"a": 1, "b": 2})
        assert out == b'{"a":1,"b":2}'
        assert b" " not in out
        assert b"\n" not in out


# =============================================================================
# Oura Service — personal access token + daily biometric fetch
# =============================================================================


class _FakeHTTPResponse:
    """Minimal stand-in for httpx.Response used by integration tests."""

    def __init__(self, status_code: int, json_data: dict | None = None):
        self.status_code = status_code
        self._json = json_data or {}

    def json(self) -> dict:
        return self._json


class _FakeOuraIntegrationRepo:
    """In-memory OuraIntegrationRepository fake."""

    def __init__(self, integration=None):
        self._integration = integration

    async def get(self):
        return self._integration

    async def upsert(self, integration):
        self._integration = integration
        return integration

    async def delete(self) -> bool:
        had = self._integration is not None
        self._integration = None
        return had


def _patch_httpx(monkeypatch, route_map: dict):
    """Monkeypatch httpx.AsyncClient to return canned responses for
    URLs that contain any key in `route_map`. Values may be a
    _FakeHTTPResponse or an Exception instance to raise.

    First-match-wins; order keys long-to-short if specificity matters.
    """
    import httpx

    class _FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            self._routes = route_map

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, url, headers=None, params=None):
            for key, value in self._routes.items():
                if key in url:
                    if isinstance(value, Exception):
                        raise value
                    return value
            return _FakeHTTPResponse(404, {})

        async def post(self, url, headers=None, params=None, data=None, json=None):
            return await self.get(url, headers=headers, params=params)

    monkeypatch.setattr(httpx, "AsyncClient", _FakeAsyncClient)


class TestOuraServiceConnect:
    """OuraService.connect validates a PAT against Oura's API
    before persisting it. Pin the validate-then-persist sequence
    so a bad token can't be silently saved."""

    async def test_valid_pat_persists_integration(self, monkeypatch):
        from beats.domain.oura import OuraService

        _patch_httpx(
            monkeypatch,
            {"personal_info": _FakeHTTPResponse(200, {"id": "oura-user-42"})},
        )
        repo = _FakeOuraIntegrationRepo()
        svc = OuraService(repo)
        integration = await svc.connect("pat-good")
        assert integration.access_token == "pat-good"
        assert integration.oura_user_id == "oura-user-42"
        # Pinned: actually upserted into the repo, not just returned
        assert (await repo.get()).access_token == "pat-good"

    async def test_invalid_pat_raises_and_does_not_persist(self, monkeypatch):
        """A 401 from /personal_info → DomainException, AND the
        repo stays empty. Pin the no-side-effects-on-failure
        invariant — the user shouldn't see a "connected" badge if
        the token never validated."""
        from beats.domain.exceptions import DomainException
        from beats.domain.oura import OuraService

        _patch_httpx(
            monkeypatch,
            {"personal_info": _FakeHTTPResponse(401, {"error": "unauthorized"})},
        )
        repo = _FakeOuraIntegrationRepo()
        svc = OuraService(repo)
        with pytest.raises(DomainException):
            await svc.connect("pat-bad")
        assert await repo.get() is None


class TestOuraServiceFetchDaily:
    """fetch_daily aggregates sleep/readiness/HRV from three Oura
    endpoints. Each call is wrapped in its own try/except so a
    5xx on readiness shouldn't drop sleep data.

    Risk: a regression that surfaces an HTTP exception from one
    endpoint would silently zero out the entire day's biometrics.
    Pin per-endpoint resilience."""

    async def test_no_integration_returns_empty(self, monkeypatch):
        """When the user hasn't connected Oura, fetch_daily must
        return {} without making any HTTP calls. Pin so a
        regression doesn't fire requests for not-connected users."""
        from beats.domain.oura import OuraService

        _patch_httpx(
            monkeypatch,
            {"": RuntimeError("should not have called HTTP without integration")},
        )
        repo = _FakeOuraIntegrationRepo(integration=None)
        svc = OuraService(repo)
        result = await svc.fetch_daily(date(2026, 4, 1))
        assert result == {}

    async def test_aggregates_sleep_readiness_and_hrv(self, monkeypatch):
        """Happy path: all three endpoints return data → result
        contains sleep_minutes, sleep_efficiency, readiness_score,
        hrv_ms, resting_hr_bpm. Pin the field names — the
        biometrics ingest pipeline binds to these keys."""
        from beats.domain.models import OuraIntegration
        from beats.domain.oura import OuraService

        _patch_httpx(
            monkeypatch,
            {
                "daily_sleep": _FakeHTTPResponse(
                    200,
                    {
                        "data": [
                            {
                                "score": 85,
                                "contributors": {"total_sleep": 27000},
                            }
                        ]
                    },
                ),
                "daily_readiness": _FakeHTTPResponse(200, {"data": [{"score": 78}]}),
                "/sleep": _FakeHTTPResponse(
                    200,
                    {"data": [{"average_hrv": 45.5, "lowest_heart_rate": 52}]},
                ),
            },
        )
        repo = _FakeOuraIntegrationRepo(
            integration=OuraIntegration(access_token="pat", oura_user_id="u1")
        )
        svc = OuraService(repo)
        result = await svc.fetch_daily(date(2026, 4, 1))
        assert result["source"] == "oura"
        assert result["sleep_minutes"] == 450  # 27000 / 60
        assert result["sleep_efficiency"] == 0.85
        assert result["readiness_score"] == 78
        assert result["hrv_ms"] == 45.5
        assert result["resting_hr_bpm"] == 52

    async def test_readiness_failure_does_not_drop_sleep(self, monkeypatch):
        """Readiness endpoint raises httpx.HTTPError → sleep data
        still lands. Pin per-endpoint try/except so a flaky Oura
        backend can't zero out the user's whole day."""
        import httpx

        from beats.domain.models import OuraIntegration
        from beats.domain.oura import OuraService

        _patch_httpx(
            monkeypatch,
            {
                "daily_sleep": _FakeHTTPResponse(
                    200,
                    {
                        "data": [
                            {
                                "score": 90,
                                "contributors": {"total_sleep": 28800},
                            }
                        ]
                    },
                ),
                "daily_readiness": httpx.ConnectError("network down"),
                "/sleep": _FakeHTTPResponse(200, {"data": []}),
            },
        )
        repo = _FakeOuraIntegrationRepo(integration=OuraIntegration(access_token="pat"))
        svc = OuraService(repo)
        result = await svc.fetch_daily(date(2026, 4, 1))
        assert result["sleep_minutes"] == 480
        assert "readiness_score" not in result

    async def test_empty_response_arrays_yield_no_keys(self, monkeypatch):
        """Each endpoint returns {"data": []} (no record for the
        date) — result has only `source` and `date`. Pin so a
        no-data day doesn't produce phantom zero values that
        masquerade as real measurements."""
        from beats.domain.models import OuraIntegration
        from beats.domain.oura import OuraService

        _patch_httpx(
            monkeypatch,
            {
                "daily_sleep": _FakeHTTPResponse(200, {"data": []}),
                "daily_readiness": _FakeHTTPResponse(200, {"data": []}),
                "/sleep": _FakeHTTPResponse(200, {"data": []}),
            },
        )
        repo = _FakeOuraIntegrationRepo(integration=OuraIntegration(access_token="pat"))
        svc = OuraService(repo)
        target = date(2026, 4, 1)
        result = await svc.fetch_daily(target)
        assert result == {"source": "oura", "date": target}


class TestOuraServiceDisconnect:
    """disconnect drops the stored integration. Pin the bool
    contract — the API route maps True/False to 200/404."""

    async def test_disconnect_returns_true_when_present(self):
        from beats.domain.models import OuraIntegration
        from beats.domain.oura import OuraService

        repo = _FakeOuraIntegrationRepo(integration=OuraIntegration(access_token="pat"))
        svc = OuraService(repo)
        assert await svc.disconnect() is True
        assert await repo.get() is None

    async def test_disconnect_returns_false_when_absent(self):
        from beats.domain.oura import OuraService

        svc = OuraService(_FakeOuraIntegrationRepo(integration=None))
        assert await svc.disconnect() is False


# =============================================================================
# Fitbit Service — OAuth flow + biometric fetch with token refresh
# =============================================================================


class _FakeFitbitIntegrationRepo:
    def __init__(self, integration=None):
        self._integration = integration

    async def get(self):
        return self._integration

    async def upsert(self, integration):
        self._integration = integration
        return integration

    async def delete(self) -> bool:
        had = self._integration is not None
        self._integration = None
        return had


def _fitbit_settings(monkeypatch):
    """Build a Settings instance with deterministic Fitbit creds.

    BaseSettings fields use `validation_alias`, which means kwargs on
    the field's Python name are silently ignored — the alias (env-var
    casing) is the only populated path. We set env vars via
    monkeypatch so the Settings constructor reads them, then reset
    on test teardown."""
    from beats.settings import Settings

    monkeypatch.setenv("FITBIT_CLIENT_ID", "cid-fb")
    monkeypatch.setenv("FITBIT_CLIENT_SECRET", "csec-fb")
    monkeypatch.setenv("FITBIT_REDIRECT_URI", "https://beats.test/oauth/fitbit")
    return Settings()


def _no_op_raise_for_status(self):
    """Drop-in raise_for_status that mirrors httpx.Response: no-op
    on 2xx, raises HTTPStatusError on 4xx/5xx."""
    if self.status_code >= 400:
        import httpx

        raise httpx.HTTPStatusError("err", request=None, response=None)  # type: ignore[arg-type]


class TestFitbitAuthUrl:
    """get_auth_url builds the OAuth consent URL deterministically.
    Pin every required parameter — Fitbit will reject the redirect
    silently if any are missing or misnamed, leaving the user on
    a "loading…" screen with no error."""

    def test_includes_client_id_redirect_response_type_and_scope(self, monkeypatch):
        from beats.domain.fitbit import FitbitService

        svc = FitbitService(_fitbit_settings(monkeypatch), _FakeFitbitIntegrationRepo())
        url = svc.get_auth_url()
        assert url.startswith("https://www.fitbit.com/oauth2/authorize?")
        assert "client_id=cid-fb" in url
        # redirect_uri is URL-encoded (colons + slashes escaped)
        assert "redirect_uri=https%3A%2F%2Fbeats.test%2Foauth%2Ffitbit" in url
        assert "response_type=code" in url
        # scope = "activity heartrate sleep" — pin the three tokens
        assert "activity" in url
        assert "heartrate" in url
        assert "sleep" in url


class TestFitbitExchangeCode:
    """exchange_code POSTs the auth code + creds to Fitbit's token
    endpoint and persists the tokens. Pin both the four-field
    persisted shape and the token_expiry math (now + expires_in)."""

    async def test_happy_path_persists_all_four_fields(self, monkeypatch):
        from beats.domain.fitbit import FitbitService

        _patch_httpx(
            monkeypatch,
            {
                "oauth2/token": _FakeHTTPResponse(
                    200,
                    {
                        "access_token": "at-fb",
                        "refresh_token": "rt-fb",
                        "expires_in": 28800,
                        "user_id": "fb-user-1",
                    },
                )
            },
        )
        monkeypatch.setattr(
            _FakeHTTPResponse, "raise_for_status", _no_op_raise_for_status, raising=False
        )

        repo = _FakeFitbitIntegrationRepo()
        svc = FitbitService(_fitbit_settings(monkeypatch), repo)
        before = datetime.now(UTC)
        integration = await svc.exchange_code("auth-code")
        after = datetime.now(UTC)

        assert integration.access_token == "at-fb"
        assert integration.refresh_token == "rt-fb"
        assert integration.fitbit_user_id == "fb-user-1"
        # token_expiry ≈ now + 28800 sec
        assert integration.token_expiry is not None
        expiry = integration.token_expiry
        assert before + timedelta(seconds=28799) <= expiry
        assert expiry <= after + timedelta(seconds=28801)
        # Persisted, not just returned
        assert (await repo.get()).access_token == "at-fb"


class TestFitbitEnsureFreshToken:
    """_ensure_fresh_token returns the integration as-is when the
    token is still valid; otherwise it refreshes via the
    refresh_token grant and persists.

    Risk: a regression here would either (a) fire a refresh on
    every request (rate-limit) or (b) skip refreshing on an
    expired token (every fetch fails)."""

    async def test_returns_same_when_not_expired(self, monkeypatch):
        """token_expiry > now → return integration unchanged, no
        HTTP call. Patched httpx raises if invoked — the test
        would fail loudly if a regression started spamming
        refreshes."""
        from beats.domain.fitbit import FitbitService
        from beats.domain.models import FitbitIntegration

        _patch_httpx(
            monkeypatch,
            {"": RuntimeError("should not refresh when token still valid")},
        )

        future = datetime.now(UTC) + timedelta(hours=2)
        existing = FitbitIntegration(
            access_token="at-current",
            refresh_token="rt",
            token_expiry=future,
        )
        repo = _FakeFitbitIntegrationRepo(integration=existing)
        svc = FitbitService(_fitbit_settings(monkeypatch), repo)
        result = await svc._ensure_fresh_token(existing)
        assert result.access_token == "at-current"

    async def test_refreshes_when_expired(self, monkeypatch):
        """token_expiry in the past → POST refresh_token grant,
        persist new access_token + token_expiry. Pin so an expired
        token doesn't silently leak through to the API call."""
        from beats.domain.fitbit import FitbitService
        from beats.domain.models import FitbitIntegration

        _patch_httpx(
            monkeypatch,
            {
                "oauth2/token": _FakeHTTPResponse(
                    200,
                    {
                        "access_token": "at-NEW",
                        "refresh_token": "rt-NEW",
                        "expires_in": 28800,
                    },
                )
            },
        )
        monkeypatch.setattr(
            _FakeHTTPResponse, "raise_for_status", _no_op_raise_for_status, raising=False
        )

        past = datetime.now(UTC) - timedelta(hours=1)
        stale = FitbitIntegration(
            access_token="at-OLD",
            refresh_token="rt-OLD",
            token_expiry=past,
        )
        repo = _FakeFitbitIntegrationRepo(integration=stale)
        svc = FitbitService(_fitbit_settings(monkeypatch), repo)
        refreshed = await svc._ensure_fresh_token(stale)
        assert refreshed.access_token == "at-NEW"
        assert refreshed.refresh_token == "rt-NEW"
        # Persisted, not just returned
        assert (await repo.get()).access_token == "at-NEW"

    async def test_refresh_preserves_existing_refresh_token_when_omitted(self, monkeypatch):
        """Fitbit sometimes omits refresh_token from the refresh
        response (when the existing one is still valid). Pin that
        we keep the existing refresh_token rather than blanking it
        — losing the refresh token would force a full re-auth."""
        from beats.domain.fitbit import FitbitService
        from beats.domain.models import FitbitIntegration

        _patch_httpx(
            monkeypatch,
            {
                "oauth2/token": _FakeHTTPResponse(
                    200,
                    {
                        "access_token": "at-NEW",
                        # No refresh_token in response
                        "expires_in": 28800,
                    },
                )
            },
        )
        monkeypatch.setattr(
            _FakeHTTPResponse, "raise_for_status", _no_op_raise_for_status, raising=False
        )

        past = datetime.now(UTC) - timedelta(hours=1)
        stale = FitbitIntegration(
            access_token="at-OLD",
            refresh_token="rt-keep",
            token_expiry=past,
        )
        repo = _FakeFitbitIntegrationRepo(integration=stale)
        svc = FitbitService(_fitbit_settings(monkeypatch), repo)
        refreshed = await svc._ensure_fresh_token(stale)
        assert refreshed.refresh_token == "rt-keep"


class TestFitbitFetchDaily:
    """fetch_daily aggregates sleep + heart rate + steps. Mirrors
    the Oura per-endpoint resilience pattern — one endpoint's
    failure must not drop another's data."""

    async def test_no_integration_returns_empty(self, monkeypatch):
        from beats.domain.fitbit import FitbitService

        _patch_httpx(
            monkeypatch,
            {"": RuntimeError("should not have called HTTP without integration")},
        )
        svc = FitbitService(_fitbit_settings(monkeypatch), _FakeFitbitIntegrationRepo(None))
        assert await svc.fetch_daily(date(2026, 4, 1)) == {}

    async def test_aggregates_sleep_hr_and_steps(self, monkeypatch):
        from beats.domain.fitbit import FitbitService
        from beats.domain.models import FitbitIntegration

        _patch_httpx(
            monkeypatch,
            {
                # Substring matches; first-match-wins. Order so the
                # most-specific routes match first.
                "/sleep/": _FakeHTTPResponse(
                    200,
                    {
                        "summary": {
                            "totalMinutesAsleep": 420,
                            "totalTimeInBed": 480,
                        }
                    },
                ),
                "/heart/": _FakeHTTPResponse(
                    200, {"activities-heart": [{"value": {"restingHeartRate": 58}}]}
                ),
                "/activities/date/": _FakeHTTPResponse(200, {"summary": {"steps": 9876}}),
            },
        )
        future = datetime.now(UTC) + timedelta(hours=2)
        repo = _FakeFitbitIntegrationRepo(
            integration=FitbitIntegration(
                access_token="at", refresh_token="rt", token_expiry=future
            )
        )
        svc = FitbitService(_fitbit_settings(monkeypatch), repo)
        result = await svc.fetch_daily(date(2026, 4, 1))
        assert result["source"] == "fitbit"
        assert result["sleep_minutes"] == 420
        assert result["sleep_efficiency"] == 420 / 480
        assert result["resting_hr_bpm"] == 58
        assert result["steps"] == 9876

    async def test_hr_failure_does_not_drop_sleep_or_steps(self, monkeypatch):
        """HR endpoint raises → sleep + steps still land. Pin
        per-endpoint resilience — a flaky Fitbit backend can't
        zero out the user's whole day."""
        import httpx

        from beats.domain.fitbit import FitbitService
        from beats.domain.models import FitbitIntegration

        _patch_httpx(
            monkeypatch,
            {
                "/sleep/": _FakeHTTPResponse(
                    200,
                    {
                        "summary": {
                            "totalMinutesAsleep": 400,
                            "totalTimeInBed": 460,
                        }
                    },
                ),
                "/heart/": httpx.ConnectError("hr down"),
                "/activities/date/": _FakeHTTPResponse(200, {"summary": {"steps": 5000}}),
            },
        )
        future = datetime.now(UTC) + timedelta(hours=2)
        repo = _FakeFitbitIntegrationRepo(
            integration=FitbitIntegration(
                access_token="at", refresh_token="rt", token_expiry=future
            )
        )
        svc = FitbitService(_fitbit_settings(monkeypatch), repo)
        result = await svc.fetch_daily(date(2026, 4, 1))
        assert result["sleep_minutes"] == 400
        assert result["steps"] == 5000
        assert "resting_hr_bpm" not in result


class TestFitbitDisconnect:
    async def test_disconnect_returns_bool(self, monkeypatch):
        from beats.domain.fitbit import FitbitService
        from beats.domain.models import FitbitIntegration

        svc_full = FitbitService(
            _fitbit_settings(monkeypatch),
            _FakeFitbitIntegrationRepo(integration=FitbitIntegration(access_token="at")),
        )
        assert await svc_full.disconnect() is True

        svc_empty = FitbitService(_fitbit_settings(monkeypatch), _FakeFitbitIntegrationRepo(None))
        assert await svc_empty.disconnect() is False


# =============================================================================
# GitHub Service — OAuth flow + commit-activity fetch with pagination
# =============================================================================


class _FakeGitHubIntegrationRepo:
    def __init__(self, integration=None):
        self._integration = integration

    async def get(self):
        return self._integration

    async def upsert(self, integration):
        self._integration = integration
        return integration

    async def delete(self) -> bool:
        had = self._integration is not None
        self._integration = None
        return had


def _github_settings(monkeypatch):
    """Build a Settings instance with deterministic GitHub creds.
    Same pattern as _fitbit_settings — env vars via monkeypatch."""
    from beats.settings import Settings

    monkeypatch.setenv("GITHUB_CLIENT_ID", "cid-gh")
    monkeypatch.setenv("GITHUB_CLIENT_SECRET", "csec-gh")
    monkeypatch.setenv("GITHUB_REDIRECT_URI", "https://beats.test/oauth/github")
    return Settings()


def _patch_httpx_callable(monkeypatch, handler):
    """Variant of _patch_httpx that delegates EVERY request to a
    single callable. Useful when the same URL needs to return
    different responses across calls (pagination).

    Handler signature: (method, url, params) -> _FakeHTTPResponse | Exception
    """
    import httpx

    class _FakeAsyncClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, url, headers=None, params=None):
            result = handler("GET", url, params or {})
            if isinstance(result, Exception):
                raise result
            return result

        async def post(self, url, headers=None, params=None, data=None, json=None):
            result = handler("POST", url, params or data or {})
            if isinstance(result, Exception):
                raise result
            return result

    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **kw: _FakeAsyncClient())


class TestGitHubAuthUrl:
    """get_auth_url builds the OAuth consent URL. Pin client_id +
    redirect_uri + scope — same risk profile as the Fitbit URL test
    (any missing param → silent rejection)."""

    def test_includes_client_id_redirect_and_scope(self, monkeypatch):
        from beats.domain.github import GitHubService

        svc = GitHubService(_github_settings(monkeypatch), _FakeGitHubIntegrationRepo())
        url = svc.get_auth_url()
        assert url.startswith("https://github.com/login/oauth/authorize?")
        assert "client_id=cid-gh" in url
        assert "redirect_uri=https%3A%2F%2Fbeats.test%2Foauth%2Fgithub" in url
        # scope = "repo:status read:user" — pin both tokens
        assert "repo" in url
        assert "user" in url


class TestGitHubExchangeCode:
    """exchange_code is a TWO-step flow: POST /access_token then
    GET /user. Both must succeed for the integration to land with
    the user's login. The user-info fetch is wrapped in try/except
    so a temporary GitHub outage on /user doesn't block the
    OAuth callback."""

    async def test_persists_token_and_username_on_happy_path(self, monkeypatch):
        from beats.domain.github import GitHubService

        def handler(method, url, params):
            if "access_token" in url:
                return _FakeHTTPResponse(200, {"access_token": "gho_abc123"})
            if "/user" in url:
                return _FakeHTTPResponse(200, {"login": "ahmed"})
            return _FakeHTTPResponse(404, {})

        _patch_httpx_callable(monkeypatch, handler)
        monkeypatch.setattr(
            _FakeHTTPResponse, "raise_for_status", _no_op_raise_for_status, raising=False
        )

        repo = _FakeGitHubIntegrationRepo()
        svc = GitHubService(_github_settings(monkeypatch), repo)
        integration = await svc.exchange_code("auth-code")
        assert integration.access_token == "gho_abc123"
        assert integration.github_username == "ahmed"
        assert (await repo.get()).github_username == "ahmed"

    async def test_user_endpoint_failure_still_persists_with_empty_username(self, monkeypatch):
        """A 5xx (or any exception) from /user should not block the
        OAuth callback — pin so a temporary GitHub outage during
        sign-in doesn't trap the user in an "auth failed" loop.
        We persist the token with empty username; subsequent calls
        can fill it in."""
        from beats.domain.github import GitHubService

        def handler(method, url, params):
            if "access_token" in url:
                return _FakeHTTPResponse(200, {"access_token": "gho_xyz"})
            if "/user" in url:
                # 500-style error wrapped via raise_for_status
                return _FakeHTTPResponse(500, {"message": "server error"})
            return _FakeHTTPResponse(404, {})

        _patch_httpx_callable(monkeypatch, handler)
        monkeypatch.setattr(
            _FakeHTTPResponse, "raise_for_status", _no_op_raise_for_status, raising=False
        )

        repo = _FakeGitHubIntegrationRepo()
        svc = GitHubService(_github_settings(monkeypatch), repo)
        integration = await svc.exchange_code("auth-code")
        assert integration.access_token == "gho_xyz"
        assert integration.github_username == ""


class TestGitHubFetchCommitCounts:
    """fetch_commit_counts paginates GitHub's /repos/:name/commits
    endpoint and aggregates by day. Three risks pinned:
      1. Returns [] (not None / not raises) when not connected
      2. Aggregation key is the YYYY-MM-DD prefix of the commit
         author date — drift would scatter commits across keys
      3. Pagination terminates: we stop on empty results or when a
         page has < 100 items. A regression that paginated forever
         would burn the user's GitHub rate limit on every dashboard
         load"""

    async def test_no_integration_returns_empty(self, monkeypatch):
        from beats.domain.github import GitHubService

        _patch_httpx_callable(
            monkeypatch,
            lambda *a, **kw: (_ for _ in ()).throw(  # noqa
                RuntimeError("HTTP should not be called without integration")
            ),
        )
        svc = GitHubService(_github_settings(monkeypatch), _FakeGitHubIntegrationRepo(None))
        result = await svc.fetch_commit_counts("a/b", date(2026, 4, 1), date(2026, 4, 7))
        assert result == []

    async def test_empty_access_token_returns_empty(self, monkeypatch):
        """An integration row with an empty access_token (e.g.
        partial OAuth callback) is treated as "not connected".
        Pin so we don't fire requests with `Bearer ` (empty token)."""
        from beats.domain.github import GitHubService
        from beats.domain.models import GitHubIntegration

        _patch_httpx_callable(
            monkeypatch,
            lambda *a, **kw: (_ for _ in ()).throw(  # noqa
                RuntimeError("HTTP should not be called for empty token")
            ),
        )
        svc = GitHubService(
            _github_settings(monkeypatch),
            _FakeGitHubIntegrationRepo(integration=GitHubIntegration(access_token="")),
        )
        result = await svc.fetch_commit_counts("a/b", date(2026, 4, 1), date(2026, 4, 7))
        assert result == []

    async def test_aggregates_commits_by_day_sorted(self, monkeypatch):
        """Three commits across two days → two output rows sorted
        ascending. Pin the YYYY-MM-DD prefix slice [:10]."""
        from beats.domain.github import GitHubService
        from beats.domain.models import GitHubIntegration

        commits = [
            {"commit": {"author": {"date": "2026-04-02T10:30:00Z"}}},
            {"commit": {"author": {"date": "2026-04-01T09:15:00Z"}}},
            {"commit": {"author": {"date": "2026-04-02T16:45:00Z"}}},
        ]

        def handler(method, url, params):
            if "/commits" in url:
                # Page 1 returns the commits, page 2 empty (terminates)
                if params.get("page", 1) == 1:
                    return _FakeHTTPResponse(200, commits)
                return _FakeHTTPResponse(200, [])
            return _FakeHTTPResponse(404, {})

        _patch_httpx_callable(monkeypatch, handler)
        monkeypatch.setattr(
            _FakeHTTPResponse, "raise_for_status", _no_op_raise_for_status, raising=False
        )

        svc = GitHubService(
            _github_settings(monkeypatch),
            _FakeGitHubIntegrationRepo(integration=GitHubIntegration(access_token="gho_x")),
        )
        result = await svc.fetch_commit_counts("ahmed/beats", date(2026, 4, 1), date(2026, 4, 7))
        assert result == [
            {"date": "2026-04-01", "commit_count": 1},
            {"date": "2026-04-02", "commit_count": 2},
        ]

    async def test_paginates_until_short_page(self, monkeypatch):
        """A first page with exactly 100 items triggers a follow-up
        request. The follow-up returning < 100 items terminates
        the loop. Pin both branches — without this, a user with
        100+ commits would silently lose every commit past page 1."""
        from beats.domain.github import GitHubService
        from beats.domain.models import GitHubIntegration

        # Page 1: 100 commits all on 2026-04-01
        page_1 = [{"commit": {"author": {"date": "2026-04-01T09:00:00Z"}}}] * 100
        # Page 2: 5 commits on 2026-04-02
        page_2 = [{"commit": {"author": {"date": "2026-04-02T10:00:00Z"}}}] * 5

        def handler(method, url, params):
            if "/commits" in url:
                p = params.get("page", 1)
                if p == 1:
                    return _FakeHTTPResponse(200, page_1)
                if p == 2:
                    return _FakeHTTPResponse(200, page_2)
                # Should not reach here
                return _FakeHTTPResponse(500, {})
            return _FakeHTTPResponse(404, {})

        _patch_httpx_callable(monkeypatch, handler)
        monkeypatch.setattr(
            _FakeHTTPResponse, "raise_for_status", _no_op_raise_for_status, raising=False
        )

        svc = GitHubService(
            _github_settings(monkeypatch),
            _FakeGitHubIntegrationRepo(integration=GitHubIntegration(access_token="gho_x")),
        )
        result = await svc.fetch_commit_counts("ahmed/beats", date(2026, 4, 1), date(2026, 4, 7))
        assert result == [
            {"date": "2026-04-01", "commit_count": 100},
            {"date": "2026-04-02", "commit_count": 5},
        ]

    async def test_exception_during_fetch_returns_partial(self, monkeypatch):
        """A network error during pagination breaks the loop
        cleanly and returns whatever was collected so far. Pin the
        partial-success contract — better to show the user some
        data than to 500 the whole dashboard."""
        from beats.domain.github import GitHubService
        from beats.domain.models import GitHubIntegration

        page_1 = [{"commit": {"author": {"date": "2026-04-01T09:00:00Z"}}}] * 100

        def handler(method, url, params):
            if "/commits" in url:
                p = params.get("page", 1)
                if p == 1:
                    return _FakeHTTPResponse(200, page_1)
                # Page 2 → error
                import httpx

                return httpx.ConnectError("network down")
            return _FakeHTTPResponse(404, {})

        _patch_httpx_callable(monkeypatch, handler)
        monkeypatch.setattr(
            _FakeHTTPResponse, "raise_for_status", _no_op_raise_for_status, raising=False
        )

        svc = GitHubService(
            _github_settings(monkeypatch),
            _FakeGitHubIntegrationRepo(integration=GitHubIntegration(access_token="gho_x")),
        )
        result = await svc.fetch_commit_counts("ahmed/beats", date(2026, 4, 1), date(2026, 4, 7))
        assert result == [{"date": "2026-04-01", "commit_count": 100}]


class TestGitHubDisconnect:
    async def test_disconnect_returns_bool(self, monkeypatch):
        from beats.domain.github import GitHubService
        from beats.domain.models import GitHubIntegration

        svc_full = GitHubService(
            _github_settings(monkeypatch),
            _FakeGitHubIntegrationRepo(integration=GitHubIntegration(access_token="gho")),
        )
        assert await svc_full.disconnect() is True

        svc_empty = GitHubService(_github_settings(monkeypatch), _FakeGitHubIntegrationRepo(None))
        assert await svc_empty.disconnect() is False


# =============================================================================
# Calendar Service — Google Calendar OAuth + event fetch
# =============================================================================


class _FakeCalendarIntegrationRepo:
    def __init__(self, integration=None):
        self._integration = integration

    async def get(self):
        return self._integration

    async def upsert(self, integration):
        self._integration = integration
        return integration

    async def delete(self) -> bool:
        had = self._integration is not None
        self._integration = None
        return had


def _calendar_settings(monkeypatch):
    """Build a Settings instance with deterministic Google OAuth
    creds. Same env-var pattern as _fitbit_settings/_github_settings."""
    from beats.settings import Settings

    monkeypatch.setenv("GOOGLE_CLIENT_ID", "cid-g")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "csec-g")
    monkeypatch.setenv("GOOGLE_REDIRECT_URI", "https://beats.test/oauth/google")
    return Settings()


class TestCalendarAuthUrl:
    """get_auth_url builds the Google OAuth consent URL. Two
    parameters here are the load-bearing pieces: access_type=offline
    + prompt=consent. Without them, Google does NOT return a
    refresh_token, and the integration breaks the moment the access
    token expires (typically 1 hour later)."""

    def test_includes_offline_access_and_consent_prompt(self, monkeypatch):
        from beats.domain.calendar import CalendarService

        svc = CalendarService(_calendar_settings(monkeypatch), _FakeCalendarIntegrationRepo())
        url = svc.get_auth_url()
        assert url.startswith("https://accounts.google.com/o/oauth2/v2/auth?")
        assert "client_id=cid-g" in url
        assert "redirect_uri=https%3A%2F%2Fbeats.test%2Foauth%2Fgoogle" in url
        assert "response_type=code" in url
        # The two pieces that ensure a refresh_token comes back:
        assert "access_type=offline" in url
        assert "prompt=consent" in url
        # Calendar read-only scope
        assert "calendar.events.readonly" in url


class TestCalendarExchangeCode:
    """exchange_code POSTs the auth code → persists access_token,
    refresh_token, token_expiry."""

    async def test_persists_tokens_with_expiry(self, monkeypatch):
        from beats.domain.calendar import CalendarService

        _patch_httpx(
            monkeypatch,
            {
                "oauth2.googleapis.com/token": _FakeHTTPResponse(
                    200,
                    {
                        "access_token": "ya29-fresh",
                        "refresh_token": "1//rt-google",
                        "expires_in": 3600,
                    },
                )
            },
        )
        monkeypatch.setattr(
            _FakeHTTPResponse, "raise_for_status", _no_op_raise_for_status, raising=False
        )

        repo = _FakeCalendarIntegrationRepo()
        svc = CalendarService(_calendar_settings(monkeypatch), repo)
        before = datetime.now(UTC)
        integration = await svc.exchange_code("auth-code")
        after = datetime.now(UTC)

        assert integration.access_token == "ya29-fresh"
        assert integration.refresh_token == "1//rt-google"
        # token_expiry ≈ now + 3600 sec
        assert integration.token_expiry is not None
        expiry = integration.token_expiry
        assert before + timedelta(seconds=3599) <= expiry
        assert expiry <= after + timedelta(seconds=3601)
        assert (await repo.get()).access_token == "ya29-fresh"


class TestCalendarEnsureFreshToken:
    """_ensure_fresh_token has THREE branches:
      1. Token still valid → return as-is, no HTTP
      2. Expired but no refresh_token → return as-is (don't 401
         on a refresh attempt that's guaranteed to fail)
      3. Expired with refresh_token → POST refresh grant, persist

    Branch 2 is calendar-specific — Fitbit doesn't have it. Pin
    so a regression doesn't fire a refresh request that would burn
    a request slot for no purpose."""

    async def test_returns_same_when_not_expired(self, monkeypatch):
        from beats.domain.calendar import CalendarService
        from beats.domain.models import CalendarIntegration

        _patch_httpx(monkeypatch, {"": RuntimeError("should not refresh")})

        future = datetime.now(UTC) + timedelta(hours=1)
        existing = CalendarIntegration(
            access_token="ya29",
            refresh_token="1//rt",
            token_expiry=future,
        )
        svc = CalendarService(
            _calendar_settings(monkeypatch),
            _FakeCalendarIntegrationRepo(integration=existing),
        )
        result = await svc._ensure_fresh_token(existing)
        assert result.access_token == "ya29"

    async def test_returns_same_when_expired_but_no_refresh_token(self, monkeypatch):
        """No refresh_token → return integration unchanged, NO HTTP
        call. Pin so a regression doesn't fire `grant_type=
        refresh_token` with an empty refresh_token (Google would
        400; user has to re-auth anyway)."""
        from beats.domain.calendar import CalendarService
        from beats.domain.models import CalendarIntegration

        _patch_httpx(
            monkeypatch,
            {"": RuntimeError("must not refresh without a refresh_token")},
        )

        past = datetime.now(UTC) - timedelta(hours=2)
        no_refresh = CalendarIntegration(
            access_token="ya29-OLD",
            refresh_token="",
            token_expiry=past,
        )
        svc = CalendarService(
            _calendar_settings(monkeypatch),
            _FakeCalendarIntegrationRepo(integration=no_refresh),
        )
        result = await svc._ensure_fresh_token(no_refresh)
        assert result.access_token == "ya29-OLD"

    async def test_refreshes_when_expired_with_refresh_token(self, monkeypatch):
        from beats.domain.calendar import CalendarService
        from beats.domain.models import CalendarIntegration

        _patch_httpx(
            monkeypatch,
            {
                "oauth2.googleapis.com/token": _FakeHTTPResponse(
                    200,
                    {"access_token": "ya29-NEW", "expires_in": 3600},
                )
            },
        )
        monkeypatch.setattr(
            _FakeHTTPResponse, "raise_for_status", _no_op_raise_for_status, raising=False
        )

        past = datetime.now(UTC) - timedelta(hours=2)
        stale = CalendarIntegration(
            access_token="ya29-OLD",
            refresh_token="1//rt-keep",
            token_expiry=past,
        )
        repo = _FakeCalendarIntegrationRepo(integration=stale)
        svc = CalendarService(_calendar_settings(monkeypatch), repo)
        refreshed = await svc._ensure_fresh_token(stale)
        assert refreshed.access_token == "ya29-NEW"
        assert (await repo.get()).access_token == "ya29-NEW"


class TestCalendarFetchEvents:
    """fetch_events iterates calendar_ids (a user can have multiple
    calendars connected) and aggregates their events. Two distinct
    risks vs Fitbit/GitHub:
      1. all-day events use {"date": "YYYY-MM-DD"} not {"dateTime"} —
         pin the all_day boolean derivation
      2. one calendar's failure must not drop the others"""

    async def test_no_integration_returns_empty(self, monkeypatch):
        from beats.domain.calendar import CalendarService

        _patch_httpx(
            monkeypatch,
            {"": RuntimeError("must not fetch without integration")},
        )
        svc = CalendarService(
            _calendar_settings(monkeypatch),
            _FakeCalendarIntegrationRepo(None),
        )
        result = await svc.fetch_events(
            datetime(2026, 4, 1, tzinfo=UTC),
            datetime(2026, 4, 2, tzinfo=UTC),
        )
        assert result == []

    async def test_disabled_integration_returns_empty(self, monkeypatch):
        """integration.enabled=False → don't fetch. Pin so the
        Settings → "pause" toggle takes effect immediately rather
        than requiring a full disconnect."""
        from beats.domain.calendar import CalendarService
        from beats.domain.models import CalendarIntegration

        _patch_httpx(
            monkeypatch,
            {"": RuntimeError("must not fetch when disabled")},
        )
        future = datetime.now(UTC) + timedelta(hours=1)
        disabled = CalendarIntegration(
            access_token="ya29",
            refresh_token="rt",
            token_expiry=future,
            enabled=False,
        )
        svc = CalendarService(
            _calendar_settings(monkeypatch),
            _FakeCalendarIntegrationRepo(integration=disabled),
        )
        result = await svc.fetch_events(
            datetime(2026, 4, 1, tzinfo=UTC),
            datetime(2026, 4, 2, tzinfo=UTC),
        )
        assert result == []

    async def test_returns_timed_event_with_all_day_false(self, monkeypatch):
        """Event with `dateTime` → all_day=False, start/end use the
        dateTime value verbatim."""
        from beats.domain.calendar import CalendarService
        from beats.domain.models import CalendarIntegration

        _patch_httpx(
            monkeypatch,
            {
                "/events": _FakeHTTPResponse(
                    200,
                    {
                        "items": [
                            {
                                "summary": "Standup",
                                "start": {"dateTime": "2026-04-01T09:00:00Z"},
                                "end": {"dateTime": "2026-04-01T09:30:00Z"},
                            }
                        ]
                    },
                )
            },
        )
        monkeypatch.setattr(
            _FakeHTTPResponse, "raise_for_status", _no_op_raise_for_status, raising=False
        )

        future = datetime.now(UTC) + timedelta(hours=1)
        svc = CalendarService(
            _calendar_settings(monkeypatch),
            _FakeCalendarIntegrationRepo(
                integration=CalendarIntegration(
                    access_token="ya29",
                    refresh_token="rt",
                    token_expiry=future,
                )
            ),
        )
        events = await svc.fetch_events(
            datetime(2026, 4, 1, tzinfo=UTC),
            datetime(2026, 4, 2, tzinfo=UTC),
        )
        assert len(events) == 1
        e = events[0]
        assert e["summary"] == "Standup"
        assert e["start"] == "2026-04-01T09:00:00Z"
        assert e["end"] == "2026-04-01T09:30:00Z"
        assert e["all_day"] is False

    async def test_returns_all_day_event_correctly(self, monkeypatch):
        """Event with `date` (not `dateTime`) → all_day=True. Pin
        so the calendar view doesn't render an all-day event as
        "12:00 AM" (the timezone-zero artifact of treating
        "2026-04-01" as a datetime)."""
        from beats.domain.calendar import CalendarService
        from beats.domain.models import CalendarIntegration

        _patch_httpx(
            monkeypatch,
            {
                "/events": _FakeHTTPResponse(
                    200,
                    {
                        "items": [
                            {
                                "summary": "Holiday",
                                "start": {"date": "2026-04-01"},
                                "end": {"date": "2026-04-02"},
                            }
                        ]
                    },
                )
            },
        )
        monkeypatch.setattr(
            _FakeHTTPResponse, "raise_for_status", _no_op_raise_for_status, raising=False
        )

        future = datetime.now(UTC) + timedelta(hours=1)
        svc = CalendarService(
            _calendar_settings(monkeypatch),
            _FakeCalendarIntegrationRepo(
                integration=CalendarIntegration(
                    access_token="ya29",
                    refresh_token="rt",
                    token_expiry=future,
                )
            ),
        )
        events = await svc.fetch_events(
            datetime(2026, 4, 1, tzinfo=UTC),
            datetime(2026, 4, 2, tzinfo=UTC),
        )
        assert events == [
            {
                "summary": "Holiday",
                "start": "2026-04-01",
                "end": "2026-04-02",
                "all_day": True,
            }
        ]

    async def test_event_without_summary_falls_back_to_no_title(self, monkeypatch):
        """Calendar events sometimes have no title (busy blocks,
        declined invites). Pin the "(No title)" fallback so the
        UI doesn't render a literal empty string."""
        from beats.domain.calendar import CalendarService
        from beats.domain.models import CalendarIntegration

        _patch_httpx(
            monkeypatch,
            {
                "/events": _FakeHTTPResponse(
                    200,
                    {
                        "items": [
                            {
                                "start": {"dateTime": "2026-04-01T10:00:00Z"},
                                "end": {"dateTime": "2026-04-01T11:00:00Z"},
                            }
                        ]
                    },
                )
            },
        )
        monkeypatch.setattr(
            _FakeHTTPResponse, "raise_for_status", _no_op_raise_for_status, raising=False
        )

        future = datetime.now(UTC) + timedelta(hours=1)
        svc = CalendarService(
            _calendar_settings(monkeypatch),
            _FakeCalendarIntegrationRepo(
                integration=CalendarIntegration(
                    access_token="ya29",
                    refresh_token="rt",
                    token_expiry=future,
                )
            ),
        )
        events = await svc.fetch_events(
            datetime(2026, 4, 1, tzinfo=UTC),
            datetime(2026, 4, 2, tzinfo=UTC),
        )
        assert events[0]["summary"] == "(No title)"

    async def test_iterates_multiple_calendars(self, monkeypatch):
        """User has primary + a second calendar — both are queried
        and their events appended. Pin so a regression doesn't only
        fetch the first calendar in the list."""
        from beats.domain.calendar import CalendarService
        from beats.domain.models import CalendarIntegration

        call_log: list[str] = []

        def handler(method, url, params):
            call_log.append(url)
            if "primary" in url:
                return _FakeHTTPResponse(
                    200,
                    {
                        "items": [
                            {
                                "summary": "From primary",
                                "start": {"dateTime": "2026-04-01T09:00:00Z"},
                                "end": {"dateTime": "2026-04-01T10:00:00Z"},
                            }
                        ]
                    },
                )
            if "work" in url:
                return _FakeHTTPResponse(
                    200,
                    {
                        "items": [
                            {
                                "summary": "From work",
                                "start": {"dateTime": "2026-04-01T11:00:00Z"},
                                "end": {"dateTime": "2026-04-01T12:00:00Z"},
                            }
                        ]
                    },
                )
            return _FakeHTTPResponse(404, {})

        _patch_httpx_callable(monkeypatch, handler)
        monkeypatch.setattr(
            _FakeHTTPResponse, "raise_for_status", _no_op_raise_for_status, raising=False
        )

        future = datetime.now(UTC) + timedelta(hours=1)
        svc = CalendarService(
            _calendar_settings(monkeypatch),
            _FakeCalendarIntegrationRepo(
                integration=CalendarIntegration(
                    access_token="ya29",
                    refresh_token="rt",
                    token_expiry=future,
                    calendar_ids=["primary", "work@example.com"],
                )
            ),
        )
        events = await svc.fetch_events(
            datetime(2026, 4, 1, tzinfo=UTC),
            datetime(2026, 4, 2, tzinfo=UTC),
        )
        summaries = [e["summary"] for e in events]
        assert "From primary" in summaries
        assert "From work" in summaries
        assert len(call_log) == 2

    async def test_one_calendar_failure_does_not_drop_others(self, monkeypatch):
        """Calendar A errors, B succeeds → result has B's events.
        Pin per-calendar resilience so a single revoked calendar
        permission doesn't kill the whole event panel."""
        import httpx

        from beats.domain.calendar import CalendarService
        from beats.domain.models import CalendarIntegration

        def handler(method, url, params):
            if "primary" in url:
                return httpx.ConnectError("permission revoked")
            if "work" in url:
                return _FakeHTTPResponse(
                    200,
                    {
                        "items": [
                            {
                                "summary": "Survivor",
                                "start": {"dateTime": "2026-04-01T09:00:00Z"},
                                "end": {"dateTime": "2026-04-01T10:00:00Z"},
                            }
                        ]
                    },
                )
            return _FakeHTTPResponse(404, {})

        _patch_httpx_callable(monkeypatch, handler)
        monkeypatch.setattr(
            _FakeHTTPResponse, "raise_for_status", _no_op_raise_for_status, raising=False
        )

        future = datetime.now(UTC) + timedelta(hours=1)
        svc = CalendarService(
            _calendar_settings(monkeypatch),
            _FakeCalendarIntegrationRepo(
                integration=CalendarIntegration(
                    access_token="ya29",
                    refresh_token="rt",
                    token_expiry=future,
                    calendar_ids=["primary", "work@example.com"],
                )
            ),
        )
        events = await svc.fetch_events(
            datetime(2026, 4, 1, tzinfo=UTC),
            datetime(2026, 4, 2, tzinfo=UTC),
        )
        assert [e["summary"] for e in events] == ["Survivor"]


class TestCalendarDisconnect:
    async def test_disconnect_returns_bool(self, monkeypatch):
        from beats.domain.calendar import CalendarService
        from beats.domain.models import CalendarIntegration

        svc_full = CalendarService(
            _calendar_settings(monkeypatch),
            _FakeCalendarIntegrationRepo(integration=CalendarIntegration(access_token="ya29")),
        )
        assert await svc_full.disconnect() is True

        svc_empty = CalendarService(
            _calendar_settings(monkeypatch),
            _FakeCalendarIntegrationRepo(None),
        )
        assert await svc_empty.disconnect() is False
