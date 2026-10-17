# Coach

The AI-driven layer of Beats — streaming chat, daily briefs, productivity-context tools, and per-user memory that compacts weekly. Single entry point for every Anthropic call.

The coach is mounted under `/api/coach/*`; this directory is the implementation underneath. See [`api/CLAUDE.md`](../../../CLAUDE.md) for the broader API conventions.

## Modules

```
coach/
├── prompts.py          COACH_PERSONA + per-purpose prompt templates
├── repos.py            CoachRepos dataclass + collection-name constants + fmt_minutes
│                        (`contracts` is a ContractService, behind CoachContractReader)
├── gateway.py          THE single entry point for client.messages.* — caching,
│                        cost math, retries, budget gate
├── usage.py            UsageTracker — records every LLM call, enforces the
│                        monthly cap (raises BudgetExceeded)
├── memory.py           MemoryStore — per-user Markdown coach memory (versioned)
├── memory_rewrite.py   Weekly compaction: 7-day data → new memory doc via LLM
├── context.py          build_system_block / build_user_context /
│                        build_day_context / build_coach_messages
├── contract_section.py The day context's day-job lines: the week after holidays
│                        and days off, the balance, its by-Sunday projection, and
│                        describe_balance (the SPA's describeBalance, in Python)
├── brief.py            generate_brief / get_brief / list_briefs
├── chat.py             handle_chat_turn — the streaming tool-use loop
├── tools.py            TOOL_SCHEMAS + per-tool dispatch handlers + execute_tool
└── README.md           ← you are here
```

## The day job's week

`build_day_context` carries a "Day-job contracts" section for each day job with a contract: what this week expects after holidays and days off, the hours worked and what is left, the days that made the week shorter, today's expected hours, the running balance, and where it would stand by Sunday (or, in the contract's first seven days, that it is the first week under the contract). The figures come from `ContractService.current_weeks`, the project page's own read, and `contract_section.py` words them.

- **Today only, by the service's clock.** `current_weeks` answers nothing unless the day asked for is today in the request timezone by `ContractService`'s clock, so a backdated brief carries no section, and a test that fixes that clock fixes both the gate and the figures.
- **The request's timezone, on every path.** The brief, the chat and the memory rewrite each take the request's `tz` and pass it to `build_coach_messages`; without it the day context is UTC's, and the week, the days off and the balance's as-of date are another day's than the project page's. Every other day and week the coach reads is that timezone's too: in the cached user context the goal line's week (so it and the week's label name one term between UTC's Monday and the user's), the weekly totals and the productivity score; in the tools `get_projects`' week, the dates `get_beats` takes and prints, and the score and the patterns; and the memory rewrite's last seven days of sessions, each under the local date it started on.
- **Uncached.** The section is in the day context, never in `build_user_context`: the figures move with every session and are the request timezone's, and putting them in message 0 would break the prompt cache on every turn.
- **Labelled as the goal line is.** The week's line names the term in force on its Monday, as `goal_term` does, so a mid-week term change does not put a second percentage beside the goal line's. On a week the contract starts inside it names the term of the contract's first day instead, where the goal line, which reads Monday only, does not yet carry the contract. Both print the percentage with `fmt_percent` (`repos.py`), the twin of the SPA's `toPercent`: to the hundredth, as the page shows it, so 87.5% is never "88%". A change to either is made in both.
- **Projection, not the bare balance.** The balance counts today's hours but charges today's expected hours only tomorrow, so it reads high all day. `_by_sunday` is the twin of `projection()` in the SPA's `standing.ts`, and `COACH_PERSONA` tells the coach to plan from "to go" and "by Sunday". In the contract's first seven days the page shows "First week under the contract." and no projection, and so does the section (`_is_first_week`, the twin of `isFirstWeek`). A change to any twin is made in both.
- **What leaves Beats** is what `PRIVACY.md` lists. A public holiday goes by its name (which can name the region: "Augsburg Peace Festival"), a company holiday only as "company holiday", and a day off only as "day off" or "half day off". The end date is sent when it falls in this week. The running balance is sent, and with it the opening balance and the balance adjustments it sums, though neither as a figure of its own: on a contract's first day the balance is the opening balance. No country code is sent, though for some subdivisions (for example Augsburg or Yap) the code is the place name and the holiday's name contains it. The adjustments' dates, kinds and notes, other weeks' days and a contract that ended before this week are not sent by the section. Another week can come back another way: `build_user_context` carries the last 14 rated briefs (`feedback.py`), each with its opening sentence, and a brief that opened on a day off or a balance repeats it in every later prompt. `PRIVACY.md` lists that too.
- **The page's figures, as the page shows them.** Expected, worked and what is left are the API's own `expected`, `worked` and `remaining`, each printed as the page's `hours1` prints it (`_hours`: one decimal, `toFixed` on the binary value), never read back off the other two. The page rounds each on its own, so 8.545 h of 40 reads 8.5 worked and 31.4 to go there, and the coach says the same rather than something that adds up; a brute-force test over whole seconds holds the two to the same tenth. Worked is the page's, the whole week's; on a week the contract starts or ends inside, what is left counts only the contract's days, and the line says "(the contract counts only its own days this week)".
- **An ended contract is not live.** Once `ended_on` is before today nothing more counts, so a contract that ended earlier this week sends only "final balance: … (contract ended …)": no "to go", no today line, no projection, as the project page shows it. The last day stays live, since its hours still count and its expectation is charged the next morning.
- Best-effort, like the calendar and biometric sections: a failing read drops the section, not the brief.

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

`chat.py:handle_chat_turn` is bounded by `MAX_TOOL_TURNS = 8`. Each round is a full LLM call; legitimate research-style turns chain 4-5 tools (e.g. `get_projects` → `get_beats` → `get_patterns` → text), and the cap leaves headroom for a clarifying follow-up before bailing out.

`TOOL_RESULT_DISPLAY_LIMIT = 500` truncates the SSE event for the UI's tool-result chip but the LLM sees the full output in the next round's messages — a long `search_beats` result over a multi-month workspace shows the user a snippet but feeds the model the complete context.

`MAX_HISTORY_TURNS = 20` caps how many prior messages we load into context per chat turn. Older turns are persisted in `coach_conversations` but not re-fed to the model; the weekly memory rewrite is the long-term memory mechanism.

## Cache control

The most consequential cost lever in this layer.

The **system prompt** (~2k tokens of `COACH_PERSONA`) and the **30-day user-context block** (~3-5k tokens of recent activity + memory) are large and stable across many turns; the **today/day-context block** is small and changes daily; per-turn user messages are small and unique.

`gateway._apply_cache_control` injects `cache_control: {"type": "ephemeral"}` markers per the `CacheSpec`:

```python
CacheSpec(
    system_cached=True,  # system prompt → 1 marker
    cached_turn_indices=[0],  # message[0] (the user-context block) → 1 marker
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
| `memory_rewrite` | `memory_rewrite.py:rewrite_coach_memory` | weekly |

`/api/coach/usage` aggregates by day and by purpose so a single weekly memory-rewrite cost (a few cents per user) doesn't hide inside the chat bucket.

## Tools

The chat coach can call five tools via Anthropic's tool-use API. Each is a small async function over the user's repos:

| Name | Purpose |
|------|---------|
| `get_projects` | Active project list with weekly goals — on a day job the contract governs, its hours and their origin (`contract, 80%`) — or the full list if `include_archived` |
| `get_beats` | Sessions in a date range (default last 7 days), optionally filtered by project name |
| `get_productivity_score` | Score 0-100 with consistency / goals / quality components |
| `get_patterns` | Detected patterns (day patterns, peak hours, stale projects, session trends) |
| `search_beats` | Sessions whose notes or tags match a query (case-insensitive) |

A tool exception becomes `"Error: <msg>"` in the `tool_result` SSE event — the LLM gets the error in the next round and can recover gracefully rather than 500'ing the whole stream. All five tools are read-only over the repos.

Schemas (`TOOL_SCHEMAS`) are built once at module load and registered on every chat-loop call.

## Persistence

Every collection name is a constant in `repos.py`:

| Constant | Collection | Holds |
|----------|------------|-------|
| `COACH_MEMORY_COLLECTION` | `coach_memory` | Per-user Markdown memory + versioned `history` array |
| `DAILY_BRIEFS_COLLECTION` | `daily_briefs` | One `brief` doc per (user_id, date) |
| `COACH_CONVERSATIONS_COLLECTION` | `coach_conversations` | One row per chat turn (role, content, tool_calls, conversation_id, created_at) |
| `LLM_USAGE_COLLECTION` | `llm_usage` | One row per gateway call (model, tokens, cost, purpose, ts) |

`MemoryStore.write` `$push`es the previous content to a `history` array on every write so a bad memory rewrite is recoverable. `daily_briefs` upserts on (user_id, date) — re-generating overwrites that day's brief.

## Test layout

Two test files cover this directory:

- **`src/beats/test_coach.py`** — module-level tests with mocked LLM. Covers fmt_minutes, MemoryStore, UsageTracker (incl. budget invariants), brief, the chat tool-use loop with fake gateway responses, the tools dispatch, the context builders (the contract section runs the real `ContractService` over in-memory stores on a fixed clock), `describe_balance`'s parity with the SPA, and the gateway integration (cache-control + budget).
- **`src/test_api.py::TestCoachEndpoints` + `TestCoachRouterGapFill`** — HTTP-level tests against the real API client. Covers the auth wall, the `/chat/history` pagination, the `/usage` aggregation shape, and the `BUDGET_EXCEEDED` 429 envelope across `/brief` and `/memory/rewrite`.

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
- **No tool with side effects on user data.** All five tools are read-only over the repos. A tool that mutated state would need to plumb through the API's auth/idempotency middleware, not the coach loop.
- **Markdown out, structured JSON for tool_use only.** Coach text replies are Markdown so the UI can render rich formatting. Tool inputs and outputs use the typed Anthropic tool-use protocol; the schemas in `TOOL_SCHEMAS` are the contract.
- **`purpose` tag on every call.** Distinguishes the cost buckets in the dashboard. New coach surfaces should pick a unique purpose value rather than reusing an existing one.
