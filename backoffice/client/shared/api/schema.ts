/**
 * The operator API's shapes, read off the generated types so the pages and
 * the API cannot drift apart silently: `gen:types:check` fails when
 * `dump_openapi_operator.py`'s output no longer matches what is committed.
 */

import type { components } from "./generated";

export type AttentionCounts = components["schemas"]["AttentionCounts"];
export type AccountMatch = components["schemas"]["AccountMatch"];
export type AccountDetail = components["schemas"]["AccountDetail"];
export type OrganisationSummary = components["schemas"]["OrganisationSummary"];
export type OrganisationDetail = components["schemas"]["OrganisationDetail"];
export type OrgAuditRow = components["schemas"]["OrgAuditRow"];
export type AbuseReport = components["schemas"]["AbuseReport"];
/** A day and a figure: signups a day, one account's coach cost a day. */
export type DayFigure = components["schemas"]["DayFigure"];
export type CapacityReport = components["schemas"]["CapacityReport"];
export type OperatorMe = components["schemas"]["OperatorMe"];
/** What a command would do, answered without doing it. */
export type CommandPreview = components["schemas"]["CommandPreview"];
/** The hour's sign-ups against the usual, and the largest network's share. */
export type SignupWave = components["schemas"]["SignupWave"];
/** One platform control as it stands (docs/backoffice.md § Controls). */
export type ControlState = components["schemas"]["ControlState"];
/** One person on the operator allowlist, as the deployment was started. */
export type AccessEntry = components["schemas"]["AccessEntry"];
/** One logged erasure request: a reference and an id, never an address. */
export type ErasureRequestState = components["schemas"]["ErasureRequestState"];
/** One row behind an Attention count: ids and dates, never a name. */
export type QueueRow = components["schemas"]["QueueRow"];
/** Live health from Cloud Monitoring: live, stale (with its age) or unavailable. */
export type HealthReport = components["schemas"]["HealthReport"];
