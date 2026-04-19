# VS Code Extension — `beats-vscode`

> Companion extension for the Beats daemon. Emits workspace heartbeats so the daemon can detect which git repo you're working in and improve Flow Score accuracy.

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
