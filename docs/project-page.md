# The Project Page, and the Afternoon

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

This is the design record for the project page and the theme. Every part of
it has shipped; the plan it grew from, phase by phase, is in git history.

The mockup is the artifact
<https://claude.ai/code/artifact/46cd0657-df15-434b-8124-15cb3ab43a2f>
(version 3, "Sky and meadow"). Its structure came from a design panel
(three concepts, three judges) and its look from a second one, both
recorded in the session that produced it. The decisions below were then
confirmed by the owner on 2026-09-12 and are not to be re-litigated.

The copy of record is [docs/project-page-mockup.html](project-page-mockup.html),
checked in beside this file; the artifact link is a convenience.

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
5. **The health card is cut.** Its goal sparkline goes. Its stale-project
   alert survives as one line in the standing with its Snooze, and its
   "Focus today" average as a figure in the rail's quiet facts; the
   per-session focus score survives as a small mark on today's session
   rows. The Avg / Longest / Sessions / Last-tracked tiles become one muted
   all-time line under the ledger and a "Last tracked" fact in the rail.
6. **Two hours, and no other themes.** `afternoon` (light, the default) and
   `dusk` (dark), on `data-theme`. There is no separate colour mode and no
   third hour; density is its own axis. Any stored value that is not one of
   the two reads as `afternoon`.
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
    Nothing reconstructs a balance client-side.
12. **Every existing action survives**: colour, name, description, repo,
    kind, term add / edit / remove, absence record / change / remove,
    session edit / delete, goal overrides on weeks the contract does not
    govern, archive and restore. Some move: archive to the settings
    drawer's foot, restore also onto the *Archived* chip.
13. **The marketing page** (`/`, logged out, `HomePage.css`) got the
    afternoon last, as its own pass. The companion, daemon, VS Code
    extension and wall clock were untouched.

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
                       Holidays Switzerland · Zürich · 2 company days · 1 not given
                         · Brought forward +2.0 h · Ended — · Holidays · Edit
            TIME OFF   upcoming                                          + Book
                       Tomorrow · Fri Sep 11 · Vacation · Zürich trip          vacation
                       Mon Oct 5 – Fri Oct 9 · Vacation · 5 days               vacation
                       Thu Dec 24 · Christmas Eve · company holiday             holiday
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
exists. *Objective / 0-hour term*: no balance ("An objective term — no
balance while it lasts."), no expectation, the personal goal if set; the
register shows the term as a labelled gap or a step at zero. *Before the
first term*: "Contract starts Mon Sep 14, 2026 · 33.6 h/week", worked
only. *After `ended_on`*: "Final balance · ended Aug 31" with the proof
frozen at that date and no projection. *Missing region*: a notice line in
the standing and the register's constants line carry the caveat; no
banner. *Past week open*: the balance stays pinned to today; the right
half becomes "Week 35 · closed +1.5 h over", no sentence, the day rows
show that week. A week still to come gets its figures and no verdict.
*Empty project*: the seven rows with their expectations and "No sessions
yet — start the timer in the sidebar."

### How the page is put together

- **The regions are named**: "Where you stand", "Days", "Earlier weeks",
  and in the rail "Contract" or "Goal", "Time off". Tests and E2E specs
  find the page by those names, never by class.
- **The layout queries the content column, not the viewport**
  (`@container/content`): the standing's two halves from 640 px, the day
  row's narrow grid under 560, the ledger's two-line grid under 640, the
  rail beside the main column from 860. The container variants are written
  out in full in the source, because Tailwind reads class names off the
  file text; a template-built variant compiled to nothing.
- **On a day job with a contract, the standing waits for
  `/contract/week`**: "…" while it loads, the API's message on failure,
  never the personal goal as a stand-in.
- **While a beat runs on this project**, the current week and the ledger
  poll every 60 s. A past or next week does not, and a timer start
  invalidates nothing: nothing a project read returns has moved at that
  instant.
- **A day's figure is the API's**: `/contract/week`'s day on a day job with
  a contract, else the ledger's `days[i]`. The sessions under it are
  grouped by the same local-start rule, so they add up to it; the live
  row's duration ticks every 30 s while the figure beside it moves with the
  query. The "+0.4" delta shows on days before today only. Session times
  are the 24 h clock.
- **Today keeps its own row on the weekend.** Saturday and Sunday fold into
  "Sat–Sun" only when both are empty and neither is today.
- **Remaining is never negative**: 0.0 h once the week is met, and the
  sentence carries the over. Decision 1 leaves no "Over" label to switch to.
- **A governed past week's "closed" line is the ledger's +/−**, so the
  standing and the row agree.
- **The ledger stops at the opening balance.** Weeks ending before `since`
  are dropped, so the opening rule is the last row. "Show 5 more weeks"
  hides once nothing is left before the opening balance, and at the API's
  104.
- **A term's rule row sits under the week its date falls in**, so reading
  down, everything above the rule is under the new terms. The closing rule
  sits above the week the contract ended in; a rule dated in the current
  week or later sits at the top, a ghost while still to come. A quiet run
  of weeks folds into one row and breaks at a rule; it reads "n weeks
  away · … · vacation" only when every note in it is a vacation.
- **The goal is the standing goal, not this week's**: the permanent
  override in force this Monday, else the project's own (`standingGoalOn`),
  for both the kind chip and the Goal panel. A one-week override bends
  This week, not the chip: the chip identifies, This week measures.
- **The rail's first panel has three shapes**: *Contract* on a day job with
  a contract; the no-contract state only on a day job with neither a
  contract nor a personal goal; *Goal* everywhere else. On a day job with a
  contract the register still lists stored goal overrides — they govern
  the weeks the contract does not — so they can be removed.
- **Time off** makes one absence read, `[Jan 1, today + 365]`, for the
  upcoming list and the year's tally. A run of one type bridges weekends
  and holidays. A holiday row — public, or a company day reading "company
  holiday" — opens its week in Days (it has nothing to book); an absence
  row opens the dialog on the run.
- **The Holidays dialog** (`HolidaysDialog`, from the register's
  constants) edits the contract's company days and the public holidays the
  employer does not give, one year at a time (‹ 2026 ›), and saves with one
  whole-contract `PUT …/contract`, other years' entries untouched. A
  weekday public holiday has a "Day off at work" tick; a weekend one costs
  nothing and has none. A date still marked not given that matches no
  holiday of the region — left by a region change, a cleared region or a
  library upgrade — is listed under "No longer a holiday here" so it can be
  seen and removed, but only once that year's calendar is in: until then,
  or when it fails to load, every date not given would look left over. A
  company day on a date marked not given is refused, and its row offers
  "Clear the mark". A region change in the settings form clears neither
  list. The constants' "2 company days · 1 not given" are counted off
  `/holidays?include=not_given`, not the raw lists, so a leftover date is
  never counted, nor a date not given that a company day covers.
- **The booking dialog records with `POST …/absences`**, the API's upsert,
  one weekday at a time, as one mutation with one invalidation at the end.
  The first failure stops the run and keeps the dialog open ("2 of 5 days
  saved — …"); nothing is rolled back, and saving again is idempotent. The
  dialog does not close while a run is saving. A booked day keeps its own
  note unless one is typed. Remove takes the whole range when every
  bookable weekday in it is on record. The cost line counts against what
  is already booked, so a half day becoming a full one "drops by 3.4 h".
- **A kind change deletes the contract**: its terms, region and opening
  balance are not kept, and nothing comes back with a return to day job.
  The settings drawer says so before save, on a project with a contract.
- **An archived project's page opens**, so the Archived chip's Restore and
  the drawer's are reachable from the projects index.
- **Focus goes back to the opener**, in the `Dialog` primitive: Radix
  returns it only to a `Trigger`, which no dialog here renders. When a save
  has removed the opener, the caller's `returnFocus` stands in.

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
match shows the figures and no sentence — never a guessed one. The code is
`entities/project/model/standing.ts` and `ledger.ts`, pure and clock-free.

- **The projection is the current week's only.** The balance is pinned to
  today whatever week is open, so the page always passes the current
  week's `/contract/week`. Its figures round to 0.01 like the API's, so the
  sign is the balance's.
- **A cap has no sentence.** The personal-goal path serves every kind, and
  a day job under an objective term or before its first term, over the
  calendar days left.
- **`nominalLine`** ("33.6 h nominal − Fri vacation 6.7 h") deducts what
  each weekday's expectation actually lost, so a half day comes out right,
  and is null unless the named days add up to Expected within 0.05 h. A
  mid-week term change measures a day against the wrong per-day hours, and
  no line beats a wrong one. Past two days off it counts them by kind
  ("3 days vacation 20.2 h − 2 holidays 13.4 h"), a kind with one day
  keeping its name, so a week of Christmas stays one line.
- **The ledger's +/− (`weekDelta`) is the move between two closes** when
  the row and the one before both have one. On the contract's first close
  it is the move from the opening balance. Only then does it fall back to
  worked − expected, else worked − goal. Worked − expected is wrong on the
  week a contract starts or ends mid-week, because `worked` counts hours
  the balance does not (see *The ledger route*).
- **The since line is worked − expected with the opening in brackets**, so
  it adds up to the standing's balance.

---

## The ledger route

`GET /api/projects/{id}/ledger?weeks=N&tz=…` — any kind of project,
newest week first, `weeks` 1–104 (default 8; a 422 naming `weeks`
outside it). One beats read, and on a day job with a contract one absence
read and one holiday calendar over
`[min(contract.starts_on, first Monday), max(today, last Sunday)]`, then
`worked_by_local_day(beats, tz)` once. The assembly is pure, in
`domain/ledger.py`; its docstring says what each figure is and when it is
null.

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

`/contract/week` carries sibling fields, never a retyped `balance`:
`balance_as_of` (date), `balance_opening`, `balance_worked`,
`balance_expected_through` — null exactly when `balance` is null, and
required-nullable like it, so the generated type does not call them
optional.

What the shape settles:

- **The closing balance is the Monday-morning figure.** Reading the
  balance on the following Monday would count that Monday's hours (today's
  work counts as soon as it happens) while charging only through Sunday,
  and the row-to-row proof would fail. `closing_balances` in
  `contracts.py` reads every Sunday's close off one running total over the
  same per-day rule `balance_terms` sums, so the proof is one rule in one
  place.
- **`balance_end` and `contract_expected` share one null rule**, decided
  by `week_expectation`: a week with no expectation has no closing
  balance. A term starting on a Saturday leaves its week before the
  contract on both counts, and its weekend hours move the next close.
- **After `ended_on` every row repeats the final balance**, and
  `contract_expected` is 0 there (owed nothing by circumstance; the term
  still governs). Hours tracked after the end appear in `worked` and move
  nothing.
- **`totals` is null on the week route's rule for today's balance**, so
  the standing and the ledger's foot go blank together.
- **The proof holds to the cent, not to the bit.** `balance` is
  `round(opening + worked − expected, 2)`; the three terms are rounded on
  their own, so their sum can differ from `balance` by up to 0.01.
- **`notes` are weekdays only**, by date, a holiday before an absence on
  the same day. The absence's free-text note is not carried; the rail's
  Time off panel reads the absence list for that.
- A paired device can read the ledger, as it can the week: `/api/projects`
  is in `DEVICE_ALLOWED_PREFIXES`.
- The projects index (`include=this_week`) does not read the ledger. Its
  `weekly_minutes` and goal come from `ProjectService._this_week_from_beats`:
  completed beats, the current week by server date.

---

## The theme

Tokens kept their names so that every page followed on the day the block
landed; the values changed. On `:root` (afternoon), redefined under
`:root[data-theme="dusk"]`, in `ui/client/global.css`. They are stored as
HSL triples so `hsl(var(--x) / .5)` works by hand; the table gives the
mockup's colours.

| token | afternoon | dusk |
|---|---|---|
| `--background` | the sky's low haze `#E4F0F1` (the sky itself is a fixed layer) | `#2E3E6E` |
| `--card`, `--popover` | `#FFFDF7` at 93 % | `#243049` at 94 % |
| `--foreground` | `#2B3A44` | `#ECF1F6` |
| `--muted` | a sky-grey, `203 35% 85%` | `218 19% 28%` |
| `--muted-foreground` | `206 10% 40%`, a step darker than the mockup's `#66737D` | `#A6B1BF` |
| `--secondary` (washes) | `rgb(114 176 214 / .16)` | `rgb(140 190 230 / .14)` |
| `--border` | `rgb(43 58 68 / .09)` | `rgb(236 241 246 / .10)` |
| `--accent` / `--primary` | `#F2B233`, foreground `#2B3A44` | `#F5C55B`, foreground `#2B3A44` |
| `--accent-ink` | `#8C5E12` | the accent |
| `--success` / `--success-ink` | `#3F8F55` / `136 45% 30%` | `#8AD6A0` for both |
| `--destructive` / `--destructive-ink` | `#D2683F` / `#A84924` | `#F2A182` for both |
| `--radius` | `1.5rem` | same |
| sidebar family | the panel at 82 % and its ink | the panel at 86 %, dusk values |
| `--tint-*` | vacation, sick, holiday, other: a fill and its ink each | same, dusk values |

`--shadow-soft` is the panel shadow (`0 22px 48px -26px`, its colour per
hour), `--shadow-card` the dialog's. The radius scale is explicit and
monotonic on the mockup's stops (sm 10, md 12, lg 16, xl 18, 2xl 22,
3xl = `--radius`, 4xl 28 px); deriving it from `--radius` ± 2 px had put
`rounded-sm` above `rounded-xl`.

**The sky** is `SkyBackdrop` (`shared/ui/sky-backdrop.tsx`), rendered first
by `Layout` and by the marketing page: a `position: fixed` layer at
z-index −1 with the gradient, the sun, five drifting clouds and the
three-hill SVG, coloured by the `--sky-*`, `--cloud*` and `--hill-*`
tokens. It shows only while nothing between it and the root paints a
background or opens a stacking context, which is why `Layout`'s root and
`.homepage-root` do neither. Never `background-attachment: fixed` on
`body`: iOS Safari paints it black under a `backdrop-filter` overlay (the
note in `global.css`). The clouds drift over two to three minutes. Under
`prefers-reduced-motion` nothing moves: the clouds stop, and every
animation and transition jumps to its end state. `NotFound` and
`ErrorBoundary` keep `bg-background`, since they render outside `Layout`
with no sky behind them.

**The primitives.** `Panel` (`shared/ui/panel.tsx`: `rounded-[1.625rem]
bg-card shadow-soft`) is the one card. `Button` variants are pills; chips
and tints are pills. `Dialog` keeps its bottom sheet on phones and is a
rounded cloud on desktop. `AuthModal` is restyled but still hand-rolled:
moving it onto `Dialog` would change its Escape and backdrop behaviour
mid-sign-in. Settings offers *Afternoon* and *Dusk* beside *Layout
Density*. `PROJECT_COLORS` were re-picked to sit on the sky, at the same
count so hashing is stable.

The rules every page follows:

- **The raw accent is never text.** As text it is `text-accent-ink`; the
  accent itself is under 2:1 on a panel by day. Fills and borders keep the
  accent; at dusk the two tokens are one colour.
- **Small text in a tone takes the ink**: `--success-ink` and
  `--destructive-ink` for small figures, chips and alerts; the tone itself
  only on big figures (large text passes at 3:1), fills and icons.
- **The accent where it means something**: today, the running timer, one
  primary action a page, links in accent ink, and the pressed option of a
  segmented control (the mockup's `.seg`: the accent as a fill with ink on
  it, `aria-pressed`). Where a control is not one — tabs, chips, option
  cards — the selected one sits on the heavier wash in ink. Totals, big
  figures, tags and heading icons are ink or the wash. `Progress` fills in
  leaf, not sunlight.
- **Colour that carries meaning stays**: leaf for good scores and data
  marks, persimmon for low ones and alerts, up/down deltas in success and
  destructive. Destructive red fills only actions that delete for good;
  elsewhere remove turns red on hover. Coach usage bars are the sky — leaf
  would call spending the budget good. Project colours are user data.
- **Hairlines only where they separate content**: list rows, panel
  footers, the blocks inside a settings section. Every other border is
  gone.
- **On the bare sky, the card surface, not the wash** — a wash vanishes
  there — for controls like the search field and filter chips. Text on the
  sky is ink, or ink at 80–90 % for secondary copy, never the muted tone:
  it falls under 3:1 at the sky's top and scrolls over the dusk sky's
  purple band.
- **`font-mono` is not a monospace**: it is the rounded figures face. Real
  code is `font-code`.

**First paint.** A script at the top of `ui/index.html` stamps the stored
hour and density before first paint, so a stored dusk does not flash the
afternoon. It repeats the two storage keys and the dusk sky's hex, which
`shared/lib/useTheme.ts` owns; a change to either is made in both places.
`theme-color` follows the hour (`THEMES` carries each hour's sky).

**The marketing page** reads the theme through a few local variables on
`.homepage-root` (`--hp-panel`, `--hp-ink`, `--hp-wash` …), so dusk has no
rules of its own there. The accent is its running beat and primary button.

---

## Follow-ups and open questions

Tracked in Linear — the [LifePete project](https://linear.app/elghareeb/project/lifepete-a8ecce3a86de), milestone *Project
page follow-ups*. The ledger's write side, vacation entitlement and the
companion's week card are under *Work contracts follow-ups*. The open
question, `apple-mobile-web-app-status-bar-style` under the sky, is AHM-29.
