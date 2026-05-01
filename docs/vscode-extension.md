# VS Code Extension — `beats-vscode`

> **Status: end-to-end shipped, persisted on the API.**
>
> The VS Code extension at `integrations/vscode-beats/` posts heartbeats
> to the daemon's editor listener at `daemon/internal/editor/listener.go`,
> which exposes the most recent fresh beat to the collector loop. Each
> flow window carries the active editor's workspace + branch + language
> alongside the existing flow signals, persisted on the `FlowWindow`
> document and exposed downstream:
>
> **API** — `GET /api/signals/flow-windows` returns the rows with
> `editor_repo`, `editor_branch`, `editor_language` fields. Optional
> filters (AND-composed): `editor_repo`, `editor_language`, `bundle_id`,
> `project_id`. Companion endpoints:
> - `GET /api/signals/flow-windows/summary` — single round-trip aggregate
>   (avg / peak / count + top bucket per axis) for callers wanting the
>   headline without paginating rows.
> - `GET /api/signals/flow-windows.csv` — same slice as a CSV download.
>
> **Web Insights page** — eight Flow* cards plot the data along
> different axes:
> - `FlowToday` (sparkline, today), `FlowThisWeek` (7-day bars),
>   `FlowTrend` (12-week line).
> - `FlowRhythm` (hour-of-day, 7 days) and `FlowByWeekday` (day-of-week,
>   28 days) — *when* you flow best.
> - `FlowByRepo` / `FlowByLanguage` / `FlowByApp` — clickable rows that
>   set page-wide filter chips. `BestMoment` highlights the peak window
>   of the week.
>
> **Filter UX** — every filter (project + tag dropdowns plus the three
> click-to-filter chips) persists in the URL —
> `?project=…&tag=…&repo=…&language=…&bundle=…` — so a filtered view is
> bookmarkable and shareable. When 2+ are active, an
> "× clear all filters" link in the header resets the page in one click.
> The chip row also surfaces a "↓ csv" download link for the visible
> slice.
>
> **Home page** — `FlowHeadline` card renders today's avg / peak / count
> + best repo + best language using `/summary` (single round-trip).
> Tapping jumps to `/insights`.
>
> **Terminal** — `beatsd recent`, `beatsd top`, and `beatsd stats` all
> consume the same filter params:
> - `beatsd recent --repo … --language … --bundle … [--json]` — table
>   or pipeable JSON of recent windows.
> - `beatsd top` — three top-5 leaderboards (by repo / language / app).
> - `beatsd stats [filters] [--json]` — one-line headline for shell
>   prompts, hits `/summary` directly.

Companion extension for the Beats daemon. Emits workspace heartbeats so the
daemon can detect which git repo you're working in and improve Flow Score
accuracy.

## Why

The daemon can detect the frontmost app (e.g. "VS Code is open") but not _which project_ you're editing. Without this extension, the `category_fit_score` component of the Flow Score can only match on app category ("coding"), not on the specific project. With it, the daemon knows `{repo: "ahmed/beats", branch: "main"}` and can match against `Project.autostart_repos` for precise auto-timer suggestions.

## Architecture

```
integrations/vscode-beats/
├── package.json          Extension manifest
├── tsconfig.json
├── src/
│   └── extension.ts      Activation + heartbeat loop
├── .vscodeignore
└── README.md
```

The extension runs a 30-second interval timer. Each tick, it reads the active workspace folder's git remote/branch and POSTs a JSON heartbeat to `localhost:37499` (the daemon's local HTTP listener). The daemon consumes these heartbeats to populate `ActiveProjectID` on flow windows.

## Heartbeat Protocol

```
POST http://localhost:37499/heartbeat
Content-Type: application/json

{
  "editor": "vscode",
  "repo": "/Users/ahmed/code/beats",        // workspace root
  "branch": "main",
  "language": "typescript",                  // active file language ID
  "timestamp": "2026-04-18T12:00:00Z"
}
```

- Port `37499` is configurable via `beats.daemonPort` VS Code setting.
- The daemon binds this port only on `127.0.0.1` (no network exposure).
- If the daemon isn't running, POSTs silently fail (fire-and-forget fetch with 1s timeout).

## Daemon-Side Listener

A new package `daemon/internal/editor/listener.go`:

```go
// StartListener binds a local HTTP server on 127.0.0.1:37499
// that receives editor heartbeats. Returns the latest heartbeat
// via a thread-safe getter.
func StartListener(ctx context.Context, port int) (getLatest func() *Heartbeat, err error)
```

The collector loop calls `getLatest()` on each flush to populate `ActiveProjectID` by matching the heartbeat's `repo` path against projects' `autostart_repos`.

The same listener also serves `GET /health` (loopback-only) returning `{ok, version, uptime_sec, editor_count}`. Editor extensions can probe it on a setInterval to drive a connected/disconnected status indicator without firing heartbeats that get silently dropped.

## Implementation Steps

1. **Scaffold extension** — `npx @vscode/create-extension beats-vscode`. Minimal activation: `onStartupFinished`.
2. **Git detection** — Use `vscode.workspace.workspaceFolders[0].uri.fsPath` for repo path. Use `vscode.extensions.getExtension('vscode.git')?.exports.getAPI(1)` for branch.
3. **Heartbeat loop** — `setInterval` at 30s. `fetch("http://127.0.0.1:37499/heartbeat", ...)` with `AbortSignal.timeout(1000)`.
4. **Settings** — `beats.daemonPort` (default 37499), `beats.enabled` (default true).
5. **Daemon listener** — `internal/editor/listener.go`: `net/http` server on `127.0.0.1:{port}`, stores latest heartbeat per editor in a `sync.Mutex`-guarded map.
6. **Wire into collector** — `loop.go` calls `getLatest()` and matches `heartbeat.Repo` against projects fetched via a new `GET /api/signals/timer-context` response that includes `autostart_repos`.
7. **Publish** — `vsce package` → `.vsix` file. Publish to VS Code Marketplace under `ahmed.beats-vscode` or distribute via GitHub releases.

## Testing

- **Extension**: manual test — open a workspace, verify heartbeat appears in daemon logs.
- **Daemon listener**: unit test with `httptest` — POST a heartbeat, verify `getLatest()` returns it.
- **Integration**: start daemon in dry-run, open VS Code with extension, verify flow window logs show the repo path.

## Dependencies

- VS Code >= 1.85
- Node >= 20 for building
- `@vscode/vsce` for packaging

## Notes

- JetBrains plugin follows the same heartbeat protocol if built later — the daemon listener is editor-agnostic.
- The heartbeat is intentionally minimal: repo path + branch + language. No file names, no content, no keystrokes.
- Consider a `beats.privacy.sendBranch` setting (default true) for users who want to suppress branch names.
