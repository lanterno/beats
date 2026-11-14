/**
 * When an erasure request must be answered: one calendar month from the day
 * its mail arrived (GDPR Art. 12(3)), not thirty days. A period in months
 * ends on the same day of the next month, or on that month's last day when
 * it has no such day (Regulation 1182/71, art. 3(2)(c)): mail received on
 * 31 January is due on 28 February, or on the 29th in a leap year.
 *
 * The API holds the other half (`ERASURE_REQUEST_ATTENTION_DAYS` in
 * api/src/beats/operator/reads.py): a request with nothing queued is on the
 * queue after 14 days, and an erasure runs 7 days after it is queued — 21,
 * inside the shortest month there is.
 */

/** The last day to answer a request received on `received`, both
 * YYYY-MM-DD. */
export function deadlineOf(received: string): string {
	const [year, month, day] = received.split("-").map(Number);
	// `month` is 1-based, so as a month index it is already the next month,
	// and day 0 of the month after that is the next month's last day.
	const last = new Date(Date.UTC(year, month + 1, 0)).getUTCDate();
	return new Date(Date.UTC(year, month, Math.min(day, last))).toISOString().slice(0, 10);
}

/** Whole days from one day to another, both YYYY-MM-DD. */
export function daysBetween(from: string, to: string): number {
	return Math.round((Date.parse(`${to}T00:00:00Z`) - Date.parse(`${from}T00:00:00Z`)) / 86_400_000);
}
