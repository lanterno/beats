# Beats API

FastAPI + PyMongo (async MongoDB) — Python 3.14, managed by uv.

## Architecture

```
src/beats/
├── api/          Route handlers + Pydantic schemas
│   ├── routers/  One file per resource — see CLAUDE.md (root) for the full route table
│   ├── errors.py     Unified error envelope: {detail, code, fields?}
│   ├── middleware/   IdempotencyMiddleware (the auth middleware lives in
│   │                  src/server.py; rate limits are decorator-based via
│   │                  slowapi on the routes themselves)
│   ├── schemas.py    Request/response Pydantic models
│   └── dependencies.py
├── domain/       Business logic + models (no framework deps)
│   ├── models.py        Pydantic domain models (Beat, Project, WeeklyPlan, …)
│   ├── exceptions.py    DomainException hierarchy → unified envelope
│   ├── services.py      TimerService, ProjectService, BeatService, ContractService
│   ├── contracts.py     Work-contract arithmetic: term in force, expected hours, balance
│   ├── holidays.py      The only importer of the `holidays` package: calendars, regions
│   ├── analytics.py     Heatmap, daily rhythm, untracked gaps
│   ├── intelligence/    Productivity score, digests, patterns, planning, focus,
│   │                    health — one module each, plus a thin IntelligenceService
│   ├── ports.py         Protocols the domain asks persistence for (narrow by design)
│   ├── calendar.py      Google Calendar OAuth + event fetching
│   ├── github.py        GitHub OAuth + commit correlation
│   ├── fitbit.py        Fitbit OAuth + biometric sync
│   ├── oura.py          Oura PAT + biometric sync
│   └── utils.py         Date helpers (week-of, ISO conversion)
├── coach/        AI coach — streaming chat, brief generation, memory
│   ├── chat.py, gateway.py, context.py, tools.py, memory.py, …
├── infrastructure/
│   ├── database.py      PyMongo async client singleton (Database.connect/disconnect)
│   ├── migrations.py    Startup pass: a project without `kind` gets one (and a contract)
│   └── repositories.py  Abstract + MongoDB repo implementations
├── settings.py   pydantic-settings (reads .env / env vars)
├── auth/         WebAuthn + JWT session management
└── server.py     FastAPI app + lifespan (in src/, not src/beats/)
```

## Running

```bash
just run-locally        # uvicorn --reload on :7999
uv run --group dev pytest src/ -v   # Tests (auto-starts MongoDB via testcontainers)
```

## Testing

Nine test files cover different layers (849 tests, ~30s for the full run):

- **`src/test_api.py`** — HTTP integration tests against real MongoDB (testcontainers). One class per router; 293 tests.
- **`src/beats/test_domain.py`** — pure-Python domain tests (no DB). Models, validation, AnalyticsService helpers. Uses small in-memory fakes where a repo is needed; 266 tests.
- **`src/beats/test_contracts.py`** — the work-contract arithmetic on its interesting inputs, plus one round trip through the absence repository; 27 tests.
- **`src/beats/test_migration.py`** — the startup pass that gives every project a `kind` and derives a day job's contract from its goal history; 15 tests.
- **`src/beats/test_coach.py`** — coach gateway, chat loop, memory, and usage tracking against scripted Anthropic responses; 137 tests.
- **`src/beats/test_auth.py`** — session manager, WebAuthn, and token revocation; 62 tests.
- **`src/beats/test_sso.py`** — home.space SSO with a scripted issuer (`httpx.MockTransport`) and real Ed25519 tokens; 35 tests.
- **`src/beats/test_middleware.py`** — idempotency middleware, no DB; 8 tests.
- **`src/beats/test_device_access.py`** — the device-verdict cache; 6 tests.

Harness:

- `conftest.py` starts a `MongoDbContainer` via testcontainers, sets `DB_DSN`/`DB_NAME` env vars
- The `test_client` fixture creates `TestClient(app)` inside a `with` block (triggers lifespan)
- The `mongo` fixture is one session-scoped `MongoClient` shared by every fixture below it
- `_indexes` builds the index set once per session by calling the production
  `ensure_indexes()` directly, so the harness cannot drift from what the app creates
- `clean_db` empties collections between test classes with `delete_many({})` rather than
  dropping them — a drop takes the collection's indexes with it, and rebuilding the full
  index set per class is what used to exhaust mongod's file descriptors and crash it
  mid-run. Per-test cleanup goes in autouse fixtures inside each test class (see
  `TestAccountAPI._reset_account_state` for the pattern)
- An autouse `_reset_rate_limiter` fixture clears the slowapi store before every test so rate-limit-exhausting tests don't bleed into the rest of the suite
- Coverage threshold: 65% (`--cov-fail-under=65`)
- Set `BEATS_TEST_ENV=1` to skip testcontainers (uses whatever `DB_DSN` is configured)

Before adding a test, see **What to test, and what not to** in the repo-root
`CLAUDE.md` — in particular that configuration, framework behaviour, and
whatever a mock was told to return are not worth pinning.

## Key Patterns

- `Database` is a singleton; `connect()` is called in the FastAPI lifespan, not at import time
- Settings use pydantic-settings: env vars override `.env` file values
- Auth: All endpoints require JWT Bearer token (WebAuthn sessions). Public paths: `/api/auth/*`, `/health`, `/api/device/pair/exchange` (the daemon's pairing-code redemption — unauthenticated by design, rate-limited at 10/min)
- Device tokens (daemon, wall-clock) are a separate JWT type; the auth middleware allows them only on paths in `DEVICE_ALLOWED_PREFIXES` (see `src/server.py`). Adding a new daemon-reachable path means appending to that tuple.
- Error envelope: every non-2xx response carries `{detail, code, fields?}`. Routers can override the auto-mapped code by raising `HTTPException(detail={"code": "X", "message": "..."})` — see `coach.py` and `auth.py` for examples.
- Multi-user: Each user's data is scoped via `user_id` field on all collections. Repos accept `user_id` in constructor.
- `auth_info` fixture in conftest.py creates a test user + JWT for integration tests
- The `date` type from `datetime` is imported as `date_type` to avoid Pydantic field-name clashes

## Linting

```bash
uv run --group dev ruff check       # Lint
uv run --group dev ruff format      # Format
uv run --group dev ty check         # Type check (ty has suppressed warnings for PyMongo/Pydantic)
```
