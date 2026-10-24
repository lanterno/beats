---
linear: unfiled
title: "pnpm gen:types cannot run: openapi-typescript 7.13 crashes on TypeScript 7"
team: AHM
project: lifepete
milestone: none
labels: [ui, Bug]
state: Todo
priority: 3
parent: none
---

`cd ui && pnpm gen:types` fails before it reads anything:

```
node_modules/.pnpm/openapi-typescript@7.13.0_typescript@7.0.2/.../lib/ts.mjs:11
const BOOLEAN = ts.factory.createKeywordTypeNode(ts.SyntaxKind.BooleanKeyword);
TypeError: Cannot read properties of undefined (reading 'createKeywordTypeNode')
```

The crash is at module load, so it is independent of the input document.
`openapi-typescript@^7.13.0` reaches for `ts.factory`, which TypeScript 7
(`typescript@^7.0.2`, both in `ui/package.json`) no longer exposes the same
way. This is on `main`, not something a branch introduced.

## Why it matters

Two things are broken, neither loudly:

- `client/shared/api/generated.ts` cannot be regenerated, so it is frozen at
  whatever the last working run produced and drifts further from the API with
  every route added.
- `pnpm gen:types:check` is a **pre-push gate** (`lefthook.yml`) and part of
  `.github/workflows/ui.yml`. It runs `gen:types` first, so it fails for this
  reason rather than for drift — which means the gate currently cannot detect
  the thing it exists to detect.

## What saves it from being urgent

Nothing imports the generated types. `client/shared/api/schema.ts` re-exports
them (`Schemas`, `Paths`) and has no consumers; the SPA validates with the
hand-written Zod schemas in `client/shared/api/schemas.ts` instead. So the
stale file misleads no runtime code today.

## Fix

Upgrade `openapi-typescript` to a release that supports TypeScript 7, or pin
TypeScript back for this one tool. Then regenerate `generated.ts` — it will be
a large diff covering every route added since it last ran, including phase 1c's
`/api/reports/{token}` and `/api/clients/{id}/links`.

Worth deciding at the same time whether `schema.ts` and `generated.ts` earn
their place at all, given nothing imports them.
