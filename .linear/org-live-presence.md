---
linear: unfiled
title: "Decide whether a manager can see that a timer is running now"
team: AHM
project: lifepete
milestone: none
labels: [api, ui, decision]
state: Backlog
priority: 2
parent: AHM-74
---

From AHM-74's decisions:

> Can a manager see that a timer is running now? Proposed: off by default. An
> organisation can turn it on only with each member's consent, shown on the
> "can see" page.

## Where this already bites

Phase 1c had to answer a smaller version of it and answered no: a report link's
response carries no `running` flag, deliberately, so a client cannot learn from
an invoice's backing that a timer is on at this moment (`docs/billing.md`,
phase 1c decision 7). Whatever is decided here should not leave those two
surfaces contradicting each other.

## What makes it harder than a feature flag

"Off by default, on with each member's consent" is three states, not two —
organisation off, organisation on but this member has not consented,
organisation on and consented — and the third is the only one that shows
anything. A per-member consent record is a small amount of storage and a large
amount of care: it has to be revocable, it has to be visible on the "What Acme
can see" page, and revoking it has to take effect immediately rather than at
the next read.

It is also the single feature most likely to be read as surveillance by a works
council, which is the audience the epic is explicitly selling to. The cheapest
correct answer may be "not at all, in any phase" — worth considering against
the proposal rather than assuming the proposal.
