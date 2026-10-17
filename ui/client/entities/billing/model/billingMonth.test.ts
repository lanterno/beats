/**
 * The Clients page's month navigator: 'YYYY-MM' strings, as `?month=` and
 * the API's `month` take them. The API answers 409 MONTH_NOT_STARTED for a
 * month after the current one, so the page never asks for one.
 */
import { describe, expect, it } from "vitest";
import { isFutureMonth, monthOf, nextMonth, prevMonth } from "./billingMonth";

const TODAY = "2026-10-17";

describe("month navigation", () => {
	it("names the month a day falls in", () => {
		expect(monthOf(TODAY)).toBe("2026-10");
		expect(monthOf("2026-01-01")).toBe("2026-01");
	});

	it("steps across a year boundary both ways", () => {
		expect(nextMonth("2026-12")).toBe("2027-01");
		expect(prevMonth("2027-01")).toBe("2026-12");
		expect(nextMonth("2026-09")).toBe("2026-10");
		expect(prevMonth("2026-10")).toBe("2026-09");
	});

	it("stops at the current month", () => {
		expect(isFutureMonth("2026-10", TODAY)).toBe(false);
		expect(isFutureMonth("2026-09", TODAY)).toBe(false);
		expect(isFutureMonth("2025-12", TODAY)).toBe(false);
		expect(isFutureMonth(nextMonth(monthOf(TODAY)), TODAY)).toBe(true);
		expect(isFutureMonth("2027-01", TODAY)).toBe(true);
	});
});
