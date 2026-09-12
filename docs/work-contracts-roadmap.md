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

**Phases 1 and 2 deploy together.** From Phase 1 on the repository
writes the model's default `kind` (`side_project`) on every save, so a
target project saved under Phase 1 alone would look migrated to this
pass and keep its goal with no contract. The `PUT /api/projects` route
must carry `kind` and `contract` from the stored project, as it already
carries `goal_overrides`, or the first ordinary edit undoes the pass.

Rules, applied per project:

1. No `weekly_goal`, or one that is zero or negative → `side_project`.
2. `weekly_goal` set and `goal_type == cap` → `side_project`, goal kept
   (a cap is a limiter, not a contract).
3. `weekly_goal` set and `goal_type == target` → `day_job`:
   - the base term: `effective_from` = the date of the project's
     earliest beat, running or not, or — `Project` has no `created_at`
     — the ObjectId's date if it has none; `custom`;
     `weekly_hours = weekly_goal`.
   - every `effective_from` override becomes a term on that date:
     `weekly_goal` → `custom` with those hours; `weekly_goal is None`
     → `custom` with `weekly_hours = 0` (no expectation from here;
     "sabbatical" reads the same way). An override dated on or before
     the base date was already in force then, so it *replaces* the base
     term's hours instead of adding a term — the latest such override
     wins, as it did under `effective_goal` — and the project's own
     `weekly_goal` appears in no term, having applied only to weeks
     before the first beat. An override typed `cap` becomes a term at
     its hours all the same; its date is logged, since a limit has
     become an obligation.
   - `week_of` overrides are one-week deviations, not contract
     changes. They are left on `goal_overrides` untouched; the contract
     does not know them. Their weeks are logged so the user can be told.
   - `weekly_goal` and `goal_overrides` are **left as they are**. Nothing
     reads the contract until Phases 3 and 5, and a push deploys, so
     clearing the goal here would blank the week card, the score, the
     coach and the patterns for every day job until then. Leaving it
     also makes the pass additive: a rollback, or the old revision still
     serving during a Cloud Run rollout, shows the goal it always did,
     and a document it rewrites without `kind` is migrated again to the
     same contract. Clearing the personal goal on day jobs is Phase 5's,
     once the week card reads the contract.
   - no region, no opening balance. The UI's "complete your contract"
     nudge covers both.

Overrides are sorted by date and coalesced when consecutive terms have
the same hours. Log one line per migrated project — id only, no name —
with what it became. A document the pass cannot read is logged, left
without a `kind` so the next boot retries, and does not stop startup.

**Tests** (`test_migration.py`): a target project with two
`effective_from` overrides (one to a new number, one to `None`) becomes
three terms in order; a cap project stays a side project; a project
with a `week_of` override only gets one term and the override is left in
place; re-running the migration changes nothing; a document the pass
cannot read is skipped and the rest migrated; and, Monday by Monday from
the first beat, `term_on` says what `effective_goal` said — Decision 10
as an assertion. `test_api.py`: a PUT that does not mention `kind` or
`contract` keeps both (in `TestContractAPI`, since Phase 3 put them on the
wire).

### Phase 3 — HTTP contract `[api]`

The contract routes live in `routers/projects.py` (the contract belongs to
the project), absences in `routers/absences.py` under the same
`/api/projects/{id}` prefix, and the region list in a new `routers/meta.py`.
`ContractService` in `domain/services.py` holds the week and balance
assembly behind three narrow ports — `ProjectReader` (new, one read),
`ProjectBeatReader`, `AbsenceStore` — and `ProjectService.replace_contract`
is the one contract write, since it is a project write with the region
check. Routers stay thin: the index's per-project loop and its skip policy
are `ContractService.weeks_for`, and `holidays` and `list_absences` own
their `tz` defaults as `week` does, so each is testable with a fake.

| Route | Purpose |
|---|---|
| `POST/PUT /api/projects` | `kind` and `contract` on create/update; 422 from the validators, at the term's path (`contract.terms.0`) |
| `PUT /api/projects/{id}/contract` | replace terms / region / opening balance / `ended_on` as one object — whole, like `goal-overrides`; `kind` untouched |
| `GET /api/projects/{id}/contract/week?week_of=` | `{week_of, expected, worked, remaining, balance, days: [{date, expected, worked, holiday, absence}]}` |
| `GET /api/projects/{id}/holidays?year=` | the region's holidays as `[{date, name}]`; `[]` without a region; `year` in 1..9999 |
| `GET/POST/DELETE /api/projects/{id}/absences` | list by range, create (upsert on date, 201), delete (204) |
| `GET /api/meta/holiday-regions` | `[{code, name, subdivisions: [{code, name}]}]`; `Cache-Control: public, max-age=86400`; behind the normal auth |

Decisions made while building it:

- **Omitted is not null on `PUT /api/projects`.** The update is a wholesale
  replace and older clients do not send `kind` or `contract`, so the route
  reads `model_fields_set`: a field left out keeps the stored value,
  `contract: null` clears it. `kind` has no empty state, so a null there
  reads as left out. The request and response carry the domain `Contract`
  model itself rather than a mirror — its validators are what produce the
  422, and a copy would drift.
- **A contract lives only on a day job.** `POST`/`PUT /api/projects` refuse
  a contract sent with any other kind — 409 `NOT_A_DAY_JOB`, as
  `PUT /{id}/contract` already answers — and a `PUT` that moves a day job
  to another kind without mentioning `contract` clears it: the kind change
  is what was asked for, and the contract goes with it. Nothing dormant is
  kept for an undo; the alternative was a contract stored on a project no
  route could read it from, and region-checked on every save all the same.
  The check is `ProjectService`'s, beside the region check.
- **Every non-2xx is in the envelope.** A malformed project id is a 404
  like an unknown one — `MongoProjectRepository.get_by_id` reads `InvalidId`
  as not found, which also fixes the older routes on the same path — and a
  `year` outside 1..9999 or a `week_of` whose seven days run past the end of
  the calendar is a 422 naming the parameter. On `PUT /{id}/contract` a
  model-level validator — terms out of order, no terms, `ended_on` before
  the first term — comes back with an empty `path` in `fields`: the body
  *is* the contract, and an empty path is the body as a whole. The same
  error through `POST /api/projects` is at `contract`.
- **Wrong kind is a 409**, not a 400: `NOT_A_DAY_JOB` on the contract,
  week, holidays and absence routes; `NO_CONTRACT` for the week of a day
  job that has none yet. Both are `DomainException`s with a `code`, and
  `UnknownHolidayRegion` now carries `UNKNOWN_HOLIDAY_REGION` (400).
- **The week's `expected` and `remaining` are null**, and `days` carry
  `expected: 0`, when no weekday of the week has a time-based term in force
  — an objective term, or a week before the contract. That is distinct from
  0, which is a week the contract owed nothing by circumstance (holidays,
  after `ended_on`). `balance` is null on the same rule for today. Hours
  are rounded to two decimals on the wire; `remaining` goes negative once
  the week is over.
- **Worked hours are bucketed by the local date each beat started on**, in
  the request timezone (`tz`, default UTC): a beat crossing midnight
  belongs whole to the day it began. A running timer counts up to now.
  `balance` uses every beat on the project since the contract started, not
  the week's.
- **`week_of` must be a Monday** (422 naming the field, via a query-param
  validator); it defaults to the current week in `tz`.
- **Holidays come with names.** `domain/holidays.py`'s
  `named_holidays_between` replaces `holidays_between` — a caller that
  wants only the dates takes the keys — with a per-`(region, year)` cache — the balance rebuilds every year since the
  contract started on each request, and some regions cost ~10 ms a year. A
  stored region the library has stopped knowing (a library upgrade) raises
  `UnknownHolidayRegion`: the week route reports it, the project index
  logs it and leaves that project's contract fields null.
- **Absences**: `GET` defaults each bound on its own to the current
  calendar year in `tz`. `POST` answers 201 even when it replaced an
  absence on that date, and is accepted on a day job that has no contract
  yet — leave first, contract later; only the week needs one, hence
  `NO_CONTRACT` there alone. `DELETE` is by id within the project in the
  path (and the user), so its 404 means "not on this project". Someone
  else's project is a 404 on every route, never a 403.
- **`this_week` on `GET /api/projects`** gains `contract_expected`,
  `contract_worked`, `contract_remaining`, `balance` — what the week route
  reports for the current week, so a card can show expected · worked ·
  remaining from the index alone. Null on anything that is not a day job
  with a contract, and all but `contract_worked` null under an objective
  term. `contract_worked` is carried although `weekly_minutes` sits beside
  it because the two are different figures: `weekly_minutes` is the
  personal goal's — completed beats only, by UTC date — and is left as it
  was, since the current UI reads it. Beats stay one query; each day job
  with a contract costs one absence read and one calendar build, and other
  projects cost nothing.

**`DEVICE_ALLOWED_PREFIXES` is unchanged**, but `/api/projects` was
already in it, and the middleware matches by prefix: a paired device can
therefore reach every new route under `/api/projects/{id}/…` — the
contract, its week, holidays and absences. That is acceptable because a
device could already `PUT /api/projects` and rewrite the whole project,
contract included, so nothing new is exposed that was not reachable by a
longer road. `/api/meta` is not in the tuple and stays session-only. The
follow-up about widening the tuple for the companion's week card is moot:
the route is reachable today.

**Types**: the UI's generated API types (`ui/client/shared/api/openapi.json`,
`generated.ts`) are stale from this phase until Phase 4 runs
`pnpm gen:types`; the `ui-api-types` pre-push gate runs unconditionally.

**Tests** (`test_api.py`, four classes beside the project tests): the
envelope for an invalid term (422 with `fields`); a malformed project id as
a 404 in the envelope; a week query on a project of the wrong kind and on a
day job without a contract, each 409 with its code; absences scoped to the
user (404, not 403, for someone else's project, and no reach into another
user's absence by id) and a delete scoped to the project in the path;
create-then-week round trip reflecting the absence and its replacement by
a half day; `PUT` without `contract` keeping it, with `contract: null`
clearing it, and with another `kind` taking it away; a contract sent with
another kind refused; a percentage change mid-week in `days`; `week_of` off
a Monday; holidays without a region; the first named weekday holiday *after
the contract starts* zeroing its day and the week's total (an earlier one
would be zero for want of a term, and the holiday rule would go
unexercised); the objective term's nulls; a running timer's minutes in
`worked`; a beat across midnight landing on its local start day; the
`this_week` fields on a day job adding up and null on the others; the
region list's shape and that it is `public`ly cacheable (the TTL is
configuration and not restated). In `test_domain.py`, `weeks_for` with a
fake holding a region the library rejects — unreachable over HTTP, since
the region check keeps one from being written — skipping that project
alone. No test of which days a region observes, and none restating a
default.

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
- **Clear the personal goal on day jobs** `[api]`. Phase 2 left
  `weekly_goal` in place because nothing read the contract yet. Once the
  week card does, a second startup pass unsets it on every `day_job`
  with a contract, and the API-side readers (`scoring`, `patterns`, the
  coach context) take the contract's hours instead.
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
- **Companion week card** — the same numbers in the tray. The route is
  already device-reachable through the `/api/projects` prefix (see Phase
  3); what is missing is the companion reading it.
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
