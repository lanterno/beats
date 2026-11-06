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
│   ├── schemas.py    Request/response Pydantic models — one name for the wire
│   │                  vocabulary; the billing and organisation sections live in
│   │                  schemas_billing.py and schemas_organisations.py and are
│   │                  re-exported from here
│   ├── params.py     Query parameters more than one router takes (`MonthQuery`)
│   └── dependencies.py
├── domain/       Business logic + models (no framework deps)
│   ├── models.py        Pydantic domain models (Beat, Project, WeeklyPlan, …) — the
│   │                    one name every import site uses; the contract, billing and
│   │                    organisation sections live in models_contracts.py,
│   │                    models_billing.py and models_organisations.py and are
│   │                    re-exported from here
│   ├── exceptions.py    DomainException hierarchy → unified envelope
│   ├── services.py      TimerService, ProjectService, BeatService, and the project
│   │                    guards the rest share
│   ├── contract_service.py ContractService: a day job read against its contract, its
│   │                    absences and its balance adjustments
│   ├── contracts.py     Work-contract arithmetic: term in force, expected hours, balance adjustments, and one running pass for the balance, its terms and the closes
│   ├── ledger.py        Pure assembly of the project page's weeks (goal, expectation, closing balance and its move, adjustments)
│   ├── vacation.py      Vacation arithmetic: a year of the entitlement from its dated opening, the carry-over, what a day off costs
│   ├── timesheet.py     Pure assembly of a day job's month: a row per finished day, brought and carried forward, off the ledger's one pass
│   ├── billing.py       Pure billing arithmetic: rate and flag resolution, lines as runs of days, Decimal half-up per line, the closed-past check (`past_change`)
│   ├── billing_budgets.py Pure billing budget arithmetic: the current period, spend summed month by month over `assemble_client`, the integer state, a running timer's crossing instants, the guarded projection
│   ├── billing_service.py BillingService: clients, project billing, billable overrides, billing budgets and report links, their write-time rules, the month report, one client's range for a link (`client_period`), the budgets' reading, the backup's dry run
│   ├── currencies.py    The ISO 4217 table: the one source of a currency's minor units
│   ├── organisations.py OrganisationService: membership, roles, invites and requests, the organisation's projects and assignments, connecting a project, leaving, and who may read the record
│   ├── organisation_record.py The record and archive shapes, and the two assemblies that fill them — given the store and the record reader, not a service
│   ├── employment.py    EmploymentService (extends OrganisationService): managed contracts, absence requests, timesheets with the frozen month and its lock, admin-entered time, teams and manager scope, the audit read, the record and compliance CSVs
│   ├── holidays.py      The only importer of the `holidays` package: calendars, regions, and a contract's holiday set (`contract_calendar`, `contract_holidays`)
│   ├── analytics.py     Heatmap, daily rhythm, untracked gaps
│   ├── flow.py          Pure aggregation over the daemon's flow windows, for the coach
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
│   ├── migrations.py    Startup passes: a project without `kind` gets one (a day job its
│   │                    contract too); a day job whose term governs loses `weekly_goal`;
│   │                    an assignment made by a connect gets the `private_before` that says
│   │                    what the member kept back; a pairing code stored with string dates
│   │                    gets BSON dates, or goes if expired
│   ├── plan_migration.py Startup pass: weekly plans stored under a Sunday move to their Monday
│   ├── organisations.py MongoOrganisationStore — the organisation's own collections, scoped by organisation, never by user_id
│   ├── organisation_records.py MongoOrganisationRecords — its read of beats and absences by its stamp, the other class not scoped by user_id
│   ├── erasure.py       Erase an account, keeping each organisation's working-time record under a tombstone
│   ├── repositories.py  MongoStore, the serializers and the one-model repositories
│   ├── project_repositories.py Beats, projects and the approved month's lock; MongoProjectRepository merges a member's assignments in
│   ├── contract_repositories.py Absences and balance adjustments
│   ├── billing_repositories.py Clients, project billing, overrides, budgets, report links
│   └── signal_repositories.py Flow windows, signal summaries, pending suggestions, biometrics
├── settings.py   pydantic-settings (reads .env / env vars)
├── auth/         WebAuthn + JWT sessions; OpenID Connect sign-in (oidc.py, sso_accounts.py)
└── server.py     FastAPI app + lifespan (in src/, not src/beats/)
```

## Running

```bash
just run-locally        # uvicorn --reload on :7999
uv run --group dev pytest src/ -v   # Tests (auto-starts MongoDB via testcontainers)
```

## Testing

Fifty-four test files cover different layers; the full run takes about 30
seconds, and the root CLAUDE.md carries the count. Four of them were carved
into the rest on 2026-11-06 at the size ceiling in roadmaps/file-sizes.md
(`test_api.py`, `test_domain.py`, `test_coach.py`, `test_organisations.py`),
and what they shared went to four modules that are deliberately **not**
`test_`-prefixed, so pytest does not collect them and no suite imports
another: `src/api_helpers.py`, `src/organisation_helpers.py`,
`src/beats/domain_fakes.py`, `src/beats/coach_fakes.py` and
`src/beats/auth_fakes.py`. Add a shared fixture there, never to a sibling
suite.

- **`src/test_api.py` and `src/test_api_*.py`** — HTTP integration tests against real MongoDB (testcontainers), one file per router area: projects, contracts, the ledger and what the project page reads off it, billing, report links (`test_api_reports.py` — the public read with no Authorization header, and the four assertions that a link cannot reach another client, a personal project, an internal id or a running timer), beats and the timer, the coach, intelligence, export and backup, accounts and auth, devices, signals, the daemon's suggestions, integrations and SSO. `test_api.py` itself keeps what belongs to no one router: the error envelope, what a stop names, the idempotency replay, two accounts' isolation.
- **`src/test_account_controls.py`** — account controls over HTTP (docs/account-controls.md): suspension on both credential branches and at the pairing and report-link doors, sign-out everywhere against `auth_time`, the two last-seen stamps, and the per-account limits. Shares `test_api.py`'s harness and billing helpers; the SSO door's suspension test stays with `TestSSOAPI`.
- **`src/test_operator.py`** — the operator deployment's contract (docs/backoffice.md): the fresh-interpreter isolation pins (no `beats.settings` in the operator root; no operator router in `server`), the allowlist and Origin lines, **the wall** (a sentinel in every right-column thing, grepped out of every page), and the IAP verifier with a test that fails each of Google's checks on purpose. The operator env and the `operator_client` fixture are `conftest.py`'s.
- **`src/test_operator_commands.py`** — the commands and the job queue: the runner's gates (confirmation, role, 404 at queue time for a mistyped subject), the organisation acts behind `ORGANISATION_HAS_OWNER`, and the erasure window's consistency rules (one queued job per subject, no unsuspend around it, a failed queueing leaves nothing standing, the sweep spares the operator's own records).
- **`src/test_organisations.py`** — the organisations contract (docs/organisations.md), same harness: the lifecycle, an organisation's project on a member's own routes, the record and the member's view of it, and the wall (`TestOrganisationWall`).
- **`src/test_organisations_projects.py`** — an organisation's projects over their life: connecting from a day, merging, leaving and removal with the archive, erasure, and what a backup carries.
- **`src/test_organisations_closing.py`** — closing and deleting an organisation (#347), the retention purge, and the project index's plan.
- **`src/test_employment.py`** — employment (stages 3–4): managed contracts and the member's refused writes, absence requests end to end, timesheets (submit, approve-and-freeze, the lock on every write path, changes requested, reopen, the running-timer refusal), teams with manager scope, the viewer, the compliance CSV's breaks, the audit read and admin-entered time.
- **`src/beats/test_models.py`, `test_analytics.py`, `test_intelligence.py`, `test_planning.py`, `test_focus.py`, `test_services.py`, `test_project_service.py`, `test_project_aggregations.py`, `test_health_integrations.py`, `test_dev_integrations.py`** — pure-Python domain tests, one file per domain module under test, over the in-memory fakes in `domain_fakes.py`. `test_services.py` also holds the one timer stop against the real beat repository, for a write that lands while the stop reads the flow windows.
- **`src/beats/test_contracts.py`** — the work-contract arithmetic on its interesting inputs, balance adjustments among them, plus one round trip through the absence repository.
- **`src/beats/test_ledger.py`** — the ledger assembly on fixed dates: a term change, a vacation week, `ended_on`, balance adjustments and a settlement, the row-to-row balance proof.
- **`src/beats/test_compliance.py`** — the compliance warnings on their boundaries, over synthetic records: exactly ten hours or eleven hours' rest is lawful, the day and the night between are the person's across projects, the first day read has no rest to judge, a day can carry both warnings. The CSV's shape stays in `test_organisations.py`.
- **`src/beats/test_timesheet.py`** — the monthly timesheet on fixed dates: four months worked out by hand (a mid-month start and term change, weekend work, a vacation week, a half day, a payout, Easter), the month-to-month and row-to-row proofs, the range's clipping, the null rule under an objective term.
- **`src/beats/test_billing.py`** — the billing arithmetic on fixed dates: rate and flag resolution at both levels, lines as runs of days, bucketing by the local start day across midnight, month ends and DST, the running timer and a beat that ends before it starts, half-up rounding in JPY, EUR and KWD, totals that are sums of lines, who a report lists, the closed-past check, and the term lists' validators.
- **`src/beats/test_billing_budgets.py`** — the billing budget arithmetic on fixed dates: a run across a month boundary summed month by month (2.02 h, not 2.01), the monthly reading equal to the month report, project beside client scope, overrides, a late beat in Berlin, the integer thresholds and the floored percent, unpriced hours under a money budget, an upcoming total, a running timer's crossing instants (a rate change at midnight, an override of false, two timers, a DST night), every projection guard and the 28-day window, and the model's unit, period and warning rules.
- **`src/beats/test_vacation.py`** — the vacation arithmetic on fixed dates: the opening on a contract started years before it, each carry-over rule, the end year's pro-rating and rounding, which days cost leave.
- **`src/beats/test_migration.py`** — the startup passes: the one that gives every project a `kind` and derives a day job's contract from its goal history, the one that then clears the personal goal the contract replaced, the one that moves weekly plans stored under a Sunday to their Monday, and the one that gives pairing codes stored with string dates the BSON dates their TTL index expires.
- **`src/beats/test_coach*.py`** — the coach against scripted Anthropic responses, by surface: usage and cost (`test_coach.py`), the gateway in the round, briefs, memory, the chat loop, the tool dispatch, the context builders and the day context — over `coach_fakes.py`.
- **`src/beats/test_auth.py`** — the session manager (`auth_time` included), token revocation and the challenge slots.
- **`src/beats/test_webauthn.py`** — `WebAuthnManager`, the second passkey on a signed-in account, the Mongo credential storage, and the `JWT_SECRET` and `FORWARDED_ALLOW_IPS` validators. Both over `auth_fakes.py`.
- **`src/beats/test_accounts.py`** — the account auth-state cache's safety properties and the account service's rules, the erasure wording among them.
- **`src/beats/test_sso.py`** — OpenID Connect sign-in against `src/fake_idp.py` (a scripted provider, real RS256 tokens) and the account rules.
- **`src/beats/test_middleware.py`** — idempotency middleware, no DB.
- **`src/beats/test_device_access.py`** — the device-verdict cache.

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
- Auth: All endpoints require JWT Bearer token (WebAuthn sessions). Public paths: `/api/auth/*`, `/health`, `/api/device/pair/exchange` (the daemon's pairing-code redemption — unauthenticated by design, rate-limited at 10/min), and `/api/reports` (a report link, read by a client with no account — the token, sent in `X-Report-Token` and never in the URL that Cloud Run logs, is the whole authorisation, rate-limited at 30/min; it is the only public path that serves a user's data, and `routers/reports.py` opens with the rules that let it)
- Rate limits (slowapi, `limiter` in `routers/auth.py`) key on `request.client.host`, which `ProxyHeadersMiddleware` (outermost in `src/server.py`) sets to the right-most `X-Forwarded-For` entry not written by a proxy `FORWARDED_ALLOW_IPS` names — required, no `*`, checked in `settings.py`. Every launch command passes `--no-proxy-headers`, so uvicorn's own copy stays out of it. In tests, `TestClient(app, client=("169.254.169.126", 443))` stands behind Cloud Run's front end (`TestRateLimiting`). The counts are per instance, which is a decision recorded beside the limiter, not an oversight.
- Device tokens (daemon, wall-clock) are a separate JWT type; the auth middleware allows them only on paths in `DEVICE_ALLOWED_PREFIXES`, plus GET/HEAD on `DEVICE_READ_ONLY_PREFIXES` (see `device_may_reach` in `src/server.py`). Adding a new daemon-reachable path means appending to one of those tuples — the read-only one when the prefix also carries writes a device shouldn't make (as `/api/coach/memory` carries delete and rewrite).
- Error envelope: every non-2xx response carries `{detail, code, fields?}`. Routers can override the auto-mapped code by raising `HTTPException(detail={"code": "X", "message": "..."})` — see `coach.py` and `auth.py` for examples.
- Multi-user: Each user's data is scoped via `user_id` field on all collections. Repos accept `user_id` in constructor. The exceptions are named: `MongoProjectRepository` also reads the organisation projects the user is assigned to (`project_repository_for`), and `infrastructure/organisations.py` is scoped by organisation, never by user — every route under `/api/organisations` resolves the caller's membership first.
- Passkeys: `/api/auth/register/*` is the sign-up door and 409s for an email that
  already has one — matching an existing account by email is how one would be taken
  over. An account that wants a second passkey uses `POST /api/account/credentials/start`
  and `/verify` instead: the same ceremony behind a session, so the account is the
  token's, the challenge sits in its own slot, and no second token is issued.
- `auth_info` fixture in conftest.py creates a test user + JWT for integration tests
- The `date` type from `datetime` is imported as `date_type` to avoid Pydantic field-name clashes

## Linting

```bash
uv run --group dev ruff check       # Lint
uv run --group dev ruff format      # Format
uv run --group dev ty check         # Type check (ty has suppressed warnings for PyMongo/Pydantic)
```
