import { describe, expect, it } from "vitest";
import { notGivenYears, revivedNotGiven } from "./regionChange";
import type { Contract } from "./types";

type Marks = Pick<Contract, "holidaysNotGiven" | "companyHolidays">;

// England and Scotland in 2026, as far as these tests need them.
const ENGLAND = new Map([
	["2026-04-06", "Easter Monday"],
	["2026-12-25", "Christmas Day"],
]);
const SCOTLAND = new Map([
	["2026-01-02", "New Year Holiday"],
	["2026-11-30", "Saint Andrew's Day"],
	["2026-12-25", "Christmas Day"],
]);

function marks(holidaysNotGiven: string[], companyDays: string[] = []): Marks {
	return {
		holidaysNotGiven,
		companyHolidays: companyDays.map((date) => ({ date, name: "Founders' Day" })),
	};
}

describe("revivedNotGiven", () => {
	it("lists a mark the new region has a holiday on and the old had none, by the new name", () => {
		expect(revivedNotGiven(marks(["2026-11-30"]), ENGLAND, SCOTLAND)).toEqual([
			{ date: "2026-11-30", name: "Saint Andrew's Day" },
		]);
	});

	it("leaves out a mark on a holiday of both regions: it was a working day already", () => {
		expect(revivedNotGiven(marks(["2026-12-25"]), ENGLAND, SCOTLAND)).toEqual([]);
	});

	it("leaves out a mark the new region has no holiday on, whatever the old had", () => {
		// Easter Monday leaves with England, 4 March was never a holiday:
		// either way the mark does nothing in Scotland.
		expect(revivedNotGiven(marks(["2026-04-06", "2026-03-04"]), ENGLAND, SCOTLAND)).toEqual([]);
	});

	it("leaves out a date a company day covers, which stays a day off", () => {
		expect(revivedNotGiven(marks(["2026-11-30"], ["2026-11-30"]), ENGLAND, SCOTLAND)).toEqual([]);
	});

	it("brings every mark on a new holiday into force when there was no region", () => {
		const found = revivedNotGiven(marks(["2026-12-25", "2026-01-02"]), new Map(), SCOTLAND);
		expect(found.map((h) => h.date)).toEqual(["2026-01-02", "2026-12-25"]);
	});

	it("lists a date stored twice once", () => {
		expect(revivedNotGiven(marks(["2026-11-30", "2026-11-30"]), ENGLAND, SCOTLAND)).toHaveLength(1);
	});
});

describe("notGivenYears", () => {
	it("names each year a mark falls in once, ascending", () => {
		expect(notGivenYears(marks(["2027-01-01", "2025-12-26", "2027-04-02"]))).toEqual([2025, 2027]);
	});
});
