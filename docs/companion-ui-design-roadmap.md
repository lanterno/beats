# Companion App UI Design Roadmap — From Functional to Magnetic

> Aesthetic direction: **Warm Instrument** — the app should feel like a hand-crafted analog tool made digital. Think: the dashboard of a vintage Porsche crossed with a Japanese ceramic tea set. Warm, tactile, purposeful, alive.

## Current State

The app is functional but utilitarian — Material 3 defaults, flat lists, no motion, no personality. Every screen feels like a form. The screens read top-to-bottom with no visual hierarchy, no breathing room, and no moments of delight.

---

## Phase 1 — Typography & Color Foundation

**Impact: Massive. Cost: Low.**

The fastest way to transform the app from "developer tool" to "designed product."

### Typography

- **Add Google Fonts dependency** (`google_fonts` package)
- **Display font**: DM Serif Display or Playfair Display — for the greeting, timer labels, section titles. Gives warmth and editorial weight.
- **Body font**: DM Sans or Instrument Sans — clean, humanist, modern
- **Mono font**: JetBrains Mono (already referenced) — for timer digits, stats, numbers
- **Type scale**: establish a rigid scale — 10/12/14/16/20/28/40 — and never deviate. The current code uses arbitrary sizes.

### Color System

Replace the `ColorScheme.fromSeed` with a hand-crafted palette:

```dart
// Surfaces
background:     Color(0xFF0E0C0A)   // true deep black-brown
surface:        Color(0xFF171412)   // card background
surfaceAlt:     Color(0xFF1E1A15)   // elevated cards, sheets
border:         Color(0xFF2A2520)   // subtle borders
borderAccent:   Color(0xFF3D3428)   // emphasized borders

// Foreground
textPrimary:    Color(0xFFF0E8DC)   // warm off-white (not pure white)
textSecondary:  Color(0xFF9C8E7C)   // warm muted
textTertiary:   Color(0xFF5C5247)   // labels, hints

// Accents
amber:          Color(0xFFD4952A)   // primary action, running state
amberGlow:      Color(0xFFD4952A).withOpacity(0.15)  // ambient glow
red:            Color(0xFFBF4040)   // destructive/stop
green:          Color(0xFF66B366)   // success/streak
```

Key rule: **no pure white (`#FFFFFF`) anywhere**. All text should be warm off-white to match the ember aesthetic.

### Implementation

- Create `lib/theme/beats_theme.dart` — centralized theme with all constants
- Create `lib/theme/beats_text_styles.dart` — named text styles (`displayLarge`, `label`, `mono`, `caption`)
- Update `main.dart` to use the custom theme instead of `ColorScheme.fromSeed`

---

## Phase 2 — Motion & Transitions

**Impact: Transformative. Cost: Medium.**

Motion is what makes an app feel alive vs. static.

### Tab Transitions

- Replace `IndexedStack` (instant swap, no animation) with a `PageView` or custom `AnimatedSwitcher`
- Each tab slides in from the direction of navigation (left tab → slide right, right tab → slide left)
- Duration: 250ms, curve: `Curves.easeOutCubic`

### Screen Load Animations

- Every screen should **stagger its content in** on first load
- Pattern: each section fades in + slides up 12px, with 60ms delay between sections
- Use `AnimatedOpacity` + `AnimatedSlide` or a custom `StaggeredEntrance` widget
- Timer card, stats row, and any below-fold content should each be their own stagger step

### Micro-interactions

- **Project card tap**: slight scale-down (0.97) on press, spring back on release
- **Start button**: pulse glow animation on hover/long-press before confirming
- **Stop button**: brief shake animation if tapped too quickly (< 5 seconds into a session)
- **Tab bar icons**: selected icon scales up slightly (1.1×) with a bounce curve
- **Mood emoji tap**: selected emoji bounces (scale 1.0 → 1.2 → 1.0 over 300ms)
- **Pull-to-refresh**: custom refresh indicator with the Beats amber color, not Material default

### Running State Ambient Motion

- The amber glow on the timer card should **breathe** — slowly pulsing opacity (already done for the dot, extend to the card shadow)
- The timer digits should have a subtle fade transition on each second tick (not a hard swap)

---

## Phase 3 — Timer Screen Polish

**Impact: High. This is the hero screen.**

### Layout Refinements

- Add **generous padding** — the card feels cramped. Timer card inner padding: 28px (currently 20px)
- Timer digits should be **vertically centered** in the available space with equal breathing room above and below
- The divider between PROJECT and TIMER sections should be a subtle gradient fade (not a hard line)
- Project selector: add a subtle inner shadow to the input field for depth

### Running State Enhancements

- **Background gradient**: when running, the entire screen background should shift from flat black-brown to a **radial gradient** with a faint amber center (matching the web's `radial-gradient(ellipse at 50% 40%, hsl(38 20% 12%) 0%, hsl(25 15% 6%) 70%)`)
- **Project color bleed**: the project's color should tint the card's left border (4px wide vertical accent bar, like a bookmark)
- **Elapsed time hint**: below the stats row, show a subtle "since HH:MM" label

### Stats Row Improvements

- Add **real data** — fetch today's total and this week's total from the API (currently hardcoded)
- Add **week-over-week comparison arrow** (↑ 12% or ↓ 5%) matching the web's `SidebarStats`
- Add **streak display** below the stats row when streak > 0 (flame emoji + "N-day streak")

### Project Picker Sheet

- Add **project color stripe** on the left of each row (4px bar, not just a dot)
- Add **recent projects** section at the top (projects used in the last 3 days, separated by a "Recent" label)
- Animate the sheet entrance with a spring curve (`Curves.easeOutBack`)

---

## Phase 4 — Flow Screen Redesign

**Impact: High. Currently the weakest screen.**

### Score Gauge

- Replace the CustomPaint arc with a **full-circle ring** using `CustomPainter` with:
  - Background ring: very faint (opacity 0.05)
  - Foreground ring: gradient from amber to warm white, with rounded caps
  - Inner circle: subtle radial gradient (not flat)
  - Score number: DM Serif Display at 48pt, with a "/ 100" suffix in small muted text
- Add a **glow effect** behind the ring when score > 70 (same pulsing technique as timer)

### Flow Timeline

- Replace the basic bar chart with a **smooth area chart** using `CustomPainter`
- X-axis: hours of the day (6am → now)
- Y-axis: flow score 0–1
- Fill: gradient from transparent to amber at the bottom
- Add **touch interaction**: tap a point to see the exact score + dominant app at that time

### Category Breakdown

- Replace `LinearProgressIndicator` with **custom rounded bars** with category-specific colors:
  - coding: blue (#5B9CF6)
  - communication: purple (#A78BFA)
  - browser: cyan (#22D3EE)
  - design: pink (#F472B6)
  - writing: amber (#FBBF24)
  - other: gray
- Each bar should animate from 0 to its value on screen load (300ms stagger)

---

## Phase 5 — Coach Screen Elevation

**Impact: Medium. Currently plain text in cards.**

### Morning Brief

- Replace the flat Card with a **textured card** — subtle noise overlay or grain texture on the card background
- Add a **sunrise gradient** at the top of the card (amber → transparent, 40px tall)
- Brief text should use the display body font, not monospace
- Add a **timestamp** in the top-right corner showing when the brief was generated

### Evening Review

- Questions should be **numbered** with large, amber-colored numerals (1, 2, 3) on the left
- Each question card should have a **text input area** that expands on tap (currently questions are read-only)
- Add a **subtle progress indicator** — "1 of 3 answered" at the top

### Mood Picker

- Replace emoji text with **custom mood illustrations** (or at minimum, larger emoji with colored background circles)
- The selected mood should have a **colored ring** animation (not just a border)
- Add a **"What went well?"** text input below the mood picker for optional notes
- Show **mood history sparkline** — last 7 days as tiny dots, color-coded

---

## Phase 6 — Intentions Screen Refinement

**Impact: Medium.**

### Visual Hierarchy

- Each intention should show the **project color** as a left border accent
- Completed intentions: strikethrough text + reduced opacity (0.4), not just a checkbox
- Add a **progress ring** at the top showing "2 of 3 completed" as a circular indicator

### Add Intention Sheet

- The bottom sheet should have a **visual preview** of the intention being created (project dot + name + duration) that updates live as the user selects options
- Duration chips should be **pill-shaped** with the selected one having an amber fill (not Material ChoiceChip)
- Add a **quick-add row** at the top: last 3 project+duration combinations as one-tap shortcuts

### Completion Animation

- When checking off an intention: **confetti burst** from the checkbox (subtle, 4-5 particles, amber/gold)
- The item should **slide and compress** slightly, then settle back

---

## Phase 7 — Settings & Pairing Polish

**Impact: Low but important for first impressions.**

### Pairing Screen

- Add the **Beats logo** (or a stylized "B" mark) above the title
- The code input should have **individual character boxes** (6 separate boxes) instead of a single text field — like a verification code input
- Each box highlights amber when receiving input
- Add a **subtle particle/ember animation** in the background — floating dots that drift upward slowly

### Settings Screen

- Group sections with **section headers** that have a line extending to the right edge
- Connection status indicators: replace text with **colored dots** (green = connected, gray = disconnected)
- Unpair button: move to a **danger zone** section at the very bottom with a red tint

---

## Phase 8 — Bottom Navigation Bar

**Impact: Medium. Visible on every screen.**

### Custom Navigation

- Replace Material `NavigationBar` with a **custom bottom bar**:
  - Frosted glass effect (`BackdropFilter` with `ImageFilter.blur`)
  - No labels (icon-only, cleaner)
  - Selected icon: amber color + subtle glow dot below
  - Unselected: warm gray (0.3 opacity)
  - Center icon (Plan) could be slightly elevated as a floating action button
- Height: 56px (slim), with safe area padding below

---

## Implementation Priority

| Phase | Impact | Effort | Do When |
|-------|--------|--------|---------|
| **1 — Typography & Color** | Massive | 1 day | First — transforms everything |
| **2 — Motion** | Transformative | 2 days | Second — makes it feel alive |
| **3 — Timer Polish** | High | 1 day | Third — hero screen |
| **8 — Nav Bar** | Medium | 0.5 day | With Phase 2 — always visible |
| **4 — Flow Redesign** | High | 1.5 days | After timer is polished |
| **5 — Coach Elevation** | Medium | 1 day | Content screens |
| **6 — Intentions** | Medium | 1 day | Content screens |
| **7 — Settings/Pairing** | Low | 0.5 day | Last — least visible |

**Total: ~8.5 days for the complete transformation.**

---

## Guiding Principles

1. **Warm, not cold.** Every surface, every text color, every shadow should carry warmth. No cool grays, no blue-tinted whites.

2. **Breathe.** More padding, more negative space. Let elements float. The current UI is too dense for a daily-use app.

3. **Reward attention.** Small details that users discover over time — the way the glow breathes, the way a project's color bleeds into its card, the way the mood sparkline tells a story.

4. **Consistent motion vocabulary.** Every animation uses the same timing (250ms), the same curve family (easeOutCubic for enters, easeInCubic for exits), and the same distance (12px for slides, 0.97–1.0 for scales).

5. **The timer is sacred.** It's the center of the app. Every design decision should make the timer screen feel more important, more present, more alive than anything else.
