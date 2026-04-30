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

### Shipped — local notifications, free-tier path

`NotificationsService` + `NotificationPoller` (in `companion/lib/services/`)
deliver coach prompts using only OS-level local notifications. No APNs,
no FCM, no Apple Developer / Google Play projects required.

| Prompt | Delivery |
|---|---|
| **Morning brief** | Foreground polling every 5 min — fires `notifyBriefAvailable` when `/api/coach/brief/today` returns a new id. Deduped per-day in `SharedPreferences`. |
| **Evening review** | Same poller — `notifyReviewAvailable` on a new review's `date` key. |
| **EOD mood prompt** | OS-scheduled (`zonedSchedule`, `matchDateTimeComponents: time`). Fires daily at the user-configured time (default 21:00) **even when the app isn't running**. Configured from Settings → NOTIFICATIONS. |

Tapping any of these payloads switches the app to the Coach tab.

### Trade-off the free-tier path makes

Brief and review prompts only fire while the app is alive (foreground or
recently-backgrounded). If the user closes the app and the coach generates
a brief at 7 AM, they'll see the notification on next open instead. The
EOD mood prompt is the one piece that reaches them while the app is
closed, because it's pre-scheduled at the OS level rather than triggered
by a server check.

### Also shipped — daemon-side notifications (macOS)

The daemon's `autotimer` and `shield` modules both fire native macOS
notifications via `osascript` while running:

- **Auto-timer suggestion**: 8 consecutive 1-minute flow windows ≥ 0.7
  with a category match against an `autostart_repos` project triggers
  "Start tracking?". Wired through `daemon/internal/autotimer/suggest.go`.
- **Drift alert**: 30s+ continuous time on a known-distraction bundle
  (Twitter, Spotify, Discord, etc.) while a timer is running fires
  "Drift detected". Wired through `daemon/internal/shield/shield.go`,
  with the timer-running state cached from `/api/signals/timer-context`
  on a 30s poller.

Linux/Windows fall through to a log line — extending those to native
notifications (libnotify / Win toast) is a small follow-up.

### Still pending

- **"Start suggested project" action button** on the brief notification
- **Companion-side auto-timer + drift notifications** — daemon notifies
  on the desktop today, but mobile users only see prompts when the
  companion poller runs. This needs either a daemon→companion bridge
  or server-side push.
- **True server-pushed delivery** via APNs/FCM — would solve the
  "app must be alive" limitation but needs an Apple Developer account
  and an FCM project. Out of scope for the free-tier path.

---

## Phase 4 — Quick Entry Polish

The post-stop "How did it go?" prompt is shipped (note + freeform tags + skip; updates the just-stopped beat in place via `PUT /api/beats/`).

The **EOD mood prompt** is also shipped — see Phase 3. A daily local notification at the user-configured time opens the Coach tab where the existing mood picker + "What went well?" note land in the day's `daily-note`.

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
| **3** | Coach notifications (free-tier path ✅) | The coach reaches users proactively | 0.5 week (server-push extras) |
| **4** | EOD mood prompt + post-stop note ✅ | — | 0 |
| **5** | Widgets + watch (menu bar polish ✅) | Ambient presence on home screen / wrist | ~1.5 weeks |

**Total: ~2 weeks for the remaining vision** — and the bulk is widgets / watch / server-push, all of which need real devices or paid platform credentials.
