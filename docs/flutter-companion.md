# Flutter Companion App — `beats-companion`

> Cross-platform companion for Beats. Bridges HealthKit (iOS/iPad) and Health Connect (Android) to the Beats API. Serves as pairing hub on all 6 platforms.

## Why

Desktop browsers can't access HealthKit or Health Connect. The companion app is the bridge that pushes daily biometric data (sleep, HRV, resting HR, steps, readiness) from your phone/watch to the Beats API, where it feeds the coach's recovery-aware briefs and chronotype detection.

On desktop (macOS/Windows/Linux), the app provides a native pairing flow and Fitbit/Oura OAuth without needing the web UI.

## Architecture

```
companion/
├── lib/
│   ├── main.dart
│   ├── app.dart                        MaterialApp + routing
│   ├── screens/
│   │   ├── pairing_screen.dart         QR scan (mobile) or code entry (desktop)
│   │   ├── home_screen.dart            Status + last sync info
│   │   ├── health_settings_screen.dart Metric toggles, push schedule
│   │   └── integrations_screen.dart    Fitbit/Oura OAuth (desktop)
│   ├── services/
│   │   ├── api_client.dart             HTTP client with device token auth
│   │   ├── health_service.dart         HealthKit/Health Connect via `health` pkg
│   │   ├── token_storage.dart          flutter_secure_storage
│   │   └── background_sync.dart        Platform-specific nightly push
│   └── models/
│       └── biometric_day.dart          Mirrors API's BiometricDay schema
├── android/
│   └── app/src/main/AndroidManifest.xml  Health Connect permissions
├── ios/
│   ├── Runner/Info.plist                 HealthKit usage descriptions
│   └── Runner/AppDelegate.swift          BGTaskScheduler registration
├── macos/
├── windows/
├── linux/
├── pubspec.yaml
└── README.md
```

## Platform Capabilities

| Platform | Health data | Background sync | Pairing |
|----------|-----------|-----------------|---------|
| iOS/iPad | HealthKit (sleep, HRV, resting HR, steps, workouts) | `BGTaskScheduler` via Swift method channel | QR scan |
| Android | Health Connect (sleep, heart rate, steps, exercise) | `WorkManager` via `workmanager` plugin | QR scan |
| macOS | None | N/A | Pairing code text entry |
| Windows | None | N/A | Pairing code text entry |
| Linux | None | N/A | Pairing code text entry |

## Key Dependencies

```yaml
# pubspec.yaml
dependencies:
  flutter:
    sdk: flutter
  health: ^11.0.0              # Unified HealthKit + Health Connect
  flutter_secure_storage: ^9.0.0  # Keychain/Keystore/libsecret
  mobile_scanner: ^5.0.0       # QR scanning (iOS/Android only)
  http: ^1.2.0                 # HTTP client
  workmanager: ^0.5.2          # Android background tasks
  shared_preferences: ^2.3.0   # Simple key-value storage
```

## Implementation Steps

### Phase 1: Scaffold + Pairing (4 days)

1. `flutter create --org com.beats beats_companion --platforms=ios,android,macos,windows,linux`
2. **Token storage** (`token_storage.dart`): wrap `flutter_secure_storage` with `saveToken(token)`, `loadToken()`, `deleteToken()`.
3. **API client** (`api_client.dart`): HTTP client with `Authorization: Bearer <token>` header. Methods: `exchangePairCode(code)`, `postBiometricDay(data)`, `postHeartbeat()`.
4. **Pairing screen**: on mobile, scan QR code containing the 6-char pairing code. On desktop, text input. Both call `exchangePairCode(code)` → store device token.
5. **Home screen**: shows pairing status, last sync time, connected health source.

### Phase 2: Health Integration (4 days)

6. **Health service** (`health_service.dart`): wrap the `health` package.
   - `requestPermissions()` → request HealthKit/Health Connect read access for: `SLEEP_ASLEEP`, `HEART_RATE_VARIABILITY_SDNN`, `RESTING_HEART_RATE`, `STEPS`, `WORKOUT`.
   - `fetchYesterdayData() -> BiometricDay` → read yesterday's data, aggregate to a single `BiometricDay`.
7. **Health settings screen**: toggle which metrics to sync, choose sync time (default: 6 AM).
8. **Manual sync**: button on home screen to trigger an immediate sync.

### Phase 3: Background Sync (2 days)

9. **iOS background sync**:
   - Register `BGAppRefreshTask` in `AppDelegate.swift` for `com.beats.healthSync`.
   - On trigger: start Flutter engine headless, call `health_service.fetchYesterdayData()`, POST to API.
   - Alternative (simpler): keep the health read in native Swift, POST directly with `URLSession`. This avoids starting the Flutter engine in background.

10. **Android background sync**:
    - Use `workmanager` plugin to register a periodic task (minimum 15 min interval on Android, schedule for ~6 AM).
    - The callback reads Health Connect data and POSTs to the API.

### Phase 4: Desktop Features (2 days)

11. **Integrations screen** (desktop only): Fitbit/Oura OAuth. Open system browser for OAuth, handle redirect via deep link or localhost callback.
12. **Platform-conditional UI**: use `Platform.isIOS || Platform.isAndroid` to show/hide health-specific screens.

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

The companion uses the same device token auth as the Go daemon. It calls:

- `POST /api/device/pair/exchange` — pair (public endpoint)
- `POST /api/biometrics/daily` — push daily health data (device token)
- `POST /api/device/heartbeat` — keep-alive (device token)
- `GET /api/fitbit/auth-url` — initiate Fitbit OAuth (session token, desktop)
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

- The app is intentionally minimal — it's a bridge, not a dashboard. All visualization lives in the web UI.
- If a user has both HealthKit and Fitbit, the API handles dedup by source priority (HealthKit > Oura > Fitbit).
- Consider adding Apple Watch complication in Stage 6 as an extension of this app.
