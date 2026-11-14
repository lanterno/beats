"""Domain models and their validation: the local-date helpers, `Beat`,
`ExpectedBeat`, `Project`, the exception hierarchy, goal overrides and
their resolution, the contract's hold on the goal, and `BiometricDay`.

Split out of `test_domain.py` at the size ceiling (CLAUDE.md § Conventions);
the shared fakes and factories are `domain_fakes.py`'s.
"""

from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

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
    Contract,
    ContractTerm,
    ExpectedBeat,
    GoalOverride,
    GoalType,
    Project,
    ProjectKind,
    ScheduleType,
)
from beats.domain.utils import local_date, local_dt, normalize_tz


class TestLocalDateHelpers:
    """Pin local_date / local_dt — the heart of the timezone-correctness
    fix. A late-evening UTC instant must land on the correct LOCAL day for
    the requesting timezone, and naive datetimes (Mongo may return them)
    are treated as UTC."""

    def test_utc_default_is_identity_for_date(self):
        utc = ZoneInfo("UTC")
        dt = datetime(2026, 1, 1, 23, 30, tzinfo=UTC)
        assert local_date(dt, utc) == date(2026, 1, 1)

    def test_negative_offset_keeps_same_or_earlier_day(self):
        # 2026-01-01T23:30Z in New York (UTC-5) is 18:30 the SAME day.
        ny = ZoneInfo("America/New_York")
        dt = datetime(2026, 1, 1, 23, 30, tzinfo=UTC)
        assert local_date(dt, ny) == date(2026, 1, 1)
        assert local_dt(dt, ny).hour == 18

    def test_positive_offset_rolls_to_next_day(self):
        # 2026-01-01T23:30Z in Tokyo (UTC+9) is 08:30 the NEXT day.
        tokyo = ZoneInfo("Asia/Tokyo")
        dt = datetime(2026, 1, 1, 23, 30, tzinfo=UTC)
        assert local_date(dt, tokyo) == date(2026, 1, 2)
        assert local_dt(dt, tokyo).hour == 8

    def test_naive_datetime_treated_as_utc(self):
        # A naive datetime (as Mongo returns) is interpreted as UTC, then
        # converted — must match the aware-UTC result exactly.
        tokyo = ZoneInfo("Asia/Tokyo")
        naive = datetime(2026, 1, 1, 23, 30)
        aware = datetime(2026, 1, 1, 23, 30, tzinfo=UTC)
        assert local_date(naive, tokyo) == local_date(aware, tokyo)
        assert local_dt(naive, tokyo) == local_dt(aware, tokyo)

    def test_early_morning_utc_rolls_back_for_negative_offset(self):
        # 2026-01-02T02:00Z in Los Angeles (UTC-8) is 18:00 the prior day.
        la = ZoneInfo("America/Los_Angeles")
        dt = datetime(2026, 1, 2, 2, 0, tzinfo=UTC)
        assert local_date(dt, la) == date(2026, 1, 1)


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


class TestExpectedBeat:
    """A write's precondition compares instants to the millisecond, because
    a BSON date keeps no more: what a client sent with microseconds comes
    back truncated, not rounded, and must still match."""

    START = datetime(2026, 4, 16, 9, 0, 0, 123000, tzinfo=UTC)

    def _stored(self, end: datetime | None = None) -> Beat:
        return Beat(id="b1", project_id="p1", start=self.START, end=end)

    def test_microseconds_mongo_dropped_still_match(self):
        sent = ExpectedBeat(project_id="p1", start=self.START.replace(microsecond=123999))
        assert sent.matches(self._stored())

    def test_the_next_millisecond_does_not(self):
        sent = ExpectedBeat(project_id="p1", start=self.START.replace(microsecond=124000))
        assert not sent.matches(self._stored())

    def test_a_naive_instant_reads_as_utc(self):
        sent = ExpectedBeat(project_id="p1", start=self.START.replace(tzinfo=None))
        assert sent.matches(self._stored())

    def test_a_running_session_does_not_match_a_finished_one(self):
        end = datetime(2026, 4, 16, 10, 0, tzinfo=UTC)
        assert not ExpectedBeat(project_id="p1", start=self.START).matches(self._stored(end=end))
        assert not ExpectedBeat(project_id="p1", start=self.START, end=end).matches(self._stored())

    def test_another_project_does_not_match(self):
        assert not ExpectedBeat(project_id="p2", start=self.START).matches(self._stored())


class TestProjectModel:
    """Tests for the Project domain model."""

    def test_project_creation_minimal(self):
        """Test creating a project with only required fields."""
        project = Project(name="Test Project")
        assert project.name == "Test Project"
        assert project.description is None
        assert project.archived is False

    def test_project_creation_full(self):
        """Test creating a project with all fields."""
        project = Project(
            id="test-id",
            name="Test Project",
            description="A test project",
            archived=True,
        )
        assert project.id == "test-id"
        assert project.name == "Test Project"
        assert project.description == "A test project"
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

    def _project(self, **kwargs: Any) -> Project:
        defaults: dict[str, Any] = {
            "name": "Test",
            "weekly_goal": 20,
            "goal_type": GoalType.TARGET,
        }
        return Project(**{**defaults, **kwargs})

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


class TestContractGoal:
    """`Project.effective_goal` on a day job with a contract: the contract's term is
    the goal on the weeks it governs, and the personal goal is untouched on the rest."""

    START = date(2026, 3, 2)  # a Monday

    def _day_job(self, *terms: ContractTerm, kind: ProjectKind = ProjectKind.DAY_JOB) -> Project:
        return Project(
            name="Acme",
            kind=kind,
            contract=Contract(terms=list(terms)),
            # A personal goal, and overrides on both shapes, that all say otherwise.
            weekly_goal=20,
            goal_type=GoalType.CAP,
            goal_overrides=[
                GoalOverride(week_of=self.START, weekly_goal=10),
                GoalOverride(effective_from=self.START - timedelta(weeks=8), weekly_goal=15),
            ],
        )

    @staticmethod
    def _part_time(effective_from: date) -> ContractTerm:
        return ContractTerm(
            effective_from=effective_from,
            schedule_type=ScheduleType.PART_TIME,
            full_time_hours=42,
            percentage=0.8,
        )

    def test_time_based_term_is_the_goal_and_the_personal_goal_is_not_read(self):
        term = self._part_time(self.START - timedelta(weeks=4))
        p = self._day_job(term)
        assert p.effective_goal(self.START) == (pytest.approx(33.6), GoalType.TARGET)
        assert p.goal_term(self.START) == term

    def test_objective_term_leaves_the_personal_goal(self):
        p = self._day_job(
            ContractTerm(
                effective_from=self.START - timedelta(weeks=4),
                schedule_type=ScheduleType.OBJECTIVE,
            )
        )
        assert p.effective_goal(self.START) == (10, GoalType.CAP)
        assert p.goal_term(self.START) is None

    def test_before_the_first_term_the_personal_goal_applies(self):
        p = self._day_job(self._part_time(self.START + timedelta(days=7)))
        assert p.effective_goal(self.START) == (10, GoalType.CAP)
        assert p.goal_term(self.START) is None

    def test_a_term_changing_midweek_takes_over_the_following_monday(self):
        wednesday = self.START + timedelta(days=2)
        p = self._day_job(
            self._part_time(self.START - timedelta(weeks=4)),
            ContractTerm(
                effective_from=wednesday,
                schedule_type=ScheduleType.FULL_TIME,
                full_time_hours=42,
            ),
        )
        assert p.effective_goal(self.START)[0] == pytest.approx(33.6)
        assert p.effective_goal(self.START + timedelta(weeks=1))[0] == 42

    def test_a_contract_on_any_other_kind_is_not_read(self):
        p = self._day_job(
            self._part_time(self.START - timedelta(weeks=4)), kind=ProjectKind.FREELANCE
        )
        assert p.effective_goal(self.START) == (10, GoalType.CAP)

    def test_a_term_of_no_hours_governs_the_week_and_sets_no_goal(self):
        """The migration's reading of an override that said "no goal from here":
        the personal goal must not resurface under it, and the week has no goal
        — not a goal of 0 h — as it had under the override (Decision 10)."""
        sabbatical = ContractTerm(
            effective_from=self.START - timedelta(weeks=4),
            schedule_type=ScheduleType.CUSTOM,
            weekly_hours=0,
        )
        p = self._day_job(self._part_time(self.START - timedelta(weeks=8)), sabbatical)
        assert p.goal_term(self.START) == sabbatical
        assert p.effective_goal(self.START) == (None, GoalType.TARGET)


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


class TestNormalizeTz:
    """normalize_tz attaches UTC tzinfo to naive datetimes (Mongo
    returns naive timestamps) and passes through aware datetimes
    unchanged. Pin both branches — a regression that flipped the
    convention would silently propagate naive datetimes through
    the domain layer and break every timezone-aware comparison."""

    def test_naive_datetime_gets_utc_attached(self):

        naive = datetime(2026, 4, 1, 9, 0)
        out = normalize_tz(naive)
        assert out.tzinfo is UTC
        # Wall-clock time preserved
        assert out.hour == 9
        assert out.year == 2026

    def test_aware_datetime_passes_through_unchanged(self):
        """A datetime that already has tzinfo is returned as-is.
        Pin so a non-UTC tz isn't silently coerced to UTC (would
        shift wall-clock time and break user-facing displays)."""
        from datetime import timezone

        pacific = timezone(timedelta(hours=-8))
        aware = datetime(2026, 4, 1, 9, 0, tzinfo=pacific)
        out = normalize_tz(aware)
        assert out.tzinfo is pacific
        assert out.hour == 9
