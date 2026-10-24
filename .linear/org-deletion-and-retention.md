---
linear: unfiled
title: "Decide what account deletion does to working-time records an employer must keep"
team: AHM
project: lifepete
milestone: none
labels: [api, decision]
state: Backlog
priority: 2
parent: AHM-74
---

From AHM-74's decisions:

> Account deletion and legal retention. Spain keeps records for 4 years, for
> example. Proposed: the organisation keeps the working-time rows, with the
> name kept only as the employer's own record. Everything else is erased.

Gates phase 2, because "leaving" and "being removed" are in that phase and
deletion is the same question one step further.

## Why it needs an answer before the data model is set

Today deletion is total and simple: PRIVACY.md promises that emailing the
operator removes **every** document associated with the user, and lists them.
The proposal above makes that promise conditional for the first time — some
rows survive, under someone else's control, with a name attached.

That is a defensible position and probably the legally required one, but it
changes what we can honestly say on the privacy page, and it has to be
decidable **per row** at deletion time. Which means the ownership model from
phase 2 has to make "this beat is an organisation's working-time record" a
property of the document rather than something inferred by joining through a
project that is itself being deleted.

## What has to be answered

- Which rows survive: beats on organisation projects only, or absences and
  approved timesheets too?
- What identifies the person on a surviving row once the account is gone — a
  name, an employee number, an opaque id the employer can map themselves?
- Who can delete them afterwards, and when does the retention clock stop?
- Does the person get an export before deletion, as the epic promises for a
  deleted organisation?
- What does PRIVACY.md say instead of what it says now?

## Related

Retention settings per organisation are phase 4, but the per-row decision here
is what makes them implementable.
