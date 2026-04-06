# Project Context for AI Assistants

## Architecture

- **Frontend-only React SPA** - No local backend, connects to external API
- **External API**: `http://localhost:7999` (configurable via `VITE_API_URL`)
- **API Docs**: `http://localhost:7999/openapi.json`
- **Package Manager**: pnpm (preferred)
- **Node Version**: >=25.0.0
- **Architecture**: Feature-Sliced Design (FSD)

## Tech Stack

- React 19 + React Router 7 + TypeScript + Vite
- TanStack Query v5 for data fetching
- TailwindCSS 3 + Radix UI + Lucide React icons
- Zod v4 for runtime validation
- Vitest for testing

## Project Structure (Feature-Sliced Design)

```
client/
├── app/                     # App layer: providers, routing
│   ├── App.tsx
│   └── providers/           # QueryProvider
│
├── pages/                   # Pages layer: route components
│   ├── index/               # Home page
│   ├── project-details/     # Project detail page
│   └── not-found/           # 404 page
│
├── features/                # Features layer: user interactions
│   └── timer/               # Timer feature
│       ├── api/             # API calls
│       ├── model/           # State (useTimer hook)
│       └── ui/              # Components
│
├── entities/                # Entities layer: business objects
│   ├── project/
│   │   ├── api/             # useProjects, useProject queries
│   │   ├── model/           # Types, mappers, colors
│   │   └── ui/              # ProjectsTable, etc.
│   └── session/
│       ├── api/             # useSessions, useUpdateSession
│       ├── model/           # Session types
│       └── ui/              # SessionCard, etc.
│
├── shared/                  # Shared layer: no business logic
│   ├── api/                 # API client, Zod schemas
│   ├── config/              # Environment config
│   ├── lib/                 # Utilities (cn, date, format)
│   └── ui/                  # UI primitives (Button, Table, etc.)
│
└── main.tsx                 # Entry point
```

## Key Conventions

### Path Aliases
- `@/*` → `client/*`
- `@shared/*` → `shared/*` (legacy)

### Data Fetching
- Use TanStack Query hooks (`useProjects`, `useSessions`, etc.)
- Query keys defined in `*Keys` objects
- Mutations invalidate related queries automatically

### API Layer
- API client at `@/shared/api/client`
- Zod schemas for response validation at `@/shared/api/schemas`
- Entity-specific API functions in `entities/*/api/`

### Styling
- TailwindCSS utility classes
- `cn()` utility for conditional classes (from `@/shared/lib`)
- Theme configured in `client/global.css`

### Routing
- Routes defined in `client/app/App.tsx`
- Page components in `client/pages/*/`
- React Router 7 SPA mode

### Module Boundaries
- Import from public APIs (`index.ts`) only
- Never import internal files directly
- Each slice (entity/feature) is self-contained

## Development

```bash
pnpm dev        # Dev server on port 8080
pnpm build      # Build to dist/spa/
pnpm typecheck  # TypeScript check (strict mode)
pnpm test       # Run tests
```

**Note**: Backend API must be running at `http://localhost:7999` for frontend to work.
