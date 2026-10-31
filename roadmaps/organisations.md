# Organisations — what is left to build

The epic is GitHub issue #353. Four stages of it shipped. What is left is
**sixteen bugs in what shipped, seven items that wait on something outside
the code, and a back office**, and every one of them is written out in full
below.

**This file is meant to be enough on its own.** Whoever picks it up may have
no access to GitHub. So unlike the other roadmaps, which link to issues and
never restate them, this one carries each open issue's whole content: what
is wrong, where, what to do, and what to test. Each item keeps its GitHub
number so the two can be synced by whoever has access. If this file and an
issue disagree, this file was written later (2026-10-31), but say so to the
owner rather than picking one silently.

What is already built — the four rules, decisions 1–33, the data model, the
HTTP contract and the rules the UI keeps — is
[docs/organisations.md](../docs/organisations.md). **Read it first.** Nothing
here repeats it; items below cite its decisions by number.

---

## How to work from this file

1. **Read** [docs/organisations.md](../docs/organisations.md) and the
   repo-root `CLAUDE.md` (commands, conventions, and *What to test, and what
   not to*). For the API, also `api/CLAUDE.md`.
2. **Pick** from [Order of work](#order-of-work). Items marked **Ask the
   owner first** contain a choice that is the owner's to make. Ask in the
   session, then write the answer into `docs/organisations.md` as a decision
   before building.
3. **Branch** from an up-to-date `main`, named `<type>/<n>-<slug>`, for
   example `fix/404-share-day-stamp`. The checkout is shared with other
   sessions: work in a `git worktree` or restore whatever branch you found.
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
   - delete its section here, and its row in *Order of work*;
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
  enforces rule 3 mechanically across every collection. Stage 2 widened it
  for exactly one collection (`projects`) and left the rest alone. A read
  that crosses users gets its own narrow class that does nothing else — as
  `MongoOrganisationRecords` and `MongoReportLinkLookup` do — not a filter
  applied after the fact, and not a field allowlist somebody has to remember.
- **The coach never reaches past the member.** It reads projects through
  the member's own merged repository (`project_repository_for`, in
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
  removing a project ends the assignment; merging and deleting repoint
  rows. The one exception is rows kept under an `erased:` tombstone, which
  go when the organisation is deleted or its retention expires. Keep it
  that way in every fix below.

---

## Order of work

Most important first. Several retention items must land **before the
retention purge is ever run**: today nothing schedules it
(`api/scripts/retention_purge.py` is operator-run and dry by default), so
nothing has been lost yet.

| # | What | Surface | Why at this place |
|---|------|---------|-------------------|
| 407 | Unset retention ignores the country's floor | api | Tiny, and legal. Before any purge |
| 404 | Edits stamp entries from before the share day | api | Breaks rule 4, the core promise |
| 406 | A merge drops former members from the record | api | Loses part of a legal record |
| 405 | Five writes skip the approved-month lock | api | Approved months can move. Part of it: **ask the owner first** |
| 415 | Record and CSVs use the caller's timezone | api | Two deciders get two different legal records |
| 409 | A purge hides long-standing members' balances | api | Before any purge |
| 408 | The purge keeps tombstoned names and contracts | api | Before any purge |
| 410 | Erasure leaves raw ids in two columns | api | Small |
| 411 | Leaving keeps a person in teams | api | Small |
| 412 | The employer's contract write skips two checks | api | Small; touches #405's contract half |
| 413 | A resubmitted sheet keeps the old decision | api | Small |
| 414 | Re-running a deletion duplicates projects | api | Small |
| 419 | The project page offers writes the API refuses | ui | — |
| 420 | The join page understates what crosses | ui | Copy |
| 421 | The companion doesn't mark entered time | companion | — |
| 422 | PRIVACY.md disagrees with the code | docs | After #405 and #408 for two of its points. **The owner reviews it** |
| 424 | A back office for the operator | api, ui | When the owner starts it |
| 340–352 | The seven waiting items | — | Each when its blocker clears; see the section |

---

## Bugs in what shipped

Found on 2026-10-31 by checking `docs/organisations.md` against the code.
Each is a fix to something already decided, not new scope. Line numbers are
approximate (as of `main` on 2026-10-31); the function names are what to
search for.

### #404 — Editing an entry from before a connected project's share day hands it to the organisation

**What's wrong.** Rule 4: connecting a project shares history only from the
day the member chooses. Decision 7: a beat without the stamp, "or before a
connected project's `shared_from`", is not read. But every live write stamps
from the project alone and never compares with `shared_from`:

- `BeatService._stamped` (`api/src/beats/domain/services.py` ~333) sets
  `beat.organisation_id = organisation_of(project)`. `update_beat` (~383)
  calls it on every edit, so changing only the note or end of a pre-share
  entry stamps it. From then on the organisation reads it in `/record`, the
  CSVs and the member's `/visible`.
- `create_beat` (~369) stamps a back-dated entry the same way.
- So does `TimerService.start_timer` (~196, the `Beat(...)` at ~228) with a
  back-dated start, and `ContractService.record_absence` (~1165) for an
  absence dated before the share day.

The backup restore already gets it right (`api/src/beats/api/routers/export.py`
~495–504, decision 18): a beat new to the account takes the stamp only from
`shared_from` on.

**Fix.** `project.organisation.shared_from` (`ProjectOrganisation` in
`domain/models.py`) is on every merged project:

- **Beats:** stamp only when `start >= shared_from`; otherwise leave or clear
  the stamp. An edit that moves a stamped beat to before `shared_from`
  clears it.
- **Absences:** compare by day. `connect_project` (`domain/organisations.py`
  ~798) stamps absences from the chosen *date*, but stores only the instant
  `utc_midnight(share_from, tz)`, in the member's timezone at the time. Two
  options, the first preferred:
  1. Store the chosen day on the assignment at connect time. Old
     assignments default to `shared_from`'s date in the organisation's
     timezone.
  2. Compare against `shared_from` converted to the organisation's timezone.
     Off by a day when the two timezones differ.

Once one pre-share row is stamped, `has_unshared` (decision 16) changes
answer, so the fix also restores the balance rule.

**Test.** A bug that happened: in `api/src/test_organisations.py`, connect a
project with history, edit a pre-share entry's note, and assert it does not
appear in `/record` or `/visible`. Do the same for a back-dated create.

### #406 — Merging two organisation projects drops former and erased members from the record

**What's wrong.** Decision 28: a merge moves rows and never stamps, and the
organisation keeps its record. In `OrganisationService.merge_project`
(`api/src/beats/domain/organisations.py` ~868):

- It folds only **active** source assignments.
  `store.list_assignments(organisation_id, project_id=source_id)` defaults to
  `active_only=True` (`infrastructure/organisations.py` ~415).
- Then it deletes **every** source assignment, ended ones included
  (`delete_assignments`, ~499).
- `repoint_project_rows` (~481) still moves former and erased members'
  stamped rows to the target, which has no assignment for them.
- `_record` (`domain/organisations.py` ~979) builds the record from
  assignments, so those rows vanish from `/record`, both CSVs and that
  person's `/visible`. An employer may be legally bound to keep exactly
  those rows.

**Fix.**

- Fold ended assignments too (`active_only=False`), with the same rules as
  today: the earlier `shared_from`, and the source's contract only where the
  target's assignment has none. The folded assignment is ended only if both
  were (`ended_at` = the later of the two); otherwise it is active.
- Also repoint the member's own references to the source project:
  weekly-plan budgets (`weekly_plans.budgets[].project_id`) and flow windows
  (`flow_windows.active_project_id`). Do it inside the same organisation-
  checked write as `repoint_project_rows`.
- Check the deletion hand-back (`repoint_member_rows`, ~557) for the same
  two references.
- The source's `contract_managed` travels with a folded contract (~913).
  That is fine, since the contract travels whole; say so in decision 28.

**Test.** Merge a source project that has a former member with stamped rows,
and assert they still appear in `/record` for the merged project.

### #407 — An organisation with no retention setting would be purged below its country's floor

**What's wrong.** Decision 30, `DATA.md` and `PRIVACY.md` say a retention
period is never below the country's statutory floor. `_check_fields`
(`domain/organisations.py` ~248) only checks an explicit setting. An unset
`retention_years` reads as `DEFAULT_RETENTION_YEARS = 4`
(`domain/retention.py`, `retention_years()`), whatever the country, and the
purge uses it (`infrastructure/retention.py` ~61). A Polish organisation
(floor 10) that never set a period would be purged after 4 years.

**Fix.** Use one helper for the effective period,
`max(retention_years(stored), retention_floor(holiday_country))`, in
`purge_expired_records` and wherever the period is shown or returned.
Changing `holiday_country` already re-runs `_check_fields`, so an explicit
setting stays valid.

**Test.** In `api/src/test_organisations.py` (or a small pure test beside
`domain/retention.py`): a PL organisation with no setting has an effective
period of 10. Then a purge dry run with `today` 5 years on counts nothing
for it.

### #405 — Five writes skip the approved-month lock

**What's wrong.** Decision 23: once a month is approved, every write dated
inside it answers 409 `PERIOD_APPROVED`. Timesheets don't need a managed
contract (`EmploymentService.submit_timesheet`, `domain/employment.py`
~449), so an approved month can exist on an assignment the member still
writes. Five writes skip the lock:

1. `ContractService.remove_absence` (`domain/services.py` ~1177) checks
   `_refuse_managed` but never `refuse_locked`.
2. `ContractService.remove_adjustment` (~1205): the same.
3. Backup import: `import_full_json` (`api/routers/export.py` ~346; the beat
   loop at ~495–504) writes beats with `beat_repo.restore()` and no lock
   check. A file can insert a stamped beat inside an approved month, or
   overwrite one by id. The import's absences and adjustments do go through
   the checked path.
4. The member's contract write on an unmanaged assignment (`update_project`
   ~549, `replace_contract` ~633, including the adjustment purge
   `_reconcile_adjustments` ~603 triggers). It can move an approved month's
   expectation and balance.
5. The employer's contract write (`EmploymentService.set_contract`, ~204)
   has the same effect.

**Fix.**

- **1–3 need no decision.** Call `refuse_locked(self.locks, project, None,
  day)` before the delete in the two removes, the way `record_absence` and
  `record_adjustment` do. In the import, check each beat new to the account
  (and each overwrite) with `refuse_locked`, and report a refused one under
  `skipped` with `PERIOD_APPROVED`, the way the import already skips an
  `ORGANISATION_PROJECT`.
- **4–5: ask the owner first.** A contract change moves every month's
  expectation at once. The frozen figure itself never moves (it is stored),
  but the live ledger would then disagree with an approved month. The
  candidate rule: refuse a contract write when, for any approved month on
  that assignment, the month's expected hours or the adjustments counted in
  it would differ before and after the write. Compute it with the ledger
  pass the frozen month was taken from. Record the answer in decision 23.

**Test.** For 1–3: approve a month on an unmanaged assignment, then assert
409 on removing an absence and an adjustment dated inside it, and that an
import's beat there is skipped. The lock tests in `test_organisations.py`
show the shape.

### #415 — The record and compliance CSVs bucket days in the caller's timezone, not the organisation's

**What's wrong.** `api/src/beats/domain/employment.py` opens by promising
that months are the organisation's own timezone's: "the lock, the freeze
and the compliance day all bucket by it". The lock and the freeze do
(`MongoPeriodLocks._zone_of` reads the organisation's `timezone`). The reads
don't: `GET /{id}/record` and `/visible` (`api/routers/organisations.py`
~598, ~614) and `/record.csv`, `/visible.csv` and `/compliance.csv`
(`api/routers/employment.py` ~531, ~558, ~583) all take the caller's `tz`
(`TimezoneDep`). As a result:

- deciders in Lisbon and Berlin download different compliance files for
  the same month;
- a late entry lands on a different day, which moves the 10-hour and
  11-hour-rest warnings (decision 26);
- the record a decider reads can disagree with the month they froze.

**Fix.** Bucket these five reads in the organisation's `timezone`. Stop
using `tz` there; leaving the parameter accepted-but-ignored, or removing
it, are both safe for a deployed SPA. Then stop the SPA sending it in its own
commit. `/archive` is the member's own view and may keep the caller's
`tz`. Add a line to decision 26 or 23 saying the record is the
organisation's timezone's.

**Test.** An entry at 23:30 UTC on the last day of a month, for an
organisation in `Europe/Berlin`, falls in the next month in `/record`
whatever `tz` the caller sends.

### #409 — After a retention purge, the organisation stops seeing a long-standing member's balance

**What's wrong.** The purge unstamps a living member's rows older than the
cutoff (`infrastructure/retention.py` ~96–104). Then
`MongoOrganisationRecords.has_unshared` (`infrastructure/organisations.py`
~952) asks whether the member has *any* unstamped row on the project. It
exists to withhold a balance that would carry pre-share history (decision
16), and after the first purge it answers yes for every long-standing
member. So `_balance` (`domain/organisations.py` ~935) returns nothing, and
the organisation loses the balance on its own record permanently.

**Fix.** Tell rows a purge unstamped apart from rows never shared.
Recommended: `has_unshared` ignores unstamped rows dated on or after the
member's `shared_from` and before the organisation's current retention
cutoff (`retention_cutoff(today, effective period)`, see #407). Those were
shared once and have only expired. Every row a purge unstamped is older than
the cutoff it ran with, which is never later than today's. Rows before
`shared_from` still count, as decision 16 intends. Write the amendment into
decision 16.

**Test.** Purge (with `apply`) an organisation whose member has rows older
than the period, then assert `/record` still shows that member's balance.

### #408 — The retention purge keeps a deleted account's name, email and contract forever

**What's wrong.** Decision 30 says the period covers "the contract and
adjustments behind a balance it read, and tombstoned ex-member rows".
`PRIVACY.md` says the purge "removes what it kept of a deleted account".
`purge_expired_records` (`infrastructure/retention.py` ~49) touches only
beats, absences, adjustments, timesheets and the audit log. These kept
under a tombstone at erasure (`infrastructure/erasure.py` ~131–157) are
never removed:

- the tombstoned assignment, with its `contract`;
- the tombstoned membership's `name` and `email`, which are the most
  personal data left.

Separately, a living member's decided `org_absence_requests` never expire.
Decision 30 doesn't list them, so give them a rule too.

**Fix (recommended rules — confirm with the owner if in doubt).**

- In the purge, after the tombstoned rows go, delete a tombstoned membership
  and its assignments once no tombstoned beat, absence, adjustment or
  timesheet of that tombstone is left in the organisation.
- Delete decided absence requests dated before the cutoff.
- Count each in the report and the `retention.purged` audit event. Keep the
  report shape: counts, `cutoff` and `years`, no data.

**Test.** Erase a member, run the purge past their last row, and assert
their membership and assignment are gone. Erase another with a row still
inside the period, and assert theirs stay.

### #410 — Erasure leaves the person's raw id in `entered_by` and timesheet history

**What's wrong.** The erasure module's docstring
(`infrastructure/erasure.py`) promises that every column in the organisation
naming the person gets the tombstone. It does this for `created_by`,
`assigned_by`, `decided_by` and the audit actor, and misses two:

- **`entered_by` on beats.** A decider who logged time for others (decision
  24) leaves their raw id on those members' beats.
- **`org_timesheets.history[].by`.** The per-organisation loop re-points the
  sheet's `user_id` and `decided_by` (~117–125), but not the history
  entries.

**Fix.** In `erase_account`'s per-organisation loop:

- Set `entered_by` to that organisation's tombstone on beats with
  `{"organisation_id": org_id, "entered_by": user_id}`.
- Set `history.$[e].by` with `array_filters=[{"e.by": user_id}]` on that
  organisation's sheets.
- A beat the member has since moved to a personal project has no stamp, so
  no tombstone fits it. After the loop, set `entered_by` to the literal
  `"erased"` on any beat still carrying the raw id.

**Test.** Extend the erasure test in `test_organisations.py`: a decider
enters time and decides a sheet, then is erased. No document keeps their
raw id.

### #411 — Leaving or being removed keeps a person in the organisation's teams

**What's wrong.** `MongoOrganisationStore.remove_from_teams`
(`infrastructure/organisations.py` ~661, on the port in `domain/ports.py`)
says it runs "when they leave, are removed, or are erased". Nothing calls
it. Erasure pulls the id itself. `_end_membership`
(`domain/organisations.py` ~444) ends the membership and assignments and
leaves the teams alone. So a person who rejoins is silently back in their
old team, and a former manager re-invited as a manager gets their old scope
back without anyone assigning it.

**Fix.** Call `self.store.remove_from_teams(organisation_id, user_id)` in
`_end_membership`, after `end_assignments`. After this, a manager's narrowed
record no longer lists that former member; owners, admins and viewers
still do (decision 25).

**Test.** Leave, rejoin, and assert the team no longer lists the person.

### #412 — The employer's contract write skips the day-job check and the adjustment reconcile

**What's wrong.** Decision 21 says one set of rules validates a contract,
whoever writes it. `EmploymentService.set_contract` (`domain/employment.py`
~204) skips two checks the member's route makes:

- **The day-job check.** `check_contract_rules_for` (~686) validates through
  a shell `Project(kind=DAY_JOB)`, so the employer can put a contract on a
  `freelance` or `side_project` organisation project. The member's route
  refuses that with 409 `NOT_A_DAY_JOB`.
- **`_reconcile_adjustments`** (`domain/services.py` ~603). The member's
  write purges or refuses balance adjustments the new terms leave outside
  the contract. The employer's does neither, so it can move a start date
  past an adjustment.

**Fix.** Load the organisation's project (`store.get_project`), and refuse
`NotADayJob` unless `kind` is `day_job`. Run the same adjustment reconcile
against the member's adjustments, through the member-scoped repository the
employer's adjustment write already uses (`enter_adjustment`). This
overlaps #405's contract half; do it after that decision if both are open.

**Test.** The employer's `PUT …/contract` on a freelance organisation
project answers 409 `NOT_A_DAY_JOB`.

### #413 — A resubmitted timesheet keeps the previous decision's decider, time and comment

**What's wrong.** Resubmitting a sheet that was sent back writes
`decided_at=None`, `decided_by=None` and `comment=None`
(`submit_timesheet`, `domain/employment.py` ~449). But `upsert_timesheet`
(`infrastructure/organisations.py` ~750) writes through `_dump`, which is
`model_dump(exclude_none=True)` (~66), so the Nones never reach `$set`. The
sheet reads as submitted while still carrying the "changes requested"
comment. The `history` is right.

**Fix.** `$unset` `decided_at`, `decided_by` and `comment` in
`upsert_timesheet` when they are None. In the same pass,
`withdraw_absence` (`domain/employment.py` ~442) writes no audit event,
unlike every other request step. Add one (`absence.withdrawn`).

**Test.** Request changes, resubmit, and assert the listed sheet has no
`comment` or `decided_by`.

### #414 — Re-running an organisation's deletion after a crash gives contract holders a second copy

**What's wrong.** Decision 29: the hand-backs run before the wipe, "so a
crash midway strands nothing of a member's". Nothing is stranded, but a
re-run of `DELETE /{id}` duplicates. Rows already handed back now belong to
the new personal copies, so `row_owner_ids` no longer finds them.
`delete_organisation` (`domain/organisations.py` ~342, the holders at
~368–379) also adds every holder of a contract on a still-existing
assignment. So each contract holder gets a second copy holding the contract
and no rows.

**Fix.** Make the hand-back idempotent. The simplest version ends or
deletes the assignment in the same step as `hand_back_project`, so a re-run
does not see it again. Alternatively, look for an existing copy before
making one.

**Test.** Run the deletion's hand-back loop twice (call the service twice,
the second time after the hand-backs but before the wipe, or fake the
crash), and assert one personal copy per holder.

### #419 — The member's project page offers contract edits and Restore that the API refuses

**What's wrong.** On an organisation's project, the member's own page offers
controls the API then refuses:

- **Managed contract.** While the organisation manages the contract
  (decision 21), the member's writes answer 409 `CONTRACT_MANAGED`.
  `ContractRegister.tsx` (`ui/client/pages/project-details/`) swaps only
  "Change contract from…" for "Managed by Acme" (~542). These stay live: the
  per-term **Edit** and **Remove** (~507, ~516), **Holidays** (~588), and
  **Edit the region, the opening balance and the end** (~598). The settings
  form (`ui/client/entities/project/ui/ProjectForm.tsx` ~378) still says
  "Your goal, local repo paths and contract are yours" and leaves the
  contract frame editable.
- **Restore.** `/unarchive` answers 409 `ORGANISATION_PROJECT` on an
  organisation's project; the organisation archives its own. The header's
  inline Restore (`ProjectHeader.tsx` ~220–236) and the archived list's
  Restore (`ui/client/pages/projects-index/ProjectsIndex.tsx`,
  `handleRestore` ~149) show regardless.

**Fix.** Read `project.organisation?.contractManaged` (and
`project.organisation` for Restore). Hide those controls, and say whose they
are, the way the settings drawer already does for the organisation's fields
("Managed by Acme", "Archived by Acme").

**Test.** A component test beside the existing ones (for example
`OrganisationPanel.test.tsx`): a managed project renders no term Edit or
Remove, and an archived organisation project renders no Restore.

### #420 — The join page understates what the organisation sees

**What's wrong.** The invite page (`ui/client/pages/organisations/JoinPage.tsx`
~119–121) says the organisation sees "…your absences as a date and a type,
and a managed contract's balance". Rule 3 says any contract on its
projects, its terms (decision 32) and its balance, and an absence's half
day. The organisation page's "What Acme can see" sentences say "Where you
have a contract on one, it sees the balance" (`Organisation.tsx` ~374), which
leaves out the terms.

**Fix.** Copy only. On the join page: "…your absences as a date, a type and
whether it was a half day, and a contract you hold on one, its terms and its
balance." On the organisation page: "Where you have a contract on one, it
sees its terms and its balance." This is the sentence a person reads before
agreeing to join, so it must never understate what crosses.

**Test.** None needed for copy.

### #421 — The companion doesn't mark a session a decider entered for the member

**What's wrong.** Decision 24: a session a decider logs lands on the
member's timeline marked "entered for you", and the mark is the
notification. The web app marks it (`ui/client/pages/index/TodayFeed.tsx`
~185, `ui/client/pages/project-details/WeekDays.tsx` ~518). The companion
shows the session but no mark: nothing in `companion/lib` reads
`entered_by`, and the Today strip builds sessions from raw maps
(`companion/lib/screens/today_screen.dart` ~672). The beat model is in
`companion/lib/services/api_client.dart` (~21).

**Fix.** Read `entered_by` and mark the session with the web's wording.

**Test.** If the label is a pure helper, a parity test in `companion/test/`
beside the other label tests.

### #422 — PRIVACY.md disagrees with the code on organisations and single sign-on

`PRIVACY.md` is the owner's promise to users. **Draft the change, and have
the owner review it before it ships.** Two points depend on #405 and #408
landing first.

Where the code does more than PRIVACY.md says:

- **Single sign-on, what is stored** (PRIVACY.md ~line 28). It says only the
  issuer and subject are kept. `LinkedIdentity` (`domain/models.py` ~24) also
  keeps the provider's `name` and `email` claims, refreshed on every
  sign-in, and `linked_at`. `DATA.md` § Account and auth omits the user's
  `identities[]` altogether.
- **Single sign-on, which door** (same line). "Nothing downstream records
  which door was used" holds for sessions, but `api/routers/sso.py` ~260
  logs `SSO sign-in: provider=%s user=%s` at INFO into Cloud Logging. **Ask
  the owner:** drop the provider from that line (recommended; #342's design
  rests on this promise), or disclose it.
- **The contract** (~line 21). It says the organisation sees "its running
  balance. It sees nothing else". Decision 32 says it also sees the
  contract's terms; say so, and say that sharing gives it no power to delete
  your entries.
- **"Its days locked"** (~line 21). True only once #405 lands.

Where PRIVACY.md lags the code:

- **Timesheets and entered time** (~line 21) are described as parts of a
  managed contract. Submitting, approving, locking and entering time work on
  any assignment, and owners and managers can enter time, not only admins.
- **Closing and deleting an organisation** (decision 29) aren't mentioned:
  the notice period, the personal copies members get, the unstamping, and
  the deletion of its record, tombstoned rows included.
- **Retention** (~line 93) says the purge "removes what it kept of a deleted
  account". True only once #408 lands. Check the floor wording against #407
  too.

---

## Waiting on something outside the code

None of these should be started until its blocker clears. Each section says
what blocks it, when to start, and what it must not do.

| # | What | Blocked by | Start when |
|---|------|-----------|------------|
| 340 | Money as a permission of its own | Nothing external — there is no organisation money to guard yet | Organisation-side money is designed |
| 341 | Verified email domains for joining | The API sends no email | Email infrastructure exists |
| 342 | SSO per organisation, optionally required | Nothing — the shape is decided | A customer requires it |
| 343 | SCIM provisioning | #342 | SSO per organisation ships |
| 345 | Per-seat billing | No payment machinery anywhere in the codebase | The end of the beta is decided; then as its own project |
| 351 | A digest or push for what is missing or waiting | No channel: no email, no server push (#298) | Either channel exists |
| 352 | DPA, works-council sheet, DPIA template | Counsel review | A customer asks, or counsel is engaged |
| 424 | A back office for the operator | Nothing — not started | The owner starts it |

### #340 — Money as a permission

There is no organisation-side money at all: billing stayed personal, and an
organisation's project is billed by nobody (`ORGANISATION_PROJECT`, raised in
`domain/billing_service.py`). So there is nothing for a permission to guard,
and this is blocked on a design that does not exist yet, not on a
dependency. When it arrives, the epic's rule is that **seeing money is its
own permission**, independent of role.

When it comes, **it must not be bolted on.** Every other item here is
additive; this one is a cross-cutting read rule, and the cheapest version —
a flag checked in each billing route — is the version that leaks the first
time someone adds a route and forgets. The seam already exists: clients,
project billing, billable overrides and billing budgets are their own
collections, outside every device prefix, with no coach port. Attach to that
boundary rather than carving a new one.

### #341 — Verified email domains

People with an `@acme.com` address ask to join, or join automatically.

Blocked on email infrastructure the API deliberately does not have. Without
verification a domain rule hands memberships to whoever registers an address
— the exact hole decision 11 closed for invitations. Email first, then this;
building it the other way round reopens the hole on purpose.

### #342 — SSO per organisation

**The shape was decided 2026-10-28.** It is built when a customer requires
it, not before — but it is designed, so this is a build task, not a
decision. SSO is included in the paid seat price, not an add-on
([docs/pricing.md](../docs/pricing.md)).

Not by stamping the door on the session: sessions stay door-blind, which
keeps the promise that nothing downstream knows which door was used (see the
log line in #422). Instead, a **per-organisation attestation**, the way
GitHub gates an organisation behind SAML:

- An organisation that requires SSO configures its own OpenID Connect
  provider. This is a scoping layer over `api/src/beats/auth/oidc.py`, which
  is built and tested already — discovery, code exchange with PKCE and a
  nonce, every ID-token check — plus `auth/sso_accounts.py` (identities
  keyed on issuer + subject, `allow_signup`) and `src/fake_idp.py`, a
  scripted provider with real RS256 keys to test against. Provider
  configuration is deployment-wide today (`OIDC_PROVIDERS` in
  `settings.py`), and `OrgMembership` has no attestation fields. **It is not
  a new protocol.**
- Entering that organisation's slice needs a fresh verification with *that*
  provider, stored on the membership: verified at T, expiring at T+N. It
  shows on the "What Acme can see" page and is audited.
- The person's passkey still opens their personal account and every other
  organisation — rule 1.
- Enforce it as a dependency on the organisation router, in one place, like
  the role checks. Never a flag per route; that is #340's lesson borrowed
  early.
- **Change PRIVACY.md first, and narrowly**: an organisation that requires
  SSO sees when you last verified with its provider. That is not "we record
  how you log in", and the wording matters.

Open at build time: whether a lapsed attestation blocks the organisation's
routes alone, or also starting new timers on its projects. Existing data is
never blocked. Ask the owner.

### #343 — SCIM provisioning

Provision and deprovision members from an identity provider. Its own protocol
surface and credential story, keyed on the same per-organisation provider as
#342, so it comes after it. It belongs to a later, sales-led enterprise tier,
not the seat price ([docs/pricing.md](../docs/pricing.md)).

### #345 — Per-seat billing

**The price is decided** ([docs/pricing.md](../docs/pricing.md), 2026-10-28):

- €8 a seat a month billed annually, €10 billed monthly; free up to five
  seats; SSO included.
- A seat is an active member with an assignment: viewers are free,
  contractors count when assigned, and nobody counts before they join.
- One subscription per organisation.
- Everything is free during the beta, shown as a 100 % discount; the
  marketing page already shows the price struck through
  (`ui/client/pages/homepage/HomePage.tsx`).
- After the beta, an organisation that does not pay goes read-only, never
  deleted.

What remains is collecting it, and that is the first time money flows *to
us*. Nothing in the codebase handles payment: a provider, tax, invoices and
dunning are a dependency well outside the shape of this epic. Treat it as
its own project, started when the end of the beta is decided.

### #351 — A digest or push for what is missing or waiting

Today this shows where people already look: a member's timesheet list offers
the ended months still to submit and marks the ones sent back, and a decider's
Approvals tab counts and groups what waits (decision 27). A digest or a push
needs a channel first: email infrastructure, or server push (#298, "Server
push: APNs / FCM notifications", outside this epic; today the companion's
notifications are local only).

### #352 — Sales and legal material

Three drafts in [legal/](legal/), unreviewed by counsel:

- `dpa.md`, the processing agreement;
- `works-council-sheet.md`, the one-page "what LifePete records" sheet;
- `dpia-template.md`, the DPIA template.

[legal/README.md](legal/README.md) says whose document each is, the two
facts to re-check before relying on them (Spain's fine amounts, Germany's
reform status, both last checked October 2026), and that **counsel review
is the whole blocker**. Nothing there reaches a customer first. When counsel
signs them off, they move to `docs/`.

Re-read them against `docs/organisations.md` whenever a decision changes
what an organisation sees (they were last aligned for decision 32). The
works-council sheet's whole point is that every sentence can be checked.

### #424 — A back office for the operator

Decision 31: an organisation whose last owner's account is erased stays as
it is, run by its admins, and noticing it is the operator's job. That needs
somewhere to notice it. The first thing a back office shows is
**organisations with no owner**. Until it exists, the only trace is the
`account.erased` event in that organisation's audit log.

A cheap interim, if the owner wants one first: `api/scripts/erase_account.py`
prints which organisations the erasure leaves without an owner (the operator
is the one running it). What a back office is — pages behind an operator
role, a CLI, or both — and what else belongs in it are the owner's call.
Keep it out of `/api/organisations` and away from every device prefix.

---

## Related, outside the epic

- **A note input in the companion** (#316, "Writing Tools on the post-stop
  note", macOS). The companion has no note input. If one comes back, it
  ships with the marker the web's input carries ("Acme can read this note"
  on an organisation's project, following the project picked), because the
  organisation reads an entry's note (decision 1).
- **Server push** (#298): the channel #351 waits on.

---

## Settled — do not reopen

A fresh reader tends to re-ask these. Each is decided in
`docs/organisations.md`; reopening one is a new decision for the owner, not
a fix.

- No live presence, ever: the record carries no `running` flag (decision 2).
- The API sends no email, and the invitations list carries no token
  (decision 11).
- An approved month refuses edits until a recorded reopen (decision 23).
- A merge never changes a stamp (decision 28). Closing is notice, and
  deletion hands back before it wipes (decision 29). Retention has a
  statutory floor, and expiry unstamps rather than deletes a living
  member's rows (decision 30).
- An organisation left without an owner stays as it is (decision 31).
- A decider reads the contract's terms on any assignment, and sharing is not
  control (decision 32).
- A decider may approve their own timesheet and absence request, for now
  (decision 33).
- The price (`docs/pricing.md`), and the SSO shape (#342 above).

---

## Out of scope, by decision

Not oversights. If one of these is asked for, it is a new decision, not a
continuation of this epic.

- **Separate work-only accounts an employer controls.** Large customers will
  ask. It is a layer on top, later — never the default, which would undo
  rule 1.
- **Several workspaces inside one organisation**, for agencies.
- **Payroll integrations**, and invoicing beyond what clients need.
- **Screenshots, activity levels, app tracking for employers, idle detection
  reported to employers. Not later, not ever.** This is the line the whole
  product is built to sit on the right side of: a tracker that already knows
  your flow, sleep and heart rate becomes a surveillance tool the moment an
  employer can see any of it. What makes these records sellable to a works
  council is that they *cannot* be used to watch anyone.

---

## Why the stages went in the order they did

Kept because it explains the shape of what is built, and because the same
logic orders what is left.

Stage 2 (foundations) was the only stage that changed the data model. Stages
3 (employment) and 4 (scale) are additive on top of it — which is what made
the sequencing simple: get the ownership model right, and the rest is
ordinary work. The remaining items are additive too, with one exception,
#340, which is why it carries the warning it does.

Two things were deliberately done early because they are cheap to add before
and expensive to add after:

- **The audit log** was written from stage 2 on and only read from stage 4.
  Every membership change, contract edit and approval made before it exists
  is unrecorded, and those are exactly the events a works council asks about.
- **The index on `projects`** (`{user_id: 1, archived: 1}`) went in before
  any organisation code. Every project read had been a collection scan —
  harmless at one person's scale, wrong as soon as the read became "mine,
  plus every organisation project I am assigned to" across every tenant.

The one thing stage 3 broke on purpose: **approval stores a derived figure.**
No other working-time or billing figure is stored — every week's closing
balance is recomputed on each read, billing budgets store only their limit, a
report link stores no figure. (The weekly digests keep their own totals,
outside both.) A frozen month is the exception, because an edit after approval
must not silently move an approved figure. It leaves the system with two
answers to one question, and every reader has to know which it wants. That was
decided deliberately rather than discovered, because it is very hard to
migrate out of once approved periods exist.

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
