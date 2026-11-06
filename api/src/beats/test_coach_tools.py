"""The tool dispatch the chat loop runs.

Split out of `test_coach.py` at the ceiling in roadmaps/file-sizes.md;
the shared fakes and factories are `coach_fakes.py`'s.
"""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from beats.coach import tools as tools_module
from beats.coach_fakes import (
    CONTRACT_NOW,
    ZURICH,
    _completed_beat,
    _contract_job,
    _fake_coach_repos,
    _project,
)


class TestToolsDispatch:
    """Each coach tool is an async function over the repos. The chat
    loop calls execute_tool(name, input). Wrong dispatch = the LLM
    gets useless text + the user perceives a confused coach.

    Tests cover every tool's happy path + the most consequential
    edge cases (filters, dates, empty data)."""

    async def test_unknown_tool_name_returns_error_string(self):
        """The LLM occasionally hallucinates tool names. The dispatcher
        must NOT raise — the chat loop's exception handler would turn
        a raise into an "Error: ..." tool_result, but a string
        return is more graceful (the LLM can recover)."""
        repos = _fake_coach_repos()
        result = await tools_module.execute_tool(
            "user-1",
            "non_existent_tool",
            {},
            repos=repos,
            projects=[],
        )
        assert "Unknown tool" in result
        assert "non_existent_tool" in result

    # -- get_projects --

    async def test_get_projects_lists_active_with_goal_lines(self):
        projects = [
            _project("p1", "Alpha", weekly_goal=10, goal_type="target"),
            _project("p2", "Beta"),
        ]
        repos = _fake_coach_repos(projects=projects)
        result = await tools_module.execute_tool(
            "user-1", "get_projects", {}, repos=repos, projects=projects
        )
        assert "Alpha" in result
        assert "Beta" in result
        # weekly_goal renders as a float; the LLM-facing format is
        # "(goal: 10.0h/wk target)".
        assert "10.0h/wk target" in result
        # No archived suffix on either.
        assert "archived" not in result

    async def test_get_projects_excludes_archived_by_default(self):
        projects = [
            _project("p1", "Active"),
            _project("p2", "Stale", archived=True),
        ]
        repos = _fake_coach_repos(projects=projects)
        result = await tools_module.execute_tool(
            "user-1", "get_projects", {}, repos=repos, projects=projects
        )
        assert "Active" in result
        assert "Stale" not in result

    async def test_get_projects_includes_archived_when_requested(self):
        projects = [
            _project("p1", "Active"),
            _project("p2", "Stale", archived=True),
        ]
        repos = _fake_coach_repos(projects=projects)
        result = await tools_module.execute_tool(
            "user-1",
            "get_projects",
            {"include_archived": True},
            repos=repos,
            projects=projects,
        )
        assert "Active" in result
        assert "Stale" in result
        assert "archived" in result

    async def test_get_projects_empty_returns_friendly_text(self):
        repos = _fake_coach_repos(projects=[])
        result = await tools_module.execute_tool(
            "user-1", "get_projects", {}, repos=repos, projects=[]
        )
        assert "No projects found" in result

    # -- get_beats --

    async def test_get_beats_default_window_summarizes_total(self):
        """Default window is the last 7 days. The summary line counts
        sessions and sums hours — pin the format the LLM relies on."""
        today = datetime.now(UTC).date()
        recent_iso = (datetime.combine(today, datetime.min.time()).replace(tzinfo=UTC)).isoformat()

        projects = [_project("p1", "Alpha")]
        beats = [_completed_beat(recent_iso[:-6], 60, "p1", note="planning")]
        repos = _fake_coach_repos(projects=projects, beats=beats)

        result = await tools_module.execute_tool(
            "user-1", "get_beats", {}, repos=repos, projects=projects
        )
        # The session line + the summary footer.
        assert "Alpha" in result
        assert "1h 0m" in result or "60m" in result
        assert "1 sessions, 1.0h total" in result or "1 sessions, 1.0" in result

    async def test_get_beats_filters_by_project_name_case_insensitive(self):
        projects = [
            _project("p1", "Alpha"),
            _project("p2", "Beta"),
        ]
        today_str = datetime.now(UTC).date().isoformat()
        beats = [
            _completed_beat(f"{today_str}T09:00:00", 30, "p1"),
            _completed_beat(f"{today_str}T10:00:00", 45, "p2"),
        ]
        repos = _fake_coach_repos(projects=projects, beats=beats)

        result = await tools_module.execute_tool(
            "user-1",
            "get_beats",
            {"project_name": "alpha"},  # lowercase — pin case-insensitivity
            repos=repos,
            projects=projects,
        )
        assert "Alpha" in result
        assert "Beta" not in result
        assert "1 sessions" in result

    async def test_get_beats_reads_the_users_days(self, monkeypatch):
        """At noon on Monday 19 October in Tokyo, a session from 07:00 that
        morning began at 22:00 UTC on the Sunday. It is Monday's, at 07:00,
        as the day context files it, not Sunday's at 22:00."""
        tokyo = ZoneInfo("Asia/Tokyo")
        instant = datetime(2026, 10, 19, 3, 0, tzinfo=UTC)

        class _At(datetime):
            @classmethod
            def now(cls, tz=None):
                return instant.astimezone(tz) if tz else instant.replace(tzinfo=None)

        monkeypatch.setattr(tools_module, "datetime", _At)
        projects = [_project("p1", "Alpha")]
        repos = _fake_coach_repos(
            projects=projects, beats=[_completed_beat("2026-10-18T22:00:00", 60, "p1")]
        )

        default = await tools_module.execute_tool(
            "user-1", "get_beats", {}, repos=repos, projects=projects, tz=tokyo
        )
        monday = await tools_module.execute_tool(
            "user-1",
            "get_beats",
            {"start_date": "2026-10-19", "end_date": "2026-10-19"},
            repos=repos,
            projects=projects,
            tz=tokyo,
        )

        assert default.splitlines()[0] == "2026-10-19 07:00 | Alpha | 1h 0m"
        assert monday.splitlines()[0] == "2026-10-19 07:00 | Alpha | 1h 0m"

    async def test_get_beats_empty_returns_friendly_text(self):
        repos = _fake_coach_repos(projects=[], beats=[])
        result = await tools_module.execute_tool(
            "user-1", "get_beats", {}, repos=repos, projects=[]
        )
        assert "No sessions found" in result

    # -- get_productivity_score --

    async def test_get_productivity_score_formats_components(self, monkeypatch):
        async def fake_score(_self, tz):
            return {
                "score": 87,
                "components": {
                    "consistency": 80,
                    "goals": 70,
                    "quality": 65,
                },
            }

        from beats.domain.intelligence import IntelligenceService

        monkeypatch.setattr(IntelligenceService, "compute_productivity_score", fake_score)

        projects = [_project("p1", "Alpha")]
        repos = _fake_coach_repos(projects=projects)
        result = await tools_module.execute_tool(
            "user-1", "get_productivity_score", {}, repos=repos, projects=projects
        )
        assert "Score: 87/100" in result
        assert "Consistency: 80" in result
        assert "Goals: 70" in result
        assert "Intentions" not in result

    async def test_get_productivity_score_swallows_exception(self, monkeypatch):
        """If IntelligenceService raises (e.g. divide-by-zero on fresh
        account), the tool returns an error message instead of
        crashing the chat stream. The LLM can describe the outcome
        to the user instead of seeing a 500."""
        from beats.domain.intelligence import IntelligenceService

        async def boom(_self, tz):
            raise ValueError("score broke")

        monkeypatch.setattr(IntelligenceService, "compute_productivity_score", boom)

        projects = [_project("p1", "Alpha")]
        repos = _fake_coach_repos(projects=projects)
        result = await tools_module.execute_tool(
            "user-1", "get_productivity_score", {}, repos=repos, projects=projects
        )
        assert "Could not compute score" in result
        assert "score broke" in result

    # -- get_patterns --

    async def test_get_patterns_lists_first_ten(self, monkeypatch):
        from beats.domain.intelligence import IntelligenceService
        from beats.domain.models import InsightCard

        async def fake_detect(_self, tz):
            return [
                InsightCard(
                    id="i1", type="day_pattern", title="Tuesdays peak", body="b1", priority=1
                ),
                InsightCard(id="i2", type="time_pattern", title="9am peak", body="b2", priority=2),
            ]

        monkeypatch.setattr(IntelligenceService, "detect_patterns", fake_detect)
        repos = _fake_coach_repos(projects=[])
        result = await tools_module.execute_tool(
            "user-1", "get_patterns", {}, repos=repos, projects=[]
        )
        assert "Tuesdays peak" in result
        assert "9am peak" in result
        assert "(day_pattern)" in result

    async def test_get_patterns_empty_returns_friendly_text(self, monkeypatch):
        from beats.domain.intelligence import IntelligenceService

        async def fake_detect(_self, tz):
            return []

        monkeypatch.setattr(IntelligenceService, "detect_patterns", fake_detect)
        repos = _fake_coach_repos(projects=[])
        result = await tools_module.execute_tool(
            "user-1", "get_patterns", {}, repos=repos, projects=[]
        )
        assert "No patterns" in result

    async def test_get_patterns_quotes_the_contracts_week_as_the_inbox_does(self, monkeypatch):
        """Pentecost Monday takes a day off a 40-hour week, which then expects
        32 hours. The stale-project card get_patterns returns quotes the 32, as
        the Inbox's does, not the term's nominal 40."""
        from beats.domain.intelligence import patterns as patterns_module

        class _At(datetime):
            @classmethod
            def now(cls, tz=None):
                return CONTRACT_NOW.astimezone(tz) if tz else CONTRACT_NOW.replace(tzinfo=None)

        monkeypatch.setattr(patterns_module, "datetime", _At)
        projects = [_contract_job()]
        repos = _fake_coach_repos(projects=projects)

        result = await tools_module.execute_tool(
            "user-1", "get_patterns", {}, repos=repos, projects=projects, tz=ZURICH
        )

        assert "Acme needs attention" in result
        assert "your contract still expects 32.0h of it this week" in result

    async def test_get_patterns_survives_one_failing_contract_read(self, monkeypatch):
        """AHM-85. A raise from one day job's week expectation failed
        detect_patterns whole, and the coach read "Pattern detection
        failed". Now the other job's card quotes its contract's 32 h and the
        failing one its term's plain 40 h."""
        from beats.domain.intelligence import patterns as patterns_module

        class _At(datetime):
            @classmethod
            def now(cls, tz=None):
                return CONTRACT_NOW.astimezone(tz) if tz else CONTRACT_NOW.replace(tzinfo=None)

        class _FailsForGlobex:
            async def current_weeks(self, projects, tz, as_of):
                return {}

            async def expected_for_week(self, project, week_of):
                if project.id == "globex":
                    raise RuntimeError("mongo went away")
                return 32.0

        monkeypatch.setattr(patterns_module, "datetime", _At)
        acme = _contract_job()
        globex = acme.model_copy(update={"id": "globex", "name": "Globex"})
        repos = _fake_coach_repos(projects=[acme, globex], contracts=_FailsForGlobex())

        result = await tools_module.execute_tool(
            "user-1", "get_patterns", {}, repos=repos, projects=[acme, globex], tz=ZURICH
        )

        assert "Pattern detection failed" not in result
        assert "Acme needs attention" in result
        assert "your contract still expects 32.0h of it this week" in result
        assert "Globex needs attention" in result
        assert "your contract still expects 40.0h of it this week" in result

    # -- search_beats --

    async def test_search_beats_matches_note_text(self):
        projects = [_project("p1", "Alpha")]
        beats = [
            _completed_beat("2026-05-01T09:00:00", 30, "p1", note="auth refactor planning"),
            _completed_beat("2026-05-02T09:00:00", 45, "p1", note="meeting prep"),
        ]
        repos = _fake_coach_repos(projects=projects, beats=beats)

        result = await tools_module.execute_tool(
            "user-1", "search_beats", {"query": "REFACTOR"}, repos=repos, projects=projects
        )
        # Case-insensitive match on the note text.
        assert "auth refactor planning" in result
        assert "meeting prep" not in result

    async def test_search_beats_matches_tags(self):
        projects = [_project("p1", "Alpha")]
        beats = [
            _completed_beat("2026-05-01T09:00:00", 30, "p1", tags=["focus", "deep-work"]),
            _completed_beat("2026-05-02T09:00:00", 45, "p1", tags=["meeting"]),
        ]
        repos = _fake_coach_repos(projects=projects, beats=beats)

        result = await tools_module.execute_tool(
            "user-1", "search_beats", {"query": "deep"}, repos=repos, projects=projects
        )
        assert "2026-05-01" in result
        assert "2026-05-02" not in result

    async def test_search_beats_empty_query_short_circuits(self):
        repos = _fake_coach_repos(projects=[], beats=[])
        result = await tools_module.execute_tool(
            "user-1", "search_beats", {"query": ""}, repos=repos, projects=[]
        )
        assert "No search query" in result

    async def test_search_beats_no_matches_returns_query_in_message(self):
        projects = [_project("p1", "Alpha")]
        beats = [_completed_beat("2026-05-01T09:00:00", 30, "p1", note="something")]
        repos = _fake_coach_repos(projects=projects, beats=beats)
        result = await tools_module.execute_tool(
            "user-1", "search_beats", {"query": "nonsense"}, repos=repos, projects=projects
        )
        assert "nonsense" in result
        assert "No sessions matching" in result
