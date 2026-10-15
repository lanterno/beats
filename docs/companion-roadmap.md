# Companion App Roadmap — From Pairing Hub to Primary Timer

> The companion app is the daily driver. Users control timers, see flow
> state, and receive coaching nudges here. The web UI remains the
> analytics and configuration surface.

**Companion = action.** Start/stop timers, see what's running, get nudged.
**Web = reflection.** Heatmaps, weekly reviews, goal tuning, integrations setup.

## Remaining

The open work is tracked in Linear — the [LifePete project](https://linear.app/elghareeb/project/lifepete-a8ecce3a86de),
milestone *Companion: native & device*: iOS and Android widgets (AHM-39,
AHM-40), the Apple Watch (AHM-41), server push (AHM-42) and offline support
(AHM-44). The notes below are the design to start from.

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

- SQLite local cache for projects and recent beats
- Mutation queue (mirrors the web's IndexedDB queue in
  `ui/client/shared/lib/mutationQueue.ts`): start/stop and beat edits
  queued when offline, replayed on reconnect
- Timer runs locally when offline — syncs the beat on reconnect

### Auth model

- Device token from pairing now sits in OS secure storage (Keychain /
  EncryptedSharedPreferences / libsecret / DPAPI) via
  `flutter_secure_storage` — see `flutter-companion.md` for the
  migration story and the `SecureStore` interface
- All API calls send `Authorization: Bearer <device_token>`
- `DEVICE_ALLOWED_PREFIXES` (in `api/src/server.py`) covers the device
  endpoints (`status`, `heartbeat`, `favorites`, `weekly`), `signals`,
  `biometrics/daily`, `timer`, `projects`, `beats`, `coach/brief`,
  `analytics/heatmap` and `analytics/tags` — append as new endpoints land.
  The match is by prefix, so `/api/projects` already admits the contract
  routes under `/api/projects/{id}/…` (`contract`, `contract/week`,
  `ledger`, `holidays`, `absences`); `/api/meta`, the holiday-region list,
  is not in the tuple. The companion is unaware of contracts and reads none
  of those routes — a week card in
  the tray is a follow-up in `work-contracts-roadmap.md`
