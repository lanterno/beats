/**
 * The control plane's few renderings: sizes, days and counts, as an operator
 * reads them. Pure, and tested; the rest of this UI lays out the API's own
 * figures.
 */

const UNITS = ["B", "KB", "MB", "GB", "TB"] as const;

/** 0 → "0 B", 1536 → "1.5 KB", 10 GB → "10 GB": one decimal until the
 * number is wide enough to carry none. */
export function formatBytes(bytes: number): string {
	if (!Number.isFinite(bytes) || bytes < 0) return "—";
	let value = bytes;
	let unit = 0;
	while (value >= 1024 && unit < UNITS.length - 1) {
		value /= 1024;
		unit += 1;
	}
	const rounded = value >= 100 || unit === 0 ? Math.round(value).toString() : value.toFixed(1);
	return `${rounded.replace(/\.0$/, "")} ${UNITS[unit]}`;
}

/** An ISO instant or date as its UTC day, or "—" for nothing: the control
 * plane shows days, not times, wherever a day is all the job needs. */
export function dayOf(value: string | null | undefined): string {
	if (!value) return "—";
	return value.slice(0, 10);
}

/** An ISO instant as its UTC minute, "2026-11-08 19:31", or "—": for the
 * audits and the job queue, where the day is not enough. The API writes
 * every instant in UTC. */
export function minuteOf(value: unknown): string {
	if (typeof value !== "string" || !value) return "—";
	return value.slice(0, 16).replace("T", " ");
}

/** 1 → "1 owner", 3 → "3 owners". */
export function counted(n: number, one: string, many: string): string {
	return `${n} ${n === 1 ? one : many}`;
}

/** 412330 → "412,330". */
export function whole(n: number): string {
	return n.toLocaleString("en-US");
}

/** 1.2 → "$1.20". */
export function dollars(amount: number): string {
	return `$${amount.toFixed(2)}`;
}

/**
 * Every day of the last `count` up to `today`, oldest first. The API sends
 * only the days something happened on, and a chart that closed those gaps
 * would draw a quiet month as a busy week.
 */
export function everyDay(
	rows: ReadonlyArray<{ day: string; value: number }>,
	count: number,
	today: Date,
): Array<{ day: string; value: number }> {
	const byDay = new Map(rows.map((row) => [row.day.slice(0, 10), row.value]));
	return Array.from({ length: count }, (_, i) => {
		const day = new Date(
			Date.UTC(today.getUTCFullYear(), today.getUTCMonth(), today.getUTCDate() - (count - 1 - i)),
		)
			.toISOString()
			.slice(0, 10);
		return { day, value: byDay.get(day) ?? 0 };
	});
}
