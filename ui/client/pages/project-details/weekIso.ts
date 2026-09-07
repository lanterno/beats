/**
 * Local-Monday date math for the per-week columns.
 *
 * Noon-anchored on purpose: setting the date from midnight can land on the
 * wrong day when a DST transition moves the clock across the boundary, and the
 * result is fed straight into API queries keyed by week.
 */

/** Local Monday (ISO YYYY-MM-DD) `weeksAgo` weeks back. */
export function getMondayIsoFor(weeksAgo: number, now: Date = new Date()): string {
	const d = new Date(now);
	d.setHours(12, 0, 0, 0);
	d.setDate(d.getDate() - ((d.getDay() + 6) % 7) - weeksAgo * 7);
	const yyyy = d.getFullYear();
	const mm = String(d.getMonth() + 1).padStart(2, "0");
	const dd = String(d.getDate()).padStart(2, "0");
	return `${yyyy}-${mm}-${dd}`;
}

/** The last `weekCount` Mondays, most recent first. */
export function computeMondayIsoList(weekCount: number, now: Date = new Date()): string[] {
	return Array.from({ length: weekCount }, (_, i) => getMondayIsoFor(i, now));
}
