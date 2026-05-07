# Beats

Personal time tracking that lives on your desk, in your browser, and in your pocket.

A full-stack system across six surfaces — Python API, React SPA, Go daemon, Flutter desktop companion, VS Code extension, and ESP32 wall clock — deployed to Google Cloud.

```
                            ┌─────────────┐
                            │  FastAPI    │ ◄────► MongoDB
                            │  (Python)   │
                            └──────┬──────┘
            ┌──────────────────────┼──────────────────────┐
            │             ┌────────┼────────┐             │
     ┌──────┴──────┐ ┌────┴────┐ ┌─┴──────┐ ┌─────────┐ ┌─┴────────┐
     │  React UI   │ │ Flutter │ │ beatsd │ │ VS Code │ │  ESP32   │
     │  (Vite/TS)  │ │  app    │ │ daemon │ │  ext    │ │  clock   │
     └─────────────┘ └─────────┘ └───┬────┘ └────┬────┘ └──────────┘
                                     │           │
                                     └─heartbeat─┘
```

## Tech Stack

| Component | Stack |
|-----------|-------|
| **API** | Python 3.14, FastAPI, Motor (async MongoDB), Pydantic v2 |
| **UI** | React 19, TypeScript, Vite, TanStack Query, Tailwind CSS v4 |
| **Daemon** | Go 1.23, macOS/Linux signal collection, Flow Score engine |
| **Companion** | Flutter (macOS/iOS/Android/Linux/Windows), HealthKit + Health Connect bridges |
| **VS Code extension** | TypeScript, sends `{repo, branch, language}` heartbeats to the daemon |
| **Wall Clock** | ESP32 firmware (Arduino/C++) with WS2812B LED + e-ink display |
| **Infrastructure** | Terraform, GCP Cloud Run, Cloud Build, Artifact Registry |

## Quick Start

```bash
# API — requires Docker (testcontainers auto-starts MongoDB)
cd api && uv run --group dev pytest src/ -v

# API local server
cd api && just run-locally    # uvicorn on :7999

# UI
cd ui && pnpm install
cd ui && pnpm dev             # Vite dev server on :8080
```

A [devcontainer](.devcontainer/devcontainer.json) is provided for VS Code / GitHub Codespaces with all dependencies pre-installed.

## Repository Layout

```
api/                          Python API (FastAPI + Motor/MongoDB)
ui/                           React SPA (Vite + TypeScript)
daemon/                       Go daemon — ambient signal collection + Flow Score
companion/                    Flutter desktop companion (timer, coach, integrations)
integrations/vscode-beats/    VS Code extension (workspace heartbeats + status bar)
wall-clock/                   ESP32 firmware + docs
terraform/                    GCP infrastructure-as-code
docs/                         Design notes
```

## Daemon (`beatsd`)

A local daemon that observes your desktop and computes a Flow Score — a 0–1 measure of how focused your current work session is. It detects the active app, idle time, and context switches, then posts aggregated scores to the API. No raw content ever leaves your machine.

```bash
# Pair the daemon to your account
beatsd pair <code>

# Run the collector (or try dry-run first)
beatsd run --dry-run
beatsd run
```

Once paired, the CLI gives you terminal-native access to your flow data without leaving the shell:

```bash
beatsd status                 # paired? daemon running? api reachable? today's flow
beatsd doctor                 # validate every prerequisite ✓/✗
beatsd recent --here          # last hour of windows in this repo, table form
beatsd top --here --json      # top-5 leaderboards (repo/lang/app), pipeable into jq
beatsd stats --language go    # one-line headline for `--repo X / --language Y / --bundle Z`
beatsd open --here            # open Insights filtered to the current repo
```

Every read-side command (`recent`, `top`, `stats`, `status`, `doctor`, `config`, `version`) supports `--json` for shell pipelines. `--here` is shorthand for `--repo $(git rev-parse --show-toplevel)`. See [daemon/README.md](daemon/README.md) for the full table. The daemon also supports auto-timer suggestions (notifies you to start tracking when sustained focus is detected) and a distraction shield (alerts when you drift to non-work apps during a timer).

### Companion surfaces

The Flutter app and VS Code extension are shipped in this repo:

| Surface | Path | What it does |
|---------|------|--------------|
| Flutter companion | [`companion/`](companion/) | Desktop/mobile app — timer, coach chat, end-of-day reflections, tray icon, post-stop tagging. Bridges HealthKit (iOS/macOS) and Health Connect (Android) to `/api/biometrics`. |
| VS Code extension | [`integrations/vscode-beats/`](integrations/vscode-beats/) | Sends `{repo, branch, language}` heartbeats to the daemon so flow windows carry editor context. Shows the live flow score in the status bar. |

### Design notes

| Document | What it covers |
|----------|---------------|
| [Companion Roadmap](docs/companion-roadmap.md) | What the companion ships today and what's left — native widgets, Apple Watch, server push |
| [Companion UI Design Roadmap](docs/companion-ui-design-roadmap.md) | Brutalist-Luxury design system, per-screen polish (mostly shipped, three small open items) |
| [Flutter Companion](docs/flutter-companion.md) | File-by-file companion architecture, API contract, and the remaining HealthKit / Health Connect / background-sync work |
| [Homebrew Tap](docs/homebrew-tap.md) | One-time tap-repo bootstrap to publish `brew install <user>/beats/beatsd` (formula + release workflow already live) |

## Testing

```bash
# API — unit + HTTP contract end-to-end (testcontainers spins up MongoDB)
cd api && uv run --group dev pytest src/ -v

# UI
cd ui && pnpm test                              # Vitest unit tests
cd ui && pnpm e2e                               # Playwright E2E (needs API + UI running)

# Daemon (scorer, autotimer, shield, collector)
cd daemon && go test ./...

# Companion
cd companion && flutter analyze && flutter test

# VS Code extension
cd integrations/vscode-beats && npm test
```

API integration tests spin up a real MongoDB via [testcontainers](https://testcontainers.com/) — no manual database setup needed, just Docker running. The pytest suite covers the HTTP contract end-to-end; the older `tests/hurl/` files are historical and not run from CI.

## Code Quality

**Local git hooks** (Lefthook) run on every commit and push:

- Pre-commit: Ruff lint/format, ty type check, Biome check
- Pre-push: pytest, tsc

**CI** (GitHub Actions) runs lint, type check, tests, and build on every push and PR — separately for `api/` and `ui/` changes.

**Deployment** is handled by Google Cloud Build: pushes to main trigger a Docker build, push to Artifact Registry, and deploy to Cloud Run.

## Features

- Start/stop timer per project with weekly goals (targets and caps)
- Contribution heatmap, daily rhythm chart, streak tracking
- Session notes, freeform tags, session timeline
- Daily intentions and end-of-day reflections
- Monthly retrospectives and year-in-review
- Full JSON backup/restore, CSV export, webhooks
- Five dark themes, three density levels
- WebAuthn passkey login
- ESP32 wall clock with ambient daily progress display
- PWA-ready with offline timer support
- Ambient daemon with Flow Score (macOS + Linux)
- Auto-timer suggestions based on sustained focus
- Distraction shield with drift detection
- Privacy dashboard with signal audit + delete
- Biometric integrations: Fitbit (OAuth), Oura (PAT), HealthKit + Health Connect (companion app)
- Chronotype detection from Flow Score × time-of-day data
- Recovery-aware AI coach with biometric context

## License

Private project.
