# Back office

The operator's control plane UI ([docs/backoffice.md](../docs/backoffice.md)):
today, accounts, organisations, trust and safety, capacity, jobs, privacy and
the audit — operational metadata, never user content. Served by the operator
deployment itself (`operator_server.py` mounts the build), behind Google Cloud
IAP, so the browser has one origin and the credential is IAP's cookie.

It wears the app's look (the sky, the panels, the two hours; tokens in
`client/tokens.css`), with a "Back office" mark on every page so an operator is
never unsure which surface they are on, and a label above every page saying
*which* deployment it is — the hostname is the only source for that, since one
image serves local and production alike (`shared/lib/where.ts`).

## Running

```bash
pnpm install
pnpm dev             # Vite on :8081, proxying /api/operator to :7998
cd ../api && just run-operator-locally   # the operator API (needs .env.operator;
                                         # copy api/.env.operator.example)
```

Both ports are overridable, for a second checkout on the same machine:

```bash
BACKOFFICE_PORT=8085 BACKOFFICE_OPERATOR_API=http://localhost:7995 pnpm dev
```

The port is strict rather than stepping to the next free one, and
`OPERATOR_ORIGIN` in `api/.env.operator` has to name whichever port you chose:
the operator API refuses a write whose `Origin` is not its own, so a dev
server that quietly moved reads every page and cannot run a command.

```bash
pnpm test            # Vitest (node env — the pages are tables over API figures)
pnpm lint            # biome check .
pnpm typecheck       # tsc
pnpm build           # → ../api/src/beats/operator/static (gitignored; Cloud
                     #   Build runs this before the API image build)
pnpm gen:types:check # regenerate client/shared/api/* from the operator API's
                     #   schema and fail on drift (pre-push and CI do this)
```

## Layout

Feature-Sliced like `ui/`, as far as this app needs layers:

```
client/
├── app/App.tsx        the shell: the grouped sidebar, the mark, the
│                      deployment label, the /me badge, the routes
├── app/Palette.tsx    ⌘K: pages, a command's review, one exact account
├── pages/             Today, Queue, Accounts, Account, Review, Organisations,
│                      Trust, Capacity, Jobs, Compliance, Audit, Runbooks —
│                      one file per operator job
└── shared/
    ├── api/           same-origin fetch client (no token: IAP's cookie is the
    │                  credential), the command POST, generated types + schema
    ├── lib/           renderings (bytes, days, counts), the hour, which
    │                  deployment this is, what a failure says to the
    │                  operator, and the queue's and the palette's rules
    ├── commands.ts    each account command in the operator's words
    ├── runbooks.ts    the runbooks, each with its reviewed_on
    ├── config/        brand.ts, stamped by scripts/gen_brand.py
    └── ui/            Page, Panel, Table, Facts, the icons, and CommandForm —
                       one command as a row with its typed confirmation
```

The sidebar is grouped by the question being asked — Now, People, Platform,
Governance — and a place is listed only once its page exists, so the nav never
offers a screen that is not there. What each page is for is in
[docs/backoffice.md](../docs/backoffice.md) § *The pages*.

A workspace of its own: `ui/`'s workspace reaches only its `tools/*`, so this
one pins the same `packageManager` and copies its supply-chain policy
(`pnpm-workspace.yaml`); `tools/openapi-types` repeats `ui/`'s package for the
same reason (openapi-typescript drives the compiler API that typescript@7 no
longer exposes). Nothing is shared with `ui/` on purpose — the API-client
pattern is small enough to copy once and let diverge.

Every mutation goes through `CommandForm` → `POST /api/operator/commands/{name}`
(docs/backoffice.md § Commands). The browser adds the `Origin` header the
server requires on writes; nothing here can or should fake one.
