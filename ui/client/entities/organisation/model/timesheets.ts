/**
 * The words and arithmetic every timesheet reader shares: the organisation
 * page's two sections and the project page's Organisation panel all say a
 * month, a status and the frozen figures the same way. They lived in
 * `TimesheetsSection` and were imported by its siblings, which made one
 * page's section another page's library.
 */

import { hoursText } from "@/shared/lib";
import type { ChipTone } from "@/shared/ui";
import type { Timesheet, TimesheetStatus } from "./types";

export const TIMESHEET_STATUS_LABELS: Record<TimesheetStatus, string> = {
	submitted: "Submitted",
	approved: "Approved",
	changes_requested: "Changes requested",
	reopened: "Reopened",
};

/**
 * A status as a chip's tone, beside its word: submitted waits on a decider
 * (the accent wash), approved settled well, and a month back with the
 * member — changes asked, or reopened — is simply waiting.
 */
export const TIMESHEET_STATUS_TONE: Record<TimesheetStatus, ChipTone> = {
	submitted: "warn",
	approved: "ok",
	changes_requested: "wait",
	reopened: "wait",
};

/**
 * The one sentence under an approved month whose contract has since changed
 * (decision 23): the figures above are as approved and the month is still
 * locked, so the reader is told what moved and what the way back is, and
 * nothing is recomputed beside the frozen figure — two numbers side by side
 * is the confusion the frozen month exists to avoid.
 */
export function supersededText(sheet: Timesheet): string | null {
	if (sheet.status !== "approved" || !sheet.supersededAt) return null;
	const day = new Date(sheet.supersededAt).toLocaleDateString("en-US", {
		month: "short",
		day: "numeric",
		year: "numeric",
	});
	const by = sheet.supersededByName ? ` by ${sheet.supersededByName}` : "";
	return `The contract changed on ${day}${by}, after this month was approved. The figures are as approved and the month stays locked; reopen it to approve against the current terms.`;
}

/** "September 2026" from a sheet month's "2026-09-01" (or "2026-09"). */
export function sheetMonthTitle(month: string): string {
	const date = new Date(Number(month.slice(0, 4)), Number(month.slice(5, 7)) - 1, 1, 12);
	return date.toLocaleDateString("en-US", { month: "long", year: "numeric" });
}

/** "42.5 h worked · 160 h expected · balance −12.3 h at the close". */
export function frozenText(frozen: NonNullable<Timesheet["frozen"]>): string {
	const parts = [`${hoursText(frozen.worked)} worked`];
	if (frozen.expected !== null) parts.push(`${hoursText(frozen.expected)} expected`);
	if (frozen.balanceEnd !== null) {
		const b = frozen.balanceEnd;
		const signed = b < 0 ? `−${hoursText(-b)}` : `+${hoursText(b)}`;
		parts.push(`balance ${signed} at the close`);
	}
	return parts.join(" · ");
}

/**
 * The last `n` months that ended before the day `todayIso` sits in, newest
 * first, as the sheet-month "YYYY-MM-01". Which day "today" is decides
 * whether a month has ended, and the API decides in the organisation's
 * timezone — so give this `organisationToday`, not the browser's clock.
 */
export function endedMonths(todayIso: string, n: number): string[] {
	const year = Number(todayIso.slice(0, 4));
	const month = Number(todayIso.slice(5, 7));
	return Array.from({ length: n }, (_, i) => {
		const d = new Date(year, month - 1 - (i + 1), 1, 12);
		return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-01`;
	});
}

/**
 * Today as "YYYY-MM-DD" in the organisation's timezone — the day the API
 * means when it says a month has ended (409 MONTH_NOT_ENDED). Around a
 * month's turn the browser's day and the organisation's can differ.
 */
export function organisationToday(timezone: string, now: Date = new Date()): string {
	try {
		// en-CA formats as YYYY-MM-DD.
		return now.toLocaleDateString("en-CA", { timeZone: timezone });
	} catch {
		return now.toLocaleDateString("en-CA");
	}
}
