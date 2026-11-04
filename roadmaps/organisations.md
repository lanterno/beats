# Organisations — what is left to build

The epic is GitHub issue #353. Four stages of it have shipped, and so have
fifteen of the sixteen bugs the 2026-10-31 audit found. What is left here
is **one page for the owner to read and five items that wait on something
outside the code** — each written out in full below. Nothing here is built
by hand any more; everything left is a decision, a reading, or a wait.

| # | What | Blocked by | Start when |
|---|------|-----------|------------|
| 422 | PRIVACY.md, drafted and already public on `main` | The owner reading every sentence | Nothing to start: once it is read, delete its section |
| 340 | Money behind the organisation's own roles | No organisation-side money exists to guard | Organisation-side money is designed |
| 341 | Verified email domains for joining | No verified address: the API sends no email, and an account has one address, not many ([account-emails.md](account-emails.md)) | Accounts carry verified secondary addresses |
| 345 | Per-seat billing | No payment machinery anywhere; the beta runs for months yet ([subscriptions.md](subscriptions.md)) | The end of the beta is decided |
| 351 | Telling people what is missing or waiting | No channel: server push is #298 ([server-push.md](server-push.md)) | #298 ships |
| 352 | DPA, works-council sheet, DPIA template | Counsel review | The owner takes it up — **they have said it matters** |

Five things that used to live here now have roadmaps of their own, because
none is an organisations feature: SSO per organisation and SCIM
([organisation_sso.md](organisation_sso.md)), the operator's back office
([docs/backoffice.md](../docs/backoffice.md); its open ends in
[backoffice.md](backoffice.md)), several verified addresses on an account
([account-emails.md](account-emails.md)), server push
([server-push.md](server-push.md)) and taking the money
([subscriptions.md](subscriptions.md)).

**This file is meant to be enough on its own.** Whoever picks it up may have
no access to GitHub. So unlike the other roadmaps, which link to issues and
never restate them, this one carries each open issue's whole content: what
is wrong, where, what to do, and what to test. Each item keeps its GitHub
number so the two can be synced by whoever has access. If this file and an
issue disagree, this file was written later (2026-10-31), but say so to the
owner rather than picking one silently.

What is already built — the four rules, decisions 1–33, the data model, the
HTTP contract and the rules the UI keeps — is
[docs/organisations.md](../docs/organisations.md). **Read it first.** Items
below cite its decisions by number.

---

## How to work from this file

1. **Read** [docs/organisations.md](../docs/organisations.md) and the
   repo-root `CLAUDE.md` (commands, conventions, and *What to test, and what
   not to*). For the API, also `api/CLAUDE.md`.
2. **Pick** from the table at the top. Items marked **Ask the owner
   first** contain a choice that is the owner's to make. Ask in the session,
   then write the answer into `docs/organisations.md` as a decision before
   building. An item that records a decision already taken says so and
   dates it — build to it rather than reopening it.
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
   - delete its section here, and its row in the table at the top;
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
  enforces rule 3 mechanically across every repository built on it
  (decision 4). Stage 2 widened it for exactly one collection (`projects`)
  and left the rest alone. A read that crosses users gets its own narrow
  class that does nothing else — as `MongoOrganisationRecords` and
  `MongoReportLinkLookup` do — not a filter applied after the fact, and not
  a field allowlist somebody has to remember.
- **The coach never reaches past the member.** It reads projects through
  the member's own merged repository (`project_repository_for`, called in
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
  taking a project off someone ends the assignment; merging two of its
  projects (decision 28) and deleting the organisation (decision 29)
  repoint rows. The one exception is rows kept under an `erased:`
  tombstone, which go when the organisation is deleted or its retention
  expires. Keep it that way in every fix below.

---

## Bugs in what shipped

Found on 2026-10-31 by checking `docs/organisations.md` against the code.
Fifteen of the sixteen have shipped and their sections are deleted: #404,
#405, #406, #407, #408, #409, #410, #411, #412, #413, #414, #415, #419,
#420, #421; what they changed is in
[docs/organisations.md](../docs/organisations.md). One is open: #422, which
needs the owner's eyes rather than anybody's hands.

### #422 — PRIVACY.md, drafted and waiting for the owner to read it

`PRIVACY.md` is the owner's promise to users, so **the owner reads every
sentence of it.** The draft has already shipped: commit `b8dd8f7b`, which
brought `PRIVACY.md` and `DATA.md` up to what the code does, is on `main`,
and the homepage's Privacy link opens `PRIVACY.md` on `main`
(`ui/client/pages/homepage/HomePage.tsx`), so users read it today. The
owner's reading is the only thing left here; the work is done.

That commit's message lists each change and why, and its diff is where the
new promises are. For the one promise the code broke — that nothing
downstream records which door a sign-in used — the owner chose to change
the code, not the page: `13e6f9d7` took the provider and the person out of
the sign-in log line in `api/src/beats/api/routers/sso.py`, and the comment
there and that commit's message say why both had to go.

**When the owner has read it**, delete this section. If a sentence needs
changing, that is a `docs(legal):` commit of its own, not a reopening of
the epic.

---

## Waiting on something outside the code

None of these should be started until its blocker clears. Each section says
what blocks it, when to start, and what it must not do. Three of them — #341,
#345 and #351 — wait on a roadmap split out of this file (see the top), and
say what stays this epic's when it lands.

### #340 — Money behind the organisation's own roles

There is no organisation-side money at all: billing stayed personal, and an
organisation's project is billed by nobody (`ORGANISATION_PROJECT`, raised
in `domain/billing_service.py`). So there is nothing to guard yet, and this
waits on a design that does not exist rather than on a dependency.

**Decided 2026-10-31 by the owner: money is read by owners and admins.**
The epic had carried "seeing money is its own permission, independent of
role" since stage 4; it is not that. It is the organisation's existing role
ladder, which means it fits the shape decision 25 already set — what the
roles below admin may do is read off **capabilities on the role**
(`decides`, `reads_record`), not off rungs, and administering is the ladder
from admin up. So this is one more capability, true for owner and admin and
false below:

```
reads_money: owner yes, admin yes, manager no, viewer no, member no
```

A manager decides timesheets and reads their teams' hours and still sees no
money; a viewer — an accountant, a works-council seat — reads the whole
working-time record and still sees no money, which is the case that proves
the capability is not the record's.

**It must not be bolted on.** Every other item here is additive, but for
#345's read-only state, which must be one gate on every write under
`/api/organisations` ([subscriptions.md](subscriptions.md)). This one is a
cross-cutting read rule, and the cheapest version — a flag checked in each
billing route — is the version that leaks the first time somebody adds a
route and forgets. The seam already exists: clients, project billing,
billable overrides and billing budgets are their own collections, outside
every device prefix, with no coach port. Attach to that boundary, the way
#342 attaches its check in one place — `OrganisationService._member`, which
both routers under `/api/organisations` go through
([organisation_sso.md](organisation_sso.md)).

### #341 — Verified email domains

People with an `@acme.com` address ask to join, or join automatically.

**Blocked on the account model, not on this epic.** The rule the owner set
(2026-10-31) is to match the domain against one of the account's **verified**
addresses — never a typed string — and an account holds one address today,
and nothing has verified it. That prerequisite is its own piece of work:
[account-emails.md](account-emails.md), which also carries the verification
flow and the narrow revisiting of decision 11's no-email rule that it needs.

What stays this epic's when that lands is small and worth stating now: a
domain rule is a property of the organisation, it makes a **join request**
or a membership by exactly the paths an invite link already does
(`requires_approval`), and it must never be a way in that skips decision
11's reasoning — whoever registers an address must not be handed the
organisation because of it.

### #345 — Per-seat billing

**The price is decided** ([docs/pricing.md](../docs/pricing.md), 2026-10-28)
and **collecting it has a roadmap of its own**:
[subscriptions.md](subscriptions.md). A payment provider, EU VAT, invoices
and dunning are not an organisations feature, and the owner has it on hold
while the beta runs (2026-10-31).

What is this epic's, and is written into that file rather than built here:
a seat today is counted off `org_members` and `org_assignments`, but a past
period is not — a rejoin or a reassignment reopens the same document, a
membership keeps only its current role, and `org_audit` can lose an event —
so billing a period needs seat history of its own; an organisation that
does not pay goes **read-only, never deleted**, because its working-time
record is a legal one; and no billing state may ever refuse a person their
own data (rule 1).

### #351 — Telling people what is missing or waiting

Today this shows where people already look: a member's timesheet list offers
the ended months still to submit and marks the ones sent back, and a
decider's Approvals tab counts and groups what waits (decision 27).

**Decided 2026-10-31 by the owner: the channel is server push, and the
person controls what they get.** Push is a platform capability rather than
an organisations one, so it has its own roadmap —
[server-push.md](server-push.md), issue #298 — and it carries the
constraints that decide its shape, Cloud Run's among them.

What is this epic's, once a channel exists: which moments are worth a push
at all. The candidates are the three the surfaces already show — a month
ended and still to submit, a request waiting on my decision, a request of
mine decided — and the rule the owner set holds over all of them: an
employer must not be able to turn on a notification its members cannot turn
off. Decision 11's no-email rule is untouched; push is not email.

### #352 — Sales and legal material

Three drafts in [legal/](legal/), unreviewed by counsel:

- `dpa.md`, the processing agreement;
- `works-council-sheet.md`, the one-page "what LifePete records" sheet;
- `dpia-template.md`, the DPIA template.

[legal/README.md](legal/README.md) says whose document each is and that
**counsel review is the whole blocker**. Two facts in the works-council
sheet go stale on their own — Spain's fine amounts and Germany's reform
status, both last checked in October 2026 — and are re-checked before
anyone relies on them. Nothing there reaches a customer first.

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
  it will use — no reminder goes by email (decision 11, and the owner again
  on 2026-10-31).

---

## Settled — do not reopen

A fresh reader tends to re-ask these. Each is decided where its line
points — a numbered decision in `docs/organisations.md`, or else the file
or section it names; reopening one is a new decision for the owner, not a
fix.

- No live presence, ever: the record carries no `running` flag (decision 2).
- The API sends no email, and the invitations list carries no token
  (decision 11). The one narrow revisit, a verification message and never
  an invitation or a reminder, is [account-emails.md](account-emails.md)'s.
- An approved month refuses edits until a recorded reopen (decision 23).
- A merge never changes a stamp (decision 28). Closing is notice, and
  deletion hands back before it wipes (decision 29). Retention has a
  statutory floor, and expiry unstamps rather than deletes a living
  member's rows (decision 30).
- An organisation left without an owner stays as it is (decision 31).
- A decider reads the contract's terms on any assignment it decides for,
  managed or not, and sharing is not control (decision 32).
- A decider may approve their own timesheet and absence request, for now
  (decision 33).
- The price (`docs/pricing.md`), and the SSO shape
  ([organisation_sso.md](organisation_sso.md)).
- A contract write is never refused for an approved month; it marks the
  approval instead (decision 23, built 2026-10-31).
- Money in an organisation is read by owners and admins, as a capability on
  the role — not a permission of its own (#340 above, decided 2026-10-31).
- What the epic will never build — work-only accounts, workspaces inside an
  organisation, payroll, and above all any monitoring for employers — is in
  [docs/organisations.md § Out of scope, by decision](../docs/organisations.md#out-of-scope-by-decision).

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
