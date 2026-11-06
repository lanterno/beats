"""What the coach is told: the system block, the messages and the user
context.

Split out of `test_coach.py` at the ceiling in roadmaps/file-sizes.md;
the shared fakes and factories are `coach_fakes.py`'s.
"""

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from beats.coach import context as context_module
from beats.coach import tools as tools_module
from beats.coach.memory import MemoryStore
from beats.coach.repos import (
    COACH_MEMORY_COLLECTION,
)
from beats.coach_fakes import (
    _async_db,
    _completed_beat,
    _fake_coach_repos,
    _FakeAbsenceStoreForCoach,
    _FakeAdjustmentStoreForCoach,
    _FakeBeatRepoForTools,
    _FakeProjectRepoForTools,
    _project,
)
from beats.infrastructure.database import Database
from beats.settings import settings


class TestBuildSystemBlock:
    """Pure function — returns COACH_PERSONA. Locked here so a
    refactor that quietly changes the persona text is visible."""

    def test_returns_non_empty_string(self):
        result = context_module.build_system_block()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_returns_the_coach_persona(self):
        from beats.coach.prompts import COACH_PERSONA

        assert context_module.build_system_block() == COACH_PERSONA


class TestBuildCoachMessages:
    """build_coach_messages composes the (system, messages, spec) tuple
    every coach call uses. The structure is load-bearing for prompt
    caching (the cache_spec marks index 0 of messages as cached, which
    is the user_ctx block — a refactor that re-orders the preamble
    without updating the spec would silently miss the cache)."""

    @pytest.fixture
    def patched_context(self, monkeypatch):
        """Stub build_repos / build_user_context / build_day_context so
        we can drive the composition without real Mongo data."""

        async def fake_build_repos(_user_id):
            return _fake_coach_repos()

        async def fake_user_ctx(_user_id, _repos, _tz=None):
            return "USER_CTX_BLOCK"

        async def fake_day_ctx(_user_id, _repos, _target_date, _tz=None):
            return "DAY_CTX_BLOCK"

        monkeypatch.setattr(context_module, "build_repos", fake_build_repos)
        monkeypatch.setattr(context_module, "build_user_context", fake_user_ctx)
        monkeypatch.setattr(context_module, "build_day_context", fake_day_ctx)

    async def test_returns_system_messages_and_spec(self, patched_context):
        system, _messages, spec = await context_module.build_coach_messages(
            "user-1", "what should I do today?"
        )
        # System is the persona string.
        assert isinstance(system, str)
        assert len(system) > 0
        # Spec marks system + first message index for caching.
        assert spec.system_cached is True
        assert spec.cached_turn_indices == [0]

    async def test_preamble_is_user_assistant_user_assistant_user(self, patched_context):
        """The preamble alternates user/assistant/user/assistant before
        the actual user message — Anthropic's API requires user/assistant
        alternation, and the fake "Context loaded." / "Ready." assistant
        turns are how we keep the shape valid while loading large
        cacheable context blocks. Pin the role sequence — a refactor
        that drops one of the assistant acks would break the API call."""
        _, messages, _ = await context_module.build_coach_messages("user-1", "hello")
        roles = [m["role"] for m in messages]
        # First 4 are the preamble, then the trailing user message.
        assert roles[:5] == ["user", "assistant", "user", "assistant", "user"]

    async def test_user_ctx_is_message_index_0(self, patched_context):
        """Cache spec marks index 0 — that index MUST be the user
        context block (the heavy 30-day aggregate that's cheap to cache).
        A refactor that swapped index 0 for the day_ctx would silently
        cache the wrong (volatile) content."""
        _, messages, spec = await context_module.build_coach_messages("user-1", "hi")
        assert spec.cached_turn_indices == [0]
        assert messages[0]["content"] == "USER_CTX_BLOCK"

    async def test_day_ctx_is_message_index_2(self, patched_context):
        """Day context follows the user_ctx ack at index 1, lands at
        index 2. NOT cached — it changes every day."""
        _, messages, _ = await context_module.build_coach_messages("user-1", "hi")
        assert messages[2]["content"] == "DAY_CTX_BLOCK"

    async def test_user_message_is_last(self, patched_context):
        _, messages, _ = await context_module.build_coach_messages("user-1", "what's my best week?")
        assert messages[-1]["role"] == "user"
        assert messages[-1]["content"] == "what's my best week?"

    async def test_history_inserted_between_preamble_and_user_message(self, patched_context):
        """History from prior turns goes after the preamble (index 4)
        and before the new user message. Pin so a refactor doesn't put
        history INSIDE the preamble (would break cache index 0) or
        after the user message (would mean the LLM sees the new
        question before the conversation it's responding to)."""
        history = [
            {"role": "user", "content": "earlier question"},
            {"role": "assistant", "content": "earlier answer"},
        ]
        _, messages, _ = await context_module.build_coach_messages(
            "user-1", "follow up", history=history
        )
        # Preamble (4) + history (2) + user message (1) = 7
        assert len(messages) == 7
        assert messages[4]["content"] == "earlier question"
        assert messages[5]["content"] == "earlier answer"
        assert messages[6]["content"] == "follow up"

    async def test_no_history_omits_history_section(self, patched_context):
        _, messages, _ = await context_module.build_coach_messages("user-1", "hi")
        # Preamble (4) + user message (1) = 5
        assert len(messages) == 5

    async def test_target_date_threads_to_day_ctx(self, monkeypatch):
        """Locks that target_date is passed through. Without this, a
        brief generated for a past date would silently use today's
        signals — confusing if a user asks the coach to brief
        yesterday."""
        captured = {}

        async def fake_build_repos(_user_id):
            return _fake_coach_repos()

        async def fake_user_ctx(_user_id, _repos, _tz=None):
            return "USER"

        async def fake_day_ctx(_user_id, _repos, target_date, _tz=None):
            captured["target_date"] = target_date
            return "DAY"

        monkeypatch.setattr(context_module, "build_repos", fake_build_repos)
        monkeypatch.setattr(context_module, "build_user_context", fake_user_ctx)
        monkeypatch.setattr(context_module, "build_day_context", fake_day_ctx)

        target = date(2026, 5, 1)
        await context_module.build_coach_messages("user-1", "yesterday's brief", target_date=target)
        assert captured["target_date"] == target


class TestBuildUserContext:
    """build_user_context is the heavy 30-day aggregate. Tests cover
    the structural composition (header lines, sections) and the
    productivity-score-unavailable fallback. Repo data uses small
    in-memory fakes."""

    @pytest.fixture(autouse=True)
    async def _setup_db(self):
        """build_user_context reads from MemoryStore which uses
        Database.get_db(). Connect for the duration of the test."""
        await Database.connect(settings.db_dsn, settings.db_name)
        await Database.get_db()[COACH_MEMORY_COLLECTION].delete_many({})
        yield
        await Database.disconnect()

    async def test_renders_section_headers_in_expected_order(self, monkeypatch):
        """Pin the markdown structure the LLM consumes — section
        order matters because the model gives early sections more
        attention. A refactor that re-orders these would silently
        change coach behavior."""
        from beats.domain.intelligence import IntelligenceService

        async def fake_score(_self, tz):
            return {
                "score": 75,
                "components": {
                    "consistency": 80,
                    "goals": 75,
                    "quality": 75,
                },
            }

        monkeypatch.setattr(IntelligenceService, "compute_productivity_score", fake_score)

        repos = _fake_coach_repos(projects=[_project("p1", "Alpha", weekly_goal=10)])
        result = await context_module.build_user_context("user-1", repos)

        # Expected sections in order.
        sections = [
            "## User profile (30-day window)",
            "Active projects: Alpha",
            "### Hours by project (last 30 days)",
            "### Weekly totals",
            "Productivity score: 75/100",
            "### Weekly goals",
            "## Coach memory",
        ]
        last_pos = -1
        for s in sections:
            pos = result.find(s)
            assert pos > last_pos, f"section {s!r} out of order in:\n{result}"
            last_pos = pos

    async def test_score_unavailable_renders_fallback(self, monkeypatch):
        """When IntelligenceService raises (fresh account, divide-by-
        zero), the context should still render — with "Productivity
        score: unavailable" instead of a Python traceback. Pin so a
        refactor of the except-Exception swallow doesn't quietly
        break the coach for new users."""
        from beats.domain.intelligence import IntelligenceService

        async def boom(_self, tz):
            raise ValueError("fresh user")

        monkeypatch.setattr(IntelligenceService, "compute_productivity_score", boom)

        repos = _fake_coach_repos(projects=[_project("p1", "Alpha")])
        result = await context_module.build_user_context("user-1", repos)
        assert "Productivity score: unavailable" in result

    async def test_flow_rollup_renders_from_daemon_windows(self, monkeypatch):
        """The 30-day flow rollup surfaces avg score + top repo/language
        from the ambient daemon's windows — the coach's automatic
        understanding of what work looked like. Pin so it doesn't drop out."""
        from datetime import UTC, datetime

        from beats.domain.intelligence import IntelligenceService
        from beats.domain.models import FlowWindow

        async def fake_score(_self, tz):
            return {"score": 70, "components": {"consistency": 70, "goals": 70, "quality": 70}}

        monkeypatch.setattr(IntelligenceService, "compute_productivity_score", fake_score)

        recent = datetime.now(UTC) - timedelta(days=2)
        windows = [
            FlowWindow(
                device_id="d",
                window_start=recent,
                window_end=recent + timedelta(minutes=5),
                flow_score=0.8,
                editor_repo="/home/me/beats",
                editor_language="Python",
            ),
            FlowWindow(
                device_id="d",
                window_start=recent + timedelta(minutes=6),
                window_end=recent + timedelta(minutes=11),
                flow_score=0.6,
                editor_repo="/home/me/beats",
                editor_language="Python",
            ),
        ]
        repos = _fake_coach_repos(projects=[_project("p1", "Alpha")], flow_windows=windows)
        result = await context_module.build_user_context("user-1", repos)
        assert "### Flow (30 days, from ambient signals)" in result
        assert "repo beats" in result
        assert "top language python" in result

    async def test_no_memory_renders_empty_marker(self, monkeypatch):
        """First-run users have no coach_memory document. The context
        should render the placeholder so the LLM doesn't see "None"
        or an unterminated section. Pin the exact phrasing the cached
        context expects."""
        from beats.domain.intelligence import IntelligenceService

        async def fake_score(_self, tz):
            return {
                "score": 50,
                "components": {
                    "consistency": 50,
                    "goals": 50,
                    "quality": 50,
                },
            }

        monkeypatch.setattr(IntelligenceService, "compute_productivity_score", fake_score)

        repos = _fake_coach_repos(projects=[_project("p1", "Alpha")])
        result = await context_module.build_user_context("user-1", repos)
        assert "(No coach memory yet" in result

    async def test_existing_memory_is_inlined(self, monkeypatch):
        """When MemoryStore has content, that content appears verbatim
        under the ## Coach memory section. Pin so a refactor of the
        MemoryStore.read() call doesn't drop the user's persisted
        personality from the cache."""
        from beats.domain.intelligence import IntelligenceService

        async def fake_score(_self, tz):
            return {
                "score": 60,
                "components": {
                    "consistency": 60,
                    "goals": 60,
                    "quality": 60,
                },
            }

        monkeypatch.setattr(IntelligenceService, "compute_productivity_score", fake_score)

        # Seed memory directly via MemoryStore.
        client, db = _async_db()
        try:
            store = MemoryStore(db, "user-1")
            await store.write("# Memory\n\nUser ships at night.")
        finally:
            await client.close()

        repos = _fake_coach_repos(projects=[_project("p1", "Alpha")])
        result = await context_module.build_user_context("user-1", repos)
        assert "User ships at night." in result

    async def test_no_goals_renders_no_goals_set(self, monkeypatch):
        from beats.domain.intelligence import IntelligenceService

        async def fake_score(_self, tz):
            return {
                "score": 50,
                "components": {
                    "consistency": 50,
                    "goals": 50,
                    "quality": 50,
                },
            }

        monkeypatch.setattr(IntelligenceService, "compute_productivity_score", fake_score)

        # Project with no weekly_goal.
        repos = _fake_coach_repos(projects=[_project("p1", "Alpha", weekly_goal=None)])
        result = await context_module.build_user_context("user-1", repos)
        assert "(No goals set)" in result

    async def test_goal_line_and_contract_week_name_one_term_on_sunday_evening(self, monkeypatch):
        """80 % of 42 h until Sunday 18 October, full-time from Monday 19. At
        01:00 UTC on the 19th it is still Sunday evening in Los Angeles: the
        goal line, the contract week's label and get_projects all name the
        user's week's term, where UTC's Monday would have put next week's
        "full-time" beside this week's 33.6 h."""
        from beats.domain.contract_service import ContractService
        from beats.domain.models import Contract, ContractTerm, Project, ProjectKind, ScheduleType

        los_angeles = ZoneInfo("America/Los_Angeles")
        instant = datetime(2026, 10, 19, 1, 0, tzinfo=UTC)

        class _At(datetime):
            @classmethod
            def now(cls, tz=None):
                return instant.astimezone(tz) if tz else instant.replace(tzinfo=None)

        monkeypatch.setattr(context_module, "datetime", _At)
        monkeypatch.setattr(tools_module, "datetime", _At)
        terms = [
            ContractTerm(
                effective_from=date(2026, 1, 5),
                schedule_type=ScheduleType.PART_TIME,
                full_time_hours=42,
                percentage=0.8,
            ),
            ContractTerm(
                effective_from=date(2026, 10, 19),
                schedule_type=ScheduleType.FULL_TIME,
                full_time_hours=42,
            ),
        ]
        job = Project(
            id="job", name="Acme", kind=ProjectKind.DAY_JOB, contract=Contract(terms=terms)
        )
        repos = _fake_coach_repos(
            projects=[job],
            contracts=ContractService(
                project_repo=_FakeProjectRepoForTools([job]),
                beat_repo=_FakeBeatRepoForTools([]),
                absence_repo=_FakeAbsenceStoreForCoach([]),
                adjustment_repo=_FakeAdjustmentStoreForCoach([]),
                now=lambda tz: instant.astimezone(tz),
            ),
        )

        user_ctx = await context_module.build_user_context("user-1", repos, los_angeles)
        day_ctx = await context_module.build_day_context("user-1", repos, tz=los_angeles)
        tool = await tools_module.execute_tool(
            "user-1", "get_projects", {}, repos=repos, projects=[job], tz=los_angeles
        )

        assert "  Acme: 33.6h/week (contract, 80%)" in user_ctx.splitlines()
        assert "  Acme (contract, 80%): this week expects 33.6 h" in day_ctx
        assert "(goal: 33.6h/wk, contract, 80%)" in tool
        for text in (user_ctx, day_ctx, tool):
            assert "full-time" not in text
        # The same instant on UTC's week is the full-time term's.
        utc_ctx = await context_module.build_user_context("user-1", repos)
        assert "  Acme: 42h/week (contract, full-time)" in utc_ctx.splitlines()

    async def test_goal_line_and_get_projects_give_a_terms_hours_as_the_page(self):
        """68.75 % of 42 h is 28.875 h, which the page shows as 28.88 h. The
        goal line and get_projects said 28.875."""
        from beats.domain.models import Contract, ContractTerm, Project, ProjectKind, ScheduleType

        term = ContractTerm(
            effective_from=date(2026, 1, 5),
            schedule_type=ScheduleType.PART_TIME,
            full_time_hours=42,
            percentage=0.6875,
        )
        job = Project(
            id="job", name="Acme", kind=ProjectKind.DAY_JOB, contract=Contract(terms=[term])
        )
        repos = _fake_coach_repos(projects=[job])

        user_ctx = await context_module.build_user_context("user-1", repos)
        tool = await tools_module.execute_tool(
            "user-1", "get_projects", {}, repos=repos, projects=[job]
        )

        assert "  Acme: 28.88h/week (contract, 68.75%)" in user_ctx.splitlines()
        assert "- Acme (goal: 28.88h/wk, contract, 68.75%)" in tool

    async def test_weekly_totals_are_the_users_weeks(self, monkeypatch):
        """At 18:00 on Tuesday 20 October in Los Angeles, an hour from 20:00
        on Sunday the 18th belongs to the week of 12 October there, though
        it began at 03:00 UTC on Monday the 19th."""
        los_angeles = ZoneInfo("America/Los_Angeles")
        instant = datetime(2026, 10, 21, 1, 0, tzinfo=UTC)

        class _At(datetime):
            @classmethod
            def now(cls, tz=None):
                return instant.astimezone(tz) if tz else instant.replace(tzinfo=None)

        monkeypatch.setattr(context_module, "datetime", _At)
        repos = _fake_coach_repos(
            projects=[_project("p1", "Alpha")],
            beats=[_completed_beat("2026-10-19T03:00:00", 60, "p1")],
        )

        result = await context_module.build_user_context("user-1", repos, los_angeles)

        lines = result.splitlines()
        assert "  Week of Oct 12: 1.0h" in lines
        assert "  Week of Oct 05: 0.0h" in lines
