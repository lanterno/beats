# Companion App Roadmap — From Pairing Hub to Primary Timer

> The companion app is the daily driver. Users control timers, see flow
> state, and receive coaching nudges here. The web UI remains the
> analytics and configuration surface.

**Companion = action.** Start/stop timers, see what's running, get nudged.
**Web = reflection.** Heatmaps, weekly reviews, goal tuning, integrations setup.

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
