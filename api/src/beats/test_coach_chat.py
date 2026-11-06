"""The streaming chat turn and the recent-data summary it is given.

Split out of `test_coach.py` at the ceiling in roadmaps/file-sizes.md;
the shared fakes and factories are `coach_fakes.py`'s.
"""

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from anthropic.types import TextBlock

from beats.coach import chat as chat_module
from beats.coach import memory_rewrite as memory_rewrite_module
from beats.coach.gateway import (
    GatewayResponse,
)
from beats.coach.repos import (
    COACH_CONVERSATIONS_COLLECTION,
)
from beats.coach_fakes import (
    _completed_beat,
    _fake_coach_repos,
    _fake_tool_use,
    _FakeRepos,
    _project,
    _resp,
)
from beats.infrastructure.database import Database
from beats.settings import settings


class TestHandleChatTurn:
    """The streaming chat turn — runs an LLM round, optionally executes
    tools, optionally loops, and yields SSE events. Tested by replacing
    `complete()` with a sequence of canned GatewayResponses and
    `execute_tool` with a deterministic stub."""

    @pytest.fixture(autouse=True)
    async def _setup(self, monkeypatch):
        await Database.connect(settings.db_dsn, settings.db_name)
        await Database.get_db()[COACH_CONVERSATIONS_COLLECTION].delete_many({})

        # Replace the upstream context builder so we don't need to
        # seed a fake user with full beats/projects history.
        async def fake_build(user_id, message, history=None, **_):
            messages = list(history or [])
            messages.append({"role": "user", "content": message})
            return ("system", messages, None)

        monkeypatch.setattr(chat_module, "build_coach_messages", fake_build)

        # Stub build_repos so we don't hit the project repo for real.
        async def fake_build_repos(_user_id):
            return _FakeRepos()

        monkeypatch.setattr(chat_module, "build_repos", fake_build_repos)

        yield
        await Database.disconnect()

    @pytest.fixture
    def patch_complete(self, monkeypatch):
        """Returns a setter that lets a test queue a sequence of
        GatewayResponses; chat.py's tool-loop pulls one per round."""
        responses: list[GatewayResponse] = []
        captured_calls: list[dict] = []

        async def fake_complete(**kwargs):
            captured_calls.append(kwargs)
            if not responses:
                raise AssertionError("complete() called more times than expected")
            return responses.pop(0)

        monkeypatch.setattr(chat_module, "complete", fake_complete)
        return responses, captured_calls

    @pytest.fixture
    def patch_execute_tool(self, monkeypatch):
        """Records every tool call and returns a deterministic string."""
        calls: list[tuple] = []

        async def fake_execute(_user_id, name, tool_input, *, repos, projects, tz):
            calls.append((name, tool_input))
            return f"<{name} result>"

        monkeypatch.setattr(chat_module, "execute_tool", fake_execute)
        return calls

    async def _drain(self, gen):
        events = []
        async for ev in gen:
            events.append(ev)
        return events

    async def test_text_only_response_emits_text_then_done(self, patch_complete):
        """Happy path with no tool use — single LLM round, single text
        block, terminates with the done event."""

        responses, _calls = patch_complete
        responses.append(_resp([TextBlock(type="text", text="hello there", citations=None)]))

        events = await self._drain(
            chat_module.handle_chat_turn(user_id="user-1", message="hi", conversation_id="c-1")
        )

        assert events[0] == {"type": "text", "text": "hello there"}
        assert events[-1] == {"type": "done", "conversation_id": "c-1"}

    async def test_persists_user_and_assistant_messages(self, patch_complete):

        responses, _ = patch_complete
        responses.append(_resp([TextBlock(type="text", text="reply", citations=None)]))

        await self._drain(
            chat_module.handle_chat_turn(user_id="user-1", message="hi", conversation_id="c-1")
        )

        rows = (
            await Database.get_db()[COACH_CONVERSATIONS_COLLECTION]
            .find({"conversation_id": "c-1"})
            .to_list(10)
        )
        roles = sorted([r["role"] for r in rows])
        # The user message and the assistant message both persist.
        assert roles == ["assistant", "user"]
        assistant = next(r for r in rows if r["role"] == "assistant")
        assert assistant["content"] == "reply"

    async def test_auto_generates_conversation_id_when_omitted(self, patch_complete):
        """Locks the conversation_id contract — caller can pass None
        and chat.py mints a uuid that flows through to the done event
        and to every persisted row."""

        responses, _ = patch_complete
        responses.append(_resp([TextBlock(type="text", text="ok", citations=None)]))

        events = await self._drain(chat_module.handle_chat_turn(user_id="user-1", message="hi"))

        done = next(ev for ev in events if ev["type"] == "done")
        cid = done["conversation_id"]
        assert cid  # not empty
        # And the persisted user message carries the same id.
        row = await Database.get_db()[COACH_CONVERSATIONS_COLLECTION].find_one({"role": "user"})
        assert row is not None
        assert row["conversation_id"] == cid

    async def test_tool_use_round_then_text_round(self, patch_complete, patch_execute_tool):
        """Round 1: LLM emits tool_use → chat.py runs the tool, yields
        tool_use + tool_result events. Round 2: LLM emits text → done.
        Locks the loop's two-round happy path."""

        responses, calls = patch_complete
        responses.append(
            _resp(
                [
                    TextBlock(type="text", text="let me check", citations=None),
                    _fake_tool_use("get_score", {}, "tu_1"),
                ]
            )
        )
        responses.append(_resp([TextBlock(type="text", text="your score is X", citations=None)]))

        events = await self._drain(
            chat_module.handle_chat_turn(
                user_id="user-1", message="how am I doing?", conversation_id="c-1"
            )
        )

        # Sequence: round 1 text, tool_use, tool_result, round 2 text, done.
        types = [ev["type"] for ev in events]
        assert types == ["text", "tool_use", "tool_result", "text", "done"]

        # Tool was actually invoked.
        assert patch_execute_tool == [("get_score", {})]

        # Round 2 received the tool_result in messages.
        assert len(calls) == 2
        round2_messages = calls[1]["messages"]
        # Last user-role message in round 2 carries the tool_result block.
        last = round2_messages[-1]
        assert last["role"] == "user"
        assert last["content"][0]["type"] == "tool_result"
        assert last["content"][0]["content"] == "<get_score result>"

    async def test_tool_execution_error_becomes_error_text(self, patch_complete, monkeypatch):
        """A tool that raises an exception must NOT 500 the chat
        stream — chat.py catches and surfaces "Error: ..." in the
        tool_result so the LLM can recover and the user sees the
        failure."""

        async def failing_execute(*_args, **_kwargs):
            raise RuntimeError("tool blew up")

        monkeypatch.setattr(chat_module, "execute_tool", failing_execute)

        responses, _ = patch_complete
        responses.append(_resp([_fake_tool_use("get_score", {}, "tu_1")]))
        responses.append(
            _resp([TextBlock(type="text", text="couldn't fetch your score", citations=None)])
        )

        events = await self._drain(
            chat_module.handle_chat_turn(user_id="user-1", message="score?", conversation_id="c-1")
        )

        tool_result = next(ev for ev in events if ev["type"] == "tool_result")
        assert "Error: tool blew up" in tool_result["result"]

    async def test_tool_result_truncated_in_sse_event_only(self, patch_complete, monkeypatch):
        """The SSE event truncates the tool result to
        TOOL_RESULT_DISPLAY_LIMIT chars (so the UI doesn't render a
        novel), but the FULL text goes back to the LLM in the next
        round's messages. Pin both halves — without the LLM-side
        full-content guarantee, large tool outputs would silently
        get truncated mid-thought."""

        big_payload = "x" * 5000  # well over the 500-char display cap

        async def big_execute(*_args, **_kwargs):
            return big_payload

        monkeypatch.setattr(chat_module, "execute_tool", big_execute)

        responses, calls = patch_complete
        responses.append(_resp([_fake_tool_use("search_beats", {}, "tu_1")]))
        responses.append(_resp([TextBlock(type="text", text="ok", citations=None)]))

        events = await self._drain(
            chat_module.handle_chat_turn(user_id="user-1", message="search", conversation_id="c-1")
        )

        # SSE event truncated to display limit.
        tool_result_event = next(ev for ev in events if ev["type"] == "tool_result")
        assert len(tool_result_event["result"]) == chat_module.TOOL_RESULT_DISPLAY_LIMIT

        # But the LLM message in round 2 has the FULL payload — locks
        # the contract that the LLM gets to see what really came back.
        round2_messages = calls[1]["messages"]
        last = round2_messages[-1]
        assert last["content"][0]["content"] == big_payload  # full size

    async def test_max_tool_turns_constant_value(self):
        """Locks the constant value at 8. Changing this is a pricing
        decision (each round = one full LLM call) so should be
        deliberate. Bumping from 5 (the previous inline cap) gives
        legitimate research-style turns headroom for a 4-5 tool
        chain plus a clarifying follow-up."""
        assert chat_module.MAX_TOOL_TURNS == 8

    async def test_tool_loop_exhaustion_emits_typed_error_event(
        self, patch_complete, patch_execute_tool
    ):
        """When the LLM can't produce text within MAX_TOOL_TURNS rounds,
        the handler emits a typed `error` event (NOT a faked text
        event) followed by `done`. Pin the event shape — the UI's
        error-branch handler reads `event.error` and renders it
        distinctly from a model-authored text turn. Without the typed
        event, a "the coach kept failing tool calls" outcome would
        look identical to a normal coach reply."""
        responses, _ = patch_complete

        # Queue MAX_TOOL_TURNS rounds of pure tool_use (no text), so
        # the loop never finds a non-tool response and falls through.
        for i in range(chat_module.MAX_TOOL_TURNS):
            responses.append(_resp([_fake_tool_use("get_score", {}, f"tu_{i}")]))

        events = await self._drain(
            chat_module.handle_chat_turn(user_id="user-1", message="loop", conversation_id="c-1")
        )

        # No text events should appear — we queued only tool_use.
        assert not any(ev["type"] == "text" for ev in events)

        # Final two events: typed error + done. Same shape the /chat
        # router uses for budget-exceeded so the UI's existing error
        # handler renders it without changes.
        error_events = [ev for ev in events if ev["type"] == "error"]
        assert len(error_events) == 1
        assert "tool-call limit" in error_events[0]["error"].lower()
        assert error_events[0]["code"] == 502
        assert events[-1] == {"type": "done", "conversation_id": "c-1"}

    async def test_loop_does_not_call_complete_more_than_max_turns(
        self, patch_complete, patch_execute_tool
    ):
        """Hard upper bound on LLM calls per chat turn. Pin so a
        future refactor that changes the loop structure can't
        accidentally let the cap leak."""
        responses, calls = patch_complete

        # Queue more responses than the cap; the loop must stop early.
        for i in range(chat_module.MAX_TOOL_TURNS + 5):
            responses.append(_resp([_fake_tool_use("get_score", {}, f"tu_{i}")]))

        await self._drain(
            chat_module.handle_chat_turn(user_id="user-1", message="loop", conversation_id="c-1")
        )

        # complete() called exactly MAX_TOOL_TURNS times — no more,
        # no fewer. Locks the per-turn LLM cost ceiling.
        assert len(calls) == chat_module.MAX_TOOL_TURNS

    async def test_history_is_loaded_in_chronological_order(self, patch_complete):
        """Messages persist with descending sort by created_at, but
        chat.py reverses to chronological for the LLM. Pin so a
        refactor that drops the reverse() doesn't feed the LLM
        history backwards."""

        _td = timedelta
        now = datetime.now(UTC)
        await Database.get_db()[COACH_CONVERSATIONS_COLLECTION].insert_many(
            [
                {
                    "user_id": "user-1",
                    "conversation_id": "c-1",
                    "role": "user",
                    "content": "FIRST",
                    "created_at": now - _td(minutes=10),
                },
                {
                    "user_id": "user-1",
                    "conversation_id": "c-1",
                    "role": "assistant",
                    "content": "SECOND",
                    "created_at": now - _td(minutes=5),
                },
            ]
        )

        responses, calls = patch_complete
        responses.append(_resp([TextBlock(type="text", text="ok", citations=None)]))

        await self._drain(
            chat_module.handle_chat_turn(user_id="user-1", message="THIRD", conversation_id="c-1")
        )

        # The fake build_coach_messages preserves history order; the
        # call to complete() should see FIRST → SECOND → THIRD.
        sent = calls[0]["messages"]
        contents = [m["content"] for m in sent if isinstance(m.get("content"), str)]
        # Should be [FIRST, SECOND, THIRD] in order.
        assert contents == ["FIRST", "SECOND", "THIRD"]

    async def test_passes_purpose_chat_to_gateway(self, patch_complete):
        """The cost dashboard distinguishes chat from brief/review.
        Pin so a refactor doesn't leak chat spend into the wrong
        bucket."""

        responses, calls = patch_complete
        responses.append(_resp([TextBlock(type="text", text="ok", citations=None)]))

        await self._drain(
            chat_module.handle_chat_turn(user_id="user-99", message="hi", conversation_id="c-1")
        )

        assert calls[0]["purpose"] == "chat"
        assert calls[0]["user_id"] == "user-99"
        assert calls[0]["tools"] is not None  # tools registered every call


class TestRecentDataSummary:
    """_recent_data_summary builds the human-readable context block
    that's prepended to the memory-rewrite LLM prompt. It walks
    7 days of beats and renders Markdown.

    Why test directly: the existing TestRewriteCoachMemory stubs
    this whole helper out, so a regression in the rendering would
    silently degrade the LLM's input quality without any test
    failure. Pin the sessions section plus the empty-state fallback."""

    @pytest.fixture
    def patch_repos(self, monkeypatch):
        """Returns a setter that monkeypatches build_repos to return
        the supplied CoachRepos instance."""

        def setter(repos):
            async def fake_build_repos(_user_id):
                return repos

            monkeypatch.setattr(memory_rewrite_module, "build_repos", fake_build_repos)

        return setter

    async def test_empty_data_renders_no_sessions_line(self, patch_repos):
        """No beats → output still renders the section header with the
        documented empty-state line. Pin so the LLM gets a stable
        structure even on a first-week user."""
        patch_repos(_fake_coach_repos())
        out = await memory_rewrite_module._recent_data_summary("user-1")
        assert "## Last 7 days of sessions" in out
        assert "(No sessions in the last 7 days)" in out

    async def test_recent_beats_render_with_project_name_and_duration(self, patch_repos):
        """A beat in the last 7 days renders as
        `**YYYY-MM-DD** (Xh): ProjectName (45m)`. Pin the
        project name resolution + the fmt_minutes formatting."""
        recent_iso = (
            (datetime.now(UTC) - timedelta(days=2))
            .replace(hour=10, minute=0, second=0, microsecond=0)
            .isoformat()
        )
        recent_iso = recent_iso[:19]  # strip tz suffix for the helper
        beats = [_completed_beat(recent_iso, 45, project_id="p1")]
        repos = _fake_coach_repos(
            projects=[_project("p1", "Alpha")],
            beats=beats,
        )
        patch_repos(repos)
        out = await memory_rewrite_module._recent_data_summary("user-1")
        # Project name must resolve (not "?") and the duration
        # uses fmt_minutes (45m, not "0:45:00")
        assert "Alpha (45m)" in out
        # The empty-state line must NOT appear
        assert "(No sessions in the last 7 days)" not in out

    async def test_old_beats_excluded_from_session_summary(self, patch_repos):
        """A beat from 10 days ago must not appear in the
        last-7-days section. Pin so the rewrite prompt isn't
        polluted with stale activity."""
        old_iso = (
            (datetime.now(UTC) - timedelta(days=10))
            .replace(hour=10, minute=0, second=0, microsecond=0)
            .isoformat()[:19]
        )
        beats = [_completed_beat(old_iso, 60, project_id="p1")]
        repos = _fake_coach_repos(
            projects=[_project("p1", "Alpha")],
            beats=beats,
        )
        patch_repos(repos)
        out = await memory_rewrite_module._recent_data_summary("user-1")
        # The beat IS in beats but should be filtered out by the >= week_ago check
        assert "(No sessions in the last 7 days)" in out
        assert "Alpha" not in out

    async def test_unknown_project_id_renders_as_question_mark(self, patch_repos):
        """Beat references a project_id not in the project map
        (project deleted between session creation and rewrite)
        → renders as "? (45m)" rather than crashing on KeyError.
        Pin so a deleted project doesn't kill the weekly rewrite."""
        recent_iso = (
            (datetime.now(UTC) - timedelta(days=1))
            .replace(hour=10, minute=0, second=0, microsecond=0)
            .isoformat()[:19]
        )
        beats = [_completed_beat(recent_iso, 45, project_id="ghost")]
        repos = _fake_coach_repos(
            projects=[],  # project map is empty
            beats=beats,
        )
        patch_repos(repos)
        out = await memory_rewrite_module._recent_data_summary("user-1")
        assert "? (45m)" in out

    async def test_sessions_are_filed_under_the_users_days(self, patch_repos):
        """22:00 UTC is 07:00 the next morning in Tokyo: the rewrite files
        the session under Tokyo's date, as get_beats and the day context
        do, not the UTC date it read as before (AHM-77)."""
        tokyo = ZoneInfo("Asia/Tokyo")
        start = (datetime.now(UTC) - timedelta(days=2)).replace(
            hour=22, minute=0, second=0, microsecond=0
        )
        beats = [_completed_beat(start.isoformat()[:19], 45, project_id="p1")]
        patch_repos(_fake_coach_repos(projects=[_project("p1", "Alpha")], beats=beats))

        out = await memory_rewrite_module._recent_data_summary("user-1", tokyo)

        local_day = start.astimezone(tokyo).date()
        assert local_day == start.date() + timedelta(days=1)
        assert f"**{local_day.isoformat()}** (0.8h): Alpha (45m)" in out
        assert f"**{start.date().isoformat()}**" not in out

    async def test_the_last_seven_days_are_seven_dates(self, monkeypatch, patch_repos):
        """On Saturday 17 October the seven days are Sunday the 11th to today,
        as the header, the docstring and PRIVACY.md say: a session on the 10th
        is an eighth day, and is left out."""
        instant = datetime(2026, 10, 17, 12, 0, tzinfo=UTC)

        class _At(datetime):
            @classmethod
            def now(cls, tz=None):
                return instant.astimezone(tz) if tz else instant.replace(tzinfo=None)

        monkeypatch.setattr(memory_rewrite_module, "datetime", _At)
        beats = [
            _completed_beat("2026-10-10T10:00:00", 30, project_id="p1"),
            _completed_beat("2026-10-11T10:00:00", 45, project_id="p1"),
        ]
        patch_repos(_fake_coach_repos(projects=[_project("p1", "Alpha")], beats=beats))

        out = await memory_rewrite_module._recent_data_summary("user-1")

        assert "**2026-10-11** (0.8h): Alpha (45m)" in out
        assert "2026-10-10" not in out
