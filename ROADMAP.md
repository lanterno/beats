# Beats Roadmap

> All planned phases (1-12) are implemented. This document tracks what was built.

---

## Completed Phases

| Phase | What | Status |
|-------|------|--------|
| 1-8 | Core tracking, analytics, planning, platform, auth, infra | Done |
| 9 | Intelligence — weekly digests, productivity score, patterns, smart plan, focus scores | Done |
| 10 | Context — calendar overlay, git correlation, untracked gaps, auto-start rules, daily webhook | Done |
| 11 | Rituals — weekly planning, recurring intentions, morning briefing, weekly review, streaks | Done |
| 12 | Presence — ESP32 firmware with e-ink, 3-button, LED strip, pomodoro, dock mode | Done |

## v1 Polish (all complete)

- [x] Richer stop toast with daily average comparison
- [x] Background sync — offline event queue surviving tab close
- [x] Wall clock multi-project switching — double-press cycling
- [x] Wall clock ambient progress — periodic status polling

## What needs external setup

| Feature | Requires |
|---------|----------|
| Google Calendar | `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` env vars |
| GitHub correlation | `GITHUB_TOKEN` env var |
| Daily summary auto-trigger | External cron hitting `POST /api/webhooks/daily-summary/trigger` |
| Wall clock | ESP32 hardware + PlatformIO toolchain |

---

*Last updated: 2026-04-14*
