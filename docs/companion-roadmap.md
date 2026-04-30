# Companion App Roadmap — From Pairing Hub to Primary Timer

> The companion app becomes the daily driver. Users control timers, see flow state, and receive coaching nudges here. The web UI remains the analytics and configuration surface.

## Philosophy

**Companion = action.** Start/stop timers, see what's running, get nudged.
**Web = reflection.** Heatmaps, weekly reviews, goal tuning, integrations setup.

## Current State

- Pairing via 6-char code
- Connection status (heartbeat)
- Fitbit/Oura integration management
- Timer control: start/stop, project picker, custom start/stop times
- Flow score gauge, today's timeline, activity-category breakdown
- Coach screen: morning brief, evening review questions, daily mood picker
- Intentions screen: today's plan with progress bar, add/toggle/complete
- Health screen: 7-day biometric dashboard (sleep, HRV, resting HR, steps, readiness)
- 6-tab frosted-glass bottom nav (Timer / Flow / Plan / Coach / Health / Settings)
- Dark theme, all 6 platforms

---

## Phase 3 — Coach Notifications

The coach speaks through the companion. Coach content is already rendered in-app — this phase makes it reach the user without opening the app.

### Morning Brief

- Push notification at configured time (e.g., 7 AM)
- Tapping opens the Coach tab
- "Start suggested project" button if the brief recommends one

### Evening Review

- Push notification at configured time (e.g., 9 PM)
- Opens the Coach tab with the review questions focused
- Question cards need to expand into editable text inputs (currently read-only) so answers can `POST /api/coach/review`

### Auto-Timer Notifications

- When the daemon detects high flow without a timer: push notification "Start tracking Beats?"
- Tap → starts the matched project's timer directly from the notification
- Requires: iOS APNs / Android FCM setup, or local notifications triggered by polling `/api/signals/suggest-timer`

### Drift Alerts

- When the daemon logs a drift event: push notification "You've been on Twitter for 2 min while Beats is tracking"
- Non-blocking — just awareness. No action required.

### Implementation Notes

- **iOS**: local notifications via `flutter_local_notifications` plugin. Background fetch every 15 min checks for new briefs/suggestions.
- **Android**: same plugin. WorkManager for background checks.
- **Desktop**: system tray notifications (macOS: `NSUserNotification`, Linux: `libnotify`, Windows: toast).

---

## Phase 4 — Quick Entry Polish

The Intentions screen exists. Two small flows still missing:

### Quick Note After Stop

Shipped. After stopping a timer, the companion shows a "How did it go on \<project\>?" bottom sheet with a multiline note field, a freeform comma/space-separated tags input, and Skip / Save actions; Save updates the just-stopped beat in place via PUT `/api/beats/`. No tag suggestions yet — recent-tags chips are a future polish.

### End-of-Day Mood Prompt

- The mood picker lives on the Coach tab today; it should also surface as a notification or in-app prompt at the configured end-of-day time
- Stored via `POST /api/daily-notes` (already wired)

---

## Phase 5 — Widgets & Watch

Native platform integration for glanceable info.

### iOS Widgets (WidgetKit)

- **Small**: current project name + elapsed time, or "No timer" with last session
- **Medium**: timer + today's total + flow score gauge
- Tap opens the app to Timer tab

### Android Widgets (Glance/AppWidget)

- Same as iOS: timer status + daily total

### Apple Watch (WatchOS Companion)

- Complication: elapsed time or daily total
- Watch app: start/stop timer, project picker (favorites only)
- Uses WatchConnectivity to share device token with the phone app

### macOS Menu Bar Polish

The tray (`tray_service.dart`) shows live elapsed time + project, a Start Timer submenu of recent projects, Stop Timer, Open Beats, and Quit. The icon now renders a colored dot matching the running project (gray when idle), via PNGs cached under the OS temp dir by `TrayIconRenderer`. No further menu-bar polish pending.

---

## Technical Architecture

### State Management

- Use `provider` or `riverpod` for reactive state
- `TimerState`: `{running, projectId, projectName, projectColor, startTime, elapsed}`
- `FlowState`: `{currentScore, todayWindows[], todaySummary}`
- `CoachState`: `{brief, reviewQuestions[], unreadCount}`

### Offline Support

- SQLite local cache for projects, recent beats, intentions
- Mutation queue (same concept as web's IndexedDB queue): start/stop/intention changes queued when offline, replayed on reconnect
- Timer runs locally even when offline — syncs the beat on reconnect

### Auth Model

- Device token (from pairing) stored in SharedPreferences
- All API calls use `Authorization: Bearer <device_token>`
- `DEVICE_ALLOWED_PREFIXES` already covers timer, projects, coach, intentions, daily-notes, signals, biometrics. Expand as new endpoints are needed.
- Consider: session token for read-heavy endpoints (analytics) to avoid expanding device scope too far. Alternative: add a `/api/companion/*` proxy that validates device tokens but provides read access.

### Push Notifications

- **Option A (simple)**: local notifications triggered by background polling. No server infrastructure needed. Limitation: 15-min minimum interval on iOS.
- **Option B (real-time)**: FCM/APNs with a notification service on the API. The API pushes when: brief is generated, review is due, drift is detected, auto-timer suggestion fires. More complex but lower latency.
- Recommend: start with Option A, upgrade to B when notification timing matters.

---

## Priority & Sequencing

| Phase | What | Value | Effort |
|-------|------|-------|--------|
| **3** | Coach notifications | The coach reaches users proactively | 1.5 weeks |
| **4** | EOD mood prompt (post-stop note ✅) | Frictionless capture around timer events | 0.25 week |
| **5** | Widgets + watch (menu bar polish ✅) | Ambient presence on home screen / wrist | ~1.5 weeks |

**Total: ~3.25 weeks for the remaining vision.**
