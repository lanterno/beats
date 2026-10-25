# Beats UI

React 19 SPA — Vite 8, TypeScript 6, TailwindCSS 4, pnpm.

## Architecture

Feature-Sliced Design (FSD):

```
client/
├── app/           App.tsx (router + providers), Layout.tsx (authenticated
│                  shell), session.ts (wires auth into the session port)
├── pages/         Route-level components — homepage, index, insights, coach,
│                  plan, projects-index, project-details, clients, organisations,
│                  settings, not-found
├── widgets/       Cross-page composite UI — sidebar (desktop) + mobile header
├── features/      User interactions — timer, auth
├── entities/      Business objects — project, absence, session, planning,
│                  coach, intelligence, calendar, github, client, billing,
│                  organisation
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
  FastAPI app (no server needed; it reads `api/.env.test` for the settings the app
  needs to import) and regenerates `shared/api/generated.ts`, which `coachApi.ts`,
  `intelligenceApi.ts` and `importSummary.ts` read through `shared/api/schema.ts`;
  `gen:types:check` fails on drift, in pre-push and in CI. The generator,
  `openapi-typescript`, drives the TypeScript compiler API that `typescript@7` no
  longer exposes, so it lives in its own workspace package, `tools/openapi-types`,
  with a TypeScript 5 of its own — a peer dependency cannot be overridden away from
  the root's compiler, and the SPA's compiler stays on 7. The API's own `/docs` sits
  behind the auth middleware and a browser tab carries no bearer token, so it is not
  reachable from the SPA — read `shared/api/openapi.json` instead.
- **Linting**: Biome (replaces ESLint+Prettier) — tabs, line width 100. Covers
  `client/`, `e2e/` and the root config files; accessibility rules fail the
  check, all but `noAutofocus` (dialogs focus their first field on purpose).
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
- **Text on the sky** glows in the sky's colour (`--sky-halo-shadow`), because the page
  scrolls over the hills and the dusk's warm band, where no ink clears 4.5:1. `Layout`'s
  `<main>` carries `.on-sky`, which every descendant inherits; any element with a `bg-*`
  class, and every form control, turns it off for its subtree. The marketing page applies
  the shadow to its sky copy by class instead.
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
(`docs/project-page.md`). `ProjectDetails.tsx` owns the reads its panels
share — `/contract/week` for the open week, the current week (the balance is pinned to
today) and the next, the ledger, the sessions and the running timer — and the open
week, which is the URL's `?week=`, so ‹ ›, a ledger row and a time-off entry all move
one navigator; it also owns the booking dialog every "Book time off" opens and the
Holidays dialog (`HolidaysDialog`) the register's constants open. Under
`ProjectHeader` the main column is `Standing` ("Where you stand": the balance and its
proof, or a side project's pace, beside the open week), `WeekDays` ("Days") and
`WeekLedger` ("Earlier weeks", whose "Adjust balance" and adjustment rows open the
`AdjustmentDialog`); the rail holds `ContractRegister` (the contract with
its step chart and the month's timesheet download, `TimesheetDownload`, or the
goal), `TimeOff` on a day job (whose tally reads the vacation entitlement's year
when the contract has one), `BillingPanel` on a freelance project (its client and
dated billing terms, edited through `BillingDialog`, and its billing budget; the page
reads the billing and the entry marks and hands them to it and to `WeekDays`, whose
finished sessions then carry a Billable pill), and `QuietFacts`. The layout
queries the content column (`@container/content`), not the viewport, and the rail sits
beside the column from 860 px of it. Every figure is the API's, a ledger row's +/− too
on a week that closes (its `balance_moved`); the page's own arithmetic — the sentence,
the Sunday projection, the ledger's rows, and the +/− on a week without a close
(worked − expected, else worked − goal) — is pure functions in `entities/project/model`
(`standing.ts`, `ledger.ts`), a test per branch. Tests and E2E specs find the panels by their region names, never by class.

## Clients and billing

`pages/clients` is `/clients`, a month of what each client is owed (`docs/billing.md`):
the sentence (`summary.ts`), a `ClientPanel` per client, the freelance hours billed to
no one. The sidebar offers it once there is a client or a freelance project
(`useShowClients`). Every hour and amount is the API's `/api/billing/month`; the SPA
never prices. Money is integer minor units with the API's `minor_units`
(`shared/lib/money.ts`: `formatMoney`; `parseAmount` reads the string, never
`parseFloat`, and `parseMoney` and `parseHours` are made of it). The one billing rule
run here is the flag, `entryBillable` in `entities/billing/model/resolve.ts`,
parity-tested against the Python. A write that may change a month already over goes
through `withPastConsent`, which asks in the API's words before sending again with
`rewrite_past`. `ClientDialog` and `BillableSwitch` live in their entities, since both
the Clients page and the project page open them; the query roots a session or timer
write invalidates are in `shared/api/keys.ts`, so no entity imports another.

Billing budgets (phase 1b) are read as of today with `useBillingBudgets`, under the
billing root, so every billing write, session write and timer start or stop refreshes
them; `useTimer` also refreshes the root when the polled status's `since` changes, so a
timer started from a device reaches them. Their words, and the only thing worked out
here, a running timer's crossing instant against the clock, are pure functions in
`entities/billing/model/budget.ts` (`describeBillingBudget`, `billingBudgetState`);
`BillingBudgetRow`, `BillingBudgetMeter` and `BillingBudgetDialog` live in the entity,
since the Clients page and the Billing panel both draw and edit them. The minute's tick
is `useNow` and the hours are `hoursText`, both in `shared/lib`, so an entity or a widget
can read them. The Clients nav item wears a dot only while an active budget is used up
(`widgets/sidebar/useBillingBudgetAttention.ts`). When the budgets cannot be read, each
block says "Budgets aren't available right now." and the rest renders as before.

Report links (phase 1c) let a client read its own hours with no account. Each
`ClientPanel` carries a *Shared reports* disclosure (`ReportLinksBlock`, in the billing
entity): the client's links with what each shows in words, Copy, Revoke, and *Share
<month>* behind two checkboxes. It reads only once opened — a panel per client would
otherwise be a request per client on load — and Copy builds the URL from the SPA's own
origin, since the API returns a bare token. The reader's page is `/r/:token`
(`pages/report`), the second route outside `ProtectedRoute` and the only one that shows
anyone's data: no `Layout`, no nav, no sign-in prompt, and one message for every way a
link fails, because the API answers one 404 for all of them. It reads through
`getPublic`, a GET that never attaches the session, so the page cannot read differently
for its owner than for the client they sent it to.

## Organisations

`entities/organisation` is the SPA's half of docs/organisations.md: the hooks under
`organisationsRootKey`, `OrganisationMark` (the tile and name every list marks an
organisation's project with), `describeShareFrom`, `inviteUrl`, and
`ConnectProjectDialog`. A `Project` carries `organisation` when an organisation owns it
and a `Session` its `organisationId`. `pages/organisations` is `/organisations` (my
invitations, my organisations, the ones I left), `/organisations/:id` (the organisation:
*What Acme can see* and *Leave* for everyone; members, invites, requests, projects,
assignments and settings for admins), `/organisations/:id/record` and `/visible` (one
component over two hooks: the organisation's read, and the same read narrowed to me),
`/organisations/:id/archive` (my own rows that are its record, with a CSV) and
`/organisations/join/:token`. On the project side: the index and the picker mark an
organisation's project (the sidebar names it on hover, since a tile there cost the name
its width); the activity feed offers *Everything · Personal · Acme* (`?owner=`); the
project page's header names the organisation, its rail's `OrganisationPanel` says whose
the project is and links to what they see, or on a personal project offers *Connect to
Acme…* (`ConnectProjectDialog`, on the page rather than inside the settings drawer), and
the settings drawer disables the organisation's fields; a note shown on an
organisation's project says "Acme can read this note".
Every write that changes what is on the member's own timeline — joining, leaving, an
assignment, a connect — invalidates the project and session roots too. The Organisations
nav item wears a dot while an invitation to this account waits
(`widgets/sidebar/useInvitationAttention.ts`); the invitation itself is joined through the
link the inviter sent, since the API hands out no token. A page behind `ProtectedRoute`
opened while signed out — an invite URL, a project link — is kept (`shared/lib/returnTo.ts`)
and is where sign-in, passkey or SSO, lands.

Employment (stages 3–4): the organisation page adds Teams, pending absence requests (the
note is addressed to the decider), timesheets with the frozen figures and
approve / ask-for-changes / reopen, *Your timesheets* with a submit for ended months, the
audit-log disclosure, Contract… and Enter time… per assignment, and the record page's
Record/Compliance CSV downloads; managers (scoped to their teams) and viewers read the
record. On a managed assignment the member's project page asks instead of booking
(`RequestAbsenceDialog`, the request list in `TimeOff`), the contract register names the
organisation as the terms' owner, and the rail's Organisation panel carries the project's
timesheets and submit; a decider-entered session wears "entered for you".

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
  `screen.findByRole` / `findByText`. Layout.test.tsx mirrors this shape for a
  hook-heavy component.

Before adding a test, see **What to test, and what not to** in the repo-root
`CLAUDE.md` — in particular that configuration, framework behaviour, and
whatever a mock was told to return are not worth pinning.

## Linting

```bash
pnpm lint          # biome check .
pnpm lint:fix      # biome check --write .
pnpm typecheck     # tsc
```
