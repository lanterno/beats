/**
 * A running timer that uses a budget up before the next read: the bar is
 * drawn full in the used-up ink while the API's percent is still the one
 * from before the timer, so the meter must say used up as well — a screen
 * reader hears the meter, not the colour.
 */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { BillingBudgetStatus } from "../model";
import { BillingBudgetRow } from "./BillingBudgetRow";

const NEAR: BillingBudgetStatus = {
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
	billableHours: 35.5,
	unpricedHours: 0,
	amountMinor: 301_750,
	remainingHours: 4.5,
	percentUsed: 88,
	state: "near",
	running: {
		projectId: "p1",
		since: "2026-10-18T07:10:00Z",
		priced: true,
		overAt: "2026-10-18T11:40:00Z",
	},
};

afterEach(cleanup);

describe("BillingBudgetRow", () => {
	it("reads the API's percent until the running timer uses the budget up", () => {
		render(<BillingBudgetRow status={NEAR} now={Date.parse("2026-10-18T11:00:00Z")} />);
		const meter = screen.getByRole("meter", { name: "Studio Kite's budget" });
		expect(meter).toHaveAttribute("aria-valuenow", "88");
		expect(meter).toHaveAttribute("aria-valuetext", "88% used");
	});

	it("says used up once the running timer's instant has passed", () => {
		render(<BillingBudgetRow status={NEAR} now={Date.parse("2026-10-18T12:00:00Z")} />);
		const meter = screen.getByRole("meter", { name: "Studio Kite's budget" });
		expect(meter).toHaveAttribute("aria-valuenow", "100");
		expect(meter).toHaveAttribute("aria-valuetext", "Used up by the running timer");
	});
});
