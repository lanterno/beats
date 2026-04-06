# Beats UI

A modern time tracking application for managing project hours and work sessions.

## Tech Stack

- **Framework**: React 19 + TypeScript + Vite
- **Routing**: React Router 7
- **Data Fetching**: TanStack Query v5
- **Styling**: TailwindCSS 3 + Radix UI
- **Validation**: Zod v4
- **Package Manager**: pnpm

## Getting Started

```bash
# Install dependencies
pnpm install

# Start development server (port 8080)
pnpm dev

# Type check
pnpm typecheck

# Build for production
pnpm build
```

**Note**: The backend API must be running at `http://localhost:7999` for the frontend to work.

## Architecture

This project follows **Feature-Sliced Design (FSD)**, a modern frontend architectural methodology that organizes code by business domains rather than technical types.

### Layer Structure

```
client/
├── app/                    # App layer: routing, providers, global config
├── pages/                  # Pages layer: route components (orchestration)
├── features/               # Features layer: user interactions with business logic
├── entities/               # Entities layer: business domain objects
└── shared/                 # Shared layer: reusable utilities with no business logic
```

### Layers Explained

| Layer | Purpose | Can Import From |
|-------|---------|-----------------|
| `app/` | Application shell, providers, routing | All layers |
| `pages/` | Full pages, compose features/entities | features, entities, shared |
| `features/` | User interactions (e.g., timer) | entities, shared |
| `entities/` | Business objects (project, session) | shared |
| `shared/` | Utilities, UI primitives, config | Nothing (foundation layer) |

### Slice Structure

Each entity/feature follows a consistent internal structure:

```
entities/project/
├── api/          # Data fetching (TanStack Query hooks, API functions)
├── model/        # Types, domain logic, mappers
├── ui/           # Presentational components
└── index.ts      # Public API (barrel exports)
```

## Best Practices

### 1. TanStack Query for Data Fetching

All server state is managed through TanStack Query, providing:
- Automatic caching and deduplication
- Background refetching
- Optimistic updates
- Consistent loading/error states

```typescript
// Use query hooks in components
const { data, isLoading, error } = useProjects();

// Invalidate after mutations
const queryClient = useQueryClient();
queryClient.invalidateQueries({ queryKey: projectKeys.all });
```

### 2. Runtime Validation with Zod

API responses are validated at runtime using Zod schemas:

```typescript
const data = await get<unknown>("/api/projects/");
return parseApiResponse(ApiProjectListSchema, data);
```

### 3. Type-Safe API Layer

Domain types are separated from API types with explicit mappers:

```typescript
// API type (matches backend response)
interface ApiProject { id?: string | null; name: string; ... }

// Domain type (clean, non-nullable)
interface Project { id: string; name: string; color: string; ... }

// Mapper function
function toProject(api: ApiProject): Project { ... }
```

### 4. Public APIs via Index Files

Each module exposes a public API through `index.ts`:

```typescript
// Import from public API
import { useProjects, ProjectsTable } from "@/entities/project";

// Never import internals directly
// BAD: import { useProjects } from "@/entities/project/api/queries";
```

### 5. TypeScript Strict Mode

The project uses TypeScript strict mode for maximum type safety:
- `strict: true`
- `strictNullChecks: true`
- `noImplicitAny: true`

## Project Structure

```
client/
├── app/
│   ├── App.tsx              # Root component with providers and routing
│   └── providers/           # QueryProvider (TanStack Query)
│
├── pages/
│   ├── index/               # Home page (dashboard)
│   ├── project-details/     # Project detail page
│   └── not-found/           # 404 page
│
├── features/
│   └── timer/               # Timer feature (start/stop work sessions)
│       ├── api/             # Timer API calls
│       ├── model/           # useTimer hook, timer state
│       └── ui/              # TimerManager, TimerDisplay
│
├── entities/
│   ├── project/             # Project entity
│   │   ├── api/             # useProjects, useProject, useProjectWeeks
│   │   ├── model/           # Project types, color assignment, mappers
│   │   └── ui/              # ProjectsTable, TopProjectsTable, StatsCards
│   │
│   └── session/             # Session entity (work session / beat)
│       ├── api/             # useSessions, useUpdateSession
│       ├── model/           # Session types, mappers
│       └── ui/              # SessionCard, SessionEditForm, DailySummaryGrid
│
├── shared/
│   ├── api/                 # API client, Zod schemas, error handling
│   ├── config/              # Environment configuration
│   ├── lib/                 # Utilities (cn, date, format)
│   └── ui/                  # UI primitives (Button, Table, Progress, etc.)
│
├── global.css               # Global styles and CSS variables
└── main.tsx                 # Entry point
```

## Path Aliases

| Alias | Path |
|-------|------|
| `@/*` | `client/*` |
| `@shared/*` | `shared/*` (legacy, prefer `@/shared/*`) |

## Further Reading

- [Feature-Sliced Design](https://feature-sliced.design/) - Architecture methodology
- [TanStack Query](https://tanstack.com/query) - Data fetching library
- [Zod](https://zod.dev/) - TypeScript-first schema validation
