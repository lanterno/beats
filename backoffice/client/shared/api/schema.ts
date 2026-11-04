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
export type CapacityReport = components["schemas"]["CapacityReport"];
export type OperatorMe = components["schemas"]["OperatorMe"];
