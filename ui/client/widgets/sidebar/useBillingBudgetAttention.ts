/**
 * Whether the Clients nav item wears a dot: only while some active billing
 * budget is used up, counting a running timer whose `overAt` has passed
 * (docs/billing.md, phase 1b). "Near" lights nothing here — a dot lit for
 * ten days would teach people to ignore it, and the Clients page's notes
 * say near. Nothing is read unless the nav offers Clients, and a failed read
 * lights nothing.
 */

import { billingBudgetState, useBillingBudgets } from "@/entities/billing";
import { browserTimeZone, useNow } from "@/shared/lib";

export function useBillingBudgetAttention(showClients: boolean): boolean {
	const { data } = useBillingBudgets(browserTimeZone(), { enabled: showClients });
	const budgets = showClients ? (data ?? []) : [];
	// A minute's tick, only while a running timer could use one up.
	const now = useNow(60_000, { enabled: budgets.some((b) => b.active && b.running) });
	return budgets.some((b) => b.active && billingBudgetState(b, now) === "used_up");
}
