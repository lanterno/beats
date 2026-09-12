import { describe, expect, it } from "vitest";
import {
	contractFieldErrors,
	contractFromForm,
	termFormDefaults,
	termFromForm,
	validateTerm,
} from "./contractForm";

describe("term form ↔ domain", () => {
	it("sends a percentage as a fraction and a full-time term at 100%", () => {
		expect(
			termFromForm({
				effectiveFrom: "2026-04-01",
				scheduleType: "part_time",
				fullTimeHours: "42",
				percentage: "80",
				weeklyHours: "",
				note: " went to 80% ",
			}),
		).toEqual({
			effectiveFrom: "2026-04-01",
			scheduleType: "part_time",
			fullTimeHours: 42,
			percentage: 0.8,
			note: "went to 80%",
		});
		expect(
			termFromForm({
				effectiveFrom: "2026-04-01",
				scheduleType: "full_time",
				fullTimeHours: "40",
				percentage: "",
				weeklyHours: "",
				note: "",
			}),
		).toEqual({
			effectiveFrom: "2026-04-01",
			scheduleType: "full_time",
			fullTimeHours: 40,
			percentage: 1,
		});
	});

	it("leaves the numbers a schedule type does not use out of the term", () => {
		// A custom term typed after switching from part time still holds the
		// old percentage in its input; it must not reach the wire.
		const term = termFromForm({
			effectiveFrom: "2026-04-01",
			scheduleType: "custom",
			fullTimeHours: "42",
			percentage: "80",
			weeklyHours: "32",
			note: "",
		});
		expect(term).toEqual({ effectiveFrom: "2026-04-01", scheduleType: "custom", weeklyHours: 32 });
		expect(
			termFromForm({ ...termFormDefaults(), scheduleType: "objective", fullTimeHours: "42" }),
		).not.toHaveProperty("fullTimeHours");
	});

	it("shows a stored fraction back as a percent", () => {
		expect(
			termFormDefaults({
				effectiveFrom: "2026-04-01",
				scheduleType: "part_time",
				fullTimeHours: 42,
				percentage: 0.8,
			}).percentage,
		).toBe("80");
	});

	it("keeps the terms it is handed, sorted, and drops a blank region", () => {
		const contract = contractFromForm(
			{ holidayCountry: "", holidaySubdivision: "ZH", openingBalanceHours: "", endedOn: "" },
			[
				{ effectiveFrom: "2026-04-01", scheduleType: "objective" },
				{ effectiveFrom: "2026-01-05", scheduleType: "objective" },
			],
		);
		expect(contract.terms.map((t) => t.effectiveFrom)).toEqual(["2026-01-05", "2026-04-01"]);
		expect(contract.openingBalanceHours).toBe(0);
		// A subdivision without a country is what the API rejects; it goes with it.
		expect(contract).not.toHaveProperty("holidayCountry");
		expect(contract).not.toHaveProperty("holidaySubdivision");
	});
});

describe("validateTerm", () => {
	it("judges the percentage as the wire will carry it, not as typed", () => {
		const partTime = (percentage: string) => ({
			...termFormDefaults(),
			scheduleType: "part_time" as const,
			fullTimeHours: "42",
			percentage,
		});
		// Rounded to four decimals these reach the API as 1 and 0, which it refuses.
		expect(validateTerm(partTime("99.999"))).toHaveProperty("percentage");
		expect(validateTerm(partTime("0.001"))).toHaveProperty("percentage");
		expect(validateTerm(partTime("99.99"))).toEqual({});
		expect(validateTerm(partTime("0.01"))).toEqual({});
	});
});

describe("contractFieldErrors", () => {
	it("pins a project route's 422 to the term on screen and the frame", () => {
		const sorted = contractFieldErrors(
			{
				"contract.terms.0.percentage": "must be in (0, 1]",
				"contract.terms.1.weekly_hours": "required",
				"contract.holiday_country": "unknown",
				"contract.terms": "out of order",
				name: "too long",
			},
			"contract",
			0,
		);
		expect(sorted.term).toEqual({ percentage: "must be in (0, 1]" });
		expect(sorted.frame).toEqual({ holidayCountry: "unknown" });
		// Another term's error and the list-level one have no input here.
		expect(sorted.general).toEqual(["required", "out of order"]);
	});

	it("reads PUT /contract's paths from the body root, an empty path included", () => {
		const sorted = contractFieldErrors(
			{ "terms.2.full_time_hours": "must be positive", "": "ended_on is before the first term" },
			"",
			2,
		);
		expect(sorted.term).toEqual({ fullTimeHours: "must be positive" });
		expect(sorted.general).toEqual(["ended_on is before the first term"]);
	});
});
