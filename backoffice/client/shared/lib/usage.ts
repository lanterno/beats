/**
 * The People and Hours pages' arithmetic and sentences, pure and tested:
 * every bucket of a span filled in (the API sends only the ones something
 * was logged in, and a chart that closed the gaps would draw a quiet quarter
 * as a busy week), the figures the page opens on, and how the rows sort.
 */

import type { AccountRow, HoursBucket, HoursUnit } from "@/shared/api/schema";

/** The spans a reader can pick per unit, in buckets; the first is the
 * page's default. Each is within the API's bound for the unit
 * (`HOURS_MAX_PERIODS`). */
export const SPANS: Record<HoursUnit, readonly number[]> = {
	day: [30, 90, 365],
	week: [12, 26, 52, 104],
	month: [6, 12, 24, 60],
};

export const UNITS: ReadonlyArray<{ id: HoursUnit; label: string; one: string; many: string }> = [
	{ id: "day", label: "By day", one: "day", many: "days" },
	{ id: "week", label: "By week", one: "week", many: "weeks" },
	{ id: "month", label: "By month", one: "month", many: "months" },
];

const isoDay = (y: number, m: number, d: number): string =>
	new Date(Date.UTC(y, m, d)).toISOString().slice(0, 10);

/** The first day of each of `periods` buckets from `since` (the API's own
 * first bucket), oldest first, so the two agree on where a bucket starts. */
export function bucketDays(since: string, unit: HoursUnit, periods: number): string[] {
	const [y, m, d] = since.split("-").map(Number);
	return Array.from({ length: periods }, (_, i) => {
		if (unit === "month") return isoDay(y, m - 1 + i, 1);
		return isoDay(y, m - 1, d + i * (unit === "week" ? 7 : 1));
	});
}

export interface Drawn {
	day: string;
	value: number;
	sessions: number;
	accounts: number;
}

/** Every bucket of the report's span, the quiet ones at nothing. */
export function everyBucket(
	buckets: ReadonlyArray<HoursBucket>,
	since: string,
	unit: HoursUnit,
	periods: number,
): Drawn[] {
	const by = new Map(buckets.map((b) => [b.period, b]));
	return bucketDays(since, unit, periods).map((day) => {
		const b = by.get(day);
		return { day, value: b?.hours ?? 0, sessions: b?.sessions ?? 0, accounts: b?.accounts ?? 0 };
	});
}

/** 1234.5 → "1,234.5 h"; 0.25 → "0.25 h". Two decimals at most, none
 * trailing. */
export function hoursOf(hours: number): string {
	const rounded = Math.round(hours * 100) / 100;
	return `${rounded.toLocaleString("en-US", { maximumFractionDigits: 2 })} h`;
}

/** The chart's sentence: what was logged over the span and when the most was. */
export function hoursSentence(drawn: Drawn[], unit: HoursUnit): string {
	const spec = UNITS.find((u) => u.id === unit) ?? UNITS[0];
	const span = `${drawn.length} ${drawn.length === 1 ? spec.one : spec.many}`;
	const total = drawn.reduce((sum, d) => sum + d.value, 0);
	if (total === 0) return `Nothing was logged in the last ${span}.`;
	const busiest = drawn.reduce((best, d) => (d.value > best.value ? d : best), drawn[0]);
	const from = unit === "day" ? "on" : "in the one starting";
	return `${hoursOf(total)} logged over the last ${span}. The busiest ${spec.one} was ${from} ${busiest.day}, with ${hoursOf(busiest.value)}.`;
}

/** The page's first sentence, off the totals. */
export function hoursHeadline(totalHours: number, accountsLast30d: number): string {
	if (totalHours === 0) return "No hours have been logged yet.";
	const who =
		accountsLast30d === 0
			? "nobody in the last 30 days"
			: `${accountsLast30d} ${accountsLast30d === 1 ? "person" : "people"} in the last 30 days`;
	return `${hoursOf(totalHours)} logged all told, by ${who}.`;
}

export type SortKey = "created" | "seen" | "projects" | "sessions";

const stamp = (value: string | null | undefined): number => (value ? Date.parse(value) : -1);

/** Rows by a column, largest or newest first; the API's order is newest
 * created first. Ties keep the API's order. */
export function sortRows(rows: ReadonlyArray<AccountRow>, key: SortKey): AccountRow[] {
	const by: Record<SortKey, (r: AccountRow) => number> = {
		created: (r) => stamp(r.created_at),
		seen: (r) => stamp(r.last_seen_on),
		projects: (r) => r.projects,
		sessions: (r) => r.sessions,
	};
	return rows
		.map((r, i) => ({ r, i }))
		.sort((a, b) => by[key](b.r) - by[key](a.r) || a.i - b.i)
		.map(({ r }) => r);
}

/** The People page's first sentence. */
export function peopleHeadline(total: number, seenLast30d: number): string {
	if (total === 0) return "Nobody has an account yet.";
	return `${total} ${total === 1 ? "person has" : "people have"} an account, and ${seenLast30d} ${seenLast30d === 1 ? "was" : "were"} here in the last 30 days.`;
}
