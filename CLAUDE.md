# Beats — Developer Guide

Personal time-tracking system: Python API + React SPA + ESP32 wall clock.

## Repository Layout

```
api/          Python (FastAPI + Motor/MongoDB)
ui/           React 19 SPA (Vite + TypeScript)
wall-clock/   ESP32 firmware (Arduino/C++)
terraform/    GCP infrastructure
```

## Quick Start

```bash
# API — requires Docker for MongoDB (testcontainers handles it automatically)
cd api && uv run --group dev pytest src/ -v

# UI
cd ui && pnpm dev          # Dev server on :8080
cd ui && pnpm test         # Vitest unit tests
cd ui && pnpm e2e          # Playwright (needs API + UI running)

# API local server
cd api && just run-locally  # uvicorn on :7999
```

## Git Hooks (Lefthook)

Pre-commit: `ruff check`, `ty check`, `biome check`
Pre-push: `pytest`, `tsc`

Install: `lefthook install` (from repo root)

## Key Commands

| What            | Where | Command                          |
|-----------------|-------|----------------------------------|
| API lint        | api/  | `uv run --group dev ruff check`  |
| API typecheck   | api/  | `uv run --group dev ty check`    |
| API test        | api/  | `uv run --group dev pytest src/` |
| UI lint         | ui/   | `pnpm lint`                      |
| UI lint fix     | ui/   | `pnpm lint:fix`                  |
| UI typecheck    | ui/   | `pnpm typecheck`                 |
| UI test         | ui/   | `pnpm test`                      |
| UI E2E          | ui/   | `pnpm e2e`                       |
| API contracts   | api/  | `hurl --test tests/hurl/*.hurl`  |

## Testing Strategy

- **API integration tests** use testcontainers (auto-starts MongoDB). Just run `pytest`.
  Set `BEATS_TEST_ENV=1` to skip testcontainers (e.g., in Docker Compose or CI with service containers).
- **UI unit tests** are in `client/**/*.test.ts` (Vitest).
- **E2E tests** are in `ui/e2e/` (Playwright, Chromium only).
- **API contract tests** are in `api/tests/hurl/` (Hurl).

## Conventions

- Python: Ruff for linting/formatting, ty for type checking, line length 100
- TypeScript: Biome for linting/formatting, tsc strict mode, tabs, line width 100
- API auth: JWT Bearer token (WebAuthn sessions) for all endpoints
- Dates: API sends UTC, UI converts to local timezone on display
