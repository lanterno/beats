# Beats UI

React 19 + TypeScript SPA — the web frontend for the Beats time-tracking system. Talks to the Python API at `http://localhost:7999` in dev.

See `CLAUDE.md` for runtime + testing conventions, and the repo-root `README.md` for the broader system overview.

## Tech Stack

- **Framework**: React 19 + TypeScript + Vite 7
- **Routing**: React Router 7
- **Data fetching**: TanStack Query v5
- **Styling**: TailwindCSS 4 (`@theme` + `@layer base` syntax) + Radix UI primitives
- **Validation**: Zod v4
- **Tests**: Vitest (unit) + Playwright (e2e, Chromium-only)
- **Lint/format**: Biome (replaces ESLint + Prettier)
- **PWA**: vite-plugin-pwa with workbox runtime caching
- **Package manager**: pnpm

## Getting Started

```bash
pnpm install
pnpm dev                  # Vite dev server on :8080
pnpm build                # production build → dist/spa/

# Quality
pnpm lint                 # biome check
pnpm lint:fix             # biome check --write
pnpm typecheck            # tsc

# Tests
pnpm test                 # vitest unit tests (one-shot)
pnpm e2e                  # playwright e2e (requires API on :7999 + UI on :8080)
```

The backend API must be running at `http://localhost:7999` for the dev server to work. Override via `VITE_API_URL` if needed.

## Architecture: Feature-Sliced Design

Code is organized by domain rather than technical layer.

```
client/
├── app/                    Application shell, providers, routing (Layout.tsx)
├── pages/                  Route-level components (one directory per route)
├── widgets/                Composite components used across pages (e.g. sidebar)
├── features/               User interactions with business logic
├── entities/               Business domain objects (data + types + UI)
└── shared/                 Reusable utilities — no business logic
```

| Layer | Purpose | Can import from |
|-------|---------|-----------------|
| `app/` | Application shell, providers, routing | All layers |
| `pages/` | Full pages, compose features/entities/widgets | widgets, features, entities, shared |
| `widgets/` | Cross-page composite UI (sidebar, headers) | features, entities, shared |
| `features/` | User interactions (timer, auth) | entities, shared |
| `entities/` | Business objects (project, session, planning, ...) | shared |
| `shared/` | Utilities, UI primitives, API client | nothing (foundation layer) |

### Slice structure

Each entity / feature follows the same internal shape:

```
entities/project/
├── api/          Data fetching (TanStack Query hooks, API functions)
├── model/        Types, domain logic, mappers
├── ui/           Presentational components
└── index.ts      Public API (barrel exports)
```

Cross-slice imports go through the public `index.ts` — never reach into another slice's internals.

## Project Structure

```
client/
├── app/
│   ├── App.tsx                 Root component — router + provider tree
│   ├── Layout.tsx              Authenticated app shell (sidebar, mobile header,
│   │                            command palette, focus mode, EOD review)
│   └── providers/              QueryProvider + auth gate
│
├── pages/                      One directory per route
│   ├── index/                  Today / dashboard
│   ├── homepage/               Public landing
│   ├── insights/               Flow trends, contribution heatmap, retrospectives
│   ├── coach/                  AI coach chat
│   ├── plan/                   Weekly plan + recurring intentions
│   ├── project-details/        Project deep-dive
│   ├── settings/               Account, theme, integrations, devices
│   └── not-found/              404
│
├── widgets/
│   └── sidebar/                Desktop Sidebar + Mobile drawer header
│
├── features/
│   ├── timer/                  Start/stop timer (ProjectSelector, TimerManager)
│   └── auth/                   AuthModal + WebAuthn flow + auth store
│
├── entities/
│   ├── project/                Projects + goal overrides
│   ├── session/                Beats / sessions / flow windows
│   ├── planning/               Intentions, daily notes, weekly plans
│   ├── coach/                  Coach chat hooks + history
│   ├── intelligence/           Productivity score, patterns, suggestions
│   ├── calendar/               Google Calendar integration
│   └── github/                 GitHub integration
│
├── shared/
│   ├── api/                    Typed API client + Zod schemas + error envelope
│   ├── lib/                    Utilities (date, format, sync engine, theme,
│   │                            keyboard shortcuts, command palette, ...)
│   ├── ui/                     UI primitives + dialogs (CommandPalette,
│   │                            FocusMode, MorningBriefing, EndOfDayReview, ...)
│   └── config/                 Environment configuration
│
├── global.css                  Tailwind 4 directives + design tokens
└── main.tsx                    Entry point
```

## Path aliases

| Alias | Path |
|-------|------|
| `@/*` | `client/*` |
| `@shared/*` | `shared/*` (legacy, prefer `@/shared/*`) |

## Conventions

### Data fetching with TanStack Query

```typescript
const { data, isLoading, error } = useProjects();

// Invalidate after mutations
const queryClient = useQueryClient();
queryClient.invalidateQueries({ queryKey: projectKeys.all });
```

### Runtime validation with Zod

API responses are validated at the client boundary:

```typescript
const data = await get<unknown>("/api/projects/");
return parseApiResponse(ApiProjectListSchema, data);
```

### Error envelope parity

Non-2xx responses are normalized into `ApiError` with the unified `{detail, code, fields?}` shape that the API and the daemon Go client and the companion Dart client all share.

```typescript
try {
  await startTimer(projectId);
} catch (err) {
  if (err instanceof ApiError && err.code === "PROJECT_ARCHIVED") { /* … */ }
  toast.error(describeError(err, "Couldn't start timer"));
}
```

### Domain types vs API types

Domain types are kept clean (non-nullable, no API noise); explicit mapper functions translate from the API shape.

### Public APIs via index files

```typescript
// Good
import { useProjects, ProjectsTable } from "@/entities/project";

// Avoid: reaching into another slice's internals
import { useProjects } from "@/entities/project/api/queries";
```

## Testing

Unit tests live next to the source (`*.test.ts` / `*.test.tsx`). E2E tests live under `e2e/`.

Currently 31 test files, 324 unit tests covering: shared/lib helpers, shared/ui primitives, entity hooks, page-level smoke tests, and the auth + timer + Layout flows.

E2E (Playwright, Chromium-only) auto-starts the dev server.

## PWA

`vite-plugin-pwa` is configured for `autoUpdate` registration. The service worker caches the API at a 5-minute TTL (good for dynamic data; avoid stale dashboards on a stale-while-revalidate refresh) and Google Fonts for a year. Config lives in `vite.config.ts`.

## Further reading

- [Feature-Sliced Design](https://feature-sliced.design/)
- [TanStack Query](https://tanstack.com/query)
- [Zod](https://zod.dev/)
