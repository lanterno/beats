/**
 * A report's dates are the API's 'YYYY-MM-DD' local days. Read as UTC
 * midnight they print the day before anywhere west of Greenwich, so this file
 * runs in Los Angeles (restored afterwards: a worker may run other files).
 */
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { betweenText, monthHeading, rangeText } from "./figures";

const zone = process.env.TZ;

beforeAll(() => {
	process.env.TZ = "America/Los_Angeles";
});

afterAll(() => {
	process.env.TZ = zone;
});

describe("a report's dates", () => {
	it("do not shift west of Greenwich", () => {
		// The zone took: a September noon there is seven hours behind UTC.
		expect(new Date(2026, 8, 1, 12).getTimezoneOffset()).toBe(420);
		expect(rangeText("2026-09-01", "2026-09-30")).toBe("1–30 September 2026");
		expect(monthHeading("2026-10")).toBe("October 2026");
	});

	it("name the year once inside one, and both across a new year", () => {
		expect(rangeText("2026-09-15", "2026-10-31")).toBe("15 September – 31 October 2026");
		expect(rangeText("2025-12-15", "2026-01-31")).toBe("15 December 2025 – 31 January 2026");
		expect(betweenText("2026-09-15", "2026-10-31")).toBe(
			"between 15 September and 31 October 2026",
		);
		expect(betweenText("2025-12-15", "2026-01-31")).toBe(
			"between 15 December 2025 and 31 January 2026",
		);
	});
});
