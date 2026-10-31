# The control plane

The operator's UI for **running the platform**. Issue **#424**.

LifePete has one operator — PRIVACY.md says so in those words — and no place
to run it from. Every operator act today is a script in `api/scripts/` fired
by hand at production, every limit is a constant that needs a redeploy to
change, and everything an operator should *notice* is noticed only by going
to look.

Split out of [roadmaps/organisations.md](organisations.md) on 2026-10-31,
designed on 2026-11-01 and re-architected the same day after a review of the
codebase against it (§ *Architecture*). It was filed under that epic because
an organisation left without an owner (decision 31) was the first thing
anyone wanted to see; a control plane is not an organisations feature.

---

## What it is, and what it is not

**A control plane: pages organised around what the operator is trying to do.**
Find the account a support mail came from and act on it. Fix an organisation
whose owner is gone. Find who is burning the coach budget and cap them. See
whether storage growth is about to cost money.

**Not a Django admin** — one page per collection with a CRUD form. That makes
the operator translate every real question into four screens of joins, and
makes the dangerous act (edit this document) the easiest one on the page.

**Not a dashboard either.** Statistics are in it because they serve two
operator jobs — predicting what the platform will cost and how it will behave
next quarter, and catching use that has turned into abuse — not because a wall
of charts is the goal.

## The line: operational metadata, never user content

The operator's job never requires reading what someone tracked. So:

| Sees | Never sees |
|---|---|
| Account id, email, created, last active, state | Sessions, their times, their notes |
| Counts: projects, sessions, devices, organisations | Project names, tags, absence notes |
| Which integrations are connected | Any integration's token or fetched content |
| Coach spend, tokens, model | Any coach conversation or memory |
| Organisation name, settings, members, roles, seats | Clients, rates, amounts, report contents |
| Biometric *row counts* | Any biometric value |

The operator can still read any document in Mongo, and PRIVACY.md says so
rather than pretending otherwise. That is why the line is worth drawing:
**every question the control plane answers is a `mongosh` session against
production that does not happen.** The wide credential stops being the
everyday tool, which is also what makes a second operator safe to add later.

## The finding that shapes the work

**A control plane can only control what the API enforces, and today the API
enforces almost none of it.** Checked 2026-11-01:

| The operator wants to | What exists now | What the API must grow |
|---|---|---|
| Suspend an abusive account | **Nothing** — no field on `User`, no check anywhere | `suspended_at` / `suspended_by` / `reason` on `User`; one check in the auth middleware, cached the way `device_access` already caches a device's revocation |
| Sign someone out everywhere | `SessionManager._revoked_tokens`, an **in-memory dict per instance** | `sessions_valid_after` on `User`: a token whose `iat` is older is refused. One field, one middleware check, no token list to share |
| Cap one account's coach spend | `settings.coach_monthly_budget_usd`, **one global number** | An `account_limits` document the budget check reads before the global |
| Rate-limit one abuser | `@limiter.limit` constants keyed on IP, per instance | Per-account ceilings from the same document, at the write routes that matter (import, signals, beats) |
| Disable a webhook | `Webhook.active` **already exists** | Nothing |

Most of the value is unlocked by those small enforcement points, and they
are API work whichever way the back office is built. Build them first: a
control plane whose controls do nothing is a viewer with buttons.

On revocation, be accurate about severity: `SESSION_TTL` is 3600, so a
revoked token dies within the hour anyway. The real gap is that
`refresh_token` mints a fresh hour on every call, so a session in active use
renews indefinitely while only one instance knows it was revoked. **This is
worth an issue of its own, control plane or not**: the user's own logout is
weaker than it looks.

## Architecture

### The question: one service, or two?

Two shapes were on the table, and the codebase review decided it.

**A. A separate full-stack service.** Its own FastAPI app, server-rendered,
reading Mongo with its own credential, sharing no code with the API. (The
first draft of this file.)

**B. Operator endpoints in the existing API, plus a UI-only service.** The
owner's proposal: one API codebase, one domain layer; the back office is a
front end over `/api/operator/*`.

| | A — separate service | B — one API, UI service |
|---|---|---|
| Domain logic | **Reimplemented.** "Grant the owner role" has a last-owner guard, an audit write and a role rule, all already in `OrganisationService`; A writes them again, with no shared code | **One implementation.** An operator method on the service that already has them, auditing through the existing `_audit` |
| Enforcement points | Live in the API regardless; A writes the flag from one codebase and checks it from another | Written and checked in one place, one model, one test |
| Tests | A new harness, plus a cross-repo fixture dance to catch schema drift | `test_api.py`'s harness: testcontainers, real Mongo, the HTTP contract, 1473 tests already keeping the invariants |
| Schema coupling | The weak point: a renamed field silently empties a page | None — same models |
| Migrations, settings, error envelope | Duplicated or diverged | Shared |
| Public reachability of privileged routes | **None** — no public ingress at all | Mounted in the public app unless something prevents it (see below) |
| Credential boundary | A narrow DB user | The API's own credential — unless the deployment is split (see below) |

The left column's one real advantage is isolation. The right column wins
everything else, and the repo's own rule — *rules implemented more than
once* are the ones that drift — weighs against A hard: a control plane is
mostly the API's own rules exercised by a different person.

**Verdict: B, with one refinement that keeps A's isolation: one API codebase,
deployed twice.**

### Why the scoping worry was overstated

The first draft kept the back office out of the API to protect its "every
query is scoped by `user_id`" invariant. On review that invariant is already
narrower than stated: `MongoOrganisationRecords`, `MongoReportLinkLookup`,
`MongoPeriodLocks._zone_of`, the whole of `infrastructure/organisations.py`
("scoped by organisation, never by user"), `erasure.py`, `retention.py` and
`migrations.py` all cross users, inside the API, today. The rule was never
"nothing crosses"; it is **"what crosses is a named, narrow class, never a
widening of `MongoStore._q`."** An operator reader obeys that rule as
naturally as the record does.

### One API codebase, deployed twice

A single `BEATS_ROLE` setting decides which routers `server.py` mounts:

- **`BEATS_ROLE=api`** — today's deployment, exactly as it is. The operator
  router is **not mounted**: the public app has no `/api/operator` routes to
  guard, so no bug in operator auth is reachable from the internet.
- **`BEATS_ROLE=operator`** — a second Cloud Run service from the **same
  image**, mounting the operator router (and, for its own health checks,
  nothing else of the user-facing API). No public ingress; IAP in front.
- **`BEATS_ROLE=job`** — Cloud Run Jobs from the same image for the wide,
  irreversible work (below).

This is cheap — one `google_cloud_run_service` more in `terraform/`, one
env var — and it buys back everything column A had:

- **No privileged route is public.** This matters more than it looks because
  of the middleware's current shape: a *session* token passes **every path**
  (the dispatch validates it and returns `call_next` with no path check;
  only *device* tokens are allowlisted through `device_may_reach`). Mounting
  operator routes in the public app would need a new *negative* rule for
  sessions in a middleware whose pattern is positive allowlists. Not mounting
  them needs nothing.
- **The credential boundary survives.** The operator deployment reads its
  `DB_DSN` from its own secret — a database user that reads what it shows
  and writes only `users`, `org_members`, `organisations`, `webhooks`,
  `account_limits` and `operator_audit`, with **no write grant on any content
  collection**. Same image, narrower key.
- **One domain layer, one test suite, one migration pass.** The operator
  service is a module in `api/src/beats/domain/`, tested in
  `api/src/test_operator.py` against the same real Mongo as everything else.

### The UI service: `backoffice/`

A **React 19 SPA**, built with the toolchain `ui/` already runs — React 19.3,
TypeScript 7, Vite 8, Tailwind 4, TanStack Query 5, Zod 4, react-router 8,
Biome — because that *is* the latest stack and the team already owns it. The
first draft proposed Jinja2 and htmx for simplicity; against an existing
toolchain that is a step backwards and a second idiom to maintain, not a
saving. It follows `ui/`'s Feature-Sliced layout (`app/ pages/ widgets/
entities/ shared/`), and generates its API types with the same
`openapi-typescript` step, pointed at the operator deployment's OpenAPI
document.

Self-contained, with its own `package.json` and config, the way
`integrations/vscode-beats` already is — `ui/`'s pnpm workspace is rooted at
`ui/` and only reaches `tools/*`, so a sibling surface cannot join it without
re-rooting the workspace, which is not worth doing for this. Shared code with
`ui/` is nothing at first; the API client pattern (`get`, `parseApiResponse`,
the Zod schemas) is small enough to copy once and let diverge.

Deliberately **not the sky**: no `SkyBackdrop`, no two hours, a denser, plainer
look. An operator should never mistake which surface they are on.

Served as static files from a tiny Cloud Run service behind the same IAP as
the operator API, so one sign-in covers both.

### Authentication, end to end

- **Google IAP** in front of both the UI and the operator deployment. Cloud
  Run has had a built-in IAP option since 2025 that needs no load balancer
  — which removes the standing LB cost that was the first draft's biggest
  objection. *Verify it is GA in the deployment's region before relying on
  it*; if not, the load balancer is the fallback.
- The browser's requests to `/api/operator/*` carry IAP's signed assertion
  (`x-goog-iap-jwt-assertion`). The operator deployment **verifies that JWT**
  — issuer, audience, signature — and checks the asserted email against an
  **operator allowlist** in settings, with a role beside each: `viewer` or
  `operator`. Two roles from day one, so a contractor can look without acting.
- A third token type in the middleware, `operator`, resolved from the IAP
  assertion and nothing else: **a user session JWT is refused on the operator
  deployment**, which is trivially true because that deployment never issues
  or accepts one. Who may enter is an IAM policy plus an allowlist; the
  service implements no login, session, passkey or password.
- Locally, `BACKOFFICE_DEV_OPERATOR=<email>` stands in for the assertion, the
  way `BEATS_TEST_ENV` stands in for testcontainers.

### Jobs for the wide and irreversible work

Erasure and the retention purge touch every collection and cannot be undone.
They are not buttons in a request handler.

The operator deployment **enqueues** (a row in `operator_jobs`: what, who,
when, a cancellation deadline); a **Cloud Run Job** from the same image with
`BEATS_ROLE=job` and the wide credential executes, running the same
`infrastructure/erasure.py` and `infrastructure/retention.py` the scripts
call today. Three things come free: the operator deployment's grant stays
narrow, the act is auditable at both ends, and an irreversible act sits in a
cancellation window before it runs. Cloud Scheduler triggers the job on a
short cadence to pick up due work — the same mechanism
[server-push.md](server-push.md) needs, for the same Cloud Run reason: there
is no always-on process to wait in.

### Audit, in two places

Every operator action writes an append-only `operator_audit` row — who, what,
when, before and after. **And an action that touches an organisation also
writes to that organisation's `org_audit`** through the existing `_audit`,
which its admins already read: an operator granting someone the owner role is
visible to the people it affects. The product's own value, applied to its
operator.

Reads and page views go to **Cloud Logging** as structured logs, which is
where Cloud Run already keeps every request URL. (The same URL logging is why
`/api/reports` keeps its token in a header; here the logging is the point.)

### What is deliberately not here

No message broker, no separate analytics store, no GraphQL layer, no tracing
collector. The scale is one operator and a few dozen queries; every one of
those would be a system to run for no question it answers better than an
aggregation pipeline and a Cloud Run Job.

## Fit with the codebase

What the review found, and where each piece goes so it reads like the rest.

**API — `api/src/beats/`**

| Piece | Where | In the shape of |
|---|---|---|
| `User.suspended_at/by/reason`, `User.sessions_valid_after`, `AccountLimits`, `OperatorAuditEvent`, `OperatorJob` | `domain/models.py` | `OrgAuditEvent`, `DeviceRegistration` |
| `OperatorReads` (counts, overviews, outliers — returns aggregates, never a document) and `OperatorStore` (the narrow writes) | `domain/ports.py` | `OrganisationRecords`, `PeriodLocks` — narrow Protocols, so the service that reads cannot quietly write |
| `OperatorService` — composes `OrganisationService` for the owner grant, `UsageTracker` for spend, the ports for the rest | `domain/operator.py` | `EmploymentService` extending `OrganisationService` |
| `MongoOperatorReads`, `MongoOperatorStore` | `infrastructure/operator.py` | `MongoOrganisationRecords` — the named cross-tenant class, never a widened `_q` |
| The router, `/api/operator/*`, mounted only under `BEATS_ROLE=operator` | `api/routers/operator.py` | `routers/employment.py`; same error envelope |
| The IAP assertion → `operator` token type; the suspension and `sessions_valid_after` checks for session tokens | `src/server.py` middleware | the device branch: cached lookup, `DEVICE_REVOKED`-style codes |
| `BEATS_ROLE`, the operator allowlist, the IAP audience | `settings.py` | pydantic-settings, env-overridable |
| The per-account ceiling read before the global | `coach/usage.py` `enforce_budget` | its own existing shape |
| `test_operator.py`: the HTTP contract, and the wall — a sentinel note, tag, project name and biometric value appear in **no byte** of any operator response | `api/src/` | `TestOrganisationWall` |

The wall test is the one that matters most. It is how "never user content"
stops being a sentence in a roadmap and becomes something CI refuses.

**UI — `backoffice/`**: `app/` (router, the IAP-aware API client), `pages/`
(attention, accounts, organisations, abuse, capacity, compliance, audit),
`entities/` (account, organisation, limits, job — each a Zod schema, a
mapper, hooks under one query root), `shared/` (api client, ui primitives).
Its own `biome.json`, `tsconfig`, `vite.config.ts`; `pnpm test` with Vitest;
types from `openapi-typescript` against the operator OpenAPI document,
`--check`ed in CI like `ui/`'s.

**Infrastructure — `terraform/`**: a second `google_cloud_run_service`
(`beats_operator`) and a third for the static UI, both with IAP and no
`allUsers` invoker; a `google_cloud_run_v2_job` for `BEATS_ROLE=job` with a
Cloud Scheduler trigger; a second Mongo user and a second `DB_DSN` secret;
IAM for the operator allowlist. Same image, same Cloud Build, same deploy
lock.

**CLAUDE.md** gains `backoffice/` in the layout table and `/api/operator` in
the routes table when it ships — not before.

## What it does, by the job it serves

### 1. Attention — the landing page

The reason to open it. Each row a count, linking to the thing.

- **Organisations with no owner** (decision 31). Owner-only acts wait until
  someone notices, and the only trace today is an `account.erased` line in
  that organisation's audit log.
- **Erasure requests waiting**, and queued erasures inside their window.
- **What a retention purge would take**, per organisation. The script is dry
  by default and nothing schedules it (decision 30); nobody is reminded.
- **Accounts over a limit**: coach spend near or past the cap; storage or
  write-rate outliers.
- **Approvals superseded and never reopened** (`superseded_at`, decision 23):
  one standing for months means a decider never saw the mark.
- **Absence requests pending beyond a threshold.**
- **Deploy state**: the live commit, and whether `beats/deploy.lock` is held.

### 2. Accounts

Found by **exact email or id** — not a browsable list, not a prefix search.
The common entry is a support or erasure mail carrying a full address;
exact-match serves that and is useless for fishing.

One account: created, last active, suspension state, passkeys and linked
providers, devices, organisations and roles, counts of projects / sessions /
biometric rows, storage estimate, coach spend against its cap, integrations
connected.

**Actions**: suspend and unsuspend; set or clear a limits override; sign out
everywhere; queue an erasure (typed confirmation, cancellation window);
generate a subject-access export.

On **sign-in doors**: identities per provider is a fact the account *stores*
and fair to show. It is **not** a record of which door a sign-in used, which
the code deliberately does not keep. Do not let one grow into the other.

### 3. Organisations

A list: name, created, members by role, active assignments, **seat count**
([docs/pricing.md](../docs/pricing.md) defines it; [subscriptions.md](subscriptions.md)
bills on it), free-tier position, retention years, closing state. One
organisation adds memberships with roles and dates, projects and how many
were connected, timesheets by status, and its audit log.

**Actions**: grant the owner role to an existing admin — decision 31 refuses
to auto-promote but leaves somebody having to act, and this is where; start or
extend a closing notice; delete after it; later, adjust a plan or seat
allowance.

### 4. Abuse and limits

**Detection**, by outlier rather than guessed threshold: coach spend per
account; flow windows per account per day (the daemon is the heaviest writer
— 100× the median is a broken or hostile one); sessions and projects created
per day and import sizes; **report links minted per account** (`/api/reports`
is the only public path serving a user's data); **webhook destinations by
domain** (outbound HTTP from our servers to arbitrary URLs is ours to answer
for); pairing codes and devices per account; signups per day and provider.

**Controls**: `account_limits` overrides read at the API's enforcement
points; suspension; disabling one webhook.

### 5. Capacity and cost

Documents and storage per collection with growth; write volume per day by
kind; distributions as percentiles rather than lists; **coach cost** from
`llm_usage` (`UsageTracker.usage_summary` already calls itself "for the cost
dashboard") as a platform total by day and model, with the cache-hit ratio.
**Latency, error rates and instance counts are Cloud Monitoring's** — link,
do not rebuild.

### 6. Compliance operations

The erasure queue; retention due per organisation and running it as a job; a
subject-access export; the operator audit, readable and filterable, editable
by nobody.

## What must not happen

- **No "view as this user", ever.** It contradicts PRIVACY.md directly and
  makes a product whose pitch is "we cannot watch you" false.
- **No user content**, per the table; no page, export or CSV carries a note,
  a tag, a project name or a figure from someone's record. The wall test
  enforces it.
- **No free-text search** over content, and none over addresses beyond the
  exact-match lookup.
- **No destructive act in a request handler.** Erasure and the purge are jobs
  with a typed confirmation and a cancellation window.
- **The operator router is never mounted under `BEATS_ROLE=api`.** That one
  line is the isolation; a test asserts the public app has no
  `/api/operator` route.
- **The operator deployment's database user has no write grant on content
  collections**, whatever the code claims to do.
- **Nothing silent inside an organisation.** An operator act that changes a
  membership lands in that organisation's own audit log.
- **Reads go through the named narrow classes** — never by widening
  `MongoStore._q`, never by handing an existing service a wider scope.
- **It does not become customer support** with a deeper tier of access
  because someone asked a question it cannot answer. That is a new decision
  with a new PRIVACY.md sentence, not a patch.

## Open, for when it starts

- **Order.** The enforcement points first — the suspension flag is smallest
  and unlocks most — then the operator deployment, then the UI.
- **Cloud Run built-in IAP**: confirm GA in the region; otherwise a load
  balancer, priced before committing.
- **PRIVACY.md** should say that an account can be suspended by the operator,
  and that operator actions are audited, before the first one ships.
- **Pre-computed aggregates.** Per-request pipelines are fine at this size
  and will not stay fine; a nightly roll-up is the first thing that will ask
  the operator deployment for a wider write grant, so decide it deliberately
  when it does.
