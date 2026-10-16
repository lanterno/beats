/**
 * The Time off tally's words for a year of the vacation entitlement, one
 * example per branch. The figures are the API's; what is ours is which line
 * says what, and that a negative figure is said by its size with the sign
 * in words — `halfDays` alone would print −2.5 as "−3½".
 */
import { describe, expect, it } from "vitest";
import type { VacationEntitlement, VacationYear } from "./types";
import { describeVacationYear } from "./vacation";

const ENTITLEMENT: VacationEntitlement = {
	daysPerYear: 25,
	carryOver: "all",
	openingOn: "2026-10-01",
	openingDays: 12,
};

function year(fields: Partial<VacationYear>): VacationYear {
	return {
		year: 2027,
		accrued: 25,
		carriedIn: 0,
		available: 25,
		booked: 0,
		remaining: 25,
		...fields,
	};
}

describe("describeVacationYear", () => {
	it("says the opening in the opening year", () => {
		const words = describeVacationYear(
			year({ year: 2026, accrued: null, available: 12, booked: 8, remaining: 4 }),
			ENTITLEMENT,
			undefined,
		);
		expect(words).toEqual({
			headline: "8 of 12 d vacation · 4 left",
			detail: "12 d left on Oct 1",
		});
	});

	it("says what the year gives and what the year before carried in", () => {
		const words = describeVacationYear(
			year({ carriedIn: 2.5, available: 27.5, booked: 8, remaining: 19.5 }),
			ENTITLEMENT,
			undefined,
		);
		expect(words).toEqual({
			headline: "8 of 27½ d vacation · 19½ left",
			detail: "25 d for 2027 · 2½ d carried from 2026",
		});
	});

	it("says how far the year runs in the year the job ends, and nothing carried when none was", () => {
		const words = describeVacationYear(
			year({ accrued: 12.5, available: 12.5, remaining: 12.5 }),
			ENTITLEMENT,
			"2027-06-30",
		);
		expect(words.detail).toBe("12½ d for 2027 through Jun 30");
	});

	it("says an overdrawn year is over, by how much", () => {
		const words = describeVacationYear(
			year({ booked: 26.5, remaining: -1.5 }),
			ENTITLEMENT,
			undefined,
		);
		expect(words.headline).toBe("26½ of 25 d vacation · 1½ d over");
	});

	it("says a deficit carried in as overdrawn, not as a negative carry", () => {
		const words = describeVacationYear(
			year({ year: 2026, carriedIn: -2.5, available: 22.5, remaining: 22.5 }),
			{ ...ENTITLEMENT, openingOn: "2025-03-02" },
			undefined,
		);
		expect(words.detail).toBe("25 d for 2026 · 2½ d overdrawn in 2025");
	});

	it("says a negative opening as overdrawn, and a year that starts below zero without an 'of'", () => {
		const words = describeVacationYear(
			year({ year: 2026, accrued: null, available: -1.5, remaining: -1.5 }),
			{ ...ENTITLEMENT, openingOn: "2026-03-02", openingDays: -1.5 },
			undefined,
		);
		expect(words).toEqual({
			headline: "0 d vacation · 1½ d over",
			detail: "1½ d overdrawn on Mar 2",
		});
	});
});
