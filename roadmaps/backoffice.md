# The control plane

The operator's UI for **running the platform**. Issue **#424**.

LifePete has one operator — "I … am the only operator", PRIVACY.md says — and
no place to run it from. Every operator act today is a script in
`api/scripts/` fired by hand at production, every limit is a constant that
needs a redeploy to change, and everything an operator should *notice* is
noticed only by going to look.

Split out of [roadmaps/organisations.md](organisations.md) and designed on
2026-10-31, then revised three times by the next day: once when the
owner asked whether one API could serve both (it can, § *Architecture*), once
in a design review that found the first answer to that question broken (the
`lifespan` paragraph says how), and once when every claim was checked against
the code, which found the second answer leaning on two things the code does
not do yet — connecting without building the index set, and importing the
settings without the session secret — and the organisation commands
delegating to methods that refuse a caller who is not a member. It was filed
under that epic because an organisation left without an owner (decision 31)
was the first thing anyone wanted to see; a control plane is not an
organisations feature.

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
| Account id, email, created, the day last seen, state | Sessions, their times, their notes |
| Counts: projects, sessions, devices, organisations | Project names, tags, absence notes |
| Which integrations are connected | Any integration's token or fetched content |
| Webhook destinations, by domain | A webhook's full URL, or what was sent to it |
| Coach spend, tokens, model | Any coach conversation or memory |
| Organisation name, settings, members, roles, seats | Clients, rates, amounts, report contents |
| An organisation's audit events: what, by whom, to whom, when | Their details — a reopen's reason, a project's or a team's name |
| Biometric *row counts* | Any biometric value |

"The day last seen" is a date the API does not keep yet (below). It is not
read off the newest session: that is a session's time, on the right of this
table.

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
| Suspend an abusive account | **Nothing** — no field on `User`, no check anywhere | `suspended_at` / `suspended_by` / `reason` on `User`; one check in the auth middleware **on both branches**, session and device, cached the way `device_access` already caches a device's revocation |
| Sign someone out everywhere | `SessionManager._revoked_tokens`, an **in-memory dict per instance** | `sessions_valid_after` on `User`: a session whose sign-in is older is refused — read off an `auth_time` claim that `refresh_token` copies unchanged, not off `iat`, which every refresh renews (§ *The enforcement points*). One field, one claim, one middleware check, no token list to share. Sessions only — devices are the next row |
| Stop one device — a broken daemon, a stolen laptop | `DeviceRegistration.revoked` **already exists**, and the middleware refuses a revoked device | Nothing; the operator invokes it |
| Cap one account's coach spend | `settings.coach_monthly_budget_usd`, **one global number** | An `account_limits` document the budget check reads before the global |
| Rate-limit one abuser | **Nothing** on the write routes that matter — import, signals, beats. `@limiter.limit`, keyed on IP and counted per instance, guards only the sign-in, session and credential routes, the pairing exchange and `/api/reports` | Per-account ceilings from the same document on those routes, the first limit they have, read through the account's cached lookup (§ *The enforcement points*). Still counted per instance, like the IP limits and by the same decision (#391; the reasoning is the comment above `limiter` in `beats/api/routers/auth.py`): the document sets the ceiling, not a shared counter |
| Disable a webhook | `Webhook.active` **already exists** | Nothing |
| See when an account was last used | `DeviceRegistration.last_seen`, a field nothing writes (`update_last_seen` has no caller); **nothing** on `User` | `last_seen_on` on `User`, a date, stamped at most once a day by the same cached lookup (§ *The enforcement points*) |

Most of the value is unlocked by those small enforcement points, and they
are API work whichever way the back office is built. Build them first: a
control plane whose controls do nothing is a viewer with buttons.

On revocation, be accurate about severity: `SESSION_TTL` is 3600, so a
revoked token dies within the hour anyway. The real gap is that
`refresh_token` mints a fresh hour on every call, so a session in active use
renews indefinitely while only one instance knows it was revoked. **This is
worth an issue of its own, control plane or not**: the user's own logout is
weaker than it looks.

Device tokens are the longer-lived credential, by design:
`validate_device_token` skips expiry, so a paired daemon's token is good
until its registration is revoked. That is why suspension is checked on the
device branch as well as the session branch — a suspended account whose
daemon still writes flow windows has not been suspended — and why signing
out everywhere, which ends sessions, leaves devices to their own row. The
two acts mean one thing each: sign-out ends sessions, revocation ends one
device, suspension ends both.

They are refused in different words, because the clients act on the
status. A session signed out everywhere is refused 401 `INVALID_TOKEN`,
exactly as an expired one is, so the SPA ends it and sends the browser to
sign in again (`apiErrorFrom`, `ui/client/shared/api/client.ts`). A
suspended account is refused 403 `ACCOUNT_SUSPENDED` in the error envelope,
on either branch, as a revoked device is refused 403 `DEVICE_REVOKED`; a 401
would sign the person out with the words for an expired session, which is
not what happened. Both are statuses the SPA's sync engine
(`RETRYABLE_STATUSES`, `ui/client/shared/lib/useSyncEngine.ts`) and the
companion's queue ([docs/companion-offline.md](../docs/companion-offline.md),
rule 7) keep a write for, and that is right here too: a write queued before
either act waits for the next sign-in or for the suspension to be lifted.
Do not add `ACCOUNT_SUSPENDED` to the codes a queue drops — suspension can
be undone, and dropping would make it delete the person's own writes.

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
| Domain logic | **Reimplemented.** "Grant the owner role" needs a membership check, a role rule and an audit write, all already in `OrganisationService` | **One implementation**: the operator's act is a method beside the member's, sharing its helpers and auditing through the existing `_audit` |
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
does not survive contact with `lifespan`.** Today's lifespan connects —
and `Database.connect()` itself builds the whole index set
(`ensure_indexes`, `infrastructure/database.py`) — then runs five startup
passes, `migrate_project_kinds`, `clear_personal_goal_on_day_jobs`,
`move_sunday_plans_to_monday`, `mark_connected_assignments` and
`date_pairing_codes`, and builds the idempotency log's indexes
(`ensure_mutation_log_indexes`). An operator deployment booting that would
either fail on its narrow credential or — worse — race the API's own startup
passes. A switch that gates routers but shares a lifespan is broken, and one
that gates the lifespan too has become an app factory wearing a disguise.

So: **a second composition root in the same package.**

```
api/src/server.py            the public API        → uvicorn server:app
api/src/operator_server.py   the operator API      → uvicorn operator_server:app
api/src/beats/               the library both compose
```

Two things in that library assume the public API is the only thing that
composes it, and both change before the second root can exist:

- **`Database.connect()` stops building indexes.** `server.py`'s lifespan
  calls `ensure_indexes` after connecting, and is its only caller (beside
  the test harness, which already calls it directly). The public API is
  then the one deployment that builds indexes, the operator's collections'
  included: it holds the grant, and the operator deployment never needs one.
- **The settings stop being the API's alone.** `beats/settings.py` builds
  `settings = Settings()` at import, and `Settings` requires `JWT_SECRET`
  and `FORWARDED_ALLOW_IPS`, so importing any name from that module
  demands the session secret. `infrastructure/database.py` is the one
  importer the operator root cannot do without. The others it must not
  import: `beats.api.dependencies` and the routers built on it;
  `domain/calendar.py`, `fitbit.py` and `github.py`; anything in
  `beats.auth`, whose `__init__` imports `oidc.py`; and the coach's
  `usage.py` and `gateway.py`. So `database.py` takes its DSN from its
  caller instead — `connect()` already accepts one — and the operator root
  wires its own providers, checks the IAP assertion outside `beats.auth`,
  reads coach spend through `MongoOperatorReads`, and reads an
  `OperatorSettings` of its own: the DSN, the IAP audience or the local
  stand-in, the allowlist. The operator deployment then **never holds
  `JWT_SECRET`**, which it has no use for and which is every user's session
  in one value. A test pins it in a fresh interpreter, since the suite's
  own process loaded `beats.settings` before any test ran: importing
  `operator_server` there leaves `beats.settings` out of `sys.modules`.
  Unsetting `JWT_SECRET` would prove nothing: `Settings` also reads the env
  file `BEATS_ENV_FILE` names, which the suite points at `.env.test`, and
  that file holds one.

Same image, same `pyproject.toml`, same tests; the Cloud Run service's
command picks the module. What that buys over a flag:

- **The public app cannot serve an operator route**, because it does not
  import one. Not "a test asserts it is not mounted" — it is not reachable
  by construction. (A cheap test still pins it, against the day somebody
  adds the import.)
- **Each lifespan is honest.** `operator_server`'s connects the database and
  stops — which, once `connect()` builds nothing, is true: no migrations, no
  index building, nothing that needs a write grant on collections it must
  not touch.
- **No third mode for jobs.** A role variable for jobs would be the same
  mistake again; a Cloud Run Job runs `python -m beats.operator.jobs`, an
  entry point, not an app in a costume. It does not read `OperatorSettings`,
  which refuses to load unless exactly one of the IAP audience and the local
  stand-in is set (§ *Authentication*), and a job has neither. It reads
  settings of its own — the wide DSN and the database's name, and nothing
  else: no allowlist, no `JWT_SECRET`.
- **Middleware differs where it must.** Two roots means two middleware
  stacks: the operator app's resolves an IAP assertion and no other
  credential, rather than one dispatch carrying a branch for a caller it
  will never see in production.

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
| Grant the owner role | `OrganisationService`, in a new method beside `set_role` (below) |
| Start, move or cancel a closing notice | `OrganisationService`, in a new method beside `begin_closing` and `cancel_closing`; moving the day is calling it again, so "extend" needs nothing of its own |
| Delete an organisation whose notice has run out | `OrganisationService`, beside `delete_organisation`; wide, so a job |
| Suspend, unsuspend, sign out everywhere | A new account service — these are account rules, and they belong with the account, not with the operator who happens to invoke them |
| Set or clear a limit | The same |
| Revoke a device | The device registration repository; `DeviceRegistration.revoked` exists |
| Disable a webhook | The webhook repository, built for the target account (it is scoped by `user_id`); `Webhook.active` exists |
| Queue an erasure or a purge | Enqueued, never executed inline (below) |

**The organisation's methods cannot be called as they stand.** `set_role`,
`begin_closing`, `cancel_closing` and `delete_organisation` each open with
`_member(organisation_id, actor, …)`: the caller must be an active member,
and the owner role and closing are an owner's. The operator is no member,
and in the case this page exists for there is no owner at all. The
last-owner guard of decisions 10 and 20 does not help either — it guards
demotion, leaving and removal, not granting.

So each gets an operator twin beside it in `OrganisationService`, taking an
`Operator` rather than a user id and sharing everything after the
membership check. Its rule is decision 31's, made explicit: **the operator
acts only for an organisation with no owner.** While an owner exists the
organisation can act for itself, and an operator who grants the owner role
there is taking a side in its dispute — refused, 409, like any other rule.
The owner is granted to an active member, normally an admin: the person the
organisation already trusted most, named in its request.

**The organisation's own log needs an actor that is not a user.**
`OrgAuditEvent.actor_user_id` is a user id, and `None` already means the
system — `account.erased` is written that way. An operator act carries an
actor kind of its own, and the organisation's audit page reads it as the
operator, so a member reading their organisation's history can tell an
act of ours from an act of theirs.

There is then **no `OperatorService`.** The command runner below resolves
the operator, authorises the role, writes the operator's audit and
delegates; a service doing the same in front of it would be a second
coordinator. If a rule ever starts living in a command or the runner, that
is the signal it was put in the wrong place.

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
call `describe()`, run, write `operator_audit` with before and after. Where
the subject is an organisation, its own `org_audit` entry is written by the
method the command delegates to, as for every other act on it — the runner
does not write it a second time. Deletion is the exception:
`delete_organisation` deletes the organisation's `org_audit` with the rest,
so that act is kept by `operator_audit` alone. Four properties fall out of one place
rather than ten:

1. **Nothing is unaudited**; the runner is the only path.
2. **Destructive work routes itself.** `wide = True` enqueues instead of
   executing, so erasure, the retention purge and an organisation's deletion
   cannot accidentally run in a request handler holding the wrong
   credential. A queued job is just a serialised command — one abstraction,
   not two mechanisms.
3. **Confirmation is declared, not remembered** per handler.
4. **The job runner is trivial**: load the command, run the same runner,
   which executes it rather than queueing it again.

A queued command carries the operator who queued it. The role and the
typed confirmation are checked once, by the request that queues it; the job
sees no request and holds no allowlist, so it checks neither again, and
writes `operator_audit` under the operator the command carries. The
command's rules are checked when it runs, not when it was queued, because
they live in the method it delegates to: a deletion whose organisation has
been given an owner while it waited is refused then.

Ten or so commands justify this; a hundred would justify more, and three
would not.

### Deployment, and the origin problem

Three Cloud Run services from two images:

| Service | Image | Command | Ingress |
|---|---|---|---|
| `beats-api` | API | `uvicorn server:app` | all (today, unchanged) |
| `beats-operator` | API, **same image** | `uvicorn operator_server:app` | internal and Cloud Load Balancing; IAP at the LB |
| `beats-backoffice` | a static image (nginx serving files, nothing else) | serve `backoffice/dist` | internal and Cloud Load Balancing; IAP at the LB |

plus a `google_cloud_run_v2_job` running `python -m beats.operator.jobs` on
a Cloud Scheduler trigger, with the wide credential.

Not `internal`: that ingress admits an *internal* load balancer and VPC
traffic, and refuses the external load balancer a browser comes through.
`internal-and-cloud-load-balancing` admits that one and keeps the
`run.app` URL from going around IAP. The fallback below has no load balancer,
so there the ingress is `all` and the wall is Cloud Run's own IAP on the
service. Either way the new services are `google_cloud_run_v2_service` —
Cloud Run's own IAP is a v2 setting, and the API's service is still the v1
`google_cloud_run_service` — and IAP's service agent is their only invoker.

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

- **Google IAP** in front, at the load balancer, or on the service under the
  fallback. The operator app verifies the signed assertion
  (`x-goog-iap-jwt-assertion`) as Google's guide to signed headers sets
  out — `alg` ES256 and no other, a `kid` among the
  keys Google publishes, `iss` `https://cloud.google.com/iap`, `aud` the
  audience in `OperatorSettings`, `exp` and `iat` within 30 seconds of
  skew — and matches its **`sub`**, Google's stable id for the account,
  against an allowlist in `OperatorSettings` with a role beside each:
  `viewer` or `operator`. Two roles from day one, so a second person can
  look without acting. The allowlist names the operator alone until
  PRIVACY.md names that person where it now says "I … am the only
  operator", and the processing agreement's confidentiality term
  ([legal/dpa.md](legal/dpa.md)) says who else sees an organisation's
  members: a viewer reads addresses and rosters, so adding one is that
  change, not an allowlist edit. The email is shown, never matched: the
  API keys a sign-in identity on issuer and subject for the same reason
  (`auth/sso_accounts.py`), and an address can change hands.
- The audience names the resource IAP guards, so it follows the origin
  decision: behind the load balancer it is the operator API's backend
  service (`/projects/PROJECT_NUMBER/global/backendServices/ID`), and under
  the fallback, where IAP sits on the service and there is no load
  balancer, it is the Cloud Run service
  (`/projects/PROJECT_NUMBER/locations/REGION/services/NAME`). The project
  number, not its id, in both.
- IAP's IAM binding says who reaches the app; the allowlist says what they
  may do. Both name the same people, and the app refuses an identity the
  allowlist does not name, so an IAM grant made by mistake reaches a 403.
- The operator app **neither issues nor accepts a beats session JWT**, and
  does not hold the secret that signs one. Not a rule to enforce:
  `SessionManager` is not in that composition root, and `OperatorSettings`
  has no `JWT_SECRET` field.
- Locally, `BACKOFFICE_DEV_OPERATOR=<sub>` stands in for the assertion, as
  `BEATS_TEST_ENV` stands in for testcontainers. **Exactly one of it and the
  IAP audience is set**, or `OperatorSettings` refuses to load: a stand-in
  left in a deployment's environment stops the deploy instead of replacing
  the wall, and a deployment with neither has no way in rather than an open
  one.
- **The browser's credential is a cookie** — IAP's, on the operator's host
  — and a browser can send it with a request another site's page starts.
  The public API never met this: it reads a `Bearer` header that nothing
  sends on its own. So every command is a `POST` with a JSON body, never a
  form, and no `GET` changes anything: JSON from another origin needs a
  preflight that nothing on this path grants. And the operator app refuses
  a command whose `Origin` is missing or not its own, or whose
  `Sec-Fetch-Site` is not `same-origin` where the browser sends one. The
  typed confirmation is no defence: the forging page sends it as easily as
  the operator types it.

### The enforcement points, and their cost

Suspension and `sessions_valid_after` are checked in the **public** API's
middleware, on every authenticated request — suspension on the device branch
as well as the session branch. Done naively that is a Mongo round-trip per
request.

The answer is already in the codebase: `auth/device_access.py` caches a
device's revocation verdict for 30 seconds, process-local, with its reasoning
written out — the token signature and expiry are still checked every time;
only the flag lookup is skipped; revoking through the API drops the entry so
it takes effect at once, and the TTL only bounds staleness from a change made
directly in the database.

An account's auth state takes the same shape, and its ceilings ride with it:
**one cached lookup returning** `suspended`, `sessions_valid_after` and
`last_seen_on` off `User`, and the ceilings off its `account_limits`
document. One cache, two reads on a miss, for every feature that needs the
account on the request path — including the ceiling on the flow window a
daemon posts every minute, which would otherwise read Mongo for it. When the
cached `last_seen_on` is not today, the middleware writes today with a
conditional update (`last_seen_on` not already today), so an account costs
one write a day, not one a request, however many instances see it.

**It is not invalidated by the operator's command, and cannot be.** The
cache is per process in the public API; the command runs in another
service. An operator's suspension or sign-out therefore takes effect within
the TTL — 30 seconds, on every instance — which is the bound `device_access`
already accepts for a change made directly in the database, and is short
enough for both acts. Revoking a device from the control plane is the same:
`device_access.forget` drops the entry only in the process that calls it.

That window is why sign-out compares against the **sign-in**, not the
token. `refresh_token` mints a new token with a new `iat`; compared against
`iat`, a session refreshed on an instance whose cache had not yet seen the
sign-out would come out newer than `sessions_valid_after` and outlive it for
good. A session token carries `auth_time` — when the passkey or SSO sign-in
happened — and every refresh copies it, so a refreshed token is exactly as
old as the sign-in behind it and is refused the moment the cache catches up.
A token minted before the claim exists has none, and a refresh would have
nothing to copy: let through, a tab open on the day this ships, which the
SPA's `scheduleRefresh` renews every 55 minutes, would outlive every
sign-out for as long as it stayed open. So `validate_session_token` refuses
a session token without `auth_time` — which keeps it from the middleware and
from `refresh_token` alike — and whoever is signed in when it deploys signs
in once more. Reading such a token's `iat` instead would spare them that, for
a branch that is dead an hour later.

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
| `connect()` stops building indexes and stops importing the settings singleton; `server.py`'s lifespan calls `ensure_indexes` | `beats/infrastructure/database.py` | the test harness, which already calls `ensure_indexes` directly |
| `OperatorSettings`: the DSN, the IAP audience or the local stand-in (exactly one), the allowlist by `sub` — and no `JWT_SECRET` | `beats/operator/settings.py` | `beats/settings.py`, without the API's secrets |
| `User.suspended_at/by/reason`, `User.sessions_valid_after`, `User.last_seen_on`, `AccountLimits`, `OperatorAuditEvent`, `OperatorJob` | `beats/domain/models.py` | `OrgAuditEvent`, `DeviceRegistration` |
| `auth_time` on a session token, copied by `refresh_token`; a session token without it refused by `validate_session_token` | `beats/auth/session.py` | the claims `create_session_token` already sets |
| Account rules: suspend, unsuspend, sign out everywhere, limits | `beats/domain/accounts.py` | `ContractService` — rules with the thing they govern |
| The operator's organisation acts — grant the owner role, closing, deletion — refused while an owner exists; an actor kind on `OrgAuditEvent` | `beats/domain/organisations.py`, beside `set_role`, `begin_closing`, `cancel_closing`, `delete_organisation` | the member's method beside each, sharing all but `_member` |
| `OperatorReads` (aggregates only) and `OperatorStore` (the narrow writes) | `beats/domain/ports.py` | `OrganisationRecords`, `PeriodLocks` |
| The command protocol, the runner — the one coordinator — and the commands | `beats/operator/` (`commands.py`, `runner.py`, `jobs.py`) | `beats/coach/` — a package for a surface, beside the domain it uses |
| `MongoOperatorReads`, `MongoOperatorStore` | `beats/infrastructure/operator_reads.py`, `operator_store.py` | `MongoOrganisationRecords` — the named cross-tenant class, never a widened `_q` |
| The router | `beats/api/routers/operator.py` | `routers/employment.py`; same error envelope |
| The operator's providers: the database, the organisation service, `OperatorReads`, `OperatorStore`, the runner | `beats/operator/dependencies.py` | `beats/api/dependencies.py`, which the operator root must not import |
| The IAP assertion → `request.state.operator` | `operator_server.py` middleware | the device branch, minus the user id |
| Suspension (both branches), `sessions_valid_after` against `auth_time`, `last_seen_on`, the account's ceilings, cached | `server.py` middleware + `auth/account_access.py` | `auth/device_access.py`, TTL and all |
| The per-account ceiling, read before the global — by the budget check and by `GET /api/coach/usage`, whose `budget_usd` the Settings page shows and today reports the global | `beats/coach/usage.py`, `beats/api/routers/coach.py` | its own existing shape |
| `test_operator.py`: the HTTP contract against `operator_server`; **the wall** — a sentinel in every stored thing the right-hand column of § *The line* names (a session's note, and its day, years before the run so no account's own dates can match it; a project's and a team's name; a tag; an absence note; a client's name and rate; a webhook URL's path; a coach message and a memory; an integration's token; a biometric value; an organisation audit entry's reason) in no byte of any operator response; `operator_server`, imported in a fresh interpreter, leaving `beats.settings` out of `sys.modules`; `server` not importing the operator router; a command with a foreign `Origin`, or none, refused | `api/src/` | `TestOrganisationWall` |
| `scripts/dump_openapi_operator.py` → `backoffice/`'s types | `api/scripts/` | `dump_openapi.py`, which imports `server:app`; this one imports the other root |

The wall test matters most. It is how "never user content" stops being a
sentence in a roadmap and becomes something CI refuses. So it plants the
whole column, not a sample: the database user reads every collection, and
the likeliest leaks sit beside reads the control plane does make — a
webhook's URL read for its domain, an integration's document read for
whether it exists, an audit event read without its `details`.

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

The generated types are its own as well. `ui/tools/openapi-types` installs
with `ui/`'s workspace, and is a package of its own there because
`openapi-typescript` drives the compiler API that TypeScript 7 no longer
exposes; `backoffice/` repeats that split — a workspace of its own, the
generator in `tools/` with a TypeScript 5 — and a drift check in the shape
of `gen:types:check` over what `dump_openapi_operator.py` writes. Its gates
are new too: `lefthook.yml` and `.github/workflows/ui.yml` name `ui/`, not a
sibling, so `backoffice/` gets entries of its own in both, its type check
triggered by `api/src/**` the way `ui-api-types` is — an API-only change is
what stales the types, and it touches nothing under `backoffice/`.

Deliberately **not the sky** — no `SkyBackdrop`, no two hours, a denser and
plainer look. An operator should never be unsure which surface they are on.

**Infrastructure — `terraform/`**: `beats_operator` and, if the origin
decision keeps it, `beats_backoffice`, as `google_cloud_run_v2_service`s with
no `allUsers` invoker; a `google_cloud_run_v2_job` with a Cloud Scheduler
trigger; and, if the decision lands on it, the IAP-protected load balancer
with path routing, its hostname and certificate. IAM for the allowlist, and
for the landing page's deploy state the reads `deploy_lock.sh` makes: the
API service and its revisions, the tags in the Artifact Registry
repository, and `beats/deploy.lock` alone, as a get under a condition on
`resource.name` (a condition on the name cannot narrow a list, so the
operator never lists the bucket). Same image for the operator service, same
Cloud Build, same deploy lock. `apis.tf` gains the IAP and Cloud Scheduler
APIs, and Compute if the load balancer is chosen; none is enabled today.
The load balancer's hostname is a record in `cloudflare.tf`, beside
`api_cname`.

Each new service, and the job, runs as a service account of its own
(`google_service_account`), never the Compute Engine default that
`cloudrun.tf` leaves the API on. That account holds `roles/editor` on the
project and, through `projectEditor`, owns every object in the state bucket,
so anything running as it reads the whole Terraform state — the DSN and
`JWT_SECRET` included — whatever condition is written for the lock. Reading
the API service and its revisions is the same hole by another door: their
spec carries `JWT_SECRET` and the DSN as plain environment values, so those
grants wait until the API takes both from Secret Manager, which the
operator's account is never given.

**The second database user is not Terraform's.** The API's DSN is a plain
variable (`var.mongodb_connection_string`) and the cluster is run outside
this repository, so the user and its role are made at the database's host,
by hand, and the steps written into `terraform/README.md` beside the
variable that carries its DSN. Its role reads every collection — the counts
need them, and the wall is in the code and the wall test, not the grant —
and **writes only these**: `users` (suspension, `sessions_valid_after`),
`account_limits`, `device_registrations` (`revoked`), `webhooks` (`active`),
`organisations` (closing), `org_members` and `org_audit` (the owner role, and
each act's entry), `operator_audit` and `operator_jobs`. It creates no index.
That list is the grant: a command that needs a collection not on it changes
this paragraph first.

**Nor is IAP's OAuth client.** The project, `beats-476914`, sits in no
Google Cloud organisation (checked 2026-11-01), and Google's managed OAuth
client serves only an organisation's internal users, so IAP needs a custom
client whichever origin is chosen: a consent screen for external users and
a web client, made by hand in the console — no API creates one — then
handed to IAP: by the backend service's `iap` block behind a load
balancer, or by `google_iap_settings` when IAP is on the Cloud Run service
itself. The steps go into
`terraform/README.md` beside the one-time GitHub connection, and the
client's id and secret into the tfvars as sensitive variables.

**CLAUDE.md** gains `backoffice/` in the layout table, `/api/operator` in
the routes table, and a line in *Infrastructure* about the second
deployment — when it ships, not before.

## What it does, by the job it serves

### 1. Attention — the landing page

The reason to open it. Each row a count, linking to the thing.

- **Organisations with no owner** (decision 31). Owner-only acts wait until
  someone notices, and the only trace today is an `account.erased` line in
  that organisation's audit log.
- **Queued erasures inside their cancellation window.** Not requests:
  PRIVACY.md has a person ask by email, so a request lives in the operator's
  inbox until it is queued from the account page. Counting them here would
  take an in-app request, which is a product change and a PRIVACY.md change,
  not a control-plane page.
- **What a retention purge would take**, per organisation. The script is dry
  by default and nothing schedules it (decision 30); nobody is reminded.
- **Accounts over a limit**: coach spend near or past the cap; storage or
  write-rate outliers.
- **Approvals superseded and never reopened** (`superseded_at`, decision 23):
  one standing for months means a decider never saw the mark.
- **Absence requests pending beyond a threshold.**
- **Deploy state**: the live commit — the API service's latest ready
  revision, read the way `deploy_lock.sh` reads it — and whether
  `beats/deploy.lock` is held. The IAM for both reads is under
  *Infrastructure*: the lock sits beside the Terraform state, read as that
  one object and never the bucket, and the revision waits until the API's
  secrets leave its spec.

### 2. Accounts

Found by **exact email or id** — not a browsable list, not a prefix search.
The common entry is a support or erasure mail carrying a full address;
exact-match serves that and is useless for fishing. Exact, but not
case-sensitive: sign-up stores an address as typed (`routers/auth.py`),
under a unique index with no collation (`infrastructure/database.py`), so
`Ana@example.com` and `ana@example.com` can be two accounts, and a mail
from either spelling must find both. The lookup asks with a case-insensitive
collation and lists every account it matches; the unique index cannot serve
that query, so it reads `users` whole.

One account: created, the day last seen, suspension state, passkeys and
linked providers, devices with each one's last seen, organisations and
roles, counts of projects / sessions / biometric rows, storage estimate,
coach spend against its cap, integrations connected.

**Actions**: suspend and unsuspend; set or clear a limits override; sign out
everywhere (sessions); revoke one device; queue an erasure (typed
confirmation, cancellation window).

**No subject-access export.** A person exports everything themselves
(`/api/export/full`), and an export the operator generates would carry all of
someone's content through the one surface built never to. Someone who
cannot sign in to export has an account-recovery problem, not an export
one, and that is a design of its own.

On **sign-in doors**: identities per provider is a fact the account *stores*
and fair to show. It is **not** a record of which door a sign-in used, which
the code deliberately does not keep. Do not let one grow into the other.

### 3. Organisations

A list: name, created, members by role, active assignments, **seat count**
([docs/pricing.md](../docs/pricing.md) defines it; [subscriptions.md](subscriptions.md)
bills on it), free-tier position, retention years, closing state. One
organisation adds memberships with roles and dates, how many projects it
has and how many came by a connect, timesheets by status, and its audit log
— each event's kind, actor, subject and time, **without its `details`**,
which carry what the organisation wrote: a reopened month's `reason`, a
created project's or team's name.

**Actions**, while the organisation has no owner and only then: grant the
owner role to an active member — decision 31 refuses to auto-promote but
leaves somebody having to act, and this is where; start, move or cancel a
closing notice; delete it once the notice has run out.

Adjusting a plan or a seat allowance is not one of those acts — it is the
platform's own term with the organisation, not one its owner would have
made — and waits on #345, which collects the per-seat price
([subscriptions.md](subscriptions.md)).

### 4. Abuse and limits

**Detection**, by outlier rather than guessed threshold: coach spend per
account; flow windows per account per day (the daemon is the heaviest writer
— 100× the median is a broken or hostile one); sessions and projects created
per day and import sizes; **report links minted per account** (`/api/reports`
is the only public path serving a user's data); **webhook destinations by
domain** (outbound HTTP from our servers to arbitrary URLs is ours to answer
for); pairing codes and devices per account; signups per day and provider.
Abuse that shows in requests rather than in accounts — rejections under
`/api/`, and guessing at sign-in, report links or pairing codes — is already
counted and alerted on in Cloud Monitoring
([terraform/README.md](../terraform/README.md#monitoring)); this section is
the half that needs the database.

**Controls**: `account_limits` overrides read at the API's enforcement
points; suspension; revoking one device — the narrow answer to one broken
daemon; disabling one webhook.

### 5. Capacity and cost

Documents and storage per collection with growth; write volume per day by
kind; distributions as percentiles rather than lists; **coach cost** from
`llm_usage` as a platform total by day and model, with the cache-hit ratio.
That is a new pipeline in `operator_reads.py`: `UsageTracker.usage_summary`,
the "cost dashboard" its docstring names, is one account's own
`/api/coach/usage`, by day and not by model.
**Latency, error rates and instance counts are Cloud Monitoring's**, on the
dashboard `terraform/monitoring.tf` already builds — link to it, do not
rebuild it.

### 6. Compliance operations

The erasure queue; retention due per organisation and running it as a job;
the operator audit, readable and filterable, editable by nobody.

## What must not happen

- **No "view as this user", ever.** PRIVACY.md admits the operator can read
  any document and promises not to log into an account or read its sessions
  without a reason. A button would make reading an account the everyday
  tool, and the home page's "we don't watch you" false.
- **No user content**, per the table; no page, export or CSV carries a note,
  a tag, a project name, an audit entry's details or a figure from someone's
  record. The wall test enforces it.
- **No free-text search** over content, and none over addresses beyond the
  exact-match lookup.
- **No destructive act in a request handler.** Erasure, the purge and an
  organisation's deletion are jobs with a typed confirmation and a
  cancellation window.
- **`server.py` never imports the operator router.** That import, absent, is
  the isolation — not a flag, not a conditional. A test pins it for the day
  somebody adds one.
- **No rule lives in a command or the runner.** They resolve, authorise,
  audit and delegate. A guard written there is a guard that will disagree
  with the one the member-facing route enforces.
- **No mutation outside the command runner**, or the audit becomes a thing
  people remember to write.
- **The operator deployment's database user writes only the collections
  listed under *Infrastructure***, and builds no index, whatever the code
  claims to do.
- **The operator deployment never holds `JWT_SECRET`.** Holding it is
  holding every user's session; a test imports `operator_server` in a fresh
  interpreter and finds no `beats.settings` in `sys.modules`.
- **The operator does not act for an organisation that can act for itself.**
  Granting the owner role, closing and deletion are refused while the
  organisation has an owner.
- **Nothing silent inside an organisation.** An operator act on one lands in
  its own audit log, under an actor its members can tell is the operator.
- **Reads go through the named narrow classes** — never by widening
  `MongoStore._q`, never by handing an existing service a wider scope.
- **It does not become customer support** with a deeper tier of access
  because someone asked a question it cannot answer. That is a new decision
  with a new PRIVACY.md sentence, not a patch.

## Open, for when it starts

- **Order.** Four steps, each shippable and each useful alone:
  1. the enforcement points in the public API — suspension first, on both
     branches, since it is the smallest and unlocks the most; then
     `sessions_valid_after` with `auth_time`, `last_seen_on` and
     `account_limits`, with the cached auth-state lookup;
  2. `operator_server.py` with the queries only — after `Database.connect`
     stops building indexes and `database.py` stops importing the settings
     singleton, the changes that let it boot with a narrow credential and
     no session secret. A read-only control plane is already worth having,
     and it proves the composition root and the wall test before any
     command exists;
  3. the command runner and the commands, inline ones first, with the
     operator's methods beside the organisation's;
  4. the job runner, and only then the irreversible work.
- **The origin decision**: an IAP-protected load balancer with path routing
  (one origin, a standing cost) against serving `backoffice/dist` from the
  operator app (one service, built-in IAP, no LB). Price both. Either is
  fine; two origins is not.
- **PRIVACY.md** should say that an account can be suspended and a device
  revoked by the operator, that the day an account was last seen is kept,
  and that operator actions are audited — in the organisation's own log too
  when they touch one — before the first one ships. A second name on the
  allowlist is a later change to it, and to the processing agreement
  (§ *Authentication*).
- **Pre-computed aggregates.** Per-request pipelines are fine at this size
  and will not stay fine; a nightly roll-up is the first thing that will ask
  the operator deployment for a wider write grant, so decide it deliberately
  when it does.
