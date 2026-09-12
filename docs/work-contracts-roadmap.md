# Work Contracts — Roadmap

> Beats records what you worked on. This makes it able to say what you
> *owed* — so that on a Thursday afternoon you know whether Friday ends
> at three or at seven, and whether you are ahead of the company or
> behind it.

A project gains a **kind** (`day_job`, `freelance`, `side_project`), and
a day-job project carries its **contract**: how much of a week it is
owed, where it is (for the public holidays), and how those terms have
changed over time. From the contract, the holidays, and the user's
absences, Beats derives the hours expected each week and a running
**balance** — overtime if positive, hours owed if negative.

The decisions below were made in conversation and are recorded so that
the implementation does not re-litigate them. Anything marked *open* is
genuinely undecided.

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

---

## Data model

### `Project` gains

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
    full_time_hours: float | None     # required unless custom / objective
    percentage: float | None          # 0 < p <= 1; 1.0 for full_time
    weekly_hours: float | None        # required for custom; derived otherwise
    note: str | None

    @property
    def hours_per_week(self) -> float | None: ...   # None for objective
    @property
    def hours_per_day(self) -> float | None: ...    # hours_per_week / 5

class Contract(BaseModel):
    terms: list[ContractTerm]         # sorted by effective_from, non-empty
    holiday_country: str | None       # ISO 3166-1 alpha-2, e.g. "CH"
    holiday_subdivision: str | None   # ISO 3166-2 part, e.g. "ZH"
    opening_balance_hours: float = 0  # hours banked before Beats
    ended_on: date | None             # freezes the balance

class Project(BaseModel):
    ...
    kind: ProjectKind = ProjectKind.SIDE_PROJECT
    contract: Contract | None = None  # only meaningful when kind == day_job
```

`weekly_goal` / `goal_type` / `goal_overrides` are untouched. They are
the *personal* goal and keep applying to side projects, freelance work,
and objective-based day jobs. For a time-based day job the contract is
the goal; the form hides the personal one and the week card does not
show it.

### `Absence` (new collection)

```python
class AbsenceType(StrEnum):
    VACATION = "vacation"
    SICK = "sick"
    OTHER = "other"

class Absence(BaseModel):
    id: str | None
    project_id: str
    date: date
    half_day: bool = False
    type: AbsenceType
    note: str | None
```

Unique on `(user, project_id, date)`. The type is for the record and the
UI's colour; the arithmetic treats all three identically.

---

## The arithmetic

Everything reduces to one function over a date range.

```
expected(d) for a weekday d:
    term  = the term with the latest effective_from <= d     (none → 0)
    base  = term.hours_per_day                                (objective → 0)
    if d < first term's effective_from or d > ended_on:      0
    if d is a public holiday in the contract's region:        0
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
- **Half day** costs `base / 2`; two absences on one day are one absence.

```
balance(today) = opening_balance_hours
               + worked(start .. min(now, ended_on))
               - expected(start .. yesterday)
```

Today's expectation is charged tomorrow, so the balance does not read
−6 h every morning. `start` is the first term's `effective_from`.
`ended_on` freezes both sides: nothing is expected after it, and time
tracked on the project after it does not count as overtime either.

**Day boundaries** use the request timezone the API already resolves
(`TimezoneDep`). The holiday *region* is the employer's, which may be a
different country from the user's timezone — a frontalier gets Geneva's
holidays on Paris time, which is correct.

---

## Phases

Each phase ends green on the pre-push gates and, where the phase touches
`main`, pushes to it. Later phases must not be started on the strength
of an earlier one being "basically done".

### Phase 1 — Domain: terms, expectation, balance `[api]`

Pure code, no HTTP, no Mongo beyond the new repository.

- `domain/models.py`: `ProjectKind`, `ScheduleType`, `ContractTerm`,
  `Contract`, `AbsenceType`, `Absence`. Validators: terms non-empty and
  strictly increasing by `effective_from`; `percentage` in `(0, 1]`;
  `full_time` forces `percentage = 1`; `part_time` needs it below 1;
  `custom` requires `weekly_hours`; `objective` allows none of the
  numbers; `holiday_subdivision` needs `holiday_country`. That both are
  codes the library recognises is checked by `ProjectService` when a
  contract is written, not by the model: the model is re-validated on
  every read, and a code a library upgrade stops knowing must make one
  contract un-editable, not the user's whole project list unreadable.
- `domain/contracts.py`: `term_on(contract, day)`,
  `expected_hours(contract, absences, holidays, start, end)`,
  `balance(...)`. Takes holidays as a `set[date]` so the function is
  pure and the library is injected.
- `domain/holidays.py`: the only place that imports `holidays`.
  `holidays_between(country, subdivision, start, end) -> set[date]`,
  `regions() -> list[Region]` for the picker. Add `holidays` to
  `pyproject.toml`.
- `domain/ports.py`: `AbsenceStore` (list by project + range, upsert,
  delete). `infrastructure/repositories.py`: the Mongo implementation
  and the `(user, project, date)` unique index in the startup index
  build.

**Tests** (`test_contracts.py`, beside `test_domain.py`) — the interesting
inputs only:
holiday on a Saturday; substitute Monday for a Sunday holiday in `GB`;
half day; two terms changing on a Wednesday; contract starting on a
Thursday; `ended_on` mid-week; objective term contributes zero; balance
excludes today's expectation and includes today's work; a term with
`percentage = 0.8` on `full_time_hours = 42` yields 33.6 and 6.72/day.
No test that a region "has" a holiday — that is the library's suite.

### Phase 2 — Migration `[api]`

Runs once at startup for every project document without a `kind`
field; a migrated document has one, so it is idempotent by
construction. Lazy defaults are *not* used here because terms derived
from overrides must be stored once and then owned by the user.

Rules, applied per project:

1. No `weekly_goal` → `side_project`.
2. `weekly_goal` set and `goal_type == cap` → `side_project`, goal kept
   (a cap is a limiter, not a contract).
3. `weekly_goal` set and `goal_type == target` → `day_job`:
   - the base term: `effective_from` = the project's earliest beat's
     date, or `created_at` if it has none; `custom`;
     `weekly_hours = weekly_goal`.
   - every `effective_from` override becomes a term on that date:
     `weekly_goal` → `custom` with those hours; `weekly_goal is None`
     → `custom` with `weekly_hours = 0` (no expectation from here;
     "sabbatical" reads the same way).
   - `week_of` overrides are one-week deviations, not contract
     changes. They are left on `goal_overrides` untouched and stop
     applying, because the week card for a day job reads the contract.
     Their count and weeks are logged so the user can be told.
   - `weekly_goal` is **cleared** on the project (the contract owns it
     now); `goal_overrides` is left as is.
   - no region, no opening balance. The UI's "complete your contract"
     nudge covers both.

Overrides are sorted by date and coalesced when consecutive terms have
the same hours. Log one line per migrated project with what it became.

**Tests** (`test_migration.py`): a target project with two
`effective_from` overrides (one to a new number, one to `None`) becomes
three terms in order; a cap project stays a side project; a project
with a `week_of` override only gets one term and the override is left in
place; re-running the migration changes nothing.

### Phase 3 — HTTP contract `[api]`

Added to `routers/projects.py` (contract belongs to the project) and a
new `routers/absences.py`.

| Route | Purpose |
|---|---|
| `POST/PUT /api/projects` | `kind` and `contract` on create/update; 422 from the validators |
| `PUT /api/projects/{id}/contract` | replace terms / region / opening balance / `ended_on` — same replace-whole-list shape as `goal-overrides` |
| `GET /api/projects/{id}/contract/week?week_of=` | `{expected, worked, remaining, balance, days: [{date, expected, worked, holiday?, absence?}]}` |
| `GET /api/projects/{id}/holidays?year=` | the region's holidays, for the calendar |
| `GET/POST/DELETE /api/projects/{id}/absences` | list by range, create (upsert on date), delete |
| `GET /api/meta/holiday-regions` | countries and subdivisions for the picker; cacheable, static |

`ProjectResponse` gains `kind` and `contract`. The `this_week` include
on `GET /api/projects` gains `contract_expected` / `contract_remaining`
/ `balance` for day-job projects so the index does not need N requests.

`DEVICE_ALLOWED_PREFIXES` is **not** widened — the companion reads
nothing new this iteration.

**Tests** (`test_api.py`): the envelope for an invalid term (422 with
`fields`); a week query on a project of the wrong kind is 409 with a
code; absences are scoped to the user (404, not 403, for someone else's
project); create-then-week-query round trip reflects the absence.

### Phase 4 — UI: form, contract, absences `[ui]`

FSD placement: `entities/project` gains the types, mappers, queries and
a `ContractTermsEditor`; `entities/absence` is new; the pages compose.

- **Project form / settings drawer**: a `kind` selector. Choosing
  `day_job` reveals the contract section: schedule type, full-time
  hours, percentage (or weekly hours for custom), region picker
  (country → subdivision), opening balance. Choosing `objective` hides
  the numbers and shows the personal goal instead. Time-based day jobs
  hide the personal goal field.
- **Contract history panel** on the project page, modelled on
  `OverrideManagementPanel`: a list of terms with dates, and a "Change
  contract from…" action that appends a term. Editing a past term is
  allowed (people fix dates); deleting the only term is not.
- **Absences**: a month grid on the project page with holidays
  pre-marked from `/holidays`, click a weekday to add vacation / sick /
  other, half-day toggle, click again to remove.
- **"Complete your contract"** nudge on migrated day jobs with no
  region: one line, dismisses when a region is set.

**Tests**: mappers (percentage × basis → hours, and back); the form's
show/hide rules per schedule type; nothing that restates the API.

### Phase 5 — UI: the week `[ui]`

The reason for all of the above.

- **Week card** on the day-job project page and on the index's
  `ProjectPulseList` entry: `expected · worked · remaining` for the
  current week, the days as a five-cell strip (holiday / absence /
  worked hours), and the running **balance** with its sign made
  unmistakable (+4.5 h over · −2.0 h owed).
- **Objective-based**: worked hours and the personal goal if set, no
  balance.
- **Week history**: `ProjectWeekHistory` reads expected from the
  contract for day jobs so past weeks show the term that applied then,
  not today's.
- `pnpm gen:types` after the API lands; the drift check is on pre-push.

### Phase 6 — Docs and gates

- `CLAUDE.md`: the routes table, the `holidays` dependency, the
  migration note ("a project without `kind` is migrated at startup").
- `DATA.md`: the new fields and the absences collection.
- `PRIVACY.md`: contract terms and absences are stored; the coach
  context does **not** send them (decide explicitly; if it later
  should, say so there).
- `docs/flutter-companion.md`: note that the companion is unaware of
  contracts.

---

## Follow-ups (not this iteration)

- **Monthly timesheet** — per month: expected, worked, holidays,
  absences, balance; CSV. Swiss and German employers must keep this,
  and it is what you hand HR in a dispute.
- **Vacation entitlement** — days per year, pro-rated by percentage
  and by a mid-year start, carry-over, remaining. Needs the absence
  types to mean something, which they already do.
- **Balance ledger** — dated manual adjustments (payout, annual reset,
  cap) instead of editing the opening balance.
- **Companion week card** — the same numbers in the tray; widens
  `DEVICE_ALLOWED_PREFIXES` to `/api/projects/*/contract/week`.
- **Employer-specific holidays** — per-contract add/remove on top of
  the region (Dec 24/31, bridge days).
- **Coach awareness** — the brief knowing you are 6 h over and it is
  Thursday. A privacy decision as much as a feature.

## Open

- Whether `hours_per_day` should be configurable for contracts on a
  4-day full-time week (some Belgian and Dutch employers). Decision 3
  says no; revisit if a user asks.
- Whether the index shows the balance or only the week. Start with the
  week; the balance is one tap away on the project.
