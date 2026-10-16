/**
 * The vacation entitlement in words (docs/work-contracts.md, Decision 14).
 * Pure and clock-free: every figure is the API's or the contract's, and
 * this only says them. Days are counted in halves (`halfDays`), which
 * formats a count, not a signed figure — so a negative one is said by its
 * size, with the sign in words ("overdrawn", "over"), never as "−3½".
 */

import { formatDateShort, parseIsoDate } from "@/shared/lib";
import { halfDays } from "./standing";
import type { VacationEntitlement, VacationYear } from "./types";

/** "Oct 1" — the year is the tally's own. */
function monthDay(iso: string): string {
	return formatDateShort(parseIsoDate(iso) ?? new Date(0));
}

/** "Vacation 25 d/yr · up to 5 d carry over" — the register's constant. */
export function describeEntitlement(vacation: VacationEntitlement): string {
	const rule =
		vacation.carryOver === "all"
			? "all carry over"
			: vacation.carryOver === "none"
				? "unused lapse"
				: `up to ${halfDays(vacation.carryOverMaxDays ?? 0)} d carry over`;
	return `Vacation ${halfDays(vacation.daysPerYear)} d/yr · ${rule}`;
}

export interface VacationYearWords {
	/** "8 of 23½ d vacation · 15½ left", or "· 1½ d over" when overdrawn. */
	headline: string;
	/**
	 * Where the year's figure came from: "12 d left on Oct 1" in the opening
	 * year, "25 d for 2027 · 2½ d carried from 2026" after it, "… through
	 * Jun 30" in the year the job ends, "… · 2½ d overdrawn in 2026" for a
	 * deficit carried in.
	 */
	detail: string;
}

/**
 * The Time off tally for one year of the entitlement. `endedOn` is the
 * contract's, for the end year's "through". Every figure is the API's;
 * the opening's are the contract's.
 */
export function describeVacationYear(
	year: VacationYear,
	vacation: VacationEntitlement,
	endedOn: string | undefined,
): VacationYearWords {
	const left =
		year.remaining >= 0
			? `${halfDays(year.remaining)} left`
			: `${halfDays(-year.remaining)} d over`;
	const headline =
		year.available >= 0
			? `${halfDays(year.booked)} of ${halfDays(year.available)} d vacation · ${left}`
			: `${halfDays(year.booked)} d vacation · ${left}`;

	if (year.accrued === null) {
		const opening = vacation.openingDays;
		const state = opening >= 0 ? "left" : "overdrawn";
		const detail = `${halfDays(Math.abs(opening))} d ${state} on ${monthDay(vacation.openingOn)}`;
		return { headline, detail };
	}
	const through = endedOn?.startsWith(`${year.year}-`) ? ` through ${monthDay(endedOn)}` : "";
	const parts = [`${halfDays(year.accrued)} d for ${year.year}${through}`];
	const before = year.year - 1;
	if (year.carriedIn > 0) parts.push(`${halfDays(year.carriedIn)} d carried from ${before}`);
	if (year.carriedIn < 0) parts.push(`${halfDays(-year.carriedIn)} d overdrawn in ${before}`);
	return { headline, detail: parts.join(" · ") };
}
