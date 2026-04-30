# beatsd

The Beats ambient daemon. Runs in the background, samples desktop
state, computes a `Flow Score` every minute, and ships windows to the
API.

```
┌─────────────┐     127.0.0.1:37499     ┌─────────────────┐
│  VS Code    │  ─── heartbeat ───────►  │                 │
│  extension  │                          │                 │
└─────────────┘                          │     beatsd      │
                                          │  (this binary)  │  ── flow window ──►  api.lifepete.com
┌─────────────┐                          │                 │
│ macOS HID   │  ─── CGEventTap ──────►  │                 │
│ events      │     (kbd / mouse cnt)    └─────────────────┘
└─────────────┘                                  ▲
                                                  │
                                                  └─── /api/signals/timer-context  (30s poll)
```

## Quick start

```bash
go build -o beatsd ./cmd/beatsd
./beatsd pair ABC123     # exchange a 6-char code from web Settings
./beatsd doctor          # verify every prerequisite
./beatsd run             # foreground; ^C to stop
```

For background use, install via [Homebrew](../docs/homebrew-tap.md) and
`brew services start beatsd`.

## Commands

| Command | What it does |
|---|---|
| `beatsd pair <code>` | Exchange a pairing code (from the web UI's Settings → Daemon page) for a device token, stored in the OS keychain. |
| `beatsd run` | Start the collector loop. Polls desktop state every 5 s, flushes a flow window every 60 s. |
| `beatsd doctor` | Diagnostics — checks pairing, API reachability, editor-listener port, and Accessibility permission. Exit 1 on any failure for use in startup scripts. |
| `beatsd status` | Snapshot of right-now state — pair, daemon-running probe, current timer state from the API. |
| `beatsd recent [--minutes N] [--repo P] [--language L] [--bundle B]` | Print the last hour (default) of flow windows in a small terminal-friendly table — time, score, dominant app, repo. Optional filters mirror the web Insights chips: `--repo` matches the editor workspace path, `--language` matches a VS Code language id, `--bundle` matches a macOS bundle id. Filters AND-compose. Useful for "what was the daemon seeing the last hour, on this repo / in Go / inside Xcode?" without opening the web UI. |
| `beatsd version` | Print version, git SHA (with `-dirty` marker if built off uncommitted changes), build date, Go version, OS/arch, and cgo flag. |
| `beatsd unpair` | Remove the device token from the keychain. |

`--dry-run` works on `run` to skip API posts and just print computed flow windows to stdout.

## What gets collected

Each 1-minute window contains:

- **flow_score** (composite, 0–1) = 40% cadence + 40% coherence + 20% category fit
- **cadence_score** — input event rate from CGEventTap (darwin only); 0.5 fallback elsewhere
- **coherence_score** — how concentrated the user was on a single app vs context-switching
- **category_fit_score** — does the dominant app category match the running timer's project category?
- **idle_fraction** — share of samples where no input was detected
- **dominant_bundle_id** + **dominant_category** — which app was most active
- **context_switches** — count of distinct frontmost apps in the window
- **active_project_id** — set if a timer is running on the API side
- **editor_repo / branch / language** — set when the VS Code extension's heartbeat covered the window

No keystrokes, no mouse coordinates, no file paths beyond the workspace root.

## Configuration

`~/.config/beats/daemon.toml` (created on first run with defaults):

```toml
[api]
base_url = "https://api.lifepete.com"

[collector]
poll_interval_sec = 5     # how often to sample
flush_interval_sec = 60   # how often to compute + send a flow window
```

Device token lives in the OS keychain (macOS: Keychain Access; Linux: libsecret),
not the config file.

## Architecture

```
daemon/
├── cmd/beatsd/         Entry point + command dispatch (pair, run, doctor, …)
├── internal/
│   ├── autotimer/      Detects sustained high flow and asks the API for a
│   │                    timer suggestion; fires native notifications.
│   ├── client/         HTTP client — pairing exchange, flow window POST,
│   │                    timer-context, suggest-timer endpoints.
│   ├── collector/      Sample loop, flow score computation, CGEventTap
│   │                    cadence probe (cadence_darwin.go), non-darwin stub.
│   ├── config/         TOML config loading.
│   ├── editor/         Loopback HTTP listener (127.0.0.1:37499) for editor
│   │                    heartbeats from the VS Code extension.
│   ├── notify/         Cross-platform native notifications (osascript /
│   │                    notify-send / PowerShell toast).
│   ├── pair/           Pairing-code exchange + keychain token storage.
│   └── shield/         Detects drift into known time-sink apps while a
│                        timer is running, fires drift notifications.
└── go.mod / go.sum
```

## CGEventTap (cadence) — Accessibility permission

For real input-event counting on macOS, the binary needs Accessibility
access in System Settings → Privacy & Security → Accessibility. Without
it, `CGEventTapCreate` returns NULL and the daemon logs:

```
collector: input event tap not available, cadence will default to 0.5
```

Cadence is 40 % of the flow score, so this is meaningful but not fatal —
the other 60 % (coherence + category fit) still produces useful signal.
`beatsd doctor` reports this clearly:

```
✓  Input event tap (cadence) — available
```
or
```
✗  Input event tap (cadence)
   event tap not available — grant via System Settings → Privacy & Security → Accessibility
```

See [docs/cgeventtap-cadence.md](../docs/cgeventtap-cadence.md) for the
implementation rationale.

## Editor heartbeats

The daemon binds `127.0.0.1:37499` for editor heartbeats — see the
[VS Code extension](../integrations/vscode-beats/) and
[docs/vscode-extension.md](../docs/vscode-extension.md). Heartbeats are
loopback-only (the listener rejects non-127.0.0.1 peers) and carry only
workspace path + branch + active language; never file content.

The collector merges the most recent fresh heartbeat (≤ 90 s old) into
each flow window's `editor_repo` / `editor_branch` / `editor_language`
fields.

## Build + test

```bash
go test ./...              # run all unit tests
go build ./...             # darwin native build
GOOS=linux go build ./...  # cross-compile for linux
```

For tagged releases, `.github/workflows/release-daemon.yml` builds
darwin + linux × arm64 + amd64 tarballs and uploads them to the GitHub
release. Bump the [Homebrew formula](../integrations/homebrew-formula/)
SHA256s afterwards.

## Troubleshooting

| Symptom | First thing to check |
|---|---|
| Flow score stuck at 0.5 cadence | `beatsd doctor` — did the Accessibility prompt appear? |
| API errors on `run` | `beatsd doctor` — does the heartbeat row pass? Check `~/.config/beats/daemon.toml` `base_url`. |
| "port in use" on startup | Another `beatsd run` is already up. `beatsd status` reports `daemon: running`. |
| Editor context not appearing on flow windows | `beatsd doctor` confirms 37499 is bound. Check that the VS Code extension is installed and focused. |
| Notifications not firing on linux | `apt install libnotify-bin` — the daemon falls through to a log line otherwise. |

If something else is off, please attach the output of `beatsd version`
and `beatsd doctor` to the bug report.
