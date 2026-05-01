# Beats API

FastAPI + Motor (async MongoDB) — Python 3.14, managed by uv.

## Architecture

```
src/beats/
├── api/          Route handlers + Pydantic schemas
│   ├── routers/  One file per resource (projects, timer, analytics, calendar, github, planning, etc.)
│   ├── schemas.py
│   └── dependencies.py
├── domain/       Business logic + models (no framework deps)
│   ├── models.py
│   ├── analytics.py
│   ├── intelligence.py
│   ├── calendar.py   Google Calendar OAuth + event fetching
│   ├── github.py     GitHub OAuth + commit correlation
│   └── services.py
├── infrastructure/
│   ├── database.py      Motor singleton (Database.connect/disconnect)
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

- Tests are in `src/test_api.py` — integration tests against real MongoDB
- `conftest.py` starts a `MongoDbContainer` via testcontainers, sets `DB_DSN`/`DB_NAME` env vars
- The `test_client` fixture creates `TestClient(app)` inside a `with` block (triggers lifespan)
- `clean_db` fixture drops all collections between test classes
- Coverage threshold: 65% (`--cov-fail-under=65`)
- Set `BEATS_TEST_ENV=1` to skip testcontainers (uses whatever `DB_DSN` is configured)

## Key Patterns

- `Database` is a singleton; `connect()` is called in the FastAPI lifespan, not at import time
- Settings use pydantic-settings: env vars override `.env` file values
- Auth: All endpoints require JWT Bearer token (WebAuthn sessions). Public paths: `/api/auth/*`, `/health`, `/talk/ding`
- Multi-user: Each user's data is scoped via `user_id` field on all collections. Repos accept `user_id` in constructor.
- `auth_info` fixture in conftest.py creates a test user + JWT for integration tests
- The `date` type from `datetime` is imported as `date_type` to avoid Pydantic field-name clashes

## Linting

```bash
uv run --group dev ruff check       # Lint
uv run --group dev ruff format      # Format
uv run --group dev ty check         # Type check (ty has suppressed warnings for Motor/Pydantic)
```
