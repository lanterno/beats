/**
 * The dates as the project page writes them: "Mon Aug 3, 2026", "Aug 31 –
 * Sep 6", "W36". Every input is a bare 'YYYY-MM-DD' read as the local
 * calendar day it names, never a timestamp. Internal to the model; the
 * standing and the ledger both speak this way.
 */

import { addIsoDays, formatDateShort, getDayName, getISOWeek, parseIsoDate } from "@/shared/lib";

function day(iso: string): Date {
	// A malformed date falls to the epoch rather than throwing mid-render.
	return parseIsoDate(iso) ?? new Date(0);
}

/** "Mon". */
export function weekdayShort(iso: string): string {
	return getDayName(day(iso), "short");
}

/** "Monday". */
export function weekdayLong(iso: string): string {
	return getDayName(day(iso), "long");
}

/** Monday to Friday. */
export function isWeekday(iso: string): boolean {
	const dow = day(iso).getDay();
	return dow >= 1 && dow <= 5;
}

/** "Mon Aug 3, 2026" — the weekday is always there, so a mid-week date says which. */
export function longDate(iso: string): string {
	const d = day(iso);
	return `${getDayName(d, "short")} ${formatDateShort(d)}, ${d.getFullYear()}`;
}

/** "Tue Aug 18". */
export function formatShortDate(iso: string): string {
	const d = day(iso);
	return `${getDayName(d, "short")} ${formatDateShort(d)}`;
}

/** The ISO week number, 1–53. */
export function isoWeek(weekOf: string): number {
	return getISOWeek(day(weekOf));
}

/** "W36". */
export function weekNumber(weekOf: string): string {
	return `W${isoWeek(weekOf)}`;
}

/** The week's Sunday. */
export function sundayOf(weekOf: string): string {
	return addIsoDays(weekOf, 6);
}

/**
 * "Sep 7 – 13" inside one month, "Aug 31 – Sep 6" across two, and the years
 * named when they differ: "Dec 29, 2025 – Jan 4, 2026".
 */
export function dateRange(startIso: string, endIso: string): string {
	const start = day(startIso);
	const end = day(endIso);
	if (start.getFullYear() !== end.getFullYear()) {
		return `${formatDateShort(start)}, ${start.getFullYear()} – ${formatDateShort(end)}, ${end.getFullYear()}`;
	}
	if (start.getMonth() === end.getMonth()) {
		return `${formatDateShort(start)} – ${end.getDate()}`;
	}
	return `${formatDateShort(start)} – ${formatDateShort(end)}`;
}

/** The week's Monday to Sunday: "Aug 31 – Sep 6". */
export function weekRange(weekOf: string): string {
	return dateRange(weekOf, sundayOf(weekOf));
}

/** Hours at the decimal the page shows them: "6.7 h", "42.0 h". */
export function hours1(hours: number): string {
	return `${hours.toFixed(1)} h`;
}

/** "Thu and Fri", "Wed – Fri" for three or more in a row, "Mon, Wed and Fri" otherwise. */
export function nameDays(isoDates: string[], name: (iso: string) => string = weekdayShort): string {
	if (isoDates.length === 0) return "";
	if (isoDates.length === 1) return name(isoDates[0]);
	const consecutive = isoDates.every((iso, i) => i === 0 || addIsoDays(isoDates[i - 1], 1) === iso);
	if (consecutive && isoDates.length >= 3) {
		return `${name(isoDates[0])} – ${name(isoDates[isoDates.length - 1])}`;
	}
	const names = isoDates.map(name);
	return `${names.slice(0, -1).join(", ")} and ${names[names.length - 1]}`;
}
