# Companion App UI Design Roadmap

> Aesthetic direction: **Brutalist Luxury** — luxury timepiece meets brutalist
> typography. Massive type that owns the screen, dramatic negative space,
> zero visual clutter, every screen stripped to its essence. Warm amber
> accents on a near-black ground.

The first wave of this redesign is fully shipped. New polish items land here
as they're identified.

## Shipped — System & Foundation

- Amber color palette (`BeatsColors`), DM Serif / DM Sans / JetBrains Mono
  typography (`BeatsType`)
- Frosted-glass custom bottom nav, `StaggeredEntrance`, fade+slide tab
  transitions
- Shared `PressScale` (1.0 → 0.97 on press) for buttons + tappable cards
- Shared `BeatsRefresh` pull-to-refresh (thin amber stroke, surface backdrop)

## Shipped — Timer

- Radial-gradient running state tinted by project color
- Today / Week / Streak stats row below the action area, derived from the
  heatmap; streak forgives a zero-today
- Project picker with **RECENT** section + spring entrance
- Stop button shakes (elastic-in, ±8px) on first tap inside a sub-5s session
- Brutalist time digits with HR / MIN / SEC labels

## Shipped — Flow

- Score ring with breathing glow at score ≥ 0.7
- Inner radial gradient and sweep-gradient (amber → warm-white → amber)
  ring stroke
- Tap/drag-to-inspect timeline with vertical guide and detail row showing
  time, exact score, dominant category, and the editor's repo + branch
  when a VS Code heartbeat covered that window
- "PEAK 91 AT 14:32" line under the score ring — tap-to-jump the
  inspector to the day's best window
- Animated category bars

## Shipped — Coach

- Cardless "text on the page" treatment with thin dividers
- Inline editor on each evening review question with debounce-save and
  `X OF N ANSWERED` progress indicator
- Mood picker with 1.0 → 1.2 → 1.0 bounce on selection
- "What went well?" debounce-saving note field
- 7-day mood sparkline (red ≤2 / amber =3 / green ≥4)

## Shipped — Plan / Intentions

- Color-bar accent + strikethrough completion + top progress bar
- Live preview row in the add-sheet that updates as the user picks
- QUICK ADD row of the last 3 distinct (project, duration) combos from today
- 6-particle confetti burst on completion

## Shipped — Pairing & Settings

- 6-box pairing code input with amber active highlight and transparent
  backing TextField (preserves keyboard, paste, autofill)
- Slow ambient `Embers` field behind the pairing form
- Settings rewritten in the brutalist vocabulary: section headers with
  trailing rule, surface containers, dot status indicators, tinted
  DANGER ZONE block, brutalist confirm dialog for unpair

## Shipped — Tray (macOS / Windows / Linux)

- Live elapsed time + project in the menu bar
- Quick-start submenu, stop, open, quit
- Tray icon renders a colored dot matching the running project
  (gray when idle), cached on disk by hex via `TrayIconRenderer`

---

## Open polish

Small touches that didn't make the first wave. Nice-to-have, not blocking.

- **Timer block**: more generous padding above/below the digits
- **Timer block**: subtle gradient-fade divider between the project chip
  and the time
- **Timer card shadow**: extend the dot's pulsing breath to the card shadow

Recently shipped:

- Project-selector inner shadow for depth
- Stats row: ↑/↓ week-over-week percentage badge under WEEK total (hidden
  when last week had < 30 minutes — avoids noisy "↑200%" early on)
- Stats row: 🔥 glyph replaces "DAYS" once the streak is ≥ 7
- Timer digits: 220ms cross-fade between values on each second tick
- Coach morning brief: HH:MM timestamp in the top-right of the section
- Recent-tag chips on the post-stop sheet (one-tap select + freeform
  input merges with chip selections on save)

---

## Guiding Principles

1. **Warm, not cold.** Every surface, every text color, every shadow should
   carry warmth. No cool grays, no blue-tinted whites.

2. **Brutalist clarity over decoration.** Massive type, dramatic negative
   space, thin dividers instead of cards. No grain, no noise overlays, no
   faux-tactile textures.

3. **Reward attention.** Small details that users discover over time — the
   way the glow breathes, the way a project's color tints the timer
   background, the way the mood sparkline tells a story.

4. **Consistent motion vocabulary.** Every animation uses the same timing
   (250ms), the same curve family (easeOutCubic for enters, easeInCubic for
   exits), and the same distance (12px for slides, 0.97–1.0 for scales).

5. **The timer is sacred.** It's the center of the app. Every design
   decision should make the timer screen feel more important, more present,
   more alive than anything else.
