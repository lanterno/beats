# Beats Roadmap

> A personal time tracking tool that's more than just a timer.
> Beats lives on your desk, in your browser, and in your pocket — helping you understand how you spend your time and make better choices about it.

---

## What's been built

Beats is a mature, full-featured time tracker with three surfaces: a React SPA, a FastAPI backend, and an ESP32 wall clock. The foundation is strong:

- **Tracking** — Timer with start/stop, manual logging, session notes, tags, project goals (target and cap modes with per-week overrides)
- **Analytics** — Contribution heatmap, daily rhythm chart, streak tracker, monthly retrospective, year-in-review, weekly comparison, session stats
- **Planning** — Daily intentions with auto-completion, end-of-day review with mood tracking, focus mode
- **Hardware** — Device API endpoints (status, favorites, heartbeat) with RGB color mapping and energy meter logic — firmware not yet implemented
- **Platform** — PWA with offline timer, install prompt, forgotten-timer notifications, keyboard shortcuts, five themes, three density modes
- **Integration** — Webhooks, CSV/JSON export and import, developer settings page
- **Auth** — WebAuthn passkeys, JWT sessions
- **Infra** — Cloud Run + Firebase Hosting, Cloud Build CI/CD, zero-cost deployment

### Remaining polish from v1

- [ ] Richer stop toast — add daily average comparison
- [ ] Background sync — offline event queue surviving tab close
- [ ] Wall clock multi-project switching — firmware double-press cycling
- [ ] Wall clock ambient progress — firmware periodic status polling

---

## What's next

The first eight phases built a complete tool. The next four make it *intelligent*, *connected*, *habitual*, and *tangible*. Each phase is 2-4 sessions.

---

## Phase 9: Intelligence — "What Does It Mean?" ✅ Complete

All five features shipped — API endpoints in `intelligence.py`, UI components on the dashboard and insights pages.

- **Weekly digest** — `WeeklyDigest` model, `/api/intelligence/digests` endpoints, UI at `/insights/digests`. Includes total hours, top project, vs-last-week delta, streaks, observations.
- **Productivity score** — 0-100 composite (consistency, intentions, goals, quality). `/api/intelligence/score` + `ProductivityScore` dashboard component with hoverable breakdown.
- **Pattern detection** — `detect_patterns()` surfaces day-of-week trends, peak-hour analysis, stale projects, mood correlations. Dismissible `PatternCards` on insights page.
- **Smart daily plan** — `suggest_daily_plan()` recommends up to 3 projects with durations based on day-of-week patterns, recent activity, and unmet weekly goals. Integrated into `TodaysPlan` component.
- **Focus quality indicator** — `compute_focus_scores()` scores each session on duration, time-of-day, and fragmentation. Shown as color-coded dots on session cards in `TodayFeed`.

---

## Phase 10: Context — "Where Does Time Go?"

Right now, Beats knows you worked 3 hours. It doesn't know you were in meetings for 2 of them. This phase connects Beats to the systems where your time actually happens.

### Features

- **Calendar overlay** — Connect Google Calendar (OAuth2, read-only). On the project detail timeline view, calendar events appear as translucent blocks behind your tracked sessions. Instantly see: "I was in meetings from 10-12 but only tracked 30 minutes — the rest was untracked." No auto-logging, just visibility.

- **Git activity correlation** — Optional GitHub integration. On project detail, show commit count alongside tracked time. "You made 12 commits during 4.2h of tracked work on this project." Helps calibrate whether tracked time reflects actual output. Configured per-project: link a GitHub repo to a Beats project.

- **Untracked time report** — A new section on the daily view: gaps between sessions, highlighted. "11:00-13:30 — 2.5h untracked." If calendar is connected, show what was scheduled during gaps. Not judgmental — just awareness.

- **Auto-start rules** — Simple triggers: "When I push to repo X, start timer on Project Y" (via existing webhook infrastructure, reversed). "Start timer at 9 AM on weekdays for Project Z." Rules engine is just cron + webhook, no daemon.

- **Daily summary webhook** — At end of day, POST a structured summary to a configured URL. Enables Slack bot integration, daily standup notes, journaling tools. Format: project breakdown, total hours, completed intentions, daily note.

### Why this matters

Time tracking in isolation is only half the picture. Calendar overlay alone answers the question every knowledge worker has: "Where did my day go?" — without requiring you to track meetings separately.

---

## Phase 11: Rituals — "Make It a Practice"

The best productivity system is the one you actually use. This phase turns Beats into a daily and weekly habit with minimal friction.

### Features

- **Weekly planning view** — A new `/plan` page, available Sunday evening or Monday morning. Shows last week's summary side-by-side with an empty week template. Set project-level time budgets for the week. Drag to rebalance. Saves as `WeeklyPlan` and feeds the smart daily plan suggestions.

- **Recurring intentions** — Templates for daily intentions: "Every weekday, plan 2h for Deep Work." Auto-creates intentions each morning. Editable per-day. Managed in settings.

- **Morning briefing** — When you open Beats for the first time each day, a brief overlay: yesterday's summary (hours, completed intentions, mood), today's auto-created intentions, and any weekly goal warnings ("You need 4h on Project X to hit your weekly target — you have 2 days left").

- **Review workflow** — End-of-day review gets a companion: weekly review. Friday/Sunday prompt walks through the week: what went well, what didn't, what to change next week. Stored alongside `WeeklyDigest`. The monthly retrospective pulls from these notes.

- **Intention streaks** — Track consecutive days where you completed all intentions. Separate from activity streaks. "You've hit your daily plan 12 days in a row." A meta-habit for the habit.

### Why this matters

Features 1-8 built a capable tracker. But a tracker you check once a week isn't a practice. Morning briefing + evening review + weekly planning creates a rhythm. The tool becomes part of how you start and end each day.

---

## Phase 12: Presence — "The Desk Companion"

The wall clock is Beats' most distinctive feature, but it's currently a $35 toggle switch. This phase makes it a desk companion you glance at fifty times a day.

### Features

- **E-ink daily dashboard** — Add a small e-ink display (2.9" Waveshare, ~$15) to the wall clock. Shows: current project name, elapsed time, today's total, weekly goal progress bar, next calendar event (if connected). Updates every 60 seconds. Readable from across the room. Low power — e-ink holds image without power.

- **Multi-button interaction** — Replace the single toggle with a 3-button layout: Start/Stop (main), Next Project (cycle through favorites), and Mode (toggle between clock display, today's summary, weekly progress). Physical buttons are faster than reaching for your phone.

- **Ambient color coding** — The LED strip becomes a progress bar. LED 1-7 fill up as daily hours accumulate. Color shifts from project color (active) to a muted palette (idle). A long fade animation on stop makes the transition feel intentional.

- **Pomodoro mode** — Long-press Mode button to enter a 25-minute focused session. E-ink shows a countdown. LEDs pulse gently. At completion, the display shows "Break?" and the button pauses for 5 minutes. Simple, physical, no phone required.

- **Charging dock display** — When plugged in and charging, the e-ink shows a minimal clock face with today's total hours. The wall clock becomes a desk clock at night. Battery percentage shown in corner.

### Why this matters

The physical device is what makes Beats different from every other time tracker. An e-ink display transforms it from "button that talks to an API" into "ambient information display that happens to have a button." You glance at it like a watch — and it tells you about your day.

---

## Phase Dependencies

```
v1 (Phases 1-8) ── Phase 9 ✅ ── Phase 11
                       │
                       └── Phase 10
                              │
Phase 12 (independent) ───────┘ (calendar events on e-ink)
```

- **9** (Intelligence) — **complete**, unblocks 10 and 11
- **10** (Context) benefits from 9's pattern detection for smarter gap analysis
- **11** (Rituals) needs 9's weekly digest and smart suggestions
- **12** (Presence) is mostly independent firmware work, but calendar overlay from 10 feeds the e-ink display

---

*Last updated: 2026-04-14*
