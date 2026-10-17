/**
 * Last year's company days, copied into the year the Holidays dialog shows
 * (docs/work-contracts.md, Decision 12). A company day is a dated day, never
 * a rule, because an employer's policy changes from year to year; the copy
 * is what keeps that from meaning Christmas Eve typed in again every
 * December. Each of last year's days moves to the same month and day, for
 * the user to check and save: nothing here writes.
 *
 * A copied day is left out where it would change nothing or could not be:
 * on a date that already has a company day, on a public holiday the
 * employer gives, and on 29 February into a year without one. That last is
 * left out rather than moved to the 28th or 1 March: a day given on a leap
 * day says nothing about which neighbour the employer would give instead,
 * and the note says so, so the user can add one by hand. A day that lands on
 * a weekend is copied — the dialog says on the row that it owes nothing
 * there — so a policy kept by date is kept whole.
 */

import { formatDateShort, parseIsoDate } from "@/shared/lib";
import type { CompanyHoliday } from "./types";

/** Why a day of last year's was not copied. */
export type CompanyDaySkip = "taken" | "public_holiday" | "no_such_day";

export interface CompanyDaysCopy {
	/** The new days, by date, in the target year. */
	copied: CompanyHoliday[];
	/** Last year's days left out, under their own (last year's) date. */
	skipped: (CompanyHoliday & { reason: CompanyDaySkip })[];
}

/** The days in `year` a list holds, by date; a row still without a date is none. */
function daysIn(days: readonly CompanyHoliday[], year: number): CompanyHoliday[] {
	return days
		.filter((d) => parseIsoDate(d.date) && d.date.startsWith(`${year}-`))
		.sort((a, b) => a.date.localeCompare(b.date));
}

/** Whether a list holds a company day in `year`: last year's, for the copy to offer. */
export function hasCompanyDaysIn(days: readonly CompanyHoliday[], year: number): boolean {
	return daysIn(days, year).length > 0;
}

/**
 * Last year's company days in `days` moved into `year`. `days` is every
 * company day the dialog holds, any year, saved or not: a date in `year`
 * among them is taken. `publicHolidays` is `year`'s public holidays the
 * employer gives, as far as they are known — empty while the calendar
 * loads, when the dialog's row note says what this could not.
 */
export function copyCompanyDays(
	days: readonly CompanyHoliday[],
	year: number,
	publicHolidays: ReadonlySet<string>,
): CompanyDaysCopy {
	const taken = new Set(daysIn(days, year).map((d) => d.date));
	const copy: CompanyDaysCopy = { copied: [], skipped: [] };
	for (const day of daysIn(days, year - 1)) {
		const date = `${year}${day.date.slice(4)}`;
		// parseIsoDate rolls a date that does not exist over: 29 February into the 1st of March.
		const reason: CompanyDaySkip | null =
			parseIsoDate(date)?.getDate() !== Number(date.slice(8))
				? "no_such_day"
				: taken.has(date)
					? "taken"
					: publicHolidays.has(date)
						? "public_holiday"
						: null;
		if (reason) {
			copy.skipped.push({ ...day, reason });
		} else {
			copy.copied.push({ date, name: day.name });
			taken.add(date);
		}
	}
	return copy;
}

/**
 * "Copied 2 days from 2025 — save to keep them. Left out: Dec 25, already a
 * public holiday · Feb 29, 2027 has none." — the dialog's line under the copy.
 */
export function describeCompanyDaysCopy(copy: CompanyDaysCopy, year: number): string {
	const n = copy.copied.length;
	const head =
		n > 0
			? `Copied ${n === 1 ? "1 day" : `${n} days`} from ${year - 1} — save to keep ${n === 1 ? "it" : "them"}.`
			: `Nothing copied from ${year - 1}.`;
	if (copy.skipped.length === 0) return head;
	const left = copy.skipped.map((d) => {
		const why =
			d.reason === "taken"
				? "already a company day"
				: d.reason === "public_holiday"
					? "already a public holiday"
					: `${year} has none`;
		return `${formatDateShort(parseIsoDate(d.date) ?? new Date(0))}, ${why}`;
	});
	return `${head} Left out: ${left.join(" · ")}.`;
}
