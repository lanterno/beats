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

The copy of record is [docs/project-page-mockup.html](project-page-mockup.html),
checked in beside this file; the artifact link is a convenience.

---

## Status

| Phase | Commit |
|---|---|
| 1 — API: the ledger route and the balance proof | `59bb011` the week ledger route and the balance proof |
| 2 — The afternoon: tokens, fonts, sky, panels, shell, settings | `cf090e1` the afternoon and the dusk |
| 3a — Project page: the standing, the days, the ledger | `8e77327` the standing, the days and the ledger |
| 3b — Project page: the register, time off, the drawer | feat(ui): the register, time off and the drawer |
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

**Notes** — what the phase settled that the text above left open:

- **The raw accent is never text.** Every `text-accent` outside the
  marketing page became `text-accent-ink` (~130 sites, the pages included,
  not the shell alone): the gate is "every page reads on both hours", and
  the token swap had left the pages' links, chips and figures at 1.6–1.8:1
  by day. Fills and borders keep the accent; at dusk the two tokens are one
  colour, so nothing there moved. `HomePage.css` waits for Phase 5.
- **Settings' selected option is the mockup's `.seg`**: the accent as a
  fill with ink on it, `aria-pressed`, no border; unselected the wash. The
  swatch dot is each hour's sky, not its accent — the accent dot vanished
  on the accent fill, and the sky is what differs between the two.
- **Focus mode lost its hard-coded ember gradient** (it painted
  `hsl(38 20% 12%)` under accent digits whatever the hour). Now the haze at
  85 % with a blur over the sky, the figure in ink at heading weight like
  the sidebar's elapsed. Verified by class, not on screen — it needs a
  running timer, which writes a session.
- **Two veils the escape grep could not see** — `bg-black` under
  `CoachMemoryDialog` and `AuthModal` — are `bg-veil`.
- **`--muted` is a sky-grey (`203 35% 85%`), not the mockup's neutral
  #EEEBE2**: at 1.15:1 on the panel a goal ring at 0 % and every bar track
  vanished. `--muted-foreground` is one step darker than the mockup's ink-2
  (`206 10% 40%`) because page subtitles sit on the bare sky until Phase 4;
  ~3:1 on the sky's top, ~5.7:1 on a panel.
- **The radius scale is explicit and monotonic** on the mockup's stops (sm
  10, md 12, lg 16, xl 18, 2xl 22, 3xl = `--radius`, 4xl 28 px) instead of
  `--radius` ± 2 px, which had put `rounded-sm` (20 px) above `rounded-xl`
  (12 px). The unrestyled `rounded-md` controls are 12 px — the mockup's
  input — rather than 22; the timer's custom-time field uses it.
- **`Button` is the mockup's `.btn`**: the heavier wash (28 %, the token
  the sidebar's active row also uses — reused on purpose, no new name) at
  14 px / 700 for `secondary` and `outline`, so a button reads heavier than
  a chip on the lighter wash.
- **The idle timer's Start is the wash** (`.timer.idle .btn`); the accent
  pill in the sidebar is the running state alone.
- **`Progress` fills in leaf, not sunlight** (`bg-success/70`): the accent
  stays with today, the running timer and the primary action.
- **Code is `font-code`** at the four settings sites (`CodeBlock`, the API
  base URL, webhook URLs, the pairing code), since `font-mono` now means
  the rounded figures face.
- **`index.html` stamps the stored hour and density before first paint**,
  so a stored dusk no longer flashes the afternoon. The two storage keys and
  the dusk sky's hex are repeated there; `useTheme.ts` owns them, and its
  `THEMES` table carries each hour's `sky` for the meta and the swatch.
- **The useTheme test asserts that `theme-color` moves with the hour and
  returns**, not which hex — the old assertion restated a token value.
- **Insights' header wraps at 400 px** (`flex-wrap`, `shrink-0
  whitespace-nowrap` on the heading and its two chips), and those chips are
  the mockup's `.hdr .chip` — the panel with ink on it — because on the
  sky a 10 px accent-ink link was still under 3:1. The rest of the page is
  Phase 4's.
- **Nothing moves under reduced motion**: every animation and transition
  collapses to its end state (`0.01ms !important`, the inline
  `fadeSlideIn`/`sparkGrow` included); the clouds' `animation: none` stays.
- **Bare triples in `WeeklyCard` and `YearInReview`** (`var(--accent)`
  where a colour is required, so the declaration was dropped) are
  `hsl(var(--accent))`; the busiest-month and day bars paint again.
- **The mobile hamburger has a name** (`Open menu`, `aria-expanded`), and
  the colour picker's default is `assignColor(project.id)`, not the
  retired amber.
- **Declined**: `apple-mobile-web-app-status-bar-style` stays
  `black-translucent` — `default` would draw a system-coloured bar over an
  indigo page at dusk, and neither can be checked here; a Phase 5 question
  beside the PWA manifest.

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

**Notes** — what the entity half settled that the text above left open:

- **The ledger's nulls stay null on the model.** `LedgerWeek.effectiveGoal`,
  `contractExpected`, `balanceEnd`, `Ledger.since` and `totals` are `null`,
  unlike `ContractWeek`, whose wire nulls become undefined: on the ledger
  each null is a figure in its own right ("no goal", "no expectation", "no
  close") and the rules in `model/ledger.ts` test for it by name.
- **The four proof fields are required-nullable in `ContractWeekSchema`**,
  as `balance` is (Phase 1's review); on the model they are `balanceAsOf?`,
  `balanceOpening?`, `balanceWorked?`, `balanceExpectedThrough?`, undefined
  exactly when `balance` is.
- **`useProjectLedger(projectId, weeks = 8)`** is keyed
  `[...projectKeys.ledger(id), weeks]`, fresh for 30 s, enabled with an id.
  The absence hook invalidates `projectKeys.ledger(id)` beside
  `contractWeeks`; every other write already goes through `projectKeys.all`.
  `QuickLog` invalidates only `sessionKeys.all` after posting a beat — a gap
  the week card had before and the ledger inherits, left as it was.
- **`useProjectWeeks`, `fetchProjectWeek`, `WeekHours` and
  `WeekBreakdownSchema` are still in the tree**: `ProjectDetails.tsx` reads
  them and `ProjectDetails.test.tsx` mocks them with rows it asserts on, so
  deleting them before the page is rewritten would have broken either `tsc`
  or three page tests. They go with the page: `projectApi.ts`
  (`WeekBreakdownResult`, `fetchProjectWeek`), `queries.ts` (`useProjectWeeks`,
  `projectKeys.week`, `projectKeys.weeks`), `model/types.ts` (`WeekHours`,
  `DailySummary` — also dead), the three project barrels,
  `shared/api/schemas.ts` (`WeekBreakdownSchema`, `WeekBreakdown`) and its
  barrel, the `fetchProjectWeek` mock in `queries.test.tsx`, and the
  `projectKeys.weeks` line in the absence hook.
- **A term's rule row sits under the week its date falls in** — newest
  first: the week, then the rule, then the older weeks — as the mockup lays
  it out, so reading down everything above the rule is under the new terms.
  The closing rule sits above the week the contract ended in. A rule dated
  in the current week or later sits at the top of the list, `planned` when
  after today (the ghost). A rule older than the oldest week shown is not
  shown; the page's "26 more back to the opening balance" covers it.
- **The opening rule is the first term's**: "Contract starts Mon Jan 5,
  2026 · Part time 60% of 42 h = 25.2 h/wk" over "brought forward +2.0 h"
  ("nothing brought forward" at 0). A later term reads "From Wed Aug 5,
  2026 · …" — the weekday is always named, so a mid-week date says which —
  over "was 60% · 25.2 h · “the note”". The closing rule: "Ended Wed Aug 26,
  2026 · final balance +5.7 h" (`totals.balance`, else that week's close);
  "Ends … · planned" while still to come.
- **The +/− cell** (`LedgerWeekRow.delta`) is the move between two closes
  when the row and the one before both have one — Phase 1's note on the
  week a contract starts or ends mid-week; else worked − expected; else
  worked − goal (a side project); null with none. Rounded to 0.01.
- **A quiet run breaks at a rule row.** "n weeks away · Jul 6 – 26 ·
  vacation" needs at least one note and every note a vacation; anything
  else is "n quiet weeks". A side project's empty weeks fold too (its
  expectation is null).
- **`ledgerCsv`** writes the week as its Monday's ISO date, a side project's
  goal in the expected column, a blank for every null, and a rule or quiet
  row as one escaped cell followed by four empty ones.
- **`isFirstWeek` is false before the contract starts** — that is the
  "Contract starts …" state — and true from `starts_on` for seven days.
- **`projection` is null when today is not in the week**: the balance is
  pinned to today, so only the current week projects; the page passes the
  current week's `/contract/week` whatever week is open. Its two figures are
  rounded to 0.01 like the API's and formatted with `formatSignedHours`, so
  the sign is the balance's.
- **`nominalLine` names a holiday by name and an absence by type**
  ("Fri vacation 6.7 h", "Tue sick 3.4 h", "Fri Swiss National Day 6.7 h"),
  weekdays only, and deducts what the day's expectation actually lost
  (`termHoursPerDay − day.expected`), so a half day and a holiday under an
  absence both come out right. Null when the difference has no day to name
  (a mid-week term change or start): the rule row says so there.
- **The sentence's branches, filled in**: "Nothing due today (…)" also leads
  the N-days sentence when today expects nothing and two or more days
  remain; three or more consecutive days read as a range ("Wed – Fri"), two
  as "Thu and Fri"; under an hour a day is "about 50 min a day" to the five
  minutes; the "then Mon 6.7 h" tail is the following week's first day with
  an expectation, "Then Mon 6.7 h." on its own when no day is off. The
  mockup's first-week overload line ("more than two days can hold …") is not
  a branch: the figures show and the N-days sentence says what they say.
- **A cap has no sentence.** The personal-goal path serves a day job under
  an objective term or before its first term as well as the other kinds,
  over the calendar days left. `weekSentence` takes a `StandingWeek`
  (`weekOf`, `worked`, optional `expected`, `remaining`, `days`): a
  `ContractWeek` on a day job, `{weekOf, worked}` off the ledger elsewhere.
- **`groupSessionsByLocalDay(sessions, mondayIso)`** lives in
  `entities/session/model`; `calculateDailySummary` is a wrapper over it for
  the sidebar. There is no `useRunningBeat()`: an entity cannot import the
  timer feature, so `timerStatusKey` and `fetchTimerStatus` are exported
  from `features/timer` for the page to subscribe with the timer's own key.
- **`addIsoDays` and `mondayOfIso`** joined `shared/lib/date.ts`;
  `getISOWeek` is now on its barrel.

**Notes** — what the page half settled that the text above left open:

- **The regions are named as the roadmap names them**: `Panel` with
  `role="region"` and `aria-label` "Where you stand", "Days", "Earlier
  weeks"; the rail keeps "Contract history" and "Absences" until 3b. The
  tests and the E2E specs find the page by those names, never by class.
- **The layout queries the content column, not the viewport**, as the
  mockup's `@container content` does: `@container/content` on the column
  under the header, the standing's two halves from 640 px, the day row's
  narrow grid under 560, the ledger's two-line grid under 640, the rail
  beside the main column from 860. Tailwind v4's named container variants
  (`@min-[640px]/content:`, `@max-[640px]/content:`) compile them — written
  out in full in the source, because Tailwind reads class names off the file
  text and a `${PHONE}:` template left the whole phone ledger uncompiled
  (found on the first 400 px screenshot).
- **The tints are tokens** (`--tint-vacation`, `-sick`, `-holiday`, `-other`,
  each with an `-ink`, mapped as `--color-tint-*`): the mockup's sky,
  blossom, leaf and neutral on both hours, used by the day rows, the ledger's
  day cells and the legend. Phase 2 had not needed them.
- **A day's figure is the API's, in this order**: `/contract/week`'s day on a
  day job with a contract, else the ledger's `days[i]`, else the sessions'
  sum plus the running beat. The sessions under it are grouped by the same
  local-start rule, so they add up to it; the live row's duration ticks
  every 30 s on the client while the figure beside it moves with the query
  (it can lag the live row by up to a refetch, never disagree with the
  standing). The delta ("+0.4") shows on days before today only.
- **Today keeps its own row on the weekend.** Saturday and Sunday fold into
  "Sat–Sun" only when both are empty and neither is today: the folded row
  cannot be open by default, and a "today" chip wrapping inside it was the
  first thing the screenshot showed.
- **A past week open** shows its figures on the right and "Week 35 · closed
  +1.5 h over" / "closed 0.7 h short" / "closed even" in the sentence's
  place, from the week's `remaining` on a governed week and worked − goal
  elsewhere; the balance stays as of today.
- **Remaining is never negative**: 0.0 h once the week is met, and the
  sentence carries the over ("The week is done — 0.5 h over."). Decision 1
  leaves no "Over" label to switch to. A cap's third figure is "Under cap".
- **After `ended_on`** the label reads "Final balance · ended Mon Aug 31,
  2026", the proof's third line "expected through" that day, no projection;
  the right half shows Worked alone. Before the first term the left reads
  "Contract starts Mon Sep 14, 2026 · 33.6 h/week" and the right Worked
  alone; under an objective or 0 h term "An objective term — no balance
  while it lasts." and the personal goal's figures if there is one.
- **The proof's second line names the contract's first day** ("worked since
  Mon Jun 29"); the third names the weekday alone while it is in the current
  week ("through Sat") and the date outside it. "0.0 h brought forward" where
  the chip would say "even".
- **The kind chip**: "Day job · 80% of 42 h · CH-ZH", "Day job · Full time ·
  42 h · CH-ZH", "Day job · 32 h/week", "Day job · objective", "Day job · no
  contract" (also before any term), "Day job · ended Aug 31, 2026"; "Side
  project · goal 8 h/week" / "· cap 8 h/week" / "Side project";
  "Freelance" likewise. `kindChip` is exported from `ProjectHeader.tsx`.
- **"Edit goal" shows whenever the contract is not time-based today**
  (`isTimeBasedOn`: every other kind, a day job without a contract, an
  objective term) and opens the drawer on the goal; "Book time off" whenever
  a day job has a contract and, like a day's "Change", scrolls to the
  Absences panel in the rail until 3b's dialog.
- **The four-week average** is over the ledger's last four closed weeks
  ("3-week average" while fewer are closed, "No weeks closed yet" at none);
  "Goal met N of the last M weeks" counts the weeks that had a goal, a cap
  met when kept.
- **The ledger stops at the opening balance**: weeks ending before `since`
  are dropped, so the opening rule is the last row and "N more back to the
  opening balance" is the count from `since`'s Monday to the oldest week
  shown; the button goes at 0 and at the API's 104. A side project shows
  "Show 5 more weeks" alone. Empty: "No earlier weeks — the contract started
  this week." or "No earlier weeks yet."
- **A run of days off reads as one range** in the row's why-line ("Mon Jul
  20 – Fri Jul 24 · vacation") — five notes on one line was too much;
  holidays and half days keep the entity's wording. "override" joins the line
  on an ungoverned week with one.
- **The ledger's cells carry no units** ("33.6", "+5.7"), the balance's zero
  is "0.0" in the muted ink (not "even"), and the day cells scale to the
  largest day among the rows shown, as the legend says.
- **The since line is worked − expected with the opening in brackets**:
  "Since Mon Jun 29, 2026 · 258.7 h expected · 255.3 h worked · −3.4 h
  (+2.0 h brought forward)", so it adds up to the standing's balance.
- **The goal cell's override** keeps `ProjectWeekHistory`'s save and remove
  (one-off on `weekOf`, permanent on `effectiveFrom`, the same toasts), now
  in `WeekLedger`; the popover is offered only where the contract governs
  neither the week nor its expectation (`contractGovernsWeek`, or a
  `contractExpected`).
- **Session times are the 24 h clock** ("13:10 → now"), as the mockup
  writes them, and durations "3h 05m"; `formatTime`'s 12 h form stays on the
  dashboard.
- **Restore sits on the Archived chip** (the existing unarchive mutation and
  toast); `ProjectDangerZone` stays at the page's foot until 3b moves
  archive into the drawer.
- **The `/week/` symbols are gone**: `useProjectWeeks`, `fetchProjectWeek`,
  `WeekBreakdownResult`, `WeekHours`, `DailySummary`, `WeekBreakdownSchema`
  and `WeekBreakdown`, `projectKeys.week` / `weeks`, the mock in
  `queries.test.tsx` and the absence hook's invalidation of it. Nothing in
  the UI calls `GET …/week/` any more; the route itself goes in Phase 5.
- **Not done here**: the folded weekend keeps "nothing expected" as its
  figure whatever the hours on it (the days are empty by definition); the
  `QuickLog` invalidation gap noted above stands.

**Notes** — what the review settled:

- **The contract's first close moves from the opening balance.**
  `weekDelta` gives the week holding `since` (or the week after, when a
  weekend start leaves that one without a close) close − opening, not
  worked − expected, which counts hours logged before the first day.
- **A governed past week's "closed" line is the ledger's +/−**, so the
  standing and the row agree; the week's `remaining` stands in only when
  the ledger has not reached the week. Remaining itself stays the week
  route's figure.
- **A week still to come gets its figures and no verdict**: no "closed"
  line, no sentence. › stays unbounded, since a time-off entry may open
  one.
- **`nominalLine` is null unless the named days add up to Expected**
  (within 0.05 h). A mid-week term change with a day off measures the day
  against the wrong per-day hours, and no line beats a wrong one.
- **A quiet week, where the contract does not govern, has no goal and no
  override.** A missed 8 h goal is a −8.0 row, and an overridden week keeps
  the cell its override is removed from.
- **While a beat runs on this project, the current week and the ledger
  poll every 60 s** (the live row's granularity). A past or next week does
  not, and a timer start invalidates nothing: nothing a project read returns
  has moved at that instant.
- **On a day job with a contract, the standing waits for `/contract/week`**:
  "…" while it loads, the API's message (`role="alert"`) on failure, never
  the personal goal. A side project's average is "…" or the ledger's error
  until the ledger answers.
- **A day row's toggle is a real `<button aria-expanded>` over the day's
  name**, stretched across the row with `::after`; "Change" is a sibling
  lifted above it. The button's name is the day alone ("Mon 7").
- **At phone width the day-off pill ellipsizes and "Change" keeps its
  width.** A session's edit and delete hide until hover only where
  `(hover: hover)`, so a phone shows them.
- **A contract's expectation cell has one decimal** ("0.0" on a week off);
  **a goal is written as entered** ("8" in the ledger, "8 h" in the
  standing), as the chip writes it.
- **Opening a week from a ledger row scrolls the Days panel into view**
  and marks that row (`aria-current`, the wash).
- **`QuickLog` invalidates `projectKeys.all`**, closing the gap noted
  above.
- **The dead exports went from the project and session barrels.** The
  `shared/api` barrel keeps every schema and its type, as it does for
  `ContractDaySchema`. `weekIso.ts` is deleted, and the page's column is a
  `<div>`, since the shell owns `<main>`.

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

**Notes** — what the phase settled that the text above left open:

- **The rail's first panel has three shapes.** *Contract* on a day job with a
  contract; the no-contract state ("No contract yet · Add contract") only on a
  day job with neither a contract nor a personal goal; *Goal* everywhere else — including a
  day job without a contract that has a goal, which adds a foot line "No
  contract yet · Add contract".
- **The in-force line reads by schedule type**: "Part time · 80% of 42 h",
  "Full time · 42 h", "Custom · 32 h", "Objective"; under it "33.6 h/week ·
  since Mon Aug 3, 2026" ("from" before the contract starts, "no weekly
  expectation" on an objective term). After `ended_on` the last term keeps the
  headline, no term is *In force*, there is no *Next*, and the constants say
  "Ended Aug 31, 2026" ("Ends …" while still to come). *Next* is the first term
  dated after today and not after the end: "Next → Full time · 42 h/week from
  Mon Jan 4, 2027".
- **The step chart is `stepChart.ts`**, pure geometry pinned by
  `stepChart.test.ts`; the panel only paints it. A term dated after today is
  dashed from its first day, the current term dashed after today; an objective
  term is a gap (no line, no risers, its label on the axis), a 0 h term a line
  on the axis. A step narrower than 40 of the 296 units keeps its line but not
  its label, and an axis date within 36 units of the one before is left out —
  the term list names both. The chart is capped at 26 rem, since under 860 px
  of content the rail stacks full width and the text scaled with it; its text
  carries a panel-coloured halo (`paint-order: stroke`) because the today line
  crossed "80% · 33.6 h" on the first screenshot. The aria-label names every
  step and "planned".
- **The terms list oldest first**, as the mockup draws it; edit and remove hide
  until the row is hovered or focused only where `(hover: hover)`. The
  missing-region state is two lines: the caveat in the owed tone with *Set
  region*, then "Brought forward … · Ended —" with *Edit*; both open the drawer
  on the region.
- **The Goal is the standing goal, not this week's.** The latest `effective_from`
  override on or before this Monday, else the project's goal; a one-week
  override is listed, not headlined. "since" walks back through the permanent
  overrides that set the same figure and type; with none in force it is the
  local day of the project's first session — the project carries no creation
  date on the wire — and the goal's first chart step starts there. *Next* is
  the first permanent override after this Monday.
- **The override list moved oldest first** (the drawer's panel was newest
  first) and still removes by identity (FF.6): a permanent override in force is
  *In force*, a later one *Planned*, a week override "W31 · Jul 27, 2026 · No
  goal that week · one-week override". **On a day job with a contract** the
  register lists stored overrides under "Goal overrides" too — they govern the
  weeks the contract does not — so their remove survived the drawer losing the
  panel.
- **Time off makes one absence read**, `[Jan 1, today + 365]`, for both the
  upcoming list and the year's tally; holidays for this year and next, weekdays
  from today. A run needs one type (not one note) and bridges weekends and
  public holidays — Thu Dec 24 to Mon Dec 28 over Christmas is one row; its note
  shows when every day shares it; days count in halves ("4½ days"); a single
  half day reads "Vacation ½". A holiday sorts before an absence on the same
  day. Six rows, then "Show all N"; "Nothing coming up." when empty. The tally
  lists vacation, sick, other with "booked" after the first, over every absence
  recorded in the calendar year. The region note shows without a region or
  without a contract.
- **A holiday row opens its week in Days** (Decision 10: a time-off entry moves
  the open week) — it has nothing to book; an absence row opens the dialog on
  the run: its days, its type, half day when every day is one, the shared note.
- **The dialog records with `POST …/absences`**, the API's upsert (there is no
  PUT), one weekday at a time; the first failure stops the run and keeps the
  dialog open with "2 of 5 days saved — …". Nothing is rolled back, and saving
  again is idempotent. Titled "Book time off", or "Change time off" when opened
  on a booked day.
- **Remove takes the whole range** when every bookable weekday in it is booked
  ("Remove 5 days"), not only a single day — otherwise a week of vacation could
  only be taken back a day at a time.
- **The grid**: weekends are not buttons; past days and holidays are (sick leave
  is recorded afterwards, and a range may start on a holiday); a holiday inside
  the selection keeps its tint, since it is skipped; each day's name carries the
  date, the holiday, the booking and "today", and `aria-pressed` marks the
  selection. Save waits for the range's holidays and absences, so a holiday
  cannot be booked by a race. More than 366 days is refused as a typo.
- **The cost line counts against what is booked.** Per weekday, the term's day
  (nothing before the first term, after `ended_on`, or under an objective term)
  times the new share less the share already booked, so a half day becoming a
  full one "drops by 3.4 h" and the reverse "rises by"; "stays as it is" at 0.
  "This week's …" / "Week 38's expectation … to 26.9 h" only when the range sits
  in one week with an expectation; across weeks "The expectation drops by
  13.4 h." A range of weekends and holidays says "Nothing to book: weekends and
  public holidays are skipped." with Save off.
- **Standing's "Book time off" starts on the first day after today with hours
  due** in this week's or next week's `/contract/week` (the page already reads
  both), else the next weekday — not today. Time off's *+ Book* starts there
  too.
- **A governed weekday row offers "Book time off"** when nothing is off on it,
  past days included: a text link from 560 px of content, a "+" under it, named
  "Book time off on Mon 7" either way; faded until the row is hovered where
  there is hover, shown on focus, and the next tab stop after the day's toggle.
  "Change" hands the dialog the day's absence as its starting fields.
- **The drawer's foot** is a section "Archive" ("Archived" once it is) under a
  hairline: the existing sentence, *Archive project*, an inline confirm
  ("Archive <name>?" · Archive project · Cancel) that closes the drawer and
  goes to `/app`, or *Restore project*. A restore from another tab clears the
  confirm.
- **The kind line does not say the terms stay stored** — they do not. A kind
  change clears the contract and nothing comes back with a return to day job
  (`test_changing_the_kind_takes_the_contract_with_it`), so the line reads
  "Changing the kind deletes the contract: its terms, region and opening balance
  are not kept." It shows only on a project with a contract, while another kind
  is chosen. `ProjectForm` grew `kindNotice(kind)`, rendered in an
  always-mounted `<output>` under the kind radios and joined to them by
  `aria-describedby`, so the change is announced.
- **`ContractNudge` was already gone** (3a); the four panels went with their
  tests.
- **An archived project's page opens.** `useProject` read only the active
  list, so `/project/<id>` of an archived project said "Project not found" —
  the header's Archived chip and the drawer's Restore could never be reached,
  and the projects index's Archived rows led to that page. It now looks in the
  archived list (cached, then fetched) before giving up; the page is its only
  caller.
- **Not done here**: a side project's header chip reads the project's own goal
  ("goal 5 h/week") while the Goal register reads the override in force (8 h) —
  `kindChip` is 3a's; the Days' day-off pill shrinks to "V…" at 400 px beside
  *Change* (3a's rule); the nominal line under Expected runs long with five days
  off; holiday names are the calendar's own language ("Weihnachten").
  `contracts.spec.ts` passed against the dev API, but on the headless shell
  already in the Playwright cache (build 1234): this Playwright wants 1243,
  and its download timed out from here.

**Notes** — what the review settled:

- **A booked day keeps its own note unless one is typed.** Opening a run whose
  days had different notes and saving a half day sent the empty field to every
  day and erased them. The field is written only once edited; untouched, a day
  on record keeps its note and a day not yet booked takes the field. Differing
  notes show as the placeholder "Different notes — typing replaces them".
- **The dialog does not close while a run is saving**: Cancel is off, and
  Escape, the overlay and × do nothing. Cancelled mid-save, the writes carried
  on and their close shut whichever booking was open next; the page's close
  also acts only on the booking that opened the dialog now.
- **A run of writes is one mutation**, `useRecordAbsences` /
  `useRemoveAbsences` (the per-day hooks went): in order, each write tried
  twice as the app's mutations are, the first that fails twice ending the run
  with `{ done, error }`, one invalidation when it is over. Per day, seven
  queries refetched under the dialog before the next write (35 GETs for five
  days) and the cost line moved mid-save.
- **Focus goes back to the opener, in the `Dialog` primitive.** Radix returns it
  only to a `Trigger`, which no dialog here renders, so every close (booking,
  term, settings) left focus on `<body>`. The opener is read while rendering the
  open, since a field inside autofocuses before Radix's scope looks. When a save
  has removed it, the caller's `returnFocus` stands in: the day row's booking
  control (`[data-booking]`, its new *Change* or *Book* again), Time off's
  *+ Book* for a booking opened from the rail or the standing, *+ Change
  contract from…* for a term. The archive confirm takes focus to its Cancel,
  and Cancel back to *Archive project*.
- **Remove shows whenever every bookable weekday in the range is on record** —
  vacuously on a holiday, so an absence stored on one before the region was
  set can be taken back; a Days row on a holiday that holds one keeps *Change*.
- **Small text in the owed tone is `--destructive-ink`**: `#A84924` by day
  (5.4:1 on the panel, where `#D2683F` is 3.4:1), `--destructive` itself at
  dusk (6.4:1). It carries the region caveat, the kind line, the form's errors
  and the page's alerts; `--destructive` stays on figures and fills. The small
  owed deltas in Days and the ledger are the same 3.4:1 and wait for Phase 4's
  sweep. In the grid, past weekdays and weekend numbers take the full muted ink
  (weekends lighter in weight rather than colour), and the dialog description
  lost its 70 %.
- **The day row's "+" is a 24 × 24 target** (WCAG 2.5.8) that does not grow the
  row: `h-6 -my-1.5`, `w-6` once the label hides, and the cell clips on x only
  so the box is not cut.
- **The register's no-contract state is one line**, like the Goal foot: the
  sentence stays in the balance slot, so it no longer shows twice on a screen.
  The region caveat ends at "Public holidays are not deducted." and *Set
  region* carries the action.
- **Time off gives a date outside this year its year** ("Fri Jan 1, 2027") and
  wraps its second line as the mockup does. A run's starting fields are built
  in `TimeOff` (half day only when every day is one, the note only when
  shared), so its test pins them.
- **The step in force keeps its label and its date when steps crowd.** A label
  within 40 units after it, or the axis date just before it, gives way instead;
  the today line no longer crosses an unlabelled step.
- **"+ Book" with nothing due in the two weeks read** skips weekdays already off
  or on a holiday, rather than opening *Book time off* on a booking.
- **Not changed:** the stepChart test that matches the meadow's path string
  stays, since the string is what `<path d>` paints and the helper has no other
  consumer; removing a term or an override with its own button (no dialog)
  still drops focus when the row goes.

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
