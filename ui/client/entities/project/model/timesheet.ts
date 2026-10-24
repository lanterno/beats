/**
 * The monthly timesheet's months and its file's name (docs/work-contracts.md,
 * "The timesheet"). The figures are the API's, in the CSV it sends; this
 * only decides which months to offer and what to call the download.
 *
 * `timesheetMonths` mirrors the API's `timesheet_range`: a sheet covers the
 * finished days of a month inside the contract, from its first term through
 * `ended_on`, and the current month through yesterday. So the page never
 * offers a month the API answers 409 for, and a month cut short carries the
 * same last day in its label and its file's name as the API stops at.
 */

import { APP_NAME } from "@/shared/config";
import { addIsoDays, earlierIso, formatDateShort, parseIsoDate } from "@/shared/lib";
import { sortTerms } from "./contract";
import type { Contract } from "./types";

export interface TimesheetMonth {
	/** 'YYYY-MM', as the route takes it. */
	month: string;
	/** The sheet's last day, 'YYYY-MM-DD': the month's end, `endedOn` or yesterday, the earliest. */
	last: string;
	/** Whether the sheet stops before the month's end. */
	partial: boolean;
}

/** The last day of the month 'YYYY-MM', as 'YYYY-MM-DD'. */
function monthEnd(month: string): string {
	const year = Number(month.slice(0, 4));
	const index = Number(month.slice(5, 7));
	// Day 0 of the next month is this month's last; UTC keeps it off the clock.
	const days = new Date(Date.UTC(year, index, 0)).getUTCDate();
	return `${month}-${String(days).padStart(2, "0")}`;
}

/** The month after 'YYYY-MM'. */
function nextMonth(month: string): string {
	const year = Number(month.slice(0, 4));
	const index = Number(month.slice(5, 7));
	return index === 12
		? `${String(year + 1).padStart(4, "0")}-01`
		: `${month.slice(0, 5)}${String(index + 1).padStart(2, "0")}`;
}

/**
 * The months with a timesheet, newest first: from the month of the first
 * term through the month of yesterday or `endedOn`, whichever is earlier.
 * Empty while no day of the contract has finished — a contract starting
 * today or later.
 */
export function timesheetMonths(contract: Contract, todayIso: string): TimesheetMonth[] {
	const startsOn = sortTerms(contract.terms)[0]?.effectiveFrom;
	if (startsOn === undefined) return [];
	const yesterday = addIsoDays(todayIso, -1);
	const covered =
		contract.endedOn !== undefined && contract.endedOn < yesterday ? contract.endedOn : yesterday;
	if (covered < startsOn) return [];
	const months: TimesheetMonth[] = [];
	const lastMonth = covered.slice(0, 7);
	for (let month = startsOn.slice(0, 7); month <= lastMonth; month = nextMonth(month)) {
		const end = monthEnd(month);
		const last = earlierIso(covered, end);
		months.push({ month, last, partial: last < end });
	}
	return months.reverse();
}

/** "September 2026", or "October 2026 (through Oct 15)" for a month cut short. */
export function timesheetMonthLabel({ month, last, partial }: TimesheetMonth): string {
	const name = (parseIsoDate(`${month}-01`) ?? new Date(0)).toLocaleDateString("en-US", {
		month: "long",
		year: "numeric",
	});
	return partial ? `${name} (through ${formatDateShort(parseIsoDate(last) ?? new Date(0))})` : name;
}

/** "Acme AG" → "acme-ag"; a name with nothing to keep reads "project". */
function slug(name: string): string {
	const kept = name
		.toLowerCase()
		.replace(/[^\p{L}\p{N}]+/gu, "-")
		.replace(/^-+|-+$/g, "");
	return kept || "project";
}

/**
 * "LifePete-timesheet-acme-ag-2026-09.csv", and "…-2026-10-through-15.csv"
 * for a month cut short: a re-download of a finished month keeps one name,
 * and one that will still grow says where it stopped.
 */
export function timesheetFilename(projectName: string, sheet: TimesheetMonth): string {
	const through = sheet.partial ? `-through-${sheet.last.slice(8, 10)}` : "";
	return `${APP_NAME}-timesheet-${slug(projectName)}-${sheet.month}${through}.csv`;
}
