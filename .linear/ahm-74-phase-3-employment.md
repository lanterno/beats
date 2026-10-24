---
linear: unfiled
title: "Organisations: employment — employer contracts, leave requests, timesheet approval (phase 3)"
team: AHM
project: lifepete
milestone: none
labels: [api, ui, Feature]
state: Backlog
priority: 3
parent: AHM-74
---

AHM-74's third phase, section 3 of the epic. It turns the day-job contract we
already have into something two parties agree on. Depends on phase 2: there is
no employer to own a contract until organisations exist.

## Scope

- Contract terms belong to the employer: weekly hours or percentage, start and
  end, holiday region, opening balance. A personal weekly goal stays the
  person's own.
- Absences become requests: the employee asks, a manager approves.
- Timesheets: submit a week or month, approve or ask for changes with a
  comment, approval locks the period and freezes that week's balance,
  reopening needs a reason and is recorded.
- Reminders for missing hours, unsubmitted timesheets, pending approvals.
- Admin-entered time, with the member notified and the change recorded.
- Compliance record: per person, per day, start / end / breaks / total,
  exportable and retained for the period local law requires. Rest-period and
  maximum-daily-hours warnings later.

## What already exists

More than the epic's wording suggests. All of this is built and tested:

- `Contract` with dated terms, holiday region, opening balance and `ended_on`
  (`domain/models.py`), plus the arithmetic in `domain/contracts.py`.
- Absences (`/{id}/absences`), typed vacation / sick / other, whole or half.
- Balance adjustments (`/{id}/adjustments`) — AHM-32.
- The monthly timesheet, a row per finished day, as CSV
  (`/{id}/timesheet.csv?month=`, `domain/timesheet.py`) — AHM-30.
- The vacation entitlement, a year at a time (`domain/vacation.py`) — AHM-31.
- Employer holidays, company additions and removals (`domain/holidays.py`) —
  AHM-33.

So phase 3 is mostly about **who owns these and who may approve them**, not
about computing anything new. The compliance record is the one genuinely new
artefact, and even it is close to the timesheet's shape with breaks added.

## The one architectural change, worth knowing early

**Locking a period means storing a derived figure for the first time.**

Today nothing about a contract's standing is stored. Every week's closing
balance is recomputed on each read from one running pass over worked time,
absences, holidays and adjustments (`running_balance` in
`domain/contracts.py`; the ledger assembles N weeks from it in
`domain/ledger.py`). The same principle holds across the codebase on purpose —
billing budgets store only their limit, a report link stores no figure, the
month's report is assembled per request.

"Approval locks the period and freezes that week's balance" breaks that. A
frozen balance is a stored number that the live arithmetic can then disagree
with — which is the point, since an edit after approval must not silently move
an approved figure, but it means the system gains two answers to one question
and every reader has to know which it wants. Decide deliberately:

- what exactly is frozen (the Sunday close? every row of the week? the
  expectation as well as the worked hours?),
- what a later edit to a locked period does (refused, allowed and flagged,
  allowed into an amendment),
- and what the project page shows when the stored close and the recomputed one
  differ.

Getting this wrong is the kind of thing that is very hard to migrate out of
later, because by then there are approved periods in the database.

## Blocked on

Phase 2, and two of AHM-74's open decisions: what "day job" means once an
employer is an entity (`docs/work-contracts.md` decision 1 says today that the
day-job project *is* the contract and an employer is not an entity — this phase
reverses that for employer-owned projects), and what happens when the
employer's terms differ from what the employee had.
