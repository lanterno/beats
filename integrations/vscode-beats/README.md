# Beats — VS Code Extension

Sends a 30-second workspace heartbeat to the local Beats daemon so it can
tell *which* git repo you're editing, not just that you're in VS Code.
Improves Flow Score accuracy and powers per-repo auto-timer suggestions.

## What it sends

One JSON POST every 30s while VS Code is focused, to
`http://127.0.0.1:37499/heartbeat`:

```json
{
  "editor": "vscode",
  "repo": "/Users/you/code/your-project",
  "branch": "main",
  "language": "typescript",
  "timestamp": "2026-04-30T12:00:00Z"
}
```

That's the entire payload. No file paths, no file contents, no keystrokes.
The daemon binds the listener to `127.0.0.1` only — nothing leaves the
machine.

## Settings

| Key | Default | Purpose |
|---|---|---|
| `beats.enabled` | `true` | Master switch. |
| `beats.daemonPort` | `37499` | Local TCP port the Beats daemon listens on. |
| `beats.heartbeatIntervalSeconds` | `30` | Cadence in seconds (min 5). |
| `beats.privacy.sendBranch` | `true` | Set to `false` to suppress branch names. |
| `beats.webUrl` | `http://localhost:8080` | Base URL of your Beats web UI; the "Open Insights" command opens this. Set to your public URL for self-hosted deploys. |
| `beats.statusBar.enabled` | `true` | Show a status-bar item indicating whether the daemon is connected. |

## Commands

⌘⇧P (or F1) → "Beats: Open Insights" opens your Beats web UI Insights
page in the system browser, pre-filtered to the current workspace's
repo path AND the active editor's language id when both are
available. Uses the same `?repo=…&language=…` URL the page persists
when you click chips — so a deep link from the editor lands on the
same filtered view a chip click would. Bare `/insights` when no
workspace and no editor are active.

## Status bar

A status-bar item polls the daemon every 60s and shows whether your
heartbeats are landing — and once today's flow data has accrued, the
current avg score:

- `⚡ Beats 67` — daemon connected, today's avg flow score is 67/100.
  Tooltip carries avg + peak + window count, today's best repo + best
  language (when editor heartbeats covered the slice), plus the
  daemon version and uptime.
- `⚡ Beats` — daemon connected but no flow data yet today (early
  morning before any windows accrued, or summary endpoint
  unavailable).
- `⊘ Beats` — daemon offline; heartbeats are being silently dropped.
  Tooltip suggests `beatsd run`.

When the daemon's been up for >90s but `windowsEmitted` is still 0,
the tooltip flags a likely Accessibility-permission revocation —
the canonical "connected but silently producing nothing" pattern
that's otherwise invisible from the status bar's connected state.

When `windowsDropped > 0` (any non-zero value), the tooltip flags
that flow windows are being computed but failing to POST — the
network/API leg, not the local Accessibility leg. Distinct from
the diagnostic above so the user knows which side to investigate.

Click either state to open the Insights page (same as the command).
Disable via `beats.statusBar.enabled`.

## Install (development)

```bash
cd integrations/vscode-beats
npm install
npm run compile
# Open this folder in VS Code, hit F5 to launch the extension host
```

## Package & install (.vsix)

```bash
npm install
npm run package        # produces beats-vscode-0.1.0.vsix
code --install-extension beats-vscode-0.1.0.vsix
```

## Daemon listener

The extension is a no-op if the daemon isn't running — it's fire-and-forget
with a 1-second timeout. The companion daemon listener that consumes these
heartbeats lives in `daemon/internal/editor/listener.go` (planned, not yet
implemented at the time of writing). Until then, you can run this extension
safely; it'll just be silently dropped.

## Why fire-and-forget?

If the daemon is down or hasn't yet shipped the listener, we don't want a
yellow toast appearing every 30 seconds. The cost of a missed heartbeat is
one window's worth of less-precise project attribution; the cost of a
spammy editor is real friction. So: silent on error.
