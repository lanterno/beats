"""`TimerService` and `BeatService`, and the flow tags a stop derives.

Split out of `test_domain.py` at the ceiling in roadmaps/file-sizes.md;
the shared fakes and factories are `domain_fakes.py`'s.
"""

from datetime import UTC, date, datetime, timedelta

import pytest

from beats.domain.exceptions import (
    InvalidEndTime,
    NoActiveTimer,
    ProjectNotFound,
    TimerAlreadyRunning,
)
from beats.domain.models import (
    Beat,
)
from beats.domain_fakes import (
    _beat_service,
    _FakeFlowRepo,
    _flow_win,
    _project,
    _timer_service,
)


class TestDeriveFlowTags:
    """derive_flow_tags turns the daemon's flow-window signals into session
    tags — the app takes no manual tag input. Repos come first (more
    specific), then languages; both deduped, basename'd, lowercased, capped."""

    async def test_repos_before_languages_deduped(self):
        from beats.domain.services import derive_flow_tags

        start = datetime(2026, 4, 1, 9, 0, tzinfo=UTC)
        repo = _FakeFlowRepo(
            [
                _flow_win(start, repo="/home/me/beats", language="Python"),
                _flow_win(start + timedelta(minutes=6), repo="/home/me/beats", language="Python"),
            ]
        )
        tags = await derive_flow_tags(repo, start, start + timedelta(minutes=30))
        assert tags == ["beats", "python"]

    async def test_basename_lowercase_and_owner_repo_form(self):
        from beats.domain.services import derive_flow_tags

        start = datetime(2026, 4, 1, 9, 0, tzinfo=UTC)
        repo = _FakeFlowRepo(
            [
                _flow_win(start, repo="acme/Widgets", language="TypeScript"),
                _flow_win(start + timedelta(minutes=6), repo=None, language="Go"),
            ]
        )
        tags = await derive_flow_tags(repo, start, start + timedelta(minutes=30))
        assert tags == ["Widgets", "typescript", "go"]

    async def test_no_end_returns_empty(self):
        from beats.domain.services import derive_flow_tags

        start = datetime(2026, 4, 1, 9, 0, tzinfo=UTC)
        repo = _FakeFlowRepo([_flow_win(start, repo="beats", language="Python")])
        assert await derive_flow_tags(repo, start, None) == []

    async def test_caps_at_six(self):
        from beats.domain.services import derive_flow_tags

        start = datetime(2026, 4, 1, 9, 0, tzinfo=UTC)
        windows = [
            _flow_win(start + timedelta(minutes=i), repo=f"repo{i}", language=f"lang{i}")
            for i in range(10)
        ]
        tags = await derive_flow_tags(_FakeFlowRepo(windows), start, start + timedelta(hours=1))
        assert len(tags) == 6

    async def test_stop_timer_autotags_beat(self):
        start = datetime(2026, 4, 1, 9, 0, tzinfo=UTC)
        active = Beat(id="b1", project_id="p1", start=start, end=None)
        svc = _timer_service(
            beats=[active],
            projects=[_project("p1", "Alpha")],
            flow_windows=[_flow_win(start + timedelta(minutes=5), repo="beats", language="Python")],
        )
        stopped = await svc.stop_timer(end_time=start + timedelta(minutes=30))
        assert stopped.tags == ["beats", "python"]


class TestSummarizeFlow:
    """summarize_flow reduces daemon flow windows to a coach headline:
    count/avg/peak + top repo (basename) and top language, excluding
    drift (flow_score=0) events from the average."""

    def test_none_for_empty_or_all_drift(self):
        from beats.domain.flow import summarize_flow
        from beats.domain.models import FlowWindow

        start = datetime(2026, 4, 1, 9, 0, tzinfo=UTC)
        assert summarize_flow([]) is None
        # flow_score=0 windows are drift markers — excluded, so all-drift -> None
        drift = FlowWindow(
            device_id="d",
            window_start=start,
            window_end=start + timedelta(minutes=5),
            flow_score=0.0,
            dominant_category="drift",
        )
        assert summarize_flow([drift]) is None

    def test_aggregates_and_basenames_top_repo(self):
        from beats.domain.flow import summarize_flow

        start = datetime(2026, 4, 1, 9, 0, tzinfo=UTC)
        windows = [
            _flow_win(start, repo="/home/me/beats", language="Python"),
            _flow_win(start + timedelta(minutes=6), repo="/home/me/beats", language="Python"),
            _flow_win(start + timedelta(minutes=12), repo="acme/widgets", language="Go"),
        ]
        fs = summarize_flow(windows)
        assert fs is not None
        assert fs.count == 3
        assert fs.top_repo == "beats"  # basename, most frequent
        assert fs.top_language == "python"
        assert 0.0 < fs.avg_score <= 1.0
        assert fs.peak_score == 0.8


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

        svc = _timer_service()
        with pytest.raises(ProjectNotFound):
            await svc.start_timer("ghost")

    async def test_raises_timer_already_running(self):
        """An active timer (end=None) on any project blocks a new
        start. Pin so the multi-timer corruption can't slip in."""

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
        # the UI can render "Already tracking Alpha" — in the message and
        # in `detail`, which is what reaches the client in the error envelope.
        assert "Alpha" in str(exc.value)
        assert exc.value.detail["project_name"] == "Alpha"


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

        svc = _timer_service()
        with pytest.raises(NoActiveTimer):
            await svc.stop_timer()

    async def test_raises_invalid_end_time_when_end_before_start(self):
        """end < start would produce a negative duration. Pin the
        guard so the validation can't be quietly removed."""

        projects = [_project("p1", "Alpha")]
        start = datetime(2026, 4, 1, 10, 0, tzinfo=UTC)
        active = Beat(id="b1", project_id="p1", start=start, end=None)
        svc = _timer_service(beats=[active], projects=projects)
        too_early = datetime(2026, 4, 1, 9, 0, tzinfo=UTC)
        with pytest.raises(InvalidEndTime):
            await svc.stop_timer(end_time=too_early)

    async def test_a_write_during_the_flow_read_survives_the_stop(self):
        """The stop reads the running beat, then awaits the flow windows, then
        writes. Against real Mongo: a write landing in that await (the
        companion moving the start earlier, an import bringing a note) is
        not reverted by the stop, which writes only the end and the tags."""
        import os

        from bson import ObjectId
        from pymongo import AsyncMongoClient

        from beats.domain.services import TimerService
        from beats.infrastructure.project_repositories import (
            MongoBeatRepository,
            MongoProjectRepository,
        )

        client = AsyncMongoClient(os.environ.get("DB_DSN", "mongodb://localhost:27017"))
        try:
            db = client[os.environ.get("DB_NAME", "beats_test")]
            user_id = str(ObjectId())
            beats = MongoBeatRepository(db.beats, user_id=user_id)
            start = datetime(2026, 4, 1, 9, 0, tzinfo=UTC)
            moved = start - timedelta(minutes=20)
            running = await beats.create(Beat(project_id="p1", start=start))
            assert running.id is not None

            class _WriteDuringRead:
                async def list_by_range(self, start: datetime, end: datetime) -> list:
                    await db.beats.update_one(
                        {"_id": ObjectId(running.id)},
                        {"$set": {"start": moved, "note": "Imported"}},
                    )
                    return []

            svc = TimerService(
                beat_repo=beats,
                project_repo=MongoProjectRepository(db.projects, user_id=user_id),
                flow_repo=_WriteDuringRead(),
            )
            end = start + timedelta(hours=1)
            stopped = await svc.stop_timer(end_time=end)

            stored = await beats.get_by_id(running.id)
            assert (stored.start, stored.end, stored.note) == (moved, end, "Imported")
            assert stopped == stored
        finally:
            await client.close()


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
