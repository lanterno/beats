# Beats

Personal time tracking that lives on your desk, in your browser, and in your pocket.

A full-stack system with a **Python API**, **React SPA**, **Go daemon**, and **ESP32 wall clock** — deployed to Google Cloud.

```
┌─────────────┐     HTTP/REST     ┌─────────────┐     Motor      ┌──────────┐
│   React UI  │ ◄──────────────► │  FastAPI     │ ◄────────────► │ MongoDB  │
│  (Vite/TS)  │                   │  (Python)    │                │          │
└─────────────┘                   └──────┬───────┘                └──────────┘
                                         │
                                    ┌────┴────┐
                                    │         │
                             ┌──────┴───────┐ ┌──────────────┐
                             │  ESP32 Wall  │ │   beatsd     │
                             │    Clock     │ │  (Go daemon) │
                             └──────────────┘ └──────────────┘
```

## Tech Stack

| Component | Stack |
|-----------|-------|
| **API** | Python 3.14, FastAPI, Motor (async MongoDB), Pydantic v2 |
| **UI** | React 19, TypeScript, Vite, TanStack Query, Tailwind CSS v4 |
| **Daemon** | Go 1.23, macOS/Linux signal collection, Flow Score engine |
| **Wall Clock** | ESP32 firmware (Arduino/C++) |
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
api/           Python API (FastAPI + Motor/MongoDB)
ui/            React SPA (Vite + TypeScript)
daemon/        Go daemon — ambient signal collection + Flow Score
wall-clock/    ESP32 firmware + docs
terraform/     GCP infrastructure-as-code
docs/          Design documents for upcoming integrations
```

## Daemon (`beatsd`)

A local daemon that observes your desktop and computes a Flow Score — a 0–1 measure of how focused your current work session is. It detects the active app, idle time, and context switches, then posts aggregated scores to the API. No raw content ever leaves your machine.

```bash
# Pair the daemon to your account
beatsd pair <code>

# Run the collector (or try dry-run first)
beatsd --dry-run run
beatsd run
```

See [CLAUDE.md](CLAUDE.md) for full daemon commands. The daemon also supports auto-timer suggestions (notifies you to start tracking when sustained focus is detected) and a distraction shield (alerts when you drift to non-work apps during a timer).

### Planned integrations

These require separate projects/repos. Design documents are in `docs/`:

| Document | What it covers |
|----------|---------------|
| [Flutter Companion App](docs/flutter-companion.md) | Cross-platform app (iOS/Android/macOS/Windows/Linux) bridging HealthKit and Health Connect to the API |
| [VS Code Extension](docs/vscode-extension.md) | Editor plugin that sends `{repo, branch}` heartbeats to the daemon for project-aware flow scoring |
| [Homebrew Tap](docs/homebrew-tap.md) | `brew install` distribution with cross-compiled binaries and `brew services` LaunchAgent |
| [CGEventTap Cadence](docs/cgeventtap-cadence.md) | Replaces the cadence stub with real input event counting via macOS Accessibility API |

## Testing

```bash
# API
cd api && uv run --group dev pytest src/ -v   # Unit + integration (testcontainers)
cd api && hurl --test tests/hurl/*.hurl       # Contract tests

# Daemon
cd daemon && go test ./... -v                 # Unit tests (scorer, parser, client)

# UI
cd ui && pnpm test              # Vitest unit tests
cd ui && pnpm e2e               # Playwright E2E (needs API + UI running)
```

API integration tests spin up a real MongoDB via [testcontainers](https://testcontainers.com/) — no manual database setup needed. Just have Docker running.

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
