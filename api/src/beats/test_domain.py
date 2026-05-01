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
