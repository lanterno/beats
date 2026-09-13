/**
 * The dates as the page writes them beside the entity's own wording
 * ("Mon Aug 3, 2026", "Aug 31 – Sep 6"): a short day ("Thu Sep 10"), a long
 * one with the year, and a clock time. Every input is a bare 'YYYY-MM-DD'
 * read as the local calendar day it names, or a UTC timestamp shown in the
 * browser's zone.
 */

import { addIsoDays, formatDateShort, getDayName, parseIsoDate, parseUtcIso } from "@/shared/lib";

function day(iso: string): Date {
	return parseIsoDate(iso) ?? new Date(0);
}

/** "Thu Sep 10". */
export function shortDate(iso: string): string {
	const d = day(iso);
	return `${getDayName(d, "short")} ${formatDateShort(d)}`;
}

/** "Mon Aug 3, 2026". */
export function longDate(iso: string): string {
	const d = day(iso);
	return `${getDayName(d, "short")} ${formatDateShort(d)}, ${d.getFullYear()}`;
}

/** "Aug 31, 2026" — the day without its weekday, for a chip. */
export function plainDate(iso: string): string {
	const d = day(iso);
	return `${formatDateShort(d)}, ${d.getFullYear()}`;
}

/** Monday to Friday. */
export function isWeekdayIso(iso: string): boolean {
	const dow = day(iso).getDay();
	return dow >= 1 && dow <= 5;
}

/** The first Monday-to-Friday day after `iso`. */
export function nextWeekdayAfter(iso: string): string {
	let next = addIsoDays(iso, 1);
	while (!isWeekdayIso(next)) next = addIsoDays(next, 1);
	return next;
}

/** "13:10" — a timestamp as the local clock, 24 h, as the mockup writes session times. */
export function clock(timestamp: string): string {
	const d = parseUtcIso(timestamp);
	if (Number.isNaN(d.getTime())) return "—";
	return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

/** "3h 05m" — minutes as the session rows show them. */
export function hoursMinutes(minutes: number): string {
	const whole = Math.max(0, Math.round(minutes));
	const h = Math.floor(whole / 60);
	const m = whole % 60;
	return `${h}h ${String(m).padStart(2, "0")}m`;
}

/** "7.1" — hours to the decimal the day rows show. */
export function hours1(hours: number): string {
	return hours.toFixed(1);
}

/** "1,284 h" — a total with its thousands separated; "2.5 h" while it is still small. */
export function hoursTotal(hours: number): string {
	if (hours < 100) return `${hours.toFixed(1)} h`;
	return `${Math.round(hours).toLocaleString("en-US")} h`;
}
