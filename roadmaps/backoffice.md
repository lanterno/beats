# The control plane

The operator's UI for **running the platform**. Issue **#424**.

LifePete has one operator. PRIVACY.md says "I … am the only operator", and
there is no place to run the platform from. Every operator act today is a
script in `api/scripts/` fired by hand at production. Every limit is a
constant that needs a redeploy to change. Everything an operator should
*notice* is noticed only by going to look.

Split out of [roadmaps/organisations.md](organisations.md) and designed on
2026-10-31. By the next day it had been revised three times:

- once when the owner asked whether one API could serve both (it can,
  § *Architecture*);
- once in a design review that found the first answer to that question broken
  (the `lifespan` paragraph says how);
- once when every claim was checked against the code. That found the second
  answer resting on two things the code doesn't do yet (connecting without
  building the index set, and importing the settings without the session
  secret), and the organisation commands delegating to methods that refuse any
  caller who isn't a member.

It was reviewed again on 2026-11-04, for what an implementer would still have
to decide. That review found three claims wrong: what the clients do with a
refused write, who reads an organisation's audit log, and how a closing notice
moves. It also found erasure deleting the control plane's own records, and
filled every gap with a decision. Those decisions are listed in § *Work*, so
they can be argued with in one place.

It was filed under the organisations epic because an organisation left without
an owner (decision 31) was the first thing anyone wanted to see. A control
plane is not an organisations feature.

## What blocks what

Step 1 — enforcement in the public API — shipped on 2026-11-04; what it
built is [docs/account-controls.md](../docs/account-controls.md).

| Step | Blocked by | Gives |
|---|---|---|
| 2. The operator deployment, read-only | The `beats.settings` split, the hand-made OAuth client and database user (§ *Infrastructure*), and the answer to § *Needs the owner* | Every page, and no button |
| 3. Inline commands | Step 2 | Suspend, limits, revoke, the organisation acts |
| 4. The job runner and the irreversible work | Step 3 | Erasure, an organisation's deletion, the retention purge |
| The landing page's deploy-state row | [secret-manager.md](secret-manager.md) | Its reads need the API's spec to carry no secret |

Each step ships alone. § *Work* lists what each one does.

---

## What it is, and what it is not

**A control plane: pages organised around what the operator is trying to do.**
Find the account a support mail came from and act on it. Fix an organisation
whose owner is gone. Find who is burning the coach budget and cap them. See
whether storage growth is about to cost money.

**Not a Django admin**, with one page per collection and a CRUD form. That
makes the operator translate every real question into four screens of joins.
It also makes the dangerous act (edit this document) the easiest one on the
page.

**Not a dashboard either.** Statistics are in it because they serve two
operator jobs: predicting what the platform will cost and how it will behave
next quarter, and catching use that has turned into abuse. A wall of charts
is not the goal.

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
| An organisation's audit events: what, by whom, to whom, when | Their details: a reopen's reason, a project's or a team's name |
| Biometric *row counts* | Any biometric value |

"The day last seen" is a date the API doesn't keep yet (below). It isn't read
off the newest session, because a session's time belongs in the right-hand
column of this table.

The operator can still read any document in Mongo. PRIVACY.md says so rather
than pretending otherwise, and that is why the line is worth drawing: **every
question the control plane answers is a `mongosh` session against production
that doesn't happen.** The wide credential stops being the everyday tool,
which is also what makes a second operator safe to add later.

## The finding that shaped step 1

**A control plane can only control what the API enforces, and when this was
checked (2026-11-01, and again 2026-11-04) the API enforced almost none of
it**: no suspension anywhere, a revocation list in one instance's memory, one
global coach budget, no rate limit on the write routes that matter, and
nothing recording that an account was in use at all. Those enforcement
points were API work whichever way the back office is built, so they were
built first — a control plane whose controls do nothing is a viewer with
buttons — and shipped as step 1 on 2026-11-04.

What the API now enforces — suspension end to end (403 `ACCOUNT_SUSPENDED`
everywhere the account can act, worded around `contact_email`), sign-out
everywhere (`sessions_valid_after` against the token's `auth_time`), the two
last-seen stamps, `account_limits` with the write ceilings and
`webhooks_disabled`, and what each client does with a refusal — is
[docs/account-controls.md](../docs/account-controls.md). Device revocation
(`DeviceRegistration.revoked`) predates it; the operator only invokes it.

One piece of that analysis stays open here: the user's own logout
(`account.py`) is weaker than it looks, because `refresh_token` mints a
fresh hour on every call while only one instance knows a token was revoked.
That is **#451**, and `sessions_valid_after` with `auth_time` is the
mechanism that fixes it: logout becomes "this session's `jti`, everywhere"
once the check reads the account rather than the instance. Whether that
ships is #451's call.

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
own rule weighs hard against A: *rules implemented more than once* are the
ones that drift, and a control plane is mostly the API's own rules exercised
by a different person.

**Verdict: B, with a refinement that keeps A's isolation: one codebase, two
composition roots, deployed separately.**

### Two composition roots, not a mode switch

The obvious way to do B is an env var that decides which routers mount. **It
does not survive contact with `lifespan`.** Today's lifespan connects, and
`Database.connect()` itself builds the whole index set (`ensure_indexes`,
`infrastructure/database.py`). It then runs five startup passes and builds
the idempotency log's indexes (`ensure_mutation_log_indexes`). The passes are:

- `migrate_project_kinds`
- `clear_personal_goal_on_day_jobs`
- `move_sunday_plans_to_monday`
- `mark_connected_assignments`
- `date_pairing_codes`

An operator deployment booting that would either fail on its narrow
credential or, worse, race the API's own startup passes. A switch that gates
routers but shares a lifespan is broken, and one that gates the lifespan too
has become an app factory wearing a disguise.

So: **a second composition root in the same package.**

```
api/src/server.py            the public API        → uvicorn server:app
api/src/operator_server.py   the operator API      → uvicorn operator_server:app
api/src/beats/               the library both compose
```

Three things in that library assume the public API is the only thing that
composes it, and all three change before the second root can exist.

**`Database.connect()` stops building indexes.** `server.py`'s lifespan calls
`ensure_indexes` after connecting, and is its only caller beside the test
harness, which already calls it directly. The public API is then the one
deployment that builds indexes, the operator's collections' included: it
holds the grant, and the operator deployment never needs one.

**The settings stop being the API's alone.** `beats/settings.py` builds
`settings = Settings()` at import, and `Settings` requires `JWT_SECRET` and
`FORWARDED_ALLOW_IPS`, so importing any name from that module demands the
session secret.

- `infrastructure/database.py` imports it at module level, and
  `beats/infrastructure/__init__.py` imports `database.py`. So **every**
  `beats.infrastructure.*` import loads the settings today: the repositories,
  `organisations.py`, `erasure.py` and `retention.py` included. Checked in a
  fresh interpreter, 2026-11-04: with `database.py` no longer importing the
  settings, all four load clean. That one change is enough for the library.
- `database.py` takes its DSN and database name from its caller instead.
  `connect()` already accepts both. Every caller that passes neither changes
  in the same commit: `server.py`'s lifespan, `scripts/erase_account.py`,
  `scripts/retention_purge.py`, `test_middleware.py`, `test_auth.py`, and
  about a dozen sites in `test_coach.py`.
- The operator root must not import these, each of which loads the settings
  itself:
  - `beats.api.dependencies`, and the routers built on it;
  - `routers/auth.py`, `sso.py` and `coach.py`, which import the settings
    directly;
  - `domain/calendar.py`, `fitbit.py` and `github.py`;
  - anything in `beats.auth`, whose `__init__` imports `oidc.py`. That
    includes **`device_access`**, so the operator root can't call
    `device_access.forget`, and doesn't need to (§ *The enforcement points*);
  - the coach's `usage.py`, `gateway.py` and `context.py` (lazily).
- So the operator root wires its own providers, checks the IAP assertion
  outside `beats.auth`, reads coach spend through `MongoOperatorReads`, and
  reads an `OperatorSettings` of its own (§ *Authentication* lists its
  fields).
- The operator deployment then **never holds `JWT_SECRET`**, which it has no
  use for and which is every user's session in one value.
- A test pins it in a fresh interpreter, because the suite's own process
  loaded `beats.settings` before any test ran: importing `operator_server`
  there leaves `beats.settings` out of `sys.modules`. Unsetting `JWT_SECRET`
  would prove nothing. `Settings` also reads the env file `BEATS_ENV_FILE`
  names, which the suite points at `.env.test`, and that file holds one.

**The connection is not a class attribute.** `Database` keeps its client on
the class (`Database.client`, `Database.db`), so two apps in one process
share one. The operator app's `connect()` would replace the client the public
app made on another event loop, and its `disconnect()` would set it to `None`
under the public app. That is exactly what the test suite does, with both
apps in one process. So `operator_server`'s lifespan builds its own
`AsyncMongoClient` into `app.state`, and its providers read it from there.
`Database` stays the public API's.

Same image, same `pyproject.toml`, same tests; the Cloud Run service's
command picks the module. What that buys over a flag:

- **The public app cannot serve an operator route**, because it does not
  import one. It isn't that a test asserts it is not mounted: it is not
  reachable by construction. A cheap test still pins it, for the day somebody
  adds the import.
- **Each lifespan is honest.** `operator_server`'s connects and stops. Once
  `connect()` builds nothing, that is true: no migrations, no index building,
  nothing that needs a write grant on collections it must not touch.
- **No third mode for jobs.** A role variable for jobs would be the same
  mistake again. A Cloud Run Job runs `beats.operator.jobs` as an entry
  point, not an app in a costume. It doesn't read `OperatorSettings`, which
  refuses to load unless exactly one of the IAP audience and the local
  stand-in is set (§ *Authentication*), and a job has neither. It reads
  settings of its own: its DSN and the database's name, and nothing else
  today. No allowlist, no `JWT_SECRET`.
  [subscriptions.md](subscriptions.md) plans its seat reconciliation on this
  job, and whatever that needs is its change to argue.
- **Middleware differs where it must.** Two roots means two middleware
  stacks. The operator app's resolves an IAP assertion and no other
  credential, rather than one dispatch carrying a branch for a caller it will
  never see in production.

### The one invariant this protects

`request.state.user_id` is what every user-scoped dependency reads. **The
operator app never sets it.** It sets `request.state.operator` instead.

So if a user-scoped repository or router were ever imported into the operator
app by mistake, it would not quietly scope to the operator. It would fail,
loudly, on a missing attribute. That is fail-closed by construction, the same
instinct as `MongoStore._q` stamping a filter nobody can forget.

### Queries and commands are different shapes

The operator surface is read-heavy with a handful of commands, and the two
deserve different treatment. Giving both to one `OperatorService` would grow
the god-object this design is otherwise avoiding.

**Queries: no service layer.** "Accounts created per day", "organisations
with no owner" and "flow windows per account" are aggregation pipelines.
There is no rule to enforce and nothing to decide, so a domain service in
front of them would be a pass-through. They live in
`infrastructure/operator_reads.py` and return frozen dataclasses, and the
router calls them through an `OperatorReads` Protocol so a test can fake
them. The repo's narrow-port convention is kept; the empty service is not.

**Commands: delegate, never reimplement.** Each command belongs to whatever
already owns the rule. § *The commands* lists every one.

### The operator's organisation acts

**The organisation's methods can't be called as they stand.** `set_role`,
`begin_closing`, `cancel_closing` and `delete_organisation` each open with
`_member(organisation_id, actor, …)`. The caller must be an active member
(404 otherwise), and the owner role and closing are an owner's (403). The
operator is no member, and in the case this page exists for there is no owner
at all. The last-owner guard of decisions 10 and 20 doesn't help either: it
guards demotion, leaving and removal, not granting.

So each gets an operator twin beside it in `OrganisationService`. The twin
takes an `Operator` rather than a user id and shares everything after the
membership check. Its rule is new, and it amends decisions 10, 29 and 31
([docs/organisations.md](../docs/organisations.md)) when step 3 ships:
**the operator acts only for an organisation with no owner, and only when
asked.** "Has an owner" is a count of active members with the owner role
(`count_owners`). A suspended owner counts
([docs/account-controls.md](../docs/account-controls.md)).

- **The request.** It comes by email to the PRIVACY.md address, from the
  address on the requester's account, the way PRIVACY.md takes an erasure
  request. The requester must hold the highest role any active member of
  the organisation holds. The operator checks both with the exact-match
  account lookup and the organisation's page. A request that fails either
  check is refused by reply, and nothing is done.
- **The owner role goes to the requester**, nobody else. Picking among
  members is taking a side, and the requester is the person the organisation
  already trusted most.
- **Closing on request** uses the owner's own terms: at least 30 days out,
  60 by default, in the organisation's timezone.
- **Deletion needs no second request.** The notice was the request. Once the
  day has come, the operator queues it as a job (§ *Jobs*).
- **While an owner exists, all three are refused, 409 `ORGANISATION_HAS_OWNER`.**
  The organisation can act for itself, and an operator who grants the owner
  role there is taking a side in its dispute.

**Moving a closing notice.** The first draft said moving the day is calling
`begin_closing` again. It is, but `begin_closing` refuses any day less than
30 days from today, so a notice with five days left can't be extended by a
week. The rule changes for the owner and the operator alike, and amends
decision 29: **a day at least 30 days out, or any day later than the one
already set.** The minimum protects members from short notice, and a later
day only gives them more. Moving a notice earlier still needs the 30 days.

**The organisation's own log needs an actor that isn't a user.**
`OrgAuditEvent.actor_user_id` is a user id, and `None` already means the
system: `account.erased` is written that way.

- `OrgAuditEvent` gains `actor_kind`: `member`, `system` or `operator`. It is
  derived from `actor_user_id` for rows that predate it.
- Two writers skip `_audit` and insert raw rows with `actor_user_id: None`:
  `erasure.py` and `retention.py`. Both move onto a shared writer that takes
  the kind. Run by an operator's job, they write `operator`.
- The audit route returns `actor_kind`, and the SPA's `AuditSection.tsx` says
  "by LifePete" for it. That runs through the API's response model,
  `openapi.json`, `generated.ts`, `schemas.ts` and the mapper.
- Only an admin reads the audit log (`audit_log` requires ADMIN; PRIVACY.md
  says "nobody below admin"), so it is an admin who can tell an act of ours
  from an act of theirs. An SPA older than the API shows an operator's act
  the way it shows a system one, with no actor. That is acceptable skew, and
  says nothing false.
- The operator's id is never in the organisation's log; `actor_kind` is
  enough.

There is then **no `OperatorService`.** The command runner below resolves
the operator, authorises the role, writes the operator's audit and
delegates. A service doing the same in front of it would be a second
coordinator. If a rule ever starts living in a command or the runner, that is
the signal it was put in the wrong place.

**Wiring.** The public API builds `EmploymentService`, with the caller's
user-scoped billing repository as `BillingPresence`. The operator's providers
build `OrganisationService` with a `BillingPresence` that raises. Only
`connect_project` reads it, which is a member's act, and a stand-in that
answers would be a guess about somebody's billing.

### Commands are objects, so the audit can't be forgotten

An audit that each handler must remember to write will be missing from the
one action anybody cares about. So a mutation is not a function call in a
route. It is a small object:

```
class OperatorCommand(Protocol):
    name: str                      # "organisation.grant_owner"
    role: OperatorRole             # who may run it; every command today is "operator"
    window: timedelta | None       # None: execute inline. Else: enqueue, run after the window
    confirmation: str | None       # what the operator must type back
    def describe(self) -> dict     # subject + before, for the audit
    async def execute(self, ctx) -> dict   # … and after
```

One runner executes them:

1. check the role;
2. check the typed confirmation;
3. call `describe()`;
4. run;
5. write `operator_audit` with before and after.

Where the subject is an organisation, its own `org_audit` entry is written by
the method the command delegates to, as for every other act on it. The runner
doesn't write it a second time. Deletion is the exception:
`delete_organisation` deletes the organisation's `org_audit` with the rest,
so that act is kept by `operator_audit` alone.

Four properties fall out of one place rather than ten:

1. **Nothing is unaudited**; the runner is the only path.
2. **Destructive work routes itself.** A command with a window enqueues
   instead of executing. So erasure, the retention purge and an
   organisation's deletion can't accidentally run in a request handler
   holding the wrong credential. A queued job is just a serialised command:
   one abstraction, not two mechanisms.
3. **Confirmation is declared, not remembered** per handler.
4. **The job runner is trivial**: load the command, run the same runner,
   which executes it rather than queueing it again.

A queued command carries the operator who queued it. The role and the typed
confirmation are checked once, by the request that queues it. The job sees no
request and holds no allowlist, so it checks neither again, and writes
`operator_audit` under the operator the command carries.

The command's rules are checked when it runs, not when it was queued, because
they live in the method it delegates to. A deletion whose organisation has
been given an owner while it waited is refused then.

Ten or so commands justify this; a hundred would justify more, and three
would not.

### The commands

| Command | Runs | Confirmation | Delegates to |
|---|---|---|---|
| `account.suspend` | inline | the account's email | the account service (`beats/domain/accounts.py`) |
| `account.unsuspend` | inline | — | the same |
| `account.sign_out_everywhere` | inline | — | the same: sets `sessions_valid_after` |
| `account.set_limits`, `account.clear_limits` | inline | — | the same: `account_limits` |
| `device.revoke` | inline | — | the device registration repository's `revoke` |
| `account.erase` | job, **7-day** window | the account's email | `erasure.erase_account` |
| `organisation.grant_owner` | inline | the organisation's name | `OrganisationService`'s operator twin of `set_role` |
| `organisation.begin_closing` | inline | the organisation's name | the twin of `begin_closing` (start or move) |
| `organisation.cancel_closing` | inline | — | the twin of `cancel_closing` |
| `organisation.delete` | job, 1-day window | the organisation's name | the twin of `delete_organisation` |
| `retention.purge` | job, 1-day window | the organisation's name, or `all` | `purge_expired_records`, which gains `organisation_id` |
| `job.cancel` | inline | — | the job store; unsuspends an account whose suspension was the erasure's |

Every command needs the `operator` role; a `viewer` runs none. The
confirmations type back names from the left-hand column of § *The line*,
never content.

### The routes

Every route is under `/api/operator`, mounted only by `operator_server`.

| Route | Reads or does |
|---|---|
| `GET /me` | The signed-in operator: sub, email, role |
| `GET /attention` | The landing page's counts |
| `POST /accounts/lookup` | Exact email (case-insensitive) or id, in the **body**. An address in a URL is in Cloud Run's request log for 30 days, the reason `/api/reports` takes its token in a header |
| `GET /accounts/{id}` | One account |
| `GET /organisations`, `GET /organisations/{id}`, `GET /organisations/{id}/audit` | The list, one, and its log without `details` |
| `GET /abuse`, `GET /capacity` | The outlier and growth pipelines |
| `GET /audit`, `GET /jobs` | The operator audit and the job queue, filterable |
| `POST /commands/{name}` | `{args, confirmation}` → the runner. Answers the audit entry, and the job when one was queued |

The router is `beats/api/routers/operator.py`, in the error envelope.
`operator_server` also serves the UI (§ *Deployment*). A `GET` changes
nothing.

### Jobs

`operator_jobs` holds queued commands, and a Cloud Run Job drains it.

```
operator_jobs
  command, args              the serialised command
  subject_kind, subject_id   "account" | "organisation" | "all", and its id
  queued_by                  {sub, email} of the operator
  queued_at, run_after       run_after = queued_at + the command's window
  state                      queued | running | done | failed | cancelled
  attempts, claimed_at, finished_at, error
```

- **The trigger.** Cloud Scheduler starts the job every 15 minutes. It finds
  nothing due and exits on almost every run, which on Cloud Run Jobs costs
  next to nothing. Nothing else is scheduled: the retention purge stays an
  act the operator starts (decision 30, PRIVACY.md and the DPA all say so),
  now from a page rather than a shell.
- **Claiming.** A run claims one entry at a time with `find_one_and_update`:
  `queued` with `run_after` past, or `running` with `claimed_at` over an hour
  old, a run that died. It sets `running`, `claimed_at` and `attempts + 1`,
  then executes and loops until nothing is due. Overlapping runs can't take
  the same entry.
- **Re-runs must be safe**, because a run that dies mid-command is run again.
  - `erase_account` already is: memberships are tombstoned before anything is
    deleted.
  - The purge is idempotent by decision 30.
  - `delete_organisation` hands projects back and then deletes. Whether a
    second pass after a death halfway is safe is checked, and pinned with a
    test, in step 4 before it is queued for real.
- **Failure.** After three attempts an entry is `failed`. It shows on the
  landing page, and the job logs at `ERROR`, which a log-based alert in
  `terraform/alerts.tf` sends to `var.alert_email`. Today every alert watches
  only `beats-api`, so a silently failing erasure would page nobody.
- **The window** is for the operator's second thoughts and the person's.
  - **An erasure's window is 7 days, and queueing one suspends the account**
    with the erasure's own reason. Nothing new is written in that week, and if
    the mail didn't come from the account holder, they find out the moment
    they next open the app, from the erasure wording the suspension already
    carries ([docs/account-controls.md](../docs/account-controls.md)).
  - `job.cancel` inside the window lifts that suspension, and only that kind:
    a suspension for abuse is not lifted by cancelling an erasure.
  - PRIVACY.md gains the window (§ *Work*).

**Erasure must not take the control plane's records with it.** `erase_account`
ends by running `delete_many({"user_id": …})` over **every** collection in the
database. So:

- `operator_audit` and `operator_jobs` name their subject as `subject_id`,
  **never `user_id`**. Otherwise the sweep would delete the erasure job's own
  entry mid-run, and the audit of the act itself.
- `account_limits` is keyed on `user_id` on purpose, so the sweep takes it.
- A test pins all three.
- **`operator_audit` stores ids, never addresses.** `describe()` returns
  ids, and the page resolves an id to its email when it reads. After an
  erasure that resolves to "erased account". The audit keeps that the act
  happened, and nothing that names the person.
- `operator_audit` is kept for **four years**, the platform's default
  retention, and `retention.purge` removes older entries.

**The erasure script stays**, as the break-glass path. It changes to take an
account id, or to list every case-insensitive match for an address and stop.
Today's exact `find_one` can miss the account a mail came from (§ *Accounts*).

### Deployment: one service, behind Cloud Run's own IAP

**Decided 2026-11-04, on cost: the operator app serves `backoffice/dist`
itself, behind IAP on the Cloud Run service. There is no load balancer.**

The browser needs one origin. The first draft proposed Cloud Run's built-in
IAP *and* two services. Two services means two origins, which means CORS on a
privileged surface and the browser needing an IAP session per origin. The
choice was between:

- **an IAP-protected load balancer with path routing**: `/` to a UI service,
  `/api/operator/*` to the operator API. A global external Application Load
  Balancer's forwarding rule costs about **$18 a month standing**, plus
  $0.008 a GB processed. It also brings a global address, a managed
  certificate that provisions only once DNS resolves, an A record in
  `cloudflare.tf` (not a CNAME like `api_cname`), a backend service, and
  the Compute API;
- **serving `backoffice/dist` from the operator app** via `StaticFiles`,
  with the UI kept as its own codebase but not its own service. There is no
  standing cost at zero minimum instances, and nothing above.

At one operator, $18 a month buys nothing a person would notice. The
separation the owner asked for is in the repo and the build, which is where it
earns its keep; whether it is also a second Cloud Run service is a
deployment detail. Revisit if the back office ever needs to deploy apart from
the API.

What makes the fallback viable, checked 2026-11-04 against Google's
[IAP for Cloud Run](https://docs.cloud.google.com/run/docs/securing/identity-aware-proxy-cloud-run)
and the provider's docs:

- It supports a project with no organisation, which `beats-476914` is, through
  a custom OAuth client made in the console. Google says no API creates one
  (§ *Infrastructure*).
- It covers the `run.app` URL.
- `iap_enabled` on `google_cloud_run_v2_service` is a GA argument of
  `hashicorp/google`, so no `google-beta` is needed. Confirm on `~> 8.8` at
  the first `terraform init`.

| Service | Image | Command | Ingress |
|---|---|---|---|
| `beats-api` | API | today's, unchanged | all |
| `beats-operator` | API, **same image** | `uv run --no-dev uvicorn operator_server:app --host 0.0.0.0 --port ${PORT} --app-dir src --no-proxy-headers` | all, with `iap_enabled`; IAP's service agent its only invoker |

plus a `google_cloud_run_v2_job`, `beats-operator-jobs`, running `uv run
--no-dev python -m beats.operator.jobs` with `PYTHONPATH=src`, on the Cloud
Scheduler trigger above. A bare `python` in the image is the system
interpreter, without the project's dependencies.

- **The hostname is the `run.app` URL.** No domain mapping: Google's page
  names `run.app` URLs and load balancers, not mappings, and a hostname of our
  own would buy a nicer bookmark for one person.
- **The UI is built into the image.** `cloudbuild.yaml` gains a step before
  `build-image`: a Node image runs `pnpm install --frozen-lockfile && pnpm
  build` in `backoffice/`. Vite's `outDir` is
  `api/src/beats/operator/static/` (gitignored), so the Dockerfile's existing
  `COPY src/` carries it.
  - The Dockerfile doesn't change, and nor does the self-hosted build, which
    builds `./api` without the step and never runs the operator app.
  - The trigger's `included_files` gains `backoffice/**`.
  - A back-office-only change therefore builds a new image and redeploys
    `beats-api` with the same code, under the same deploy lock. That is
    accepted: it is one more revision, not a second pipeline.
- **`operator_server` serves the UI** at `/`, with `index.html` for any path
  outside `/api/operator` (the SPA's own routes). It refuses to start without
  `static/index.html` unless `BACKOFFICE_DEV_OPERATOR` is set, because
  locally Vite serves the UI.
- **The deploy lock's `decide` compares `beats-api` alone**, and one
  `terraform apply` covers all of it. An operator resource that fails to
  apply turns the API's deploy red too. That is accepted, and said here so it
  isn't a surprise.

### Authentication

- **Google IAP is in front, on the service.** The operator app verifies the
  signed assertion (`x-goog-iap-jwt-assertion`) as Google's guide to signed
  headers sets out:
  - `alg` ES256 and no other;
  - a `kid` among the keys Google publishes at
    `https://www.gstatic.com/iap/verify/public_key-jwk`;
  - `iss` `https://cloud.google.com/iap`;
  - `aud` the audience in `OperatorSettings`, which is the Cloud Run service
    (`/projects/PROJECT_NUMBER/locations/REGION/services/beats-operator`),
    with the project number, not its id;
  - `exp` and `iat` within 30 seconds of skew.
- **The verifier is its own** (`beats/operator/iap.py`). `oidc.py` can't be
  reused, because it imports the settings. It is built the way `oidc.py` is:
  an async `httpx` fetch of the key set with a TTL cache, and `jwt.PyJWK` per
  key. It doesn't use `PyJWKClient`, which is synchronous urllib and would
  block the loop. `pyproject.toml` declares `pyjwt[crypto]`: ES256 needs
  `cryptography`, which today arrives only through `webauthn` and
  `pyopenssl`.
- **It matches the assertion's `sub`**, Google's stable id for the account,
  against an allowlist in `OperatorSettings` with a role beside each:
  `viewer` or `operator`. There are two roles from day one, so a second person
  can look without acting.
  - The allowlist names the operator alone until PRIVACY.md names that person
    where it now says "I … am the only operator", and the processing
    agreement's confidentiality term ([legal/dpa.md](legal/dpa.md), a
    placeholder today) says who else sees an organisation's members. A viewer
    reads addresses and rosters, so adding one is that change, not an
    allowlist edit.
  - The email is shown, never matched. The API keys a sign-in identity on
    issuer and subject for the same reason (`auth/sso_accounts.py`): an
    address can change hands.
- **IAP's IAM binding says who reaches the app; the allowlist says what they
  may do.** Both name the same people, and the app refuses an identity the
  allowlist doesn't name, so an IAM grant made by mistake reaches a 403.
- **The operator app neither issues nor accepts a beats session JWT**, and
  doesn't hold the secret that signs one. That isn't a rule to enforce:
  `SessionManager` is not in that composition root, and `OperatorSettings`
  has no `JWT_SECRET` field.
- **`OperatorSettings`** holds the DSN and database name, the IAP audience or
  the local stand-in, the allowlist, and **the app's own origin**, which the
  command check below compares `Origin` against. In production that is the
  `run.app` URL; locally it is the Vite dev server's.
- **Locally, `BACKOFFICE_DEV_OPERATOR=<sub>` stands in for the assertion**, as
  `BEATS_TEST_ENV` stands in for testcontainers. Exactly one of it and the IAP
  audience is set, or `OperatorSettings` refuses to load. A stand-in left in a
  deployment's environment stops the deploy instead of replacing the wall,
  and a deployment with neither has no way in rather than an open one.
  - Locally the operator API runs on **:7998** (`just run-operator-locally`,
    beside `run-locally`'s :7999).
  - `backoffice/`'s dev server runs on **:8081** and proxies `/api/operator`
    to it.
  - The origin is then `http://localhost:8081`, which the proxy passes
    through unchanged.
- **The browser's credential is a cookie**: IAP's, on the operator's host.
  A browser can send it with a request another site's page starts. The public
  API never met this, because it reads a `Bearer` header that nothing sends
  on its own.
  - So every command is a `POST` with a JSON body, never a form, and no `GET`
    changes anything. JSON from another origin needs a preflight that nothing
    on this path grants.
  - The operator app refuses a `POST` whose `Origin` is missing or isn't its
    own, or whose `Sec-Fetch-Site` isn't `same-origin` where the browser sends
    one. That includes the account lookup, which reads.
  - The typed confirmation is no defence here: the forging page sends it as
    easily as the operator types it.

### The enforcement points, and their cost

Shipped with step 1: the public API checks suspension and
`sessions_valid_after` off one cached account lookup
(`auth/account_access.py`, the shape and TTL of `device_access.py`), which
also stamps the two last-seen fields and carries the account's ceilings.
[docs/account-controls.md](../docs/account-controls.md) holds the detail,
including why the sign-out cut compares against `auth_time` and never `iat`.
What matters to the steps left here: the cache is process-local in the
public API, so **an operator's command cannot invalidate it and doesn't
need to** — a suspension or sign-out written by the operator deployment
takes effect within the TTL (30 seconds) on every instance, the same bound
`device_access` already accepts for a change made elsewhere.

### What is deliberately not here

No message broker, no separate analytics store, no GraphQL layer, no tracing
collector, no event sourcing for the audit. The scale is one operator and a
few dozen queries. Each of those is a system to run, and none answers a
question better than an aggregation pipeline, an append-only collection and a
Cloud Run Job.

No pre-computed aggregates either, yet. A pipeline per request is fine at this
size and won't stay fine. A nightly roll-up would be the first thing to
widen the operator's database user past the list under § *Infrastructure*,
or to give the job work beyond draining its queue. Either is decided
deliberately when it comes, not slipped in with the page that wants it.

### Not in the self-hosted bundle

`compose.selfhost.yml` doesn't gain the operator app. IAP doesn't exist
outside GCP, and a self-hoster already has the database. Shipping a
privileged surface with a different, weaker auth story to people running it
on their own box is how one ends up with a default credential on the
internet. If it is ever wanted there, that is a separate decision with its own
authentication design.

## Fit with the codebase

**API: `api/src/`**

| Piece | Where | In the shape of |
|---|---|---|
| The second composition root: its own `lifespan` (its own client into `app.state`, and nothing else), its own middleware, the operator router, the static UI | `operator_server.py` | `server.py`, minus everything it must not do |
| `connect()` stops building indexes and stops importing the settings singleton; every caller passes the DSN and name; `server.py`'s lifespan calls `ensure_indexes` | `beats/infrastructure/database.py` | the test harness, which already calls `ensure_indexes` directly |
| `OperatorSettings`: DSN, database name, the IAP audience or the local stand-in (exactly one), the allowlist by `sub`, the app's origin, and no `JWT_SECRET` | `beats/operator/settings.py` | `beats/settings.py`, without the API's secrets |
| `OperatorAuditEvent`, `OperatorJob`, `OrgAuditEvent.actor_kind` | `beats/domain/models.py` | `OrgAuditEvent`, and step 1's fields on `User` and `AccountLimits`, already there |
| The `account_limits` writes the operator's commands make (set, clear) | `beats/domain/accounts.py` | the shipped suspend / unsuspend / sign-out beside them |
| The operator's organisation acts, refused while an owner exists; a closing notice that may always move later | `beats/domain/organisations.py`, beside `set_role`, `begin_closing`, `cancel_closing`, `delete_organisation` | the member's method beside each, sharing all but `_member` |
| One `org_audit` writer taking the actor kind, used by `_audit`, erasure and the purge | `beats/infrastructure/organisations.py` | `_audit` |
| `purge_expired_records(organisation_id=…)`, and the operator audit's four years | `beats/infrastructure/retention.py` | its existing pass |
| `OperatorReads` (aggregates only) and `OperatorStore` (the narrow writes) | `beats/domain/ports.py` | `OrganisationRecords`, `PeriodLocks` |
| The command protocol, the runner (the one coordinator), the commands, the IAP verifier, the job entry point | `beats/operator/` (`commands.py`, `runner.py`, `iap.py`, `jobs.py`) | `beats/coach/`: a package for a surface, beside the domain it uses |
| `MongoOperatorReads`, `MongoOperatorStore`, `MongoOperatorJobs` | `beats/infrastructure/operator_reads.py`, `operator_store.py`, `operator_jobs.py` | `MongoOrganisationRecords`: the named cross-tenant class, never a widened `_q` |
| The router | `beats/api/routers/operator.py` | `routers/employment.py`; same error envelope |
| The operator's providers: the client on `app.state`, the organisation service with a refusing `BillingPresence`, `OperatorReads`, `OperatorStore`, the runner | `beats/operator/dependencies.py` | `beats/api/dependencies.py`, which the operator root must not import |
| The IAP assertion → `request.state.operator`; the `Origin` check on every `POST` | `operator_server.py` middleware | the device branch, minus the user id |
| `test_operator.py` (below) | `api/src/` | `TestOrganisationWall` |
| `scripts/dump_openapi_operator.py` → `backoffice/`'s types. It imports `operator_server` with `BACKOFFICE_DEV_OPERATOR` set and an unused DSN, and never runs the lifespan | `api/scripts/` | `dump_openapi.py`, which imports `server:app` under `.env.test` |

`test_operator.py` holds:

- the HTTP contract against `operator_server`;
- **the wall**: a sentinel in every stored thing the right-hand column of
  § *The line* names, found in no byte of any operator response. That means a
  session's note, and its day, years before the run so no account's own dates
  can match it; a project's and a team's name; a tag; an absence note; a
  client's name and rate; a webhook URL's path; a coach message and a memory;
  an integration's token; a biometric value; and an organisation audit
  entry's reason;
- `operator_server`, imported in a fresh interpreter, leaving `beats.settings`
  out of `sys.modules`;
- `server` not importing the operator router;
- a `POST` with a foreign `Origin`, or none, refused;
- `erase_account` leaving `operator_audit` and `operator_jobs` rows and taking
  `account_limits`.

The wall test matters most. It is how "never user content" stops being a
sentence in a roadmap and becomes something CI refuses. So it plants the whole
column, not a sample. The database user reads every collection, and the
likeliest leaks sit beside reads the control plane does make: a webhook's URL
read for its domain, an integration's document read for whether it exists, an
audit event read without its `details`.

**UI: `backoffice/`**

A React 19 SPA on the toolchain `ui/` already runs, because that is the
current stack and the team owns it: React 19.3, TypeScript 7, Vite 8,
Tailwind 4, TanStack Query 5, Zod 4, react-router 8, Biome. (The first draft
proposed Jinja2 and htmx. Against an existing toolchain that is a second idiom
to maintain, not a saving.) It is Feature-Sliced like `ui/`: `app/ pages/
widgets/ entities/ shared/`.

- **It is a pnpm workspace of its own**, rooted at `backoffice/`. `ui/`'s
  workspace is rooted at `ui/` and reaches only `tools/*`, so a sibling can't
  join it without re-rooting, which isn't worth doing for this.
  - `vscode-beats` is not the model, because it is npm with no workspace.
  - `backoffice/` pins the same `packageManager` as `ui/`, and copies what
    `ui/pnpm-workspace.yaml` carries: the security `overrides`, `allowBuilds`
    and the release-age cooldown.
- **The generated types are its own.** `ui/tools/openapi-types` is a package
  of its own because `openapi-typescript` drives the compiler API that
  TypeScript 7 no longer exposes. `backoffice/tools/openapi-types` repeats
  that, with TypeScript `^5.9`, and `renovate.json`'s "TypeScript < 7" rule
  gains its path, or Renovate moves it to 7 and breaks it.
  - A drift check in the shape of `gen:types:check` runs over what
    `dump_openapi_operator.py` writes.
- **Its gates are its own.**
  - `.github/workflows/backoffice.yml` runs lint, type check, tests and the
    drift check. Like `ui.yml`'s `quality` job, it runs on pull requests that
    touch `backoffice/**` or `api/src/**`, and on pushes that touch
    `backoffice/**`. It has no deploy job: Cloud Build ships it.
  - `lefthook.yml` gains `backoffice-check` before each commit (Biome on
    staged `backoffice/` files), and `backoffice-typecheck`, `backoffice-test`
    and `backoffice-api-types` before each push. The last uses the glob
    `{api/src/**/*.py,backoffice/client/shared/api/*}`, the way `ui-api-types`
    does: an API-only change is what stales the types, and it touches nothing
    under `backoffice/`.
  - `.github/labeler.yml` and `.github/release.yml` gain a `backoffice`
    entry.
- **Nothing is shared with `ui/` at first.** The API-client pattern is small
  enough to copy once and let diverge.

It is deliberately **not the sky**: no `SkyBackdrop`, no two hours, a denser
and plainer look. An operator should never be unsure which surface they are
on.

**Infrastructure: `terraform/`**

- **The services.** `beats_operator` is a `google_cloud_run_v2_service` with
  `iap_enabled`, ingress all, and IAP's service agent
  (`service-PROJECT_NUMBER@gcp-sa-iap.iam.gserviceaccount.com`) as its only
  `roles/run.invoker`. It has no `allUsers`.
- **The job.** `beats_operator_jobs` is a `google_cloud_run_v2_job`, started
  by a `google_cloud_scheduler_job` every 15 minutes.
- **The APIs.** `apis.tf` gains `iap.googleapis.com` and
  `cloudscheduler.googleapis.com`. With no load balancer, Compute isn't
  needed. `apis.tf` is not a full record of what is enabled anyway:
  `run.googleapis.com` isn't in it, and the API runs.
- **Alerts.** `alerts.tf` gains the job's failure alert, and a 5xx alert for
  `beats-operator` in the shape of `api_5xx`.
- **Service accounts.** Each new service, the job and the scheduler run as a
  `google_service_account` of their own, never the Compute Engine default
  that `cloudrun.tf` leaves the API on. That account holds `roles/editor` on
  the project, which reads every object in the state bucket: the whole
  Terraform state, the DSN and `JWT_SECRET` included.

  | Account | Holds |
  |---|---|
  | `beats-operator` | `secretAccessor` on `beats-operator-dsn`; `artifactregistry.reader` on the repository; and, once [secret-manager.md](secret-manager.md) has shipped, the deploy-state reads |
  | `beats-operator-jobs` | `secretAccessor` on `beats-jobs-dsn`; `artifactregistry.reader` |
  | `beats-operator-scheduler` | `roles/run.invoker` on the job |

- **The deploy-state reads.** These are what `deploy_lock.sh` reads: the API
  service and its revisions, the tags in the Artifact Registry repository,
  and `beats/deploy.lock` alone, as an object get under a condition on
  `resource.name`. A condition on the name can't narrow a list, so the
  operator never lists the bucket.
  - These wait for [secret-manager.md](secret-manager.md). The API's spec
    carries `JWT_SECRET` and the DSN as plain environment values today, so
    reading the service is reading them.
  - Until then the landing page links to the Cloud Run console instead.
- **Same image for the operator service, same Cloud Build, same deploy
  lock.**

**Credentials.** Each one is a Secret Manager secret, bound to the one account
that reads it. Each value is added by hand with `gcloud secrets versions
add` and never passes through Terraform, which manages the secret containers
and their bindings only ([secret-manager.md](secret-manager.md) § *The shape*,
for the same reason):

| Secret | Read by | Holds |
|---|---|---|
| `beats-operator-dsn` | `beats-operator` | the operator's database user |
| `beats-jobs-dsn` | `beats-operator-jobs` | the job's database user |

Neither account is ever bound to an API secret.

**The database users are not Terraform's.** The database is MongoDB Atlas,
in europe-west1 (`api/README.md`, PRIVACY.md). The users and their custom
roles are made in Atlas by hand. Custom roles work on every Atlas tier, M0 and
Flex included, and a change takes up to 30 seconds to apply. The steps go into
`terraform/README.md`. Atlas's own Terraform provider is not adopted: it would
put an Atlas API key in CI for two users made once.

- **`beats-operator`.** Its role reads every collection, plus `collStats`,
  `dbStats` and `listCollections` for § *Capacity*. The counts need them; the
  wall is in the code and the wall test, not the grant. It **writes only
  these**:
  - `users`: suspension, `sessions_valid_after`;
  - `account_limits`: insert, update and remove;
  - `device_registrations`: `revoked`;
  - `organisations`: closing;
  - `org_members` and `org_audit`: the owner role, and each act's entry;
  - `operator_audit` and `operator_jobs`.

  It creates no index. That list is the grant: a command that needs a
  collection not on it changes this paragraph first.
- **`beats-jobs`.** Its role finds, inserts, updates and removes in every
  collection of the database, because erasure, an organisation's deletion and
  the purge between them touch nearly all of them. It creates no index and
  drops nothing. It is a user of its own, not the API's, so each credential
  can be rotated alone.
- **Network access.** The API reaches Atlas from Cloud Run with no VPC
  connector and no fixed egress, so Atlas's access list already admits
  Cloud Run's addresses. The new services come from the same addresses and
  need nothing more. Confirm it in Atlas when the users are made.

**Nor is IAP's OAuth client Terraform's.** The project, `beats-476914`, sits
in no Google Cloud organisation (checked 2026-11-01), and Google's managed
OAuth client serves only an organisation's internal users. So IAP needs a
custom client: a consent screen for external users, and a web client.

- Both are made by hand in the console; Google's page says no API creates
  one.
- The consent screen can stay in *Testing*, with the operator as its only
  test user: nobody else is meant to get through it.
- The client goes to the service's IAP settings by `google_iap_settings`, if
  that resource carries a custom client for a Cloud Run resource on
  `~> 8.8`, and by hand in the console if it doesn't. Check this when the
  Terraform is written. If it does go through Terraform, its id and secret
  are sensitive tfvars variables.
- The steps go into `terraform/README.md`, beside the one-time GitHub
  connection.

**Every new tfvars variable is added to `beats-terraform-tfvars` before the
change merges.** Cloud Build copies that secret wholesale, so a required
variable it lacks fails every API deploy.

**CLAUDE.md** gains `backoffice/` in the layout table, `/api/operator` in the
routes table, and a line in *Infrastructure* about the second deployment. That
happens when it ships, not before.

## What it does, by the job it serves

### 1. Attention: the landing page

The reason to open it. Each row is a count, linking to the thing.

- **Organisations with no owner** (decision 31). Owner-only acts wait until
  someone notices, and today the only trace is an `account.erased` line in
  that organisation's audit log.
- **Organisations whose every owner is suspended.** They have an owner, so the
  operator doesn't act for them (the decision below; a suspended owner is
  still an owner), but somebody should know.
- **Queued jobs inside their window**, erasures first, and **failed jobs**.
  Erasure requests themselves are not counted here. PRIVACY.md has a person
  ask by email, so a request lives in the operator's inbox until it is queued
  from the account page. Counting them here would take an in-app request,
  which is a product change and a PRIVACY.md change, not a control-plane
  page.
- **What a retention purge would take**, per organisation: the dry run.
  Nothing schedules the purge (decision 30), and nobody is reminded.
- **Accounts over a limit**: coach spend near or past the cap (80% and over),
  and accounts that were refused 429 on a write route in the last seven days.
- **Approvals superseded and never reopened** (`superseded_at`, decision 23)
  for more than 30 days. One standing for months means a decider never saw
  the mark.
- **Absence requests pending more than 14 days.**
- **Deploy state.**
  - The live commit: the API service's latest ready revision, read the way
    `deploy_lock.sh` reads it.
  - Whether `beats/deploy.lock` is held.
  - This waits for [secret-manager.md](secret-manager.md) (§ *Infrastructure*),
    and links to the Cloud Run console until then.

The thresholds are constants in `operator_reads.py`, named and commented.
They decide only what the operator is shown, never what a user is allowed,
so a constant is enough. Changing one is a deploy, and no user notices it.

### 2. Accounts

**Found by exact email or id**, not a browsable list or a prefix search. The
common entry is a support or erasure mail carrying a full address. Exact match
serves that, and is useless for fishing.

Exact, but not case-sensitive. Sign-up stores an address as typed
(`routers/auth.py`), under a unique index with no collation
(`infrastructure/database.py`). So `Ana@example.com` and `ana@example.com`
can be two accounts, and a mail from either spelling must find both. The
lookup asks with a case-insensitive collation and lists every account it
matches. The unique index can't serve that query, so it reads `users` whole.
The query arrives in a `POST` body, never a URL (§ *The routes*).

**One account shows**:

- created, the day last seen, suspension state;
- passkeys and linked providers;
- devices, with each one's last seen;
- organisations and roles;
- counts of projects, sessions and biometric rows;
- a storage estimate;
- coach spend against its cap;
- the integrations connected.

The storage estimate is the sum of `$bsonSize` over the account's documents
in each collection keyed on `user_id`. It is read on this page only, for one
account, through the `user_id` index each of those collections leads with. It
is never computed for a list.

**Actions**: suspend and unsuspend; set or clear a limits override (coach cap,
write ceilings, webhooks off); sign out everywhere (sessions); revoke one
device; queue an erasure (typed confirmation, 7-day window, the account
suspended meanwhile).

**No subject-access export.** A person exports everything themselves
(`/api/export/full`), and an export the operator generates would carry all of
someone's content through the one surface built never to. Someone who can't
sign in to export has an account-recovery problem, not an export one, and
that is a design of its own.

On **sign-in doors**: which identities an account has per provider is a fact
the account *stores*, and fair to show. It is **not** a record of which door a
sign-in used, which the code deliberately does not keep. Don't let one grow
into the other.

### 3. Organisations

**The list shows**:

- name and created;
- members by role;
- active assignments;
- **seat count**, which [docs/pricing.md](../docs/pricing.md) defines and
  [subscriptions.md](subscriptions.md) bills on. Pricing doesn't settle
  whether an owner or admin with no assignment counts. This page shows
  pricing's count, and the question is pricing's, not this page's;
- free-tier position;
- retention years;
- closing state.

**One organisation adds**:

- memberships, with roles and dates;
- how many projects it has, and how many came by a connect;
- timesheets by status;
- its audit log. Each event shows its kind, actor kind, subject and time,
  **without its `details`**, which carry what the organisation wrote: a
  reopened month's `reason`, a created project's or team's name.

**Actions**, while the organisation has no owner and only then, and only on
a request that passes § *The operator's organisation acts*: grant the owner
role to the requester; start, move or cancel a closing notice; queue its
deletion once the notice has run out.

Adjusting a plan or a seat allowance is not one of those acts. It is the
platform's own term with the organisation, not one its owner would have made,
and it waits on #345, which collects the per-seat price
([subscriptions.md](subscriptions.md)).

### 4. Abuse and limits

**Detection** works by outlier rather than by a guessed threshold:

- coach spend per account;
- flow windows per account per day. The daemon is the heaviest writer, and
  100× the median is a broken or hostile one;
- sessions and projects created per day, and import sizes;
- **report links minted per account**: `/api/reports` is the only public path
  serving a user's data;
- **webhook destinations by domain**: outbound HTTP from our servers to
  arbitrary URLs is ours to answer for;
- pairing codes and devices per account;
- signups per day and provider.

Abuse that shows in requests rather than in accounts (rejections under
`/api/`, and guessing at sign-in, report links or pairing codes) is already
counted and alerted on in Cloud Monitoring
([terraform/README.md](../terraform/README.md#monitoring)). This section is the
half that needs the database.

**Controls**: `account_limits` overrides, read at the API's enforcement
points (coach cap, write ceilings, webhooks off); suspension; and revoking one
device, the narrow answer to one broken daemon.

### 5. Capacity and cost

- Documents and storage per collection, with growth (`$collStats`).
- Write volume per day, by kind.
- Distributions as percentiles rather than lists.
- **Coach cost** from `llm_usage`, as a platform total by day and model, with
  the cache-hit ratio (`cache_read_input_tokens` against input). That is a
  new pipeline in `operator_reads.py`: `UsageTracker.usage_summary`, the "cost
  dashboard" its docstring names, is one account's own `/api/coach/usage`, by
  day and not by model.

**Latency, error rates and instance counts are Cloud Monitoring's**, on the
dashboard `terraform/monitoring.tf` already builds. Link to it; don't rebuild
it.

### 6. Compliance operations

- The job queue, erasures first.
- Retention due per organisation, and queueing the purge for one organisation
  or for all.
- The operator audit, readable and filterable, editable by nobody, kept four
  years.

## What must not happen

- **No "view as this user", ever.** PRIVACY.md admits the operator can read
  any document, and promises not to log into an account or read its sessions
  without a reason. A button would make reading an account the everyday tool,
  and make the home page's "we don't watch you" false.
- **No user content**, per the table. No page, export or CSV carries a note, a
  tag, a project name, an audit entry's details or a figure from someone's
  record. The wall test enforces it.
- **No free-text search** over content, and none over addresses beyond the
  exact-match lookup. **No address in a URL.**
- **No destructive act in a request handler.** Erasure, the purge and an
  organisation's deletion are jobs, with a typed confirmation and a window.
- **`server.py` never imports the operator router.** That import, absent, is
  the isolation: not a flag, not a conditional. A test pins it for the day
  somebody adds one.
- **No rule lives in a command or the runner.** They resolve, authorise,
  audit and delegate. A guard written there is a guard that will disagree with
  the one the member-facing route enforces.
- **No mutation outside the command runner**, or the audit becomes a thing
  people remember to write.
- **No operator collection keys its subject on `user_id`** except
  `account_limits`, or erasure's sweep deletes the record of the erasure.
- **The operator deployment's database user writes only the collections
  listed under *Infrastructure***, and builds no index, whatever the code
  claims to do.
- **The operator deployment never holds `JWT_SECRET`.** Holding it is holding
  every user's session. A test imports `operator_server` in a fresh
  interpreter and finds no `beats.settings` in `sys.modules`.
- **The operator does not act for an organisation that can act for itself,
  nor unasked.** Granting the owner role, closing and deletion are refused
  while the organisation has an owner.
- **Nothing silent inside an organisation.** An operator act on one lands in
  its own audit log, under an actor kind its admins can tell is the operator.
- **Reads go through the named narrow classes.** Never by widening
  `MongoStore._q`, never by handing an existing service a wider scope.
- **No client drops a write because the account is suspended.**
- **It does not become customer support** with a deeper tier of access because
  someone asked a question it can't answer. That is a new decision with a new
  PRIVACY.md sentence, not a patch.

## Work

What is owed, step by step. Each step ships alone, in the commits CLAUDE.md
asks for: code before its tests, API and UI apart. When a step ships, its part
of this file moves to `docs/` (roadmaps/README.md § *When something ships*).

### Step 1: enforcement in the public API

**Shipped 2026-11-04.** What it built — suspension end to end, sign-out
everywhere over `auth_time`, the two last-seen stamps, `account_limits` and
the write ceilings, `contact_email`, and each client's handling of a refusal
— is [docs/account-controls.md](../docs/account-controls.md). The write-limit
defaults ship off; turning one on starts with the traffic check that file
describes.

### Step 2: the operator deployment, read-only

- `database.py` off the settings singleton, and every caller of `connect()`.
- `operator_server.py` with its own client, `OperatorSettings`, the IAP
  verifier, the allowlist, the `Origin` check, `request.state.operator`, and
  the static UI.
- `MongoOperatorReads` and the read routes.
- `test_operator.py`'s wall, the fresh-interpreter import test, and the
  "`server` imports no operator router" test.
- `backoffice/`: the workspace, the generated types and their drift check, the
  pages, and the gates and workflow listed under § *UI*.
- Infrastructure:
  - the operator's database user and secret, made by hand;
  - the OAuth client and consent screen, made by hand;
  - `beats_operator`, its service account and `apis.tf`;
  - the Cloud Build step and the trigger's `backoffice/**`;
  - the tfvars secret updated first;
  - the README steps.

### Step 3: inline commands

- The runner, the command protocol, `operator_audit`, and `POST
  /commands/{name}`.
- The account commands and `device.revoke`.
- `OrgAuditEvent.actor_kind`, the one `org_audit` writer, and the SPA's "by
  LifePete".
- The organisation twins, the request rule, `ORGANISATION_HAS_OWNER`, and a
  closing notice that may always move later.
- `docs/organisations.md`'s decisions 10, 29 and 31 amended in the same
  change.
- PRIVACY.md: operator acts are audited, in the organisation's own log too.

### Step 4: jobs and the irreversible work

- `operator_jobs`, `MongoOperatorJobs`, `beats.operator.jobs`, `job.cancel`.
- `beats_operator_jobs`, the scheduler, their service accounts, the job's
  database user and secret, and the failure alert.
- `account.erase`, with its window and suspension, and `operator_audit` and
  `operator_jobs` off `user_id`, tested against the sweep. The erasure script
  changed to an id or a case-insensitive list.
- `delete_organisation`'s re-run checked and pinned. Then
  `organisation.delete`.
- `purge_expired_records(organisation_id=…)`, the operator audit's four years,
  then `retention.purge`.
- PRIVACY.md: the 7-day window and the suspension during it, and how long the
  operator audit is kept. DATA.md: `operator_audit`, `operator_jobs`,
  `account_limits`.

### Decided in the 2026-11-04 review

Each was open, and each went the way the reasoning beside it gives. If one of
them is wrong, it is cheaper to say so now than after step 1.

| Decision | Why |
|---|---|
| One service behind Cloud Run's IAP; no load balancer | About $18 a month standing buys one person nothing; Cloud Run's IAP works for a project with no organisation |
| A suspended owner is still an owner | Otherwise suspending an owner hands the operator their organisation |
| The owner role goes to the requester holding the organisation's highest role | Picking among members is taking a side |
| A closing notice may always move later | The 30-day minimum protects members, and a later day only gives them more |
| Erasure: 7-day window, the account suspended meanwhile | Time to catch a mail that wasn't the holder's; well inside GDPR's month |
| `operator_audit` holds ids, not addresses, for four years | It outlives the account it names; the platform's default retention |
| The job is a third database user | Each credential rotates alone; the operator's stays narrow |
| The retention purge stays unscheduled | Decision 30, PRIVACY.md and the DPA all promise an operator runs it |

### Needs the owner

- **What Cloud Build's service account really holds.** `cloudbuild.tf`
  grants it `run.admin`, `iam.serviceAccountUser`, `logging.logWriter`, the
  tfvars secret, the state bucket and `artifactregistry.writer`. That isn't
  enough to create service accounts, Secret Manager secrets, IAM bindings,
  enabled APIs, IAP settings or a scheduler job. The monitoring and IAM
  resources that already apply suggest more was granted by hand, and nothing
  in the repo says what. Run:

  ```
  gcloud projects get-iam-policy beats-476914 \
    --flatten="bindings[].members" \
    --filter="bindings.members:cloudbuild" \
    --format="table(bindings.role)"
  ```

  - **If it holds `roles/editor` or more**, CI applies the new resources as
    it applies everything else.
  - **If not**, the recommendation is that the owner runs the first apply
    that creates them, from a machine holding Owner, and CI's steady-state
    applies only refresh them. Granting CI IAM-admin roles for a one-time
    creation would leave it holding them.
