import { describe, expect, it } from "vitest";
import { daysBetween, deadlineOf } from "./deadline";

describe("deadlineOf", () => {
	it("is the same day of the next month", () => {
		expect(deadlineOf("2026-11-01")).toBe("2026-12-01");
		expect(deadlineOf("2026-12-15")).toBe("2027-01-15");
		expect(deadlineOf("2026-12-31")).toBe("2027-01-31");
	});

	it("is the next month's last day when it has no such day", () => {
		// Thirty days would put these on 2 March and 1 March, past the law's month.
		expect(deadlineOf("2027-01-31")).toBe("2027-02-28");
		expect(deadlineOf("2028-01-31")).toBe("2028-02-29");
		expect(deadlineOf("2026-03-31")).toBe("2026-04-30");
	});
});

describe("daysBetween", () => {
	it("counts whole days, across a month end", () => {
		expect(daysBetween("2026-11-01", "2026-11-01")).toBe(0);
		expect(daysBetween("2027-01-31", "2027-02-28")).toBe(28);
	});
});
