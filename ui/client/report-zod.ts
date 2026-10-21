/**
 * Imported first by client/report.tsx, before any zod schema is built.
 *
 * Zod compiles its object parsers with `new Function` once a probe has found
 * that eval works, and it decides when each schema is built. The report
 * page's CSP has no 'unsafe-eval', so the probe would be refused and reported
 * as a violation, though zod catches it and parses without. jitless skips
 * the probe and the compiler; it must be set before a schema exists, which
 * is why it is a module of its own and not a line in report.tsx.
 */
import { z } from "zod";

z.config({ jitless: true });
