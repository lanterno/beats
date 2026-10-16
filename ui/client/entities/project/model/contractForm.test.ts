import { describe, expect, it } from "vitest";
import {
	type ContractFrameValues,
	contractFieldErrors,
	contractFrameDefaults,
	contractFromForm,
	termFormDefaults,
	termFromForm,
	validateContractFrame,
	validateTerm,
} from "./contractForm";
import type { ContractTerm } from "./types";

const TERMS: ContractTerm[] = [{ effectiveFrom: "2026-01-05", scheduleType: "objective" }];
const NO_HOLIDAY_CHANGES = { companyHolidays: [], holidaysNotGiven: [] };

/** A frame with nothing in it but `fields`. */
function frame(fields: Partial<ContractFrameValues> = {}): ContractFrameValues {
	return { ...contractFrameDefaults(), ...fields };
}

/** A frame with an entitlement typed in full; `fields` change it. */
function vacationFrame(fields: Partial<ContractFrameValues> = {}): ContractFrameValues {
	return frame({
		vacationDaysPerYear: "25",
		vacationCarryOver: "all",
		vacationOpeningOn: "2026-03-02",
		vacationOpeningDays: "12",
		...fields,
	});
}

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
			frame({ holidaySubdivision: "ZH" }),
			[
				{ effectiveFrom: "2026-04-01", scheduleType: "objective" },
				{ effectiveFrom: "2026-01-05", scheduleType: "objective" },
			],
			{ companyHolidays: [], holidaysNotGiven: [] },
		);
		expect(contract.terms.map((t) => t.effectiveFrom)).toEqual(["2026-01-05", "2026-04-01"]);
		expect(contract.openingBalanceHours).toBe(0);
		// A subdivision without a country is what the API rejects; it goes with it.
		expect(contract).not.toHaveProperty("holidayCountry");
		expect(contract).not.toHaveProperty("holidaySubdivision");
	});

	it("carries the holiday lists it keeps unchanged, the region cleared or not", () => {
		const kept = {
			companyHolidays: [{ date: "2026-12-24", name: "Christmas Eve" }],
			holidaysNotGiven: ["2026-12-26"],
		};
		const terms = [{ effectiveFrom: "2026-01-05", scheduleType: "objective" as const }];
		for (const holidayCountry of ["CH", ""]) {
			const contract = contractFromForm(frame({ holidayCountry }), terms, kept);
			expect(contract.companyHolidays).toEqual(kept.companyHolidays);
			expect(contract.holidaysNotGiven).toEqual(kept.holidaysNotGiven);
		}
	});
});

describe("the vacation entitlement, form ↔ domain", () => {
	it.each([
		["all", "", { carryOver: "all" }],
		["capped", "5.5", { carryOver: "capped", carryOverMaxDays: 5.5 }],
		["none", "", { carryOver: "none" }],
	] as const)("carries a %s carry-over to the contract and back", (mode, max, rule) => {
		const typed = vacationFrame({ vacationCarryOver: mode, vacationCarryOverMax: max });

		const contract = contractFromForm(typed, TERMS, NO_HOLIDAY_CHANGES);

		expect(contract.vacation).toEqual({
			daysPerYear: 25,
			openingOn: "2026-03-02",
			openingDays: 12,
			...rule,
		});
		expect(contractFrameDefaults(contract)).toEqual(typed);
	});

	it("leaves the entitlement out when days per year are empty, whatever else is typed", () => {
		const contract = contractFromForm(
			vacationFrame({ vacationDaysPerYear: " " }),
			TERMS,
			NO_HOLIDAY_CHANGES,
		);
		expect(contract).not.toHaveProperty("vacation");
		expect(validateContractFrame(vacationFrame({ vacationDaysPerYear: "" }), "2026-01-05")).toEqual(
			{},
		);
	});

	it("asks for everything an entitlement needs, in halves", () => {
		expect(
			validateContractFrame(
				frame({ vacationDaysPerYear: "25.3", vacationOpeningDays: "-1.5" }),
				"2026-01-05",
			),
		).toEqual({
			vacationDaysPerYear: "Enter the days per year, in whole or half days",
			vacationCarryOver: "Choose what happens to unused days",
			vacationOpeningOn: "Enter the day counting starts",
		});
		expect(
			validateContractFrame(vacationFrame({ vacationCarryOver: "capped" }), "2026-01-05"),
		).toEqual({
			vacationCarryOverMax: "Enter how many days carry over, in whole or half days",
		});
		expect(
			validateContractFrame(vacationFrame({ vacationOpeningDays: "" }), "2026-01-05"),
		).toHaveProperty("vacationOpeningDays");
	});

	it("keeps the opening inside the contract's dates", () => {
		expect(validateContractFrame(vacationFrame(), "2026-03-03")).toEqual({
			vacationOpeningOn: "Counting cannot start before the contract does",
		});
		expect(validateContractFrame(vacationFrame({ endedOn: "2026-03-01" }), "2026-01-05")).toEqual({
			vacationOpeningOn: "Counting cannot start after the contract ends",
		});
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

	it("pins the entitlement's leaves to its inputs, and the entitlement as a whole to general", () => {
		const sorted = contractFieldErrors(
			{
				"contract.vacation.days_per_year": "must be a multiple of 0.5",
				"contract.vacation.carry_over_max_days": "say how many days carry over",
				"contract.vacation": "bad entitlement",
			},
			"contract",
			0,
		);
		expect(sorted.frame).toEqual({
			vacationDaysPerYear: "must be a multiple of 0.5",
			vacationCarryOverMax: "say how many days carry over",
		});
		expect(sorted.general).toEqual(["bad entitlement"]);
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
