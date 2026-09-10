# Beats — Developer Guide

Personal time-tracking system: Python API + React SPA + Go daemon + Flutter companion + VS Code extension + ESP32 wall clock.

## Repository Layout

```
shared/                       Cross-surface data (app-labels.json)
scripts/                      Cross-surface codegen (gen_app_labels.py)
api/                          Python (FastAPI + PyMongo/MongoDB)
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

Pre-commit (parallel, fast — runs only on staged files for the relevant surface):
- `ruff check` + `ruff format --check` (Python)
- `ty check src/` (Python type check)
- `biome check client/` (TypeScript lint + format)
- `gofmt -l` (Go formatting)
- `flutter analyze` (Dart)

Pre-push (sequential, full test suites):
- `pytest src/` (API, with testcontainers Mongo — ~25s for 775 tests)
- `tsc` + `vitest` + `pnpm gen:types:check` (UI typecheck, unit tests, generated-API-types drift check)
- `go test ./...` + `go vet ./...` + `staticcheck ./...` (daemon)
- `flutter test` (companion)
- `npm test` (VS Code extension — biome + tsc + node --test)

Install: `lefthook install` (from repo root). Source of truth is [`lefthook.yml`](lefthook.yml).

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
| Daemon staticcheck     | daemon/                       | `go run honnef.co/go/tools/cmd/staticcheck@v0.8.1 ./...` |
| Companion analyze      | companion/                    | `flutter analyze`                |
| Companion test         | companion/                    | `flutter test`                   |
| VS Code extension lint | integrations/vscode-beats/    | `npm run lint`                   |
| VS Code extension test | integrations/vscode-beats/    | `npm test`                       |

## Testing Strategy

- **API integration tests** use testcontainers (auto-starts MongoDB). Just run `pytest` —
  the full 775-test suite takes about 25 seconds.
  Set `BEATS_TEST_ENV=1` to skip testcontainers and point the suite at an
  already-running MongoDB via `DB_DSN`/`DB_NAME` (CI does this with a service
  container; locally it is the fallback when Docker is unavailable):

  ```bash
  docker run -d --name beats-test-mongo -p 27018:27017 mongo:8
  BEATS_TEST_ENV=1 DB_DSN=mongodb://localhost:27018 DB_NAME=beats_test \
    uv run --group dev pytest src/
  ```

  The suite shares one Mongo connection and one index build across the whole
  run; `clean_db` empties collections between test classes rather than dropping
  them, so indexes (including TTL indexes the app creates at startup) survive.
  Dropping and rebuilding them per class is what previously exhausted mongod's
  file descriptors and crashed the database partway through a run.
  The pytest suite covers the HTTP contract end-to-end (TestClient, real Mongo).
- **UI unit tests** are in `client/**/*.test.{ts,tsx}` (Vitest, jsdom env). The `.ts` files cover pure helpers in `shared/lib/`; the `.tsx` files cover React components and hooks via `@testing-library/react`. Both globs are wired in `vitest.config.ts`.
- **E2E tests** are in `ui/e2e/` (Playwright, Chromium only). They need the API on
  :7999 and a MongoDB behind it; the dev server starts itself. A `setup` project
  mints a session with `api/scripts/e2e_session.py` and plants it in
  localStorage — every page under test sits behind `ProtectedRoute`, and the
  passkey ceremony that normally issues a session cannot run headless. The same
  script seeds a project and three tagged sessions, because several assertions
  are about UI that only exists once there is data.

  ```bash
  docker run -d --name beats-dev-mongo -p 27019:27017 mongo:8
  cd api && DB_DSN=mongodb://localhost:27019 DB_NAME=beats_dev JWT_SECRET=<32+ bytes> \
    uv run uvicorn --app-dir src server:app --port 7999 &
  cd ui && DB_DSN=mongodb://localhost:27019 DB_NAME=beats_dev JWT_SECRET=<same> pnpm e2e
  ```
- **Daemon tests** live next to the code (`*_test.go` per package). The CLI's pure formatters (`formatRecentTable`, `formatStatusJSON`, etc.) are tested directly without spinning up an HTTP server; integration paths use `httptest`.
- **Companion tests** are in `companion/test/` (flutter_test). Pure helpers — bundle labels, repo path shortening, brief preview, tray icons — have parity tests that mirror the equivalent Go and TypeScript tests.
- **Bundle-label parity** is structural, not tested: `shared/app-labels.json` is the
  single source and `scripts/gen_app_labels.py` renders it into the Go, TypeScript
  and Dart tables. Edit the JSON, run the script, commit the output;
  `--check` fails CI and pre-push when it is stale.
- **VS Code extension tests** are in `integrations/vscode-beats/src/*.test.ts` (`node --test`, no framework). The pure helpers (`buildInsightsUrl`, `formatStatusBar`) have cross-language parity assertions matching the daemon and companion equivalents.

## Conventions

- Python: Ruff for linting/formatting, ty for type checking, line length 100.
  Repository interfaces are `Protocol`s in `infrastructure/repositories.py`; the
  Mongo classes inherit them for a nominal check while test fakes satisfy them
  structurally. Domain services depend on the narrow ports in `domain/ports.py`
  instead, so the dependency points inward and a service that reads beats cannot
  quietly start writing them.
  The ruff select list in `api/pyproject.toml` documents what each group is for
  and, just as usefully, which groups are deliberately left out. `ty` cannot fail
  CI on its own yet (`error-on-warning = false`); `api/scripts/ty_budget.py` holds
  the diagnostic count at its current ceiling so a new one still does.
- TypeScript: Biome for linting/formatting, tsc strict mode, tabs, line width 100.
  Biome covers `client/`, `e2e/` and the root config files, and the VS Code
  extension has its own config. Accessibility rules are on; seven of them run at
  `warn` because their remaining sites need per-component decisions rather than a
  blanket fix (see `ui/biome.json` for which and why).
- Go: gofmt + `go vet` + `staticcheck`; tests use stdlib `testing` only (no testify).
  `main()` only turns `run(args) int` into a process exit, so the CLI dispatch is
  testable without spawning a process. Pure formatters are extracted from CLI commands so they're testable without HTTP fixtures.
- Dart: `flutter analyze` (no extra linter config); tests use `flutter_test` package.
- API auth: JWT Bearer token for all endpoints. Two ways to obtain one — beats'
  own WebAuthn passkey login, or a home.space SSO exchange. After the exchange the
  token is an ordinary beats session; nothing downstream distinguishes them except
  the `sso` claim, which exists so `/api/account/refresh` can re-check the identity
  against its issuer.
- Dates: API sends UTC, UI converts to local timezone on display
- API errors: every non-2xx response shares the unified envelope `{detail, code, fields?}` (see `api/src/beats/api/errors.py`). The daemon Go client, UI ApiError, and companion ApiException all parse this shape.

## Daemon CLI

`beatsd` is the Go daemon. After `beatsd pair <code>`, every read-side command (`recent`, `top`, `stats`, `status`, `doctor`, `config`, `version`) supports `--json` for shell pipelines. `--here` is shorthand for `--repo $(git rev-parse --show-toplevel)`. See [daemon/README.md](daemon/README.md) for the full command reference.

## Infrastructure

Beats now runs on the **home network**, in the `home.space` stack at
`/home/green/lab/home`. `terraform/` and `cloudbuild.yaml` describe the previous
Google Cloud deployment and are kept for reference — they are not what runs.

### Home deployment (current)

`compose.home.yml` at the repo root: Mongo and the API on an internal network, plus
an nginx that serves the built SPA and proxies `/api` to the API. **One** published
port, 6008. `justfile` at the repo root holds the verbs the stack calls
(`up-detached`, `down`, `build`, `health`, `logs`, `backup`, `restore`).

The SPA and the API deliberately share one origin. That is not a packaging
preference: home.space SSO rides on a `Home-Session` cookie scoped to
`.home.space`, and a browser only attaches it to same-origin requests. The old
Firebase-plus-Cloud-Run split had two origins joined by CORS; restoring that
split silently breaks SSO. `ui/Dockerfile` builds with `VITE_API_URL=""` and fails
the build if the bundle still names `localhost:7999`.

`api/compose.yml` is untouched and is still what local development uses.

### home.space SSO

A second, optional door beside beats' own passkey login — see
`/home/green/lab/home/AGENTS.md` for the full writeup and the four decisions behind
it. In this repo:

- `src/beats/auth/sso.py` — verifies the cookie (issuer introspection first, offline
  JWKS signature check as the fallback).
- `src/beats/auth/sso_accounts.py` — link / provision / unlink.
- `src/beats/api/routers/sso.py` — the public endpoints.
- `src/beats/test_sso.py` — unit tests, no DB or network (scripted issuer via
  `httpx.MockTransport`, real Ed25519 tokens in the issuer's exact format).
- `TestSSOAPI` in `src/test_api.py` — the HTTP contract.

Off by default (`BEATS_SSO_ENABLED`), so nothing changes for a deployment without an
identity service. `just sso-doctor` from the repo root diagnoses it.

### Google Cloud (previous)

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
| `/api/intelligence` | Digests, score, patterns, suggestions, focus scores, inbox |
| `/api/plans` | Weekly plans (structured per-project hour targets) |
| `/api/webhooks` | Webhook CRUD |
| `/api/coach` | Brief generation, streaming chat, usage, memory |
| `/api/biometrics` | Daily health data from companion app / HealthKit / Health Connect |
| `/api/calendar` | Google Calendar OAuth + events |
| `/api/github` | GitHub OAuth + status |
| `/api/fitbit` | Fitbit OAuth + status |
| `/api/oura` | Oura personal-access-token connection + status |
| `/api/signals` | Daemon-emitted flow windows and signal summaries |
| `/api/device` | Wall clock status, favorites, weekly bars, heartbeat, pairing |
| `/api/export` | CSV/JSON export and import |
| `/api/account` | User account management (me, refresh, credentials, logout, home.space link) |
| `/api/auth` | WebAuthn registration + login (public) |
| `/api/auth/sso` | home.space SSO config + session exchange (public) |
