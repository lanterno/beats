/**
 * Ergonomic re-exports of the generated OpenAPI types.
 *
 * `generated.ts` is produced by `pnpm gen:types` from the FastAPI OpenAPI
 * schema. Its native shape is `components["schemas"]["Name"]`, which is
 * verbose at call sites. This module exposes:
 *
 *   - `Schemas` — index type for ad-hoc access: `Schemas["WeeklyDigestResponse"]`
 *   - `Paths`   — same for the path map, useful when wiring openapi-fetch
 *
 * Prefer these over the hand-written Zod-derived types in `./schemas` for new
 * code. The Zod schemas remain as runtime-validation backstops; they may be
 * retired incrementally as consumers migrate.
 */

import type { components, paths } from "./generated";

export type Schemas = components["schemas"];
export type Paths = paths;
