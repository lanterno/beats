---
linear: unfiled
title: "Organisations: foundations — membership, org-owned projects, leaving (phase 2)"
team: AHM
project: lifepete
milestone: none
labels: [api, ui, Feature]
state: Backlog
priority: 2
parent: AHM-74
---

AHM-74's second phase, and the one that changes the data model. Sections 1, 2
and 6 of the epic: organisations and membership, organisation projects on the
personal timeline, connecting an existing project, the "What Acme can see"
page, and leaving.

Phase 1 is done (1a clients and rates, 1b billing budgets, 1c report links) and
needed none of this.

## Scope

- Organisations: name, logo, week start, default holiday region, timezone.
- Joining by email invite and by invite link with an optional approval step.
  Verified domains, SSO and SCIM are phase 4.
- Roles Owner / Admin / Member. Manager, Viewer and the money permission are
  phase 4.
- Organisation-owned projects, assigned to members, appearing in each member's
  own project list marked with the organisation.
- Connecting an existing personal project to an organisation, sharing history
  only from a date the person picks, or starting fresh.
- Filters over one timeline: Everything · Personal · Acme.
- The "What Acme can see" page, in plain sentences, showing the actual data
  held.
- Leaving and removal: tracking stops, the projects leave the active list, a
  read-only "Acme (left)" archive remains, the organisation keeps the hours.

## What the code says this costs

Researched on the 1c branch; all of it is current.

**The wall is one line.** `MongoStore._q`
(`api/src/beats/infrastructure/repositories.py:104`) stamps
`{"user_id": self.user_id}` onto every query. Eighteen repositories inherit it
and twenty dependencies build them (`_user_scoped` in
`api/src/beats/api/dependencies.py`). Principle 3 — "hours, not the person" —
is already enforced mechanically for every collection; phase 2's job is to
widen it for exactly one and leave the other seventeen untouched. That is the
whole privacy story, and it should stay a collection boundary rather than
become a serialiser allowlist.

**Only `projects` needs a second owner.** A beat on an organisation's project
is still the member's own document, and should stay user-scoped. The
organisation never gets a user-scoped repository for somebody else; it gets a
reader keyed on *project id*, across users. Absences, adjustments and the
contract follow the project the same way.

**1c already built that read, one user at a time.**
`BillingService.client_period` takes a set of project ids, reads the beats
started in a range over them, and assembles — without ever touching another
client's inputs. An organisation's read of its own projects is the same shape
with the user filter removed. And 1c established the pattern for a read that
crosses users: one narrow unscoped class that does nothing else
(`MongoReportLinkLookup`), with the route saying at the call site why the
account did not come from a token. Phase 2 should reuse both rather than
invent.

**Three things that will bite, found by reading rather than guessing:**

1. **`projects` has no index at all.** `ensure_indexes`
   (`api/src/beats/infrastructure/database.py`) covers eighteen collections
   and `projects` is not among them — every project list is a collection scan
   filtered by `user_id`. That is fine for one person's twenty projects and
   wrong the moment a project list is "mine, plus every organisation project
   I am assigned to" across every tenant. Filed separately; fix it before the
   read gets more complicated, not after.
2. **Devices already reach `/api/projects` by prefix.**
   `DEVICE_ALLOWED_PREFIXES` in `api/src/server.py` matches `/api/projects`
   and `/api/beats`, and the timer's status hands a paired device the project
   document whole. That is *correct* — a member tracks on organisation
   projects from their Mac app and wall clock like any other — but it means an
   organisation-owned project document is handed to every paired device of
   every assigned member. Nothing the organisation considers private may live
   on that document. This is the same reasoning as `docs/billing.md` decision
   2, which kept money off `Project` for exactly this reason.
3. **The full backup exports the user's projects.** `GET /api/export/full`
   (version 1.3) carries projects, sessions, absences and adjustments. What a
   personal backup does with an organisation-owned project — and what an
   import does with one — is undecided and needs to be before the export
   silently starts including other people's working-time records.

**The coach is already safe and should stay dumb about this.** It queries
Mongo directly with its own `user_id` filters in six modules (`brief.py`,
`chat.py`, `context.py`, `feedback.py`, `memory.py`, `usage.py`) and has no
ports to widen. Give it no organisation port either.

## Blocked on

Four of AHM-74's open decisions gate this phase and should be resolved first:
notes and tags crossing, live presence, account deletion against legal
retention, and what "day job" means once an employer is an entity. Each is
filed as its own `decision` issue.
