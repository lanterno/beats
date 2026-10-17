/**
 * Which months the Contract panel offers a timesheet for, and what the file
 * is called. `timesheetMonths` is the API's `timesheet_range` a second time,
 * so the cases on the contract of `api/src/beats/test_timesheet.py` — from
 * Wednesday 14 January 2026, read on Thursday 16 April — are repeated here
 * as a parity check: a month the page offers is one the API has a sheet for,
 * cut short on the same day.
 */
import { describe, expect, it } from "vitest";
import { APP_NAME } from "@/shared/config";
import { timesheetFilename, timesheetMonthLabel, timesheetMonths } from "./timesheet";
import type { Contract } from "./types";

const TODAY = "2026-04-16";

function contract(startsOn: string, endedOn?: string): Contract {
	return {
		terms: [
			{ effectiveFrom: startsOn, scheduleType: "full_time", fullTimeHours: 40, percentage: 1 },
		],
		openingBalanceHours: 0,
		endedOn,
		companyHolidays: [],
		holidaysNotGiven: [],
	};
}

const months = (c: Contract, today = TODAY) => timesheetMonths(c, today).map((m) => m.month);

describe("timesheetMonths", () => {
	it("lists every month from the first term's through the current one, newest first", () => {
		expect(months(contract("2026-01-14"))).toEqual(["2026-04", "2026-03", "2026-02", "2026-01"]);
	});

	it("runs a month that started mid-contract to its end, and the current one through yesterday", () => {
		const [april, march, , january] = timesheetMonths(contract("2026-01-14"), TODAY);
		expect(april).toEqual({ month: "2026-04", last: "2026-04-15", partial: true });
		expect(march).toEqual({ month: "2026-03", last: "2026-03-31", partial: false });
		// January starts on the 14th but ends on the 31st: not cut short.
		expect(january).toEqual({ month: "2026-01", last: "2026-01-31", partial: false });
	});

	it("stops at ended_on, cutting that month short", () => {
		const offered = timesheetMonths(contract("2026-01-14", "2026-03-18"), TODAY);
		expect(offered.map((m) => m.month)).toEqual(["2026-03", "2026-02", "2026-01"]);
		expect(offered[0]).toEqual({ month: "2026-03", last: "2026-03-18", partial: true });
	});

	it("does not offer the current month on its 1st", () => {
		expect(months(contract("2026-01-14"), "2026-04-01")).toEqual(["2026-03", "2026-02", "2026-01"]);
	});

	it("offers nothing until a day of the contract has finished", () => {
		expect(months(contract("2026-04-16"))).toEqual([]);
		expect(months(contract("2026-05-04"))).toEqual([]);
		expect(timesheetMonths(contract("2026-04-15"), TODAY)).toEqual([
			{ month: "2026-04", last: "2026-04-15", partial: true },
		]);
	});

	it("crosses a year boundary", () => {
		expect(months(contract("2025-12-15"), "2026-01-10")).toEqual(["2026-01", "2025-12"]);
	});

	it("ends a leap February on the 29th", () => {
		const february = timesheetMonths(contract("2028-01-03"), "2028-06-01").find(
			(m) => m.month === "2028-02",
		);
		expect(february).toEqual({ month: "2028-02", last: "2028-02-29", partial: false });
	});
});

describe("timesheetMonthLabel", () => {
	it("names the month, and where a month cut short stops", () => {
		expect(timesheetMonthLabel({ month: "2026-09", last: "2026-09-30", partial: false })).toBe(
			"September 2026",
		);
		expect(timesheetMonthLabel({ month: "2026-10", last: "2026-10-15", partial: true })).toBe(
			"October 2026 (through Oct 15)",
		);
	});
});

describe("timesheetFilename", () => {
	it("names a finished month by the project and the month", () => {
		expect(
			timesheetFilename("Acme AG", { month: "2026-09", last: "2026-09-30", partial: false }),
		).toBe(`${APP_NAME}-timesheet-acme-ag-2026-09.csv`);
	});

	it("says where a month cut short stops", () => {
		expect(
			timesheetFilename("Acme AG", { month: "2026-10", last: "2026-10-05", partial: true }),
		).toBe(`${APP_NAME}-timesheet-acme-ag-2026-10-through-05.csv`);
	});

	it("keeps letters beyond ASCII, and names a project with none 'project'", () => {
		const sheet = { month: "2026-09", last: "2026-09-30", partial: false };
		expect(timesheetFilename("Zürich — Büro", sheet)).toBe(
			`${APP_NAME}-timesheet-zürich-büro-2026-09.csv`,
		);
		expect(timesheetFilename("!!!", sheet)).toBe(`${APP_NAME}-timesheet-project-2026-09.csv`);
	});
});
