# Back office

The operator's control plane UI ([docs/backoffice.md](../docs/backoffice.md)):
what needs attention, accounts, organisations, trust and safety, capacity, and
the records only the control plane keeps (jobs, audit, compliance) —
operational metadata, never user content. Served by the operator deployment
itself (`operator_server.py` mounts the build), behind Google Cloud IAP, so the
browser has one origin and the credential is IAP's cookie.

It wears the app's look (the sky, the panels, the two hours; tokens in
`client/tokens.css`), with a "Back office" mark on every page so an operator is
never unsure which surface they are on.

## Running

```bash
pnpm install
pnpm dev             # Vite on :8081, proxying /api/operator to :7998
cd ../api && just run-operator-locally   # the operator API (needs .env.operator;
                                         # copy api/.env.operator.example)
```

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
├── app/               App.tsx (the routes), places.ts (where the back office
│                      goes, grouped by job), Sidebar.tsx and Topbar.tsx (the
│                      mark, who is signed in, the hour)
├── pages/             Attention, Accounts, Organisations, Trust, Capacity,
│                      Jobs, Audit, Compliance — one file per operator job
└── shared/
    ├── api/           same-origin fetch client (no token: IAP's cookie is the
    │                  credential), the command POST, generated types + schema
    ├── lib/           renderings (bytes, days, counts), what an audit row
    │                  changed, the hour, and what a failure says to the operator
    ├── config/        brand.ts, stamped by scripts/gen_brand.py
    └── ui/            Page, Panel, Table, Facts, the icons, and CommandForm —
                       one command as a row with its typed confirmation
```

A workspace of its own: `ui/`'s workspace reaches only its `tools/*`, so this
one pins the same `packageManager` and copies its supply-chain policy
(`pnpm-workspace.yaml`); `tools/openapi-types` repeats `ui/`'s package for the
same reason (openapi-typescript drives the compiler API that typescript@7 no
longer exposes). Nothing is shared with `ui/` on purpose — the API-client
pattern is small enough to copy once and let diverge.

Every mutation goes through `CommandForm` → `POST /api/operator/commands/{name}`
(docs/backoffice.md § Commands). The browser adds the `Origin` header the
server requires on writes; nothing here can or should fake one.
