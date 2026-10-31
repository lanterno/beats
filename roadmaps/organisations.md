# Organisations — what is left to build

The epic is GitHub issue #353. Four stages of it shipped. Of the sixteen
bugs found in what shipped on 2026-10-31, fourteen were fixed the same day
(PRs #427–#441; the roadmap entries went with them). What is left is **two
decisions the owner has to make before the last two bugs can be fixed, a
privacy draft awaiting the owner's review, seven items that wait on
something outside the code, and a back office**, and every one of them is
written out in full below.

**This file is meant to be enough on its own.** Whoever picks it up may have
no access to GitHub. So unlike the other roadmaps, which link to issues and
never restate them, this one carries each open issue's whole content: what
is wrong, where, what to do, and what to test. Each item keeps its GitHub
number so the two can be synced by whoever has access. If this file and an
issue disagree, this file was written later (2026-10-31), but say so to the
owner rather than picking one silently.

What is already built — the four rules, decisions 1–33, the data model, the
HTTP contract and the rules the UI keeps — is
[docs/organisations.md](../docs/organisations.md). **Read it first.** Nothing
here repeats it; items below cite its decisions by number.

---

## How to work from this file

1. **Read** [docs/organisations.md](../docs/organisations.md) and the
   repo-root `CLAUDE.md` (commands, conventions, and *What to test, and what
   not to*). For the API, also `api/CLAUDE.md`.
2. **Pick** from [Order of work](#order-of-work). Items marked **Ask the
   owner first** contain a choice that is the owner's to make. Ask in the
   session, then write the answer into `docs/organisations.md` as a decision
   before building.
3. **Branch** from an up-to-date `main`, named `<type>/<n>-<slug>`, for
   example `fix/404-share-day-stamp`. The checkout is shared with other
   sessions: work in a `git worktree` or restore whatever branch you found.
4. **Commit** by the owner's rules:
   - the code commit first, then its test commit, separately;
   - frontend and backend never share a commit;
   - one goal per commit;
   - no issue number in a commit subject (`fix(api): …`). Put `Fixes #n` (or
     `Part of #n`) in the commit body instead, so the issue can be closed
     from it.
5. **Test.** Work out which tests are worth writing from the item's *Test*
   line and `CLAUDE.md`. Commands:
   - API: `cd api && uv run --group dev pytest src/test_organisations.py -q`,
     then the full `pytest src/` (about 30 s, needs Docker or
     `BEATS_TEST_ENV=1`).
   - UI: `cd ui && pnpm test`, then `pnpm typecheck`.
   - Companion: `cd companion && flutter test`.
   - A change to a route's signature or docstring changes the generated
     types: run `cd ui && pnpm gen:types` and commit the result on its own.
6. **When an item ships:**
   - delete its section here, and its row in *Order of work*;
   - if behaviour changed, write it into `docs/organisations.md` (amend the
     decision it touches, or add one) and into `DATA.md` / `PRIVACY.md` if
     they describe it;
   - list the issue number in your final summary, so someone with GitHub can
     close it and tick its box in #353.
7. **Something new you find** that is out of scope goes in
   [Found since the last sync](#found-since-the-last-sync) at the bottom,
   in the shape given there, not in a TODO comment.

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

Two more facts that trip up fixes here:

- **The SPA and the API deploy separately** (`CLAUDE.md` § Infrastructure),
  so an old SPA can run against a new API. Changing a route's parameters
  must not break the SPA already deployed. FastAPI ignores unknown query
  parameters, so dropping one is safe; making a new one required is not.
- **Only the person deletes their own rows** (decision 32). An organisation
  removing a project ends the assignment; merging and deleting repoint
  rows. The one exception is rows kept under an `erased:` tombstone, which
  go when the organisation is deleted or its retention expires. Keep it
  that way in every fix below.

---

## Order of work

Most important first. The retention purge is still operator-run and dry by
default (`api/scripts/retention_purge.py`), and nothing schedules it; #409
is the one retention question still open before it is run in earnest.

| # | What | Surface | Why at this place |
|---|------|---------|-------------------|
| 405 | A contract write can move an approved month | api | **Ask the owner first**; parts 1–3 shipped |
| 409 | A purge withholds long-standing members' balances | api | **Ask the owner first**; the recommended fix was wrong |
| 422 | PRIVACY.md disagrees with the code | docs | Drafted in PR #442. **The owner reviews it** |
| 424 | A back office for the operator | api, ui | When the owner starts it |
| 340–352 | The seven waiting items | — | Each when its blocker clears; see the section |

---

## Bugs in what shipped

Found on 2026-10-31 by checking `docs/organisations.md` against the code.
Fourteen of the sixteen are fixed (PRs #427–#441). The two left are not
fixes but decisions, each written out with what was found while trying to
fix it. Line numbers are approximate (as of `main` on 2026-10-31); the
function names are what to search for.

### #405 — A contract write can move an approved month — **ask the owner first**

Parts 1–3 of this issue (the two removes and a backup's beats skipping
the lock) are fixed in PR #434. What is left is the decision:

**What's wrong.** A contract change moves every month's expectation at
once. The frozen figure itself never moves (it is stored), but the live
ledger then disagrees with an approved month. Two writes can do it: the
member's contract write on an unmanaged assignment (`update_project`,
`replace_contract`, including the adjustment purge `_reconcile_adjustments`
triggers), and the employer's (`EmploymentService.set_contract`).

**Candidate rule.** Refuse a contract write when, for any approved month on
that assignment, the month's expected hours or the adjustments counted in
it would differ before and after the write. Compute it with the ledger pass
the frozen month was taken from. Record the answer in decision 23. If the
answer is "allowed", decision 23 should say that an approved month's
*expectation* can move under a later contract write while its days cannot.

**Test.** Approve a month, then move the contract's first day or hours
inside it, and assert 409 `PERIOD_APPROVED` (or whatever the decision is).

### #409 — After a retention purge, the organisation's balance is withheld — **ask the owner first**

The recommended fix was built on 2026-10-31 and dropped before merging,
because it is wrong; the finding is on the issue.

**What happens.** The purge unstamps a living member's rows older than the
cutoff. `MongoOrganisationRecords.has_unshared` then reads them as rows
never shared, so `_balance` returns nothing for every long-standing member
after the first purge.

**Why the recommended fix is wrong.** `_balance` computes the organisation's
figure from `records.beats_of_member`, which reads **stamped** beats only.
After a purge, the hours before the cutoff are gone from that read, but
`balance_terms` still runs from `contract.starts_on` and expects them: a
contract that began before the cutoff would show every pre-cutoff day as
expected and none worked. Ignoring purge-unstamped rows in `has_unshared`
would replace a withheld balance with a wrong one. Today's behaviour
(withheld) is the safer of the two. The member's own figure
(`/contract/week`) reads all their rows and is unaffected.

**Options.**

1. Keep withholding, and say so: once a contract's span reaches before the
   organisation's retention cutoff, the organisation's balance read is None
   by rule, made explicit rather than an accident of `has_unshared`.
2. At purge time, carry the balance at the cutoff forward as a stored
   opening on the assignment — a second stored derived figure beside
   `FrozenMonth`, reopening the "no stored figures" decision deliberately.
3. Let the balance read the member's unstamped rows from `shared_from` on
   (the purged ones) — a figure, not the rows — which decision 30's wording
   currently excludes.

Decisions 16 and 30 are where the answer goes.

### #422 — PRIVACY.md disagrees with the code on organisations and single sign-on

Drafted as PR #442 (a draft PR) for the owner's review, with the SSO log
line's provider dropped in its own commit so that choice can be reversed.
It reads correctly once #427, #434 and #436 are merged; merge it after
them. Nothing to build until the owner has read it.

---

## Waiting on something outside the code

None of these should be started until its blocker clears. Each section says
what blocks it, when to start, and what it must not do.

| # | What | Blocked by | Start when |
|---|------|-----------|------------|
| 340 | Money as a permission of its own | Nothing external — there is no organisation money to guard yet | Organisation-side money is designed |
| 341 | Verified email domains for joining | The API sends no email | Email infrastructure exists |
| 342 | SSO per organisation, optionally required | Nothing — the shape is decided | A customer requires it |
| 343 | SCIM provisioning | #342 | SSO per organisation ships |
| 345 | Per-seat billing | No payment machinery anywhere in the codebase | The end of the beta is decided; then as its own project |
| 351 | A digest or push for what is missing or waiting | No channel: no email, no server push (#298) | Either channel exists |
| 352 | DPA, works-council sheet, DPIA template | Counsel review | A customer asks, or counsel is engaged |
| 424 | A back office for the operator | Nothing — not started | The owner starts it |

### #340 — Money as a permission

There is no organisation-side money at all: billing stayed personal, and an
organisation's project is billed by nobody (`ORGANISATION_PROJECT`, raised in
`domain/billing_service.py`). So there is nothing for a permission to guard,
and this is blocked on a design that does not exist yet, not on a
dependency. When it arrives, the epic's rule is that **seeing money is its
own permission**, independent of role.

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
decision. SSO is included in the paid seat price, not an add-on
([docs/pricing.md](../docs/pricing.md)).

Not by stamping the door on the session: sessions stay door-blind, which
keeps the promise that nothing downstream knows which door was used (see the
log line in #422). Instead, a **per-organisation attestation**, the way
GitHub gates an organisation behind SAML:

- An organisation that requires SSO configures its own OpenID Connect
  provider. This is a scoping layer over `api/src/beats/auth/oidc.py`, which
  is built and tested already — discovery, code exchange with PKCE and a
  nonce, every ID-token check — plus `auth/sso_accounts.py` (identities
  keyed on issuer + subject, `allow_signup`) and `src/fake_idp.py`, a
  scripted provider with real RS256 keys to test against. Provider
  configuration is deployment-wide today (`OIDC_PROVIDERS` in
  `settings.py`), and `OrgMembership` has no attestation fields. **It is not
  a new protocol.**
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
never blocked. Ask the owner.

### #343 — SCIM provisioning

Provision and deprovision members from an identity provider. Its own protocol
surface and credential story, keyed on the same per-organisation provider as
#342, so it comes after it. It belongs to a later, sales-led enterprise tier,
not the seat price ([docs/pricing.md](../docs/pricing.md)).

### #345 — Per-seat billing

**The price is decided** ([docs/pricing.md](../docs/pricing.md), 2026-10-28):

- €8 a seat a month billed annually, €10 billed monthly; free up to five
  seats; SSO included.
- A seat is an active member with an assignment: viewers are free,
  contractors count when assigned, and nobody counts before they join.
- One subscription per organisation.
- Everything is free during the beta, shown as a 100 % discount; the
  marketing page already shows the price struck through
  (`ui/client/pages/homepage/HomePage.tsx`).
- After the beta, an organisation that does not pay goes read-only, never
  deleted.

What remains is collecting it, and that is the first time money flows *to
us*. Nothing in the codebase handles payment: a provider, tax, invoices and
dunning are a dependency well outside the shape of this epic. Treat it as
its own project, started when the end of the beta is decided.

### #351 — A digest or push for what is missing or waiting

Today this shows where people already look: a member's timesheet list offers
the ended months still to submit and marks the ones sent back, and a decider's
Approvals tab counts and groups what waits (decision 27). A digest or a push
needs a channel first: email infrastructure, or server push (#298, "Server
push: APNs / FCM notifications", outside this epic; today the companion's
notifications are local only).

### #352 — Sales and legal material

Three drafts in [legal/](legal/), unreviewed by counsel:

- `dpa.md`, the processing agreement;
- `works-council-sheet.md`, the one-page "what LifePete records" sheet;
- `dpia-template.md`, the DPIA template.

[legal/README.md](legal/README.md) says whose document each is, the two
facts to re-check before relying on them (Spain's fine amounts, Germany's
reform status, both last checked October 2026), and that **counsel review
is the whole blocker**. Nothing there reaches a customer first. When counsel
signs them off, they move to `docs/`.

Re-read them against `docs/organisations.md` whenever a decision changes
what an organisation sees (they were last aligned for decision 32). The
works-council sheet's whole point is that every sentence can be checked.

### #424 — A back office for the operator

Decision 31: an organisation whose last owner's account is erased stays as
it is, run by its admins, and noticing it is the operator's job. That needs
somewhere to notice it. The first thing a back office shows is
**organisations with no owner**. Until it exists, the only trace is the
`account.erased` event in that organisation's audit log.

A cheap interim, if the owner wants one first: `api/scripts/erase_account.py`
prints which organisations the erasure leaves without an owner (the operator
is the one running it). What a back office is — pages behind an operator
role, a CLI, or both — and what else belongs in it are the owner's call.
Keep it out of `/api/organisations` and away from every device prefix.

---

## Related, outside the epic

- **A note input in the companion** (#316, "Writing Tools on the post-stop
  note", macOS). The companion has no note input. If one comes back, it
  ships with the marker the web's input carries ("Acme can read this note"
  on an organisation's project, following the project picked), because the
  organisation reads an entry's note (decision 1).
- **Server push** (#298): the channel #351 waits on.

---

## Settled — do not reopen

A fresh reader tends to re-ask these. Each is decided in
`docs/organisations.md`; reopening one is a new decision for the owner, not
a fix.

- No live presence, ever: the record carries no `running` flag (decision 2).
- The API sends no email, and the invitations list carries no token
  (decision 11).
- An approved month refuses edits until a recorded reopen (decision 23).
- A merge never changes a stamp (decision 28). Closing is notice, and
  deletion hands back before it wipes (decision 29). Retention has a
  statutory floor, and expiry unstamps rather than deletes a living
  member's rows (decision 30).
- An organisation left without an owner stays as it is (decision 31).
- A decider reads the contract's terms on any assignment, and sharing is not
  control (decision 32).
- A decider may approve their own timesheet and absence request, for now
  (decision 33).
- The price (`docs/pricing.md`), and the SSO shape (#342 above).

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

---

## Found since the last sync

Out-of-scope problems found while working from this file, waiting for
someone with GitHub to file them. Use this shape, one per problem, and
delete the entry once it has an issue number:

```
### <title stating the problem in plain words>
Labels: <surface: api, ui, companion, daemon, docs, …>, <bug | enhancement | decision>
Where: path/to/file.py:~line (function)
What is wrong, why it matters, and what you would do about it.
```

None yet.
