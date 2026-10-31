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

**Where this document sits.** The epic is GitHub issue
[#353](https://github.com/lanterno/beats/issues/353); what it still owes is an
issue each, listed there, and `CLAUDE.md` says open work lives in issues, not in
docs. This file keeps what an issue cannot: the four rules, the reasoning behind
each stage, the decisions and why they went the way they did, and what the code
said before stage 2 changed it.

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
| **1** | Clients for freelancers | **Done** — [docs/billing.md](../docs/billing.md) |
| **2** | Foundations: organisations, membership, org projects, leaving | **Done** — [docs/organisations.md](../docs/organisations.md), decisions 1–20, and 28 for the duplicate a connect can leave |
| **3** | Employment: employer contracts, leave requests, timesheet approval | **Done** — decisions 21–24 and 26–27 |
| **4** | Scale: teams, money permission, SSO, SCIM, audit, per-seat billing | **Done, but for what waits on a trigger outside the code** — teams, manager and viewer roles, the audit read and the report CSVs (decision 25), retention with its purge (decision 30), closing and deletion (decision 29). Organisation money, verified domains, SSO per organisation, SCIM and the payment machinery each wait — see *What remains*, below, and with them the epic's section 7, the legal material |

Stage 2 was the only one that changed the data model. Stages 3 and 4 are
additive on top of it, which is what made the sequencing simple: get the
ownership model right and the rest is ordinary work.

---

## What each stage settled

The lists of what each stage was asked for went with the stages; what stays is
the reasoning that carried from one to the next.

### Stage 1 — Clients for freelancers

Section 4 of the epic without its client-organisation part. It needed no
organisations, which is why it went first, and it sells to one of the two
target groups on its own. Three of its decisions carried into organisations,
because they are the same problems one step smaller:

- Billing lives in **its own collections**, never as fields of `Project` or
  `Beat`, so a contractor's rates stay on the far side of a collection
  boundary rather than behind a serialiser someone must remember.
- A reader of one client **cannot reach another's** because the query for
  another's is never made — not because a filter removed it afterwards.
- A report says **nothing about now**: no `running` flag, so an invoice's
  backing cannot be used to see whether someone is working at this moment.

### Stage 2 — Foundations

Sections 1, 2 and 6 of the epic: an organisation can exist, have members, own
projects that appear on each member's own timeline, and be left — with the
wall of rule 3 enforced structurally rather than by vigilance. Four things were
settled before any code, each cheaper to settle then than to migrate out of
later: notes and tags, live presence, and deletion against legal retention
(all below), and the index on `projects`. `ensure_indexes`
(`api/src/beats/infrastructure/database.py`) covered eighteen collections and
`projects` was not among them, so every project read was a collection scan
filtered by `user_id` — harmless at one person's scale and wrong as soon as
the read became "mine, plus every organisation project I am assigned to"
across every tenant. `{user_id: 1, archived: 1}` matches what
`MongoProjectRepository.list` asks for, and it went in first, measured rather
than assumed.

The proof the stage was asked for, and has: an organisation sees hours on its
own projects and nothing else, shown by tests in the shape of 1c's — another
member's personal project, a tag, a flow score and a biometric are each
unreachable *because the query is never made*.

### Stage 3 — Employment

Section 3 of the epic: turn the day-job contract into something two parties
agree on. More of it existed than the epic's wording suggested — `Contract`
with dated terms, holiday region, opening balance and `ended_on`, the
arithmetic in `domain/contracts.py`, typed absences, balance adjustments, the
monthly timesheet CSV, the vacation entitlement, employer holidays — so the
stage was about **who owns these and who may approve them**, not about
computing anything new. The compliance record was the one genuinely new
artefact, and even it is close to the timesheet's shape with breaks added.

**Locking a period stores a derived figure for the first time.** Nothing
about a contract's standing was stored before: every week's closing balance is
recomputed on each read from one running pass over worked time, absences,
holidays and adjustments (`running_balance`), and the same principle holds
deliberately across the codebase — billing budgets store only their limit, a
report link stores no figure, the month's report is assembled per request.
"Approval freezes the balance" breaks it on purpose: an edit after approval
must not silently move an approved figure, so the system gains two answers to
one question and every reader has to know which it wants. The stage decided
deliberately what is frozen and what a later edit does — refused, with a
recorded way back (decision 23) — because this is very hard to migrate out of
once there are approved periods in the database.

### Stage 4 — Scale

Sections 1, 5 and 7 of the epic: everything that only matters once
organisations have more than a handful of people in them. Built: teams with
manager scope, the viewer role, the audit log read, the record and compliance
CSVs (decision 25), retention with a statutory floor and the operator-run
purge behind it (decision 30), and closing with notice before deletion hands
members their projects back (decision 29). What the rest builds on:

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

One sequencing lesson, since it shaped what is already built: **the audit
log is cheap to add late and expensive to backfill.** Every membership
change, contract edit and approval made before it exists is unrecorded, and
those are exactly the events a works council asks about. So it was written
from stage 2 on, and only read from stage 4.

---

## What remains, and what each waits for

Five items from stage 4, each an issue under
[#353](https://github.com/lanterno/beats/issues/353). They are decisions, not
omissions: the reason each waits is here, so picking one up starts from it.

- **Money as a permission** ([#340](https://github.com/lanterno/beats/issues/340)).
  There is no organisation-side money yet — billing stayed personal, and an
  organisation's project is billed by nobody (`ORGANISATION_PROJECT`) — so
  there is nothing for the permission to guard. It must not be bolted on when
  it comes: every other item here is additive, this one is a cross-cutting
  read rule, and the cheapest version — a flag checked in each billing route
  — leaks the first time someone adds a route and forgets. Lean on the
  collection boundary billing already is.
- **Verified email domains** ([#341](https://github.com/lanterno/beats/issues/341)).
  Needs the email infrastructure the API deliberately does not have
  (decision 11). Without verification a domain rule would hand memberships to
  whoever registers an address — the exact hole decision 11 closed for
  invitations. Email first, then this.
- **SSO per organisation, and "required to enter"**
  ([#342](https://github.com/lanterno/beats/issues/342)) — *shape decided
  2026-10-28, built when a customer requires it.* Not by stamping the door on
  the session: sessions stay door-blind, keeping the promise that nothing
  downstream knows which door was used. Instead a **per-organisation
  attestation**, as GitHub gates an organisation behind SAML. An organisation
  that requires SSO configures its own OpenID Connect provider — a scoping
  layer over `auth/oidc.py`, which is built and tested already (discovery,
  code exchange with PKCE and a nonce, every ID-token check, identities keyed
  on issuer + subject, `allow_signup`, and a scripted provider with real
  RS256 keys) — and entering its slice needs a fresh verification with *that*
  provider, stored on the membership, verified at T and expiring at T+N,
  shown on the "What Acme can see" page and audited. The passkey still opens
  the personal account and every other organisation (rule 1). Enforced as a
  dependency on the organisation router, one place, like the role checks —
  never a flag per route, which is the money permission's lesson. PRIVACY.md
  changes narrowly and first: an organisation that requires SSO sees when you
  last verified with its provider, which is not "we record how you log in".
  Open at build time: whether a lapsed attestation blocks the organisation's
  routes alone or also starting new timers on its projects. Existing data,
  never.
- **SCIM provisioning** ([#343](https://github.com/lanterno/beats/issues/343)).
  Its own protocol surface and credential story, keyed on the same
  per-organisation provider, so it comes after SSO.
- **Per-seat billing** ([#345](https://github.com/lanterno/beats/issues/345))
  — *the numbers are decided* ([docs/pricing.md](../docs/pricing.md): €8 a
  seat a month annual, free to five seats, a seat is an active member with an
  assignment, everything free during the beta). What remains is collecting
  it, the first time money flows *to us*: nothing in the codebase handles
  payment, and a provider, tax, invoices and dunning are a dependency well
  outside the shape of this epic — its own project rather than a bullet here.

Two more sit under the epic without being stage 4: a digest or push for what
is missing or waiting ([#351](https://github.com/lanterno/beats/issues/351)),
which needs a channel — email, or server push — before it can exist; and the
sales and legal material of the epic's section 7
([#352](https://github.com/lanterno/beats/issues/352)), drafted in
[legal/](legal/) and unreviewed by counsel.

---

## The decisions, and why

Six, from the epic, all settled; the rows say how, and the notes under
them are kept as the reasoning. The first five are recorded in
[docs/organisations.md](../docs/organisations.md); pricing in
[docs/pricing.md](../docs/pricing.md), with the payment machinery it needs as
[#345](https://github.com/lanterno/beats/issues/345).

| Decision | Settled | Gates |
|---|---|---|
| Does an organisation see an entry's **note**? Do personal **tags** cross? | **Settled:** note yes, tags no. No surface writes a note today, so the marker goes where a note is shown; any note input brought back ships it | 2 |
| Can a manager see that a **timer is running now**? | **Settled: no, in any stage.** The record takes finished entries only and carries no running flag | 2 |
| What does **account deletion** do to records an employer must legally keep? | **Settled:** the stamped working-time rows, the balance's inputs and the name on the membership stay under a tombstone; everything else is erased (`erasure.py`) | 2 |
| What does **"day job"** mean once an employer can be an entity? | **Settled:** personal day jobs stay exactly as they are; on an organisation project the contract lives on the assignment, the member's until the employer takes it under management (decision 21) | 3 |
| Who wins when the **employer's contract terms differ** from the employee's? | **Settled:** management starts from the terms the member recorded; the employer's changes are audited acts, never silent recomputation (decision 21) | 3 |
| **Pricing**: seat price, free tier, whether contractors count as seats | **Settled** (2026-10-28): €8/seat/mo annual (€10 monthly), free to 5 seats, SSO included; a seat is an active member with an assignment — viewers free, contractors count when assigned; one subscription per organisation; everything free during the beta as a shown 100% discount, and non-payment afterwards degrades to read-only, never deletion. Priced against the vendors' own pages in [docs/pricing.md](../docs/pricing.md); the payment machinery stays its own project, [#345](https://github.com/lanterno/beats/issues/345) | 4 |

### Notes and tags

Rule 3 lists exactly what crosses, and the note is the only free-text field in
it — the only one a person might write something personal into without
realising who reads it. Settled in stage 2: the note crosses, and since no
surface writes a note today (the companion's post-stop sheet went with the
last free-text inputs, the web app takes none, the API ignores one on edit),
the marker sits where a note is *shown* on an organisation's project. Any
note input brought back ships the marker on the input with it.

Tags are the easier half: they are derived from the daemon's flow windows, which
makes them a signal about *how* someone worked rather than *what* they worked
on — much closer to the flow scores rule 3 puts firmly on the far side. They do
not cross.

The same question existed one step smaller for a freelancer's client; a report
link still shows no notes (`docs/billing.md`, 1c decision 6).

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

Each was settled in [docs/organisations.md](../docs/organisations.md): erasure keeps the
stamped rows — entries, absences, the contract and adjustments behind a balance
the organisation read — under a tombstone with the name it knew the person by,
and nothing else (decision 3); retention bounds that exception with a floor by
jurisdiction and a purge the operator runs, which unstamps a living member's
rows and deletes only tombstoned ones (decision 30); and an organisation's own
end is notice first, then a deletion that hands each member a personal copy of
the projects they hold rows on (decision 29). The record's keeper destroying
the record is theirs to do; a person's rows outliving their account is bounded
by law, not by us.

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

Researched against the tree as it stood after 1c, and kept as the reasoning
behind [docs/organisations.md](../docs/organisations.md)'s decisions 4–15; each
"will bite" below was answered there (the index, the device prefix, the
backup).

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
