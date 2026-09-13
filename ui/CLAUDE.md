# Beats UI

React 19 SPA — Vite 8, TypeScript 6, TailwindCSS 4, pnpm.

## Architecture

Feature-Sliced Design (FSD):

```
client/
├── app/           App.tsx (router + providers), Layout.tsx (authenticated
│                  shell), session.ts (wires auth into the session port)
├── pages/         Route-level components — homepage, index, insights, coach,
│                  plan, projects-index, project-details, settings, not-found
├── widgets/       Cross-page composite UI — sidebar (desktop) + mobile header
├── features/      User interactions — timer, auth
├── entities/      Business objects — project, absence, session, planning,
│                  coach, intelligence, calendar, github
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
- **Styling**: TailwindCSS 4 (`@theme`, `@layer base` syntax), Radix UI primitives (see
  Theme below)
- **PWA**: vite-plugin-pwa with workbox runtime caching
- **Node**: >=25.0.0

## Theme

Two hours: `afternoon` (light, the default) and `dusk`. `client/global.css` defines
the tokens on `:root` and redefines them under `:root[data-theme="dusk"]`; they are
the names every component already reads (`--card`, `--accent`, `--muted-foreground`
…), as HSL triples so `hsl(var(--x) / .5)` works by hand, and `@theme` maps them to
Tailwind colours. `shared/lib/useTheme.ts` owns the hour and the density: the
storage keys, the `data-theme` / `data-density` attributes and `theme-color`; a
stored value that is not one of the two hours reads as afternoon. The inline script
at the top of `index.html` stamps both before first paint, so a stored dusk does not
flash, and repeats the keys and the dusk sky's hex — change them in both places.

- **The sky** is `SkyBackdrop` (`shared/ui/sky-backdrop.tsx`), rendered first by
  `Layout` and by the marketing page: a `position: fixed` layer at z-index −1 with the
  gradient, the sun, five drifting clouds and three hills, coloured by the `--sky-*`,
  `--cloud*` and `--hill-*` tokens. It shows only while nothing between it and the
  root paints a background or opens a stacking context, which is why `Layout`'s root
  and `.homepage-root` do neither. Never `background-attachment: fixed` on `body`:
  iOS Safari paints it black under a `backdrop-filter` overlay (the note in
  `global.css`).
- **`Panel`** (`shared/ui/panel.tsx`) is the one card: `rounded-[1.625rem] bg-card
  shadow-soft`, no border, `p-6` unless `padding` says otherwise. Controls are pills,
  separators inside a list are the hairline (`border-border`), highlights are washes
  (`bg-secondary`). A wash vanishes on the bare sky, so a control there sits on the
  card surface.
- **The accent is sunlight** and marks today, the running timer and a page's primary
  action. As text it is `text-accent-ink`, never the raw accent, which is under 2:1
  on a panel by day; small text in a tone takes `--success-ink` or
  `--destructive-ink`, and big figures and fills the tone itself. Vacation, sick,
  holiday and other are the `tint-*` tokens.
- **Fonts**, loaded from Google Fonts at the top of `global.css`: M PLUS Rounded 1c
  (500 / 700 / 800) is `font-heading` and `font-mono` — the display figures and every
  column of digits, whose numerals are one width, so no `tnum`. Zen Maru Gothic
  (400 / 500 / 700) is `font-body`, everything read. Real code is `font-code`, since
  `font-mono` is not a monospace.
- Under `prefers-reduced-motion` nothing moves: the clouds stop, and every animation
  and transition jumps to its end state.

## The project page

`pages/project-details` answers "where do I stand?" in its first screen
(`docs/project-page-roadmap.md`). `ProjectDetails.tsx` owns the reads its panels
share — `/contract/week` for the open week, the current week (the balance is pinned to
today) and the next, the ledger, the sessions and the running timer — and the open
week, which is the URL's `?week=`, so ‹ ›, a ledger row and a time-off entry all move
one navigator; it also owns the booking dialog every "Book time off" opens. Under
`ProjectHeader` the main column is `Standing` ("Where you stand": the balance and its
proof, or a side project's pace, beside the open week), `WeekDays` ("Days") and
`WeekLedger` ("Earlier weeks"); the rail holds `ContractRegister` (the contract with
its step chart, or the goal), `TimeOff` on a day job, and `QuietFacts`. The layout
queries the content column (`@container/content`), not the viewport, and the rail sits
beside the column from 860 px of it. Every figure is the API's; the page's own
arithmetic — the sentence, the Sunday projection, the ledger's rows and their +/− — is
pure functions in `entities/project/model` (`standing.ts`, `ledger.ts`), a test per
branch. Tests and E2E specs find the panels by their region names, never by class.

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

Before adding a test, see **What to test, and what not to** in the repo-root
`CLAUDE.md` — in particular that configuration, framework behaviour, and
whatever a mock was told to return are not worth pinning.

## Linting

```bash
pnpm lint          # biome check .
pnpm lint:fix      # biome check --write .
pnpm typecheck     # tsc
```
