# Beats Roadmap

> A personal time tracking tool that's more than just a timer.
> Beats lives on your desk, in your browser, and in your pocket — helping you understand how you spend your time and make better choices about it.

This roadmap covers 8 phases of development, each building on the last. Phases are designed to be completed in 2-4 sessions each.

---

## Phase 1: Self-Awareness — "Know Thyself"

Right now Beats tells you *how many hours* you worked. That's table stakes. This phase makes it tell you *how you work* — your patterns, rhythms, and tendencies.

### Features

- **Contribution heatmap** — A GitHub-style 52-week grid on a new `/insights` page. Each cell is a day, color-coded by total hours (faint at <1h, fully saturated at 6h+). Hoverable: "Mon, Mar 9 — 4.2h across 3 projects." New API endpoint with MongoDB aggregation pipeline for efficient date grouping.

- **Daily rhythm chart** — A 24-hour horizontal visualization showing *when* you work. Aggregate sessions into 30-minute slots across the selected period (week/month/all-time). Answers: "Am I a morning person or a night owl?"

- **Streak tracker** — Current and longest consecutive-day streaks displayed in the sidebar. Days with at least one session count. A quiet motivator that costs nothing to compute.

- **Session stats per project** — On the project detail page: average session length, longest session, session count this month. Computed client-side from already-fetched data.

- **Weekly comparison** — In sidebar stats, show percentage change vs last week with a subtle arrow. "This week: 18.2h (+12%)" tells you more than "18.2h" alone.

### Why this matters

Time tracking without insight is data entry. Users who see their patterns develop a relationship with the tool — it becomes a mirror, not a chore.

---

## Phase 2: Polish and Feel — "Make It Breathe"

The architecture is clean, the data model is solid. Now make the interface feel *alive*. The difference between "I use this" and "I love this" is mostly in the details.

### Features

- **Animated timer digits** — Odometer-style roll animation on the sidebar timer. Digits count up smoothly, settle with ease-out on stop. The timer already glows amber — now the numbers move.

- **Page transitions** — Subtle cross-fade with slight Y-translate between dashboard and project detail. Framer Motion `AnimatePresence` wrapping the `<Outlet />` in Layout.

- **Keyboard shortcuts** — `Space` to start/stop timer (outside inputs), `1-9` to select project by position. `Cmd+K` or `/` opens a command palette for project search and navigation.

- **Sparkline entrance animation** — The bars in ProjectPulseList grow from zero to target height with staggered delay (30ms per bar). Gives a "filling up" effect on page load.

- **Favicon timer indicator** — When the timer runs, the browser favicon shows a small colored dot matching the project color. Canvas-generated, driven by `useTimer` state.

- **Richer stop toast** — Replace the plain text toast with a custom component: project color dot, duration, and a mini bar showing how this session compares to your daily average.

### Why this matters

These aren't features — they're feelings. Every micro-interaction signals that someone cared about the details. This is what makes screenshots shareable and the app worth opening.

---

## Phase 3: Progressive Web App — "Always With You"

A time tracker you have to open a browser tab for is a time tracker you forget about. This phase makes Beats a real app.

### Features

- **PWA manifest + service worker** — Add `vite-plugin-pwa` to the build. App icons, warm amber theme color, stale-while-revalidate caching. "Add to Home Screen" on mobile and desktop.

- **Offline timer** — When offline, the timer still works. Start/stop actions queue in IndexedDB and replay when connectivity resumes. A subtle amber "offline" dot in the header signals queued state. The existing `useTimer` localStorage persistence is the foundation.

- **Push notifications for forgotten timers** — After the timer runs for 2+ hours (configurable), a browser notification: "You've been working on [Project] for 2 hours. Still going?" Prevents the #1 pain point of time tracking.

- **Install prompt** — A non-intrusive banner in the sidebar when the browser fires `beforeinstallprompt`. "Install Beats for quick access." Dismissible, preference stored in localStorage.

- **Background sync** — Timer start/stop events reach the server even if the tab closes while offline. Critical for wall clock interop — the device might toggle the timer while the web app is closed.

### Why this matters

PWA transforms Beats from a website into an app that lives in your dock. On your phone without an app store. Offline without anxiety. This is the infrastructure for "always there."

---

## Phase 4: Planning and Intention — "What Will You Do?"

Tracking time is retrospective. This phase makes it *prospective*. You don't just see what you did — you decide what you'll do.

### Features

- **Daily intentions** — A "Today's Plan" section at the top of the dashboard. Set 1-3 time-boxed intentions each morning: "2h on API refactor, 1h on docs." Auto-checks when tracked time for that project exceeds the plan. New `Intention` model and CRUD endpoints.

- **Focus mode** — When the timer runs, toggle a distraction-free view: large centered timer, project name, stop button. Nothing else. Fullscreen optional. Keyboard shortcut: `F`.

- **Goal ring visualization** — Replace the thin progress bars on project pulse with SVG radial arcs. Brief confetti animation when a goal is met. Contextual text: "2.5h to go" or "Goal met! +1.2h extra."

- **Time budgets** — Extend weekly goals with a "cap" mode: "No more than 10h/week on Project X." Progress bar fills red instead of green as you approach the limit. New `goal_type` field on the project model: `"target"` vs `"cap"`.

- **End-of-day review** — At a configurable time (default 5 PM), a prompt: "How was your day?" Shows today's summary with a text area for a brief note and optional mood (1-5). Stored as `DailyNote` model. The beginning of the qualitative layer.

### Why this matters

The moment you set intentions and track against them, time tracking becomes a productivity system. This is what separates a cool gadget from something that changes how you work.

---

## Phase 5: Wall Clock Superpowers — "The Hardware Edge"

The wall clock is a $35 toggle switch that sends an HTTP POST. This phase makes it an ambient display that reflects your day in light and color.

### Features

- **Device status API** — New `GET /api/device/status` returning timer state optimized for ESP32: `{clocked_in, project_name, elapsed_minutes, daily_total_minutes, energy_level (0-7)}`. The firmware fetches real values instead of hardcoding `SetEnergyMeter(5)`.

- **Project-colored LEDs** — The status LED shows the current project's color from the web UI palette. Status endpoint includes `project_color_rgb: [r, g, b]`. The firmware's `StatusColor` enum gets a `Custom(u8, u8, u8)` variant.

- **Multi-project switching** — Double-press cycles through "favorite" projects (fetched at boot from `GET /api/device/favorites`). LED briefly flashes each project's color before confirming selection.

- **Device dashboard** — Firmware periodically POSTs heartbeats: `POST /api/device/heartbeat {battery_voltage, wifi_rssi, uptime_seconds}`. Sidebar shows: "Wall clock: 78% battery, seen 2m ago."

- **Ambient daily progress** — Every 5 minutes, the firmware fetches the status endpoint and updates the 7 energy meter LEDs to reflect real-time daily hours. A glanceable physical object on your desk that fills up throughout the day.

### Why this matters

The wall clock is the single most unique thing about Beats. Nobody else has a physical desk device that shows your productivity in colored light. This phase makes that real instead of theoretical.

---

## Phase 6: Notes, Tags, and Context — "Remember the Why"

Hours tell you *how long*. This phase adds *what* and *why*. Lightweight metadata without turning Beats into a project management tool.

### Features

- **Session notes** — Optional `note` field on beats. When stopping the timer, a small inline input: "What did you work on?" (not required, easily dismissed). Notes appear in session lists and today feed. Searchable via `GET /api/beats/?q=search_term`.

- **Tags** — Freeform tags on sessions: `["deep-work", "meetings", "learning"]`. Autocomplete from previously used tags. Appear as small pills on session rows. Filter the heatmap and insights by tag.

- **Session timeline view** — A horizontal timeline on the project detail page: sessions as colored blocks on a 24-hour axis, one row per day. At-a-glance view of *when* you worked, not just how much.

- **Monthly retrospective** — Auto-generated at `/insights/month/2026-04`: total hours, top project, busiest day, average daily hours, longest session, tag cloud, rhythm chart. "Copy summary" button for journaling or standups.

- **Quick log** — A "+" button on the dashboard to manually log a past session. Covers the "I forgot to use the timer" case. Project, date, start/end, optional note. Uses the existing `POST /api/beats/` endpoint.

### Why this matters

After months of use, the most valuable thing in Beats isn't today's timer — it's the history. Notes and tags make that history searchable and meaningful. "What was I working on in February?" becomes answerable.

---

## Phase 7: Data Export and Ownership — "Your Data, Your Way"

This is what makes Beats trustworthy. You can leave anytime and take everything with you.

### Features

- **CSV export** — Export buttons on project detail and insights pages. Sessions as CSV: `date, project, start, end, duration_minutes, note, tags`. Weekly summaries as a separate CSV. Server-side streaming response.

- **Full JSON backup and restore** — `GET /api/export/full` dumps everything: projects, beats, intentions, notes. `POST /api/import/full` restores with upsert-by-ID. Disaster recovery and self-hosted migration in one feature.

- **Webhooks** — Register URLs to receive `timer.start` and `timer.stop` events. Enables IFTTT, Zapier, Home Assistant, or custom automations. Managed via a settings page.

- **Shareable weekly card** — A visual summary card (rendered via canvas or SVG): project colors, hours breakdown, streak count, goal completion. Screenshot-friendly. Useful for journaling, standups, or sharing with an accountability partner.

- **Developer page** — A `/settings` page showing API base URL, link to OpenAPI docs, curl examples for the toggle endpoint, and wall clock setup instructions.

### Why this matters

Trust is the moat of an indie tool. The moment someone worries "what if I lose my data?" they stop investing. Export, backup, and webhooks turn Beats from a product you use into infrastructure you own.

---

## Phase 8: Delight and Identity — "Make It Yours"

The final layer. After 7 phases of capability, this is pure personality.

### Features

- **Color themes** — 4-5 dark themes beyond the current warm brown/amber: "Midnight" (cool blue/slate), "Forest" (green/dark), "Mono" (pure grayscale), "Sunset" (warm red/orange). Implemented by swapping CSS custom property values. Preference in localStorage.

- **Custom project colors** — User-selectable colors replace the hash-based auto-assignment. A small color picker (8-10 swatches + hex input) in project creation/edit. Falls back to auto-assignment for projects without a chosen color.

- **Layout density** — Three options: Comfortable (current), Compact (smaller fonts, tighter spacing, more visible data), Spacious (larger type, more breathing room). A CSS class on the root adjusts spacing custom properties.

- **Animated empty states** — Replace "No sessions yet" text with small, tasteful SVG animations. A pulsing clock, a sprouting seedling. Sets a tone without being childish.

- **Year-in-review** — Available each January: a scrollable page summarizing the entire previous year. Total hours, project rankings, busiest month, longest streak, work hour distribution. Styled as a typographic poster. Saveable as image.

- **Wall clock theme sync** — When the web theme changes, the wall clock's LED palette matches. The status endpoint includes `theme_accent_rgb`. Energy meter LEDs use the theme's gradient instead of hardcoded colors.

### Why this matters

This is the difference between a tool you respect and a tool you have affection for. The annual review becomes something people anticipate. The custom themes make it feel like home.

---

## Phase Dependencies

```
Phase 1 ──┐
           ├── Phase 3 ── Phase 4 ── Phase 6 ── Phase 7
Phase 2 ──┘                  │
                             └── Phase 5 ── Phase 8
```

- **1 & 2** can run in parallel (data/API vs UI/animation)
- **3** builds on both (animations in install prompt, data for offline)
- **4** needs insights from 1
- **5 & 6** can overlap (firmware vs web with new API models)
- **7** needs notes/tags from 6 to include in exports
- **8** ties everything together

---

*Last updated: 2026-04-06*
