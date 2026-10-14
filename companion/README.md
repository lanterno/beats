# Beats Companion

Cross-platform Flutter app — desktop tray icon + mobile companion for the Beats time-tracking system.

## What it does

On a Mac it is a window with a sidebar and a menu bar item, drawn in the web
app's sky (afternoon or dusk):

- **Today** — the running timer (Stop, switch, "Started earlier?"), today against
  the week's targets, the day's sessions, flow and calendar on one strip, and the
  week, the coach's brief and the body in a card each
- **Flow** — the day's best stretch in a sentence, five-minute flow bars to pick
  through, best repo / language / app, where attention went
- **Coach** — the morning brief as a letter, where each project's week stands, and
  streaming chat over `/api/coach/chat`
- **Body** — readiness, sleep, HRV, resting heart rate and steps over a week, and
  sleep beside the next day's flow (Oura, Fitbit, HealthKit, Health Connect)
- **Quick start** (⌘K in the window, ⌃⌥T from any app) — type a project, and a
  time: "kite from 11:00", "spanish 25m ago", "stop at 17:30"
- **Menu bar** — the running time and project, and a popover with Stop, today and
  the week, and one-click starts; closing the window leaves it running there
- **Focus mode** (⇧⌘F) — the running clock, full window, at dusk
- **Notifications** — the morning brief, drift nudges and auto-timer suggestions,
  each switchable, and held while you're in flow

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
flutter test                # widget + unit tests (281)

# A debug build opens on any surface, for looking at one without clicking:
open --env LIFEPETE_SECTION=flow   build/macos/Build/Products/Debug/beats_companion.app
open --env LIFEPETE_ROUTE=settings build/macos/Build/Products/Debug/beats_companion.app   # or focus
open --env LIFEPETE_POPOVER=panel  build/macos/Build/Products/Debug/beats_companion.app   # or palette
```

## Architecture

```
lib/
├── main.dart               Entry points: the window (main) and the menu bar popover (popoverMain)
├── screens/
│   ├── shell.dart                 The window: sidebar, menus and shortcuts, routes
│   ├── today_screen.dart, flow_screen.dart, coach_screen.dart, body_screen.dart
│   ├── settings_screen.dart, focus_screen.dart, palette.dart
│   ├── pairing_screen.dart, qr_pairing_screen.dart (phones)
│   └── timer_actions.dart         Start / stop / switch with the same confirmation and Undo everywhere
├── popover/popover_app.dart The menu bar popover's app (a second Flutter engine)
├── state/
│   ├── timer_controller.dart      The timer and projects, shared by every surface
│   ├── week_controller.dart       The week per project, read off each project's ledger
│   ├── prefs.dart, hour.dart      Settings, and afternoon / dusk / follow macOS
├── services/               API client and the pure logic each screen tells its story with
│   ├── api_client.dart            HTTP client → API (and decodeSse for chat)
│   ├── *_story.dart, day_ribbon.dart, quick_parse.dart, time_format.dart
│   ├── tray_service.dart, status_menu.dart, mac_ambient.dart   Menu bar, Dock, login item
│   └── ...
├── theme/sky.dart          The web's tokens and faces (ui/client/global.css), in two hours
└── ui/kit.dart             Panels, pill buttons, rings, the sky backdrop
macos/Runner/
├── StatusItemController.swift     Menu bar item, popover engine, ⌃⌥T hot key
└── MacAmbientBridge.swift         Dock badge and icon, open at login
```

The popover is a second `FlutterEngine` that `StatusItemController` starts on the
first click, running `popoverMain`. It reads the same token and keeps its own
`TimerController`; when either side changes the timer it tells the other over
`companion/menubar` and `companion/popover`.

## API

Connects to the Beats API via `ApiClient` (`lib/services/api_client.dart`). Pairing flow:

1. User runs `beatsd pair-code` (or this app's pairing screen) to get a 6-char code
2. App POSTs `/api/auth/pair-companion` and receives a JWT
3. Token persists in the OS keychain (Keychain on macOS/iOS, Keystore on Android, libsecret on Linux)

All subsequent requests carry `Authorization: Bearer <jwt>`. The error envelope `{detail, code, fields?}` is parsed into `ApiException` with a `code` field that callers can branch on (mirrors the daemon Go client and UI's `ApiError`).

Read-only analytics methods (`getHeatmap`, `getFlowWindows`, `getSignalSummaries`, `getBiometrics`) throw `ApiException` on non-200 — callers wrap in try/catch where graceful degradation is desired. `getFlowWindowsSummary` and `getTodayBrief` deliberately return `Map?` for the empty-state render path.

## Testing

```bash
flutter test
```

Tests cover the logic, not the widgets:
- The timer's switch, stop and undo against a scripted API (a switch closes one
  session and opens the next at the same instant; undo reopens the same session)
- The week read off ledgers, today's running total, and overlapping reloads
- What each screen says: the day strip's geometry, Flow's best stretch and shares,
  the Coach's week standings and chat stream fold, the Body's recovery and
  sleep-beside-flow lines, Settings' readings
- What the palette reads from what you type, and the SSE decoder across chunk cuts
- API error envelope parsing, notification preferences and dedupe, the Insights URL
- Bundle labels, repo paths and status-bar formatting, with parity tests against
  the daemon (Go) and the VS Code extension (TypeScript)
- The pairing screen renders and refuses a short code

## Style

- Dart analyzer (`flutter analyze`) with no extra linter config — runs as a pre-commit hook via lefthook
- The look is the web app's: `theme/sky.dart` carries `ui/client/global.css`'s tokens; change one, change both
- No state management library — `ChangeNotifier` controllers (`state/`) shared through the window
