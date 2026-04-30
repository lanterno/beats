# Flutter Companion App — `beats-companion`

> Cross-platform companion for Beats. Bridges HealthKit (iOS/iPad) and Health Connect (Android) to the Beats API. Serves as pairing hub on all 6 platforms.

## Why

Desktop browsers can't access HealthKit or Health Connect. The companion app is the bridge that pushes daily biometric data (sleep, HRV, resting HR, steps, readiness) from your phone/watch to the Beats API, where it feeds the coach's recovery-aware briefs and chronotype detection.

On desktop (macOS/Windows/Linux), the app provides a native pairing flow and Fitbit/Oura OAuth without needing the web UI.

## Current State

The scaffold is in place under `companion/` and CI builds for all 6 platforms (`.github/workflows/companion.yml`). Pairing, heartbeat, Fitbit status display, and Oura PAT connect/disconnect are wired up. Token storage uses `shared_preferences` (intentional — `flutter_secure_storage` was tried and reverted because it broke the macOS sandbox setup).

What still needs building: HealthKit / Health Connect ingestion, background sync, QR-code pairing, and desktop Fitbit OAuth.

## Architecture (target)

```
companion/
├── lib/
│   ├── main.dart                       ✅ in place
│   ├── screens/
│   │   ├── pairing_screen.dart         ✅ desktop code entry (QR scan still TODO for mobile)
│   │   ├── home_screen.dart            ✅ status + integrations
│   │   ├── health_settings_screen.dart ⬜ metric toggles, push schedule
│   │   └── timer/flow/coach/intentions/health  ✅
│   ├── services/
│   │   ├── api_client.dart             ✅
│   │   ├── token_storage.dart          ✅ shared_preferences (chosen over secure_storage for sandbox compat)
│   │   ├── health_service.dart         ⬜ HealthKit/Health Connect via `health` pkg
│   │   └── background_sync.dart        ⬜ platform-specific nightly push
│   └── models/
│       └── biometric_day.dart          ⬜ mirrors API's BiometricDay schema
├── android/
│   └── app/src/main/AndroidManifest.xml  ⬜ Health Connect permissions
├── ios/
│   ├── Runner/Info.plist                 ⬜ HealthKit usage descriptions
│   └── Runner/AppDelegate.swift          ⬜ BGTaskScheduler registration
├── macos/   windows/   linux/             ✅ build targets exist
├── pubspec.yaml
└── README.md
```

## Platform Capabilities

| Platform | Health data | Background sync | Pairing |
|----------|-----------|-----------------|---------|
| iOS/iPad | HealthKit (sleep, HRV, resting HR, steps, workouts) | `BGTaskScheduler` via Swift method channel | QR scan |
| Android | Health Connect (sleep, heart rate, steps, exercise) | `WorkManager` via `workmanager` plugin | QR scan |
| macOS | None | N/A | Pairing code text entry ✅ |
| Windows | None | N/A | Pairing code text entry ✅ |
| Linux | None | N/A | Pairing code text entry ✅ |

## Dependencies to Add

Already present: `http`, `shared_preferences`, `intl`, `google_fonts`, `system_tray`, `window_manager`.

Still needed for the remaining work:

```yaml
dependencies:
  health: ^11.0.0              # Unified HealthKit + Health Connect
  mobile_scanner: ^5.0.0       # QR scanning (iOS/Android only)
  workmanager: ^0.5.2          # Android background tasks
```

## Remaining Implementation Steps

### Phase 2: Health Integration (~4 days)

1. **Health service** (`health_service.dart`): wrap the `health` package.
   - `requestPermissions()` → request HealthKit/Health Connect read access for: `SLEEP_ASLEEP`, `HEART_RATE_VARIABILITY_SDNN`, `RESTING_HEART_RATE`, `STEPS`, `WORKOUT`.
   - `fetchYesterdayData() -> BiometricDay` → read yesterday's data, aggregate to a single `BiometricDay`.
2. **Health settings screen**: toggle which metrics to sync, choose sync time (default: 6 AM).
3. **Manual sync**: button on home screen to trigger an immediate sync.

### Phase 3: Background Sync (~2 days)

4. **iOS background sync**:
   - Register `BGAppRefreshTask` in `AppDelegate.swift` for `com.beats.healthSync`.
   - On trigger: start Flutter engine headless, call `health_service.fetchYesterdayData()`, POST to API.
   - Alternative (simpler): keep the health read in native Swift, POST directly with `URLSession`. This avoids starting the Flutter engine in background.

5. **Android background sync**:
   - Use `workmanager` plugin to register a periodic task (minimum 15 min interval on Android, schedule for ~6 AM).
   - The callback reads Health Connect data and POSTs to the API.

### Phase 4: Desktop Features (~1 day)

6. ✅ **Fitbit OAuth on desktop** — shipped. Settings → Integrations → Fitbit "Connect" opens the consent URL in the system browser via `url_launcher`. The Fitbit redirect lands on the existing web UI callback (`/settings?fitbit=callback`), which exchanges the code for tokens. The companion's wait sheet polls `/api/fitbit/status` every 4s for up to 3 minutes and dismisses itself the instant `connected` flips to true. A "Check now" button lets the user force a refresh if the auto-poll misses.
7. **QR pairing on mobile**: replace the code-entry input with `mobile_scanner` on iOS/Android (keep code entry as fallback).

## Data Flow

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

## API Contract

The companion uses the same device token auth as the Go daemon. All endpoints are wired in `api_client.dart` and live on the API:

- `POST /api/device/pair/exchange` — pair (public endpoint)
- `POST /api/device/heartbeat` — keep-alive (device token)
- `POST /api/biometrics/daily` — push daily health data (device token) — endpoint and client method exist; nothing calls it yet (waiting on `health_service.dart`)
- `GET /api/fitbit/auth-url` — initiate Fitbit OAuth (session token, desktop) — endpoint and client method exist; not yet invoked by a desktop OAuth UI
- `POST /api/oura/connect` — store Oura PAT (session token, desktop)

## Privacy

- Health data stays on the device until the nightly sync. Only aggregated daily totals are sent.
- No continuous tracking — one read per day for yesterday's data.
- The user can delete all biometric data from the web UI (Settings → Biometrics → Delete all).
- HealthKit/Health Connect permissions can be revoked at any time in system settings.

## Testing

- **Widget tests**: pairing flow, health settings toggles.
- **Integration test**: mock `health` package → verify `BiometricDay` is correctly assembled.
- **Manual test matrix**: iOS 17+, Android 14+ (Health Connect), macOS 14+, Ubuntu 24.04.

## Distribution

- **iOS/iPad**: TestFlight → App Store. Requires Apple Developer account.
- **Android**: Internal testing → Play Store. Requires Google Play Console.
- **macOS/Windows/Linux**: GitHub releases (`.dmg`, `.msix`, `.AppImage`). Flutter's build commands produce these directly.

## Notes

- The app is intentionally minimal on the data side — it's a bridge for biometrics, not a second analytics dashboard. Visualization beyond the 7-day summary lives in the web UI.
- If a user has both HealthKit and Fitbit, the API handles dedup by source priority (HealthKit > Oura > Fitbit).
- Consider adding Apple Watch complication later as an extension of this app (see `companion-roadmap.md` Phase 5).
