# Organisations — roadmap

> LifePete is a personal tracker: one person, their projects, their time. The
> two biggest revenue sources are groups of people — companies that must record
> their employees' hours, and freelancers who bill clients. Most trackers solve
> that by splitting people up: a work account per employer, a personal account
> at home. This does the opposite. A person has **one account and one
> timeline**, and each party sees only its own slice.

That rule is the product, not a constraint on it. A tracker that already knows
your flow, sleep and heart rate becomes a surveillance tool the moment an
employer can see any of it. Draw the wall correctly and we can sell what
Hubstaff-style tools cannot: working-time records a works council can sign off
on, *because* they cannot be used to watch anyone.

**Where this document sits.** `CLAUDE.md` says open work lives in Linear and
that docs hold decisions and designs, never to-do lists. This file is a
deliberate exception while the Linear workspace is unreachable from the
development environment: it holds the staging of the epic and the decisions
still open, in one place, so the plan is legible without it. When Linear is
reachable again each stage below becomes an issue under the epic, each open
decision becomes a `decision` issue, and this file is trimmed to the design
reasoning it records — the stage lists go, the decisions and the architecture
notes stay.

---

## The four rules the code has to keep

Everything below is in service of these. They are the reason the architecture
looks the way it does, and the reason some obvious shortcuts are not taken.

1. **One person, one account, one timeline.** Joining an organisation never
   creates a second account, never moves existing data, and never needs a
   different login. You can leave every organisation and still have your
   account.
2. **Every project has exactly one owner** — you, or an organisation. What
   anyone else sees follows from that, and from nothing else.
3. **Hours, not the person.** On its own projects an organisation sees start,
   end, duration, the entry's note, absences, the contract balance and
   timesheet status. Flow scores, apps, repos, idle time, biometrics, the
   coach and its memory, calendar, insights, and personal projects — including
   their existence — never cross. No admin setting changes this. We never build
   screenshots, activity percentages or keystroke counts.
4. **Nothing is retroactive without consent.** Linking an existing project to
   an organisation shares history only from a date the person chooses.

And one that follows from them: **the person can always see what the
organisation sees**, on a "What Acme can see" page written in plain sentences,
showing the actual data held.

---

## Where we are

| Stage | What | State |
|---|---|---|
| **1** | Clients for freelancers | **Done** — 1a and 1b on `main`, 1c built on `feat/ahm-74-1c-report-links` |
| **2** | Foundations: organisations, membership, org projects, leaving | Not started; three decisions open |
| **3** | Employment: employer contracts, leave requests, timesheet approval | Not started; depends on 2 |
| **4** | Scale: teams, money permission, SSO, SCIM, audit, per-seat billing | Not started; depends on 2 and 3 |

Stage 2 is the only one that changes the data model. Stages 3 and 4 are
additive on top of it. That makes the sequencing question simple: get the
ownership model right and the rest is ordinary work.

---

## Stage 1 — Clients for freelancers · **Done**

Section 4 of the epic without its client-organisation part. It needed no
organisations, which is why it went first, and it sells to one of the two
target groups on its own. The decisions are recorded in
[docs/billing.md](billing.md); the summary here is only to say what exists.

1a and 1b are on `main`. 1c is built and green on
`feat/ahm-74-1c-report-links` and has not been merged yet; nothing in stages 2
to 4 depends on it landing first.

- **1a — clients and billing.** Clients as records in your own account, one
  currency each, dated default rates; a freelance project billed to a client
  under dated terms carrying both the billable flag and the rate; a billable
  mark per entry; the month's report per client and per currency. Money is
  integer minor units everywhere. The closed past is gated server-side
  (`RETROACTIVE_CHANGE`).
- **1b — billing budgets.** A limit on a client or a billed project, in hours
  or money, monthly or in total. Only the limit is stored; spend, remaining,
  state and projection are derived on every read.
- **1c — report links.** A link naming one client and a fixed range, which the
  client opens with no account. Amounts and per-entry rows are each opt-in.
  Served by `assemble_client` from that client's inputs alone, through a
  response schema written field by field, under the one public prefix that
  serves user data.

Three decisions from this stage carry forward into organisations, because they
are the same problems one step smaller:

- Billing lives in **its own collections**, never as fields of `Project` or
  `Beat`, so a contractor's rates stay on the far side of a collection
  boundary rather than behind a serialiser someone must remember.
- A reader of one client **cannot reach another's** because the query for
  another's is never made — not because a filter removed it afterwards.
- A report says **nothing about now**: no `running` flag, so an invoice's
  backing cannot be used to see whether someone is working at this moment.

---

## Stage 2 — Foundations

**Goal:** an organisation can exist, have members, own projects that appear on
each member's own timeline, and be left — with the wall of rule 3 enforced
structurally rather than by vigilance.

Sections 1, 2 and 6 of the epic.

### Scope

- Organisations: name, logo, week start, default holiday region, timezone.
- Joining by **email invite** and by **invite link** with an optional approval
  step. Verified domains, SSO and SCIM are stage 4.
- Roles **Owner / Admin / Member**. Manager, Viewer and the money permission
  are stage 4.
- Organisation-owned projects, assigned to members, appearing in each member's
  project list marked with the organisation's name and logo. Tracking works
  exactly as it does today — timer, manual entries, auto-timer suggestions, the
  companion, the menu bar and the wall clock make no distinction.
- Filters over one timeline: *Everything · Personal · Acme*. Views, not
  workspaces to switch between.
- **Connecting an existing project**: a person already tracking their day job
  personally picks the date from which past hours are shared, or starts fresh.
- The **"What Acme can see"** page.
- **Leaving and removal**: tracking to that organisation's projects stops, its
  projects leave the active list, a read-only "Acme (left)" archive of the
  person's own hours remains and is exportable, and the organisation keeps the
  hours as its working-time record.

### Before any code

Four things, each cheaper to settle now than to migrate out of later:

1. Decide **notes and tags** (below).
2. Decide **live presence** (below).
3. Decide **deletion against legal retention** (below) — it determines whether
   "this beat is an organisation's working-time record" has to be a property of
   the document rather than something inferred through a project.
4. **Index the `projects` collection.** `ensure_indexes`
   (`api/src/beats/infrastructure/database.py`) covers eighteen collections and
   `projects` is not among them, so every project read is a collection scan
   filtered by `user_id`. Harmless at one person's scale and wrong as soon as
   the read becomes "mine, plus every organisation project I am assigned to"
   across every tenant. `{user_id: 1, archived: 1}` matches what
   `MongoProjectRepository.list` asks for. Measure before and after rather than
   assuming — this was found by reading, not by chasing a slow query.

### Done when

- A member sees organisation projects beside their own and tracks on them from
  every surface, unchanged.
- An organisation sees hours on its own projects and nothing else — proven by
  tests in the shape of 1c's: another member's personal project, a tag, a flow
  score and a biometric are each unreachable *because the query is never made*.
- Connecting a project shares history only from the chosen date.
- Leaving stops tracking, keeps the organisation's record, and leaves the
  person a read-only archive they can export.

---

## Stage 3 — Employment

**Goal:** turn the day-job contract we already have into something two parties
agree on. Section 3 of the epic. Depends on stage 2 — there is no employer to
own a contract until organisations exist.

### Scope

- **Contract terms belong to the employer**: weekly hours or percentage, start
  and end, holiday region, opening balance. A personal weekly goal stays the
  person's own.
- **Absences become requests**: the employee asks, a manager approves.
- **Timesheets**: submit a week or a month; approve, or ask for changes with a
  comment; approval locks the period and freezes that week's balance;
  reopening needs a reason and is recorded.
- **Reminders** for missing hours, unsubmitted timesheets, pending approvals.
- **Admin-entered time**, with the member notified and the change recorded.
- **Compliance record**: per person, per day, start / end / breaks / total,
  exportable and retained for the period local law requires. Rest-period and
  maximum-daily-hours warnings (Germany's 10 h a day, 11 h rest) come later.

### What already exists

More than the epic's wording suggests — all of this is built and tested:
`Contract` with dated terms, holiday region, opening balance and `ended_on`,
and the arithmetic in `domain/contracts.py`; typed absences; balance
adjustments; the monthly timesheet CSV (`domain/timesheet.py`); the vacation
entitlement (`domain/vacation.py`); employer holidays with company additions
and removals (`domain/holidays.py`).

So this stage is mostly about **who owns these and who may approve them**, not
about computing anything new. The compliance record is the one genuinely new
artefact, and even it is close to the timesheet's shape with breaks added.

### The one architectural change, worth knowing early

**Locking a period means storing a derived figure for the first time.**

Nothing about a contract's standing is stored today. Every week's closing
balance is recomputed on each read from one running pass over worked time,
absences, holidays and adjustments (`running_balance` in
`domain/contracts.py`). The same principle holds deliberately across the
codebase: billing budgets store only their limit, a report link stores no
figure, the month's report is assembled per request.

"Approval freezes that week's balance" breaks it. A frozen balance is a stored
number the live arithmetic can then disagree with — which is the point, since
an edit after approval must not silently move an approved figure — but it means
the system gains two answers to one question and every reader has to know which
it wants. Decide deliberately: what exactly is frozen, what a later edit to a
locked period does (refused, allowed and flagged, or allowed into an
amendment), and what the project page shows when the stored close and the
recomputed one differ. This is very hard to migrate out of once there are
approved periods in the database.

---

## Stage 4 — Scale

**Goal:** everything that only matters once organisations have more than a
handful of people in them. Sections 1, 5 and 7 of the epic. Expect this to
split into several issues when it starts — it is a bucket, not a unit of work.

### Scope

- **Teams** inside an organisation, giving managers a scope.
- **Manager** and **Viewer / Accountant** roles.
- **Seeing money as its own permission**, independent of role.
- **Verified email domains**: join automatically, or ask to join.
- **Single sign-on per organisation**, optionally required to enter it.
- **SCIM** provisioning.
- **Audit log**: membership, roles, contract changes, approvals, reopened
  periods, admin edits.
- **Retention settings** per organisation.
- **Per-seat billing** paid by the organisation, separate from the person's own
  plan, which joining or leaving never changes.
- **Reports**: team overview, per project and per client, CSV / PDF / full
  export.

### What it builds on

- **OpenID Connect is built and tested** — discovery, code exchange with PKCE
  and a nonce, every ID-token check, identities keyed on issuer + subject,
  `allow_signup`, and a scripted provider with real RS256 keys to test against
  (`src/beats/auth/oidc.py`, `sso_accounts.py`, `api/routers/sso.py`,
  `test_sso.py`, `fake_idp.py`). Per-organisation SSO is a scoping and policy
  layer over this, not a new protocol.
- **The money wall is already a collection boundary.** Clients, project
  billing, billable overrides and billing budgets live in their own
  collections, outside every device prefix, with no coach port. The money
  permission has a real seam to attach to rather than needing one carved out.

### Worth deciding before building, not during

- **The money permission must not be bolted on.** Every other item here is
  additive; this one is a cross-cutting read rule, and the cheapest version —
  a flag checked in each billing route — is the version that leaks the first
  time someone adds a route and forgets. Lean on the collection boundary.
- **Per-seat billing is the first time money flows *to us*.** Nothing in the
  codebase handles payment. A provider, tax, invoices and dunning are a
  dependency well outside the shape of this epic, and probably their own
  project rather than a bullet here.
- **The audit log is cheap to add late and expensive to backfill.** If stages 2
  and 3 ship without it, every membership change, contract edit and approval
  before it exists is unrecorded — and those are exactly the events a works
  council asks about. Consider writing the log in stage 2 even if nothing reads
  it until stage 4.

---

## Decisions still open

Six, from the epic. Three gate stage 2 and should be answered first.

| Decision | Proposal on the table | Gates |
|---|---|---|
| Does an organisation see an entry's **note**? Do personal **tags** cross? | Note yes, with a visible marker on the input; tags no | **2** |
| Can a manager see that a **timer is running now**? | Off by default, on only with each member's consent | **2** |
| What does **account deletion** do to records an employer must legally keep? | The organisation keeps the working-time rows, name only as the employer's record; everything else erased | **2** |
| What does **"day job"** mean once an employer can be an entity? | Personal day jobs stay exactly as they are; nothing forces anyone into an organisation | 3 |
| Who wins when the **employer's contract terms differ** from the employee's? | — open — | 3 |
| **Pricing**: seat price, free tier, whether contractors count as seats | — open — | 4 |

### Notes and tags

Rule 3 lists exactly what crosses, and the note is the only free-text field in
it — the only one a person might write something personal into without
realising who reads it. If the answer is yes, the visible marker is not a
nicety: it is what makes the rule honest, and it has to appear on *every*
surface that writes a note — the SPA, the companion's "How did it go?" sheet,
the VS Code extension, and anything the daemon writes. That is real work in
four places and it has to land with the feature.

Tags are the easier half: they are derived from the daemon's flow windows, which
makes them a signal about *how* someone worked rather than *what* they worked
on — much closer to the flow scores rule 3 puts firmly on the far side.

The same question exists one step smaller for a freelancer's client. Stage 1c
shipped without notes precisely so the two could be decided together instead of
drifting apart; `docs/billing.md` records it as open there. Decide both in one
sitting — the marker work is shared.

### Live presence

1c already answered the smaller version and answered no: a report link carries
no `running` flag, so a client cannot learn from an invoice's backing whether a
timer is on right now (`docs/billing.md`, 1c decision 7). Whatever is decided
should not leave the two surfaces contradicting each other.

"Off by default, on with each member's consent" is three states, not two, and
only the third shows anything. The consent record has to be revocable, visible
on the "can see" page, and effective immediately rather than at the next read.
It is also the single feature most likely to read as surveillance to the works
councils this epic is explicitly selling to — so **"not at all, in any stage"**
is worth weighing against the proposal rather than assuming the proposal.

### Deletion and legal retention

Deletion is total and simple today: PRIVACY.md promises that emailing the
operator removes *every* document associated with the user, and lists them. The
proposal makes that promise conditional for the first time — some rows survive,
under someone else's control, with a name attached. Defensible, probably
legally required, and it changes what the privacy page can honestly say.

It also has to be decidable **per row** at deletion time, which is why it gates
the data model: "this beat is an organisation's working-time record" must be a
property of the document, not something inferred by joining through a project
that is itself being deleted. Open sub-questions: which rows survive (beats
only, or absences and approved timesheets too); what identifies the person once
the account is gone; who can delete them afterwards and when the retention
clock stops; whether the person gets an export first.

### Contract disagreement

The concrete case: someone tracks their day job personally with a contract they
entered themselves — 80% from March, Zurich holidays, +12 h opening balance.
They join their employer's organisation and connect the project. The employer's
record says 100% from January and says nothing about an opening balance. Their
overtime balance, a figure they may have relied on for months, now moves —
`domain/contracts.py` recomputes it from the terms on every read.

Rule 4 already points at an answer: an employer's terms should not silently
rewrite history the employee recorded before joining, and billing's existing
`RETROACTIVE_CHANGE` gate is the shape of a precedent.

### What "day job" means now

`docs/work-contracts.md` decision 1 — the day-job project *is* the contract, an
employer is not an entity — is load-bearing in code, not just prose.
`ProjectKind.DAY_JOB` is what permits a `Contract` at all (`NOT_A_DAY_JOB`
otherwise), and a startup migration derives a day job's contract from its goal
history. After stage 2 there are two kinds of day job: one whose contract its
owner wrote, one whose contract an employer owns and the employee only reads.
Same arithmetic, different write rules.

The proposal is almost certainly right and is cheap — the employer-owned case
becomes an additional state rather than a replacement. Whatever is decided,
`docs/work-contracts.md` decision 1 has to be rewritten rather than left to
contradict the code, as part of the stage that changes it.

---

## What the code says about stage 2

Researched against the tree as it stands after 1c.

**The wall is one line.** `MongoStore._q`
(`api/src/beats/infrastructure/repositories.py`) stamps
`{"user_id": self.user_id}` onto every query; eighteen repositories inherit it
and twenty dependencies build them. Rule 3 is therefore already enforced
mechanically for every collection. Stage 2's job is to widen it for exactly one
and leave the other seventeen untouched — and to keep it a collection boundary
rather than letting it become a serialiser allowlist someone has to remember.

**Only `projects` needs a second owner.** A beat on an organisation's project is
still the member's own document and should stay user-scoped. The organisation
never gets a user-scoped repository for somebody else; it gets a reader keyed
on **project id**, across users. Absences, adjustments and the contract follow
the project the same way.

**1c already built that read, one user at a time.**
`BillingService.client_period` takes a set of project ids, reads the beats
started in a range over them, and assembles — without ever touching another
client's inputs. An organisation's read of its own projects is the same shape
with the user filter removed. 1c also established the pattern for a read that
crosses users: one narrow unscoped class that does nothing else
(`MongoReportLinkLookup`), with the route saying at the call site why the
account did not come from a token. Reuse both rather than invent.

**Three things that will bite**, found by reading rather than guessing:

1. **`projects` has no index** — see *Before any code* above.
2. **Devices already reach `/api/projects` by prefix.**
   `DEVICE_ALLOWED_PREFIXES` in `api/src/server.py` matches `/api/projects` and
   `/api/beats`, and the timer's status hands a paired device the project
   document whole. That is correct — a member tracks on organisation projects
   from their Mac app and wall clock like any other — but it means an
   organisation-owned project document reaches every paired device of every
   assigned member. **Nothing the organisation considers private may live on
   that document.** This is the reasoning that kept money off `Project` in 1a.
3. **The full backup exports the user's projects.** `GET /api/export/full`
   (version 1.3) carries projects, sessions, absences and adjustments. What a
   personal backup does with an organisation-owned project — and what an import
   does with one — is undecided, and needs to be before the export silently
   starts including other people's working-time records.

**The coach is already safe and should stay dumb about this.** It queries Mongo
directly with its own `user_id` filters in six modules (`brief.py`, `chat.py`,
`context.py`, `feedback.py`, `memory.py`, `usage.py`) and has no ports to
widen. Give it no organisation port either.

---

## Out of scope for this epic

- Separate work-only accounts that an employer controls. Large customers will
  ask; it is a layer on top later, not the default.
- Several workspaces inside one organisation, for agencies.
- Payroll integrations, and invoicing beyond what clients need.
- Screenshots, activity levels, app tracking for employers, idle detection
  reported to employers. **Not later, not ever.**
