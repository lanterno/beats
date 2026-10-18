/**
 * A billing budget in words, and its state against the clock. Every figure
 * is the API's, so these pin the copy for each state the API can send, and
 * the one rule worked out here: a running timer's instant, once passed,
 * lifts the state the page draws — from under to near, or to used up —
 * before the next read moves the figures. The instants are built from local
 * times, so "13:40" reads the same in whatever zone the tests run.
 */
import { describe, expect, it } from "vitest";
import { billingBudgetState, describeBillingBudget } from "./budget";
import type { BillingBudgetRunning, BillingBudgetStatus } from "./types";

/** An instant at a local time on Oct 18, 2026, as the API sends one (UTC ISO). */
const at = (hours: number, minutes: number) => new Date(2026, 9, 18, hours, minutes).toISOString();
const now = (hours: number, minutes: number) => new Date(2026, 9, 18, hours, minutes).getTime();

function hoursBudget(overrides: Partial<BillingBudgetStatus> = {}): BillingBudgetStatus {
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

function moneyBudget(overrides: Partial<BillingBudgetStatus> = {}): BillingBudgetStatus {
	return {
		scope: "project",
		scopeId: "p1",
		clientId: "c1",
		name: "Website",
		active: true,
		currency: "EUR",
		minorUnits: 2,
		unit: "money",
		period: "total",
		limitMinor: 1_020_000,
		startsOn: "2026-09-01",
		warnAtPercent: 80,
		upcoming: false,
		first: "2026-09-01",
		through: "2026-10-18",
		billableHours: 84,
		unpricedHours: 0,
		amountMinor: 684_250,
		remainingMinor: 335_750,
		percentUsed: 67,
		state: "under",
		...overrides,
	};
}

function running(overrides: Partial<BillingBudgetRunning> = {}): BillingBudgetRunning {
	return { projectId: "p1", since: at(9, 10), priced: true, ...overrides };
}

const NOON = now(12, 0);

describe("describeBillingBudget", () => {
	it("says what is spent and left this month, with no note while under", () => {
		expect(describeBillingBudget(hoursBudget(), NOON)).toEqual({
			sentence: "18 h of 40 h this month · 22 h left.",
		});
	});

	it("adds the projection when the API makes one, and a note once near", () => {
		const near = hoursBudget({
			billableHours: 34,
			remainingHours: 6,
			percentUsed: 85,
			state: "near",
			runsOutOn: "2026-10-24",
		});
		expect(describeBillingBudget(near, NOON)).toEqual({
			sentence: "34 h of 40 h this month · 6 h left. At this pace it runs out around Oct 24.",
			note: "Studio Kite's budget for October is 85% used: 6 h left.",
		});
	});

	it("says used up at the limit, and how much over past it", () => {
		const usedUp = hoursBudget({
			billableHours: 40,
			remainingHours: 0,
			percentUsed: 100,
			state: "used_up",
		});
		expect(describeBillingBudget(usedUp, NOON)).toEqual({
			sentence: "40 h of 40 h this month: used up.",
			note: "Studio Kite's budget is used up.",
		});
		const over = hoursBudget({
			name: "Website",
			billableHours: 43.5,
			remainingHours: -3.5,
			percentUsed: 108,
			state: "used_up",
		});
		expect(describeBillingBudget(over, NOON)).toEqual({
			sentence: "43.5 h of 40 h this month: 3.5 h over.",
			note: "Website's budget is used up: 3.5 h over.",
		});
	});

	it("puts a total in money since its first day, and the hours no figure counts", () => {
		expect(describeBillingBudget(moneyBudget({ unpricedHours: 3.5 }), NOON)).toEqual({
			sentence: "€6,842.50 of €10,200.00 since Sep 1 · €3,357.50 left.",
			unpriced: "Plus 3.5 h with no rate yet.",
		});
		// An hours budget counts unpriced hours: they are hours.
		expect(describeBillingBudget(hoursBudget({ unpricedHours: 3.5 }), NOON).unpriced).toBe(
			undefined,
		);
		// A total from another year names it.
		expect(
			describeBillingBudget(moneyBudget({ startsOn: "2025-11-01", first: "2025-11-01" }), NOON)
				.sentence,
		).toBe("€6,842.50 of €10,200.00 since Nov 1, 2025 · €3,357.50 left.");
	});

	it("says when an upcoming total starts, and nothing else", () => {
		const upcoming = hoursBudget({
			period: "total",
			limitHours: 120,
			startsOn: "2026-11-01",
			first: "2026-11-01",
			last: undefined,
			through: undefined,
			upcoming: true,
			billableHours: 0,
			amountMinor: 0,
			remainingHours: 120,
			percentUsed: 0,
		});
		expect(describeBillingBudget(upcoming, NOON)).toEqual({
			sentence: "Starts Nov 1: 120 h in total.",
		});
	});

	it("says around when a running timer uses the rest, then that it did", () => {
		const status = hoursBudget({
			billableHours: 35.5,
			remainingHours: 4.5,
			percentUsed: 88,
			state: "near",
			running: running({ overAt: at(13, 40) }),
		});
		expect(describeBillingBudget(status, now(13, 5))).toMatchObject({
			sentence: "35.5 h of 40 h this month · 4.5 h left.",
			running: "A timer is running: it uses the last 4.5 h around 13:40.",
			note: "Studio Kite's budget runs out around 13:40 if the timer keeps going.",
		});
		// The figures are the API's, without the timer; the clock moves the rest.
		expect(describeBillingBudget(status, now(13, 41))).toMatchObject({
			sentence: "35.5 h of 40 h this month · 4.5 h left.",
			running: "The running timer used it up around 13:40.",
			note: "Studio Kite's budget was used up around 13:40 by the running timer.",
		});
	});

	it("says a timer on hours with no rate counts once a rate is set", () => {
		const status = moneyBudget({ running: running({ priced: false }) });
		expect(describeBillingBudget(status, NOON).running).toBe(
			"A timer is running on hours with no rate; they count once a rate is set.",
		);
	});

	it("says a timer counts once stopped when the API sent no instant", () => {
		// Two running timers, or a budget already used up: no crossing to show.
		const status = hoursBudget({ running: running() });
		expect(describeBillingBudget(status, NOON).running).toBe(
			"A timer is running; it counts once stopped.",
		);
	});
});

describe("billingBudgetState", () => {
	it("is the API's state without a running timer", () => {
		expect(billingBudgetState(hoursBudget(), NOON)).toBe("under");
		expect(billingBudgetState(hoursBudget({ state: "used_up" }), NOON)).toBe("used_up");
	});

	it("lifts under to near once the warning's instant passes, and to used up at the limit's", () => {
		const status = hoursBudget({ running: running({ nearAt: at(13, 0), overAt: at(15, 0) }) });
		expect(billingBudgetState(status, now(12, 59))).toBe("under");
		expect(billingBudgetState(status, now(13, 0))).toBe("near");
		expect(billingBudgetState(status, now(14, 59))).toBe("near");
		expect(billingBudgetState(status, now(15, 0))).toBe("used_up");
	});

	it("lifts near to used up once the limit's instant passes", () => {
		const status = hoursBudget({ state: "near", running: running({ overAt: at(13, 40) }) });
		expect(billingBudgetState(status, now(13, 39))).toBe("near");
		expect(billingBudgetState(status, now(13, 40))).toBe("used_up");
	});

	it("lifts nothing for a timer with no rate under a money budget", () => {
		// The API sends no instant for it: the hours are in no amount yet.
		const status = moneyBudget({ state: "near", running: running({ priced: false }) });
		expect(billingBudgetState(status, now(23, 59))).toBe("near");
	});
});
