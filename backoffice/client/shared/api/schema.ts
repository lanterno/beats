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
/** Which revision of the API serves, its commit, and whether the newest became ready. */
export type DeployStateReport = components["schemas"]["DeployStateReport"];
/** What shipped: the API's builds, the commit serving, the web app's live commit. */
export type ReleasesReport = components["schemas"]["ReleasesReport"];
export type ReleaseRow = components["schemas"]["ReleaseRow"];
/** The newest commit the deploy freeze held back that nothing has shipped since. */
export type HeldBuild = components["schemas"]["HeldBuild"];
/** The deploy freeze as it stands, or unknown when its bucket did not answer. */
export type FreezeState = components["schemas"]["FreezeState"];
/** The public status file read back, or why it could not be. */
export type PublicStatus = components["schemas"]["PublicStatus"];
/** The Google Cloud project and the API's service, for the console links. */
export type Deployment = components["schemas"]["Deployment"];
/** Every account with its dates and counts, under the People page's totals. */
export type AccountsReport = components["schemas"]["AccountsReport"];
export type AccountRow = components["schemas"]["AccountRow"];
/** Hours logged all told and in UTC buckets of a day, a week or a month. */
export type HoursReport = components["schemas"]["HoursReport"];
export type HoursBucket = components["schemas"]["HoursBucket"];
export type HoursUnit = HoursReport["unit"];
