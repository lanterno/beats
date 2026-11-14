# The control plane — the records nobody has decided to keep

**Nothing is blocked on this, and nothing here is scheduled.** The control
plane ([docs/backoffice.md](../docs/backoffice.md)) shipped in full on
2026-11-14 without any of these records, and every screen says what it does
instead (docs/backoffice.md § *What it does not keep*). What is open is a
decision, and it is the owner's: on 2026-11-08 the owner reviewed the redesign
and gave no answer on any of the five below.

**Must not:** build one of these in passing, or let a screen assume one. A
blank "why" column or a box that stores nothing reads as a record that is not
kept; that is the same bug as a control the API cannot serve. Until a row
below is decided, its last column is what the product does.

**History, so it is not repeated:** on 2026-11-14 the commit that moved the
redesign's roadmap to `docs/` (96d95d0d) wrote all five into docs/backoffice.md
as decided "no", with nobody named as having decided. The owner had not; they
came back here the same day.

## The five

Each is a new thing to keep, which means a retention figure in DATA.md, a
line in PRIVACY.md if it is about a person, and an Atlas grant for the
operator's role if it is a new collection.

| Record | What it would take | What the screens do instead |
|---|---|---|
| A required reason and reference on every command | `MongoOperatorAudit.record` has no such field; only `SuspendArgs` has a reason. Add them to the `POST /commands/{name}` body rather than to each command's `args_model`, and let the runner write them. Against it: a reason that has to be typed is typed badly, and the commands whose reason somebody else reads (suspension, the deploy freeze, a pause, a status post) carry theirs already | `Review` asks for the typed confirmation alone and says the record is you, the command, the subject and the two sides; `Audit` shows before and after |
| Incidents and write-ups | A new collection, its commands, and the Atlas grant. The mock's `Incidents` and `IncidentRoom` (docs/backoffice-mock/) are drawn and unscheduled. Against it: a write-up is prose, and could live in the repository's history with the fix | The status page stands without them; Today's first panel is the first thing on the queue |
| Restrictions in force across accounts | The list itself is derivable from `users.suspended_at` and `account_limits`, ids only, and showing it is the cheap half. "Look again on" and a reference are the new part. Check either against docs/backoffice.md § *The pages* (Accounts), which refuses a browsable account list | Each account's page shows its own suspension and limits; nothing lists them across accounts, or records why, or when to look again |
| An audit of each lookup | A write on a read path, which the audit does not do today and which would slow the thing the operator does most. A log of who looked at whom is a record about people, so it needs a retention figure and PRIVACY.md's word | `Accounts` says that opening an account is a read and reads are not recorded; the recent list is ids in `localStorage`, visible to nobody else (`backoffice/client/shared/lib/recent.ts` says it must not grow into that log) |
| Snoozing or finishing a queue item | Stored state per row, so a row can no longer simply leave when its condition clears, and could be ticked off while the thing itself still stands | `Queue` says there is nothing to tick off: a row is the condition, and it leaves when the condition does |

## When one is decided

A "no" goes into docs/backoffice.md § *What it does not keep* as the owner's
decision, dated, and its row here is deleted. A "yes" becomes a *Work*
section in this file, step by step, until it ships; then it moves to `docs/`
(roadmaps/README.md § *When something ships*). When the last row goes, so
does this file, with its row in roadmaps/README.md and its mention in
CLAUDE.md.
