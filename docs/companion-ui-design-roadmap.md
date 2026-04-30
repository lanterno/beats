# Companion App UI Design Roadmap — From Functional to Magnetic

> Aesthetic direction: **Brutalist Luxury** — luxury timepiece meets brutalist typography. Massive type that owns the screen, dramatic negative space, zero visual clutter, every screen stripped to its essence. Warm amber accents on a near-black ground.

## Current State

The foundation is in place: the amber color palette (`BeatsColors`), DM Serif / DM Sans / JetBrains Mono typography (`BeatsType`), the frosted-glass custom bottom nav, `StaggeredEntrance`, fade+slide tab transitions, the radial-gradient running state on the Timer screen, the today/week/streak stats row below the timer, the breathing glow behind the Flow ring at score ≥ 0.7, animated category bars, the cardless "text flows on the page" treatment for Coach, an inline editor for evening review answers with `X OF N ANSWERED` progress, and the daily mood picker are all live.

What's left is detail polish across individual screens.

---

## Phase 2 — Motion & Transitions (remaining)

Tab transitions and stagger entries already work. Outstanding micro-interactions:

- **Project card tap**: slight scale-down (0.97) on press, spring back on release
- **Start button**: pulse glow animation on hover/long-press before confirming
- **Stop button**: brief shake animation if tapped too quickly (< 5 seconds into a session)
- **Mood emoji tap**: extend the existing scale to a true 1.0 → 1.2 → 1.0 bounce
- **Pull-to-refresh**: custom indicator (currently the default with `BeatsColors.amber`)

### Running State Ambient Motion

- The amber glow on the timer card should **breathe** — slowly pulsing opacity (already done for the dot, extend to the card shadow)
- The timer digits should have a subtle fade transition on each second tick (not a hard swap)

> Flow score ring already has a breathing glow at score ≥ 0.7 — shipped.

---

## Phase 3 — Timer Screen Polish (remaining)

The radial-gradient running state and stagger entries already ship. Still missing:

### Layout Refinements

- More generous padding inside the time block — equal breathing room above/below the digits
- Subtle gradient fade divider between project chip and timer (instead of the implicit gap)
- Project selector input could use a subtle inner shadow for depth

### Stats Row

The today / week / streak stats row is live. Remaining nice-to-haves:

- Add a **week-over-week comparison arrow** (↑ 12% or ↓ 5%) matching the web's `SidebarStats`
- Restyle the streak when it's high (e.g. flame glyph at ≥ 7 days)

### Project Picker Sheet

The picker now shows a **RECENT** section at the top (last 5 projects started, tracked locally in `RecentProjects`/`SharedPreferences`) followed by an **ALL PROJECTS** section. Sheet content uses an `easeOutBack` spring entrance. Nothing pending here.

---

## Phase 4 — Flow Screen Polish (remaining)

The score ring, breathing glow at score ≥ 0.7, area-chart timeline, and animated category bars already ship. Polish remaining:

- Inner circle of the ring: subtle radial gradient (currently flat)
- Foreground ring stroke: gradient from amber to warm white instead of solid color
- Add **touch interaction** on the timeline: tap a point to see the exact score + dominant app at that time

---

## Phase 5 — Coach Screen Elevation

Numbered questions, mood picker with bouncing scale, the colored-ring selection state, and the cardless "text on the page with thin dividers" layout are in place. Still missing:

### Morning Brief

- Add a **timestamp** in the top-right showing when the brief was generated

### Evening Review

Inline editor with debounce-save and an `X OF N ANSWERED` progress indicator are shipped. No further design work pending here.

### Mood Picker

- Add a **"What went well?"** text input below the mood picker for optional notes
- Show **mood history sparkline** — last 7 days as tiny dots, color-coded

---

## Phase 6 — Intentions Screen Polish (remaining)

Color-bar accent, strikethrough completion, top progress bar, and pill-shaped duration chips are in place. Still missing:

### Add Intention Sheet

- **Visual preview** of the intention being created (project dot + name + duration) that updates live as the user selects options
- **Quick-add row** at the top: last 3 project+duration combinations as one-tap shortcuts

### Completion Animation

A 6-particle confetti burst (amber/gold, ~650ms with mild gravity) fires from the check circle on completion via `ConfettiBurst` mounted in the overlay. The check circle and text style transition smoothly across the done/undone change. No further work pending here.

---

## Phase 7 — Settings & Pairing Polish

The Settings tab still uses Material defaults (`Card`, `Chip`, `ListTile`) — out of step with the rest of the app.

### Pairing Screen

The code input now renders as 6 individual character boxes (`_CodeInput`); the active box highlights amber, filled boxes show a softer amber border, and a transparent backing TextField preserves keyboard, paste, and autofill. Remaining nice-to-have:

- Add a **subtle particle/ember animation** in the background — floating dots that drift upward slowly

### Settings Screen

- Replace `Card` / `ListTile` / `Chip` with custom containers using `BeatsColors.surface` and the project's typography
- Group sections with **section headers** that have a line extending to the right edge
- Connection status indicators: replace text with **colored dots** (green = connected, gray = disconnected)
- Unpair button: move to a **danger zone** section at the very bottom with a red tint

---

## Implementation Priority

| Phase | Impact | Effort |
|-------|--------|--------|
| **5 — Mood notes + sparkline** | Medium | 0.5 day |
| **2 — Remaining micro-interactions** | Medium | 0.5 day |
| **4 — Flow ring/timeline refinements** | Medium | 0.5 day |
| **6 — Intentions add-sheet polish (visual preview, quick-add row)** | Low-Medium | 0.5 day |
| **7 — Settings/Pairing visual rewrite** | Low but very visible to first-time users | 1 day |

**Total: ~3 days of polish remaining.**

---

## Guiding Principles

1. **Warm, not cold.** Every surface, every text color, every shadow should carry warmth. No cool grays, no blue-tinted whites.

2. **Brutalist clarity over decoration.** Massive type, dramatic negative space, thin dividers instead of cards. No grain, no noise overlays, no faux-tactile textures.

3. **Reward attention.** Small details that users discover over time — the way the glow breathes, the way a project's color tints the timer background, the way the mood sparkline tells a story.

4. **Consistent motion vocabulary.** Every animation uses the same timing (250ms), the same curve family (easeOutCubic for enters, easeInCubic for exits), and the same distance (12px for slides, 0.97–1.0 for scales).

5. **The timer is sacred.** It's the center of the app. Every design decision should make the timer screen feel more important, more present, more alive than anything else.
