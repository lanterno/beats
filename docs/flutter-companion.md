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
(`.github/workflows/companion.yml`). For the notification work see
`companion-roadmap.md`; what is left to ship is tracked in Linear (below).

### File layout

Not duplicated here — it drifted. `companion/README.md` carries the current
architecture, and `ls companion/lib/screens companion/lib/services` beats both.

What is worth knowing from outside the directory: one screen per top-level tab,
a flat `services/` layer that the screens call directly (no state-management
package — plain `setState` plus service callbacks), and `theme/` holding the
palette, typography and the ambient effects.

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

The companion knows nothing of project kinds or contracts. It lists
projects, so `kind` and `contract` arrive in that response and are
ignored (the contract figures in `this_week` come only with
`include=this_week`, which it never asks for), and it reads none of the
contract, week, ledger, holiday or absence routes under `/api/projects/{id}/…` —
reachable with its device token all the same; see `companion-roadmap.md`
§ Auth model.

### Already-installed dependencies

`http`, `shared_preferences`, `flutter_secure_storage`, `mobile_scanner`,
`intl`, `google_fonts`, `system_tray`, `window_manager`,
`flutter_local_notifications`, `flutter_timezone`, `timezone`,
`url_launcher`.

---

## Remaining

Tracked in Linear — the [LifePete project](https://linear.app/elghareeb/project/lifepete-a8ecce3a86de), milestone
*Companion: native & device*: HealthKit / Health Connect ingestion
(AHM-37), background sync (AHM-38), widgets and the Watch (AHM-39 to
AHM-41), server push (AHM-42) and the web-side pairing QR code (AHM-43).
Each issue carries the file-by-file plan that used to sit here.

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
- Apple Watch is out of scope for this app — it is its own target,
  AHM-41 in Linear.
