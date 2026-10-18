/**
 * The Clients page's sentence: one currency, several (listed, never
 * added), hours that have no rate or are not billable, a timer still
 * running, and in the current month the billing budgets near or used up,
 * each in the API's figures.
 */
import { describe, expect, it } from "vitest";
import type {
	BillingBudgetStatus,
	BillingMonth,
	ClientBilling,
	CurrencyTotal,
} from "@/entities/billing";
import { describeMonth } from "./summary";

function client(overrides: Partial<ClientBilling>): ClientBilling {
	return {
		clientId: overrides.name ?? "c",
		name: "Studio Kite",
		archived: false,
		currency: "EUR",
		minorUnits: 2,
		running: false,
		billableHours: 0,
		nonBillableHours: 0,
		unpricedHours: 0,
		amountMinor: 0,
		lines: [],
		entries: [],
		...overrides,
	};
}

function total(overrides: Partial<CurrencyTotal>): CurrencyTotal {
	return {
		currency: "EUR",
		minorUnits: 2,
		billableHours: 0,
		unpricedHours: 0,
		amountMinor: 0,
		...overrides,
	};
}

function month(clients: ClientBilling[], totals: CurrencyTotal[], key = "2026-10"): BillingMonth {
	return { month: key, first: `${key}-01`, last: `${key}-17`, totals, clients, unattached: [] };
}

describe("describeMonth", () => {
	it("says what one currency comes to, across the clients that have billable hours", () => {
		const october = month(
			[
				client({ name: "Studio Kite", billableHours: 30, amountMinor: 255000 }),
				client({ name: "Acme", billableHours: 11.5, amountMinor: 97750 }),
				client({ name: "Quiet Co" }),
			],
			[total({ billableHours: 41.5, amountMinor: 352750 })],
		);
		expect(describeMonth(october, { current: true })).toEqual({
			headline: "€3,527.50 billable so far in October, across 2 clients.",
			notes: [],
		});
		// A month that is over is not "so far".
		expect(
			describeMonth(month(october.clients, october.totals, "2026-09"), { current: false }).headline,
		).toBe("€3,527.50 billable in September, across 2 clients.");
	});

	it("lists each currency's amount on its own rather than adding them", () => {
		const october = month(
			[
				client({ name: "Studio Kite", billableHours: 41.5, amountMinor: 352750 }),
				client({ name: "Bay Labs", currency: "USD", billableHours: 10, amountMinor: 120000 }),
				client({
					name: "Kaisha",
					currency: "JPY",
					minorUnits: 0,
					billableHours: 2,
					amountMinor: 30000,
				}),
			],
			[
				total({ billableHours: 41.5, amountMinor: 352750 }),
				total({ currency: "USD", billableHours: 10, amountMinor: 120000 }),
				total({ currency: "JPY", minorUnits: 0, billableHours: 2, amountMinor: 30000 }),
			],
		);
		expect(describeMonth(october, { current: true }).headline).toBe(
			"€3,527.50, $1,200.00 and ¥30,000 billable so far in October, across 3 clients.",
		);
	});

	it("names the hours no amount counts: not billable, and billable without a rate", () => {
		const october = month(
			[
				client({
					billableHours: 41.5,
					nonBillableHours: 3.25,
					unpricedHours: 6,
					amountMinor: 301750,
				}),
			],
			[total({ billableHours: 41.5, unpricedHours: 6, amountMinor: 301750 })],
		);
		expect(describeMonth(october, { current: true })).toEqual({
			headline: "€3,017.50 billable so far in October, across 1 client.",
			notes: ["3.25 h on client projects not billed.", "6 h have no rate yet."],
		});
	});

	it("gives the hours when nothing billable is priced yet, never an amount of nothing", () => {
		const october = month(
			[client({ billableHours: 6, unpricedHours: 6 })],
			[total({ billableHours: 6, unpricedHours: 6 })],
		);
		expect(describeMonth(october, { current: true })).toEqual({
			headline: "6 h billable so far in October, across 1 client.",
			notes: ["6 h have no rate yet."],
		});
	});

	it("says a running timer counts once it stops, even before anything is billable", () => {
		const october = month([client({ name: "Studio Kite", running: true })], []);
		expect(describeMonth(october, { current: true })).toEqual({
			headline: "Nothing billable so far in October.",
			notes: ["A timer is running for Studio Kite; it counts once stopped."],
		});
	});

	describe("billing budgets", () => {
		const NOW = new Date(2026, 9, 18, 12, 0).getTime();
		const october = month(
			[client({ billableHours: 41.5, amountMinor: 352750 })],
			[total({ billableHours: 41.5, amountMinor: 352750 })],
		);
		const plain = describeMonth(october, { current: true });

		function budget(overrides: Partial<BillingBudgetStatus>): BillingBudgetStatus {
			return {
				scope: "client",
				scopeId: "c1",
				clientId: "c1",
				name: "Studio Kite",
				active: true,
				currency: "EUR",
				minorUnits: 2,
				unit: "hours",
				period: "monthly",
				limitHours: 40,
				warnAtPercent: 80,
				upcoming: false,
				first: "2026-10-01",
				last: "2026-10-31",
				through: "2026-10-18",
				billableHours: 18,
				unpricedHours: 0,
				amountMinor: 153000,
				remainingHours: 22,
				percentUsed: 45,
				state: "under",
				...overrides,
			};
		}

		const near = budget({
			billableHours: 35.5,
			remainingHours: 4.5,
			percentUsed: 88,
			state: "near",
		});
		const over = budget({
			scope: "project",
			scopeId: "p1",
			name: "Website",
			billableHours: 42,
			remainingHours: -2,
			percentUsed: 105,
			state: "used_up",
		});

		it("notes each budget near or used up, after the month's own notes", () => {
			expect(
				describeMonth(october, { current: true, budgets: [near, budget({}), over], now: NOW }),
			).toEqual({
				headline: plain.headline,
				notes: [
					"Studio Kite's budget for October is 88% used: 4.5 h left.",
					"Website's budget is used up: 2 h over.",
				],
			});
		});

		it("notes no budget of an archived scope", () => {
			expect(
				describeMonth(october, {
					current: true,
					budgets: [
						{ ...near, active: false },
						{ ...over, active: false },
					],
					now: NOW,
				}),
			).toEqual(plain);
		});

		it("notes no budget in a month already over, and none without budgets", () => {
			expect(
				describeMonth(month(october.clients, october.totals, "2026-09"), {
					current: false,
					budgets: [near, over],
					now: NOW,
				}).notes,
			).toEqual([]);
			expect(describeMonth(october, { current: true, budgets: [], now: NOW })).toEqual(plain);
			expect(plain).toEqual({
				headline: "€3,527.50 billable so far in October, across 1 client.",
				notes: [],
			});
		});
	});
});
