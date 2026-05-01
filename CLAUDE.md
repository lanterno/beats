# Beats — Developer Guide

Personal time-tracking system: Python API + React SPA + Go daemon + Flutter companion + VS Code extension + ESP32 wall clock.

## Repository Layout

```
api/                          Python (FastAPI + Motor/MongoDB)
ui/                           React 19 SPA (Vite + TypeScript)
daemon/                       Go ambient daemon (beatsd) — flow score + auto-timer
companion/                    Flutter desktop companion (timer, coach, integrations)
integrations/vscode-beats/    VS Code extension (workspace heartbeats + status bar)
wall-clock/                   ESP32 firmware (Arduino/C++)
terraform/                    GCP infrastructure
docs/                         Cross-surface design docs
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

# Daemon
cd daemon && go test ./...                  # All packages
cd daemon && go run ./cmd/beatsd run        # Foreground run (after `beatsd pair`)

# Companion (Flutter)
cd companion && flutter test                # Widget + unit tests
cd companion && flutter run -d macos        # Desktop dev run

# VS Code extension
cd integrations/vscode-beats && npm test    # tsc + node --test
```

## Git Hooks (Lefthook)

Pre-commit: `ruff check`, `ty check`, `biome check`
Pre-push: `pytest`, `tsc`, `vitest`

Install: `lefthook install` (from repo root)

## Key Commands

| What                   | Where                         | Command                          |
|------------------------|-------------------------------|----------------------------------|
| API lint               | api/                          | `uv run --group dev ruff check`  |
| API typecheck          | api/                          | `uv run --group dev ty check`    |
| API test               | api/                          | `uv run --group dev pytest src/` |
| UI lint                | ui/                           | `pnpm lint`                      |
| UI lint fix            | ui/                           | `pnpm lint:fix`                  |
| UI typecheck           | ui/                           | `pnpm typecheck`                 |
| UI test                | ui/                           | `pnpm test`                      |
| UI E2E                 | ui/                           | `pnpm e2e`                       |
| Daemon test            | daemon/                       | `go test ./...`                  |
| Daemon format          | daemon/                       | `gofmt -w .`                     |
| Daemon vet             | daemon/                       | `go vet ./...`                   |
| Companion analyze      | companion/                    | `flutter analyze`                |
| Companion test         | companion/                    | `flutter test`                   |
| VS Code extension test | integrations/vscode-beats/    | `npm test`                       |

## Testing Strategy

- **API integration tests** use testcontainers (auto-starts MongoDB). Just run `pytest`.
  Set `BEATS_TEST_ENV=1` to skip testcontainers (e.g., in Docker Compose or CI with service containers).
  The pytest suite covers the HTTP contract end-to-end (TestClient, real Mongo) so a separate hurl runner isn't needed for routine work.
- **UI unit tests** are in `client/**/*.test.ts` (Vitest).
- **E2E tests** are in `ui/e2e/` (Playwright, Chromium only).
- **`api/tests/hurl/`** holds standalone HTTP contract tests dating from before the WebAuthn/JWT auth migration; they still reference `X-API-Token` and are not run from CI or any hook. Treat them as historical until reauthored to mint a JWT in a setup step.
- **Daemon tests** live next to the code (`*_test.go` per package). The CLI's pure formatters (`formatRecentTable`, `formatStatusJSON`, etc.) are tested directly without spinning up an HTTP server; integration paths use `httptest`.
- **Companion tests** are in `companion/test/` (flutter_test). Pure helpers — bundle labels, repo path shortening, brief preview, tray icons — have parity tests that mirror the equivalent Go and TypeScript tests.
- **VS Code extension tests** are in `integrations/vscode-beats/src/*.test.ts` (`node --test`, no framework). The pure helpers (`buildInsightsUrl`, `formatStatusBar`) have cross-language parity assertions matching the daemon and companion equivalents.

## Conventions

- Python: Ruff for linting/formatting, ty for type checking, line length 100
- TypeScript: Biome for linting/formatting, tsc strict mode, tabs, line width 100
- Go: gofmt + `go vet`; tests use stdlib `testing` only (no testify). Pure formatters are extracted from CLI commands so they're testable without HTTP fixtures.
- Dart: `flutter analyze` (no extra linter config); tests use `flutter_test` package.
- API auth: JWT Bearer token (WebAuthn sessions) for all endpoints
- Dates: API sends UTC, UI converts to local timezone on display
- API errors: every non-2xx response shares the unified envelope `{detail, code, fields?}` (see `api/src/beats/api/errors.py`). The daemon Go client, UI ApiError, and companion ApiException all parse this shape.

## Daemon CLI

`beatsd` is the Go daemon. After `beatsd pair <code>`, every read-side command (`recent`, `top`, `stats`, `status`, `doctor`, `config`, `version`) supports `--json` for shell pipelines. `--here` is shorthand for `--repo $(git rev-parse --show-toplevel)`. See [daemon/README.md](daemon/README.md) for the full command reference.

## Infrastructure

- **Deploy**: Terraform owns all Cloud Run config. Cloud Build builds the image and runs `terraform apply`.
- **State**: GCS backend (`beats-476914-terraform-state`), shared by local and CI.
- **Secrets**: `terraform.tfvars` stored in Secret Manager (`beats-terraform-tfvars`) for CI.
- **Integrations**: Google Calendar and GitHub use per-user OAuth (system-wide client ID/secret, per-user tokens in MongoDB).

## API Routes

| Prefix | Purpose |
|--------|---------|
| `/api/projects` | Projects CRUD, timer start/stop, git activity |
| `/api/beats` | Sessions CRUD |
| `/api/timer` | Timer status |
| `/api/analytics` | Heatmap, rhythm, gaps, tags |
| `/api/intentions` | Daily intentions |
| `/api/daily-notes` | End-of-day notes with mood |
| `/api/intelligence` | Digests, score, patterns, suggestions, focus scores |
| `/api/plans` | Weekly plans, recurring intentions, reviews, streaks |
| `/api/webhooks` | Webhook CRUD, daily summary trigger |
| `/api/calendar` | Google Calendar OAuth + events |
| `/api/github` | GitHub OAuth + status |
| `/api/auto-start` | Auto-start rules + webhook trigger |
| `/api/device` | Wall clock status, favorites, heartbeat |
| `/api/export` | CSV/JSON export and import |
| `/api/account` | User account management |
| `/api/auth` | WebAuthn registration + login (public) |
