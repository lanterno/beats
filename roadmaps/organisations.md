# Organisations — what is left to build

The epic is [#353](https://github.com/lanterno/beats/issues/353). Four stages
of it shipped; **seven issues remain**, and this file is what an issue cannot
hold: why each waits, what it must not do, and which seam it attaches to.

What is already built — the decisions, the data model, the HTTP contract and
the rules the UI keeps — is [docs/organisations.md](../docs/organisations.md).
Read it first. Nothing here repeats it.

---

## Before you build any of this

**The four rules are in [docs/organisations.md](../docs/organisations.md)
§ The four rules, and they are not negotiable.** They were deliberately not
copied here: there was a second copy of them in this file until 2026-10-31,
the two had already drifted, and a rule that exists twice is a rule nobody
can trust. Read them there.

Three consequences of those rules bind every item below, and each is a
mistake already avoided once:

- **Widen a collection boundary, never a serialiser.** `MongoStore._q`
  (`api/src/beats/infrastructure/repositories.py`) stamps
  `{"user_id": self.user_id}` onto every query, and that one line is what
  enforces rule 3 mechanically across every collection. Stage 2 widened it
  for exactly one collection (`projects`) and left the rest alone. A read
  that crosses users gets its own narrow class that does nothing else — as
  `MongoOrganisationRecords` and `MongoReportLinkLookup` do — not a filter
  applied after the fact, and not a field allowlist somebody has to remember.
- **The coach never reaches past the member.** It reads projects through
  the member's own merged repository (`project_repository_for`, in
  `api/src/beats/coach/repos.py`), so it sees the organisation projects the
  member is assigned to, with their own half — that is how it names their
  day job. Its own collections it queries directly, with its own `user_id`
  filters, in six modules (`brief.py`, `chat.py`, `context.py`,
  `feedback.py`, `memory.py`, `usage.py`). It holds no `OrganisationStore`
  and no `OrganisationRecords`: give it neither, nor any other port that
  reads another member. It is safe today *because* it cannot reach another
  member, not because it chooses not to.
- **Nothing an organisation considers private may live on a project
  document.** `DEVICE_ALLOWED_PREFIXES` in `api/src/server.py` matches
  `/api/projects`, and the timer's status hands a paired device the project
  document whole — correctly, since a member tracks on organisation projects
  from their Mac app and wall clock. So an organisation-owned project
  document reaches every paired device of every assigned member. This is the
  reasoning that kept money off `Project`, and it applies to anything added
  there next.

---

## What remains

Seven issues, all under [#353](https://github.com/lanterno/beats/issues/353).
Five are stage 4; two are older work that outlived their stage.

The epic also lists bugs and open questions in what already shipped, found
when the docs were checked against the code on 2026-10-31. They are not
here: each is a fix to something
[docs/organisations.md](../docs/organisations.md) already decides, not new
scope, and its issue says what is wrong.

| # | What | Blocked by | Start when |
|---|------|-----------|------------|
| [#340](https://github.com/lanterno/beats/issues/340) | Money as a permission of its own | Nothing external — there is no organisation money to guard yet | Organisation-side money is designed |
| [#341](https://github.com/lanterno/beats/issues/341) | Verified email domains for joining | The API sends no email | Email infrastructure exists |
| [#342](https://github.com/lanterno/beats/issues/342) | SSO per organisation, optionally required | Nothing — the shape is decided | A customer requires it |
| [#343](https://github.com/lanterno/beats/issues/343) | SCIM provisioning | #342 | SSO per organisation ships |
| [#345](https://github.com/lanterno/beats/issues/345) | Per-seat billing | No payment machinery anywhere in the codebase | The end of the beta is decided; then as its own project |
| [#351](https://github.com/lanterno/beats/issues/351) | A digest or push for what is missing or waiting | No channel: no email, no server push (#298) | Either channel exists |
| [#352](https://github.com/lanterno/beats/issues/352) | DPA, works-council sheet, DPIA template | Counsel review | A customer asks, or counsel is engaged |

### #340 — Money as a permission

There is no organisation-side money at all: billing stayed personal, and an
organisation's project is billed by nobody (`ORGANISATION_PROJECT`). So there
is nothing for a permission to guard, and this is blocked on a design that
does not exist yet, not on a dependency.

When it comes, **it must not be bolted on.** Every other item here is
additive; this one is a cross-cutting read rule, and the cheapest version —
a flag checked in each billing route — is the version that leaks the first
time someone adds a route and forgets. The seam already exists: clients,
project billing, billable overrides and billing budgets are their own
collections, outside every device prefix, with no coach port. Attach to that
boundary rather than carving a new one.

### #341 — Verified email domains

People with an `@acme.com` address ask to join, or join automatically.

Blocked on email infrastructure the API deliberately does not have. Without
verification a domain rule hands memberships to whoever registers an address
— the exact hole decision 11 closed for invitations. Email first, then this;
building it the other way round reopens the hole on purpose.

### #342 — SSO per organisation

**The shape was decided 2026-10-28.** It is built when a customer requires
it, not before — but it is designed, so this is a build task, not a
decision.

Not by stamping the door on the session: sessions stay door-blind, which
keeps the promise that nothing downstream knows which door was used.
Instead, a **per-organisation attestation**, the way GitHub gates an
organisation behind SAML:

- An organisation that requires SSO configures its own OpenID Connect
  provider. This is a scoping layer over `api/src/beats/auth/oidc.py`, which
  is built and tested already — discovery, code exchange with PKCE and a
  nonce, every ID-token check, identities keyed on issuer + subject,
  `allow_signup`, and `src/fake_idp.py`, a scripted provider with real RS256
  keys to test against. **It is not a new protocol.**
- Entering that organisation's slice needs a fresh verification with *that*
  provider, stored on the membership: verified at T, expiring at T+N. It
  shows on the "What Acme can see" page and is audited.
- The person's passkey still opens their personal account and every other
  organisation — rule 1.
- Enforce it as a dependency on the organisation router, in one place, like
  the role checks. Never a flag per route; that is #340's lesson borrowed
  early.
- **Change PRIVACY.md first, and narrowly**: an organisation that requires
  SSO sees when you last verified with its provider. That is not "we record
  how you log in", and the wording matters.

Open at build time: whether a lapsed attestation blocks the organisation's
routes alone, or also starting new timers on its projects. Existing data is
never blocked.

### #343 — SCIM provisioning

Provision and deprovision members from an identity provider. Its own protocol
surface and credential story, keyed on the same per-organisation provider as
#342, so it comes after it.

### #345 — Per-seat billing

**The numbers are decided** ([docs/pricing.md](../docs/pricing.md)): €8 a
seat a month on an annual plan, free to five seats, a seat is an active
member with an assignment, everything free during the beta.

What remains is collecting it, and that is the first time money flows *to
us*. Nothing in the codebase handles payment: a provider, tax, invoices and
dunning are a dependency well outside the shape of this epic. Treat it as its
own project rather than an item here.

### #351 — A digest or push for what is missing or waiting

Today this shows where people already look: a member's timesheet list offers
the ended months still to submit and marks the ones sent back, and a decider's
Approvals tab counts and groups what waits (decision 27). A digest or a push
needs a channel first — email infrastructure, or server push
([#298](https://github.com/lanterno/beats/issues/298)).

### #352 — Sales and legal material

Three drafts in [legal/](legal/), unreviewed by counsel. See
[legal/README.md](legal/README.md) for what each is and what finishing them
needs. Nothing there reaches a customer first.

---

## Out of scope, by decision

Not oversights. If one of these is asked for, it is a new decision, not a
continuation of this epic.

- **Separate work-only accounts an employer controls.** Large customers will
  ask. It is a layer on top, later — never the default, which would undo
  rule 1.
- **Several workspaces inside one organisation**, for agencies.
- **Payroll integrations**, and invoicing beyond what clients need.
- **Screenshots, activity levels, app tracking for employers, idle detection
  reported to employers. Not later, not ever.** This is the line the whole
  product is built to sit on the right side of: a tracker that already knows
  your flow, sleep and heart rate becomes a surveillance tool the moment an
  employer can see any of it. What makes these records sellable to a works
  council is that they *cannot* be used to watch anyone.

---

## Why the stages went in the order they did

Kept because it explains the shape of what is built, and because the same
logic orders what is left.

Stage 2 (foundations) was the only stage that changed the data model. Stages
3 (employment) and 4 (scale) are additive on top of it — which is what made
the sequencing simple: get the ownership model right, and the rest is
ordinary work. The remaining items are additive too, with one exception,
#340, which is why it carries the warning it does.

Two things were deliberately done early because they are cheap to add before
and expensive to add after:

- **The audit log** was written from stage 2 on and only read from stage 4.
  Every membership change, contract edit and approval made before it exists
  is unrecorded, and those are exactly the events a works council asks about.
- **The index on `projects`** (`{user_id: 1, archived: 1}`) went in before
  any organisation code. Every project read had been a collection scan —
  harmless at one person's scale, wrong as soon as the read became "mine,
  plus every organisation project I am assigned to" across every tenant.

The one thing stage 3 broke on purpose: **approval stores a derived figure.**
No other working-time or billing figure is stored — every week's closing
balance is recomputed on each read, billing budgets store only their limit, a
report link stores no figure. (The weekly digests keep their own totals,
outside both.) A frozen month is the exception, because an edit after approval
must not silently move an approved figure. It leaves the system with two
answers to one question, and every reader has to know which it wants. That was
decided deliberately rather than discovered, because it is very hard to
migrate out of once approved periods exist.
