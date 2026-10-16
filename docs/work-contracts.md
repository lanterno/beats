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
**balance** — overtime if positive, hours owed if negative.

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
   way. No entitlement, no leave balance this iteration.
6. **Time off in lieu is not a feature.** A comp day is a weekday with
   no absence recorded and no work done: expectation stands, worked is
   zero, the balance goes down by itself.
7. **Worked time is whatever the timer says** on that project. No
   breaks, no rounding, no manual day entries.
8. **Objective-based day jobs** have no expectation and no balance —
   but the user may still set a *personal* weekly goal on them, which
   is the existing `weekly_goal` field doing what it always did.
9. **Contract changes are first-class.** Part-time → 80% → full-time is
   the normal life of a contract, and every calculation is term-aware
   down to the day.
10. **Migration keeps the numbers users already had**, including the
    history of how a goal changed over time.
11. **Timesheets and export are a follow-up.** The product goal of this
    iteration is the *week*: expected, worked, remaining, balance.
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
    of the two marks could not clear the other.

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

class CompanyHoliday(BaseModel):
    date: date
    name: str                         # stripped, 1-80 characters

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

That the region codes are ones the library knows is checked by
`ProjectService` when a contract is written, not by the model. The model
is re-validated on every read, and a code a library upgrade stops
knowing must make one contract un-editable, not the user's whole project
list unreadable.

Absences are unique on `(user_id, project_id, date)`: a second absence
on a day replaces the first. The type is for the record and the
calendar's colour; the arithmetic treats all three identically.

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
               + worked(start .. min(today, ended_on))
               - expected(start .. yesterday)
```

Today's expectation is charged tomorrow, so the balance does not read
−6 h every morning; today's work counts at once. `start` is the first
term's `effective_from`. `ended_on` freezes both sides: nothing is
expected after it, and time tracked after it is not overtime either.

A week's **closing balance** (`closing_balances`) is the same sum taken
through its Sunday — the Monday-morning figure. On the week a contract
starts or ends mid-week, `worked` counts hours the balance does not, so
the move between two closes is not `worked − expected`.

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
score, the health rail and the coach want what the week owes by
contract, before holidays and absences. But the Inbox's planning line,
the pacing card and the stale-project card quote a figure on the same
screen as the week, and "You need 32.0h more" beside a ring against
25.6 was the one contradiction the user saw. Those three read the
adjusted expectation through `WeekExpectationReader`
(`ContractService.expected_for_week`, mapped in `intelligence/goals.py`).
A governed line reads "You need 25.6h more this week under your
contract" — a contract is not "hit".

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
     date at its hours; `weekly_goal is None` → `weekly_hours = 0`. An
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
`routers/absences.py` under the same prefix, regions in
`routers/meta.py`. `ContractService` assembles weeks, ledgers and
balances behind narrow ports (`ProjectReader`, `ProjectBeatReader`,
`AbsenceStore`); `ProjectService.replace_contract` is the one contract
write, beside the region check.

| Route | Purpose |
|---|---|
| `POST/PUT /api/projects` | `kind` and `contract` on create/update; 422 from the validators, at the term's path (`contract.terms.0`) |
| `GET /api/projects?include=this_week` | adds `contract_expected`, `contract_worked`, `contract_remaining`, `balance` for the current week |
| `PUT /api/projects/{id}/contract` | replace terms / region / company holidays / holidays not given / opening balance / `ended_on` as one object; `kind` untouched |
| `GET /api/projects/{id}/contract/week?week_of=` | `{week_of, expected, worked, remaining, balance, balance_as_of, balance_opening, balance_worked, balance_expected_through, days: [{date, expected, worked, holiday, absence}]}` |
| `GET /api/projects/{id}/ledger?weeks=` | any kind: N weeks (1–104, default 8) newest first, each with `contract_expected` and `balance_end`; `since`; `totals` as of today |
| `GET /api/projects/{id}/holidays?year=&include=not_given` | the contract's holidays by date as `[{date, name, source, given}]`: the region's the employer gives and the company's (`source: region \| company`), all `given: true`; `include=not_given` adds the region's on `holidays_not_given` with `given: false`, even where a company day covers the date, which is then listed twice, the region's row first. Only company days without a region; `[]` without a contract |
| `GET/POST/DELETE /api/projects/{id}/absences` | list by range, create (upsert on date, 201), delete (204) |
| `GET /api/meta/holiday-regions` | `[{code, name, subdivisions: [{code, name}]}]`; `Cache-Control: public, max-age=86400`; behind the normal auth |

- **Omitted is not null on `PUT /api/projects`.** Older clients do not
  send `kind` or `contract`, so the route reads `model_fields_set`: left
  out keeps the stored value, `contract: null` clears it. Requests carry
  the domain `Contract` itself — its validators produce the 422, and a
  mirror would drift. The same holds inside a sent contract for
  `company_holidays` and `holidays_not_given`, on `PUT /api/projects` and
  `PUT /{id}/contract` alike (`keep_unsent_holiday_changes`): an SPA that
  predates them rebuilds the whole contract on every term edit, and must
  not delete them; `[]` clears. An API revision without the lists drops
  them when it rewrites a project — the rollback loss the migration
  already accepts.
- **A contract lives only on a day job.** One sent with any other kind
  is 409 `NOT_A_DAY_JOB`, and a `PUT` moving a day job to another kind
  without mentioning `contract` clears it. Nothing dormant is kept for
  an undo: it would be a contract no route could read.
- **Wrong kind is a 409**, not a 400: `NOT_A_DAY_JOB` on the contract,
  week, holidays and absence routes; `NO_CONTRACT` for the week of a day
  job without one. An unknown region is 400 `UNKNOWN_HOLIDAY_REGION`;
  the index logs it and leaves that project's contract fields null.
- **Every non-2xx is in the envelope.** A malformed project id is a 404
  like an unknown one; someone else's project is a 404, never a 403.
  `week_of` must be a Monday (defaulting to the current week in `tz`),
  and a `week_of` or `year` past the calendar is a 422 naming it. On
  `PUT /{id}/contract` a model-level error has an empty `path`: the
  body *is* the contract.
- **The balance carries its terms.** `balance_opening + balance_worked −
  balance_expected_through` is `balance` within 0.01, each rounded on its
  own; all four are null exactly when `balance` is. It is as of today,
  whatever week is asked for. `remaining` goes negative once the week is
  over.
- **Absences.** `GET` defaults each bound to the current year in `tz`.
  `POST` answers 201 even when it replaced one, and is accepted on a day
  job with no contract yet — leave first, contract later. `DELETE` is by
  id within the project in the path, so its 404 means "not on this
  project".
- **`this_week` on the index** is the week route's current week, null on
  anything but a day job with a contract. `contract_worked` sits beside
  `weekly_minutes` because they differ: `weekly_minutes` is the personal
  goal's, completed beats only, by UTC date.
- **Holidays are cached per region and year**: the balance rebuilds
  every year since the contract started on each request, and some
  regions cost ~10 ms a year. Company days and the dates not given come
  from the contract the request already read, and cost nothing.
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
- **Balance wording.** `describeBalance` rounds to the decimal shown
  before judging the sign — −0.04 h reads "even" — and never prints a
  bare signed number: "+4.5 h over", "−2.0 h owed".

**What leaves Beats.** The coach sends a day job's goal as one line
(`Acme: 33.6h/week (contract, 80%)`), not absences, the region, the
company holidays or the balance. `/api/export` carries the contract but
not absences. `PRIVACY.md` and `DATA.md` state this; a change happens
there first.

---

## Follow-ups and open questions

Tracked in Linear — the [LifePete project](https://linear.app/elghareeb/project/lifepete-a8ecce3a86de), milestone *Work
contracts follow-ups* (AHM-30 to AHM-36): the monthly timesheet, vacation
entitlement, the ledger's write side, the coach seeing the balance, the
companion's week card, and whether `hours_per_day` should be configurable
for a 4-day full-time week. The balance ledger's read side was built by
[project-page.md](project-page.md).
