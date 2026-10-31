# A back office for the operator

LifePete has one operator (PRIVACY.md says so in those words), and no place
for them to stand. Everything an operator does today is a script in
`api/scripts/` run by hand against the production database, and everything
an operator should *notice* is noticed only if they happen to look.

Split out of [roadmaps/organisations.md](organisations.md) on 2026-10-31.
It was filed there as #424, because an organisation left without an owner
was the first thing anyone wanted to see — but a back office is not an
organisations feature, and tying it to that epic would have shaped it
around one view. **What it is, and what belongs in it, is the owner's call**;
this file holds the little that is already settled and the constraints that
hold whatever it turns out to be.

---

## What is settled

- **It exists for the operator, not for a user.** Nothing in it is a
  feature of the product; nobody reaches it from the app.
- **It is out of `/api/organisations`** and away from every device prefix
  (`DEVICE_ALLOWED_PREFIXES` / `DEVICE_READ_ONLY_PREFIXES` in
  `api/src/server.py`). A paired device must not be one `beatsd` bug away
  from an operator route.
- **Pages, a CLI, or both** is undecided. The existing operator surface is
  CLI (`scripts/erase_account.py`, `scripts/retention_purge.py`), which is
  an argument for staying there; the first thing anyone wants is a list,
  which is an argument for a page.

## What it owes on day one

**Organisations with no owner.** Decision 31: an organisation whose last
owner's account is erased stays as it is, run by its admins, and noticing
it is the operator's job. Owner-only acts — granting the owner role,
closing, deleting — wait until somebody acts on it. Until a back office
exists, the only trace is the `account.erased` event in that
organisation's audit log, which nobody reads unless they already suspect.

**A cheap interim, if the owner wants one first:**
`api/scripts/erase_account.py` prints which organisations the erasure
leaves without an owner. The operator is the one running it, so the
notice reaches the right person at the right moment, and it is perhaps
twenty lines. It does not replace the list — an organisation can lose its
owner through an erasure run before this existed — but it stops the bleed.

## Candidates, none of them decided

Written down so they are not rediscovered, not because they belong:

- **Retention.** `scripts/retention_purge.py` is operator-run and dry by
  default, and nothing schedules it, so nothing auto-deletes during the
  beta (decision 30). Whether a back office schedules it, or only shows
  what a dry run would take, is a question with a privacy answer as much as
  an operational one.
- **Erasure requests.** PRIVACY.md asks people to email the operator from
  the address on their account; the operator then runs a script. The
  identity check is a human reading an email header, which is worth saying
  out loud before it is automated.
- **Deployment health** — the live commit, the deploy lock
  (`beats/deploy.lock` in the state bucket), whether an apply is stuck. The
  terraform README covers this by hand today.
- **Seat counts**, once #345 makes them mean anything
  ([roadmaps/organisations.md](organisations.md)).

## The constraint that outlives the design

An operator surface reads across every tenant by definition — it is the
one thing in the system that is allowed to. That makes it the natural
place for the next cross-user read to be added carelessly. Whatever shape
it takes, it reads through **its own narrow classes**, the way
`MongoOrganisationRecords` and `MongoReportLinkLookup` do, and never by
widening `MongoStore._q` or by handing an existing service a wider scope.
The rule in [roadmaps/organisations.md](organisations.md) — *widen a
collection boundary, never a serialiser* — is not an organisations rule;
it is the rule, and this is the surface most likely to break it.
