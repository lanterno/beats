# Beats Architecture

Beats is a personal time tracking system with four components: a **Python API**, a **React web UI**, an **ESP32 wall clock**, and **Terraform infrastructure**. This document covers how they fit together and the key design decisions behind each.

---

## System Overview

```
┌─────────────┐     HTTP/REST     ┌─────────────┐     Motor      ┌──────────┐
│   React UI  │ ◄──────────────► │  FastAPI     │ ◄────────────► │ MongoDB  │
│  (Vite/TS)  │   localhost:8080  │  (Python)    │                │ (Cloud)  │
└─────────────┘                   └──────┬───────┘                └──────────┘
                                         │
                                         │ HTTP polling
                                         │
                                  ┌──────┴───────┐
                                  │  ESP32 Wall  │
                                  │    Clock     │
                                  └──────────────┘
```

The API is the single source of truth. The UI and wall clock are both clients that read and write through it. There is no direct communication between the UI and the wall clock.

---

## API (`/api`)

**Stack:** Python 3.14, FastAPI, Motor (async MongoDB), Pydantic v2, uvicorn

### Layered Architecture

```
api/src/
├── server.py                    # FastAPI app, middleware, lifespan
├── conftest.py                  # Pytest config (testcontainers)
├── test_api.py                  # Integration tests
└── beats/
    ├── settings.py              # Pydantic Settings (env-based config)
    ├── domain/
    │   ├── models.py            # Beat, Project, Intention, DailyNote, Webhook
    │   ├── services.py          # BeatService, ProjectService, TimerService
    │   ├── analytics.py         # AnalyticsService (heatmap, rhythm)
    │   └── utils.py             # Timezone normalization
    ├── infrastructure/
    │   ├── database.py          # Motor client singleton (connect/disconnect)
    │   └── repositories.py      # Abstract repos + Mongo implementations
    ├── auth/
    │   ├── session.py           # JWT session management
    │   └── storage.py           # WebAuthn credential storage
    └── api/
        ├── dependencies.py      # FastAPI Depends() wiring
        ├── schemas.py           # Request/response Pydantic models
        └── routers/
            ├── projects.py      # CRUD, timer start/stop, stats
            ├── beats.py         # Session CRUD, filtering
            ├── timer.py         # Timer status
            ├── analytics.py     # Heatmap, rhythm, tags
            ├── intentions.py    # Daily planning
            ├── daily_notes.py   # End-of-day reflections
            ├── webhooks.py      # Webhook CRUD + dispatch
            ├── export.py        # JSON backup/restore, CSV export
            ├── device.py        # Wall clock status + favorites
            └── auth.py          # WebAuthn registration/login
```

### Domain Layer

Pure business logic with no framework dependencies.

- **Beat** — A single time tracking session with start/end timestamps, project reference, optional note and tags. Computed properties: `duration` (timedelta), `day` (date).
- **Project** — A named time category with optional weekly goal (target or cap), color, and archive flag.
- **Intention** — A daily plan item: "2h on project X today."
- **DailyNote** — An end-of-day text reflection with optional mood (1-5).
- **Webhook** — A registered URL to receive `timer.start` / `timer.stop` events.

Services orchestrate domain logic: `TimerService` enforces single-active-timer, `AnalyticsService` computes heatmaps and daily rhythm distributions.

### Infrastructure Layer

- **Database** — Singleton async MongoDB connection via Motor. Connected during FastAPI lifespan startup, disconnected on shutdown. Accepts `dsn` and `db_name` parameters for test override.
- **Repositories** — Abstract base classes (`BeatRepository`, `ProjectRepository`, etc.) with MongoDB implementations. All async. Handles ObjectId serialization.

### Dependency Injection

FastAPI's `Depends()` wires everything together in `dependencies.py`:

```
Database.get_db() → MongoXxxRepository(collection) → XxxService(repo) → Router handler
```

Type aliases like `BeatServiceDep = Annotated[BeatService, Depends(get_beat_service)]` keep router signatures clean.

### Authentication

All requests (except public paths) require a JWT Bearer token from WebAuthn passkey sessions, checked by middleware in `server.py`.

### Webhook Dispatch

When a timer starts or stops, `dispatch_webhook_event()` fires HTTP POSTs to all registered webhook URLs matching the event type. Uses `httpx.AsyncClient` with `asyncio.gather` for parallel delivery. Fire-and-forget with error logging.

---

## Web UI (`/ui`)

**Stack:** React 19, TypeScript, Vite, TanStack React Query, React Router, Tailwind CSS v4, Radix UI

### Feature-Sliced Design (FSD)

```
ui/client/
├── app/            # App shell, routing, providers
├── pages/          # Route-level components
│   ├── index/      # Dashboard (timer, feed, project list)
│   ├── insights/   # Heatmap, rhythm, monthly retro, year review
│   ├── project-details/
│   ├── settings/   # Themes, webhooks, developer info
│   └── not-found/
├── widgets/        # Complex composed UI (sidebar)
├── features/       # Cross-cutting features
│   ├── timer/      # Timer controls, hooks
│   └── auth/       # WebAuthn login
├── entities/       # Domain data layers
│   ├── session/    # Beat/session API, queries, types
│   ├── project/    # Project API, queries, types
│   └── planning/   # Intentions, daily notes
└── shared/         # Reusable utilities
    ├── api/        # HTTP client (fetch wrapper)
    ├── lib/        # formatDuration, parseUtcIso, etc.
    ├── config/     # Constants
    └── ui/         # TagInput, EmptyState, etc.
```

Each entity follows a `model/api/ui` structure. Data fetching uses TanStack Query with query key factories (e.g., `sessionKeys.all`, `sessionKeys.heatmap(year)`).

### Theming

Five dark themes implemented via CSS custom properties on `:root[data-theme="..."]`:

- **Default** — Warm brown/amber
- **Midnight** — Cool blue/slate
- **Forest** — Green/dark
- **Mono** — Pure grayscale
- **Sunset** — Warm red/orange

Three density levels (`compact`, `default`, `spacious`) adjust the root font size. Preferences stored in localStorage.

### Insights Pages

- **Contribution Heatmap** — 52-week GitHub-style grid, filterable by project and tag
- **Daily Rhythm Chart** — 48 half-hour slots showing when you work
- **Weekly Card** — Shareable visual summary with copy-to-clipboard
- **Monthly Retrospective** (`/insights/month/:yearMonth`) — Stats, project breakdown, tag cloud
- **Year in Review** (`/insights/year/:year`) — Typographic poster with monthly chart, project rankings, work hours distribution

---

## Wall Clock (`/wall-clock`)

**Stack:** ESP32, Rust (embedded), HTTP client

A physical desk device with a button, status LED, and 7-segment energy meter. Communicates with the API:

- **Button press** → `POST /api/projects/{id}/start` or `POST /api/projects/stop` (toggle)
- **Status polling** → `GET /api/device/status` returns timer state, project color, daily progress, theme accent color
- **Favorites** → `GET /api/device/favorites` for multi-project switching (double-press cycles)
- **Heartbeat** → `POST /api/device/heartbeat` reports battery, WiFi RSSI, uptime

The status LED shows the active project's color. The energy meter fills up based on daily hours tracked. Theme accent colors sync from the web UI.

---

## Testing

### Test Pyramid

```
Unit tests (beats/test_domain.py)     — Pure model/service logic, no DB
Integration tests (test_api.py)       — Full HTTP endpoint tests via TestClient
```

### Testcontainers (Local Integration Tests)

Integration tests use [Testcontainers](https://testcontainers.com/) to spin up a real MongoDB instance automatically. No manual setup required — just `uv run pytest`.

**How it works:**

1. `conftest.py::pytest_configure` starts a `MongoDbContainer("mongo:8")` on a random port
2. Sets `DB_DSN` and `DB_NAME` environment variables before any test module is imported
3. Pydantic Settings picks up the container's connection string (env vars override `.env.test`)
4. A session-scoped `test_client` fixture creates `TestClient(app)` inside a `with` block, triggering the FastAPI lifespan which connects Motor to the container
5. A class-scoped `clean_db` autouse fixture drops all collections between test classes (using sync pymongo to avoid event loop conflicts with Motor)
6. After all tests, the container is automatically stopped and removed

**Two test modes:**

| Mode | Command | Database |
|------|---------|----------|
| Local (testcontainers) | `uv run pytest src/ -v` | Auto-managed container |
| Docker Compose | `docker compose --profile test up` | `db_test` service |

When `BEATS_TEST_ENV=1` (set by the compose test profile), testcontainers is skipped and tests use the compose-provided MongoDB.

**Key files:**

- `api/src/conftest.py` — Container lifecycle hooks + fixtures
- `api/src/test_api.py` — 28 integration tests (projects, beats, timer, auth)
- `api/src/beats/test_domain.py` — 16 unit tests (models, exceptions)
- `api/.env.test` — Fallback test config (overridden by testcontainers env vars)

### Prerequisites

- **Docker** must be running (testcontainers uses the Docker daemon)
- First run pulls the `mongo:8` image (~200MB), subsequent runs use cache
- No cloud database or Docker Compose needed for local development

---

## Infrastructure (`/terraform`)

Terraform configuration for cloud deployment (GCP Cloud Run, MongoDB Atlas, etc.).

---

## Configuration

The API uses Pydantic Settings with environment variable overrides:

| Variable | Default | Purpose |
|----------|---------|---------|
| `DB_DSN` | `mongodb://localhost:27017` | MongoDB connection string |
| `DB_NAME` | `ptc` | Database name |
| `JWT_SECRET` | `change-me-in-production` | JWT signing key |
| `WEBAUTHN_RP_ID` | `localhost` | WebAuthn relying party ID |
| `WEBAUTHN_ORIGIN` | `http://localhost:8080` | WebAuthn origin |

Settings auto-detect test mode: if `pytest` is in `sys.argv` or `BEATS_TEST_ENV=1`, the `.env.test` file is loaded instead of `.env`.
