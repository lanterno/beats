/**
 * Billing API Functions
 * Under /api/billing, outside every device-token prefix: money is never
 * under /api/projects or /api/beats (docs/billing.md).
 */

import {
	ApiBillableOverrideListSchema,
	ApiBillingBudgetSchema,
	ApiBillingBudgetStatusListSchema,
	ApiProjectBillingListSchema,
	ApiProjectBillingSchema,
	BillingMonthSchema,
	del,
	get,
	parseApiResponse,
	put,
} from "@/shared/api";
import { browserTimeZone } from "@/shared/lib";
import type {
	BillingBudget,
	BillingBudgetInput,
	BillingBudgetScope,
	BillingBudgetStatus,
	BillingMonth,
	ProjectBilling,
	ProjectBillingInput,
} from "../model";
import {
	toApiBillingBudgetInput,
	toApiProjectBillingInput,
	toBillingBudget,
	toBillingBudgetStatus,
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
 * Stop billing a project. PROJECT_HAS_BILLING_BUDGET without
 * `removeBillingBudget` when it has a billing budget, which then goes with
 * it; RETROACTIVE_CHANGE without `rewritePast` when it has terms before the
 * current month. Send `removeBillingBudget` true only once the user has seen
 * the budget named.
 */
export async function removeProjectBilling(
	projectId: string,
	rewritePast: boolean,
	removeBillingBudget: boolean,
): Promise<void> {
	const params = new URLSearchParams({
		tz: browserTimeZone(),
		rewrite_past: String(rewritePast),
		remove_billing_budget: String(removeBillingBudget),
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

const BUDGET_PATHS: Record<BillingBudgetScope, string> = {
	client: "/api/billing/budgets/clients",
	project: "/api/billing/budgets/projects",
};

/** Every billing budget, read as of today in `tz`, by client name; `[]` when there are none. */
export async function fetchBillingBudgets(tz: string): Promise<BillingBudgetStatus[]> {
	const params = new URLSearchParams({ tz });
	const data = await get<unknown>(`/api/billing/budgets?${params.toString()}`);
	return parseApiResponse(ApiBillingBudgetStatusListSchema, data).map(toBillingBudgetStatus);
}

/**
 * Give a client, or a billed project, its billing budget, replacing the one
 * it had. 404 when the scope is not yours, 409 BILLING_BUDGET_NEEDS_BILLING
 * on a project that is not billed, and a 422 naming the key. Not gated: a
 * budget changes no billable figure.
 */
export async function putBillingBudget(
	scope: BillingBudgetScope,
	scopeId: string,
	input: BillingBudgetInput,
): Promise<BillingBudget> {
	const data = await put<unknown>(
		`${BUDGET_PATHS[scope]}/${scopeId}`,
		toApiBillingBudgetInput(input),
	);
	return toBillingBudget(parseApiResponse(ApiBillingBudgetSchema, data));
}

/** Take a billing budget away. 204 whether or not there was one. */
export async function deleteBillingBudget(
	scope: BillingBudgetScope,
	scopeId: string,
): Promise<void> {
	await del<void>(`${BUDGET_PATHS[scope]}/${scopeId}`);
}
