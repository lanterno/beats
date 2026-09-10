# Beats UI

React 19 SPA — Vite 7, TypeScript 5.9, TailwindCSS 4, pnpm.

## Architecture

Feature-Sliced Design (FSD):

```
client/
├── app/           App.tsx (router + providers), Layout.tsx (authenticated
│                  shell), session.ts (wires auth into the session port)
├── pages/         Route-level components — homepage, index, insights, coach,
│                  plan, project-details, settings, not-found
├── widgets/       Cross-page composite UI — sidebar (desktop) + mobile header
├── features/      User interactions — timer, auth
├── entities/      Business objects — project, session, planning, coach,
│                  intelligence, calendar, github
├── shared/        No business logic — api client, lib helpers, ui primitives,
│                  config, session port
└── main.tsx       Entry point
```

Layer rules: `app/` can import from anything; `pages/` from widgets/features/
entities/shared; `widgets/` from features/entities/shared; `features/` from
entities/shared; `entities/` from shared only; `shared/` from nothing.

Each slice is reached through its `index.ts` barrel, never by importing a file
inside it. That is what makes a slice's internals free to move, and it is why a
dead export is worth deleting rather than leaving: the barrel is the only thing
that says what the slice offers, so anything listed there reads as supported.

The rules bind in one direction, so the awkward case is a lower layer needing
something only a feature has: the API client must attach a bearer token, and
per-account browser storage needs a key identifying the account. Both live in
`features/auth`. Rather than let `shared/` reach up for them, `shared/session`
declares the port it wants — `getToken`, `getUserKey`, `subscribe`, `clear`,
`signOut` — and `app/session.ts` hands it the auth feature's implementation
before the first render. Callers get `sessionToken()`, `useSessionUserKey()`,
`endSession()` and `signOut()`; a test wires a stub with `provideSession()`
instead of mocking the module. Until it is wired the port answers as a
signed-out visitor, which is what a caller reaching it that early would be.

## Running

```bash
pnpm dev           # Vite dev server on :8080
pnpm build         # Production build → dist/spa/
pnpm test          # Vitest unit tests
pnpm e2e           # Playwright E2E (needs API on :7999 + UI on :8080)
```

## Key Details

- **Path alias**: `@/` → `client/`
- **API**: Connects to `VITE_API_URL` (default `http://localhost:7999`)
- **Data fetching**: TanStack Query v5 with Zod v4 validation
- **API schema**: `pnpm gen:types` dumps the OpenAPI document straight from the
  FastAPI app (no server needed) and regenerates `shared/api/generated.ts`;
  `gen:types:check` fails on drift. The API's own `/docs` sits behind the auth
  middleware and a browser tab carries no bearer token, so it is not reachable
  from the SPA — read `shared/api/openapi.json` instead.
- **Linting**: Biome (replaces ESLint+Prettier) — tabs, line width 100. Covers
  `client/`, `e2e/` and the root config files; accessibility rules are on, with
  seven at `warn` pending per-component decisions (see `biome.json`).
- **Styling**: TailwindCSS 4 (`@theme`, `@layer base` syntax), Radix UI primitives
- **PWA**: vite-plugin-pwa with workbox runtime caching
- **Node**: >=25.0.0

## Testing

- Unit tests: `client/**/*.test.{ts,tsx}` (Vitest, jsdom). `.ts` files cover
  pure helpers in `shared/lib/`; `.tsx` files cover React components and
  hooks via `@testing-library/react`. Both globs are wired in
  `vitest.config.ts`.
- E2E tests: `e2e/` (Playwright, Chromium only, auto-starts dev server). Needs a
  running API and Mongo; `e2e/auth.setup.ts` mints and plants a session because
  every page under test is behind `ProtectedRoute`. See the repo-root CLAUDE.md
  for the exact commands.
- Mocking pattern: see `client/features/auth/components/AuthModal.test.tsx`
  for the canonical setup — vi.mock the API module, the auth store, and
  `useNavigate`; render under `MemoryRouter`; assert on visible DOM via
  `screen.findByRole` / `findByText`. Layout.test.tsx and
  TimerManager.test.tsx mirror this shape for hook-heavy and child-component-
  heavy components respectively.

## Linting

```bash
pnpm lint          # biome check .
pnpm lint:fix      # biome check --write .
pnpm typecheck     # tsc
```
