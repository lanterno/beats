# Flutter Companion App — `beats-companion`

> Cross-platform companion for Beats. Bridges HealthKit (iOS/iPad) and
> Health Connect (Android) to the Beats API, and serves as the pairing
> hub on all 6 platforms.

## Why

Desktop browsers can't access HealthKit or Health Connect. The companion
app is the bridge that pushes daily biometric data (sleep, HRV, resting
HR, steps, readiness) from your phone or watch to the Beats API, where
it feeds the coach's recovery-aware briefs and chronotype detection.

On desktop (macOS / Windows / Linux), the app provides a native pairing
flow plus Fitbit / Oura OAuth without needing the web UI.

## Shipped

The scaffold lives under `companion/` and CI builds for all 6 platforms
(`.github/workflows/companion.yml`). For the design polish that landed
in parallel, see `companion-ui-design-roadmap.md`; for the notification
work, see `companion-roadmap.md`.

### File layout

```
companion/
├── lib/
│   ├── main.dart
│   ├── screens/
│   │   ├── pairing_screen.dart            ✅ code entry + Scan QR button on iOS/Android
│   │   ├── qr_pairing_screen.dart         ✅ mobile_scanner camera flow; auto-pairs on first valid QR
│   │   ├── home_screen.dart               ✅ status + integrations + brutalist Settings
│   │   ├── timer_screen.dart              ✅ stats row, picker, post-stop note sheet
│   │   ├── flow_screen.dart               ✅ ring, sweep gradient, tap-to-inspect timeline
│   │   ├── coach_screen.dart              ✅ sunrise card, review editor, mood sparkline
│   │   ├── intentions_screen.dart         ✅ progress, quick-add, confetti
│   │   └── health_screen.dart             ✅ 7-day biometric dashboard (reads from API)
│   ├── services/
│   │   ├── api_client.dart                ✅
│   │   ├── secure_store.dart              ✅ SecureStore interface (FlutterSecureStore + MemorySecureStore for tests)
│   │   ├── token_storage.dart             ✅ token in secure storage, URLs in shared_preferences, one-shot migration
│   │   ├── qr_pairing.dart                ✅ pure parser: JSON / beats:// / plain code
│   │   ├── notifications.dart             ✅ flutter_local_notifications wrapper, action-button support
│   │   ├── notification_poller.dart       ✅ brief / review / drift / auto-timer poll loop
│   │   └── tray_service.dart              ✅ desktop menu-bar timer
│   └── theme/                             ✅ palette, typography, embers, grain overlay, confetti
├── android/
│   └── app/src/main/AndroidManifest.xml   ✅ POST_NOTIFICATIONS, SCHEDULE_EXACT_ALARM, CAMERA shipped
├── ios/
│   └── Runner/Info.plist                  ✅ NSCameraUsageDescription shipped
├── macos/   windows/   linux/             ✅ build targets exist
├── pubspec.yaml
└── README.md
```

### Key features

- **Pairing**: 6-char code entry on every platform. iOS / Android also
  expose a "Scan QR code" button that pushes the `mobile_scanner` flow.
  `parseQrPairingPayload` accepts plain 6-char codes,
  `beats://pair/CODE` deep-links, and JSON `{code, api}` blobs (the
  rich form lets a fresh-install device pair without typing the API URL).
- **Token storage**: device token in OS secure storage (Keychain on
  iOS/macOS, EncryptedSharedPreferences on Android, libsecret on Linux,
  DPAPI on Windows) via `flutter_secure_storage`, wrapped behind a
  small `SecureStore` interface so unit tests can inject an in-memory
  implementation. `loadToken()` does a one-shot SharedPreferences →
  secure-storage migration so existing installs aren't logged out.
  URLs stay in plain `shared_preferences` because they're not secrets
  and shouldn't disappear on a Keychain wipe.
- **Desktop Fitbit OAuth**: Settings → Integrations → Fitbit "Connect"
  opens the consent URL in the system browser via `url_launcher`. The
  Fitbit redirect lands on the existing web UI callback
  (`/settings?fitbit=callback`), which exchanges the code for tokens.
  The companion's wait sheet polls `/api/fitbit/status` every 4 s for
  up to 3 minutes and dismisses itself the instant `connected` flips
  to true. A "Check now" button lets the user force a refresh.
- **Notifications**: full free-tier path (brief / review / EOD mood /
  auto-timer / drift), with an in-notification "Start" action button
  for auto-timer suggestions. See `companion-roadmap.md` for details.

### API contract

The companion uses the same device-token auth as the Go daemon. All
endpoints are wired in `api_client.dart` and live on the API:

- `POST /api/device/pair/exchange` — pair (public endpoint)
- `POST /api/device/heartbeat` — keep-alive (device token)
- `POST /api/biometrics/daily` — push daily health data (device token)
  — endpoint and client method exist; nothing calls it yet (waiting on
  HealthKit / Health Connect ingestion)
- `GET /api/fitbit/auth-url` — Fitbit OAuth bootstrap (session token,
  desktop)
- `POST /api/oura/connect` — store Oura PAT (session token, desktop)
- `GET /api/signals/flow-windows` — per-window flow data (device token)
  — used by `FlowScreen` for the timeline + inspector
- `GET /api/signals/flow-windows/summary` — single round-trip aggregate
  (avg / peak / count + top bucket per axis) — used by `FlowScreen`
  to surface the "best repo / best language today" hint under the
  score gauge
- `GET /api/signals/recent-drift` — drift events for the notification
  poller
- `GET /api/signals/pending-suggestions` — pending auto-timer
  suggestions for the notification poller

### Already-installed dependencies

`http`, `shared_preferences`, `flutter_secure_storage`, `mobile_scanner`,
`intl`, `google_fonts`, `system_tray`, `window_manager`,
`flutter_local_notifications`, `flutter_timezone`, `timezone`,
`url_launcher`.

---

## Remaining

Each item is tagged with what blocks it from autonomous code work.

### `[needs-device]` HealthKit / Health Connect ingestion

The companion still doesn't ingest native health data — the Health
screen reads whatever the API has (sourced from Fitbit / Oura today),
not from HealthKit / Health Connect.

What's left:

| File / location | What |
|---|---|
| `lib/services/health_service.dart` | Wrap the `health` package. `requestPermissions()` for `SLEEP_ASLEEP`, `HEART_RATE_VARIABILITY_SDNN`, `RESTING_HEART_RATE`, `STEPS`, `WORKOUT`. `fetchYesterdayData() -> BiometricDay`. |
| `lib/models/biometric_day.dart` | Mirrors the API's `BiometricDay` schema. |
| `lib/screens/health_settings_screen.dart` | Toggles per metric, sync time picker (default 6 AM), manual "Sync now". |
| `android/app/src/main/AndroidManifest.xml` | Health Connect permissions: `<uses-permission android:name="android.permission.health.READ_SLEEP" />`, etc. |
| `ios/Runner/Info.plist` | `NSHealthShareUsageDescription` and `NSHealthUpdateUsageDescription`. |
| Xcode project capability | Enable HealthKit on the iOS target. |

Why blocked: HealthKit / Health Connect runtime behavior (permission
prompts, data availability, source-merge rules, OS denial paths) can
only be validated against a real device with real health data. Headless
CI can compile the package but won't surface the integration bugs.

Dependency to add when picked up: `health: ^11.0.0`.

### `[needs-device]` Background sync

The companion can only push biometrics while it's open. The nightly
background path is unbuilt.

| Platform | What |
|---|---|
| iOS | Register `BGAppRefreshTask` in `AppDelegate.swift` for `com.beats.healthSync`. Either start the Flutter engine headless on trigger (call `health_service.fetchYesterdayData` then POST), or — simpler — read native HealthKit in Swift and POST directly with `URLSession`. |
| Android | `workmanager` plugin: register a periodic task (15 min minimum on Android, schedule for ~6 AM). Callback reads Health Connect data and POSTs. |

Why blocked: same as above plus iOS `BGTaskScheduler` and Android Doze
behavior change between app states and OS versions; no way to verify
this works without a real device cycling through background lifecycle.

Dependency to add when picked up: `workmanager: ^0.5.2`.

### `[needs-device]` Native widgets and Apple Watch

See `companion-roadmap.md` § Native widgets and Apple Watch.

### `[needs-paid-credentials]` APNs / FCM real-time push

See `companion-roadmap.md` § Server-pushed delivery.

### `[external-resource]` Web-side QR generator

The mobile companion's QR scanner is ready; the web Settings → Daemon
page should display a QR encoding `{"code": "<6char>", "api": "<base-url>"}`
so a fresh-install device pairs without typing the API URL. This is a
React/UI change in `ui/`, not in the companion.

---

## Data flow (post-HealthKit / Health Connect)

```
Phone/Watch → HealthKit/Health Connect
                    ↓
            Companion App (Flutter)
                    ↓ (nightly background task)
            POST /api/biometrics/daily
                    ↓
            Beats API (MongoDB)
                    ↓
            Coach context + Chronotype + Insight cards
                    ↓
            Web UI (morning brief, Settings)
```

## Privacy

- Health data stays on the device until the nightly sync. Only
  aggregated daily totals are sent.
- No continuous tracking — one read per day for yesterday's data.
- The user can delete all biometric data from the web UI
  (Settings → Biometrics → Delete all).
- HealthKit / Health Connect permissions can be revoked at any time
  in system settings.

## Distribution

- **iOS / iPad**: TestFlight → App Store. Requires Apple Developer
  account.
- **Android**: Internal testing → Play Store. Requires Google Play
  Console.
- **macOS / Windows / Linux**: GitHub releases (`.dmg`, `.msix`,
  `.AppImage`). Flutter's build commands produce these directly.

## Notes

- The app is intentionally minimal on the data side — it's a bridge
  for biometrics, not a second analytics dashboard. Visualization
  beyond the 7-day summary lives in the web UI.
- If a user has both HealthKit and Fitbit, the API handles dedup by
  source priority (HealthKit > Oura > Fitbit).
- Apple Watch is out of scope for this app — see
  `companion-roadmap.md` § Native widgets and Apple Watch.
