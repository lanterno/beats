/**
 * The control plane's few renderings: sizes and days, as an operator reads
 * them. Pure, and tested — the rest of this UI is tables over the API's own
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
