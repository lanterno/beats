# Beats API

FastAPI + Motor (async MongoDB) — Python 3.14, managed by uv.

## Architecture

```
src/beats/
├── api/          Route handlers + Pydantic schemas
│   ├── routers/  One file per resource — see CLAUDE.md (root) for the full route table
│   ├── errors.py     Unified error envelope: {detail, code, fields?}
│   ├── middleware/   Auth, idempotency, rate limit
│   ├── schemas.py    Request/response Pydantic models
│   └── dependencies.py
├── domain/       Business logic + models (no framework deps)
│   ├── models.py        Pydantic domain models (Beat, Project, Intention, …)
│   ├── exceptions.py    DomainException hierarchy → unified envelope
│   ├── services.py      TimerService, ProjectService, BeatService
│   ├── analytics.py     Heatmap, daily rhythm, untracked gaps
│   ├── intelligence.py  Productivity score, weekly digests, pattern detection
│   ├── calendar.py      Google Calendar OAuth + event fetching
│   ├── github.py        GitHub OAuth + commit correlation
│   ├── fitbit.py        Fitbit OAuth + biometric sync
│   ├── oura.py          Oura PAT + biometric sync
│   ├── export_sqlite.py Encrypted SQLite export bundle
│   ├── export_signing.py Signing/verification for export bundles
│   └── utils.py         Date helpers (week-of, ISO conversion)
├── coach/        AI coach — streaming chat, brief generation, EOD reviews
│   ├── chat.py, gateway.py, context.py, tools.py, review.py, memory.py, …
├── infrastructure/
│   ├── database.py      Motor singleton (Database.connect/disconnect)
│   ├── repositories.py  Abstract + MongoDB repo implementations
│   └── export_key_repo.py  Per-user export-bundle signing keys
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

Two test files cover different layers:

- **`src/test_api.py`** — HTTP integration tests against real MongoDB (testcontainers). One class per router; ~190 tests.
- **`src/beats/test_domain.py`** — pure-Python domain tests (no DB). Models, validation, AnalyticsService helpers. Uses small in-memory fakes where a repo is needed; ~65 tests.

Harness:

- `conftest.py` starts a `MongoDbContainer` via testcontainers, sets `DB_DSN`/`DB_NAME` env vars
- The `test_client` fixture creates `TestClient(app)` inside a `with` block (triggers lifespan)
- `clean_db` fixture drops all collections between test classes; per-test cleanup goes in autouse fixtures inside each test class (see `TestAccountAPI._reset_account_state` for the pattern)
- An autouse `_reset_rate_limiter` fixture clears the slowapi store before every test so rate-limit-exhausting tests don't bleed into the rest of the suite
- Coverage threshold: 65% (`--cov-fail-under=65`)
- Set `BEATS_TEST_ENV=1` to skip testcontainers (uses whatever `DB_DSN` is configured)

## Key Patterns

- `Database` is a singleton; `connect()` is called in the FastAPI lifespan, not at import time
- Settings use pydantic-settings: env vars override `.env` file values
- Auth: All endpoints require JWT Bearer token (WebAuthn sessions). Public paths: `/api/auth/*`, `/health`, `/talk/ding`, `/api/device/pair/exchange` (the daemon's pairing-code redemption — unauthenticated by design, rate-limited at 10/min)
- Device tokens (daemon, wall-clock) are a separate JWT type; the auth middleware allows them only on paths in `DEVICE_ALLOWED_PREFIXES` (see `src/server.py`). Adding a new daemon-reachable path means appending to that tuple.
- Error envelope: every non-2xx response carries `{detail, code, fields?}`. Routers can override the auto-mapped code by raising `HTTPException(detail={"code": "X", "message": "..."})` — see `coach.py` and `auth.py` for examples.
- Multi-user: Each user's data is scoped via `user_id` field on all collections. Repos accept `user_id` in constructor.
- `auth_info` fixture in conftest.py creates a test user + JWT for integration tests
- The `date` type from `datetime` is imported as `date_type` to avoid Pydantic field-name clashes

## Linting

```bash
uv run --group dev ruff check       # Lint
uv run --group dev ruff format      # Format
uv run --group dev ty check         # Type check (ty has suppressed warnings for Motor/Pydantic)
```
