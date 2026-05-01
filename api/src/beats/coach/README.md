# Coach

The AI-driven layer of Beats — streaming chat, daily briefs, end-of-day reviews, productivity-context tools, and per-user memory that compacts weekly. Single entry point for every Anthropic call.

The coach is mounted under `/api/coach/*`; this directory is the implementation underneath. See [`api/CLAUDE.md`](../../../CLAUDE.md) for the broader API conventions.

## Modules

```
coach/
├── prompts.py          COACH_PERSONA + per-purpose prompt templates
├── repos.py            CoachRepos dataclass + collection-name constants + fmt_minutes
├── gateway.py          THE single entry point for client.messages.* — caching,
│                        cost math, retries, budget gate
├── usage.py            UsageTracker — records every LLM call, enforces the
│                        monthly cap (raises BudgetExceeded)
├── memory.py           MemoryStore — per-user Markdown coach memory (versioned)
├── memory_rewrite.py   Weekly compaction: 7-day data → new memory doc via LLM
├── context.py          build_system_block / build_user_context /
│                        build_day_context / build_coach_messages
├── brief.py            generate_brief / get_brief / list_briefs
├── review.py           generate_review_questions / save_answer / get_review /
│                        list_reviews
├── chat.py             handle_chat_turn — the streaming tool-use loop
├── tools.py            TOOL_SCHEMAS + per-tool dispatch handlers + execute_tool
└── README.md           ← you are here
```

## Streaming protocol (UI-facing)

`POST /api/coach/chat` returns Server-Sent Events. Each event is a JSON line, prefixed `data: `, terminated by `data: [DONE]\n\n`.

```
data: {"type": "text", "text": "let me check…"}
data: {"type": "tool_use", "name": "get_score", "input": {}}
data: {"type": "tool_result", "name": "get_score", "result": "Score: 67/100\n…"}
data: {"type": "text", "text": "your score is 67…"}
data: {"type": "done", "conversation_id": "c-abc123"}
data: [DONE]
```

Two failure shapes (matched by the `useCoachChat` hook in the UI):

```
data: {"type": "error", "error": "<message>", "code": <int>}
data: {"type": "done", "conversation_id": "c-abc123"}
```

| Code | When | Source |
|------|------|--------|
| 429 | User over monthly LLM budget | `BudgetExceeded` raised inside the stream |
| 502 | Tool-loop exhausted (MAX_TOOL_TURNS rounds without text) | `chat.py` cap |
| 502 | Generic LLM/network failure inside the stream | catch-all |

The router-level (non-streaming) endpoints use the same shapes via the unified `{detail, code, fields?}` envelope. `BUDGET_EXCEEDED` appears as a string code there; in the streaming path it's the int 429 on the SSE event.

### Tool-use loop

`chat.py:handle_chat_turn` is bounded by `MAX_TOOL_TURNS = 8`. Each round is a full LLM call; legitimate research-style turns chain 4-5 tools (e.g. `get_projects` → `get_beats` → `get_intentions` → `get_patterns` → text), and the cap leaves headroom for a clarifying follow-up before bailing out.

`TOOL_RESULT_DISPLAY_LIMIT = 500` truncates the SSE event for the UI's tool-result chip but the LLM sees the full output in the next round's messages — a long `search_beats` result over a multi-month workspace shows the user a snippet but feeds the model the complete context.

`MAX_HISTORY_TURNS = 20` caps how many prior messages we load into context per chat turn. Older turns are persisted in `coach_conversations` but not re-fed to the model; the weekly memory rewrite is the long-term memory mechanism.

## Cache control

The most consequential cost lever in this layer.

The **system prompt** (~2k tokens of `COACH_PERSONA`) and the **30-day user-context block** (~3-5k tokens of recent activity + memory) are large and stable across many turns; the **today/day-context block** is small and changes daily; per-turn user messages are small and unique.

`gateway._apply_cache_control` injects `cache_control: {"type": "ephemeral"}` markers per the `CacheSpec`:

```python
CacheSpec(
    system_cached=True,           # system prompt → 1 marker
    cached_turn_indices=[0],      # message[0] (the user-context block) → 1 marker
)
```

`build_coach_messages` produces this default. Anthropic's API uses each marker as a cache read pointer; the rates are:

| Token type | $/M tokens |
|------------|-----------|
| Input (uncached) | $3.00 |
| Output | $15.00 |
| Cache write | $3.75 (one-time per cache block) |
| Cache read | $0.30 (every subsequent hit) |

A typical chat turn after the cache warms up: ~5K input total, of which ~4K cache-read at $0.30/M and ~1K fresh input at $3.00/M. **Cache disabled** would mean billing all 5K at the full $3/M rate — ~3× cost increase, silent (no crash).

The integration is end-to-end-tested: `TestApplyCacheControl` covers the helper directly; `TestGatewayCacheControlIntegration` pins the wiring between the helper, the Anthropic call, and the persisted `llm_usage` row.

## Budget enforcement

Per-user monthly cap (`settings.coach_monthly_budget_usd`, default `$10`).

Flow on every gateway call:

1. `tracker = UsageTracker(user_id)`
2. `await tracker.enforce_budget()` — raises `BudgetExceeded` if `month_spend() >= limit`
3. (only if budget passes) `await client.messages.create(...)`
4. `await tracker.record(model, input_tokens, output_tokens, cache_creation, cache_read, cost_usd, purpose)`

The **enforce-before-spend** order is invariant — `TestGatewayBudgetInvariant` pins this. A regression that swapped the two would silently overspend with no error to surface.

`coach_monthly_budget_usd <= 0` disables enforcement (the documented "no-cap" deploy mode for self-hosts that haven't configured the limit).

`UsageTracker.month_spend()` filters `ts >= month_start`, so the budget resets on the 1st automatically. Per-user filter scopes spending — A's spend never affects B.

## Per-purpose cost buckets

Every `gateway.complete()` / `stream()` call carries a `purpose` tag persisted on the `llm_usage` row:

| `purpose` | Module | Cadence |
|-----------|--------|---------|
| `chat` | `chat.py:handle_chat_turn` | per user message |
| `brief` | `brief.py:generate_brief` | once per day per user |
| `review` | `review.py:generate_review_questions` | once per day per user |
| `memory_rewrite` | `memory_rewrite.py:rewrite_coach_memory` | weekly |

`/api/coach/usage` aggregates by day and by purpose so a single weekly memory-rewrite cost (a few cents per user) doesn't hide inside the chat bucket.

## Tools

The chat coach can call six tools via Anthropic's tool-use API. Each is a small async function over the user's repos:

| Name | Purpose |
|------|---------|
| `get_projects` | Active project list with weekly goals (or full list if `include_archived`) |
| `get_beats` | Sessions in a date range (default last 7 days), optionally filtered by project name |
| `get_productivity_score` | Score 0-100 with consistency / intentions / goals / quality components |
| `get_intentions` | Daily intentions for a date (default today) with done/pending status |
| `get_patterns` | Detected patterns (day patterns, peak hours, stale projects, mood correlation) |
| `search_beats` | Sessions whose notes or tags match a query (case-insensitive) |

A tool exception becomes `"Error: <msg>"` in the `tool_result` SSE event — the LLM gets the error in the next round and can recover gracefully rather than 500'ing the whole stream.

Schemas (`TOOL_SCHEMAS`) are built once at module load and registered on every chat-loop call.

## Persistence

Every collection name is a constant in `repos.py`:

| Constant | Collection | Holds |
|----------|------------|-------|
| `COACH_MEMORY_COLLECTION` | `coach_memory` | Per-user Markdown memory + versioned `history` array |
| `DAILY_BRIEFS_COLLECTION` | `daily_briefs` | One `brief` doc per (user_id, date) |
| `REVIEW_ANSWERS_COLLECTION` | `review_answers` | One `review` doc per (user_id, date) with questions[] + answers[] |
| `COACH_CONVERSATIONS_COLLECTION` | `coach_conversations` | One row per chat turn (role, content, tool_calls, conversation_id, created_at) |
| `LLM_USAGE_COLLECTION` | `llm_usage` | One row per gateway call (model, tokens, cost, purpose, ts) |

`MemoryStore.write` `$push`es the previous content to a `history` array on every write so a bad memory rewrite is recoverable. `daily_briefs` and `review_answers` upsert on (user_id, date) — re-generating overwrites questions but `$setOnInsert` preserves answers across regenerates.

## Test layout

Two test files cover this directory:

- **`src/beats/test_coach.py`** — module-level tests with mocked LLM. Covers fmt_minutes, MemoryStore, UsageTracker (incl. budget invariants), brief, review, the chat tool-use loop with fake gateway responses, the tools dispatch, the context builders, and the gateway integration (cache-control + budget).
- **`src/test_api.py::TestCoachEndpoints` + `TestCoachRouterGapFill`** — HTTP-level tests against the real API client. Covers the auth wall, the `/chat/history` pagination, the `/usage` aggregation shape, the `/review/start` happy + error paths, the `/review/answer` envelope codes, and the `BUDGET_EXCEEDED` 429 envelope across `/brief`, `/review`, and `/memory/rewrite`.

Both files use the same `_FakeCoachRepos` / fake-Anthropic-client pattern. No test ever spends real LLM tokens.

## Configuration

| Setting | Default | Effect |
|---------|---------|--------|
| `settings.coach_model` | `claude-opus-4-5` | The Anthropic model id used for every call |
| `settings.coach_monthly_budget_usd` | `10.0` | Per-user monthly cap; `<= 0` disables enforcement |
| `settings.anthropic_api_key` | (env) | Required; `gateway._get_client` raises if missing |

Constants (in source):

| Module:line | Constant | Value | Why |
|-------------|----------|-------|-----|
| `chat.py:36` | `MAX_HISTORY_TURNS` | 20 | Recent-context window size per chat turn |
| `chat.py:37` | `TOOL_RESULT_DISPLAY_LIMIT` | 500 | UI-side truncation; LLM still sees full text |
| `chat.py:48` | `MAX_TOOL_TURNS` | 8 | Per-turn LLM-call ceiling |
| `gateway.py:29-32` | `SONNET_*_PER_MTOK` | 3.0 / 15.0 / 3.75 / 0.30 | Anthropic's published prices |
| `gateway.py:34` | `MAX_RETRIES` | 3 | Retry on 429/500/502/503/529 |
| `gateway.py:35` | `BASE_DELAY_S` | 1.0 | Exponential backoff base + jitter |

## Conventions

- **No raw Anthropic calls outside `gateway.py`.** Every LLM call goes through `complete()` or `stream()` so caching, cost, retries, and budget enforcement are consistent. Adding a new coach feature means adding a `purpose` tag, not bypassing the gateway.
- **No tool with side effects on user data.** All six tools are read-only over the repos. A tool that mutated state would need to plumb through the API's auth/idempotency middleware, not the coach loop.
- **Markdown out, structured JSON for tool_use only.** Coach text replies are Markdown so the UI can render rich formatting. Tool inputs and outputs use the typed Anthropic tool-use protocol; the schemas in `TOOL_SCHEMAS` are the contract.
- **`purpose` tag on every call.** Distinguishes the cost buckets in the dashboard. New coach surfaces should pick a unique purpose value rather than reusing an existing one.
