# The control plane

The operator's UI for **running the platform**. Issue **#424**.

LifePete has one operator — PRIVACY.md says so in those words — and no place
to run it from. Every operator act today is a script in `api/scripts/` fired
by hand at production, every setting is a constant that needs a redeploy to
change, and everything an operator should *notice* is noticed only by going
to look.

Split out of [roadmaps/organisations.md](organisations.md) on 2026-10-31 and
designed on 2026-11-01. It was filed under that epic because an organisation
left without an owner (decision 31) was the first thing anyone wanted to see;
a control plane is not an organisations feature, and tying it there would
have shaped it around one view of one thing.

---

## What it is, and what it is not

**A control plane: pages organised around what the operator is trying to do.**
Find the account a support mail came from and act on it. Fix an organisation
whose owner is gone. Find who is burning the coach budget and cap them.
See whether storage growth is about to cost money.

**Not a Django admin.** Not one page per collection with a CRUD form on it.
A table-shaped admin makes the operator translate every real question —
"who is abusing this?" — into four screens of joins, and it makes the
dangerous act (edit this document) the easiest one on the page.

**Not a dashboard either.** Statistics are in it because they serve two
operator jobs — predicting what the platform will cost and cost us next
quarter, and catching use that has turned into abuse — not because a wall of
charts is the goal.

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
rather than pretending otherwise. That is exactly why this line is worth
drawing: **every question the control plane answers is a `mongosh` session
against production that does not happen.** The wide credential stops being
the everyday tool and becomes the exceptional one — which is also what makes
a second operator, or a contractor, safe to add later.

## The finding that shapes the work

**A control plane can only control what the API enforces, and today the API
enforces almost none of it.** Checked on 2026-11-01:

| The operator wants to | What exists now | What the API must grow first |
|---|---|---|
| Suspend an abusive account | **Nothing.** No flag on `User`, no check anywhere | A suspension field, checked once in the auth middleware (`src/server.py`) |
| Sign someone out everywhere | `SessionManager._revoked_tokens` is an **in-memory dict per instance**; Cloud Run runs several and scales to zero | Shared revocation — or accept the bound below |
| Cap one account's coach spend | `settings.coach_monthly_budget_usd`, **one global number** for everybody | A per-account limits document the budget check reads |
| Rate-limit one abuser | `@limiter.limit` decorator constants keyed on IP, per instance | Per-account limits, from the same document |
| Disable a webhook | `Webhook.active` **already exists** | Nothing — this one works today |

So most of the value here is unlocked by **small enforcement points in the
API**, and the back office is the UI over them. Build them in that order; a
control plane whose controls do nothing is a viewer with buttons.

On revocation, be accurate about severity rather than alarmed: `SESSION_TTL`
is 3600, so a revoked token dies within the hour anyway. The real gap is
that `refresh_token` mints a fresh hour on each call, so a session in active
use renews indefinitely and no instance but one knows it was revoked. "Sign
out everywhere" cannot be honest until that is shared state.

## Architecture

### A separate service at `backoffice/`

A sibling of `api/`, `ui/` and `daemon/`, deployed on its own.

The user-facing API's one mechanical guarantee is that `MongoStore._q`
stamps `{"user_id": ...}` onto every query, with the handful of cross-user
readers named and narrow (`MongoOrganisationRecords`,
`MongoReportLinkLookup`). A control-plane route is cross-tenant **and
privileged** by definition. Put it in the same app and that app holds both
"everything is scoped" and "nothing is", and the next person adding a route
has to know which half they are in. Apart, the API's rule stays absolute.

### FastAPI + Jinja2 + htmx, server-rendered

Python because it is the house language and the driver, settings, Dockerfile
and Cloud Build shapes already exist. **Server-rendered, not a second SPA**:
a surface a handful of people open does not justify a second React build and
a second `pnpm gen:types` pipeline, and a privileged page is better off with
no bearer token living in a browser at all. htmx covers the forms,
confirmations and sortable tables a control plane is made of.

**Considered and rejected: a BI tool** (Metabase, Grafana) over Mongo. It
cannot act, and it works by handing whoever opens it query access to
collections — the opposite of the line above.

### Google IAP, and two operator roles

Cloud Run with restricted ingress and Identity-Aware Proxy in front. The
service implements no login: no session, no passkey, no token. Who may enter
is an IAM policy. On a surface that can suspend accounts, the best auth code
is none.

Two roles from the start, because they will be needed before a second person
is: **viewer** (everything above, read) and **operator** (the actions). A
contractor or a support hand should be able to look without being able to
act. Locally a `BACKOFFICE_DEV_OPERATOR` env var stands in for the IAP
header, as `BEATS_TEST_ENV` already stands in for testcontainers.

### Mongo with a scoped write grant

Not read-only — a control plane acts — but **not wide either**. A database
user that reads what it shows and writes only the collections the controls
touch: `users` (suspension), `org_members` (an owner grant), `organisations`
(closing), `webhooks` (disable), and two new ones, `account_limits` and
`operator_audit`. It must hold **no write grant on `timeLogs`, `absences`,
`projects` or any content collection** — a boundary outside the code is the
only kind that survives a bug in it.

### Wide and destructive work runs as a job, not in the web process

Erasure and the retention purge touch every collection and are irreversible.
They must not be a button in a request handler holding a wide credential.

The back office **enqueues**; a separate **Cloud Run Job** with the wide
credential executes, running the same `infrastructure/erasure.py` and
`infrastructure/retention.py` code the scripts already call. That buys three
things for free: the narrow grant above stays narrow, the act is auditable
at both ends, and a queued irreversible act can sit for a cancellation
window before it runs.

### Audit, in two places

Every operator action writes to an append-only `operator_audit` — who, what,
when, and the before-and-after of what changed.

**And an action that touches an organisation also writes to that
organisation's own `org_audit`**, which its admins already read. An operator
promoting someone to owner is visible to the people it affects. This is the
product's own value applied to its operator: nothing about you happens
invisibly.

Page views and reads go to **Cloud Logging** as structured logs, which is
where Cloud Run already records every request URL anyway. (A neat inversion:
that same URL logging is why `/api/reports` keeps its token in a header —
here the logging *is* the point.)

### It talks to nothing else

It does not call the user-facing API, and the API does not call it. No shared
process, deploy, or service account. **No shared code at first** either: a
control plane reads aggregates and writes a handful of fields, so importing
`api/src/beats/domain/models.py` buys little and costs a joint deploy. The
real coupling is to collection and field names, and the way to catch that is
to **run every query against the API's own testcontainers fixtures in CI**,
so a renamed field fails a test instead of silently emptying a page.

## What it does, by the job it serves

### 1. Attention — the landing page

The reason to open it. Each row a count, linking to the thing.

- **Organisations with no owner** (decision 31). Owner-only acts — granting
  the role, closing, deleting — wait until someone notices, and the only
  trace today is an `account.erased` line in that organisation's audit log.
- **Erasure requests waiting**, and any queued erasure inside its
  cancellation window.
- **What a retention purge would take**, per organisation. The script is dry
  by default and nothing schedules it (decision 30), so nothing has
  auto-deleted during the beta — and nobody is being reminded either.
- **Accounts over a limit**: coach spend near or past the cap, storage or
  write-rate outliers.
- **Approvals superseded and never reopened.** A contract write marks the
  approved months it moves (`superseded_at`, decision 23); one standing for
  months means a decider never saw the mark.
- **Absence requests pending beyond a threshold** — someone waiting on a
  decider who stopped looking.
- **Deploy state**: the live commit, and whether `beats/deploy.lock` is held.

### 2. Accounts

Find one by **exact email or id** — not a browsable list, not a prefix
search. The common entry is a support or erasure mail, which carries a full
address; exact-match is enough for that and useless for fishing.

One account shows: created, last active, suspension state, how many passkeys
and which providers are linked, devices paired, organisations and roles,
counts of projects / sessions / biometric rows, storage estimate, coach spend
this month against its cap, and which integrations are connected.

**Actions**: suspend and unsuspend, set or clear a limits override, force
sign-out, queue an erasure (typed confirmation, cancellation window), and
generate a data export for a subject-access request.

On **sign-in doors**: the count of linked identities per provider is a fact
the account *stores* and is fair to show. It is **not** a record of which
door a sign-in used, which the code deliberately does not keep
(`routers/sso.py` logs neither provider nor account). Do not let one grow
into the other.

### 3. Organisations

A list with name, created, members by role, active assignments, **seat
count** ([docs/pricing.md](../docs/pricing.md) defines it; it is what
[subscriptions.md](subscriptions.md) will bill on), free-tier position,
retention years, and closing state.

One organisation adds: its memberships with roles and dates, projects and how
many were connected rather than created, timesheets by status, and its audit
log.

**Actions**: grant the owner role to an existing admin — the answer to
decision 31, which deliberately refuses to auto-promote but leaves somebody
having to act; start or extend a closing notice; delete after the notice;
and later, adjust the plan or a seat allowance.

### 4. Abuse and limits

The job the owner named: catching use that has become abuse, and stopping it.

**Detection** — leaderboards and outliers rather than thresholds somebody has
to guess:

- coach spend per account this month, against the global cap;
- flow windows written per day per account. The daemon is the heaviest
  writer, and an account at 100× the median is a broken or hostile one;
- sessions and projects created per day, and import sizes — the backup import
  is the one route that writes in bulk;
- report links created per account: `/api/reports` is the only public path
  serving a user's data, and minting links is the way to widen it;
- webhook destinations by domain. Outbound HTTP from our servers to an
  arbitrary URL is ours to answer for, and `Webhook.active` already exists to
  switch one off;
- pairing codes and device registrations per account;
- signups per day and per provider, which is where an `allow_signup`
  misconfiguration shows.

**Controls**: per-account limits in `account_limits` — a coach budget
override, a write-rate ceiling — read by the API at its enforcement points;
suspension; and disabling a single webhook.

### 5. Capacity and cost

For predicting, not for staring at.

- Documents and storage per collection with growth — 28 indexed collections,
  and knowing which is growing is how the next bill is foreseen.
- Write volume per day by kind: sessions, flow windows, signals.
- Distributions rather than lists — projects per account, sessions per
  account — as percentiles.
- **Coach cost.** `llm_usage` already records model, tokens, cache hits and
  `cost_usd` per call, and `UsageTracker.usage_summary` calls itself "for the
  cost dashboard" in its own docstring. Its per-user shape becomes a platform
  total: spend per day by model, and the cache-hit ratio, which is the lever.
- **Latency, error rates and instance counts are Cloud Monitoring's.** Link
  to it; do not rebuild it. What belongs here is what Cloud Monitoring cannot
  know — the domain shape of the data.

### 6. Compliance operations

- The erasure queue: requested, scheduled, cancelled, done.
- Retention: what is due per organisation, and running the purge as a job.
- A subject-access export for an account.
- The operator audit itself, readable and filterable, and not editable from
  the UI by anyone.

## What must not happen

- **No "view as this user", ever.** Every admin panel grows one. It would
  contradict PRIVACY.md directly — the operator does not log into accounts —
  and make a product whose pitch is "we cannot watch you" false.
- **No user content**, per the table above. No page, export or CSV carries a
  note, a tag, a project name or a figure from someone's record.
- **No free-text search** over content, and none over addresses beyond the
  exact-match lookup.
- **No destructive act in the web process.** Erasure and the purge are jobs,
  with a typed confirmation and a cancellation window. A confirm dialog in
  front of an irreversible wide-credential write is not a safety property.
- **Nothing silent inside an organisation.** An operator act that changes a
  membership lands in that organisation's own audit log.
- **No write grant on content collections**, whatever the code claims to do.
- **It reads through its own narrow classes** — never by widening
  `MongoStore._q`, never by handing an existing service a wider scope. The
  rule in [roadmaps/organisations.md](organisations.md), *widen a collection
  boundary, never a serialiser*, is not an organisations rule; it is the
  rule, and this is the surface most able to break it.
- **It does not become customer support** with a deeper tier of access
  because someone asked a question it cannot answer. That is a new decision
  with a new PRIVACY.md sentence, not a patch.

## Open, for when it starts

- **Order.** The API enforcement points come first or alongside; the
  suspension flag is the smallest and unlocks the most.
- **Cost.** IAP needs a load balancer with a standing monthly charge out of
  proportion to one internal page. Ingress-internal plus a tunnel, or Cloud
  Run's IAM invoker check, are cheaper and clumsier. Price it before
  committing.
- **PRIVACY.md.** Suspension and operator actions are new facts about what
  happens to an account; the page should say so before the first one ships.
- **Pre-computed aggregates.** Running every query per request is fine at
  this size and will not stay fine. A nightly roll-up needs a write
  credential on a stats collection — the first thing that will ask to widen
  the grant, so it is decided deliberately when it does.
