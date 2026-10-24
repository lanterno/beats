---
linear: unfiled
title: "Decide whether a report link shows an entry's note"
team: AHM
project: lifepete
milestone: none
labels: [api, ui, decision]
state: Backlog
priority: 0
parent: AHM-74
---

`docs/billing.md` leaves this open where it lists what the month report shows:

> No notes and no tags. Whether a client's report shows notes is a decision for
> report links.

Phase 1c shipped without it: a link shows project names, lines and entries, and
no note. AHM-74 proposes the opposite answer for organisations —

> Does the organisation see the note on an entry? Proposed: yes, since it
> describes the work and clients need it for invoices, with a visible marker on
> the input. Do personal tags (#deep, #meeting) cross? Proposed: no.

— so the two surfaces should be decided together rather than drifting apart.

## What it would take

`BillingEntry` (`api/src/beats/domain/billing.py:180`) carries no note today, so
`assemble_client` would have to thread one through. The private month report
must keep *not* showing it, which is why the public and private response
schemas are written separately: adding `note` to the domain tuple must not
reach either response without a deliberate field.

Adding it later is additive — a third flag beside `show_amounts` and
`show_entries`, defaulting off, so links already minted keep showing what their
owner saw when they minted them.

## The part that is not code

If a note crosses to a third party, the note input needs the visible marker the
epic asks for, on every surface that writes one: the SPA, the companion's "How
did it go?" sheet, the VS Code extension and the daemon. Deciding yes means
that work, not just the flag.
