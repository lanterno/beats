# Organisations — what is left to build

The epic is GitHub issue #353. Four stages of it shipped, and so have
fourteen of the sixteen bugs the 2026-10-31 audit found. What is left here
is **one design to build, one page for the owner to read, and five items
that wait on something outside the code** — each written out in full below.

Two things that used to live here now have roadmaps of their own, because
neither is an organisations feature: SSO per organisation and SCIM
([organisation_sso.md](organisation_sso.md)), and the operator's back
office ([backoffice.md](backoffice.md)).

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
   before building. An item that records a decision already taken says so
   and dates it — build to it rather than reopening it.
3. **Work on one branch in the worktree**, and **do not push and do not
   open a pull request**: the owner merges and syncs GitHub themselves
   (2026-10-31). Several items in one session share that branch; the
   commits are what keep them apart, so split them as rule 4 says.
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

Most important first.

| # | What | Surface | Why at this place |
|---|------|---------|-------------------|
| 405 | A contract write marks the approvals it moves | api, ui | Designed below and decided; the only thing here that is built rather than waited on |
| 422 | The owner reads the PRIVACY.md draft | docs | Written and committed; one reading away from done |
| 340–352 | The five waiting items | — | Each when its blocker clears; see the section |

Fourteen of the sixteen bugs the 2026-10-31 audit found have shipped and
their sections are deleted: #404, #406, #407, #408, #409, #410, #411, #412,
#413, #414, #415, #419, #420, #421 — and of #405, the three writes that
needed no decision. What they changed is in
[docs/organisations.md](../docs/organisations.md); what is left of #405 and
#422 is below.

---

## Bugs in what shipped

Found on 2026-10-31 by checking `docs/organisations.md` against the code.
Of the sixteen, these two are open: #405, whose fix needed a decision the
owner has since taken, and #422, which needs the owner's eyes rather than
anybody's hands.

### #405 — A contract write marks the approvals it moves

**Decided 2026-10-31 by the owner: a contract write is never refused for
an approved month. The approval is marked instead.** Refusing would make a
term the employer got wrong unfixable once any month is approved, without
first reopening every approved month — the wrong default for what is
usually an administrative correction. And the frozen figures do not move:
they are stored. What changes is that the live ledger would now compute
something else. That is a fact *about the approval*, so the approval is
where it belongs.

Write it into decision 23 when it is built, not before — nothing here has
shipped.

**What already holds.** Decision 23's lock refuses every write dated inside
an approved month. Five writes skipped it; three are fixed (removing an
absence, removing a balance adjustment, and a backup's beat, which the
import now reports under `skipped` as `PERIOD_APPROVED`). The two left are
contract writes, and a contract write is not dated inside a month at all —
it is a list of terms spanning all of them, which is why the lock never
caught it and why refusing it is the wrong instrument:

- the member's, on an unmanaged assignment (`ProjectService.update_project`
  and `replace_contract`, and the adjustment purge `reconcile_adjustments`
  triggers);
- the employer's (`EmploymentService.set_contract`).

#### The model extension

**1. An event is not a status.** `TimesheetEvent.action` is typed
`TimesheetStatus` today, so the history cannot say anything a state cannot.
Widen it to a `TimesheetAction` StrEnum carrying the four existing strings
unchanged (`submitted`, `approved`, `changes_requested`, `reopened`) plus
`terms_changed`. Stored documents keep reading, and `status` keeps its own
narrower enum: a state the sheet is in and a thing that happened to it are
different sets, and collapsing them is what forces the next awkward field.

**2. `OrgTimesheet` gains `superseded_at: datetime | None` and
`superseded_by: str | None`** — when the terms behind an approved month
last moved, and who moved them. Null on a sheet whose terms still stand.

**`status` stays `approved`.** Making this a status value would be the
tempting shortcut and is a trap: `MongoPeriodLocks` keys the lock on
`status == approved`, so a `superseded` status would **silently unlock the
month** — the exact opposite of what is wanted. The month is still
approved, still locked, and its frozen figures are still the record; what
is in doubt is only whether a decider would approve the same figures today.

**3. The sheet's `history` gains a `terms_changed` event** at the same
moment, with the same `at` and `by`. The sheet then reads in order —
submitted, approved, terms changed — which is what a works council asks to
see, and `superseded_at` is the short answer to "is this approval still
current?" while the history is the long one.

A reopen already drops `frozen`; it drops these too, and the re-approval
freezes against the terms now in force. So the way back is the one that
already exists (decision 23), and nothing new has to be explained.

#### Which sheets a write marks

Not every approved sheet on the assignment: a term added for next year
moves nothing already approved, and marking everything would train people
to ignore the mark. One pure function decides it:

```
contract_diverges_from(previous: Contract | None, new: Contract | None) -> date | None
```

the earliest day on which the two contracts can produce a different figure,
or None when they cannot. Its cases, each a test:

- **`opening_balance_hours`** changed → the contract's first day. Every
  month's `balance_end` moves even where its `expected` does not.
- **`terms`** changed → the earliest `effective_from` that is in one list
  and not the other, or whose fields differ.
- **`ended_on`** changed → the earlier of the two, or the one that is set
  when the other is None.
- **`holiday_country` / `holiday_subdivision`** changed → the contract's
  first day. Which holidays actually moved cannot be known without walking
  the calendar, and erring early marks more approvals rather than fewer.
- **`company_holidays` / `holidays_not_given`** changed → the earliest date
  in the symmetric difference. A company day whose *name* changed and whose
  date did not moves no figure.
- **`vacation`** changed → **nothing**. The entitlement is days of leave
  left; no month's `worked`, `expected` or `balance_end` reads it.
- the contract **arriving or going** → its first day, or the previous one's.

Then every approved sheet whose month *ends* on or after that day is
marked — the month containing the divergence day is affected too, not only
the months wholly after it.

#### Where it hooks in

Both writes, through one path, because decision 21 says one set of rules
validates a contract whoever writes it — and because the member's own write
marking the employer's approval is the whole point: it turns a silent
divergence into a visible one.

Both callers already hold the pair the helper needs: the member's path
takes `previous_contract` as a required keyword, and the employer's reads
`assignment.contract`.

The member's path writes through `ProjectService`, which holds no
organisation store and must not gain one. Give it **a narrow port in the
shape of `PeriodLocks`, which it already holds** — one method, "mark the
approved sheets on this project for this member from this day" — so a
service that writes projects still cannot read another member.

#### What it is not

It is **not a second stored derived figure**. The mark says *that* the
terms moved, never what the month would come to now; recomputing that is
the ledger's job, done when a decider opens the sheet. The frozen month
stays the only stored derived working-time figure, which decision 23 calls
the one thing stage 3 broke on purpose and the hardest to migrate out of.

#### Test

- **`contract_diverges_from` on its interesting inputs**, pure, beside
  `test_contracts.py`: a term appended after every approved month (None), a
  term edited in the middle, an opening balance moved, a region swapped, a
  company holiday renamed but not moved (None), a vacation entitlement
  changed (None), a contract removed.
- **The HTTP contract**, in `test_organisations.py`: approve a month,
  change a term inside it, and assert the sheet is still `approved`, still
  locked, and carries `superseded_at` with a `terms_changed` history entry;
  that a term added after the month leaves it untouched; and that a reopen
  and re-approval clear the mark.

#### The UI, when the API is there

The decider's Timesheets tab marks a superseded approval and says what to
do about it (reopen, or let it stand on the terms in force at the time);
the member's own timesheet list says the same of their own months. Neither
shows a recomputed figure next to the frozen one without the decider asking
for it — two numbers side by side is the confusion decision 23 exists to
avoid.

### #422 — PRIVACY.md, drafted and waiting for the owner to read it

`PRIVACY.md` is the owner's promise to users, so **the owner reads every
sentence before it ships.** That reading is the only thing left here; the
work is done.

**Drafted.** Single sign-on's stored name, email and `linked_at` (and
`identities[]` in `DATA.md`, which listed none of it); the contract's terms
beside its balance, and that sharing hands over no power to delete; a
connected project keeping its history back through every later edit;
timesheets, approval, the lock and entered time working on any assignment
rather than only a managed one, with owners and managers entering time;
closing and deletion (decision 29); and retention named as the country's
floor, reaching what #408 made it reach.

**Settled 2026-10-31, and done.** The sentence "nothing downstream records
which door was used" held for sessions but not for the log:
`POST /api/auth/sso/complete` wrote `provider=… user=…` on every single
sign-in into 30 days of Cloud Logging. The owner took the recommendation —
the code changed, not the page. Dropping the provider alone would not have
been enough, since a line firing only on the SSO path and naming the
account still records that this person came through SSO; what is left names
neither.

**When the owner has read it**, delete this section. If a sentence needs
changing, that is a `docs(legal):` commit of its own, not a reopening of
the epic.

---

## Waiting on something outside the code

None of these should be started until its blocker clears. Each section says
what blocks it, when to start, and what it must not do.

Two items left this file on 2026-10-31 and have roadmaps of their own: SSO
per organisation and SCIM ([organisation_sso.md](organisation_sso.md)), and
the operator's back office ([backoffice.md](backoffice.md)) — a back office
is not an organisations feature, and filing it here was shaping it around
one view.

| # | What | Blocked by | Start when |
|---|------|-----------|------------|
| 340 | Money behind the organisation's own roles | No organisation-side money exists to guard | Organisation-side money is designed |
| 341 | Verified email domains for joining | An account has one email address, not many | Accounts carry verified secondary addresses |
| 345 | Per-seat billing | No payment machinery anywhere; the beta runs for months yet | The end of the beta is decided; then as its own project |
| 351 | Telling people what is missing or waiting | No channel: server push is #298 | #298 ships |
| 352 | DPA, works-council sheet, DPIA template | Counsel review | The owner takes it up — **they have said it matters** |

### #340 — Money behind the organisation's own roles

There is no organisation-side money at all: billing stayed personal, and an
organisation's project is billed by nobody (`ORGANISATION_PROJECT`, raised
in `domain/billing_service.py`). So there is nothing to guard yet, and this
waits on a design that does not exist rather than on a dependency.

**Decided 2026-10-31 by the owner: money is read by owners and admins.**
The epic had carried "seeing money is its own permission, independent of
role" since stage 4; it is not that. It is the organisation's existing role
ladder, which means it fits the shape decision 25 already set — rights are
read off **capabilities on the role** (`administers`, `decides`,
`reads_record`), not off rungs. So this is one more capability, true for
owner and admin and false below:

```
reads_money: owner yes, admin yes, manager no, viewer no, member no
```

A manager decides timesheets and reads their teams' hours and still sees no
money; a viewer — an accountant, a works-council seat — reads the whole
working-time record and still sees no money, which is the case that proves
the capability is not the record's.

**It must not be bolted on.** Every other item here is additive; this one is
a cross-cutting read rule, and the cheapest version — a flag checked in each
billing route — is the version that leaks the first time somebody adds a
route and forgets. The seam already exists: clients, project billing,
billable overrides and billing budgets are their own collections, outside
every device prefix, with no coach port. Attach to that boundary, the way
#342 attaches its check to the organisation router in one place.

### #341 — Verified email domains

People with an `@acme.com` address ask to join, or join automatically.

**Decided 2026-10-31 by the owner: this waits on an account being able to
hold more than one address**, and the rule is then to match the domain
against one of the account's **verified** addresses — never against a
string somebody typed. An account keeps one **main** address, the one it is
known and written to by, and any number of verified secondaries beside it.

That ordering is the whole point. Decision 11 closed exactly this hole for
invitations: an address is not verified at sign-up, so whoever registers one
first must not be handed the way in. A domain rule over unverified
addresses reopens it deliberately, and at organisation scale rather than one
invite at a time.

So the prerequisite is its own piece of work, not a detail of this one:
multiple addresses per account, each verified or not, one of them main,
with the verification flow that makes "verified" mean anything — which is
the email infrastructure the API deliberately does not have yet. Build that
first; then this is a small rule on top of it.

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
dunning are a dependency well outside the shape of this epic.

**On hold, deliberately: the owner expects the beta to run for some months
yet (2026-10-31).** Treat it as its own project when the end of the beta is
decided, not as the tail of this one.

### #351 — Telling people what is missing or waiting

Today this shows where people already look: a member's timesheet list offers
the ended months still to submit and marks the ones sent back, and a
decider's Approvals tab counts and groups what waits (decision 27).

**Decided 2026-10-31 by the owner: the channel is server push, not email**,
and **the person controls what they get.** So this waits on #298 ("Server
push: APNs / FCM notifications", outside this epic; the companion's
notifications are local only today), and when it comes it ships with its
own settings rather than a switch somebody has to ask for:

- per category at least — a timesheet still to submit, a request waiting on
  my decision, a request of mine decided — and off entirely as one choice;
- the preference is the person's, not the organisation's. An employer must
  not be able to turn on a notification its members cannot turn off; that is
  the line the whole product sits on the right side of.

Decision 11's no-email rule is untouched by this: push is not email, and the
API still sends none.

### #352 — Sales and legal material

Three drafts in [legal/](legal/), unreviewed by counsel:

- `dpa.md`, the processing agreement;
- `works-council-sheet.md`, the one-page "what LifePete records" sheet;
- `dpia-template.md`, the DPIA template.

[legal/README.md](legal/README.md) says whose document each is, the two
facts to re-check before relying on them (Spain's fine amounts, Germany's
reform status, both last checked October 2026), and that **counsel review
is the whole blocker**. Nothing there reaches a customer first.

**The owner has said this one matters (2026-10-31)** and will take it up
themselves; it is not waiting on a customer to ask. Re-read the three
against `docs/organisations.md` whenever a decision changes what an
organisation sees — they were last aligned for decision 32, and the fixes
of 2026-10-31 moved what a connect keeps back (#404) and what retention
reaches (#408), both of which the works-council sheet speaks to. Its whole
point is that every sentence in it can be checked.

## Related, outside the epic

- **A note input in the companion** (#316, "Writing Tools on the post-stop
  note", macOS). The companion has no note input. If one comes back, it
  ships with the marker the web's input carries ("Acme can read this note"
  on an organisation's project, following the project picked), because the
  organisation reads an entry's note (decision 1).
- **Server push** (#298): the channel #351 waits on, and now the only one
  it will use — email is not coming (decision 11, and the owner again on
  2026-10-31).

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
- The price (`docs/pricing.md`), and the SSO shape
  ([organisation_sso.md](organisation_sso.md)).
- A contract write is never refused for an approved month; it marks the
  approval instead (#405 above, decided 2026-10-31).
- Money in an organisation is read by owners and admins, as a capability on
  the role — not a permission of its own (#340 below, decided 2026-10-31).

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
