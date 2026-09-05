# Beats

Personal time tracking that lives on your desk, in your browser, and in your pocket.

A full-stack system across six surfaces — Python API, React SPA, Go daemon, Flutter desktop companion, VS Code extension, and ESP32 wall clock — running on the home network as part of the [`home.space`](../README.md) stack.

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
| **API** | Python 3.14, FastAPI, PyMongo (async MongoDB), Pydantic v2 |
| **UI** | React 19, TypeScript, Vite, TanStack Query, Tailwind CSS v4 |
| **Daemon** | Go 1.23, macOS/Linux signal collection, Flow Score engine |
| **Companion** | Flutter (macOS/iOS/Android/Linux/Windows), HealthKit + Health Connect bridges |
| **VS Code extension** | TypeScript, sends `{repo, branch, language}` heartbeats to the daemon |
| **Wall Clock** | ESP32 firmware (Arduino/C++) with WS2812B LED + e-ink display |
| **Infrastructure** | Docker Compose on the home network (nginx + MongoDB); Terraform/GCP kept for reference |

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
api/                          Python API (FastAPI + PyMongo/MongoDB)
ui/                           React SPA (Vite + TypeScript)
daemon/                       Go daemon — ambient signal collection + Flow Score
companion/                    Flutter desktop companion (timer, coach, integrations)
integrations/vscode-beats/    VS Code extension (workspace heartbeats + status bar)
wall-clock/                   ESP32 firmware + docs
compose.home.yml              Home-network deployment (Mongo + API + SPA on one port)
justfile                      Verbs the home.space stack calls
terraform/                    GCP infrastructure-as-code (previous deployment)
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
| [Companion Roadmap](docs/companion-roadmap.md) | What's left for the companion — native widgets, Apple Watch, server push |
| [Pete macOS Roadmap](docs/pete-macos-roadmap.md) | The Mac-only ambition — floating now-bar, Focus auto-engage, Spotlight + Shortcuts, Live Activities, Apple Intelligence |
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

API integration tests spin up a real MongoDB via [testcontainers](https://testcontainers.com/) — no manual database setup needed, just Docker running. The pytest suite covers the HTTP contract end-to-end.

## Code Quality

**Local git hooks** (Lefthook) run on every commit and push:

- Pre-commit: Ruff lint/format, ty type check, Biome check
- Pre-push: pytest, tsc

**CI** (GitHub Actions) runs lint, type check, tests, and build on every push and PR — separately for `api/` and `ui/` changes.

## Deployment

Beats runs on the **home network**, in the `home.space` stack:

```bash
just build          # build both images (pnpm install + vite build; slow the first time)
just up-detached    # start Mongo, the API and the SPA
just health         # ask the API, through the same nginx a browser uses
just logs           # follow all three
just backup <dir>   # mongodump into <dir>
```

It answers on **one** port, `http://localhost:6008`, and through the stack's
ingress at `http://beats.home.space` / `http://beats.<lan-ip>.nip.io:8080`. The
SPA and the API share that single origin deliberately — see
[Sign-in](#sign-in) below.

The stack starts and stops it through `services.toml` at the stack root, which
names the verbs above and knows nothing else about beats.

`terraform/` and `cloudbuild.yaml` describe the previous Google Cloud
deployment (Cloud Run + Firebase Hosting + Cloud Build). They are kept for
reference and are not what runs.

## Sign-in

Two independent doors into an account. Neither disables the other:

**Beats' own login** — email plus a WebAuthn passkey, exactly as before.

**home.space SSO** — the stack runs an identity issuer at `auth.home.space`
that mints an Ed25519-signed `Home-Session` cookie scoped to `.home.space`.
Beats verifies that cookie itself and exchanges it for an ordinary beats
session. On the login screen it appears as *Continue with home.space*.

- **Already have a beats account?** Sign in with your passkey, then
  **Settings → home.space identity → Link**. Linking always runs from an
  authenticated beats session — that is what proves you control both sides.
- **New to beats?** A home.space identity carrying an `owner` or `admin` role
  gets an account created on first sign-in. Guest and family credentials can be
  linked to an account, but cannot create one.

Revocation is real: revoke a device in the issuer's `/devices` page and its
beats session ends within one refresh cycle, because beats re-checks any
SSO-derived session against the issuer before extending it. If the issuer is
*unreachable*, beats falls back to verifying the cookie's signature against a
cached JWKS, so a stopped identity service degrades to "existing sessions keep
working" rather than "nobody can sign in".

Off unless `BEATS_SSO_ENABLED` is set — see `api/.env.example`. Run
`just sso-doctor` when it misbehaves.

Note that WebAuthn is origin-bound: a passkey registered against the old
`lifepete.com` origin will not work against `beats.home.space`. Linking a
home.space identity is the way an old account gets back in.

## Features

- Start/stop timer per project with weekly goals (targets and caps)
- Contribution heatmap, daily rhythm chart, streak tracking
- Session notes, freeform tags, session timeline
- Daily intentions and end-of-day reflections
- Monthly retrospectives and year-in-review
- Full JSON backup/restore, CSV export, webhooks
- Five dark themes, three density levels
- WebAuthn passkey login, plus optional home.space SSO
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
