# A back office for the operator

Somewhere for the operator to stand. Issue **#424**.

LifePete has one operator — PRIVACY.md says so in those words — and no place
to look at the platform from. Everything an operator does today is a script
in `api/scripts/` run by hand against production, and everything an operator
should *notice* is noticed only if they happen to go looking.

Split out of [roadmaps/organisations.md](organisations.md) on 2026-10-31 and
designed on 2026-11-01. It was filed under that epic because an organisation
left without an owner (decision 31) was the first thing anyone wanted to see;
a back office is not an organisations feature, and tying it there would have
shaped an operator surface around one view of one thing.

---

## What it is, in one line

**A dashboard of numbers about the platform, which cannot show a person's
data.** Not a support console, not an admin panel over the database: a place
that answers "how is it going, and what needs attention?" without ever
answering "what did Nadia do last Tuesday?"

## Why a surface that refuses data is worth building at all

The operator can already read any document in Mongo. PRIVACY.md says so
rather than pretending a single-operator service has a boundary it does not.
So a back office adds no power — and that is the point. It is **a narrower
door than the one that already exists**, and it earns its place four ways:

1. **Every question it answers is a `mongosh` session that does not happen.**
   Today "how many organisations have no owner?" means opening a shell
   against production, a tool with no limits and no record. The back office
   answers that without reaching for it.
2. **It is auditable.** A page view can be logged; a shell cannot.
3. **It survives growth.** One operator today. The boundary is what makes a
   second one — or a contractor, or a bought-in support hand — safe to add
   without a redesign.
4. **It lets PRIVACY.md eventually say something stronger.** Not yet, but
   that sentence can only tighten once routine operation stops needing the
   wide credential.

## Architecture

### A separate service, at `backoffice/`

A sibling of `api/`, `ui/` and `daemon/` in the repo layout, deployed on its
own.

The reason is the user-facing API's one mechanical guarantee: `MongoStore._q`
stamps `{"user_id": ...}` onto every query, and the handful of readers that
cross users are named, narrow classes (`MongoOrganisationRecords`,
`MongoReportLinkLookup`). A back office route is cross-tenant **by
definition**. Put it in the same app and that app contains both "everything
is scoped" and "nothing is scoped", and the next person adding a route has
to know which half they are standing in. Kept apart, the rule in the API
stays absolute, which is worth more than the code reuse.

### Stack: FastAPI + Jinja2 + htmx, server-rendered

Python because it is the house language and the Mongo driver, the settings
pattern, the Dockerfile and the Cloud Build shape are all already here.
**Server-rendered, not a second SPA**: a dashboard a handful of people open
does not justify a second React build, a second type-generation pipeline
(`pnpm gen:types`) and a second in-browser auth story. htmx covers the
interactive parts — a date-range change, a sortable table — without any of
that.

Charts: a server-rendered SVG or a single small charting library. No
analytics or telemetry SDK in this page; see *What must not happen*.

**Considered and rejected: a BI tool** (Metabase, Grafana) pointed at Mongo.
It is the cheapest answer by far, and it is the wrong one: it works by giving
whoever opens it query access to collections, which is exactly the thing this
design exists to stop. A tool whose core feature is "write your own query"
cannot also promise "shows no personal data".

### Auth: Google IAP, no login code

Cloud Run with ingress restricted and **Identity-Aware Proxy** in front. The
operator signs in with a Google account at the edge; the service implements
no login, no session, no passkey, no token. Who may enter is an IAM policy,
not a row in a database. On a privileged surface, the best auth code is none.

Locally, a `BACKOFFICE_DEV_OPERATOR` env var stands in for the IAP header,
the way `BEATS_TEST_ENV` already stands in for testcontainers.

### Database: the same Mongo, with a read-only credential

Not a replica, not a pipeline — the scale does not call for it. What matters
is that the credential is a **read-only database user**, so the service
*cannot* write even if the code tried. That is a boundary enforced outside
the code, which is the only kind that survives a bug.

A consequence worth planning for: the audit trail cannot go in Mongo.
It goes to **Cloud Logging** as structured logs — which is where Cloud Run
already records every request URL for 30 days anyway. (Neat inversion: that
same URL logging is why `/api/reports` keeps its token in a header. Here the
logging *is* the feature.)

### It talks to nothing else

It does not call the user-facing API, and the API does not call it. No shared
process, no shared deploy, no shared service account.

**No shared code either, at first.** Tempting to import
`api/src/beats/domain/models.py`, but a stats service counts documents rather
than hydrating them, so the models buy little and the coupling costs a joint
deploy. The real coupling is to collection and field *names*, and it exists
either way. Mitigate it where it can actually be caught: **run every
aggregation pipeline against the API's own testcontainers fixtures in CI**,
so a renamed field fails a test instead of silently zeroing a chart.

## The rule that makes "no personal data" mechanical

The repo already knows that a filter applied after the fact is not a
boundary. The same shape applies here:

> **No read returns a document. Every read is an aggregation that returns
> counts, buckets, distributions or time series.**

Not "fetch and strip the fields" — `find()` over user content does not appear
in this codebase at all. The things it legitimately shows per row are facts
about an *organisation* or about a *relationship*, never about a person's
content:

| Shown | Not shown |
|---|---|
| An organisation's name, created date, settings | Any project name, session note, tag, absence note |
| Counts, roles, dates on a membership | A member's name or email address |
| An account as an opaque id, and its dates | Anything the account wrote |
| Distributions and percentiles | Any individual's figures |

## What it shows

### 1. Needs attention — the first screen

The reason to open it at all. Each row is a count with a link to the detail.

- **Organisations with no owner** (decision 31). Owner-only acts — granting
  the owner role, closing, deleting — wait until someone notices. Today the
  only trace is an `account.erased` event in that organisation's audit log,
  which nobody reads unless they already suspect.
- **What a retention purge would take.** `scripts/retention_purge.py` is
  operator-run and dry by default, and nothing schedules it (decision 30), so
  nothing has auto-deleted during the beta. Showing the dry run's counts per
  organisation is exactly the nudge that is missing.
- **Approvals superseded and never reopened.** A contract write marks the
  approved months it moves (`superseded_at`, decision 23). One left standing
  for months means a decider never saw the mark — a signal the feature is
  not landing, and the kind of thing only an aggregate reveals.
- **Absence requests pending beyond a threshold**, as a count per
  organisation. Someone is waiting on a decider who has stopped looking.
- **Timers running absurdly long** — over, say, 24 hours. A count, not a
  list: it is either a forgotten stop or a bug, and both are worth knowing.
- **Deploy state**: the live commit, and whether `beats/deploy.lock` is held.
  `terraform/README.md` documents checking this by hand.

### 2. Growth

- Accounts: total, created per day/week, and the active/dormant split by
  "tracked anything in the last 7 / 30 / 90 days".
- Erasures over time.
- **Sign-in doors, carefully.** How many accounts hold a passkey, an OIDC
  identity, or both, and the count per configured provider — useful for
  deciding whether a provider is worth keeping configured. This reads
  `identities[]`, a fact the account *stores*; it is **not** a record of
  which door was used for a sign-in, which the code deliberately does not
  keep (`routers/sso.py` logs neither provider nor account). Do not let this
  statistic grow into that.

### 3. Usage and capacity

- Sessions written per day; flow windows per day — the daemon is the heaviest
  writer and its volume is what sizes the database.
- Documents and storage per collection, with growth. There are 28 indexed
  collections; knowing which is growing is how the next bill is predicted.
- Distributions rather than lists: projects per account, sessions per
  account, organisations per account — as percentiles.
- **Coach cost.** `llm_usage` already records model, tokens, cache hits and
  `cost_usd` per call, and `UsageTracker.usage_summary` is already described
  in its own docstring as being "for the cost dashboard". Its per-user shape
  becomes a platform total here: spend per day, split by model, and the
  cache-hit ratio, which is the lever on the bill.

### 4. Organisations

A table, one row per organisation — organisation facts, no personal data:

- name, created, timezone, holiday country, retention years, closing state;
- members by role (owner / admin / manager / viewer / member), and how many
  have an active assignment — which is the **seat count**
  ([docs/pricing.md](../docs/pricing.md) defines it; it is the number
  [subscriptions.md](subscriptions.md) will bill on);
- projects, and how many are connected rather than created;
- timesheets by status, and whether any month is approved;
- free-tier position: at, near or over five seats.

Drilling into one organisation shows its memberships as **role + dates +
account id** — enough to answer "who are the admins of this ownerless
organisation?", which is decision 31's whole purpose — and never the name or
address `org_members` happens to store.

## The one deliberate exception: finding an account to erase

PRIVACY.md tells people to email the operator from the address on their
account, and `scripts/erase_account.py` takes an account id. Something has to
bridge the two, and it is the only thing here that touches an address.

**An exact-match lookup**: paste a full address, get back whether an account
exists and its id. Nothing else — no list, no prefix or partial search, no
"find users like…", no browsing. Exact match only is what makes it
unusable for fishing, and the lookup is audited by the operator's identity
with the address hashed, not written, in the log.

It does **not** perform the erasure. See below.

## What must not happen

- **No route returns a document.** This is the whole design; a single
  convenience `find()` undoes it.
- **No "view as this user", ever.** Every admin panel grows one. It would
  turn a statistics surface into an impersonation surface and make every
  promise above false at a stroke.
- **No free-text search** over projects, notes, tags, or anything a person
  wrote — and no search over addresses beyond the exact-match lookup.
- **No write path, and no destructive buttons.** Erasure and the retention
  purge stay operator-run scripts. The back office may *show that they are
  due*; it must not run them. A read-only credential is a boundary a bug
  cannot cross, and the moment one button writes, that is gone — a confirm
  dialog is not the same kind of thing.
- **No personal data in an export or a chart label.** If a CSV falls out of
  this, it carries the same aggregates the page does.
- **No analytics or session-replay SDK on these pages.** Obvious, and worth
  writing down: the product refuses them on the marketing page under
  stricter conditions than apply here.
- **It reads through its own narrow classes**, as
  `MongoOrganisationRecords` does — never by widening `MongoStore._q`, and
  never by handing an existing service a wider scope. An operator surface is
  cross-tenant by nature, which makes it the most likely place for the next
  careless cross-user read; the rule in
  [roadmaps/organisations.md](organisations.md) — *widen a collection
  boundary, never a serialiser* — is not an organisations rule, it is the
  rule, and this is the surface most able to break it.
- **It does not become customer support** with a second tier of access
  because someone asked a question it cannot answer. That is a new decision,
  with a new PRIVACY.md sentence, not a patch.

## Open, for when it starts

- **Cost.** IAP needs a load balancer, which has a standing monthly cost
  disproportionate to one dashboard. The alternative — ingress-internal plus
  a tunnel, or Cloud Run's own IAM invoker check with `gcloud proxy` — is
  cheaper and clumsier. Worth pricing before committing.
- **The erasure lookup** above is the one place the "no personal data" line
  bends. It is proposed, not settled.
- **Where the aggregates run.** Every pipeline on request is fine at this
  size and will not stay fine; a nightly roll-up into a small stats
  collection is the obvious next step, and it needs a write credential,
  which is a boundary change. Do not design for it now — note that it is the
  first thing that will ask to break the read-only rule, so it is decided
  deliberately when it does.
