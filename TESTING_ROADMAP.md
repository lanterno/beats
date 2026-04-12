# Testing & CI Roadmap

> Where we are, where we're going, and the tools that get us there.

## Current State

| Area | API (Python) | UI (React/TS) |
|------|-------------|---------------|
| Unit tests | 16 (domain models) | Vitest installed, no tests written |
| Integration tests | 28 (HTTP endpoints via TestClient) | None |
| E2E tests | None | None |
| Type checking | None (no mypy/pyright) | `tsc --noEmit` (strict) |
| Linting | Ruff | Prettier only (ESLint not configured) |
| Formatting | Ruff | Prettier |
| Git hooks | None | None |
| CI | Cloud Build (build + deploy only) | Cloud Build (build + deploy only) |
| Coverage | pytest-cov available, no thresholds | None |
| Local test DB | Testcontainers (MongoDB) | N/A |

The deploy pipeline works. The test and quality pipeline doesn't exist.

---

## Phase 1: Local Quality Gates

**Goal:** Catch problems before they leave the developer's machine.

### 1.1 — Lefthook (git hooks)

[Lefthook](https://github.com/evilmartians/lefthook) is a fast, zero-dependency git hooks manager written in Go. Replaces the Python-based `pre-commit` framework with something that starts in milliseconds.

```yaml
# lefthook.yml (repo root)
pre-commit:
  parallel: true
  commands:
    api-lint:
      root: api/
      glob: "*.py"
      run: uv run ruff check {staged_files} && uv run ruff format --check {staged_files}
    api-typecheck:
      root: api/
      glob: "*.py"
      run: uv run ty check src/
    ui-check:
      root: ui/
      glob: "*.{ts,tsx}"
      run: pnpm biome check {staged_files}

pre-push:
  commands:
    api-test:
      root: api/
      run: uv run pytest src/ -x -q
    ui-test:
      root: ui/
      run: pnpm test
```

**Why Lefthook over pre-commit:** No Python dependency for the hook runner itself, parallel command execution, glob-based file filtering, and config lives in a single YAML file at the repo root.

### 1.2 — ty (Python type checker)

[ty](https://github.com/astral-sh/ty) is Astral's new type checker for Python — from the same team that built Ruff and uv. Written in Rust, it checks a full project in milliseconds. Currently in preview but moving fast.

```toml
# api/pyproject.toml
[dependency-groups]
dev = [
    # ... existing ...
    "ty>=0.0.1a10",
]

[tool.ty]
python-version = "3.14"
src = ["src"]
```

**Why ty over mypy/pyright:** Same ecosystem as your existing Ruff + uv toolchain. 10-100x faster than mypy. Designed for modern Python (3.10+ union syntax, etc.). The Astral tools are the state-of-the-art Python toolchain.

### 1.3 — Biome (UI linting + formatting)

[Biome](https://biomejs.dev/) is a Rust-based toolchain that replaces ESLint + Prettier with a single binary. Formats and lints TypeScript/JSX in one pass, 25x faster than ESLint.

```json
// ui/biome.json
{
  "$schema": "https://biomejs.dev/schemas/2.0.0/schema.json",
  "files": { "include": ["client/**"] },
  "formatter": {
    "indentStyle": "space",
    "indentWidth": 2
  },
  "linter": {
    "rules": { "recommended": true }
  }
}
```

Replaces `.prettierrc` and the unused ESLint config. One tool, one config file, one command: `biome check .`

### 1.4 — Coverage thresholds

```toml
# api/pyproject.toml
[tool.pytest.ini_options]
addopts = "-q --cov=beats --cov-fail-under=70"
```

Start at 70% and ratchet up as coverage improves. The threshold prevents regression.

---

## Phase 2: CI Pipeline (GitHub Actions)

**Goal:** Every push and PR gets tested automatically. Cloud Build continues to handle deployment.

### 2.1 — API CI

```yaml
# .github/workflows/api.yml
name: API
on:
  push:
    paths: [api/**]
  pull_request:
    paths: [api/**]

jobs:
  quality:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: api
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v6
      - run: uv sync --group dev
      - run: uv run ruff check src/
      - run: uv run ruff format --check src/
      - run: uv run ty check src/

  test:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: api
    services:
      mongo:
        image: mongo:8
        ports: [27017:27017]
        options: >-
          --health-cmd "mongosh --eval 'db.runCommand({ping:1})' --quiet"
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
    env:
      DB_DSN: mongodb://localhost:27017
      DB_NAME: beats_test
      BEATS_TEST_ENV: "1"
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v6
      - run: uv sync --group dev
      - run: uv run pytest src/ -v --cov=beats --cov-report=xml
      - uses: codecov/codecov-action@v5
        with:
          files: api/coverage.xml
```

**Key decisions:**
- Uses GitHub Actions service containers for MongoDB (faster than testcontainers in CI — no Docker-in-Docker overhead)
- `BEATS_TEST_ENV=1` tells conftest.py to skip testcontainers and use the service container
- `setup-uv` action caches the uv environment automatically
- Path filters: only runs when `api/` files change

### 2.2 — UI CI

```yaml
# .github/workflows/ui.yml
name: UI
on:
  push:
    paths: [ui/**]
  pull_request:
    paths: [ui/**]

jobs:
  quality:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: ui
    steps:
      - uses: actions/checkout@v4
      - uses: pnpm/action-setup@v4
      - uses: actions/setup-node@v4
        with:
          node-version-file: ui/.node-version
          cache: pnpm
          cache-dependency-path: ui/pnpm-lock.yaml
      - run: pnpm install --frozen-lockfile
      - run: pnpm biome check client/
      - run: pnpm typecheck
      - run: pnpm test
      - run: pnpm build
```

Build step at the end catches any Vite/Tailwind compilation issues.

---

## Phase 3: E2E Testing

**Goal:** Test the real user experience — UI + API together.

### 3.1 — Playwright (browser E2E)

[Playwright](https://playwright.dev/) is the standard for browser testing. Fast, reliable, built-in test generator, trace viewer for debugging failures.

```
ui/
├── e2e/
│   ├── playwright.config.ts
│   ├── fixtures.ts          # Custom fixtures (auth, test project)
│   └── tests/
│       ├── timer.spec.ts    # Start/stop timer, verify duration
│       ├── projects.spec.ts # Create, archive, set goals
│       ├── insights.spec.ts # Heatmap renders, monthly retro loads
│       └── settings.spec.ts # Theme switch, webhook config
```

**Setup:** Playwright starts the API (with testcontainers) and the Vite dev server as part of its `webServer` config. Tests run in Chromium headless. No external services needed.

Start with 5-10 tests covering critical paths: create project, start timer, stop timer, check dashboard, visit insights. These catch integration breakage that unit tests miss.

### 3.2 — Hurl (API contract tests)

[Hurl](https://hurl.dev/) is a command-line tool for running HTTP requests defined in plain text files. Written in Rust, designed for API testing. Think of it as executable API documentation.

```hurl
# api/tests/hurl/projects.hurl

# Create a project
POST http://localhost:7999/api/projects/
Authorization: Bearer {{jwt_token}}
{
  "name": "Hurl Test Project",
  "description": "Created by Hurl"
}
HTTP 201
[Asserts]
jsonpath "$.id" exists
jsonpath "$.name" == "Hurl Test Project"
[Captures]
project_id: jsonpath "$.id"

# Verify it appears in the list
GET http://localhost:7999/api/projects/
HTTP 200
[Asserts]
jsonpath "$[*].name" includes "Hurl Test Project"
```

**Why Hurl:** Tests are readable plain text (great for documentation), runs fast, captures values between requests, built-in assertions. Complements pytest integration tests — Hurl tests the HTTP contract, pytest tests the business logic.

---

## Phase 4: UI Unit Tests

**Goal:** Test React components and hooks in isolation with Vitest.

Vitest is already installed. The gap is that no tests are written.

**Priority targets** (highest value, easiest to test):

| Component | What to test |
|-----------|-------------|
| `formatDuration()` | Edge cases: 0 min, 1 min, 60 min, 1440 min |
| `parseUtcIso()` | Various ISO formats, timezone handling |
| `getWeekRange()` | Week boundaries, Monday start |
| `useProjects` hook | Mock API, verify query key structure |
| `WeeklyCard` | Renders with mock session data, copy button works |
| `TagInput` | Add/remove tags, keyboard navigation, autocomplete |

```ts
// client/shared/lib/__tests__/formatDuration.test.ts
import { describe, it, expect } from "vitest";
import { formatDuration } from "../time";

describe("formatDuration", () => {
  it("formats zero", () => expect(formatDuration(0)).toBe("0m"));
  it("formats minutes", () => expect(formatDuration(45)).toBe("45m"));
  it("formats hours", () => expect(formatDuration(90)).toBe("1h 30m"));
});
```

Start with pure utility functions (no React rendering needed), then expand to component tests with `@testing-library/react`.

---

## Phase 5: Developer Experience

### 5.1 — CLAUDE.md

Add `CLAUDE.md` files at repo root and in each subproject with build commands, architecture notes, and conventions. This gives AI assistants (Claude Code, Copilot) the context to make correct changes without exploring the entire codebase each time.

### 5.2 — Devcontainer

A `.devcontainer/devcontainer.json` for VS Code / GitHub Codespaces. Pre-installs uv, pnpm, Docker, just, and all project dependencies. New contributors go from clone to running tests in under 2 minutes.

### 5.3 — Renovate

[Renovate](https://docs.renovatebot.com/) auto-creates PRs for dependency updates across all three subprojects (Python/uv, Node/pnpm, Rust/Cargo). Groups minor updates, pins major versions, runs CI before merging. More configurable than Dependabot.

---

## Phase Summary

| Phase | Effort | Tools Added | What It Unlocks |
|-------|--------|-------------|-----------------|
| 1. Local Gates | 1-2 sessions | Lefthook, ty, Biome | Problems caught before commit |
| 2. CI Pipeline | 1-2 sessions | GitHub Actions, Codecov | Every PR tested automatically |
| 3. E2E Tests | 2-3 sessions | Playwright, Hurl | Confidence in real user flows |
| 4. UI Unit Tests | 2-3 sessions | Vitest (already installed) | Component regression safety net |
| 5. Developer Experience | 1-2 sessions | CLAUDE.md, Devcontainer, Renovate | Faster onboarding, auto-updates |

### Dependency Graph

```
Phase 1 (local gates)
  └── Phase 2 (CI runs the same checks)
        ├── Phase 3 (E2E in CI)
        └── Phase 4 (UI tests in CI)
              └── Phase 5 (DX polish)
```

Phases 3 and 4 can run in parallel. Each phase is independently valuable — you get returns from phase 1 without needing to complete the rest.
