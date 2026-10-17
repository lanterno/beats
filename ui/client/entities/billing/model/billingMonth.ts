/**
 * The months the Clients page steps through, as 'YYYY-MM' — what `?month=`
 * holds and the API's `month` takes. The API answers 409 MONTH_NOT_STARTED
 * for a month after the current one, so the navigator stops at it; the
 * current month is month to date.
 */

/** The month 'YYYY-MM-DD' falls in. */
export function monthOf(isoDay: string): string {
	return isoDay.slice(0, 7);
}

function shift(month: string, by: 1 | -1): string {
	const year = Number(month.slice(0, 4));
	const index = Number(month.slice(5, 7)) - 1 + by; // 0-based, may leave 0..11
	const y = year + Math.floor(index / 12);
	const m = ((index % 12) + 12) % 12;
	return `${String(y).padStart(4, "0")}-${String(m + 1).padStart(2, "0")}`;
}

/** The month before 'YYYY-MM'. */
export function prevMonth(month: string): string {
	return shift(month, -1);
}

/** The month after 'YYYY-MM'. */
export function nextMonth(month: string): string {
	return shift(month, 1);
}

/** Whether 'YYYY-MM' comes after the month of `todayIso`: one the API has no figures for yet. */
export function isFutureMonth(month: string, todayIso: string): boolean {
	return month > monthOf(todayIso);
}
