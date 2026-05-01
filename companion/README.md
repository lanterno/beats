# Beats Companion

Cross-platform Flutter app — desktop tray icon + mobile companion for the Beats time-tracking system.

## What it does

- **Timer** — start/stop, project picker with recents, custom start/stop times, post-stop note + tags sheet
- **Coach** — streaming chat with the AI coach over `/api/coach/chat`, mood sparkline from the last 7 days of daily notes
- **Flow** — today's flow score with timeline, top repo / language / app, daemon-driven flow windows
- **Intentions** — set, complete, and review daily intentions
- **Health** — HRV / sleep / readiness from connected Fitbit, Oura, HealthKit (iOS/macOS), Health Connect (Android)
- **Tray icon** (desktop) — running/idle indicator with quick start/stop from the menu bar
- **Notifications** — drift alerts, pomodoro completion, auto-timer suggestions

## Platforms

Supported by `flutter_platform_channels`, but actively used on:

- **macOS** desktop (tray + notifications)
- **iOS** mobile (HealthKit bridge)
- **Android** mobile (Health Connect bridge)

The Linux and Windows desktop builds compile but tray-icon support is best-effort.

## Running

```bash
flutter pub get
flutter run -d macos        # desktop dev run
flutter run -d <device>     # mobile

flutter analyze             # zero issues expected
flutter test                # widget + unit tests (110+)
```

## Architecture

```
lib/
├── main.dart               Entry point, theme, top-level routing
├── screens/                One file per top-level tab
│   ├── home_screen.dart
│   ├── timer_screen.dart
│   ├── coach_screen.dart
│   ├── flow_screen.dart
│   ├── health_screen.dart
│   ├── intentions_screen.dart
│   └── pairing_screen.dart
├── services/               Cross-cutting concerns
│   ├── api_client.dart            HTTP client → Beats API
│   ├── token_storage.dart         OS keychain via flutter_secure_storage
│   ├── notifications.dart         Local notifications + dedupe
│   ├── tray_icon.dart             Desktop tray icon image generation
│   ├── tray_service.dart          Desktop tray menu + click handling
│   ├── flow_summary.dart          Flow window aggregation helpers
│   ├── recent_projects.dart       Local recents list (SharedPreferences)
│   ├── tag_parsing.dart           Hashtag extraction from notes
│   ├── repo_path.dart             Path-shortening for display
│   └── ...
├── models/                 Domain models (timer, project, mood, ...)
└── theme/                  Design system: colors, typography, animations
```

## API

Connects to the Beats API via `ApiClient` (`lib/services/api_client.dart`). Pairing flow:

1. User runs `beatsd pair-code` (or this app's pairing screen) to get a 6-char code
2. App POSTs `/api/auth/pair-companion` and receives a JWT
3. Token persists in the OS keychain (Keychain on macOS/iOS, Keystore on Android, libsecret on Linux)

All subsequent requests carry `Authorization: Bearer <jwt>`. The error envelope `{detail, code, fields?}` is parsed into `ApiException` with a `code` field that callers can branch on (mirrors the daemon Go client and UI's `ApiError`).

Read-only analytics methods (`getTags`, `getHeatmap`, `getFlowWindows`, `getSignalSummaries`, `getIntentions`, `getDailyNotesRange`, `getBiometrics`) throw `ApiException` on non-200 — callers wrap in try/catch where graceful degradation is desired (e.g. tag chips are decoration, not blocking). `getFlowWindowsSummary` deliberately returns `Map?` for the empty-state render path.

## Testing

```bash
flutter test
```

Tests cover:
- API client error envelope parsing (`describeError`, `ApiException` shape)
- Pure helpers: tag parsing, repo path shortening, bundle label parity (these have parity tests with the equivalent Go and TypeScript helpers in the daemon and UI — keeping the three surfaces in lockstep)
- Pairing screen widget tests (validates the 6-char code shape)
- Notification dedupe key derivation
- Insights URL builder

The post-stop sheet's tag chip flow, timer screen state machine, and flow screen aggregation aren't yet covered by widget tests — the API client layer is.

## Style

- Dart analyzer (`flutter analyze`) with no extra linter config — runs as a pre-commit hook via lefthook
- No theming framework — `lib/theme/` defines colors and typography directly
- No state management library — `setState` + `StreamSubscription` for tray events
