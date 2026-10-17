# Beats — Developer Guide

Personal time-tracking system: Python API + React SPA + Go daemon + Flutter companion + VS Code extension + ESP32 wall clock.

## Repository Layout

```
shared/                       Cross-surface data (app-labels.json, brand.json, brand/ — the logo's SVGs)
scripts/                      Cross-surface codegen (gen_app_labels.py, gen_brand.py, gen_icons.py)
api/                          Python (FastAPI + PyMongo/MongoDB)
ui/                           React 19 SPA (Vite + TypeScript)
daemon/                       Go ambient daemon (beatsd) — flow score + auto-timer
companion/                    Flutter desktop companion (timer, coach, integrations)
integrations/vscode-beats/    VS Code extension (workspace heartbeats + status bar)
wall-clock/                   ESP32 firmware (Arduino/C++)
terraform/                    GCP infrastructure
docs/                         Cross-surface design docs
```

## Project Management

Open work lives in Linear — the
[LifePete project](https://linear.app/elghareeb/project/lifepete-a8ecce3a86de), team `AHM`
(the server is in `.mcp.json`). Docs and READMEs hold decisions and designs, never
to-do lists. The `linear` skill (`.claude/skills/linear/`) has the layout and the
loop: branch `<type>/ahm-<n>-<slug>`, `(AHM-n)` at the end of each commit subject,
`Fixes AHM-n` in the PR body, and anything found along the way filed as an issue.
GitHub issues are left to Renovate's Dependency Dashboard.

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
cd companion && flutter run -d macos --dart-define-from-file=config/local.json  # Desktop dev run, against the local API

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
- `pytest src/` (API, with testcontainers Mongo — ~20s for 1161 tests)
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
| Daemon staticcheck     | daemon/                       | `go run honnef.co/go/tools/cmd/staticcheck@v0.8.2 ./...` |
| Companion analyze      | companion/                    | `flutter analyze`                |
| Companion test         | companion/                    | `flutter test`                   |
| VS Code extension lint | integrations/vscode-beats/    | `npm run lint`                   |
| VS Code extension test | integrations/vscode-beats/    | `npm test`                       |

## Testing Strategy

- **API integration tests** use testcontainers (auto-starts MongoDB). Just run `pytest` —
  the full 1161-test suite takes about 20 seconds.
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
- **UI unit tests** are in `client/**/*.test.{ts,tsx}` (Vitest, jsdom env) — 684 of them across 81 files. The `.ts` files cover pure helpers and stores — `shared/lib/`, the entity models and query helpers, the auth store; the `.tsx` files cover React components and hooks via `@testing-library/react`. Both globs are wired in `vitest.config.ts`.
- **E2E tests** are in `ui/e2e/` (Playwright, Chromium only) — 33 of them, last
  run green against a real API + Mongo. They need the API on :7999 and a
  MongoDB behind it; the dev server starts itself. A `setup` project
  mints a session with `api/scripts/e2e_session.py` and plants it in
  localStorage — every page under test sits behind `ProtectedRoute`, and the
  passkey ceremony that normally issues a session cannot run headless. The same
  script seeds a project, three tagged sessions and a week of flow windows,
  because several assertions are about UI that only exists once there is data.
  Layout is what the suite is for that the unit tests cannot be: jsdom draws
  nothing, so a bar at no height or a panel's failure state is checked here.

  ```bash
  docker run -d --name beats-dev-mongo -p 27019:27017 mongo:8
  cd api && DB_DSN=mongodb://localhost:27019 DB_NAME=beats_dev JWT_SECRET=<32+ bytes> \
    uv run uvicorn --app-dir src server:app --port 7999 &
  cd ui && DB_DSN=mongodb://localhost:27019 DB_NAME=beats_dev JWT_SECRET=<same> pnpm e2e
  ```
- **Daemon tests** live next to the code (`*_test.go` per package). The CLI's pure formatters (`formatRecentTable`, `formatStatusJSON`, etc.) are tested directly without spinning up an HTTP server; integration paths use `httptest`.
- **Companion tests** are in `companion/test/` (flutter_test) — 322 of them. Pure helpers — bundle labels, repo path shortening, brief preview, tray icons — have parity tests that mirror the equivalent Go and TypeScript tests.
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
- **The product name** is structural the same way: `shared/brand.json` holds the name
  people see (LifePete), and `scripts/gen_brand.py` stamps it into the SPA's
  `shared/config/brand.ts`, the API's `beats/brand.py`, the companion's `lib/brand.dart`
  and the companion's native manifests and runners. Code reads those constants, never a
  literal. `--check` runs in pre-push and the Brand workflow. Build identifiers (bundle
  IDs, package and binary names, `beatsd`, the `beats` repo and database) are not the
  name and stay put.
- **The logo**, the day ring, is drawn by hand in `shared/brand/` (the tile, a full-bleed
  copy for launchers that cut their own shape, a tileless 32-grid favicon with its own
  light and dark colours, and the macOS icon on Apple's 1024 grid). `scripts/gen_icons.py`
  copies and rasterizes them into `ui/public/` and every companion target: the macOS and
  iOS AppIcon sets, Android's mipmaps, the Windows `.ico` and the Flutter web shell. It
  needs `rsvg-convert` and has no `--check`, so run it after editing an SVG and commit what
  it wrote. Android's adaptive icon is drawn again by hand as vector drawables
  (`res/drawable/ic_launcher_*`), and the Linux runner sets no icon. In code, `BrandMark`
  draws the tile beside the name (`shared/ui/brand-mark.tsx`, and in the companion's
  `screens/shell.dart`), and two places draw the ring in a project's colour: the
  running-timer favicon (`useFavicon.ts`) and the menu bar icon (`tray_icon.dart`).
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
  extension has its own config. Accessibility rules are on and fail the check, all
  but `noAutofocus`: dialogs put the cursor in their first field on purpose. A site
  that follows an ARIA pattern the rules misread, such as the project picker's
  combobox, carries a `biome-ignore` saying which.
- Go: gofmt + `go vet` + `staticcheck`; tests use stdlib `testing` only (no testify).
  `main()` only turns `run(args) int` into a process exit, so the CLI dispatch is
  testable without spawning a process. Pure formatters are extracted from CLI commands so they're testable without HTTP fixtures.
- Dart: `flutter analyze` (no extra linter config); tests use `flutter_test` package.
- API auth: JWT Bearer token for all endpoints. Two ways to obtain one — beats'
  own WebAuthn passkey login, or single sign-on through an OpenID Connect provider.
  Either way the token is an ordinary beats session; nothing downstream knows which
  door was used.
- Dates: API sends UTC, UI converts to local timezone on display
- API errors: every non-2xx response shares the unified envelope `{detail, code, fields?}` (see `api/src/beats/api/errors.py`). The daemon Go client, UI ApiError, and companion ApiException all parse this shape.
- Contracts: every project has a `kind` (`day_job`, `freelance`, `side_project`) and only a
  day job carries a `contract` — dated terms, the employer's holiday region, an opening
  balance, an `ended_on`. `ProjectService` refuses a contract on any other kind
  (409 `NOT_A_DAY_JOB`) and checks the region on every contract write. Two startup passes
  run in `lifespan` (`api/src/beats/infrastructure/migrations.py`), each keyed on document
  shape and so idempotent: `migrate_project_kinds` stamps `kind` on every project without
  one and derives a day job's contract from its target goal; `clear_personal_goal_on_day_jobs`
  unsets `weekly_goal` on every day job whose term in force today is time-based. The
  `holidays` package is imported in `domain/holidays.py` and nowhere else, and
  `contract_holidays` there is the one place the region's calendar meets the contract's own
  additions and removals (`company_holidays`, `holidays_not_given`); the arithmetic in
  `domain/contracts.py` takes holidays as a set of dates. Worked time is bucketed by the
  local date each beat started on, in the request timezone (`tz`, default UTC); the holiday
  region is the employer's, whatever the timezone. `GET /{id}/ledger` is the project page's
  one read for every week figure — `domain/ledger.py` assembles N weeks from one worked map,
  one absence list, one adjustment list and one holiday calendar, and `/contract/week`
  carries the four terms under its balance (`balance_opening + balance_worked -
  balance_expected_through + balance_adjusted`, equal to `balance` within 0.025, since each
  term is rounded on its own). A day job's balance takes dated balance adjustments (a
  signed `delta`, a `reset` to a value, a `cap` at a ceiling), one per day, each applied at
  the start of its day against the day before's close; they go with the contract. A week's
  closing balance is the Sunday close, before Monday's adjustment, read off one running
  total (`running_balance`) with today's terms and every adjustment's `applied`. The balance
  counts a day's hours only under a term that owes hours (`counts_worked`): what is worked
  under an objective or 0-hour term is not overtime. On the week a contract starts or ends
  mid-week, or such a term begins or ends, `worked` counts hours the balance does not, so the
  page's +/− is each week's `balance_moved`: the move between two closes, less the
  adjustments between, read off the same pass even for the oldest week shown. A contract
  may carry a `vacation` entitlement — days per year for a five-day week, a carry-over
  rule, and a dated opening where counting starts (nothing before it is reconstructed) —
  that `domain/vacation.py` reads one calendar year at a time; only `vacation` absences
  cost it. A contract write that leaves out `vacation` or a holiday list keeps the stored
  one (`keep_unsent_contract_fields`), and both writes refuse an opening left outside the
  contract's dates (409). The decisions are in
  [docs/work-contracts.md](docs/work-contracts.md) and
  [docs/project-page.md](docs/project-page.md).
- Theme: two hours, `afternoon` (light, the default, on `:root`) and `dusk`
  (`:root[data-theme="dusk"]`), picked in Settings beside the density. `useTheme.ts` owns the
  storage keys, and a stored value that is neither hour reads as afternoon. Behind the app and
  the marketing page is the sky — `SkyBackdrop` (`ui/client/shared/ui/sky-backdrop.tsx`: gradient, sun, clouds,
  hills), a fixed layer at z-index −1, so nothing between it and the root may paint a
  background. Surfaces are `Panel` (rounded, the panel shadow, no border) and controls are
  pills. Two rounded faces: M PLUS Rounded 1c for display figures and every column of digits
  (`font-heading`, `font-mono`), Zen Maru Gothic for everything read (`font-body`); real code
  is `font-code`. A script in `ui/index.html` stamps the stored hour and density before first
  paint, so a stored dusk does not flash the afternoon; it repeats the keys and the dusk
  sky's hex, so a change to either is made in both places. The Mac companion is drawn
  in the same two hours from the same tokens, copied into `companion/lib/theme/sky.dart`;
  a colour changed in `global.css` is changed there too.

## Daemon CLI

`beatsd` is the Go daemon. After `beatsd pair <code>`, every read-side command (`recent`, `top`, `stats`, `status`, `doctor`, `config`, `version`) supports `--json` for shell pipelines. `--here` is shorthand for `--repo $(git rev-parse --show-toplevel)`. See [daemon/README.md](daemon/README.md) for the full command reference.

## Infrastructure

**One deployment is live: lifepete.com** on Google Cloud — API on Cloud Run
(shipped by `api/cloudbuild.yaml` + `terraform/`), SPA on Firebase Hosting (shipped
by the `deploy` job in `.github/workflows/ui.yml`). **Two origins**,
`lifepete.com` and `api.lifepete.com`, joined by CORS.

Nothing you run locally resembles it, and that is the trap: the entries in
`origins` (`api/src/server.py`) that keep lifepete.com working read as dead
config from inside the repo. They are not: removing them breaks the site in a
browser with every test still green. The same goes for the Firebase `deploy`
job and `ui/firebase.json`. A change that touches origins, hosts, auth cookies,
or the deploy pipeline has to be considered against that topology.

Anything else LifePete talks to — another identity provider, a service of
your own — connects through single sign-on or an integration.
`api/compose.yml` is what local development uses.

### Self-hosted

`compose.selfhost.yml` is for anyone running LifePete themselves: Mongo and the
API on an internal network, plus an nginx that serves the built SPA and proxies
`/api`, on **one** published port, 6008. The root `justfile` wraps it
(`up-detached`, `down`, `build`, `health`, `logs`, `backup`, `restore`).
`BEATS_DB_PASSWORD`, `BEATS_RP_ID` and `BEATS_ORIGIN` are required; the rest
comes from `api/.env`. The SPA and the API share one origin, so it needs no CORS
entry: `ui/Dockerfile` builds with `VITE_API_URL=""` and fails the build if the
bundle still names `localhost:7999`.

### Single sign-on (OpenID Connect)

A second, optional door beside beats' own passkey login: any provider that speaks
OpenID Connect (Google, Microsoft, Keycloak, Authentik, …). Off unless
`OIDC_PROVIDERS` names one; `api/.env.example` shows the shape. Each deployment sets
its own `OIDC_REDIRECT_URI` — the web app's `/auth/callback` — and registers it with
each provider.

The flow is the authorization code flow with PKCE and a nonce. The API keeps each
sign-in's state, nonce and verifier in `sso_flows` (TTL ten minutes, taken once); the
provider sends the browser to the web app, which checks the state is one this tab
started (sessionStorage) and posts the code to `POST /api/auth/sso/complete`. Doing
the exchange through the web app keeps the provider's redirect on the web app's
origin, whichever origin the API is on.

- `src/beats/auth/oidc.py` — discovery, the code exchange, and every ID-token check
  (asymmetric signature, `iss`, `aud`/`azp`, `exp`, `iat`, nonce).
- `src/beats/auth/sso_accounts.py` — sign in / link / unlink. Identities are keyed on
  issuer + subject, at most one per provider per account. A provider creates
  accounts only with `allow_signup`; nothing is ever matched by email.
- `src/beats/api/routers/sso.py` — the public endpoints; linking and unlinking live in
  `account.py`, behind a session. A link must finish in the session that started it.
- `src/beats/test_sso.py` and `TestSSOAPI` — against `src/fake_idp.py`, a scripted
  provider with real RS256 keys.

### Google Cloud — lifepete.com

Split across two origins: the SPA on Firebase Hosting at `lifepete.com`, the API
on Cloud Run at `api.lifepete.com`. Both are listed in `origins` in
`api/src/server.py`, and the SPA is built with
`VITE_API_URL=https://api.lifepete.com`.

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
| `/api/projects` | Projects CRUD (with `kind` and `contract`), timer start/stop, git activity; `/{id}/ledger` (any kind: N weeks newest first, the goal and hours per week, and on a day job the adjusted expectation, each week's closing balance and today's with its terms); on a day job `/{id}/contract` (replace), `/{id}/contract/week` (the week, and today's balance with the terms that make it), `/{id}/holidays`, `/{id}/absences`, `/{id}/adjustments` (POST, DELETE: balance adjustments), `/{id}/vacation` (one year of the vacation entitlement, in days), `/{id}/timesheet.csv?month=` (a month, a row per finished day, as CSV) |
| `/api/beats` | Sessions CRUD |
| `/api/timer` | Timer status |
| `/api/analytics` | Heatmap, rhythm, gaps, tags |
| `/api/intelligence` | Digests, score, patterns, suggestions, focus scores (a day, or a week), inbox |
| `/api/plans` | Weekly plans (structured per-project hour targets) |
| `/api/webhooks` | Webhook CRUD |
| `/api/coach` | Brief generation and feedback (`PUT /brief/{date}/feedback`, which recent briefs' context reads), streaming chat, usage, memory |
| `/api/biometrics` | Daily health data from companion app / HealthKit / Health Connect |
| `/api/calendar` | Google Calendar OAuth + events |
| `/api/github` | GitHub OAuth + status |
| `/api/fitbit` | Fitbit OAuth + status |
| `/api/oura` | Oura personal-access-token connection + status |
| `/api/signals` | Daemon-emitted flow windows and signal summaries |
| `/api/device` | Wall clock status, favorites, weekly bars, heartbeat, pairing |
| `/api/export` | CSV/JSON export and import |
| `/api/account` | User account management (me, refresh, credentials, logout, linking SSO identities) |
| `/api/auth` | WebAuthn registration + login (public) |
| `/api/auth/sso` | Single sign-on: the providers offered, start and complete a sign-in (public) |
| `/api/meta` | Static reference data: holiday regions for the contract picker, and one region's holidays for a year (cacheable, still behind auth) |
