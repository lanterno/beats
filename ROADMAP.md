# Beats Roadmap

> What remains to be built. Phases 1-9 are complete.

---

## Remaining polish from v1

- [ ] Richer stop toast — add daily average comparison
- [ ] Background sync — offline event queue surviving tab close
- [ ] Wall clock multi-project switching — firmware double-press cycling
- [ ] Wall clock ambient progress — firmware periodic status polling

---

## Phase 10: Context — "Where Does Time Go?"

Connect Beats to the systems where time actually happens.

- **Calendar overlay** — Google Calendar (OAuth2, read-only). Calendar events appear as translucent blocks behind tracked sessions on the project detail timeline. Visibility into untracked meeting time without auto-logging.

- **Git activity correlation** — Optional GitHub integration. Show commit count alongside tracked time on project detail. Configured per-project: link a GitHub repo to a Beats project.

- **Untracked time report** — Gaps between sessions highlighted on the daily view. If calendar is connected, show what was scheduled during gaps.

- **Auto-start rules** — Simple triggers: "When I push to repo X, start timer on Project Y" (via existing webhook infrastructure, reversed). "Start timer at 9 AM on weekdays for Project Z." Cron + webhook, no daemon.

- **Daily summary webhook** — End-of-day POST to a configured URL. Project breakdown, total hours, completed intentions, daily note. Enables Slack bot, standup notes, journaling tools.

---

## Phase 11: Rituals — "Make It a Practice"

Turn Beats into a daily and weekly habit with minimal friction.

- **Weekly planning view** — `/plan` page, available Sunday evening or Monday morning. Last week's summary side-by-side with an empty week template. Set project-level time budgets, drag to rebalance. Saves as `WeeklyPlan` and feeds smart daily plan suggestions.

- **Recurring intentions** — Templates: "Every weekday, plan 2h for Deep Work." Auto-creates intentions each morning. Editable per-day. Managed in settings.

- **Morning briefing** — First open each day shows a brief overlay: yesterday's summary, today's auto-created intentions, weekly goal warnings.

- **Review workflow** — Weekly review companion to end-of-day review. Friday/Sunday prompt: what went well, what didn't, what to change. Stored alongside `WeeklyDigest`. Monthly retrospective pulls from these notes.

- **Intention streaks** — Consecutive days with all intentions completed. Separate from activity streaks.

---

## Phase 12: Presence — "The Desk Companion"

Build the ESP32 wall clock firmware and expand it into an ambient desk companion. The device API endpoints already exist (`/api/device/status`, `/api/device/favorites`, `/api/device/heartbeat`).

- **Base firmware** — ESP32 Arduino firmware: WiFi connection, API polling, single-button start/stop toggle, project-colored LED strip, energy meter (LED 1-7 fill with daily hours).

- **E-ink daily dashboard** — 2.9" Waveshare e-ink display. Shows current project, elapsed time, today's total, weekly goal progress bar, next calendar event. Updates every 60 seconds.

- **Multi-button interaction** — 3-button layout: Start/Stop, Next Project (cycle favorites), Mode (clock / today's summary / weekly progress).

- **Ambient color coding** — LED strip as progress bar. Color shifts from project color (active) to muted palette (idle). Fade animation on stop.

- **Pomodoro mode** — Long-press Mode for 25-minute focused session. E-ink countdown, gentle LED pulse, break prompt on completion.

- **Charging dock display** — Plugged-in mode: minimal clock face with today's total hours. Battery percentage in corner.

---

## Phase Dependencies

```
Phase 10 (Context)  ─── Phase 11 (Rituals)
       │
Phase 12 (Presence) ────┘ (calendar events on e-ink)
```

- **10** and **11** can start now — Phase 9's intelligence layer is in place
- **12** is mostly independent firmware work, but calendar overlay from 10 feeds the e-ink display

---

*Last updated: 2026-04-14*
