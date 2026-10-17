/**
 * What a change of the holiday region does to the dates a contract marks as
 * not given (docs/work-contracts.md, Decision 12). The marks are bare dates,
 * so a mark that matched no holiday of the old region — left by an earlier
 * change, or kept with no region at all — did nothing; once the new region
 * has a holiday that day, it quietly makes that holiday a working day. The
 * settings form says so before saving, from the two regions' calendars.
 */

import type { Contract, RegionHoliday } from "./types";

/** The years the contract's marks fall in, ascending: the calendars a region change needs. */
export function notGivenYears(contract: Pick<Contract, "holidaysNotGiven">): number[] {
	const years = new Set(contract.holidaysNotGiven.map((date) => Number(date.slice(0, 4))));
	return [...years].sort((a, b) => a - b);
}

/**
 * The marks a region change would bring into force, by date, each with the
 * new region's holiday: a holiday in `after` on a date `before` had none.
 * A mark on a holiday of both regions already made it a working day, and a
 * mark on a holiday of neither still does nothing, so neither is listed; nor
 * is a date a company day covers, which stays a day off whatever the region.
 * `before` and `after` are by date (YYYY-MM-DD) and name; no region is an
 * empty calendar.
 */
export function revivedNotGiven(
	contract: Pick<Contract, "holidaysNotGiven" | "companyHolidays">,
	before: ReadonlyMap<string, string>,
	after: ReadonlyMap<string, string>,
): RegionHoliday[] {
	const company = new Set(contract.companyHolidays.map((day) => day.date));
	const revived: RegionHoliday[] = [];
	for (const date of new Set(contract.holidaysNotGiven)) {
		const name = after.get(date);
		if (name !== undefined && !before.has(date) && !company.has(date)) {
			revived.push({ date, name });
		}
	}
	return revived.sort((a, b) => a.date.localeCompare(b.date));
}
