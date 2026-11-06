"""`ProjectService`'s time aggregations and its batch beat helpers.

Split out of `test_domain.py` at the ceiling in roadmaps/file-sizes.md;
the shared fakes and factories are `domain_fakes.py`'s.
"""

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from beats.domain.models import (
    Beat,
)
from beats.domain_fakes import (
    _project,
    _project_service,
)


class TestProjectServiceTimeAggregations:
    """Four aggregation methods that power the project-detail page:
    get_today_time, get_monthly_totals, get_daily_average,
    get_daily_summary.

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

    # ---------------- get_monthly_totals ----------------

    async def test_monthly_totals_empty_returns_zero(self):
        svc = _project_service(projects=[_project("p1", "Alpha")])
        result = await svc.get_monthly_totals("p1", ZoneInfo("UTC"))
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
        result = await svc.get_monthly_totals("p1", ZoneInfo("UTC"))
        assert result["durations_per_month"] == {"2026-04": 1.5, "2026-05": 2.0}
        assert result["total_minutes"] == 90 + 120

    async def test_monthly_totals_warns_on_runaway_beat(self):
        """A beat over 24h (forgotten timer) emits a warning rather
        than silently inflating the total. Pin so the warning
        always surfaces."""
        s = datetime(2026, 4, 1, 9, 0, tzinfo=UTC)
        runaway = Beat(id="b-runaway", project_id="p1", start=s, end=s + timedelta(hours=30))
        svc = _project_service(projects=[_project("p1", "Alpha")], beats=[runaway])
        result = await svc.get_monthly_totals("p1", ZoneInfo("UTC"))
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


# FF.15 — Beats-batched aggregation helpers


class TestProjectServiceBeatsBatchHelpers:
    """Pure-Python helpers that take pre-fetched beats and return the
    same shapes as the public per-project aggregations, plus the index's
    this-week slots, which have no per-project route. The list_projects
    route fetches every displayed project's beats in ONE Mongo find and
    calls these helpers directly, sharing the same in-memory list across
    the three aggregations.

    Why these tests matter: the helpers MUST stay byte-for-byte
    equivalent to the public methods, or the /projects index page
    silently disagrees with the /project/{id}/total endpoint.
    The matches_public_method tests run both paths over identical input
    and pin equality of the result dicts."""

    @staticmethod
    def _at(d: date, hour: int = 9) -> datetime:
        return datetime.combine(d, datetime.min.time(), tzinfo=UTC).replace(hour=hour)

    @staticmethod
    def _completed(id_: str, project_id: str, day: date, hour: int = 9, minutes: int = 60) -> Beat:
        s = TestProjectServiceBeatsBatchHelpers._at(day, hour)
        return Beat(id=id_, project_id=project_id, start=s, end=s + timedelta(minutes=minutes))

    @staticmethod
    def _running(id_: str, project_id: str, day: date, hour: int = 9) -> Beat:
        return Beat(
            id=id_,
            project_id=project_id,
            start=TestProjectServiceBeatsBatchHelpers._at(day, hour),
            end=None,
        )

    def test_last_tracked_from_beats_empty_returns_none(self):
        from beats.domain.services import ProjectService

        assert ProjectService._last_tracked_from_beats([]) is None

    def test_last_tracked_from_beats_uses_start_when_end_is_none(self):
        """A running beat's start counts as last activity if later than
        any completed end. Pin so an in-progress timer surfaces as 'just
        now' the same way the public method does."""
        from beats.domain.services import ProjectService

        today = date.today()
        beats = [
            self._completed("b-old", "p1", today - timedelta(days=2), minutes=60),
            self._running("b-now", "p1", today, hour=14),
        ]
        result = ProjectService._last_tracked_from_beats(beats)
        assert result == self._at(today, hour=14)

    async def test_monthly_totals_from_beats_matches_public_method(self):
        """Helper output is byte-identical to get_monthly_totals(pid)
        for the same beats. Regression-proofs that the refactor
        preserves the contract — if someone edits one path and not the
        other they break this test loudly."""
        from beats.domain.services import ProjectService

        beats = [
            self._completed("b1", "p1", date(2026, 4, 1), minutes=60),
            self._completed("b2", "p1", date(2026, 4, 15), minutes=30),
            self._completed("b3", "p1", date(2026, 5, 1), minutes=120),
            self._running("b4", "p1", date.today()),
        ]
        svc = _project_service(projects=[_project("p1", "Alpha")], beats=beats)
        via_public = await svc.get_monthly_totals("p1", ZoneInfo("UTC"))
        via_helper = ProjectService._monthly_totals_from_beats(beats, ZoneInfo("UTC"))
        assert via_helper == via_public

    def test_this_week_from_beats_minutes_and_goal(self):
        """A 1h30m completed beat in the current week yields weekly_minutes
        == 90.0 EXACTLY, beside the goal resolved for the week; a running
        beat does not count. The list_projects route reports these as the
        index's this-week slots — drift here moves what users see as 'this
        week' on the projects index."""
        from beats.domain.services import ProjectService

        today = date.today()
        monday = today - timedelta(days=today.weekday())
        beats = [
            self._completed("b1", "p1", monday, minutes=90),
            self._running("b2", "p1", today, hour=23),
        ]
        project = _project("p1", "Alpha", weekly_goal=5.0)
        result = ProjectService._this_week_from_beats(beats, project)
        assert result == {
            "weekly_minutes": 90.0,
            "effective_goal": 5.0,
            "effective_goal_type": "target",
            "effective_goal_overridden": False,
        }
