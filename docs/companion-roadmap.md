# Companion App Roadmap — From Pairing Hub to Primary Timer

> The companion app is the daily driver. Users control timers, see flow
> state, and receive coaching nudges here. The web UI remains the
> analytics and configuration surface.

**Companion = action.** Start/stop timers, see what's running, get nudged.
**Web = reflection.** Heatmaps, weekly reviews, goal tuning, integrations setup.

## Shipped

### Core experience
- Pairing via 6-char code (and QR scan on iOS / Android — see `flutter-companion.md`)
- Connection heartbeat, Fitbit / Oura integration management, desktop
  Fitbit OAuth via `url_launcher`
- Timer control: start/stop, project picker with **RECENT** section,
  custom start/stop times, post-stop "How did it go?" note + tags +
  skip sheet, today/week/streak stats row, week-over-week delta arrow,
  accidental-stop shake guard
- Flow score gauge with breathing glow ≥ 0.7, sweep-gradient ring,
  tap-to-inspect timeline (time / score / category / editor repo +
  branch), animated category bars
- Coach: morning brief in a sunrise-gradient card with grain overlay
  and HH:MM timestamp, evening review with editable text answers
  (`POST /api/coach/review`) + "X OF N ANSWERED" progress, daily mood
  picker with 1.0 → 1.2 → 1.0 bounce, "What went well?" debounce-saving
  note, 7-day mood sparkline
- Intentions: top progress bar, color-bar accent, live add-preview,
  quick-add row of recent combos, 6-particle confetti burst on
  completion
- Health: 7-day biometric dashboard (sleep / HRV / resting HR / steps /
  readiness) with sparkline metric cards, sourced from API today —
  native ingestion is separate (see `flutter-companion.md`)
- 6-tab frosted-glass bottom nav with stagger-in transitions, dark
  theme, all 6 platforms

### Notifications
Free-tier path (no APNs / FCM, no Apple Developer / Google Play
projects required), all delivered via `flutter_local_notifications`:

| Prompt | Source | Delivery |
|---|---|---|
| Morning brief | Foreground poll, 5 min cadence | `notifyBriefAvailable` on a new `id` from `/api/coach/brief/today`, dedupe per-day |
| Evening review | Foreground poll, 5 min cadence | `notifyReviewAvailable` on a new review `date`, dedupe per-day |
| EOD mood prompt | OS-scheduled | `zonedSchedule` daily at user-configured time — fires even when the app isn't running |
| Auto-timer suggestion | Foreground poll | `notifyAutoTimerSuggestion` for any new `PendingSuggestion` from `GET /api/signals/pending-suggestions`, dedupe by id |
| Drift alert | Foreground poll | `notifyDriftAlert` for any new drift event from `GET /api/signals/recent-drift`, dedupe by id; bundle id resolves to a friendly label via `driftAppLabel` |

**Auto-timer "Start" action button** — Android `AndroidNotificationAction`
+ iOS `DarwinNotificationCategory` with foreground option. Tapping fires
a `NotificationTap` with `actionId == kStartAutoTimerActionId`; the main
app's tap router parses `auto-timer:<id>|<name>` via
`parseAutoTimerPayload` and POSTs `/api/timer/start` directly — no
screen opens, just a confirmation snackbar.

**Daemon-side parallel notifications** (desktop): the daemon's
`autotimer` and `shield` modules also fire native notifications via
`osascript` (macOS), `notify-send`/libnotify-bin (Linux), and PowerShell
`ToastNotification` (Windows). Companion + daemon fire in parallel —
different channels, same prompt — so users always get the prompt
regardless of which surface is active.

### Tray (macOS / Windows / Linux)
- Live elapsed time + project label in the menu bar
- Quick-start submenu of recent projects, Stop, Open, Quit
- Tray icon renders a colored dot matching the running project (gray
  when idle), cached on disk by hex via `TrayIconRenderer`

---

## Remaining

Each item is tagged with what blocks it from autonomous code work.

### `[needs-device]` Native widgets and Apple Watch

Glanceable-info surfaces that live outside the Flutter app proper.

- **iOS Widgets (WidgetKit)** — separate Xcode target. Small variant:
  current project + elapsed time, or "No timer" + last session.
  Medium: + today total + flow score gauge. Tap opens app to Timer.
- **Android Widgets (Glance / AppWidget)** — separate Kotlin source
  set. Same content as iOS.
- **Apple Watch (WatchOS Companion)** — separate WatchOS target.
  Complication shows elapsed / daily total; watch app exposes
  start/stop + favorites picker. Uses `WatchConnectivity` to share
  the device token from the phone.

Each requires a real device to validate rendering, lifecycle, and
storage-sync behavior — can't be done in headless CI.

### `[needs-paid-credentials]` Server-pushed delivery

- **APNs / FCM real-time push** — would solve the "app must be alive"
  limitation (today: brief and review notifications only fire while
  the app is alive or recently backgrounded). Requires an Apple
  Developer account + an FCM project, plus a server-side notification
  service in the API. Out of scope for the free-tier path.

---

## Architecture notes (for when the above gets picked up)

### Push notification delivery options

- **Option A — local notifications** (current): foreground poll +
  OS-scheduled prompts. No server infra, no platform credentials.
  Limitation: 5-min minimum poll latency, app-must-be-alive for poll
  prompts. Shipped.
- **Option B — server push**: FCM/APNs notification service on the API
  that pushes when brief is generated, review is due, drift detected,
  auto-timer suggestion fires. Lower latency, app-state-independent.
  See `[needs-paid-credentials]` above.

### State management

- `provider` or `riverpod` for reactive state when complexity warrants
- `TimerState`, `FlowState`, `CoachState` as the obvious split
- Today the screens use plain `setState` + service callbacks; works
  fine at current screen count

### Offline support (not yet built)

- SQLite local cache for projects, recent beats, intentions
- Mutation queue (mirrors the web's IndexedDB queue): start/stop /
  intention changes queued when offline, replayed on reconnect
- Timer runs locally when offline — syncs the beat on reconnect

### Auth model

- Device token from pairing now sits in OS secure storage (Keychain /
  EncryptedSharedPreferences / libsecret / DPAPI) via
  `flutter_secure_storage` — see `flutter-companion.md` for the
  migration story and the `SecureStore` interface
- All API calls send `Authorization: Bearer <device_token>`
- `DEVICE_ALLOWED_PREFIXES` covers timer, projects, coach, intentions,
  daily-notes, signals, biometrics — append as new endpoints land
