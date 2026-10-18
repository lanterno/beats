/**
 * The Clients page's sentence, before any figure: what the month comes to,
 * then what is in no amount — hours on client projects that are not
 * billable, billable hours with no rate, a timer still running. Every
 * number is the API's; this only puts them into words. An amount is always
 * in one currency, so several currencies are listed, never added.
 */

import type { BillingMonth } from "@/entities/billing";
import { formatMoney, hoursText } from "@/shared/lib";

export interface MonthSummary {
	/** "€3,527.50 billable so far in October, across 2 clients." */
	headline: string;
	/** What the headline's amount leaves out, one sentence each. */
	notes: string[];
}

/** "October", for a 'YYYY-MM'. */
export function monthName(month: string): string {
	const date = new Date(Number(month.slice(0, 4)), Number(month.slice(5, 7)) - 1, 1, 12);
	return date.toLocaleDateString("en-US", { month: "long" });
}

function sum(values: number[]): number {
	// The API's figures are hundredths; summing floats must not invent a third decimal.
	return Math.round(values.reduce((total, v) => total + v, 0) * 100) / 100;
}

function listed(parts: string[]): string {
	if (parts.length < 2) return parts.join("");
	return `${parts.slice(0, -1).join(", ")} and ${parts[parts.length - 1]}`;
}

/**
 * The sentence for a month. `current` says the month is still running, so
 * its figures are "so far".
 */
export function describeMonth(
	month: BillingMonth,
	{ current }: { current: boolean },
): MonthSummary {
	const when = `${current ? "so far " : ""}in ${monthName(month.month)}`;
	const billed = month.clients.filter((client) => client.billableHours > 0);
	const billableHours = sum(billed.map((client) => client.billableHours));
	const across = `across ${billed.length} client${billed.length === 1 ? "" : "s"}`;
	const amounts = month.totals
		.filter((total) => total.amountMinor > 0)
		.map((total) => formatMoney(total.amountMinor, total.currency, total.minorUnits));

	let headline: string;
	if (billableHours === 0) headline = `Nothing billable ${when}.`;
	else if (amounts.length > 0) headline = `${listed(amounts)} billable ${when}, ${across}.`;
	else headline = `${hoursText(billableHours)} billable ${when}, ${across}.`;

	const notes: string[] = [];
	const notBilled = sum(month.clients.map((client) => client.nonBillableHours));
	if (notBilled > 0) notes.push(`${hoursText(notBilled)} on client projects not billed.`);
	const unpriced = sum(month.totals.map((total) => total.unpricedHours));
	if (unpriced > 0) {
		notes.push(`${hoursText(unpriced)} ${unpriced === 1 ? "has" : "have"} no rate yet.`);
	}
	const running = month.clients.filter((client) => client.running).map((client) => client.name);
	if (running.length > 0) {
		notes.push(`A timer is running for ${listed(running)}; it counts once stopped.`);
	}
	return { headline, notes };
}
