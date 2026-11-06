"""The coach's HTTP surface: its endpoints, the chat SSE stream, briefs
and their feedback, and the error paths.

Split out of `test_api.py` at the ceiling in roadmaps/file-sizes.md; the
harness is `conftest.py`'s and the shared fixtures `api_helpers.py`'s.
"""

from datetime import UTC, datetime, timedelta

import pytest

from api_helpers import (
    _day_job,
)


class TestCoachEndpoints:
    """Smoke tests for coach endpoints. Since we can't call the real Anthropic
    API in tests, we only test endpoints that don't require LLM calls (usage,
    brief retrieval, memory read) and verify auth/shape."""

    def test_brief_today_returns_null_when_empty(self, client, auth_headers):
        response = client.get("/api/coach/brief/today", headers=auth_headers)
        assert response.status_code == 200
        # No brief generated yet — should return null
        assert response.json() is None

    def test_brief_history_returns_empty_list(self, client, auth_headers):
        response = client.get("/api/coach/brief/history", headers=auth_headers)
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_memory_returns_empty_content(self, client, auth_headers):
        response = client.get("/api/coach/memory", headers=auth_headers)
        assert response.status_code == 200
        body = response.json()
        assert "content" in body

    def test_usage_returns_shape(self, client, auth_headers):
        response = client.get("/api/coach/usage", headers=auth_headers)
        assert response.status_code == 200
        body = response.json()
        assert "days" in body
        assert "month_total_usd" in body
        assert "budget_usd" in body
        assert isinstance(body["days"], list)
        assert body["budget_usd"] > 0

    def test_coach_endpoints_require_auth(self, client):
        for path in [
            "/api/coach/brief/today",
            "/api/coach/brief/history",
            "/api/coach/memory",
            "/api/coach/usage",
        ]:
            assert client.get(path).status_code == 401, f"{path} should require auth"

    def test_chat_requires_auth(self, client):
        response = client.post("/api/coach/chat", json={"message": "hello"})
        assert response.status_code == 401

    def test_without_an_api_key_the_coach_says_so_and_calls_nothing(self, client, auth_headers):
        """The suite runs with no ANTHROPIC_API_KEY (.env.test), as a
        self-hosted deployment may: /status says the coach is not set up,
        and every route that would call the model answers 503
        COACH_NOT_CONFIGURED before a client is even built — not the 502
        "resting" a real failure gets."""
        from beats.settings import settings

        assert settings.anthropic_api_key == ""
        status = client.get("/api/coach/status", headers=auth_headers)
        assert status.status_code == 200
        assert status.json() == {"configured": False}

        brief = client.post("/api/coach/brief/generate", json={}, headers=auth_headers)
        assert brief.status_code == 503, brief.text
        assert brief.json()["code"] == "COACH_NOT_CONFIGURED"
        rewrite = client.post("/api/coach/memory/rewrite", headers=auth_headers)
        assert rewrite.status_code == 503
        assert rewrite.json()["code"] == "COACH_NOT_CONFIGURED"
        with client.stream(
            "POST", "/api/coach/chat", json={"message": "hello"}, headers=auth_headers
        ) as chat:
            events = [line for line in chat.iter_lines() if line.startswith("data: ")]
        assert any('"code": 503' in line for line in events), events
        assert events[-1] == "data: [DONE]"

    def test_with_an_api_key_the_status_says_configured(self, client, auth_headers, monkeypatch):
        from beats.settings import settings

        monkeypatch.setattr(settings, "anthropic_api_key", "sk-ant-test")
        assert client.get("/api/coach/status", headers=auth_headers).json() == {"configured": True}


class TestCoachRouterGapFill:
    """Coach routes whose logic isn't covered by the smoke suite —
    /chat/history pagination + filtering, /usage with seeded rows,
    and the BUDGET_EXCEEDED 429 envelope. Mocks the LLM-touching
    modules so the tests run deterministically; uses real Mongo via
    testcontainers for the persistence assertions."""

    @pytest.fixture(autouse=True)
    def _reset_coach_collections(self, auth_info):
        """Wipe the coach collections this class writes to so tests
        don't pollute each other's reads."""
        import os

        from pymongo import MongoClient

        dsn = os.environ.get("DB_DSN", "mongodb://localhost:27017")
        db_name = os.environ.get("DB_NAME", "beats_test")
        sync = MongoClient(dsn)
        db = sync[db_name]
        for coll in (
            "coach_conversations",
            "llm_usage",
        ):
            db[coll].delete_many({})
        sync.close()
        return

    def _seed_message(
        self,
        auth_info,
        conversation_id: str,
        role: str,
        content: str,
        seconds_ago: int = 0,
    ) -> None:
        """Insert a row directly into coach_conversations. The router's
        /chat/history sorts by created_at desc, so this lets us seed
        a deterministic timeline."""
        import os
        from datetime import UTC as _UTC
        from datetime import datetime as _dt
        from datetime import timedelta as _td

        from bson import ObjectId
        from pymongo import MongoClient

        dsn = os.environ.get("DB_DSN", "mongodb://localhost:27017")
        db_name = os.environ.get("DB_NAME", "beats_test")
        sync = MongoClient(dsn)
        sync[db_name].coach_conversations.insert_one(
            {
                "_id": ObjectId(),
                "user_id": auth_info["user_id"],
                "conversation_id": conversation_id,
                "role": role,
                "content": content,
                "created_at": _dt.now(_UTC) - _td(seconds=seconds_ago),
            }
        )
        sync.close()

    def _seed_usage(
        self,
        auth_info,
        cost_usd: float,
        *,
        purpose: str = "chat",
        days_ago: int = 0,
    ) -> None:
        import os
        from datetime import UTC as _UTC
        from datetime import datetime as _dt

        from bson import ObjectId
        from pymongo import MongoClient

        dsn = os.environ.get("DB_DSN", "mongodb://localhost:27017")
        db_name = os.environ.get("DB_NAME", "beats_test")
        sync = MongoClient(dsn)
        sync[db_name].llm_usage.insert_one(
            {
                "_id": ObjectId(),
                "user_id": auth_info["user_id"],
                "model": "claude-opus-4-7",
                "input_tokens": 1000,
                "output_tokens": 500,
                "cache_creation_input_tokens": 0,
                "cache_read_input_tokens": 0,
                "cost_usd": cost_usd,
                "purpose": purpose,
                "ts": _dt.now(_UTC) - timedelta(days=days_ago),
            }
        )
        sync.close()

    # ── /chat/history ────────────────────────────────────────────────

    def test_chat_history_empty_returns_empty_list(self, client, auth_info):
        resp = client.get("/api/coach/chat/history", headers=auth_info["headers"])
        assert resp.status_code == 200
        assert resp.json() == []

    def test_chat_history_returns_chronological_order(self, client, auth_info):
        """Router fetches descending then reverses → chronological for
        the UI. Pin so a refactor that drops the .reverse() doesn't
        feed the chat UI history backwards."""
        # Newest first by creation time, but the router reverses to
        # oldest-first for the UI. Seed in non-chronological insert
        # order to verify the sort.
        self._seed_message(auth_info, "c-1", "user", "FIRST", seconds_ago=300)
        self._seed_message(auth_info, "c-1", "assistant", "SECOND", seconds_ago=200)
        self._seed_message(auth_info, "c-1", "user", "THIRD", seconds_ago=100)

        resp = client.get("/api/coach/chat/history", headers=auth_info["headers"])
        assert resp.status_code == 200
        contents = [m["content"] for m in resp.json()]
        # Oldest first.
        assert contents == ["FIRST", "SECOND", "THIRD"]

    def test_chat_history_filters_by_conversation_id(self, client, auth_info):
        self._seed_message(auth_info, "c-1", "user", "in c1")
        self._seed_message(auth_info, "c-2", "user", "in c2")

        resp = client.get(
            "/api/coach/chat/history?conversation_id=c-1",
            headers=auth_info["headers"],
        )
        assert resp.status_code == 200
        contents = [m["content"] for m in resp.json()]
        assert contents == ["in c1"]

    def test_chat_history_respects_limit(self, client, auth_info):
        for i in range(5):
            self._seed_message(auth_info, "c-1", "user", f"msg {i}", seconds_ago=100 - i)

        resp = client.get("/api/coach/chat/history?limit=3", headers=auth_info["headers"])
        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 3

    def test_chat_history_validates_limit_bounds(self, client, auth_info):
        # Router declares Query(default=50, ge=1, le=200).
        for q in ("?limit=0", "?limit=201"):
            resp = client.get(f"/api/coach/chat/history{q}", headers=auth_info["headers"])
            assert resp.status_code == 422

    # ── /usage ───────────────────────────────────────────────────────

    def test_usage_aggregates_seeded_rows_by_day(self, client, auth_info):
        """The /usage endpoint groups llm_usage rows by day and sums.
        Pin: today's rows roll up; the response shape carries the
        budget alongside the daily breakdown."""
        self._seed_usage(auth_info, 0.10, purpose="chat")
        self._seed_usage(auth_info, 0.20, purpose="brief")
        # Yesterday — separate bucket.
        self._seed_usage(auth_info, 0.05, purpose="chat", days_ago=1)

        resp = client.get("/api/coach/usage", headers=auth_info["headers"])
        assert resp.status_code == 200
        body = resp.json()
        assert "days" in body
        assert "month_total_usd" in body
        assert "budget_usd" in body
        # Today's total = 0.30, yesterday = 0.05.
        days = {d["date"]: d for d in body["days"]}
        assert len(days) == 2
        # Both days have non-zero cost.
        for d in body["days"]:
            assert d["cost_usd"] > 0
            assert d["calls"] >= 1

    def test_usage_validates_days_param(self, client, auth_info):
        # ge=1, le=90.
        for q in ("?days=0", "?days=91"):
            resp = client.get(f"/api/coach/usage{q}", headers=auth_info["headers"])
            assert resp.status_code == 422

    def test_brief_reads_the_day_jobs_balance_with_its_adjustments(
        self, client, auth_info, monkeypatch
    ):
        """A brief builds the coach's repositories against real Mongo, and its
        day context quotes the running balance the week route reads, a payout
        included. Once ContractService needed its adjustment store, a coach
        that did not pass one failed every brief with a 502."""
        from types import SimpleNamespace

        from anthropic.types import TextBlock

        from beats.coach import brief as brief_module
        from beats.coach.contract_section import describe_balance

        headers = auth_info["headers"]
        project = _day_job(client, headers, opening_balance_hours=10)
        last_monday = datetime.now(UTC).date() - timedelta(days=datetime.now(UTC).weekday() + 7)
        resp = client.post(
            f"/api/projects/{project['id']}/adjustments",
            params={"tz": "UTC"},
            json={"date": last_monday.isoformat(), "kind": "delta", "hours": -4},
            headers=headers,
        )
        assert resp.status_code == 201, resp.text

        sent: list[dict] = []

        async def fake_complete(**kwargs):
            sent.extend(kwargs["messages"])
            return SimpleNamespace(
                content=[TextBlock(type="text", text="Morning.")],
                model="fake",
                cost_usd=0.0,
                input_tokens=0,
                output_tokens=0,
                cache_read_input_tokens=0,
            )

        monkeypatch.setattr(brief_module, "complete", fake_complete)

        resp = client.post("/api/coach/brief/generate", params={"tz": "UTC"}, headers=headers)
        assert resp.status_code == 200, resp.text

        week = client.get(
            f"/api/projects/{project['id']}/contract/week", params={"tz": "UTC"}, headers=headers
        ).json()
        assert week["balance_adjusted"] == -4
        prompt = "\n".join(m["content"] for m in sent if isinstance(m["content"], str))
        line = f"{project['name']} running balance: {describe_balance(week['balance'])}"
        assert line in prompt

    @staticmethod
    def _zone_off_utcs_day() -> str:
        """A timezone whose calendar day is not UTC's right now: UTC+14 is
        a day ahead from 10:00 UTC, UTC−11 a day behind until 11:00 UTC."""
        from zoneinfo import ZoneInfo

        utc_today = datetime.now(UTC).date()
        for name in ("Pacific/Kiritimati", "Pacific/Pago_Pago"):
            if datetime.now(ZoneInfo(name)).date() != utc_today:
                return name
        raise AssertionError("no zone off UTC's day")  # pragma: no cover

    def _assert_day_context_in(self, client, headers, project, sent, tz) -> None:
        from zoneinfo import ZoneInfo

        from beats.coach.contract_section import describe_balance

        prompt = "\n".join(m["content"] for m in sent if isinstance(m["content"], str))
        today = datetime.now(ZoneInfo(tz)).date()
        assert f"## Today: {today.isoformat()}" in prompt
        week = client.get(
            f"/api/projects/{project['id']}/contract/week", params={"tz": tz}, headers=headers
        ).json()
        line = f"{project['name']} running balance: {describe_balance(week['balance'])}"
        assert line in prompt

    def test_chat_reads_the_contract_week_in_the_request_timezone(
        self, client, auth_info, monkeypatch
    ):
        """The chat's day context is the user's day, not UTC's: before the
        route took a tz, a Monday morning in Auckland sent last week's days
        off and contracts that had ended before the user's week, and the
        balance missed an adjustment dated the user's today."""
        from types import SimpleNamespace

        from anthropic.types import TextBlock

        from beats.coach import chat as chat_module

        headers = auth_info["headers"]
        project = _day_job(client, headers, opening_balance_hours=10)
        sent: list[dict] = []

        async def fake_complete(**kwargs):
            sent.extend(kwargs["messages"])
            return SimpleNamespace(content=[TextBlock(type="text", text="Hi.")])

        monkeypatch.setattr(chat_module, "complete", fake_complete)

        tz = self._zone_off_utcs_day()
        with client.stream(
            "POST", "/api/coach/chat", params={"tz": tz}, json={"message": "hi"}, headers=headers
        ) as resp:
            assert resp.status_code == 200
            "".join(resp.iter_text())

        self._assert_day_context_in(client, headers, project, sent, tz)

    def test_memory_rewrite_reads_the_contract_week_in_the_request_timezone(
        self, client, auth_info, monkeypatch
    ):
        """The memory rewrite's day context is the user's day, as the chat's
        and the brief's are."""
        from types import SimpleNamespace

        from anthropic.types import TextBlock

        from beats.coach import memory_rewrite as memory_rewrite_module

        headers = auth_info["headers"]
        project = _day_job(client, headers, opening_balance_hours=10)
        sent: list[dict] = []

        async def fake_complete(**kwargs):
            sent.extend(kwargs["messages"])
            return SimpleNamespace(content=[TextBlock(type="text", text="# Coach memory")])

        monkeypatch.setattr(memory_rewrite_module, "complete", fake_complete)

        tz = self._zone_off_utcs_day()
        resp = client.post("/api/coach/memory/rewrite", params={"tz": tz}, headers=headers)
        assert resp.status_code == 200, resp.text

        self._assert_day_context_in(client, headers, project, sent, tz)

    def test_memory_rewrite_budget_exceeded_uses_envelope_code(
        self, client, auth_info, monkeypatch
    ):
        """Pin parity with /brief and /review: a BudgetExceeded on
        memory rewrite must surface as 429 + code=BUDGET_EXCEEDED,
        not the generic RATE_LIMITED. Without this, a client that
        branches on the code field would render "rate limited" for
        memory but "budget reached" for brief — confusing UX. Locks
        the parity fix from the T4 audit."""
        from beats.api.routers import coach as coach_router
        from beats.coach.usage import BudgetExceeded

        async def fake_rewrite(_user_id, **_kwargs):
            raise BudgetExceeded(spent=20.0, limit=10.0)

        monkeypatch.setattr(coach_router, "rewrite_coach_memory", fake_rewrite)

        resp = client.post("/api/coach/memory/rewrite", headers=auth_info["headers"])
        assert resp.status_code == 429
        body = resp.json()
        assert body["code"] == "BUDGET_EXCEEDED"


class TestCoachDeleteAndChatSse:
    """Three paths uncovered by other coach tests:

    1. DELETE /api/coach/memory — destructive (drops the per-user
       coach personality)
    2. DELETE /api/coach/data — IRREVERSIBLE bulk delete across
       four collections (memory + briefs + conversations + usage)
    3. /api/coach/chat SSE — the streaming endpoint's three
       branches: happy-path event emission, BudgetExceeded → SSE
       error event with code=429, generic Exception → 502 event

    Both DELETE endpoints MUST be tested — they wipe user data
    and a regression in the user-scoping query would let one user
    nuke another's data."""

    def _db(self):
        import os

        from pymongo import MongoClient

        dsn = os.environ.get("DB_DSN", "mongodb://localhost:27017")
        db_name = os.environ.get("DB_NAME", "beats_test")
        sync = MongoClient(dsn)
        return sync, sync[db_name]

    @pytest.fixture(autouse=True)
    def _reset_coach_collections(self, auth_info):
        sync, db = self._db()
        for coll in (
            "coach_memory",
            "daily_briefs",
            "coach_conversations",
            "llm_usage",
        ):
            db[coll].delete_many({})
        sync.close()
        return

    def _seed_all_coach_data(self, user_id: str):
        """Insert one row in each of the four coach collections
        for the given user. Used by the DELETE /data test to
        verify all four are wiped in one shot."""
        from datetime import UTC, datetime

        sync, db = self._db()
        db.coach_memory.insert_one(
            {"user_id": user_id, "content": "be kind", "updated_at": datetime.now(UTC)}
        )
        db.daily_briefs.insert_one(
            {
                "user_id": user_id,
                "date": "2026-04-01",
                "brief": "morning",
                "created_at": datetime.now(UTC),
            }
        )
        db.coach_conversations.insert_one(
            {
                "user_id": user_id,
                "conversation_id": "c-1",
                "role": "user",
                "content": "hi",
                "created_at": datetime.now(UTC),
            }
        )
        db.llm_usage.insert_one(
            {
                "user_id": user_id,
                "ts": datetime.now(UTC),
                "model": "claude-opus-4-7",
                "input_tokens": 100,
                "output_tokens": 50,
                "cost_usd": 0.01,
                "purpose": "chat",
            }
        )
        sync.close()

    def _count_user_data(self, user_id: str) -> dict[str, int]:
        sync, db = self._db()
        out = {
            coll: db[coll].count_documents({"user_id": user_id})
            for coll in (
                "coach_memory",
                "daily_briefs",
                "coach_conversations",
                "llm_usage",
            )
        }
        sync.close()
        return out

    # ---------------- DELETE /api/coach/memory ----------------

    def test_delete_memory_wipes_only_this_users_memory(self, client, auth_info):
        """DELETE /memory drops the requesting user's coach memory
        but leaves OTHER users' memory intact. Pin the user-scoping
        — a regression here would let User A wipe User B's memory."""
        sync, db = self._db()
        # Seed the requesting user's memory + another user's memory
        db.coach_memory.insert_one({"user_id": auth_info["user_id"], "content": "mine"})
        db.coach_memory.insert_one({"user_id": "other-user", "content": "theirs"})
        sync.close()

        resp = client.delete("/api/coach/memory", headers=auth_info["headers"])
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

        sync, db = self._db()
        # Mine: gone. Theirs: intact.
        assert db.coach_memory.count_documents({"user_id": auth_info["user_id"]}) == 0
        assert db.coach_memory.count_documents({"user_id": "other-user"}) == 1
        sync.close()

    # ---------------- DELETE /api/coach/data ----------------

    def test_delete_data_wipes_all_coach_collections_for_user(self, client, auth_info):
        """DELETE /data is the "factory reset" — it MUST wipe all
        four coach collections (memory + briefs + conversations +
        usage) for the requesting user. Pin all four so a refactor
        that skips one (e.g. forgets the new usage logs) is caught."""
        self._seed_all_coach_data(auth_info["user_id"])

        # Sanity: all four non-zero before the delete
        before = self._count_user_data(auth_info["user_id"])
        assert all(c == 1 for c in before.values()), before

        resp = client.delete("/api/coach/data", headers=auth_info["headers"])
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert "all coach data" in body["deleted"]

        # All four collections empty for this user
        after = self._count_user_data(auth_info["user_id"])
        assert all(c == 0 for c in after.values()), after

    def test_delete_data_does_not_touch_other_users(self, client, auth_info):
        """Cross-user safety — DELETE /data scopes to user_id.
        Pin so a regression doesn't accidentally do an unscoped
        delete_many({}) and nuke every user's data on the deploy."""
        # Seed BOTH the requesting user AND a separate user.
        self._seed_all_coach_data(auth_info["user_id"])
        self._seed_all_coach_data("other-user")

        resp = client.delete("/api/coach/data", headers=auth_info["headers"])
        assert resp.status_code == 200

        # The other user's five rows are intact
        other_after = self._count_user_data("other-user")
        assert all(c == 1 for c in other_after.values()), other_after

    def test_delete_endpoints_require_auth(self, client):
        """Both destructive endpoints must reject unauthenticated
        requests. Pin the auth gate — an unauthenticated DELETE
        on these would be a catastrophic data-wipe primitive."""
        assert client.delete("/api/coach/memory").status_code == 401
        assert client.delete("/api/coach/data").status_code == 401

    # ---------------- /api/coach/chat SSE ----------------

    def test_chat_sse_streams_events(self, client, auth_headers, monkeypatch):
        """Happy path: handle_chat_turn yields events; the SSE
        generator wraps each in `data: <json>\\n\\n` and ends
        with `data: [DONE]\\n\\n`. Pin the framing — the UI's
        SSE parser depends on the exact form."""
        from beats.api.routers import coach as coach_router

        async def fake_handle_chat_turn(**_kwargs):
            yield {"type": "text", "text": "hello"}
            yield {"type": "done", "conversation_id": "c-abc"}

        monkeypatch.setattr(coach_router, "handle_chat_turn", fake_handle_chat_turn)

        with client.stream(
            "POST",
            "/api/coach/chat",
            json={"message": "hi"},
            headers=auth_headers,
        ) as resp:
            assert resp.status_code == 200
            assert resp.headers["content-type"].startswith("text/event-stream")
            body = "".join(resp.iter_text())

        # Every event is on its own `data:` line, terminator is [DONE]
        assert 'data: {"type": "text", "text": "hello"}' in body
        assert '"conversation_id": "c-abc"' in body
        assert body.rstrip().endswith("data: [DONE]")

    def test_chat_sse_emits_budget_exceeded_envelope(self, client, auth_headers, monkeypatch):
        """When BudgetExceeded fires inside the stream, the SSE
        generator yields a typed error event with code=429. Pin
        so the UI's "monthly budget reached" toast triggers from
        the right code."""
        from beats.api.routers import coach as coach_router
        from beats.coach.usage import BudgetExceeded

        async def fake_handle_chat_turn(**_kwargs):
            yield {"type": "text", "text": "starting…"}
            raise BudgetExceeded(spent=12.50, limit=10.00)

        monkeypatch.setattr(coach_router, "handle_chat_turn", fake_handle_chat_turn)

        with client.stream(
            "POST",
            "/api/coach/chat",
            json={"message": "hi"},
            headers=auth_headers,
        ) as resp:
            assert resp.status_code == 200
            body = "".join(resp.iter_text())

        # First event surfaces; then the 429 error event; then [DONE]
        assert '"type": "text"' in body
        assert '"type": "error"' in body
        assert '"code": 429' in body
        # The message names the spend and the limit, built from the figures
        assert "$12.50" in body
        assert "$10.00" in body
        assert body.rstrip().endswith("data: [DONE]")

    def test_chat_sse_emits_generic_502_envelope_on_unexpected_failure(
        self, client, auth_headers, monkeypatch
    ):
        """Any other exception inside the stream → a generic 502
        error event ("Coach is temporarily unavailable.") rather
        than letting the connection just close. Pin so the UI sees
        a structured error rather than an SSE truncation."""
        from beats.api.routers import coach as coach_router

        async def fake_handle_chat_turn(**_kwargs):
            yield {"type": "text", "text": "starting…"}
            raise RuntimeError("anthropic exploded")

        monkeypatch.setattr(coach_router, "handle_chat_turn", fake_handle_chat_turn)

        with client.stream(
            "POST",
            "/api/coach/chat",
            json={"message": "hi"},
            headers=auth_headers,
        ) as resp:
            assert resp.status_code == 200
            body = "".join(resp.iter_text())

        assert '"type": "error"' in body
        assert '"code": 502' in body
        assert "temporarily unavailable" in body
        # Internal error message must NOT leak to the user
        assert "anthropic exploded" not in body
        assert body.rstrip().endswith("data: [DONE]")


class TestBriefFeedback:
    """PUT /api/coach/brief/{date}/feedback: a rating on one brief, which the
    brief response carries and a null clears."""

    def _db(self):
        import os

        from pymongo import MongoClient

        dsn = os.environ.get("DB_DSN", "mongodb://localhost:27017")
        sync = MongoClient(dsn)
        return sync, sync[os.environ.get("DB_NAME", "beats_test")]

    @pytest.fixture(autouse=True)
    def _brief(self, auth_info):
        from datetime import UTC, datetime

        sync, db = self._db()
        db.daily_briefs.delete_many({})
        db.daily_briefs.insert_one(
            {
                "user_id": auth_info["user_id"],
                "date": "2026-10-14",
                "body": "Protect the morning.",
                "created_at": datetime.now(UTC),
            }
        )
        sync.close()

    def test_rating_is_stored_and_returned_and_null_clears_it(self, client, auth_info):
        url = "/api/coach/brief/2026-10-14/feedback"
        resp = client.put(url, json={"rating": "helpful"}, headers=auth_info["headers"])
        assert resp.status_code == 200
        assert resp.json()["feedback"] == "helpful"

        resp = client.put(url, json={"rating": "not_useful"}, headers=auth_info["headers"])
        assert resp.json()["feedback"] == "not_useful"

        resp = client.put(url, json={"rating": None}, headers=auth_info["headers"])
        assert resp.status_code == 200
        assert resp.json()["feedback"] is None

    def test_a_day_without_a_brief_is_404(self, client, auth_info):
        resp = client.put(
            "/api/coach/brief/2026-10-13/feedback",
            json={"rating": "helpful"},
            headers=auth_info["headers"],
        )
        assert resp.status_code == 404
        assert resp.json()["code"] == "BRIEF_NOT_FOUND"

    def test_a_bad_date_is_400_and_an_unknown_rating_422(self, client, auth_info):
        h = auth_info["headers"]
        bad_date = client.put(
            "/api/coach/brief/yesterday/feedback", json={"rating": "helpful"}, headers=h
        )
        assert bad_date.status_code == 400
        assert bad_date.json()["code"] == "INVALID_DATE"
        bad_rating = client.put(
            "/api/coach/brief/2026-10-14/feedback", json={"rating": "meh"}, headers=h
        )
        assert bad_rating.status_code == 422

    def test_a_paired_device_may_rate(self, client, auth_info):
        code = client.post("/api/device/pair/code", headers=auth_info["headers"]).json()["code"]
        token = client.post("/api/device/pair/exchange", json={"code": code}).json()["device_token"]
        resp = client.put(
            "/api/coach/brief/2026-10-14/feedback",
            json={"rating": "helpful"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200


class TestCoachBriefErrorPaths:
    """Three coach endpoints with uncovered error envelopes:
    /brief/generate (BudgetExceeded → 429, generic → 502),
    /memory/rewrite (generic → 502, BudgetExceeded already
    pinned by TestCoachRouterGapFill), and /brief/today happy
    path (when a brief doc exists). Pin the user-facing envelopes
    — the same shape contract the chat SSE branch follows."""

    def _db(self):
        import os

        from pymongo import MongoClient

        dsn = os.environ.get("DB_DSN", "mongodb://localhost:27017")
        db_name = os.environ.get("DB_NAME", "beats_test")
        sync = MongoClient(dsn)
        return sync, sync[db_name]

    @pytest.fixture(autouse=True)
    def _reset_briefs(self, auth_info):
        sync, db = self._db()
        db.daily_briefs.delete_many({})
        db.coach_memory.delete_many({})
        sync.close()
        return

    def test_brief_today_returns_doc_when_exists(self, client, auth_info):
        """GET /brief/today with a seeded brief → BriefResponse
        envelope. Pin so the dashboard can render the brief
        without a separate "no brief yet" empty state when one
        exists."""
        from datetime import UTC, datetime

        sync, db = self._db()
        # The endpoint queries today's brief by UTC date; seed on the same
        # frame so the test is deterministic on non-UTC machines (local
        # date.today() can differ from UTC today near midnight).
        today_iso = datetime.now(UTC).date().isoformat()
        db.daily_briefs.insert_one(
            {
                "user_id": auth_info["user_id"],
                "date": today_iso,
                "body": "You logged 2 hours on Alpha already.",
                "created_at": datetime.now(UTC),
            }
        )
        sync.close()

        resp = client.get("/api/coach/brief/today", headers=auth_info["headers"])
        assert resp.status_code == 200
        body = resp.json()
        # BriefResponse pins date + body — pin the body field which
        # the dashboard binds to. The exact `date` value is the
        # ISO string we seeded.
        assert body["date"] == today_iso
        assert body["body"] == "You logged 2 hours on Alpha already."

    def test_brief_today_honors_tz_query_param(self, client, auth_info):
        """/brief/today resolves 'today' in the requested timezone. Seeding
        the brief under the Tokyo-local date and fetching with tz=Asia/Tokyo
        returns it — proving the generate and fetch sides agree on the
        local-day storage key (the whole point of threading tz through)."""
        from datetime import UTC, datetime
        from zoneinfo import ZoneInfo

        sync, db = self._db()
        tokyo_today = datetime.now(ZoneInfo("Asia/Tokyo")).date().isoformat()
        db.daily_briefs.insert_one(
            {
                "user_id": auth_info["user_id"],
                "date": tokyo_today,
                "body": "Tokyo brief.",
                "created_at": datetime.now(UTC),
            }
        )
        sync.close()

        resp = client.get("/api/coach/brief/today?tz=Asia/Tokyo", headers=auth_info["headers"])
        assert resp.status_code == 200
        body = resp.json()
        assert body["date"] == tokyo_today
        assert body["body"] == "Tokyo brief."

    def test_brief_today_rejects_invalid_tz(self, client, auth_info):
        """An unknown IANA timezone name is rejected with the unified 400
        envelope (code INVALID_TIMEZONE), same as the analytics endpoints."""
        resp = client.get("/api/coach/brief/today?tz=Not/AZone", headers=auth_info["headers"])
        assert resp.status_code == 400
        body = resp.json()
        assert body["code"] == "INVALID_TIMEZONE"
        assert isinstance(body["detail"], str)

    def test_brief_generate_budget_exceeded_returns_429_envelope(
        self, client, monkeypatch, auth_info
    ):
        """POST /brief/generate when BudgetExceeded fires inside
        generate_brief → 429 with BUDGET_EXCEEDED code (NOT the
        generic RATE_LIMITED). Pin so the UI's "monthly LLM
        budget reached" toast triggers from the right code."""
        from beats.api.routers import coach as coach_router
        from beats.coach.usage import BudgetExceeded

        async def fake_generate_brief(*args, **kwargs):
            raise BudgetExceeded(spent=12.50, limit=10.00)

        monkeypatch.setattr(coach_router, "generate_brief", fake_generate_brief)

        resp = client.post("/api/coach/brief/generate", headers=auth_info["headers"])
        assert resp.status_code == 429
        body = resp.json()
        # Envelope: top-level `code` + `detail` (the unified
        # error envelope flattens nested HTTPException details
        # into the detail string)
        assert body["code"] == "BUDGET_EXCEEDED"
        assert "$12.50" in str(body)
        assert "$10.00" in str(body)

    def test_brief_generate_generic_failure_returns_502_envelope(
        self, client, monkeypatch, auth_info
    ):
        """Any other exception inside generate_brief → 502 with a
        SANITIZED message. Pin so the actual exception text
        ("anthropic exploded") doesn't leak to the user — only
        the canned "the coach is resting" string surfaces."""
        from beats.api.routers import coach as coach_router

        async def fake_generate_brief(*args, **kwargs):
            raise RuntimeError("anthropic exploded")

        monkeypatch.setattr(coach_router, "generate_brief", fake_generate_brief)

        resp = client.post("/api/coach/brief/generate", headers=auth_info["headers"])
        assert resp.status_code == 502
        text = resp.text
        assert "coach is resting" in text
        # Internal exception message MUST NOT leak
        assert "anthropic exploded" not in text

    def test_brief_generate_invalid_date_returns_400_envelope(self, client, auth_info):
        """POST /brief/generate with a malformed date string → 400
        with INVALID_DATE code. Pin so a typo doesn't 500 the
        endpoint."""
        resp = client.post(
            "/api/coach/brief/generate",
            json={"date": "not-a-date"},
            headers=auth_info["headers"],
        )
        assert resp.status_code == 400
        body = resp.json()
        assert body["code"] == "INVALID_DATE"

    def test_memory_rewrite_generic_failure_returns_502(self, client, monkeypatch, auth_info):
        """Generic exception inside rewrite_coach_memory → 502.
        Pin so the rewrite endpoint doesn't expose internal error
        text. BudgetExceeded → 429 path is already covered by
        TestCoachRouterGapFill.test_memory_rewrite_budget_exceeded."""
        from beats.api.routers import coach as coach_router

        async def fake_rewrite(*args, **kwargs):
            raise RuntimeError("memory rewrite blew up internally")

        monkeypatch.setattr(coach_router, "rewrite_coach_memory", fake_rewrite)

        resp = client.post("/api/coach/memory/rewrite", headers=auth_info["headers"])
        assert resp.status_code == 502
        text = resp.text
        # Sanitized message; internal text not leaked
        assert "memory rewrite blew up" not in text
