# Companion App Roadmap — From Pairing Hub to Primary Timer

> The companion app becomes the daily driver. Users control timers, see flow state, and receive coaching nudges here. The web UI remains the analytics and configuration surface.

## Philosophy

**Companion = action.** Start/stop timers, see what's running, get nudged.
**Web = reflection.** Heatmaps, weekly reviews, goal tuning, integrations setup.

## Current State (v0.1)

- Pairing via 6-char code
- Connection status (heartbeat)
- Fitbit/Oura integration management
- Dark theme, all 6 platforms

---

## Phase 1 — Timer Control (v0.2)

The core loop: see active timer, start/stop, pick a project.

### API Changes

Add these paths to `DEVICE_ALLOWED_PREFIXES` so the companion (device token) can call them:
- `GET /api/timer/status` — current timer state
- `POST /api/timer/start` — start timer on a project
- `POST /api/timer/stop` — stop the running timer
- `GET /api/device/favorites` — project list for picker (already exists)

### Companion Screens

**Timer Screen (new, becomes home)**
- Large timer display: project name, color dot, elapsed time (updates every second)
- Stop button when timer running
- "What are you working on?" project picker when idle
- Pull-to-refresh for sync

**Project Picker (new)**
- List of non-archived projects with color dots
- Tap to start timer on that project
- Search/filter for users with many projects
- Recent projects pinned at top

### Navigation

- Bottom nav: **Timer** | **Flow** | **Settings**
- Timer tab is the default landing screen
- Settings tab keeps the current pairing/integrations UI

### Data Flow

```
Companion                           API
   │                                 │
   │  GET /api/timer/status          │
   │ ──────────────────────────────> │
   │  {running: true, project, elapsed}
   │ <────────────────────────────── │
   │                                 │
   │  POST /api/timer/stop           │
   │ ──────────────────────────────> │
   │  {beat_id, duration}            │
   │ <────────────────────────────── │
```

### Implementation Notes

- Timer display updates locally every second (no polling). Sync with API on app foreground / every 30s.
- Optimistic UI: stop button disables immediately, confirms with API async.
- Offline: if network is down, queue the start/stop and replay on reconnect (same mutation queue pattern as the web PWA).

---

## Phase 2 — Flow Score & Daily Context (v0.3)

Show the daemon's flow data and today's context.

### Flow Tab

- Current Flow Score: large circular gauge (0–100), color-coded (red < 0.3, amber < 0.7, green >= 0.7)
- Today's flow timeline: horizontal bar chart showing score over time, colored by dominant app category
- Session breakdown: coding 3.2h, browser 1.1h, communication 0.4h (from signal summaries)
- "Your peak hours are 9–11 AM" chronotype badge

### Today's Context Card (on Timer tab)

- Compact card below the timer showing:
  - Today's total tracked time
  - Active intentions and completion status
  - Yesterday's mood (if logged)
  - Next calendar event (if connected)

### API Endpoints Needed

- `GET /api/signals/flow-windows?start=today` — already exists
- `GET /api/signals/summaries?start=today` — already exists
- `GET /api/intentions?date=today` — already exists
- `GET /api/analytics/heatmap` — for daily total (or compute locally)

---

## Phase 3 — Coach & Notifications (v0.4)

The coach speaks through the companion.

### Morning Brief

- Push notification at configured time (e.g., 7 AM)
- Tapping opens a "Brief" card on the Timer tab
- Brief text from `GET /api/coach/brief` (already exists)
- "Start suggested project" button if the brief recommends one

### Evening Review

- Push notification at configured time (e.g., 9 PM)
- Opens a review screen with 3 Socratic questions from `GET /api/coach/review`
- User types short answers → `POST /api/coach/review`
- Mood picker (1–5) at the bottom → `POST /api/daily-notes`

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

## Phase 4 — Intentions & Quick Entry (v0.5)

Light planning without opening the web UI.

### Intentions Screen

- Today's intentions list with completion checkmarks
- "Add intention" quick entry: pick project, set duration (15/30/60/90/120 min)
- Swipe to complete/delete
- Auto-checked when tracked time exceeds planned duration (same logic as web)

### Quick Note

- After stopping a timer, prompt: "How did it go?" with optional note text field
- Tags picker (recent tags + freeform)
- Skip button for fast exit

### Daily Mood

- End-of-day prompt (via notification or in-app): "How was your day?" 1–5 scale
- Stored via `POST /api/daily-notes`

---

## Phase 5 — Widgets & Watch (v0.6)

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

### macOS Menu Bar

- Persistent menu bar icon showing timer state (color dot = project color, or gray when idle)
- Click: dropdown with current timer, elapsed, stop button
- Start timer: submenu of favorite projects

---

## Phase 6 — Biometric Dashboard (v0.7)

Health data visualization in the companion (mobile only).

### Health Tab (replaces Flow tab on mobile, or added as 4th tab)

- Sleep: last night's duration + efficiency, 7-day trend sparkline
- HRV: last night's value, 7-day trend, personal norm line
- Readiness: Oura score if connected, or computed from sleep + HRV
- Steps: today + 7-day average
- Recovery advice: "Your HRV is below your norm — consider a lighter day"

### Data Source

- Reads from `GET /api/biometrics?start=7d_ago&end=today`
- All data already stored by the companion's nightly sync or Fitbit/Oura cron

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
- Need to expand `DEVICE_ALLOWED_PREFIXES` as new endpoints are used
- Consider: session token for read-heavy endpoints (projects, analytics) to avoid expanding device scope too far. Alternative: add a `/api/companion/*` proxy that validates device tokens but provides read access.

### Push Notifications

- **Option A (simple)**: local notifications triggered by background polling. No server infrastructure needed. Limitation: 15-min minimum interval on iOS.
- **Option B (real-time)**: FCM/APNs with a notification service on the API. The API pushes when: brief is generated, review is due, drift is detected, auto-timer suggestion fires. More complex but lower latency.
- Recommend: start with Option A, upgrade to B when notification timing matters.

---

## Priority & Sequencing

| Phase | What | Value | Effort |
|-------|------|-------|--------|
| **1** | Timer control | Users can stop opening the web UI for the core loop | 1 week |
| **2** | Flow + context | Glanceable awareness of current state | 1 week |
| **3** | Coach notifications | The coach reaches users proactively | 1.5 weeks |
| **4** | Intentions + quick entry | Light planning on mobile | 1 week |
| **5** | Widgets + watch | Ambient presence on home screen / wrist | 2 weeks |
| **6** | Biometric dashboard | Health data closes the loop | 1 week |

**Total: ~7.5 weeks for the full vision.**

Phase 1 is the highest-impact — it turns the companion from a setup tool into a daily-use app.
