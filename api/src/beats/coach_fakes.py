"""Fakes and factories the coach suites share — no tests of their own.

`test_coach.py` grew past the ceiling in roadmaps/file-sizes.md and split
by surface; the gateway responses, the in-memory repos, the fixed dates and
the small factories are used by more than one of those files. Not
`test_`-prefixed, so pytest does not collect it.
"""

import os
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from anthropic.types import TextBlock
from pymongo import AsyncMongoClient

from beats.coach.gateway import (
    MODEL_PRICING,
    GatewayResponse,
)
from beats.coach.repos import (
    CoachRepos,
)


def _async_db():
    """Build an async PyMongo handle for the test database. The conftest's
    testcontainer sets DB_DSN/DB_NAME; we connect directly so the
    coach modules can be exercised with their real (async) signature."""
    dsn = os.environ.get("DB_DSN", "mongodb://localhost:27017")
    db_name = os.environ.get("DB_NAME", "beats_test")
    client = AsyncMongoClient(dsn)
    return client, client[db_name]


def _text_block(text: str) -> TextBlock:
    """A real anthropic.types.TextBlock — brief.py extracts `.text` from
    each block via isinstance(), so a stand-in has to be the real type."""
    return TextBlock(type="text", text=text, citations=None)


def _fake_gateway_response(text: str = "Good morning. Two intentions today.") -> GatewayResponse:
    """Build a GatewayResponse the way `complete()` would — content is
    a list of TextBlocks, model + token + cost fields populated."""
    return GatewayResponse(
        content=[_text_block(text)],
        model="claude-opus-4-7",
        input_tokens=1234,
        output_tokens=89,
        cache_creation_input_tokens=400,
        cache_read_input_tokens=800,
        cost_usd=0.012,
        stop_reason="end_turn",
    )


SONNET_46 = "claude-sonnet-4-6"
_S46 = MODEL_PRICING[SONNET_46]


def _fake_tool_use(name: str, tool_input: dict, block_id: str = "tu_1"):
    """Build an anthropic.types.ToolUseBlock so isinstance() in chat.py
    narrows it correctly."""
    from anthropic.types import ToolUseBlock

    return ToolUseBlock(type="tool_use", id=block_id, name=name, input=tool_input)


def _resp(content_blocks, **overrides) -> GatewayResponse:
    """Wrap a list of content blocks into a GatewayResponse with
    sensible defaults for the fields chat.py doesn't read."""
    return GatewayResponse(
        content=content_blocks,
        model="claude-opus-4-7",
        input_tokens=overrides.get("input_tokens", 100),
        output_tokens=overrides.get("output_tokens", 50),
        cache_creation_input_tokens=0,
        cache_read_input_tokens=0,
        cost_usd=overrides.get("cost_usd", 0.001),
        stop_reason=overrides.get("stop_reason", "end_turn"),
    )


class _FakeRepos:
    """Stand-in for the CoachRepos dataclass — chat.py only calls
    `.project.list()` to seed the tool dispatch context."""

    class _ProjectRepo:
        async def list(self):
            return []

    project = _ProjectRepo()


class _FakeProjectRepoForTools:
    """Returns a fixed list of project objects — or one of them, by id, which
    is what the contract service asks of a project store."""

    def __init__(self, projects):
        self._projects = projects

    async def list(self, archived: bool = False):
        if archived:
            return list(self._projects)
        return [p for p in self._projects if not p.archived]

    async def get_by_id(self, project_id):
        from beats.domain.exceptions import ProjectNotFound

        for project in self._projects:
            if project.id == project_id:
                return project
        raise ProjectNotFound()


class _FakeBeatRepoForTools:
    """A fixed list of beats, satisfying CompletedBeatReader.

    `list_completed_in_range` is here for the contract rather than the tests —
    the coach reaches it only through IntelligenceService, which these tests
    stub out."""

    def __init__(self, beats):
        self._beats = beats

    async def list_all_completed(self):
        return [b for b in self._beats if b.end is not None]

    async def list_completed_in_range(self, start, end):
        return [b for b in self._beats if b.end is not None and start <= b.start.date() <= end]

    async def list_by_project(self, project_id, since=None):
        out = [b for b in self._beats if b.project_id == project_id]
        return out if since is None else [b for b in out if b.start >= since]


class _FakeAbsenceStoreForCoach:
    """In-memory AbsenceStore. The coach only reads; the writes are here
    because the contract service's port names them."""

    def __init__(self, absences):
        self._absences = list(absences)

    async def list_by_project(self, project_id, start, end):
        return [a for a in self._absences if a.project_id == project_id and start <= a.date <= end]

    async def upsert(self, absence):
        raise NotImplementedError

    async def delete(self, project_id, absence_id):
        raise NotImplementedError

    async def day_of(self, project_id, absence_id):
        raise NotImplementedError


class _FakeAdjustmentStoreForCoach:
    """In-memory AdjustmentStore: the balance counts what is here, as the
    project page's does. The coach only reads; the writes are here because
    the contract service's port names them."""

    def __init__(self, adjustments):
        self._adjustments = list(adjustments)

    async def list_by_project(self, project_id, start, end):
        return sorted(
            (a for a in self._adjustments if a.project_id == project_id and start <= a.date <= end),
            key=lambda a: a.date,
        )

    async def upsert(self, adjustment):
        raise NotImplementedError

    async def delete(self, project_id, adjustment_id):
        raise NotImplementedError

    async def day_of(self, project_id, adjustment_id):
        raise NotImplementedError


class _FakeFlowRepoForCoach:
    """Returns flow windows whose window_start falls in [start, end]."""

    def __init__(self, windows):
        self._windows = windows

    async def list_by_range(self, start, end, **kwargs):
        return [w for w in self._windows if start <= w.window_start <= end]


# The contract service's clock in these tests: Thursday 28 May 2026, noon in
# Zürich. The week is Monday 25 May, Pentecost Monday in CH-ZH.
ZURICH = ZoneInfo("Europe/Zurich")
CONTRACT_NOW = datetime(2026, 5, 28, 12, 0, tzinfo=ZURICH)
CONTRACT_TODAY = CONTRACT_NOW.date()
CONTRACT_MONDAY = date(2026, 5, 25)


def _fake_coach_repos(
    *,
    projects=None,
    beats=None,
    flow_windows=None,
    absences=None,
    adjustments=None,
    contracts=None,
) -> CoachRepos:
    """The real CoachRepos, holding in-memory repositories.

    It used to be a look-alike class, which meant nothing checked that the
    fakes matched what the coach asks for. Now the dataclass is protocol-typed,
    so this is both the real thing and a type error if a fake drifts.

    `contracts` defaults to the real ContractService over the same fakes, on a
    clock fixed at `CONTRACT_NOW`, so the contract section runs the project
    page's own assembly and passes on whatever day CI runs."""
    from beats.domain.contract_service import ContractService

    project_repo = _FakeProjectRepoForTools(projects or [])
    beat_repo = _FakeBeatRepoForTools(beats or [])
    return CoachRepos(
        project=project_repo,
        beat=beat_repo,
        flow=_FakeFlowRepoForCoach(flow_windows or []),
        contracts=contracts
        or ContractService(
            project_repo=project_repo,
            beat_repo=beat_repo,
            absence_repo=_FakeAbsenceStoreForCoach(absences or []),
            adjustment_repo=_FakeAdjustmentStoreForCoach(adjustments or []),
            now=lambda tz: CONTRACT_NOW.astimezone(tz),
        ),
    )


def _project(id_: str, name: str, *, weekly_goal=None, goal_type="target", archived=False):
    """Quick project factory."""
    from beats.domain.models import GoalType, Project

    return Project(
        id=id_,
        name=name,
        weekly_goal=weekly_goal,
        goal_type=GoalType(goal_type) if goal_type else GoalType.TARGET,
        archived=archived,
    )


def _completed_beat(start_iso: str, minutes: int, project_id: str, *, note=None, tags=None):
    from beats.domain.models import Beat

    s = datetime.fromisoformat(start_iso).replace(tzinfo=UTC)
    return Beat(
        id="b-" + start_iso,
        project_id=project_id,
        start=s,
        end=s + timedelta(minutes=minutes),
        note=note,
        tags=list(tags or []),
    )


def _to_fixed_1(hours: float) -> str:
    """The page's `hours.toFixed(1)` for hours ≥ 0, worked from ECMA-262's
    definition rather than from the coach's code: n is the integer for
    which n / 10 − hours is closest to zero on the float's exact binary
    value, the larger n on a tie."""
    from fractions import Fraction
    from math import floor

    n = floor(Fraction(hours) * 10 + Fraction(1, 2))
    return f"{n // 10}.{n % 10}"


def _contract_job(
    *,
    weekly=40.0,
    starts=date(2026, 5, 18),
    region=("CH", "ZH"),
    opening=0.0,
    ended_on=None,
    company=(),
    objective=False,
):
    from beats.domain.models import (
        CompanyHoliday,
        Contract,
        ContractTerm,
        Project,
        ProjectKind,
        ScheduleType,
    )

    term = (
        ContractTerm(effective_from=starts, schedule_type=ScheduleType.OBJECTIVE)
        if objective
        else ContractTerm(
            effective_from=starts, schedule_type=ScheduleType.CUSTOM, weekly_hours=weekly
        )
    )
    country, subdivision = region if region else (None, None)
    contract = Contract(
        terms=[term],
        holiday_country=country,
        holiday_subdivision=subdivision,
        opening_balance_hours=opening,
        ended_on=ended_on,
        company_holidays=[CompanyHoliday(date=day, name=name) for day, name in company],
    )
    return Project(id="job", name="Acme", kind=ProjectKind.DAY_JOB, contract=contract)
