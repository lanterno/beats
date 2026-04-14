# Beats UI

React 19 SPA — Vite 7, TypeScript 5.9, TailwindCSS 4, pnpm.

## Architecture

Feature-Sliced Design (FSD):

```
client/
├── app/           Providers, routing (App.tsx)
├── pages/         Route-level components (dashboard, insights, settings, plan, project-details)
├── features/      User interactions (timer)
├── entities/      Business objects (project, session, planning, calendar, github, intelligence)
├── shared/        No business logic (api client, utils, UI primitives)
└── main.tsx       Entry point
```

## Running

```bash
pnpm dev           # Vite dev server on :8080
pnpm build         # Production build → dist/spa/
pnpm test          # Vitest unit tests
pnpm e2e           # Playwright E2E (needs API on :7999 + UI on :8080)
```

## Key Details

- **Path aliases**: `@/` → `client/`, `@shared/` → `shared/`
- **API**: Connects to `VITE_API_URL` (default `http://localhost:7999`)
- **Data fetching**: TanStack Query v5 with Zod v4 validation
- **Linting**: Biome (replaces ESLint+Prettier) — tabs, line width 100
- **Styling**: TailwindCSS 4 (`@theme`, `@layer base` syntax), Radix UI primitives
- **PWA**: vite-plugin-pwa with workbox runtime caching
- **Node**: >=25.0.0

## Testing

- Unit tests: `client/**/*.test.ts` (Vitest, utility functions)
- E2E tests: `e2e/` (Playwright, Chromium only, auto-starts dev server)

## Linting

```bash
pnpm lint          # biome check client/
pnpm lint:fix      # biome check --write client/
pnpm typecheck     # tsc
```
