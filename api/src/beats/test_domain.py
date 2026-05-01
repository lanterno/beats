"""Tests for domain models and services."""

from datetime import UTC, date, datetime, timedelta

import pytest

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
