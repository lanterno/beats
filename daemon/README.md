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
│ OS input    │  ── CGEventTap (macOS) ─► │                 │
│ events      │     Raw Input (windows)  └─────────────────┘
└─────────────┘     (counts only)                ▲
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
| `beatsd doctor [--json]` | Diagnostics — checks pairing, API reachability, editor-listener port, Accessibility permission, and (informational) flow-data flow ("N windows · avg X (last hour)"). The editor-port check passes whether the port is free OR is already held by *our own* `beatsd run` (probed via the `/health` JSON endpoint), so running `doctor` on a healthy install no longer misreports a conflict — it only flags a port held by something else. The flow check never fails the command since a freshly-paired daemon has zero windows; it just surfaces the count so you can spot a daemon that's paired but not collecting. Exit 1 on any other failure, suitable for `beatsd doctor && beatsd run` startup scripts. With `--json` emits the report as a JSON object — `{all_passed: bool, checks: [{name, ok, detail, error?}, ...]}` — for monitoring scripts; the canonical guard pattern is `beatsd doctor --json \| jq -e '.all_passed'`, which propagates the same exit-1-on-failure semantics. |
| `beatsd status [--json]` | Snapshot of right-now state — pair, daemon-running probe (with this-process emitted-window count + uptime when reachable), current timer state from the API, and a one-line flow summary for the last hour ("N windows · avg X · peak Y") so you can confirm at a glance the flow pipeline is producing results. When the daemon's been up for ≥90s with zero windows emitted, an additional warning line flags the canonical "Accessibility permission revoked mid-session" pattern — same diagnostic the VS Code extension's tooltip surfaces, kept in lockstep so both surfaces flag the condition at the same moment. A non-zero `windows_dropped` count surfaces a separate warning ("⚠ N windows dropped — check API reachability") so a producing-but-not-landing pipeline gets flagged distinctly from a producing-nothing one. With `--json` emits a stable-shape JSON object — `{paired, daemon: {…}, api: {…}, timer: {…}, flow: {…}}` — so jq scripts and the companion's status widget don't have to guard against missing keys; the same exit-1-on-failure semantics apply, so `beatsd status --json \| jq -e '.paired and .api.reachable'` is a clean health predicate. |
| `beatsd recent [--minutes N] [--repo P \| --here] [--language L] [--bundle B] [--json]` | Print the last hour (default) of flow windows in a small terminal-friendly table — time, score, dominant app, repo. Optional filters mirror the web Insights chips: `--repo` matches the editor workspace path, `--language` matches a VS Code language id, `--bundle` matches a macOS bundle id. Filters AND-compose. `--here` is shorthand for `--repo $(git rev-parse --show-toplevel)` — useful from any subdir of a paired workspace; mutually exclusive with `--repo`. `--json` emits the raw windows as a JSON array instead of the table, intended for shell scripting (`beatsd recent --language go --json \| jq '.[] \| select(.flow_score > 0.7)'`). Useful for "what was the daemon seeing the last hour, on this repo / in Go / inside Xcode?" without opening the web UI. |
| `beatsd top [--minutes N] [--repo P \| --here] [--language L] [--bundle B] [--limit N] [--json]` | Print top-N leaderboards by repo / language / app for the recent window — terminal mirror of the FlowByRepo / FlowByLanguage / FlowByApp cards on the web Insights page. Each row shows the bucket label, average flow score (out of 100), and tracked minutes (count of 1-minute windows). Sorted by minutes, ties broken by avg score so higher-quality buckets surface first. `--limit` overrides the default cap of 5 rows per axis (e.g. `--limit 10`); positive integers only. The same filter flags as `recent` / `stats` (including `--here`) narrow the slice the leaderboards are computed from — `beatsd top --language go` answers "in my Go time, which repos and apps win?". `--json` emits the three leaderboards as a single object (`{by_repo: [...], by_language: [...], by_app: [...]}`) for piping into jq — JSON output uses raw bundle ids on the by_app axis instead of the human "coding" / "browser" category labels the table uses. |
| `beatsd stats [--minutes N] [--repo P \| --here] [--language L] [--bundle B] [--json]` | Print a one-line headline summary: count · avg · peak (with HH:MM) · best repo. Hits the API's `/flow-windows/summary` endpoint so it costs one round-trip — designed for shell prompts and status bars. `--here` is shorthand for `--repo $(git rev-parse --show-toplevel)`. `--json` emits the raw FlowWindowSummary object instead of the line. |
| `beatsd open [--repo PATH \| --here] [--language ID] [--bundle ID] [--print]` | Open the Beats web UI Insights page in the system browser. The three filter flags AND-compose into the same `?repo=…&language=…&bundle=…` URL scheme the page uses for click-to-filter chip persistence (so a deep-link from the CLI lands on the exact view a chip click would). `--here` is shorthand for `--repo $(git rev-parse --show-toplevel)`, so `cd ~/code/myproject && beatsd open --here` opens Insights filtered to that workspace from any subdir; falls back to the bare cwd when not inside a git work tree. `--here` and `--repo` are mutually exclusive. With `--print` writes the URL to stdout instead of launching, useful for shell pipelines (`beatsd open --here --print \| pbcopy`) and headless setups. Mirrors the VS Code extension's "Beats: Open Insights" command. Web URL is configurable via `[ui] base_url` in `daemon.toml`; defaults to `http://localhost:8080`. |
| `beatsd start <name> [--json]` | Start a timer for the project matching `<name>`. Resolution tiers, looser by step: exact name (case-insensitive) → unique prefix → unique substring; archived projects are ignored, an ambiguous tier lists the candidates, and no match suggests the nearest by edit distance. Hits `POST /api/projects/{id}/start` with the device token (already authorized), so the start time is server-stamped. `--json` emits `{action, project_id, project_name}`. Designed as the single binary that Raycast / Alfred / Spotlight / Shortcuts shell out to. |
| `beatsd stop [--json]` | Stop the running timer and print the logged duration (computed from the returned beat's span). `--json` emits `{action, duration_minutes}`. |
| `beatsd version [--json]` | Print version, git SHA (with `-dirty` marker if built off uncommitted changes), build date, Go version, OS/arch, and cgo flag. With `--json` emits the same fields as a JSON object — `{version, git_sha, git_dirty, build_date, go_version, os_arch, cgo_build}` — designed for CI release pipelines (`beatsd version --json \| jq -r .git_sha`) and bug-report tooling that would otherwise have to regex-parse the human form. |
| `beatsd config [--json]` | Print the loaded daemon configuration: API + UI URLs, collector intervals, and the path to `daemon.toml`. The device token is intentionally NOT printed — output is meant to be pasteable into bug reports without leaking credentials. With `--json` emits the same data as a JSON object: `beatsd config --json \| jq -r .ui.base_url`. |
| `beatsd unpair` | Remove the device token from the keychain. |

`--dry-run` works on `run` to skip API posts and just print computed flow windows to stdout.

## What gets collected

Each 1-minute window contains:

- **flow_score** (composite, 0–1) = 40% cadence + 40% coherence + 20% category fit
- **cadence_score** — input event rate, from CGEventTap on macOS and Raw
  Input on Windows; 0.5 fallback where neither is available (currently Linux)
- **coherence_score** — how concentrated the user was on a single app vs
  context-switching. A window in which *no* app was observed scores 0.5
  ("unknown"), not 1.0 — see the note under Platform support
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

[scoring]
# Weights for the composite flow_score. Defaults sum to 1.0; the
# final score clamps to [0,1] so weights summing higher just
# compress the scale. All four fields are optional — omitting a
# field (or leaving it at 0) keeps the shipped default for that
# field, so partial overrides work.
cadence_weight = 0.4
coherence_weight = 0.4
category_weight = 0.2
idle_threshold_sec = 30   # samples with IdleSeconds > this count as idle
```

Device token lives in the OS keychain (macOS: Keychain Access; Linux:
libsecret; Windows: Credential Manager), not the config file.

## Platform support

| Signal | macOS | Windows | Linux |
|---|---|---|---|
| Frontmost app | `lsappinfo` | `GetForegroundWindow` + `QueryFullProcessImageName` | `xdotool`/`xprop`, or `swaymsg` |
| Idle time | `ioreg` HIDIdleTime | `GetLastInputInfo` | `xprintidle` |
| Input cadence | CGEventTap (needs Accessibility) | Raw Input (no permission needed) | — falls back to 0.5 |

Windows app identity is the extension-less executable basename —
`C:\…\Code.exe` becomes `Code`. The extension is stripped at the source
because `bundle.ShortLabel` splits unknown ids on the final dot, so
`Code.exe` would surface as "exe" everywhere it's displayed. The window
title is deliberately never read: titles carry document names and full
paths, which would break the "no file paths beyond the workspace root"
guarantee below.

**Why a blind window scores 0.4 and not 0.6.** If app detection returns
nothing for a whole window, `coherence` reports 0.5 ("unknown") rather
than 1.0. It used to report 1.0, on the reading that "no apps seen" means
"no context switching" — which meant a platform with no app detection
published a flow score of exactly 0.600 on every window forever,
indistinguishable from a real measurement. `beatsd doctor`'s
**Desktop signal sources** check is the loud guard against that state;
the coherence floor is the quiet one that still holds if detection
breaks after startup.

## Architecture

```
daemon/
├── cmd/beatsd/         Entry point + command dispatch (pair, run, doctor, …)
├── internal/
│   ├── autotimer/      Detects sustained high flow and asks the API for a
│   │                    timer suggestion; fires native notifications.
│   ├── client/         HTTP client — pairing exchange, flow window POST,
│   │                    timer-context, suggest-timer endpoints. Parses
│   │                    the API's unified `{detail, code}` error
│   │                    envelope so failures surface as readable
│   │                    sentences ("flow-windows GET failed (HTTP 401):
│   │                    Device token expired [UNAUTHORIZED]") instead
│   │                    of bare status codes.
│   ├── collector/      Sample loop, flow score computation, per-platform
│   │                    cadence probes (cadence_darwin.go = CGEventTap,
│   │                    cadence_windows.go = Raw Input, cadence.go = stub).
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

The implementation lives in `internal/collector/cadence_darwin.go`
(real `CGEventTapCreate`) with a fallback in `cadence.go`.

## Raw Input (cadence) — Windows

Windows needs no permission grant. `cadence_windows.go` creates a
message-only window (parented to `HWND_MESSAGE`, so it is never visible
and never enumerated), registers for keyboard and mouse HID usages with
`RIDEV_INPUTSINK` so input arrives even when unfocused, and counts
`WM_INPUT` messages on a dedicated `runtime.LockOSThread`'d goroutine
running its own message pump.

Raw Input rather than the `WH_KEYBOARD_LL` / `WH_MOUSE_LL` hooks most
examples reach for, because low-level hooks put this process on the
synchronous delivery path for every input event in the session — a slow
callback stalls the desktop, and Windows silently evicts hooks that
exceed `LowLevelHooksTimeout`. Global input hooks are also a well-known
antivirus heuristic. Raw Input has none of those properties and needs a
message pump either way.

Privacy: we never call `GetRawInputData`, so the keycode, the mouse
delta and the device handle are never read into the process at all —
the event's *existence* is the entire payload. That's a stronger
guarantee than the macOS tap, whose callback is handed the event
regardless. `TranslateMessage` is likewise absent from the pump, since
its whole job is turning key events into character messages.

## Editor heartbeats

The daemon binds `127.0.0.1:37499` for editor heartbeats — see the
[VS Code extension](../integrations/vscode-beats/). Heartbeats are
loopback-only (the listener rejects non-127.0.0.1 peers) and carry only
workspace path + branch + active language; never file content.

The collector merges the most recent fresh heartbeat (≤ 90 s old) into
each flow window's `editor_repo` / `editor_branch` / `editor_language`
fields.

## Build + test

```bash
go test ./...                                   # run all unit tests
go build ./...                                  # native build
GOOS=linux go build ./...                       # cross-compile for linux
GOOS=windows CGO_ENABLED=0 go build ./...       # cross-compile for windows
GOOS=windows CGO_ENABLED=0 go vet ./...         # vet the windows-tagged files
```

Windows cross-compiles from any host with `CGO_ENABLED=0` — the Raw
Input collector goes through `golang.org/x/sys/windows`, which is pure
Go syscall wrappers, so no mingw toolchain is involved. Note that a
plain `go vet ./...` only ever sees the host's build tags, so the
`_windows.go` files need the explicit `GOOS=windows` vet above; CI runs
it for the same reason.

For tagged releases, `.github/workflows/release-daemon.yml` builds
darwin + linux × arm64 + amd64 tarballs plus a windows/amd64 zip and
uploads them to the GitHub release. Bump the
[Homebrew formula](../integrations/homebrew-formula/) SHA256s afterwards.

## Troubleshooting

| Symptom | First thing to check |
|---|---|
| Flow score stuck at 0.5 cadence | `beatsd doctor` — did the Accessibility prompt appear (macOS)? On Windows, did the Raw Input row pass? |
| Flow score is the same number every window | `beatsd doctor` — the **Desktop signal sources** row. A constant score means no app was detected, so coherence is reporting "unknown" every time. |
| Windows: every app shows as "other" | The category map keys off the extension-less exe basename (`Code`, not `Code.exe`). Run `beatsd status` to see what the collector actually recorded, then add the name to `internal/collector/categories.go`. |
| API errors on `run` | `beatsd doctor` — does the heartbeat row pass? Check `~/.config/beats/daemon.toml` `base_url`. |
| "port in use" on startup | Another `beatsd run` is already up. `beatsd status` reports `daemon: running`. |
| Editor context not appearing on flow windows | `beatsd doctor` confirms 37499 is bound. Check that the VS Code extension is installed and focused. |
| Notifications not firing on linux | `apt install libnotify-bin` — the daemon falls through to a log line otherwise. |

If something else is off, please attach the output of `beatsd version`
and `beatsd doctor` to the bug report.
