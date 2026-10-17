# Work Contracts

> Beats records what you worked on. This makes it able to say what you
> *owed* — so that on a Thursday afternoon you know whether Friday ends
> at three or at seven, and whether you are ahead of the company or
> behind it.

A project has a **kind** (`day_job`, `freelance`, `side_project`), and
a day-job project carries its **contract**: how much of a week it is
owed, where it is (for the public holidays), and how those terms have
changed over time. From the contract, the holidays, and the user's
absences, Beats derives the hours expected each week and a running
**balance** — overtime if positive, hours owed if negative — which dated
**balance adjustments** pay out, reset or cap.

The decisions below were made in conversation and are recorded so that
later work does not re-litigate them. The rest says what was built on
them and why. How the project page shows it is in
[project-page.md](project-page.md).

*History.* The work shipped in five phases, and code comments cite them:
1 the domain model and arithmetic, 2 the migration, 3 the routes, 4 the
form and absences, 5 the week and the pass that clears the personal
goal. Git history has the plans.

---

## Decisions

1. **The day-job project is the contract.** No separate entity. A user
   with two employers has two day-job projects, each with its own
   balance. "Project" keeps its name everywhere.
2. **Percentage needs a basis.** A time-based term stores
   `full_time_hours` (40, 42, 35 …) and `percentage`; weekly hours are
   the product. A `custom` term stores `weekly_hours` directly.
3. **No working pattern.** A week owes `weekly_hours`; a day off owes
   `weekly_hours / 5` less. We never ask which weekdays are worked.
4. **Holidays come from the `holidays` package** — country + subdivision
   code, with the library's own substitute-day rules. We store two codes
   and derive everything.
5. **Absences are one flat list**, all reducing the expectation the same
   way. Only `vacation` is counted against anything: the entitlement of
   Decision 14. Sick and other days have no allowance.
6. **Time off in lieu is not a feature.** A comp day is a weekday with
   no absence recorded and no work done: expectation stands, worked is
   zero, the balance goes down by itself.
7. **Worked time is whatever the timer says** on that project. No
   breaks, no rounding, no manual day entries.
8. **Objective-based day jobs** have no expectation and no balance —
   but the user may still set a *personal* weekly goal on them, which
   is the existing `weekly_goal` field doing what it always did. The
   same holds day by day on a contract that changes: hours worked under
   an objective term, or a term of 0 hours, count toward no balance, so
   a time-based term after one starts from the balance the last left
   and not from overtime the stretch never owed.
9. **Contract changes are first-class.** Part-time → 80% → full-time is
   the normal life of a contract, and every calculation is term-aware
   down to the day.
10. **Migration keeps the numbers users already had**, including the
    history of how a goal changed over time.
11. **Timesheets and export are a follow-up.** The product goal of this
    iteration is the *week*: expected, worked, remaining, balance.
    The monthly timesheet followed (AHM-30): see "The timesheet" below.
12. **Employer holidays are dated full days on the contract.** Where an
    employer's days off differ from its region's, the contract says so in
    two lists: `company_holidays` adds days (Christmas Eve, a bridge day),
    each with a name, and `holidays_not_given` takes region holidays away
    as bare dates. No recurrence — a policy changes from year to year, and
    a rule would apply to years nobody checked — and no half days: a half
    day is a half-day absence of type `other`, which already costs
    `base / 2`. Each list is valid on its own. A removal that matches no
    region holiday, or is kept while there is no region, does nothing and
    is kept; a company day on a removed date wins, under its own name.
    The calendar's `include=not_given` still lists that region day, as
    not given, beside the company day: an editor that could see only one
    of the two marks could not clear the other. Because the removals are
    bare dates, a region change can bring one into force: a date that
    matched no holiday of the old region and matches one of the new
    becomes a working day there. The API keeps both lists through a
    region change, as it keeps them through any other write; the settings
    form names each such date before saving, and clears it only when
    asked (see "The UI's rules"). The inverse — a removal that matched a
    holiday of the old region and matches none of the new — does nothing
    and is not mentioned at the change: it is left for the Holidays
    dialog's "No longer a holiday here", where it can be removed, and the
    same warning names it again should a later region bring it back.
    What stands in for a rule is a copy: the Holidays dialog copies the
    year before's company days into the year it shows, each on the same
    month and day, as rows the user checks and saves. It leaves out a
    date that already has a company day or is a public holiday the
    employer gives as the dialog's ticks stand, saved or not, and says so
    (a public holiday the year's calendar has not brought in yet is
    copied, and its row then says it changes nothing); a day that lands
    on a weekend is copied and its row says it changes nothing, since a
    weekend owes nothing. 29 February into a year without one is left
    out with a note, not moved to the 28th or 1 March: a leap-day policy
    does not say which neighbour the employer would give, so the user
    adds it by hand.
13. **Balance adjustments replace editing the opening balance.** A payout,
    a year-end reset or a cap is a dated record of its own, so the opening
    balance stays what was banked before Beats and the ledger shows when
    the balance was settled. Three one-off kinds: a signed `delta`, a
    `reset` to a value, a `cap` at a ceiling. No repeating rules ("cap at
    100 h every 31 December"): like company holidays, a policy changes, and
    a rule would apply to years nobody checked. A reset or a cap stores its
    target, not the hours it moved, so a session recorded later from before
    it does not undo it. One per day, and a post on a taken day replaces
    it, as an absence does: editing on the same day is then one atomic
    write. They belong to the contract's balance and go with the contract
    (a kind change, `contract: null`); absences stay, being facts about
    days.
14. **Vacation is counted in days for a five-day week, from a dated
    opening.** A contract may carry a `vacation` entitlement: days per
    year, what happens to unused days, and an opening — the days left on a
    date the owner picks, off the contract or an HR statement.
    - *The unit* is Decision 3's day: a week off is five absences whatever
      the percentage, and a part-time day is already a shorter day. So the
      entitlement is not scaled by the percentage — that would count the
      cut twice (80% of 25 is 20 days, four weeks) — and a 4-day week with
      20 days is entered as 25. The percentage shows in hours, not days.
      If `hours_per_day` becomes configurable for a 4-day week (AHM-36),
      this unit follows it.
    - *Counting starts at the opening*, which is required with the
      entitlement. Nothing before it is reconstructed: every contract the
      migration made starts at the project's first beat, possibly years
      back, and a pro-rated first year from `starts_on` would credit years
      of leave nobody recorded. Years before the opening's are out of
      range; days off before the opening cost nothing.
    - *The leave year is the calendar year.* The opening year is the
      opening figure as typed, even when the job ends in it. Every later
      year gives the full entitlement, pro-rated by calendar days only in
      the year of `ended_on`, rounded half up to the half day, so every
      figure is a whole or half day.
    - *Carry-over* is `all`, `capped` (up to `carry_over_max_days`) or
      `none` (unused days lapse on 31 December). A deficit carries whole
      whatever the rule: the rule limits what is kept, not what is owed. No
      expiry date ("use by 31 March") this iteration.
    - *A day costs leave* when it is a `vacation` absence — 1, or ½ for a
      half day — on a weekday inside the contract's dates, on or after the
      opening, that is not a holiday of the contract, whatever the term. An
      objective or 0-hour term owes no hours, but a day off under it is
      still leave: the entitlement belongs to the employment, not the
      schedule. Unpaid stretches still accrue and still cost.
    - *One figure for the contract's whole life*, on the contract, not per
      term: a per-term field would be dropped by every term edit from an
      SPA that predates it. So changing the days per year or the rule
      re-derives every year since the opening, and moving the opening
      re-anchors the chain.

---

## Data model

```python
class ProjectKind(StrEnum):
    DAY_JOB = "day_job"
    FREELANCE = "freelance"
    SIDE_PROJECT = "side_project"

class ScheduleType(StrEnum):
    FULL_TIME = "full_time"   # percentage fixed at 1.0
    PART_TIME = "part_time"   # percentage < 1.0
    CUSTOM = "custom"         # weekly_hours given directly
    OBJECTIVE = "objective"   # no expectation, no balance

class ContractTerm(BaseModel):
    effective_from: date              # any weekday, not only Mondays
    schedule_type: ScheduleType
    full_time_hours: float | None     # time-based only, > 0
    percentage: float | None          # time-based only, 0 < p <= 1
    weekly_hours: float | None        # custom only, >= 0
    note: str | None
    # hours_per_week: None for objective; hours_per_day = hours_per_week / 5

class Contract(BaseModel):
    terms: list[ContractTerm]         # strictly ascending, non-empty
    holiday_country: str | None       # ISO 3166-1 alpha-2, e.g. "CH"
    holiday_subdivision: str | None   # ISO 3166-2 part, e.g. "ZH"
    opening_balance_hours: float = 0  # hours banked before Beats
    ended_on: date | None             # freezes the balance
    company_holidays: list[CompanyHoliday] = []  # the employer's own days off
    holidays_not_given: list[date] = []          # region holidays it does not give
    vacation: VacationEntitlement | None = None  # Decision 14; None tracks nothing

class CompanyHoliday(BaseModel):
    date: date
    name: str                         # stripped, 1-80 characters

class CarryOver(StrEnum):
    ALL = "all"                       # every unused day carries
    CAPPED = "capped"                 # up to carry_over_max_days
    NONE = "none"                     # unused days lapse on 31 December

class VacationEntitlement(BaseModel):
    days_per_year: float              # > 0, <= 366, whole or half
    carry_over: CarryOver
    carry_over_max_days: float | None # required with capped, and only there; > 0
    opening_on: date                  # counting starts here, inside the contract
    opening_days: float               # left that morning for the year; may be < 0

class Project(BaseModel):
    ...
    kind: ProjectKind = ProjectKind.SIDE_PROJECT
    contract: Contract | None = None  # only on a day job

class Absence(BaseModel):            # own collection
    id: str | None
    project_id: str
    date: date
    half_day: bool = False
    type: AbsenceType                 # vacation | sick | other
    note: str | None

class AdjustmentKind(StrEnum):
    DELTA = "delta"                   # by hours, signed: a payout is negative
    RESET = "reset"                   # to hours
    CAP = "cap"                       # down to hours if above; hours >= 0

class BalanceAdjustment(BaseModel):  # own collection, balance_adjustments
    id: str | None
    project_id: str
    date: date
    kind: AdjustmentKind
    hours: float                      # finite, |hours| <= 10 000; a delta is not 0
    note: str | None
```

The validators: terms non-empty, ascending, no two on one day; `ended_on`
not before the first term; `full_time` fills in `percentage = 1` and
refuses anything else; `part_time` needs a percentage below 1; `custom`
needs `weekly_hours` and takes no basis; `objective` takes none of the
numbers; `holiday_subdivision` needs a `holiday_country`.

The two holiday lists have one rule each, and it is their own: no date
twice. Neither is checked against the region, the calendar, the
contract's dates or the other list, and none may ever be. A contract
write that leaves a list out keeps the stored one (see "Omitted is not
null" below), merged with `model_copy`, which does not re-validate; that
is safe only while every rule on these lists is per-list, since the
stored list already passed them. A rule tying a list to another field
would let the merge produce a contract that fails the next read — and
with it the user's whole project list — so it would need the merge to
re-validate and answer a 422. Both lists are additive on the stored
document, so no startup pass runs for them.

The vacation entitlement's rules are field constraints — every figure a
whole or half day, finite and bounded — so a 422 names the leaf
(`contract.vacation.days_per_year`). The cap is checked against the rule
by a validator on the cap itself, for the same reason, and is defaulted
to null rather than required: the store writes with `exclude_none`, so an
entitlement that carries everything is stored without it. The entitlement
is kept when a write leaves it out, like the lists, so its one tie to the
rest of the contract — `opening_on` inside the contract's dates — is not a
model rule but a write-time check after the merge (below). It is additive
on the stored document: no startup pass, and no entitlement is guessed for
a migrated day job.

That the region codes are ones the library knows is checked by
`ProjectService` when a contract is written, not by the model. The model
is re-validated on every read, and a code a library upgrade stops
knowing must make one contract un-editable, not the user's whole project
list unreadable.

Absences are unique on `(user_id, project_id, date)`: a second absence
on a day replaces the first. The expectation treats the three types
alike; the vacation count reads only `vacation`.

Balance adjustments are unique on `(user_id, project_id, date)` the same
way, and the repository's upsert is a replace on that key, so the id
survives and a reset posted over a noted payout does not keep the note.
The body is `BalanceAdjustmentFields`, whose validators are the 422 at
`hours`: a delta of 0 moves nothing, a cap is not negative, and the bound
keeps a sum of many records finite. The collection is new and additive,
so no startup pass runs for it; `ensure_indexes` builds its index.

`weekly_goal` / `goal_type` / `goal_overrides` are the *personal* goal
and keep applying to side projects, freelance work, and objective-based
day jobs. On a time-based day job the contract is the goal.

---

## The arithmetic

Everything reduces to one function over a date range
(`domain/contracts.py`, pure: holidays arrive as a `set[date]` and
`today` is a parameter; `domain/holidays.py` is the only importer of
the library). The set's one source is `contract_holidays` in
`domain/holidays.py`: the region's holidays, less the ones the employer
does not give, plus the company's. The week, the ledger, the balance,
the index and the Inbox and pacing readers all take it from there.

```
expected(d) for a weekday d:
    term  = the term with the latest effective_from <= d     (none → 0)
    base  = term.hours_per_day                                (objective → 0)
    if d < first term's effective_from or d > ended_on:      0
    if d is a holiday of the contract:                        0
        (the region's, less the ones not given, plus the company's)
    if an absence exists on d:                                0, or base/2 if half_day
    else                                                      base

expected(d) for Saturday / Sunday:                            0

expected(range) = Σ expected(d)
worked(range)   = Σ beat duration on this project, by local day
```

- **Mid-week contract change** is automatic: Monday–Tuesday take the
  old term's `hours_per_day`, Wednesday onward the new one.
- **Contract starting or ending mid-week** is the same rule.
- **A holiday on a weekend** costs nothing, because weekends are already
  zero. The library's substitute days (UK, US) *are* weekdays and cost
  their day.
- **Half day** costs `base / 2`.

```
balance(today) = opening_balance_hours
               + counted(start .. min(today, ended_on))
               - expected(start .. yesterday)
               + adjusted(start .. today)

counted(d) = worked(d) if the term in force on d owes hours, else 0

adjusted(d), at the start of d, against b = the close of d − 1:
    delta → hours
    reset → hours − b              (the balance becomes hours)
    cap   → min(0, hours − b)      (no higher than hours)
```

Today's expectation is charged tomorrow, so the balance does not read
−6 h every morning; today's work counts at once. `start` is the first
term's `effective_from`. `ended_on` freezes work and expectation: nothing
is expected after it, and time tracked after it is not overtime either.

**A term that owes nothing counts no work.** An objective term, or one
of 0 hours, expects nothing of its days, so the hours worked under it
are not overtime: they are in the week's `worked`, and in no balance,
`balance_worked`, close, `balance_moved` or `remaining`. A time-based
term that follows starts from the close the last one left. Under the
personal goal those hours never carried forward either, which is what
Decision 10 asks of the 0-hour terms the migration wrote. Leave is
counted apart: a day off under such a term still costs vacation
(Decision 14). `counts_worked` in `contracts.py` decides it for every
reader of the running pass.

**Adjustments apply at the start of their day**, against the previous
day's close, before the day's work. They count from `start` on, whatever
`ended_on` says, so a final payout after the end settles the frozen
balance; one dated before `start` falls outside the sum and is ignored.
A reset or a cap stores its target, and what it moves (`applied`) is
worked out on each read, so recording earlier history later changes
what it applied and not the balance after it.

**A reset makes the balance depend on the timezone.** Worked time is
bucketed by the local day each beat started on, in the request's `tz`,
so a beat late on the eve of a reset is absorbed by it in one zone and
counted after it in another. The index, the SPA and the companion each
send their own `tz`; the figures can differ by that beat, by design.

**One pass.** `running_balance` walks the contract's days once, from
`start` through the latest of today, the last close asked for and the
last adjustment, and returns today's terms, every close asked for and
every adjustment's `applied` together, so no two can disagree and a
ledger of a hundred weeks costs what one does. A day's **close** is the
balance at the end of it, before the next day's adjustment. A week's
**closing balance** is its Sunday close. On the week a contract starts or
ends mid-week, or a term that owes nothing begins or ends, `worked`
counts hours the balance does not, so the move between two closes is not
`worked − expected`; on any week it also includes the week's adjustments.
The ledger therefore sends each closed week's **move**, `balance_moved`:
the close less the one before, less the adjustments between, read off
the same pass whether or not the week before is shown.

**Day boundaries** use the request timezone (`tz`, default UTC). A beat
belongs whole to the local day it started on, and a running timer counts
up to now. The holiday *region* is the employer's, which may be a
different country from the user's timezone — a frontalier gets Geneva's
holidays on Paris time, which is correct.

**The null rule.** A week has no expectation — `null`, not 0 — when no
weekday of it has a term that owes more than 0 hours: before the
contract, under an objective term, or under a term of 0 hours. A 0 is a
week the contract owed nothing by circumstance: every weekday a holiday
or an absence, or after `ended_on`. The balance is null on the same rule
for today's term. A 0-hour term (a sabbatical, or the migration's
reading of "no goal from here") still *governs* the week, so the
personal goal does not resurface under it; reporting it as `expected: 0`
once put "12.0/0.0h" in the header. `week_expectation` and `owes` decide
this in one place, so every reader agrees to the decimal by
construction. Hour figures are rounded to two decimals on the wire.

### The goal

`Project.effective_goal(week_monday)` is the one source of a week's goal
for every reader — the score, patterns, planning, health, the coach. On
a day job whose term in force that Monday is time-based
(`Project.goal_term`), the goal is the term's plain `hours_per_week`,
always a target, and `weekly_goal` and `goal_overrides` are not read.
Elsewhere — before the first term, under an objective term, without a
contract, on any other kind — the personal goal applies with its
overrides. A term changing mid-week is the next Monday's goal. A
governing term of 0 hours is no goal. `ended_on` is not consulted: the
last term stays the goal, so no personal goal reappears that the form
cannot show; archiving takes a finished job out of the readers.

**The goal is nominal; a figure beside the week is adjusted.** The
score, the health rail and the coach's goal line want what the week owes
by contract, before holidays and absences. But the Inbox's planning line,
the pacing card and the stale-project card quote a figure on the same
screen as the week, and "You need 32.0h more" beside a ring against
25.6 was the one contradiction the user saw. Those three read the
adjusted expectation through `WeekExpectationReader`
(`ContractService.expected_for_week`, mapped in `intelligence/goals.py`).
A governed line reads "You need 25.6h more this week under your
contract" — a contract is not "hit". The coach gets both: the nominal
goal in its cached profile, and beside today, in the day context, the
adjusted week, what is left of it, the balance and its by-Sunday
projection (`coach/contract_section.py`). Its `get_patterns` tool builds
the service with the same reader, so its pacing and stale-project cards
quote the Inbox's figure. The hours all of them count against it are the
week card's too: worked on a day the balance counts (`counts_worked`), so
on a week a term that owes nothing begins or ends, the hours under it are
tracked and owe the figure nothing.

### Vacation

`domain/vacation.py`, pure like the rest: absences and a `set[date]` of
the contract's holidays in, one year out. Decision 14 is the rule.

```
the opening year (opening_on's):
    available = opening_days                      (accrued: null)
every later year y, through ended_on's:
    accrued   = days_per_year × days covered / days in y, half up to ½
                (covered is the whole year except in ended_on's)
    carried   = what y − 1 left: all, min(left, cap), or 0 — a deficit whole
    available = accrued + carried
booked    = Σ cost(d) for d in y
remaining = available − booked

cost(d) = 1, or ½ for a half day, for a vacation absence on a weekday d
          with opening_on <= d, starts_on <= d <= ended_on, and d not a
          holiday of the contract; else 0
```

The chain runs from the opening year to the year asked for, and each
year's accrual is arithmetic, so a year far ahead on an open-ended
contract costs no calendar. The calendar is built once, over the span of
the vacation days read, from `contract_holidays` like every other figure:
a company holiday costs no leave either. `booked` counts planned days as
well as taken ones; there is no split by today, so the clock is read only
for the default year.

### The timesheet

A day job's month as a CSV, for the employer (`domain/timesheet.py`, pure
like the ledger, through `GET /api/projects/{id}/timesheet.csv?month=`).
It is a download and nothing else: there is no JSON route, and the page
shows none of its figures (Decision 11; project-page.md's Decision 11).

```
first = max(the 1st, start)
last  = min(the month's end, ended_on, yesterday)     no day → 409

brought forward = opening_balance_hours           if first = start
                  close(first − 1)                otherwise, null when its term owes nothing
each day d:       expected(d), worked(d), worked − expected,
                  the adjustment and its applied, close(d)
carried forward = close(last)

brought forward + difference + adjusted = carried forward
```

- **What a sheet covers** is the month's finished days inside the
  contract. A contract starting mid-month starts its first sheet then,
  `ended_on` stops its last, and the current month runs through yesterday,
  so on the 1st it has none. The month's end comes off the calendar
  (`calendar.monthrange`), so December 9999 is a month like any other: in
  the future, 409.
- **One pass, the ledger's.** Every close, every adjustment's `applied`
  and the figure brought forward come from one `running_balance` pass over
  the contract's life through `last`, so the sheet agrees with the ledger
  and the week on the day it is downloaded. The service reads beats,
  absences, adjustments and the calendar from `start`, not from the 1st:
  a close needs every day before it.
- **The null rule is the row's.** A day whose term owes nothing (`owes`:
  an objective or 0-hour term) has no expected, difference or balance —
  blank cells. Its hours are in the day's worked and the total's, as on
  the ledger, but not in the balance (`counts_worked`), so the total's
  difference is the rows', worked less expected over the days that have
  one: without such a day it is the total's worked − expected.
  A weekend, a holiday or a day off under an owing term is 0.00, not
  blank. Brought forward follows the same rule for the day before `first`;
  on the sheet that starts on the contract's first day it is the opening
  balance. The total's expected is the sum of the days that have one, and
  blank when none does.
- **Months chain.** One month's carried forward is the next month's
  brought forward, and whenever both are set the identity above holds —
  exact on the raw figures, and within 0.02 in the file, since each of the
  four is rounded on its own from a raw sum, as the ledger's totals are.
  Rows sum to the total only within a few cents the same way: to the cent,
  not to the bit. Each row moves the balance by its difference plus its
  adjustment.
- **Adjustments are in the sheet.** A day carries the kind of the balance
  adjustment dated on it (`delta`, `reset`, `cap`) and what it moved the
  balance by, at the start of that day, against the close before; the
  total's `adjusted` is their sum. So a month with a payout still adds up.
  A settlement dated after `ended_on` falls after the last sheet: that
  sheet carries forward the final balance, before it, as the ledger's
  `ended_balance` does. The adjustment's note is not in the file.
- **What is counted.** The total's `holiday` cell counts the weekday
  holidays of the sheet; its `absence` cell the weekday absences that are
  not on a holiday, a half day as ½ — a vacation booked on a public holiday
  was given by the holiday. A holiday or an absence on a weekend is
  neither named nor counted, since a weekend owes nothing under any term.
  Vacation days show as absences of type `vacation`; the entitlement's
  figures are not in the sheet (`/vacation` has them).
- **A company holiday reads `company holiday`**, not the name typed for
  it: the file goes to the employer, and the name is the user's own text
  (`contract_holidays(…, company_name=…)`). A public holiday keeps the
  library's name, in the language `holidays.py` picks.
- **A running timer counts as it runs**, on the day it started, as on the
  ledger: a timer still running from yesterday is charged to yesterday,
  and yesterday's row and every balance after it grow until it stops.
  Stopping or correcting it changes a re-download.
- **A sheet is a snapshot.** Recording a beat, an absence or an adjustment
  in the month later, or replacing the contract (`PUT /contract` replaces
  the terms and the opening balance), changes what a fresh download says.
  Nothing is versioned. A month cut short says so in the file's name
  (`…-2026-10-through-15.csv`), which the SPA gives it; the server sends
  `Content-Disposition: attachment` with no filename, which a cross-origin
  page could not read anyway.
- **The file** is RFC 4180: comma-separated, a dot for decimals, two fixed
  decimals, UTF-8 without a BOM, CRLF line ends, one header row and no
  other metadata. German-locale Excel expects semicolons; its import dialog
  reads this file, and no parser has to guess. The columns are `date,
  weekday, expected, worked, difference, holiday, absence, half_day,
  adjustment, adjusted, balance`; a "brought forward" row comes first, with
  only its balance, and a "total" row last. A rounded −0.0 is written
  0.00, so a day worked exactly to contract does not read −0.00. Nothing
  in it is text the user typed — not an absence's note, not an
  adjustment's, not a company holiday's name — so there is no formula
  injection to guard against.

---

## Migration

Code cites these rules as "Phase 2". Two passes run at startup in
`lifespan` (`api/src/beats/infrastructure/migrations.py`), in this
order, each keyed on document shape and so idempotent.

**`migrate_project_kinds`** stamps a `kind` on every project without
one. Lazy defaults are not used, because terms derived from overrides
must be stored once and then owned by the user. Per project:

1. No `weekly_goal`, or one that is zero or negative → `side_project`.
2. `weekly_goal` set and `goal_type == cap` → `side_project`, goal kept
   (a cap is a limiter, not a contract).
3. `weekly_goal` set and `goal_type == target` → `day_job`:
   - the base term: `effective_from` = the UTC date of the project's
     earliest beat, running or not, or — `Project` has no `created_at`
     — the ObjectId's date if it has none; `custom`;
     `weekly_hours = weekly_goal`.
   - every `effective_from` override becomes a `custom` term on that
     date at its hours; `weekly_goal is None` → `weekly_hours = 0`, a
     term that owes nothing and so counts no hours toward the balance. An
     override dated on or before the base date was already in force,
     so it *replaces* the base term's hours — the latest such override
     wins, as it did under `effective_goal` — and the project's own
     `weekly_goal` appears in no term. Two overrides on one date resolve
     to the first in list order. An override typed `cap` becomes a term
     all the same; its date is logged, since a limit has become an
     obligation.
   - `week_of` overrides are one-week deviations, not contract changes.
     They stay on `goal_overrides`, and their weeks are logged.
   - no region, no opening balance.

Terms are coalesced when consecutive ones have the same hours, so the
history is of changes. The pass is additive — it sets `kind` and
`contract` and nothing else — so a rollback, or an old revision during a
rollout, shows the goal it always did, and a document rewritten without
`kind` is migrated again to the same contract. Logs carry ids only, no
names. A document the pass cannot read is logged, left without a `kind`
so the next boot retries, and does not stop startup.

**The model and this pass deploy together.** The repository writes the
default `kind` on every save, so a target project saved by a build with
the model but not the pass would look migrated with no contract. For
the same reason `PUT /api/projects` keeps the stored `kind` and
`contract` when the request omits them.

**`clear_personal_goal_on_day_jobs`** runs second, since the contract is
derived from the goal. It unsets `weekly_goal` on every day job whose
`goal_term` for today's UTC date is set — the readers' predicate. A day
job under an objective term, before its contract, or without one keeps
its goal, because its readers still show it. `goal_overrides` stay: a
`week_of` override is the user's note on a week.

This pass is not additive. Rolled back past it, cleared projects read
by the personal goal's path with only their overrides: readers disagree
until roll-forward, but nothing is lost — the number is in the terms
(Decision 10). A revision without the model that rewrites such a
document drops `kind` and `contract`, and the first pass then migrates
it as a side project. That is a rollback across four deployed phases,
and it is accepted.

---

## HTTP contract

Contract routes are in `routers/projects.py`, absences in
`routers/absences.py` and balance adjustments in `routers/adjustments.py`
under the same prefix, regions in `routers/meta.py`. `ContractService`
assembles weeks, ledgers and balances behind narrow ports
(`ProjectReader`, `ProjectBeatReader`, `AbsenceStore`, `AdjustmentStore`);
`ProjectService.replace_contract` is the one contract write, beside the
region check, and every project write reconciles the adjustments
(`ContractAdjustments`).

| Route | Purpose |
|---|---|
| `POST/PUT /api/projects` | `kind` and `contract` on create/update; 422 from the validators, at the term's path (`contract.terms.0`) |
| `GET /api/projects?include=this_week` | adds `contract_expected`, `contract_worked`, `contract_remaining`, `balance` for the current week |
| `PUT /api/projects/{id}/contract` | replace terms / region / company holidays / holidays not given / opening balance / `ended_on` / vacation entitlement as one object, except a holiday list or `vacation` the request leaves out; `kind` untouched |
| `GET /api/projects/{id}/contract/week?week_of=` | `{week_of, expected, worked, remaining, balance, balance_as_of, balance_opening, balance_worked, balance_expected_through, balance_adjusted, days: [{date, expected, worked, holiday, absence}]}` |
| `GET /api/projects/{id}/ledger?weeks=` | any kind: N weeks (1–104, default 8) newest first, each with `contract_expected`, `balance_end`, `balance_moved` and its `adjustments` (each with `applied`); `since`; `totals` as of today, `adjusted` among them; `ended_balance` |
| `GET /api/projects/{id}/holidays?year=&include=not_given` | the contract's holidays by date as `[{date, name, source, given}]`: the region's the employer gives and the company's (`source: region \| company`), all `given: true`; `include=not_given` adds the region's on `holidays_not_given` with `given: false`, even where a company day covers the date, which is then listed twice, the region's row first. Only company days without a region; `[]` without a contract |
| `GET /api/projects/{id}/timesheet.csv?month=` | a day job's month (`YYYY-MM`, required) as CSV, one row per finished day inside the contract, a "brought forward" row first and a "total" row last; `Content-Disposition: attachment`, no filename |
| `GET /api/projects/{id}/vacation?year=` | one year of the entitlement in days: `{year, accrued, carried_in, available, booked, remaining}`; `year` defaults to the current one in `tz` |
| `GET/POST/DELETE /api/projects/{id}/absences` | list by range, create (upsert on date, 201), delete (204) |
| `POST /api/projects/{id}/adjustments?tz=` | a delta, reset or cap (upsert on date, keeps the id, 201); `tz` required |
| `DELETE /api/projects/{id}/adjustments/{adjustment_id}` | 204, or 404 when it is not on this project |
| `GET /api/meta/holiday-regions` | `[{code, name, subdivisions: [{code, name}]}]`; `Cache-Control: public, max-age=86400`; behind the normal auth |
| `GET /api/meta/holidays?country=&subdivision=&year=` | one region's public holidays for a year as `[{date, name}]`, by date, as the region gives them: no contract is read, so it answers for a region no contract names yet. `country` and `year` required (422 naming the one missing); an unknown country or subdivision is 400 `UNKNOWN_HOLIDAY_REGION`; cacheable and session-only like the region list |

- **Omitted is not null on `PUT /api/projects`.** Older clients do not
  send `kind` or `contract`, so the route reads `model_fields_set`: left
  out keeps the stored value, `contract: null` clears it. Requests carry
  the domain `Contract` itself — its validators produce the 422, and a
  mirror would drift. The same holds inside a sent contract for
  `company_holidays`, `holidays_not_given` and `vacation`, on
  `PUT /api/projects` and `PUT /{id}/contract` alike
  (`keep_unsent_contract_fields`): an SPA that predates them rebuilds the
  whole contract on every term edit, and must not delete them; `[]` or
  `vacation: null` clears. An API revision without them drops them when
  it rewrites a project — the rollback loss the migration already accepts.
- **The vacation opening stays inside the contract.** Because a kept
  entitlement can meet new terms, both writes check, after the merge, that
  `opening_on` falls between the first term and `ended_on`, and answer 409
  `VACATION_OPENING_OUTSIDE_CONTRACT` otherwise ("The vacation count starts
  on Mar 2, 2026, outside the contract's dates; change it in the project
  settings first"). Removing the first term, inserting an earlier one or
  moving `ended_on` is refused, never silently reinterpreted.
- **A contract lives only on a day job.** One sent with any other kind
  is 409 `NOT_A_DAY_JOB`, and a `PUT` moving a day job to another kind
  without mentioning `contract` clears it. Nothing dormant is kept for
  an undo: it would be a contract no route could read.
- **Wrong kind is a 409**, not a 400: `NOT_A_DAY_JOB` on the contract,
  week, holidays, vacation, timesheet and absence routes; `NO_CONTRACT` for
  the week, the vacation year or the timesheet of a day job without one.
  The timesheet is also 409 `OUTSIDE_CONTRACT` for a month with no
  finished day inside the contract, and its `month` a 422 naming it unless
  it is `YYYY-MM` (`0000-01` included). The vacation year is also
  409 `NO_VACATION_ENTITLEMENT` on a contract without one, and
  `VACATION_YEAR_OUT_OF_RANGE` for a year before the opening's or after
  `ended_on`'s ("Vacation is counted from 2026 through 2028"). An unknown region is 400 `UNKNOWN_HOLIDAY_REGION`;
  the index logs it and leaves that project's contract fields null.
- **Every non-2xx is in the envelope.** A malformed project id is a 404
  like an unknown one; someone else's project is a 404, never a 403.
  `week_of` must be a Monday (defaulting to the current week in `tz`),
  and a `week_of` or `year` past the calendar is a 422 naming it. On
  `PUT /{id}/contract` a model-level error has an empty `path`: the
  body *is* the contract.
- **The balance carries its terms.** `balance_opening + balance_worked −
  balance_expected_through + balance_adjusted` is `balance` within 0.025:
  each of the four terms and the balance is rounded on its own, 0.005 at
  most apiece. All five are null exactly when `balance` is. It is as of
  today, whatever week is asked for, and counts the adjustments dated
  through today. `remaining` goes negative once the week is over. Each
  figure is rounded from the raw hours on its own, so `worked +
  remaining` can miss `expected` by a hundredth, and by a tenth at the
  decimal the page shows (8.545 h of 40 reads 8.5 worked and 31.4
  remaining). The
  ledger's totals carry the same terms, and its `ended_balance` is the
  close on `ended_on` once that day has passed — the final balance before
  a settlement after it, null otherwise, on `ended_on` itself too, whose
  hours still count.
- **Absences.** `GET` defaults each bound to the current year in `tz`.
  `POST` answers 201 even when it replaced one, and is accepted on a day
  job with no contract yet — leave first, contract later. `DELETE` is by
  id within the project in the path, so its 404 means "not on this
  project".
- **Balance adjustments.** `POST` needs a contract (409 `NO_CONTRACT`)
  and a date from the first term through today in `tz` (409
  `ADJUSTMENT_OUTSIDE_BALANCE`); `tz` is required, a 422 when missing,
  since the date rule is the caller's today. It answers 201 even when it
  replaced one. There is no list route: the ledger carries every field a
  reader wants. A contract write reconciles them against the contract it
  replaces: when the contract goes they are purged after the write; when
  one arrives where there was none, leftovers are purged first (no
  adjustment is live without a contract, so this clears what a failed
  purge left); and moving the first term later past one is 409
  `ADJUSTMENT_BEFORE_START`. Anything else — a rename resending the
  contract unchanged, a first day moved earlier — reads nothing.
- **A backup goes back through these rules.** `POST /api/export/import`
  restores a project as a project write (`ProjectService.restore_project`:
  the contract checks, and the reconcile above against the contract it
  replaces) and then the absences and adjustments through
  `ContractService`'s record methods, in the request's `tz`. A project write
  they refuse stops the import with its error, there being no transaction:
  the projects before it stay restored, and no session, absence or
  adjustment is written; importing again once the conflict is fixed is
  safe. An absence or an adjustment they refuse is left out and listed
  under `skipped` with its route's code, not a failure of the file: an
  absence outlives a kind change away from `day_job`, so an honest export
  carries one its route now refuses.
- **`this_week` on the index** is the week route's current week, null on
  anything but a day job with a contract. `contract_worked` sits beside
  `weekly_minutes` because they differ: `weekly_minutes` is the personal
  goal's, completed beats only, by UTC date.
- **Holidays are cached per region and year**: the balance rebuilds
  every year since the contract started on each request, and some
  regions cost ~10 ms a year. The cache keeps the 4,096 most recently
  read (some 20 MB at most), because `/api/meta/holidays` takes any
  region and year from any session and an unbounded one would grow with
  whatever it is asked. Company days and the dates not given come from
  the contract the request already read, and cost nothing.
- **Device tokens** reach every route under `/api/projects`, since
  `DEVICE_ALLOWED_PREFIXES` matches by prefix. That exposes nothing new:
  a device could already `PUT /api/projects`. `/api/meta` is
  session-only.

---

## The UI's rules

- **The index reads the list; the page reads the ledger and the week.**
  `weekGoalView` takes the contract's figures on a day job whose
  `contract_expected` is not null and the personal goal's elsewhere. The
  balance shows on the index as a chip, since the sign is what a glance
  is for.
- **A governed week offers no override.** `contractGovernsWeek` mirrors
  `Project.goal_term`. `isTimeBasedOn` hides the personal goal, and also
  counts a contract not yet started, so the form hides the goal a new
  contract will replace.
- **A day job may wait for its contract.** The form's first term sits
  behind "Set up the contract now", so renaming does not demand one.
- **A region change names the removals it brings into force.** While the
  settings form holds a region other than the stored one on a contract
  with `holidays_not_given`, it reads both regions' calendars from
  `/api/meta/holidays`, for the years those dates fall in, and
  `revivedNotGiven` lists each date the new region has a holiday on and
  the old one had none, by the new holiday's name — less a date a company
  day covers, which stays a day off either way. "Clear the marks" ("the
  mark" for one) drops those dates in the same save, "Keep the marks"
  takes that back, and a further region change starts over. Save waits
  for both calendars, under "Checking … holidays", so no mark comes into
  force unseen. When one fails, after the client's retries, the form
  says the marks could not be checked and what saving does to them, and
  offers "Try again"; Save is let go then, since the SPA ships apart
  from the API and holding it would block every region change against
  an API without the route.
- **Balance wording.** `describeBalance` rounds to the decimal shown
  before judging the sign — −0.04 h reads "even" — and never prints a
  bare signed number: "+4.5 h over", "−2.0 h owed". The API's twin, for
  the coach, is `describe_balance` in `coach/contract_section.py`; a
  change to either is made in both.

**What leaves Beats.** The coach sends a day job's goal as one line
(`Acme: 33.6h/week (contract, 80%)`), its hours and its percentage to
the hundredth as the page's `formatHours` and `toPercent` print them
(28.88h, never "28.875h"; 87.5%, never "88%"; `fmt_hours` and
`fmt_percent` are the twins), and on a day job with a contract the
current week against it, labelled as the goal line is (by the term in
force on the week's Monday, or on the contract's first day when it
starts mid-week; that week the goal line does not yet carry the
contract): what it expects after holidays and days off, the hours worked
and what is left, today's expected hours, the running balance and its
by-Sunday projection, the dates of this week's holidays and days off
that shortened it, and `ended_on` once it falls inside the week. Each
figure is the API's own, from the week the page reads (on `ended_on`
itself too, a day both keep live, its projection the close), and is
printed as the page prints it (one decimal, as `toFixed` rounds the
binary value; the balance through `describe_balance`), so the coach says
what the page says even where the page's figures do not add up at that
decimal. The hours worked are the page's Worked, the whole week's; on a
week the contract starts or ends inside, what is left counts only the
contract's days, and the line says "(the contract counts only its own
days this week)", which with no `ended_on` beside it says the contract
started this week. In the contract's first seven days the page shows no
projection, and the coach sends "first week under the contract" in its
place, bar the contract's last day, when both give the projection. The
balance is opening + worked − expected + adjusted, and only the sum is
sent: the opening balance and the adjustments (their dates,
kinds and notes) are not sent as figures of their own, though the sum is
the opening balance on a contract's first day and moves by a payout on
its date. A public holiday goes by its name. The region is not sent as a
field of its own, but a regional holiday's name can name it, for example
"Augsburg Peace Festival" in DE-Augsburg or "Yap Day" in FM-YAP, and for
some subdivisions the library's code is the place name, so the holiday's
name contains the code. No country code is sent. A company holiday goes
only as "company holiday", never the name the user typed; a day off only
as "day off" or "half day off", never its type or note. Other weeks'
holidays and absences are not sent by the contract section, though the
last 14 rated briefs go with every prompt, each with its opening
sentence, and a brief that opened on a day off or a balance repeats it;
`PRIVACY.md` lists them. On `ended_on` itself the contract is still
live, since that day's hours count: the coach sends today's expected
hours, the running balance and the by-Sunday projection. A contract that
ended before today, earlier in the current week, sends only its final
balance and its end date; one that ended before it sends none of the
week, though its goal line stays in the profile and in `get_projects`
until the project is archived (`goal_term` does not consult `ended_on`).
The vacation entitlement is not sent.

Every day and week the coach reads is the request timezone's: the
contract section's week and today, the calendar's day and the times its
events are printed at, the goal line's week and the weekly
totals in the profile, the productivity score, the memory rewrite's last
seven days, and the tools' (`get_projects`' week, the dates `get_beats`
takes and prints, the patterns'). So the label and the goal line name
one term on a Sunday evening west of UTC too. The SPA sends `tz` with a
brief, a chat message and a memory rewrite; a client that sends none
gets UTC's. For now that is the companion's chat, and its brief
notification, which looks for the brief of UTC's today
(`getTodayBrief` in `notification_poller.dart`, without a timezone).

`/api/export/full` carries the contract, its entitlement included, the
absences and the balance adjustments, so a backup restores the same
balance. The monthly timesheet carries, per day, the hours worked and
expected, the balance adjustment's kind and what it moved, the public
holiday's name or `company holiday`, the absence type and half-day flag,
and the balance — no note of any kind. Device tokens can reach it through
the `/api/projects` prefix, as they can the ledger. `PRIVACY.md` and
`DATA.md` state this; a change happens there first.

---

## Follow-ups and open questions

Tracked in Linear — the [LifePete project](https://linear.app/elghareeb/project/lifepete-a8ecce3a86de), milestone *Work
contracts follow-ups* (AHM-30 to AHM-36): the companion's week card, and
whether `hours_per_day` should be configurable for a 4-day full-time
week. Vacation entitlement is Decision 14, the monthly timesheet "The
timesheet", and the coach's view of the week "What leaves Beats".
The balance ledger's read side was built by
[project-page.md](project-page.md), its write side by Decision 13.
