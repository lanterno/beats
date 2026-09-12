# The Project Page, and the Afternoon — Roadmap

> The project page answers one question in its first screen. For a day
> job: *where do I stand with my employer as of today, and what does that
> make of the rest of this week?* For a side project or freelance work:
> *am I on the pace I set myself, and where did the hours go?* Everything
> under that screen is the evidence, in the order a person would check it.
>
> And the whole app moves into a painted summer afternoon: a watercolour
> sky, green hills at the foot of the screen, the figures on cloud-white
> panels with no borders, two rounded typefaces, one accent the colour of
> sunlight. At dusk the same hill under an indigo sky.

The mockup that this roadmap implements is the artifact
<https://claude.ai/code/artifact/46cd0657-df15-434b-8124-15cb3ab43a2f>
(version 3, "Sky and meadow"). Its structure came from a design panel
(three concepts, three judges) and its look from a second one, both
recorded in the session that produced it. The decisions below were then
confirmed by the owner on 2026-09-12 and are not to be re-litigated.
Anything marked *open* is genuinely undecided.

---

## Status

| Phase | Commit |
|---|---|
| 1 — API: the ledger route and the balance proof | feat(api): the week ledger route and the balance proof |
| 2 — The afternoon: tokens, fonts, sky, panels, shell, settings | — |
| 3a — Project page: the standing, the days, the ledger | — |
| 3b — Project page: the register, time off, the drawer | — |
| 4 — Every other page on the new theme | — |
| 5 — The marketing page, docs, gates | — |

---

## Decisions

1. **Vocabulary.** *Expected · Worked · Remaining · Balance*, everywhere.
   The mockup's sentences may say "to go"; labels never do.
2. **The first governed week is muted, not red.** A day job whose contract
   started less than seven days ago shows its (large, negative) balance in
   the muted tone with the line *"First week under the contract. Each day
   is charged as it closes; the figure settles once a full week is in."*
3. **The Sunday projection stays.** Under the balance: *"By Sunday: +5.7 h
   if the week is met, +3.8 h if you stop now."* Both figures are client
   arithmetic over `/contract/week` (see *The arithmetic*), rounded with
   the same rule as the balance so signs never disagree.
4. **The Planned column is demoted** to an annotation on the open week
   ("Planned 28 h · 9 commits"). The weekly plan page is untouched.
5. **The health sparkline and the "Focus today" aggregate are cut.** The
   stale-project alert survives as one line in the standing with its
   Snooze; the per-session focus score survives as a small mark on today's
   session rows. The Avg / Longest / Sessions / Last-tracked tiles become
   one muted all-time line under the ledger and a "Last tracked" fact in
   the rail.
6. **Two hours replace five themes.** `afternoon` (light, the default) and
   `dusk` (dark). The theme axis keeps its attribute (`data-theme`) and
   storage key; the separate colour-mode axis goes; density stays. Any
   stored value that is not one of the two reads as `afternoon`.
7. **No boxes, no borders, no textures.** Surfaces are rounded panels
   (radius 1.5–1.875 rem) separated by air and shadow; controls are pills;
   highlights are washes; row separators inside a list are a hairline at
   ~9 % of the ink and nothing else. No grain, no stamps, no hand-drawn
   rules, no handwriting face, no mascots.
8. **Type.** M PLUS Rounded 1c (500 / 700 / 800) for the display figures
   and *every column of digits* — its numerals are one width, so nothing
   needs `tnum`. Zen Maru Gothic (400 / 500 / 700) for everything read.
   Real code (`pre`, `code`) keeps a monospace via a separate token.
9. **The accent is sunlight** (`#F2B233` by day, `#F5C55B` at dusk) and
   marks exactly three things: today, the running timer, and the primary
   action. Leaf green for hours over, persimmon for hours owed. Vacation,
   sick and holiday tints are sky, blossom and leaf.
10. **One time navigator.** The open week — set by ‹ ›, by clicking a
    ledger row, by a time-off entry, and by the URL (`?week=YYYY-MM-DD`).
    The absence month grid survives only as the date picker inside the
    booking dialog.
11. **One ledger route.** Every week figure on the page comes from
    `GET /api/projects/{id}/ledger`, bucketed by the request timezone and
    including the running timer, exactly as `/contract/week` already is.
    Nothing reconstructs a balance client-side. `GET …/week/` stays for
    now (nothing else reads it) and is removed in Phase 5.
12. **Every existing action survives**: colour, name, description, repo,
    kind, term add / edit / remove, absence record / change / remove,
    session edit / delete, goal overrides on weeks the contract does not
    govern, archive and restore. Some move: archive to the settings
    drawer's foot, restore also onto the *Archived* chip.
13. **The marketing page** (`/`, logged out, `HomePage.css`) gets the
    afternoon last, in Phase 5, as its own pass. The companion, daemon,
    VS Code extension and wall clock are untouched.

---

## The page (day job with a contract)

```
Header      dot · name · kind chip ("Day job · 80% of 42 h · CH-ZH") · description ·
            repo · [Archived · Restore] · gear.  No figures.  Sits on the sky.

Standing    the brightest panel.
  left      BALANCE · as of Thu Sep 10
            +10.5 h over                       (leaf / persimmon / muted)
            +2.0 h brought forward · +848.5 h worked since Jan 5 · −840.0 h expected through Wed
            By Sunday: +5.7 h if the week is met, +3.8 h if you stop now.
            [one notice line when it applies: quiet-project alert + Snooze 7d;
             "Public holidays are not deducted — set the holiday region" ]
  right     THIS WEEK · Sep 7 – 13 · W37   (a past week: "WEEK 35 · Aug 24 – 30")
            Expected 26.9 h   Worked 25.0 h ●   Remaining 1.9 h
            33.6 h nominal − Fri vacation 6.7 h          (only when they differ)
            "1.9 h to go, all today. Friday is off, then Mon 6.7 h."
            [Book time off]

Days        DAYS · Sep 7 – 13 · W37                                  ‹ ›  (Today)
            Mon 7   3 sessions                      7.1 of 6.7  +0.4  ›
            Thu 10  today  2 sessions · running     3.4 of 6.7        ⌄
                08:47 → 11:52  standup, PR reviews  #review ◦74     3h 05m
                13:10 → now    API pagination                    ● 0h 20m
            Fri 11  [Vacation · Zürich trip] Change     nothing expected
            Sat–Sun 12–13                              nothing expected
            Planned 28 h · 9 commits · Timer running since 13:10

Earlier     EARLIER WEEKS · newest first                      Copy as CSV
weeks       WEEK            ▇▇▇▇▇··   EXPECTED  WORKED   +/−   BALANCE
            W36 Aug 31–Sep 6          33.6      32.9    −0.7    +5.7
            W34 Aug 17–23  Tue sick ½ 30.2      29.4    −0.8    +4.9
            ( From Mon Aug 3, 2026 · Part time 80% of 42 h = 33.6 h/wk · was 60% · "note" )
            ·· 3 weeks away · Jul 6 – 26 · vacation ··
            Show 5 more weeks · 26 more back to the opening balance
            Since Mon Jan 5, 2026 · 840.0 h expected · 848.5 h worked · +8.5 h  ·  All time 1,284 h · 412 sessions

Rail        CONTRACT   Part time · 80% of 42 h / 33.6 h/week · since Mon Aug 3, 2026
                       Next → Full time · 42 h/week from Mon Jan 4, 2027
                       [step chart: hours/week over the contract's life; dashed after today]
                       From Jan 5, 2026 · Part time · 60% of 42 h · 25.2 h/wk
                       From Aug 3, 2026 · … · IN FORCE · "Four days a week from August"
                       From Jan 4, 2027 · … · PLANNED
                       [+ Change contract from…]
                       Holidays Switzerland · Zürich · Brought forward +2.0 h · Ended — · Edit
            TIME OFF   upcoming                                          + Book
                       Tomorrow · Fri Sep 11 · Vacation · Zürich trip          vacation
                       Mon Oct 5 – Fri Oct 9 · Vacation · 5 days               vacation
                       Fri Dec 25 · Christmas Day · public holiday · Zürich     holiday
                       2026: 21 d vacation booked · ½ d sick
            FACTS      Last tracked today 11:52 · Focus today 74
```

**Side project / freelance.** No balance: the left of the standing shows
the 4-week average ("6.8 h / week · Goal met 2 of the last 4 weeks") and
the line *"No contract on a side project — no balance, nothing owed. The
goal is yours."* The week runs against the personal goal (Goal · Worked ·
Remaining; a cap reads "Under cap"). Days show worked only. The ledger has
Goal instead of Expected and no Balance; the goal cell opens the override
popover; an overridden goal is italic, "No goal" when an override says so.
The rail's first panel is **Goal** (the goal in force, its dated history
as the same step chart when there are two or more steps, the override list
with remove, *Edit goal* → drawer). No Time off panel.

**States.** *No contract yet* (day job): the balance slot reads "No
contract yet. Add the terms and the page keeps a balance from that date."
with *Add contract*; time off is bookable and counts once a contract
exists. *Objective / 0-hour term*: no balance ("no balance while it
lasts"), no expectation, the personal goal if set; the register shows the
term as a labelled gap or a step at zero. *Before the first term*:
"Contract starts Mon Sep 14 · 33.6 h/week", worked only. *After
`ended_on`*: "Final balance +N h · ended Aug 31" with the proof frozen at
that date. *Missing region*: the register's constants line and the proof
carry the caveat; no banner. *Past week open*: the balance stays pinned to
today; the right half becomes "Week 35 · closed +1.5 h over", no sentence,
the day rows show that week. *Empty project*: the seven rows with their
expectations and "No sessions yet — start the timer in the sidebar."

---

## The arithmetic (client side, all from `/contract/week` and `/ledger`)

```
today, days[] from GET /contract/week (request tz; worked includes the running beat)
remaining        = expected − worked                       (null when expected is null)
stop_now         = balance − Σ expected(d) for d in today..Sunday
met              = stop_now + max(remaining, 0)            (= Monday morning's balance)
sentence:
  expected null                         → no sentence (side project: "3.2 h to go over Thu – Sun — about 50 min a day.")
  remaining ≤ 0                         → "The week is done — 0.4 h over."  /  "The week is met."
  no later day with expected > 0:
     today.expected > 0                 → "1.9 h to go, all today. Friday is off, then Mon 6.7 h."
     today.expected = 0 (weekend, off)  → "The week closes 1.9 h short."
  today.expected = 0, later days do     → "Nothing due today (Vacation). 6.7 h to go on Friday."
  N later days with expected > 0        → "12.3 h to go over Thu and Fri — about 6.2 h a day."
  "then Mon 6.7 h" names the next day with expected > 0 in the following week (one more /contract/week call)
first week       = today < contract.starts_on + 7 days      → muted tone + the first-week line
week label       = weeks_ago 0 → "This week"; else "Week NN"
```

Every branch has a unit test with one example. A branch that does not
match shows the figures and no sentence — never a guessed one.

---

## The ledger route (Phase 1)

`GET /api/projects/{id}/ledger?weeks=N&tz=…` — any kind of project,
newest week first, `weeks` 1–104 (default 8). One beats read, one absence
read, one holiday calendar over
`[min(contract.starts_on, first Monday), max(today, last Sunday)]`, then
`worked_by_local_day(beats, tz)` once.

```
{ "weeks": [ {
    "week_of": "2026-08-31",
    "worked": 32.9,                       // Σ days, request tz, running beat included
    "days": [6.9, 6.4, 6.7, 6.5, 6.4, 0, 0],   // Mon..Sun worked hours
    "effective_goal": 33.6, "effective_goal_type": "target", "effective_goal_overridden": false,
    "contract_expected": 33.6,            // adjusted; null when nothing time-based governs
    "balance_end": 5.7,                   // the balance at the close of Sunday: opening + worked − expected
                                          // through it, the Monday-morning figure; null for the current
                                          // week and whenever contract_expected is null (one rule for the
                                          // row); the frozen final balance after ended_on
    "notes": [ {"date":"2026-08-18","kind":"sick","half_day":true},
               {"date":"2026-05-25","kind":"holiday","name":"Whit Monday"} ]
  } ],
  "since": "2026-01-05",                  // contract.starts_on, or null
  "totals": {"expected": 840.0, "worked": 848.5, "balance": 10.5} | null }
```

`/contract/week` gains sibling fields, never a retyped `balance`:
`balance_as_of` (date), `balance_opening`, `balance_worked`,
`balance_expected_through` — null exactly when `balance` is null. The
projects index and every existing reader are unaffected.

`_week_breakdown_from_beats` (server-date, completed beats) is left as it
is; the UI stops calling `/week/` in Phase 3a and the route goes in
Phase 5 with its schema and tests.

---

## The theme (Phase 2)

Tokens keep their names so that every page follows on the day the block
lands; the values change. On `:root` (afternoon), redefined under
`:root[data-theme="dusk"]`:

| token | afternoon | dusk |
|---|---|---|
| `--background` | the sky's low haze `#E4F0F1` (the sky itself is a fixed layer) | `#2E3E6E` |
| `--card`, `--popover` | `#FFFDF7` at 93 % | `#243049` at 94 % |
| `--foreground` | `#2B3A44` | `#ECF1F6` |
| `--muted-foreground` | `#66737D` | `#A6B1BF` |
| `--secondary` (washes) | `rgb(114 176 214 / .16)` | `rgb(140 190 230 / .14)` |
| `--border` | `rgb(43 58 68 / .09)` | `rgb(236 241 246 / .10)` |
| `--accent` / `--primary` | `#F2B233`, foreground `#2B3A44` | `#F5C55B`, foreground `#2B3A44` |
| `--success` | `#3F8F55` | `#8AD6A0` |
| `--destructive` | `#D2683F` | `#F2A182` |
| `--radius` | `1.5rem` | same |
| sidebar family | the panel at 82 % and its ink | same, dusk values |

The `@theme` block maps the same `--color-*` names; `--shadow-soft` becomes
the panel shadow (`0 22px 48px -26px rgb(43 84 110 / .22)`), `--shadow-card`
the dialog's. `body::before` (the old glow) becomes the **sky**: a fixed
layer with the gradient, the sun, five drifting clouds and the three-hill
SVG — kept on a fixed pseudo-element / element, never
`background-attachment: fixed` on `body` (the iOS Safari note in
`global.css` stays true). Clouds drift over ~140 s and stop under
`prefers-reduced-motion`.

A `Panel` primitive (`shared/ui/panel.tsx`: `rounded-[1.625rem] bg-card
shadow-soft`) replaces the copy-pasted card string; `Button` variants
become pills; chips and tints are pills. `Dialog` keeps its bottom-sheet
on phones and becomes a rounded cloud on desktop. The shell (sidebar,
mobile header, timer, stats, project list, device status) is restyled as
the mockup's sidebar. Settings: the *Theme* section offers *Afternoon* and
*Dusk*; *Color Mode* goes; *Layout Density* stays. `index.html`'s
`theme-color` follows the theme. The 18 hard-coded Tailwind colours
(`text-amber-500` …) become tokens. `PROJECT_COLORS` are re-picked to sit
on the sky (softer, less neon; same count so hashing is stable).

---

## Phases

Each phase is one workflow (implement → three review lenses → fix →
gate), one commit, pushed to `main`; a push deploys. Tests follow *What to
test, and what not to* in `CLAUDE.md`: rules with interesting inputs, the
HTTP contract, bugs that happened. Not class names.

### Phase 1 — API: the ledger route and the balance proof `[api]`

- `ContractService.ledger(project_id, weeks, tz)` and a pure
  `domain/ledger.py` that assembles the weeks from one worked map, one
  absence list, one holiday calendar and the project (`effective_goal`
  per Monday, `week_expectation`, `balance` per boundary).
- Route, response models, `NOT_FOUND` on a foreign id, 422 on `weeks`
  out of range; the four sibling fields on `/contract/week`.
- Tests: assembly against fixed dates (a term change mid-run, a vacation
  week, a week before the first term, `ended_on`, an objective term, a
  side project); parity — `ledger.weeks[0].worked == contract/week.worked`
  for the same tz and a beat that crossed midnight; the HTTP contract.
- `pnpm gen:types`; CLAUDE.md routes table; this file's status.

**Notes** — what the phase settled that the text above left open:

- **The closing balance is the Monday-morning figure.** `balance(today =
  week_of + 7)` as written would count the following Monday's hours (today's
  work counts as soon as it happens) while charging only through Sunday, so
  the row-to-row proof — balance moves by worked − expected — failed on the
  first fixture. `closing_balances` reads the balance at the close of the
  week's Sunday: hours worked through it, hours expected through it.
- **After `ended_on` every row repeats the final balance**, and
  `contract_expected` is 0 there (owed nothing by circumstance; the term
  still governs). `balance_terms` freezes both sides on that day, so the
  frozen figure is what the closing balance is; a blank would have hidden
  the number the "Final balance" state shows. Hours tracked after the end
  appear in `worked` and move nothing.
- **`balance_end` and `contract_expected` share one null rule**: a week with
  no expectation has no closing balance. The first cut read the term in force
  on the week's Sunday, which gave a term starting on a Saturday a balance
  under a blank expectation, and a switch to an objective term mid-week the
  reverse (review). `week_expectation`'s weekday rule now decides both, so
  the two columns go blank together; a Saturday start leaves its week before
  the contract on both counts, and its weekend hours move the next close.
- **`totals` is None on the week route's rule for today's balance**
  (`owes(term_on(contract, today))`), so the standing and the ledger's foot
  go blank together.
- **The proof holds to the cent, not to the bit.** `balance` stays
  `round(opening + worked − expected, 2)` as before; the three terms are
  rounded on their own, so `opening + worked − expected_through` can differ
  from `balance` by up to 0.01. Tests assert `abs=0.01`. `balance_opening`
  is rounded like every other hour figure on the wire.
- **`notes` are weekdays only**, by date, a holiday before an absence on the
  same day; an absence carries `half_day` (always), a holiday `name`. The
  absence's free-text `note` is not carried — the rail's Time off panel
  reads the absence list for that.
- **The shapes are domain models** (`Ledger`, `LedgerWeek`, `LedgerNote`,
  `LedgerTotals`, `LedgerNoteKind` in `domain/models.py`) and the route's
  `response_model` is `Ledger`, as `/contract/week` returns `ContractWeek`;
  no `LedgerResponse` in `api/schemas.py`. `effective_goal_type` is always a
  `GoalType` (the `/week/` breakdown could report null).
- **`week_expectation`, `owes` and `round_hours` moved from `services.py` to
  `contracts.py`** (`_owes` and `_hours` lost their underscores), and
  `_has_override_for_week` became `Project.goal_overridden`: `ledger.py`
  needs all four and `services.py` imports `ledger.py`, so they could not
  stay where they were without a cycle. `balance()` is a thin wrapper over
  `balance_terms()`.
- **`weeks` is validated by the route** (`Query(ge=1, le=104)`, default 8):
  a 422 naming `weeks` in `fields`. `ContractService.ledger` reads
  `[min(contract.starts_on, first Monday), max(today, last Sunday)]` as
  written, though today is never past the last Sunday.
- **`DEVICE_ALLOWED_PREFIXES` is unchanged**: `/api/projects` is in it, so a
  paired device can read the ledger, as it can already read the week.
- **The four `/contract/week` fields are pinned in `TestContractWeekAPI`**
  (the route's own class), the ledger's HTTP contract in `TestLedgerAPI`,
  the service's read plan and the midnight parity in
  `test_domain.py::TestContractServiceLedger`, the assembly on fixed dates in
  `test_ledger.py`.
- **The four `/contract/week` proof fields are required-nullable, like
  `balance`** (review): declared with `= None` defaults they left
  `ContractWeek.required`, and the generated type said `balance_as_of?:` —
  may be absent — when the server never omits them.
- **Closing balances come from one pass** (review): `closing_balances` in
  `contracts.py` reads every Sunday's close off a running total over the
  same per-day rule (`_daily`) that `balance_terms` sums, instead of
  re-summing the contract's life per row. 104 weeks of a five-year contract
  went from 0.32 s to 0.01 s; 400 random fixtures agree with the per-row
  formula to the bit, so the proof is still one rule in one place.
- **`ContractService` takes its clock** (`now`, default `datetime.now`)
  (review): today in the request timezone decides which week is open and
  which day the balance is as of, and no test could pin it against the wall
  clock. The service tests run at a fixed instant — Sunday 23:30 UTC is
  Monday in Zürich, on both routes.
- **`worked` and the balance's move differ on the week a contract starts or
  ends mid-week** (review): the row shows every hour logged, the balance
  counts only those from the first day through `ended_on`. Documented in
  `ledger.py` and pinned by a Wednesday start and a Wednesday end; the page
  should derive the +/− cell from two closes when it has both, not from
  worked − expected.
- **The fixtures the reviews' mutants got past** now exist: hours on a
  Sunday (the close's Sunday edge), a term starting on a Wednesday and on a
  Saturday, `ended_on` on a Wednesday, absences through the service's read
  window at both ends, and the row identity on the wire. The 422 test keeps
  one out-of-range case rather than restating `ge=1, le=104` twice.

### Phase 2 — The afternoon `[ui]`

- `global.css` rewritten: fonts, the two token blocks, `@theme`, the sky
  layer, base styles; `useTheme.ts` to two themes with the storage
  migration; Settings sections; `useTheme.test.ts`; `settings.spec.ts`.
- `Panel` primitive; `Button`, `Dialog`, `CommandPalette`, `Tooltip`,
  `ColorPicker`, `Progress` restyled; the shell restyled; `SyncStatus` and
  the other colour escapes on tokens; `PROJECT_COLORS`; `theme-color`.
- No page other than the shell is touched here; they follow the tokens.
- Gate: every page opens and reads on both hours (a live-browser lens
  walks the dashboard, projects, project, insights, plan, coach,
  settings at 1360 and 400 px).

### Phase 3a — Project page: the standing, the days, the ledger `[ui]`

- `entities/project`: `useProjectLedger(projectId, weeks)` on the new
  route, `useProjectWeeks` deleted; `ContractWeek` gains the proof
  fields; `model/standing.ts` (the sentence, the projection, the first
  week, the week label) with a test per branch; `model/ledger.ts` (rule
  rows from terms, quiet-week collapse, CSV) with tests.
- `entities/session`: a `useRunningBeat()` over the timer status query so
  today's rows can show "→ now"; day grouping by local *start* date
  generalised from `calculateDailySummary` (one rule, one test).
- Page: `ProjectHeader`, `Standing`, `WeekDays` (with the navigator and
  `?week=`), `WeekLedger`; the old `ContractWeekCard`, `ProjectWeekHistory`,
  `ProjectSessionList`, `ProjectStats`, `ProjectHealthRail`, `ContractNudge`
  deleted with their tests; `GoalOverridePopover` kept for the ledger's
  goal cells. `ProjectDetails.test.tsx` rewritten for the new regions.
- E2E: `contracts.spec.ts` asserts the new regions ("Where you stand",
  "Days", "Earlier weeks"); `projects.spec.ts` / `app.spec.ts` lose the
  stale "This Week" text.

### Phase 3b — Project page: the register, time off, the drawer `[ui]`

- `ContractRegister` (in force, next, the step chart as an SVG from
  `contract.terms`, the term list with the existing dialog, constants +
  Edit → drawer; the *Goal* variant with the override list); `TimeOff`
  (upcoming absences and holidays merged, the year tally, `AbsenceDialog`
  with *from / through* fanning out one PUT per weekday and the month grid
  as its picker); `QuietFacts`.
- Settings drawer: archive / restore at its foot with the existing copy
  and confirm; the *Archived* chip's inline Restore; the override list
  leaves the drawer for the Goal register; a kind change away from day
  job says before save that the contract will no longer govern the page.
- `ContractHistoryPanel`, `AbsenceCalendar`, `OverrideManagementPanel`,
  `ProjectDangerZone` deleted with their tests, their behaviour re-pinned
  where it moved (term add / remove; absence record / remove; archive
  navigates away; restore).
- E2E: the vacation flow in `contracts.spec.ts` through the new dialog.

### Phase 4 — Every other page on the new theme `[ui]`

- The dashboard (`pages/index`), the projects index, insights (21
  files), plan, coach, settings: the card string → `Panel`; borders →
  none or the hairline; buttons and chips → pills; the `NewProjectDialog`
  and `CoachMemoryDialog` onto the `Dialog` primitive; charts' colours on
  tokens. Layout and behaviour unchanged.
- Gate: the same live-browser walk as Phase 2, both hours, both widths;
  the full Playwright suite.

### Phase 5 — The marketing page, docs, gates

- `HomePage.css` onto the afternoon (its own pass; it already reads the
  tokens, the three hard-coded hexes and its hero go).
- `GET …/week/` removed with `WeekBreakdownResponse`, its tests and
  `fetchProjectWeek`; `gen:types`.
- Docs: `CLAUDE.md` (routes, the Contracts bullet, the theme bullet,
  counts), `ui/CLAUDE.md`, `README.md` (features: "two hours" not "five
  dark themes"), `ARCHITECTURE.md`, `docs/work-contracts-roadmap.md`
  (the follow-ups that this closes: the balance ledger read side), the
  status table above.

---

## Follow-ups (not this iteration)

- **Balance adjustments** (payouts, annual resets) — the write side of
  the ledger; the route above is read-only.
- **Vacation entitlement** — the tally counts recorded days only; "of N"
  needs entitlement, pro-rating and carry-over.
- **Focus scores over a range** — the per-session mark is today-only
  because the endpoint takes one date.
- **Companion week card** — unchanged; see `work-contracts-roadmap.md`.

## Open

- Whether `sunset`'s users (if any) should get a third hour. Two ship.
