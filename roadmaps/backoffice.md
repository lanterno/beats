# The control plane

The operator's UI for **running the platform**. Issue **#424**.

LifePete has one operator — PRIVACY.md says so in those words — and no place
to run it from. Every operator act today is a script in `api/scripts/` fired
by hand at production, every limit is a constant that needs a redeploy to
change, and everything an operator should *notice* is noticed only by going
to look.

Split out of [roadmaps/organisations.md](organisations.md) on 2026-10-31,
designed on 2026-11-01, then twice revised the same day: once when the owner
asked whether one API could serve both (it can, § *Architecture*), and once
in a design review that found the first answer to that question broken (the
`lifespan` paragraph says how). It was filed under that epic because
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

**A. A separate full-stack service.** Its own FastAPI app, reading Mongo with
its own credential, sharing no code with the API. (This file's first draft.)

**B. Operator endpoints in the existing API, plus a UI-only service.** The
owner's proposal: one API codebase, one domain layer; the back office is a
front end over `/api/operator/*`.

| | A — separate service | B — one API, UI service |
|---|---|---|
| Domain logic | **Reimplemented.** "Grant the owner role" has a last-owner guard, an audit write and a role rule, all already in `OrganisationService` | **One implementation**, auditing through the existing `_audit` |
| Enforcement points | Live in the API regardless; A writes the flag from one codebase and checks it from another | Written and checked in one place, one model, one test |
| Tests | A new harness, plus a cross-repo fixture dance to catch schema drift | `test_api.py`'s harness: testcontainers, real Mongo, the HTTP contract |
| Schema coupling | The weak point: a renamed field silently empties a page | None — same models |
| Migrations, settings, error envelope | Duplicated or diverged | Shared |
| Privileged routes reachable publicly | **No** | Only if the public app mounts them |
| Credential boundary | A narrow DB user | The API's own — unless deployed separately |

A's one real advantage is isolation. B wins everything else, and the repo's
own rule — *rules implemented more than once* are the ones that drift —
weighs against A hard: a control plane is mostly the API's own rules
exercised by a different person.

**Verdict: B, with a refinement that keeps A's isolation — one codebase, two
composition roots, deployed separately.**

### Two composition roots, not a mode switch

The obvious way to do B is an env var that decides which routers mount. **It
does not survive contact with `lifespan`.** Today's lifespan runs five
startup passes and builds the index set: `migrate_project_kinds`,
`clear_personal_goal_on_day_jobs`, `move_sunday_plans_to_monday`,
`mark_connected_assignments`, `date_pairing_codes`, `ensure_mutation_log_indexes`.
An operator deployment booting that would either fail on its narrow
credential or — worse — race the API's own startup passes. A switch that
gates routers but shares a lifespan is broken, and one that gates the
lifespan too has become an app factory wearing a disguise.

So: **a second composition root in the same package.**

```
api/src/server.py            BEATS the API         → uvicorn server:app
api/src/operator_server.py   the operator API      → uvicorn operator_server:app
api/src/beats/               the library both compose
```

Same image, same `pyproject.toml`, same tests; the Cloud Run service's
command picks the module. What that buys over a flag:

- **The public app cannot serve an operator route**, because it does not
  import one. Not "a test asserts it is not mounted" — it is not reachable
  by construction. (A cheap test still pins it, against the day somebody
  adds the import.)
- **Each lifespan is honest.** `operator_server`'s connects the database and
  stops: no migrations, no index building, nothing that needs a write grant
  on collections it must not touch.
- **No third mode for jobs.** `BEATS_ROLE=job` was the same mistake again;
  a Cloud Run Job runs `python -m beats.operator.jobs`, an entry point, not
  an app in a costume.
- **Middleware differs where it must.** Two roots means two middleware
  stacks: the operator app's resolves an IAP assertion and nothing else,
  rather than one dispatch carrying a branch for a caller it will never see
  in production.

### The one invariant this protects

`request.state.user_id` is what every user-scoped dependency reads. **The
operator app never sets it.** It sets `request.state.operator` instead.

So if a user-scoped repository or router were ever imported into the
operator app by mistake, it does not quietly scope to the operator — it
fails, loudly, on a missing attribute. Fail-closed by construction, which is
the same instinct as `MongoStore._q` stamping a filter nobody can forget.

### Queries and commands are different shapes

The operator surface is read-heavy with a handful of commands, and the two
deserve different treatment. Giving both to one `OperatorService` would
grow the god-object this design is otherwise avoiding.

**Queries — no service layer.** "Accounts created per day", "organisations
with no owner", "flow windows per account" are aggregation pipelines. There
is no rule to enforce and nothing to decide, so a domain service in front of
them would be a pass-through. They live in
`infrastructure/operator_reads.py`, return frozen dataclasses, and the
router calls them through an `OperatorReads` Protocol so a test can fake
them. The repo's narrow-port convention is kept; the empty service is not.

**Commands — delegate, never reimplement.** Each command belongs to whatever
already owns the rule:

| Command | Owned by |
|---|---|
| Grant the owner role | `OrganisationService` — the last-owner guard (decisions 10, 20) and the audit write are already there |
| Start or extend a closing notice | `OrganisationService.start_closing` |
| Suspend, unsuspend, sign out everywhere | A new account service — these are account rules, and they belong with the account, not with the operator who happens to invoke them |
| Set or clear a limit | The same |
| Disable a webhook | The webhook repository; `Webhook.active` exists |
| Queue an erasure or a purge | Enqueued, never executed inline (below) |

`OperatorService` is then **a coordinator, not a domain**: resolve the
operator, authorise the role, write the audit, delegate. If a rule ever
starts living in it, that is the signal it was put in the wrong place.

### Commands are objects, so the audit cannot be forgotten

An audit that each handler must remember to write is an audit that will be
missing from the one action anybody cares about. So a mutation is not a
function call in a route — it is a small object:

```
class OperatorCommand(Protocol):
    name: str                      # "organisation.grant_owner"
    wide: bool                     # execute inline, or enqueue as a job
    confirmation: str | None       # what the operator must type back
    def describe(self) -> dict     # subject + before, for the audit
    async def execute(self, ctx) -> dict   # … and after
```

One runner executes them: check the role, check the typed confirmation,
call `describe()`, run, write `operator_audit` with before and after, and —
where a subject is an organisation — write that organisation's own
`org_audit` too. Four properties fall out of one place rather than ten:

1. **Nothing is unaudited**; the runner is the only path.
2. **Destructive work routes itself.** `wide = True` enqueues instead of
   executing, so erasure and the retention purge cannot accidentally run in
   a request handler holding the wrong credential. A queued job is just a
   serialised command — one abstraction, not two mechanisms.
3. **Confirmation is declared, not remembered** per handler.
4. **The job runner is trivial**: load the command, run the same runner.

Ten or so commands justify this; a hundred would justify more, and three
would not.

### Deployment, and the origin problem

Three Cloud Run services from two images:

| Service | Image | Command | Ingress |
|---|---|---|---|
| `beats-api` | API | `uvicorn server:app` | public (today, unchanged) |
| `beats-operator` | API, **same image** | `uvicorn operator_server:app` | internal, IAP |
| `beats-backoffice` | a static nginx/`distroless` image | serve `backoffice/dist` | internal, IAP |

plus a `google_cloud_run_v2_job` running `python -m beats.operator.jobs` on
a Cloud Scheduler trigger, with the wide credential.

**One origin for the browser.** This is where the first draft was wrong: it
proposed Cloud Run's built-in IAP (no load balancer) *and* two services. Two
services means two origins, which means CORS on a privileged surface and the
browser needing an IAP session per origin. Either:

- **(recommended) one IAP-protected load balancer with path routing** — `/`
  to the UI service, `/api/operator/*` to the operator API. One origin, one
  sign-in, no CORS, and the UI never learns the API's hostname. The LB has a
  standing cost, and it is the cost of doing this properly;
- **(fallback) serve `backoffice/dist` from the operator app** via
  `StaticFiles` and drop the UI *service* while keeping the UI *codebase*.
  One service, built-in IAP, no LB, no CORS. The separation the owner asked
  for is in the repo and the build, which is where it earns its keep;
  whether it is also a second Cloud Run service is a deployment detail.

Decide on cost. Do not ship two origins.

### Authentication

- **Google IAP** in front, at the load balancer. The operator app verifies
  the signed assertion (`x-goog-iap-jwt-assertion`) — issuer, audience,
  signature — and matches the asserted email against an allowlist in
  settings with a role beside each: `viewer` or `operator`. Two roles from
  day one, so a contractor can look without acting.
- The operator app **neither issues nor accepts a beats session JWT**. Not a
  rule to enforce: `SessionManager` is not in that composition root.
- Locally, `BACKOFFICE_DEV_OPERATOR=<email>` stands in for the assertion, as
  `BEATS_TEST_ENV` stands in for testcontainers.

### The enforcement points, and their cost

Suspension and `sessions_valid_after` are checked in the **public** API's
middleware, on every authenticated request. Done naively that is a Mongo
round-trip per request.

The answer is already in the codebase: `auth/device_access.py` caches a
device's revocation verdict for 30 seconds, process-local, with its reasoning
written out — the token signature and expiry are still checked every time;
only the flag lookup is skipped; revoking through the API drops the entry so
it takes effect at once, and the TTL only bounds staleness from a change made
directly in the database.

An account's auth state takes the same shape: **one cached lookup returning
both** `suspended` and `sessions_valid_after`, invalidated by the operator
command that changes either. One cache, one round trip, both features.

### What is deliberately not here

No message broker, no separate analytics store, no GraphQL layer, no tracing
collector, no event sourcing for the audit. The scale is one operator and a
few dozen queries; each of those is a system to run for no question it
answers better than an aggregation pipeline, an append-only collection and a
Cloud Run Job.

### Not in the self-hosted bundle

`compose.selfhost.yml` does not gain the operator app. IAP does not exist
outside GCP, a self-hoster already has the database, and shipping a
privileged surface with a different, weaker auth story to people running it
on their own box is how one ends up with a default credential on the
internet. If it is ever wanted there, that is a separate decision with its
own authentication design.

## Fit with the codebase

**API — `api/src/`**

| Piece | Where | In the shape of |
|---|---|---|
| The second composition root: its own `lifespan` (connect, and nothing else), its own middleware, the operator router | `operator_server.py` | `server.py`, minus everything it must not do |
| `User.suspended_at/by/reason`, `User.sessions_valid_after`, `AccountLimits`, `OperatorAuditEvent`, `OperatorJob` | `beats/domain/models.py` | `OrgAuditEvent`, `DeviceRegistration` |
| Account rules: suspend, unsuspend, sign out everywhere, limits | `beats/domain/accounts.py` | `ContractService` — rules with the thing they govern |
| `OperatorReads` (aggregates only) and `OperatorStore` (the narrow writes) | `beats/domain/ports.py` | `OrganisationRecords`, `PeriodLocks` |
| The command protocol, the runner, the commands | `beats/operator/` (`commands.py`, `runner.py`, `jobs.py`) | `beats/coach/` — a package for a surface, beside the domain it uses |
| `OperatorService`, the thin coordinator | `beats/domain/operator.py` | `EmploymentService` composing `OrganisationService` |
| `MongoOperatorReads`, `MongoOperatorStore` | `beats/infrastructure/operator_reads.py`, `operator_store.py` | `MongoOrganisationRecords` — the named cross-tenant class, never a widened `_q` |
| The router | `beats/api/routers/operator.py` | `routers/employment.py`; same error envelope |
| The IAP assertion → `request.state.operator` | `operator_server.py` middleware | the device branch, minus the user id |
| Suspension and `sessions_valid_after`, cached | `server.py` middleware + `auth/account_access.py` | `auth/device_access.py`, TTL and all |
| The operator allowlist, the IAP audience | `beats/settings.py` | pydantic-settings, env-overridable |
| The per-account ceiling, read before the global | `beats/coach/usage.py` | its own existing shape |
| `test_operator.py`: the HTTP contract against `operator_server`, and **the wall** — a sentinel note, tag, project name and biometric value in no byte of any operator response | `api/src/` | `TestOrganisationWall` |
| `scripts/dump_openapi_operator.py` → `backoffice/`'s types | `api/scripts/` | `dump_openapi.py`, which imports `server:app`; this one imports the other root |

The wall test matters most. It is how "never user content" stops being a
sentence in a roadmap and becomes something CI refuses.

**UI — `backoffice/`**: a React 19 SPA on the toolchain `ui/` already runs —
React 19.3, TypeScript 7, Vite 8, Tailwind 4, TanStack Query 5, Zod 4,
react-router 8, Biome — because that is the current stack and the team owns
it. (The first draft proposed Jinja2 and htmx; against an existing toolchain
that is a second idiom to maintain, not a saving.) Feature-Sliced like
`ui/`: `app/ pages/ widgets/ entities/ shared/`. Self-contained with its own
`package.json`, `biome.json` and `vite.config.ts`, the way
`integrations/vscode-beats` is — `ui/`'s pnpm workspace is rooted at `ui/`
and reaches only `tools/*`, so a sibling cannot join it without re-rooting,
which is not worth doing for this. Nothing is shared with `ui/` at first:
the API-client pattern is small enough to copy once and let diverge.

Deliberately **not the sky** — no `SkyBackdrop`, no two hours, a denser and
plainer look. An operator should never be unsure which surface they are on.

**Infrastructure — `terraform/`**: `beats_operator` and `beats_backoffice`
Cloud Run services (no `allUsers` invoker), a `google_cloud_run_v2_job` with
a Cloud Scheduler trigger, the IAP-protected load balancer with path
routing, a second Mongo user and `DB_DSN` secret, and IAM for the allowlist.
Same image for the operator service, same Cloud Build, same deploy lock.

**CLAUDE.md** gains `backoffice/` in the layout table, `/api/operator` in
the routes table, and a line in *Infrastructure* about the second
deployment — when it ships, not before.

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
- **`server.py` never imports the operator router.** That import, absent, is
  the isolation — not a flag, not a conditional. A test pins it for the day
  somebody adds one.
- **No rule lives in `OperatorService`.** It resolves, authorises, audits
  and delegates. A guard written there is a guard that will disagree with the
  one the member-facing route enforces.
- **No mutation outside the command runner**, or the audit becomes a thing
  people remember to write.
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

- **Order.** Four steps, each shippable and each useful alone:
  1. the enforcement points in the public API — suspension first, it is the
     smallest and unlocks the most, then `sessions_valid_after` and
     `account_limits`, with the cached auth-state lookup;
  2. `operator_server.py` with the queries only — a read-only control plane
     is already worth having, and it proves the composition root and the
     wall test before any command exists;
  3. the command runner and the commands, inline ones first;
  4. the job runner, and only then the irreversible work.
- **The origin decision**: an IAP-protected load balancer with path routing
  (one origin, a standing cost) against serving `backoffice/dist` from the
  operator app (one service, built-in IAP, no LB). Price both. Either is
  fine; two origins is not.
- **PRIVACY.md** should say that an account can be suspended by the operator,
  and that operator actions are audited, before the first one ships.
- **Pre-computed aggregates.** Per-request pipelines are fine at this size
  and will not stay fine; a nightly roll-up is the first thing that will ask
  the operator deployment for a wider write grant, so decide it deliberately
  when it does.
