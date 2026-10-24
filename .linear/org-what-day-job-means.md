---
linear: unfiled
title: "Decide what \"day job\" means once an employer can be an entity"
team: AHM
project: lifepete
milestone: none
labels: [api, decision]
state: Backlog
priority: 3
parent: AHM-74
---

From AHM-74's decisions:

> What "day job" means now. The first decision in docs/work-contracts.md says
> the day-job project is the contract; an employer is not an entity.
> Organisations reverse that for employer-owned projects. Does a day job with
> no organisation behind it stay as it is today? Proposed: yes, nothing forces
> anyone into an organisation.

## Why it is more than a documentation edit

`docs/work-contracts.md` decision 1 is load-bearing in the code, not just
prose. `ProjectKind.DAY_JOB` is what permits a `Contract` at all —
`ProjectService` answers 409 `NOT_A_DAY_JOB` on any other kind — and a
startup migration derives a day job's contract from its goal history
(`infrastructure/migrations.py`). The kind means "this project is a job", and
the contract hangs off it.

After phase 2 there are two kinds of day job: one whose contract its owner
wrote, and one whose contract an employer owns and the employee only reads.
They need the same arithmetic and different write rules.

The proposal — personal day jobs stay exactly as they are — is almost certainly
right, and it is cheap: it means the employer-owned case is an additional
state, not a replacement. Worth confirming explicitly, though, because the
alternative (every day job must belong to an organisation) would be a
migration and a far worse product.

Whatever is decided, `docs/work-contracts.md` decision 1 has to be rewritten
rather than left to contradict the code, and the rewrite is part of phase 2 or
3, not a follow-up.
