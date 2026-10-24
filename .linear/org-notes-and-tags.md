---
linear: unfiled
title: "Decide whether an organisation sees an entry's note, and whether personal tags cross"
team: AHM
project: lifepete
milestone: none
labels: [api, ui, decision]
state: Backlog
priority: 2
parent: AHM-74
---

One of AHM-74's listed decisions, and it gates phase 2: an organisation's read
of its own projects either carries the note on each entry or it does not.

The epic's proposal:

> Does the organisation see the note on an entry? Proposed: yes, since it
> describes the work and clients need it for invoices, with a visible marker on
> the input. Do personal tags (#deep, #meeting) cross? Proposed: no. The
> organisation defines its own tags.

## Why it has to be decided before phase 2, not during

Principle 3 lists exactly what crosses — "start, end, duration and the entry's
note". The note is the only free-text field in that list, and the only one a
person might write something personal into without realising who reads it. If
the answer is yes, the visible marker is not a nicety: it is the thing that
makes the rule honest, and it has to appear on **every** surface that writes a
note — the SPA, the companion's "How did it go?" sheet, the VS Code extension
and anything the daemon writes. That is real work in four places, and it has to
land with the feature, not after.

Tags are the easier half. They are derived from the daemon's flow windows when
a session is logged or stopped, which makes them a signal about *how* someone
worked, not *what* they worked on — much closer to the flow scores the epic
puts firmly on the far side of the wall. "No" looks right, and saying so in the
decision record is worth more than the code it saves.

## Related

[report-links-notes](report-links-notes.md) is the same question for a
freelancer's client. Phase 1c shipped without notes so the two could be decided
together rather than drift apart; decide them in one sitting.
