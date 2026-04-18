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
from beats.domain.models import Beat, GoalOverride, GoalType, Project


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
