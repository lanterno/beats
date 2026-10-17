/**
 * Billing API Functions
 * Under /api/billing, outside every device-token prefix: money is never
 * under /api/projects or /api/beats (docs/billing.md).
 */

import {
	ApiBillableOverrideListSchema,
	ApiProjectBillingListSchema,
	ApiProjectBillingSchema,
	BillingMonthSchema,
	del,
	get,
	parseApiResponse,
	put,
} from "@/shared/api";
import { browserTimeZone } from "@/shared/lib";
import type { BillingMonth, ProjectBilling, ProjectBillingInput } from "../model";
import {
	toApiProjectBillingInput,
	toBillingMonth,
	toOverrideMap,
	toProjectBilling,
} from "../model";

/** Every billed project's billing, by project id: a small set, read whole. */
export async function fetchProjectBillings(): Promise<Map<string, ProjectBilling>> {
	const data = await get<unknown>("/api/billing/projects");
	const billings = parseApiResponse(ApiProjectBillingListSchema, data).map(toProjectBilling);
	return new Map(billings.map((billing) => [billing.projectId, billing]));
}

/**
 * Bill a freelance project, or replace its client and terms. 409
 * NOT_FREELANCE on any other kind, CURRENCY_MISMATCH for a move to a client
 * in another currency once something is priced, and RETROACTIVE_CHANGE
 * without `rewritePast` for a change before the current month.
 */
export async function setProjectBilling(
	projectId: string,
	input: ProjectBillingInput,
	rewritePast: boolean,
): Promise<ProjectBilling> {
	const params = new URLSearchParams({ tz: browserTimeZone() });
	const data = await put<unknown>(`/api/billing/projects/${projectId}?${params.toString()}`, {
		...toApiProjectBillingInput(input),
		rewrite_past: rewritePast,
	});
	return toProjectBilling(parseApiResponse(ApiProjectBillingSchema, data));
}

/**
 * Stop billing a project. RETROACTIVE_CHANGE without `rewritePast` when it
 * has terms before the current month.
 */
export async function removeProjectBilling(projectId: string, rewritePast: boolean): Promise<void> {
	const params = new URLSearchParams({
		tz: browserTimeZone(),
		rewrite_past: String(rewritePast),
	});
	await del<void>(`/api/billing/projects/${projectId}?${params.toString()}`);
}

/** Every entry mark, by entry id: they are exceptions, so the list is small. */
export async function fetchBillableOverrides(): Promise<Map<string, boolean>> {
	const data = await get<unknown>("/api/billing/entries");
	return toOverrideMap(parseApiResponse(ApiBillableOverrideListSchema, data));
}

/** Mark one entry billable or not, whatever its project's term says. 404 when it is not yours. */
export async function setEntryBillable(beatId: string, billable: boolean): Promise<void> {
	await put<unknown>(`/api/billing/entries/${beatId}`, { billable });
}

/** Return an entry to its project's rule. 204 whether or not it had a mark. */
export async function clearEntryBillable(beatId: string): Promise<void> {
	await del<void>(`/api/billing/entries/${beatId}`);
}

/**
 * One month per client and currency, each entry on the local day it started
 * in `tz`. 409 MONTH_NOT_STARTED for a month after the current one.
 */
export async function fetchBillingMonth(month: string, tz: string): Promise<BillingMonth> {
	const params = new URLSearchParams({ month, tz });
	const data = await get<unknown>(`/api/billing/month?${params.toString()}`);
	return toBillingMonth(parseApiResponse(BillingMonthSchema, data));
}
