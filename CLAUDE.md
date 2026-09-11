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
- **E2E tests** are in `ui/e2e/` (Playwright, Chromium only) — 30 of them, last
  run green against a real API + Mongo. They need the API on :7999 and a
  MongoDB behind it; the dev server starts itself. A `setup` project
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
- **Companion tests** are in `companion/test/` (flutter_test) — 159 of them. Pure helpers — bundle labels, repo path shortening, brief preview, tray icons — have parity tests that mirror the equivalent Go and TypeScript tests.
  The SDK lives at `~/development/flutter` (stable), on `PATH` via `~/.zshrc`
  and symlinked into `~/.local/bin` so the lefthook gates — which run under a
  non-interactive `sh` that reads neither — can find it. `flutter doctor`
  reports the Android, Chrome and Linux-desktop toolchains as missing; that is
  expected and does not affect `analyze` or `test`, which is all the hooks run.
  Building the companion for a real target needs those installed.
- **Bundle-label parity** is structural, not tested: `shared/app-labels.json` is the
  single source and `scripts/gen_app_labels.py` renders it into the Go, TypeScript
  and Dart tables. Edit the JSON, run the script, commit the output;
  `--check` fails CI and pre-push when it is stale.
- **VS Code extension tests** are in `integrations/vscode-beats/src/*.test.ts` (`node --test`, no framework). The pure helpers (`buildInsightsUrl`, `formatStatusBar`) have cross-language parity assertions matching the daemon and companion equivalents.

### What to test, and what not to

A test earns its place by failing when something is **broken**. A test that
fails when something is merely **different** costs more than it returns: it has
to be edited as part of every deliberate change, and once people are used to
editing tests to make them pass, the ones that matter stop being read.

**Worth testing**

- **Logic with interesting inputs.** Week math, flow aggregation, fuzzy
  ranking, goal resolution, bundle labels. Boundaries, empty sets, DST,
  timezone conversion, the off-by-one. These are where bugs actually live, and
  they need no fixture beyond the arguments.
- **The HTTP contract.** `test_api.py` drives real routes against real Mongo:
  status codes, the error envelope, auth boundaries, what a route accepts and
  returns. A client on the other end depends on those; a refactor must not move
  them silently.
- **Bugs that happened, pinned where they broke.** The asyncio GC race that
  reaped in-flight webhook dispatches, the idempotency replay, the device-token
  path. Each is a test because the failure was real, subtle, and would look
  like nothing from the outside.
- **Rules implemented more than once.** Bundle labels and status-bar formatting
  exist in Go, TypeScript and Dart. Parity assertions in each language are what
  keep three implementations of one rule honest.
- **Contracts between layers.** That a service refuses what the domain forbids,
  that a port's implementations agree. The narrow protocols in
  `domain/ports.py` exist so this is cheap.

**Not worth testing**

- **Configuration, by restating it.** A test asserting that the CORS allowlist
  contains the origins the CORS allowlist contains proves nothing: it passes
  until someone edits the list, then fails precisely because they meant to. It
  cannot catch the real failure — *forgetting a deployment exists* — because
  that judgment happens before the edit. Config is protected by a comment
  saying who breaks when it changes (see `origins` in `src/server.py`), and by
  checking the deployment, not by a unit test that mirrors the value.
- **The framework.** Starlette's CORS middleware, FastAPI's request validation,
  Pydantic enforcing its own field types, TanStack Query caching. Upstream
  tests these. Test what *we* do with it.
- **Whatever a mock was just told to return.** `AuthModal.test.tsx` mocks
  `@simplewebauthn/browser` wholesale — correctly, since the real ceremony
  needs an authenticator — but that means those tests say nothing about the
  WebAuthn library. Know which half of a mocked test is real, and don't count
  the other half as coverage. When the mocked dependency is upgraded, read its
  signatures; the green suite is not evidence.
- **Getters, wiring, and re-exports.** That a barrel re-exports a symbol, that
  a constructor assigns its arguments, that a dataclass holds fields.
- **Private helpers, directly.** Test them through the public path that uses
  them. A test bound to a private name is a refactor tax.
- **Coverage for its own sake.** The 65% floor is a floor, not a target.
  Reaching for a number produces exactly the tests above.

**When something breaks in production, ask what would have caught it** before
adding a test. Sometimes it is a test. Sometimes it is a type, a narrower port,
a comment on the line that looked dead, or a smoke check against the running
deployment — and a test written in the shape of the bug would have caught
nothing.

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

**Two deployments are live.** Read that before deleting anything that looks
like it belongs to only one of them.

- **home.space** (`compose.home.yml`) on the home network, at
  `/home/green/lab/home` — the primary. SPA and API behind one nginx, **one
  origin**, one published port.
- **lifepete.com** on Google Cloud — API on Cloud Run (shipped by
  `cloudbuild.yaml` + `terraform/`), SPA on Firebase Hosting (shipped by the
  `deploy` job in `.github/workflows/ui.yml`). **Two origins**,
  `lifepete.com` and `api.lifepete.com`, joined by CORS.

The second one is the trap, because nothing you run locally resembles it. The
home stack is same-origin, so CORS is never exercised in development or in the
test suite, and the entries in `origins` (`api/src/server.py`) that keep
lifepete.com working read as dead config from inside the repo. They are not:
removing them breaks that site in a browser with every test still green. The
same goes for the Firebase `deploy` job and `ui/firebase.json`.

A change that touches origins, hosts, auth cookies, or either deploy pipeline
has to be considered against **both** topologies.

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

### Google Cloud — lifepete.com (also live)

Split across two origins, unlike the home stack: the SPA on Firebase Hosting at
`lifepete.com`, the API on Cloud Run at `api.lifepete.com`. Both are listed in
`origins` in `api/src/server.py`, and the SPA is built with
`VITE_API_URL=https://api.lifepete.com` — the opposite of `ui/Dockerfile`, which
builds with an empty `VITE_API_URL` because the home stack is same-origin.

The two halves ship independently: the SPA on every push to `main` that touches
`ui/**` (the `deploy` job in `.github/workflows/ui.yml`, needing the
`FIREBASE_SERVICE_ACCOUNT` secret), the API via Cloud Build. They can therefore
skew — an old SPA against a newer API is a real state to reason about when
changing anything both ends share.

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
