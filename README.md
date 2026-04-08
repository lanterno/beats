# Beats

Personal time tracking that lives on your desk, in your browser, and in your pocket.

A full-stack system with a **Python API**, **React SPA**, and **ESP32 wall clock** — deployed to Google Cloud.

```
┌─────────────┐     HTTP/REST     ┌─────────────┐     Motor      ┌──────────┐
│   React UI  │ ◄──────────────► │  FastAPI     │ ◄────────────► │ MongoDB  │
│  (Vite/TS)  │                   │  (Python)    │                │          │
└─────────────┘                   └──────┬───────┘                └──────────┘
                                         │
                                         │ HTTP polling
                                         │
                                  ┌──────┴───────┐
                                  │  ESP32 Wall  │
                                  │    Clock     │
                                  └──────────────┘
```

## Tech Stack

| Component | Stack |
|-----------|-------|
| **API** | Python 3.14, FastAPI, Motor (async MongoDB), Pydantic v2 |
| **UI** | React 19, TypeScript, Vite, TanStack Query, Tailwind CSS v4 |
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
wall-clock/    ESP32 firmware + docs
terraform/     GCP infrastructure-as-code
```

## Testing

```bash
# API
cd api && uv run --group dev pytest src/ -v   # Unit + integration (testcontainers)
cd api && hurl --test tests/hurl/*.hurl       # Contract tests

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

## License

Private project.
