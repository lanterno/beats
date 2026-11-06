"""Fakes and factories the domain suites share — no tests of their own.

`test_domain.py` grew past the ceiling in roadmaps/file-sizes.md and split
by the domain module under test; the in-memory repository fakes and the
small model factories are used by more than one of those files. Not
`test_`-prefixed, so pytest does not collect it.
"""

import builtins
from collections.abc import Collection
from datetime import UTC, date, datetime, timedelta
from typing import Any

from beats.domain.exceptions import (
    ProjectNotFound,
)
from beats.domain.models import (
    Absence,
    BalanceAdjustment,
    Beat,
    Contract,
    ContractTerm,
    GoalType,
    Project,
    ProjectKind,
    ScheduleType,
)
from beats.domain.utils import normalize_tz

# --- Analytics / intelligence fakes ---


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


# IntelligenceService test scaffolding


class _FakeIntelBeatRepo(_FakeBeatRepo):
    """Extends _FakeBeatRepo with the methods IntelligenceService
    consumes beyond what AnalyticsService needs."""


class _FakeProjectRepo:
    """Returns a fixed project list, optionally filtered by archived."""

    def __init__(self, projects: builtins.list):
        self._projects = projects

    async def list(self, archived: bool = False) -> builtins.list:
        return [p for p in self._projects if p.archived == archived]


class _FakeWeekExpectationReader:
    """A `WeekExpectationReader` answering a fixed figure per project id —
    what the contract expects of the week after holidays and absences — and
    recording what it was asked."""

    def __init__(self, expected: dict[str, float | None]):
        self._expected = expected
        self.asked: list[tuple[str | None, date]] = []

    async def expected_for_week(self, project: Project, week_of: date) -> float | None:
        self.asked.append((project.id, week_of))
        return self._expected.get(project.id or "")


def _split_week() -> tuple[Project, list[Beat]]:
    """A day job on full time whose term turns objective on Wednesday 4
    March 2026, with 6 h tracked on that Monday and 4 h on the Wednesday.
    The week owes Monday and Tuesday alone, 16 h, and the week card counts
    only Monday's 6 h against them (`counts_worked`): 10 h to go, not 6."""
    terms = [
        ContractTerm(
            effective_from=date(2026, 1, 5),
            schedule_type=ScheduleType.FULL_TIME,
            full_time_hours=40,
        ),
        ContractTerm(effective_from=date(2026, 3, 4), schedule_type=ScheduleType.OBJECTIVE),
    ]
    project = Project(
        id="p1", name="Day job", kind=ProjectKind.DAY_JOB, contract=Contract(terms=terms)
    )
    beats = [
        Beat(
            id=f"b{day}",
            project_id="p1",
            start=datetime(2026, 3, day, 9, tzinfo=UTC),
            end=datetime(2026, 3, day, 9 + hours, tzinfo=UTC),
        )
        for day, hours in ((2, 6), (4, 4))
    ]
    return project, beats


def _intel_service(
    *,
    beats: list | None = None,
    projects: list | None = None,
    contracts: _FakeWeekExpectationReader | None = None,
):
    """Build an IntelligenceService with fakes for every repo."""
    from beats.domain.intelligence import IntelligenceService

    return IntelligenceService(
        beat_repo=_FakeIntelBeatRepo(beats or []),
        project_repo=_FakeProjectRepo(projects or []),
        contracts=contracts,
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


# --- Service fakes ---


class _FakeBeatRepoForServices:
    """In-memory BeatRepository fake for TimerService / BeatService.
    Implements get_active, get_last, create, update, delete, list,
    list_by_project, get_by_id with the same contract the real repo
    exposes (raising NoObjectMatched where applicable, and BeatNotFound
    from update, as the port says)."""

    def __init__(self, beats: builtins.list[Beat] | None = None):
        self._beats: list[Beat] = list(beats or [])
        self._counter = 1
        # (project_id, since) per `list_by_project`, so a test can say what
        # a caller asked storage for and not only what it did with it.
        self.ranges_read: list[tuple[str, datetime | None]] = []

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

    async def update(self, beat: Beat, fields: Collection[str]) -> Beat:
        for i, b in enumerate(self._beats):
            if b.id == beat.id:
                self._beats[i] = b.model_copy(update={f: getattr(beat, f) for f in fields})
                return self._beats[i]
        from beats.domain.exceptions import BeatNotFound

        raise BeatNotFound(beat.id)

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
    ) -> builtins.list[Beat]:
        out = list(self._beats)
        if project_id is not None:
            out = [b for b in out if b.project_id == project_id]
        if date_filter is not None:
            out = [b for b in out if b.start.date() == date_filter]
        return out

    async def list_by_project(
        self, project_id: str, since: datetime | None = None
    ) -> builtins.list[Beat]:
        self.ranges_read.append((project_id, since))
        out = [b for b in self._beats if b.project_id == project_id]
        if since is not None:
            out = [b for b in out if normalize_tz(b.start) >= since]
        return out

    async def list_grouped_by_project_ids(
        self, project_ids: builtins.list[str]
    ) -> dict[str, builtins.list[Beat]]:
        # Mirror the real repo: every requested id is present in the result
        # (empty list when no beats), and unsolicited project_ids are not.
        buckets: dict[str, list[Beat]] = {pid: [] for pid in project_ids}
        requested = set(project_ids)
        for b in self._beats:
            if b.project_id in requested:
                buckets[b.project_id].append(b)
        return buckets


class _FakeProjectRepoForServices:
    """In-memory ProjectRepository fake."""

    def __init__(self, projects: builtins.list[Project] | None = None):
        self._projects: list[Project] = list(projects or [])
        self._counter = 1

    async def exists(self, project_id: str) -> bool:
        return any(p.id == project_id for p in self._projects)

    async def get_by_id(self, project_id: str) -> Project:
        for p in self._projects:
            if p.id == project_id:
                return p

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

    async def list(self, archived: bool = False) -> builtins.list[Project]:
        return [p for p in self._projects if p.archived == archived]


class _FakeFlowRepo:
    """In-memory FlowWindowRepository fake. list_by_range returns windows
    whose window_start falls within [start, end], matching the real Mongo
    query's boundary semantics."""

    def __init__(self, windows=None):
        self._windows = list(windows or [])

    async def create(self, window):
        self._windows.append(window)
        return window

    async def list_by_range(
        self,
        start,
        end,
        project_id=None,
        editor_repo=None,
        editor_language=None,
        bundle_id=None,
        dominant_category=None,
    ):
        return [w for w in self._windows if start <= w.window_start <= end]


def _flow_win(start: datetime, *, minutes: int = 5, repo=None, language=None):
    from beats.domain.models import FlowWindow

    return FlowWindow(
        device_id="dev-1",
        window_start=start,
        window_end=start + timedelta(minutes=minutes),
        flow_score=0.8,
        editor_repo=repo,
        editor_language=language,
    )


def _timer_service(
    *,
    beats: list[Beat] | None = None,
    projects: list[Project] | None = None,
    flow_windows=None,
):
    from beats.domain.services import TimerService

    return TimerService(
        beat_repo=_FakeBeatRepoForServices(beats),
        project_repo=_FakeProjectRepoForServices(projects),
        flow_repo=_FakeFlowRepo(flow_windows) if flow_windows is not None else None,
    )


class _NoBilling:
    """Billing as the services see it, with nothing billed: no project has
    billing, and no beat an override."""

    async def exists(self, project_id: str) -> bool:
        return False

    async def delete(self, beat_id: str) -> bool:
        return False


def _beat_service(beats: list[Beat] | None = None):
    from beats.domain.services import BeatService

    return BeatService(beat_repo=_FakeBeatRepoForServices(beats), overrides=_NoBilling())


class _FakeAdjustmentRepo:
    """In-memory balance adjustments: the store the contract service reads
    and writes, and the two calls a contract write makes. Keyed on
    (project, date) like the real one's unique index. `calls` names every
    read and bulk delete, so a test can say a write touched none of them."""

    def __init__(self, adjustments: builtins.list[BalanceAdjustment] | None = None):
        self._adjustments: list[BalanceAdjustment] = list(adjustments or [])
        self.calls: list[str] = []

    async def list_by_project(
        self, project_id: str, start: date, end: date
    ) -> builtins.list[BalanceAdjustment]:
        self.calls.append("list_by_project")
        return sorted(
            (a for a in self._adjustments if a.project_id == project_id and start <= a.date <= end),
            key=lambda a: a.date,
        )

    async def upsert(self, adjustment: BalanceAdjustment) -> BalanceAdjustment:
        key = (adjustment.project_id, adjustment.date)
        self._adjustments = [a for a in self._adjustments if (a.project_id, a.date) != key]
        self._adjustments.append(adjustment)
        return adjustment

    async def delete(self, project_id: str, adjustment_id: str) -> bool:
        before = len(self._adjustments)
        self._adjustments = [
            a
            for a in self._adjustments
            if not (a.project_id == project_id and a.id == adjustment_id)
        ]
        return len(self._adjustments) < before

    async def day_of(self, project_id: str, adjustment_id: str) -> date | None:
        return next(
            (
                a.date
                for a in self._adjustments
                if a.project_id == project_id and a.id == adjustment_id
            ),
            None,
        )

    async def earliest(self, project_id: str, on_or_after: date) -> date | None:
        self.calls.append("earliest")
        days = [
            a.date
            for a in self._adjustments
            if a.project_id == project_id and a.date >= on_or_after
        ]
        return min(days, default=None)

    async def delete_by_project(self, project_id: str) -> int:
        self.calls.append("delete_by_project")
        before = len(self._adjustments)
        self._adjustments = [a for a in self._adjustments if a.project_id != project_id]
        return before - len(self._adjustments)


def _project_service(
    *,
    projects: list[Project] | None = None,
    beats: list[Beat] | None = None,
    adjustments: _FakeAdjustmentRepo | None = None,
):
    from beats.domain.services import ProjectService

    return ProjectService(
        project_repo=_FakeProjectRepoForServices(projects),
        beat_repo=_FakeBeatRepoForServices(beats),
        adjustments=adjustments or _FakeAdjustmentRepo(),
        billing=_NoBilling(),
    )


CONTRACT_START = date(2026, 1, 5)


def _day_job(id_: str | None = None, *, starts_on: date = CONTRACT_START, **region) -> Project:
    """A day job on one full-time term, with the given holiday region."""
    term = ContractTerm(
        effective_from=starts_on, schedule_type=ScheduleType.FULL_TIME, full_time_hours=40
    )
    contract = Contract(terms=[term], **region)
    return Project(id=id_, name="Day job", kind=ProjectKind.DAY_JOB, contract=contract)


class _FakeAbsenceRepo:
    """In-memory AbsenceStore: the range read and the two calendar writes."""

    def __init__(self, absences: builtins.list[Absence] | None = None):
        self._absences: list[Absence] = list(absences or [])

    async def list_by_project(
        self, project_id: str, start: date, end: date
    ) -> builtins.list[Absence]:
        return [a for a in self._absences if a.project_id == project_id and start <= a.date <= end]

    async def upsert(self, absence: Absence) -> Absence:
        key = (absence.project_id, absence.date)
        self._absences = [a for a in self._absences if (a.project_id, a.date) != key]
        self._absences.append(absence)
        return absence

    async def delete(self, project_id: str, absence_id: str) -> bool:
        before = len(self._absences)
        self._absences = [
            a for a in self._absences if not (a.project_id == project_id and a.id == absence_id)
        ]
        return len(self._absences) < before

    async def day_of(self, project_id: str, absence_id: str) -> date | None:
        return next(
            (a.date for a in self._absences if a.project_id == project_id and a.id == absence_id),
            None,
        )


# --- Integration fakes ---

# What the integration fakes hand back as a decoded body.
type JSONPayload = dict[str, Any] | builtins.list[Any]


class _FakeHTTPResponse:
    """Minimal stand-in for httpx.Response used by integration tests.

    The payload is a dict or a list because the real APIs return both —
    GitHub's commit and PR endpoints answer with arrays.
    """

    def __init__(self, status_code: int, json_data: JSONPayload | None = None):
        self.status_code = status_code
        self._json: JSONPayload = json_data if json_data is not None else {}

    def json(self) -> JSONPayload:
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

        request = httpx.Request("GET", "https://example.test")
        response = httpx.Response(self.status_code, request=request)
        raise httpx.HTTPStatusError("err", request=request, response=response)


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


def _flow_window(*, day: date, hour: int, score: float, minute: int = 0):
    from beats.domain.models import FlowWindow

    s = datetime.combine(day, datetime.min.time(), tzinfo=UTC).replace(hour=hour, minute=minute)
    return FlowWindow(
        device_id="dev-1",
        window_start=s,
        window_end=s + timedelta(minutes=1),
        flow_score=score,
    )
