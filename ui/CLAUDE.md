# Beats UI

React 19 SPA — Vite 7, TypeScript 5.9, TailwindCSS 4, pnpm.

## Architecture

Feature-Sliced Design (FSD):

```
client/
├── app/           App.tsx (router + providers) + Layout.tsx (authenticated shell)
├── pages/         Route-level components — homepage, index, insights, coach,
│                  plan, project-details, settings, not-found
├── widgets/       Cross-page composite UI — sidebar (desktop) + mobile header
├── features/      User interactions — timer, auth
├── entities/      Business objects — project, session, planning, coach,
│                  intelligence, calendar, github
├── shared/        No business logic — api client, lib helpers, ui primitives,
│                  config
└── main.tsx       Entry point
```

Layer rules: `app/` can import from anything; `pages/` from widgets/features/
entities/shared; `widgets/` from features/entities/shared; `features/` from
entities/shared; `entities/` from shared only; `shared/` from nothing.

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

- Unit tests: `client/**/*.test.{ts,tsx}` (Vitest, jsdom). `.ts` files cover
  pure helpers in `shared/lib/`; `.tsx` files cover React components and
  hooks via `@testing-library/react`. Both globs are wired in
  `vitest.config.ts`.
- E2E tests: `e2e/` (Playwright, Chromium only, auto-starts dev server).
- Mocking pattern: see `client/features/auth/components/AuthModal.test.tsx`
  for the canonical setup — vi.mock the API module, the auth store, and
  `useNavigate`; render under `MemoryRouter`; assert on visible DOM via
  `screen.findByRole` / `findByText`. Layout.test.tsx and
  TimerManager.test.tsx mirror this shape for hook-heavy and child-component-
  heavy components respectively.

## Linting

```bash
pnpm lint          # biome check client/
pnpm lint:fix      # biome check --write client/
pnpm typecheck     # tsc
```
