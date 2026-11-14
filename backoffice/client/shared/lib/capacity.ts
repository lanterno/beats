/**
 * Capacity's arithmetic, apart from the page so it can be tested. The API
 * sends the coach's cost a day and model for the last 31 days (UTC), each
 * collection's size as it stands, and the database's size a day as the job
 * runner kept it, with the pace it read off them. The pace itself is the
 * API's (`operator/growth.py`); what is here is how the page says and draws
 * it.
 */

import type { CapacityReport } from "@/shared/api/schema";
import { everyDay, formatBytes } from "./format";

/** A day and model's coach cost, as far as this arithmetic reads it. */
type CoachCost = ReadonlyArray<
	Pick<
		CapacityReport["coach_cost"][number],
		"day" | "model" | "cost_usd" | "input_tokens" | "cache_read_tokens" | "cache_saved_usd"
	>
>;
type Sizes = NonNullable<CapacityReport["sizes"]>;
type Growth = NonNullable<CapacityReport["growth"]>;
type Collection = CapacityReport["collections"][number];

const DAY_MS = 86_400_000;

/** The coach's cost a day, every day of the last `count` up to `today`, oldest first. */
export function dailyCost(
	rows: CoachCost,
	count: number,
	today: Date,
): Array<{ day: string; value: number }> {
	const byDay = new Map<string, number>();
	for (const row of rows) byDay.set(row.day, (byDay.get(row.day) ?? 0) + row.cost_usd);
	return everyDay(
		[...byDay].map(([day, value]) => ({ day, value })),
		count,
		today,
	);
}

/**
 * This UTC month so far: what it has cost, the running total a day for the
 * sparkline, and where the month is heading at the pace so far. No heading
 * before a whole day has passed: an hour's spend carried over a month says
 * nothing.
 */
export function coachMonth(
	rows: CoachCost,
	now: Date,
): { spent: number; running: number[]; heading: number | null } {
	const start = Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), 1);
	const end = Date.UTC(now.getUTCFullYear(), now.getUTCMonth() + 1, 1);
	const elapsed = now.getTime() - start;
	const daysSoFar = now.getUTCDate();
	let total = 0;
	const running = dailyCost(rows, daysSoFar, now).map((d) => {
		total += d.value;
		return total;
	});
	const heading = elapsed >= DAY_MS ? (total * (end - start)) / elapsed : null;
	return { spent: total, running, heading };
}

/**
 * The days shown, said in a sentence: how much of the input the cache
 * served, and which model most of the bill went to. `input_tokens` is the
 * uncached input; the cache's share is of both together.
 */
export function cacheSentence(rows: CoachCost, days: number, today: Date): string {
	const shown = new Set(everyDay([], days, today).map((d) => d.day));
	const within = rows.filter((row) => shown.has(row.day));
	const cost = within.reduce((sum, row) => sum + row.cost_usd, 0);
	if (within.length === 0 || cost === 0)
		return `The coach hasn't cost anything in these ${days} days.`;
	const cached = within.reduce((sum, row) => sum + row.cache_read_tokens, 0);
	const input = within.reduce((sum, row) => sum + row.input_tokens, 0) + cached;
	const byModel = new Map<string, number>();
	for (const row of within) byModel.set(row.model, (byModel.get(row.model) ?? 0) + row.cost_usd);
	const [model, share] = [...byModel].reduce((best, next) => (next[1] > best[1] ? next : best));
	const saved = within.reduce((sum, row) => sum + row.cache_saved_usd, 0);
	const cache =
		input > 0
			? `${Math.round((cached / input) * 100)}% of the input came from the cache${savingClause(cached, saved)}.`
			: "No input was counted.";
	const bill =
		byModel.size === 1
			? `It all went to ${model}.`
			: `${model} is ${Math.round((share / cost) * 100)}% of the bill.`;
	return `${cache} ${bill}`;
}

/** What the cache saved, as the end of the sentence that says its share. */
function savingClause(cached: number, saved: number): string {
	if (cached === 0) return "";
	if (saved >= 0.005) return `, which saved about ${dollars(saved)}`;
	if (saved <= -0.005) return `, and writing it cost ${dollars(-saved)} more than reading it saved`;
	return ", which saved next to nothing";
}

const dollars = (amount: number): string => `$${amount.toFixed(2)}`;

/** A sparkline's points in a `width` × `height` box, 1px in from the edges. */
export function sparkPoints(values: number[], width: number, height: number): string {
	if (values.length === 0) return "";
	const low = Math.min(...values);
	const span = Math.max(...values) - low || 1;
	const step = values.length > 1 ? (width - 2) / (values.length - 1) : 0;
	return values
		.map(
			(v, i) =>
				`${(1 + i * step).toFixed(1)},${(height - 1 - ((v - low) / span) * (height - 2)).toFixed(1)}`,
		)
		.join(" ");
}

// ── The database's size over time ───────────────────────────────────────

const LONG_DAY = new Intl.DateTimeFormat("en-GB", {
	day: "numeric",
	month: "long",
	timeZone: "UTC",
});

/** "2026-11-14" → "14 November". */
export function longDay(day: string): string {
	return LONG_DAY.format(new Date(`${day.slice(0, 10)}T00:00:00Z`));
}

const daysBetween = (from: string, to: string): number =>
	Math.round(
		(Date.parse(`${to.slice(0, 10)}T00:00:00Z`) - Date.parse(`${from.slice(0, 10)}T00:00:00Z`)) /
			DAY_MS,
	);

const nextDay = (day: string): string =>
	new Date(Date.parse(`${day.slice(0, 10)}T00:00:00Z`) + DAY_MS).toISOString().slice(0, 10);

/**
 * The page's title and lead: the pace in a sentence once the API has read
 * one, and before that where the database stands and when the pace will
 * show — never a pace made up from a single size.
 */
export function sizeHeadline(
	report: Pick<CapacityReport, "sizes" | "growth" | "collections">,
	now: Date,
): { title: string; lead: string } {
	const collections = [...report.collections].sort((a, b) => b.storage_bytes - a.storage_bytes);
	const stored = collections.reduce((sum, c) => sum + c.storage_bytes, 0);
	const growth = report.growth;
	if (!growth) {
		const largest = collections[0];
		const where = largest
			? `${largest.name} is the largest of ${collections.length} collections, at ${formatBytes(largest.storage_bytes)}.`
			: "The database has no collections yet.";
		const first = report.sizes?.[0];
		const when = first
			? `Sizes are kept once a day from ${longDay(first.day)}; the pace shows from ${longDay(nextDay(first.day))}, once there are two to compare.`
			: "The job runner keeps the database's size once a day from its next run; the pace shows the day after, once there are two to compare.";
		return { title: `The database takes up ${formatBytes(stored)}.`, lead: `${where} ${when}` };
	}
	const pace = growth.bytes_a_month;
	const title =
		pace > 0
			? `The database grows about ${formatBytes(pace)} a month.`
			: pace < 0
				? `The database shrinks about ${formatBytes(-pace)} a month.`
				: `The database has kept its size since ${longDay(growth.since)}.`;
	const fastest = collections
		.filter((c) => (c.growth_bytes_a_month ?? 0) > 0)
		.sort((a, b) => (b.growth_bytes_a_month ?? 0) - (a.growth_bytes_a_month ?? 0))[0];
	const who = fastest
		? `${fastest.name} grows fastest, about ${formatBytes(fastest.growth_bytes_a_month ?? 0)} a month.`
		: "No collection grew.";
	const span = daysBetween(growth.since, growth.until);
	const over =
		span < 7
			? `Measured over the ${span === 1 ? "one day" : `${span} days`} kept so far, so it will settle as more are kept.`
			: `Measured from ${longDay(growth.since)} to ${longDay(growth.until)}.`;
	const today = now.toISOString().slice(0, 10);
	const stale =
		daysBetween(growth.until, today) > 1
			? ` The job runner last kept a size on ${longDay(growth.until)}.`
			: "";
	return { title, lead: `${who} ${over}${stale}` };
}

/** What the database moved over the pace's days, for the tile under its size. */
export function moved(growth: Growth): string {
	const since = longDay(growth.since);
	if (growth.change_bytes > 0) return `Up ${formatBytes(growth.change_bytes)} since ${since}.`;
	if (growth.change_bytes < 0) return `Down ${formatBytes(-growth.change_bytes)} since ${since}.`;
	return `No change since ${since}.`;
}

/**
 * A collection's "Growth a month": its share of what it took up when the
 * pace's days began, or its bytes when it took up nothing then; "New" when
 * it was made since, and a dash before there is a pace at all.
 */
export function growthCell(collection: Collection, paced: boolean): string {
	if (!paced) return "—";
	const share = collection.growth_share_a_month;
	const bytes = collection.growth_bytes_a_month;
	if (share !== null && share !== undefined) {
		const percent = Math.round(share * 100);
		return percent > 0 ? `+${percent}%` : percent < 0 ? `−${-percent}%` : "0%";
	}
	if (bytes !== null && bytes !== undefined) {
		return bytes >= 0 ? `+${formatBytes(bytes)}` : `−${formatBytes(-bytes)}`;
	}
	return "New";
}

const AXIS_MONTH = new Intl.DateTimeFormat("en-GB", { month: "short", timeZone: "UTC" });
const AXIS_MONTH_YEAR = new Intl.DateTimeFormat("en-GB", {
	month: "short",
	year: "numeric",
	timeZone: "UTC",
});
const AXIS_DAY = new Intl.DateTimeFormat("en-GB", {
	day: "numeric",
	month: "short",
	timeZone: "UTC",
});

export type SizeChart = {
	/** The sizes kept, as a polyline. */
	actual: string;
	/** The pace carried on from the newest, as a polyline; empty without a pace. */
	ahead: string;
	/** Each size kept, where it is drawn, for the hover. */
	points: Array<{ x: number; y: number; day: string; bytes: number }>;
	/** Where the newest size sits, and the size projected at the end. */
	now: { x: number; y: number };
	end: { day: string; bytes: number } | null;
	/** The axis: the first day kept, the newest (when it has room), the end. */
	labels: Array<{ x: number; text: string; anchor: "start" | "middle" | "end" }>;
};

/**
 * The "Database size" chart's geometry in a `width` × `height` plot box:
 * every size kept, and the pace carried forward from the newest — as far
 * ahead as there is history behind it, at least a month and at most a year,
 * so a few days' pace is not drawn a year out. The axis is not drawn from
 * zero: the line is about change, and the newest size is labelled on it.
 * The labels' `x` is in the same box, for the page to place them outside it.
 */
export function sizeChart(
	sizes: Sizes,
	growth: CapacityReport["growth"],
	width: number,
	height: number,
): SizeChart | null {
	if (sizes.length < 2) return null;
	const first = sizes[0];
	const last = sizes[sizes.length - 1];
	if (!first || !last) return null;
	const history = daysBetween(first.day, last.day);
	const aheadDays = growth ? Math.min(365, Math.max(30, history)) : 0;
	const endDay = new Date(Date.parse(`${last.day}T00:00:00Z`) + aheadDays * DAY_MS)
		.toISOString()
		.slice(0, 10);
	const endBytes = growth
		? Math.max(0, last.storage_bytes + (growth.bytes_a_month * aheadDays) / 30)
		: null;
	const values = sizes.map((s) => s.storage_bytes).concat(endBytes === null ? [] : [endBytes]);
	let low = Math.min(...values);
	let high = Math.max(...values);
	if (high === low) {
		low = Math.max(0, low - 1);
		high += 1;
	}
	const pad = (high - low) * 0.08;
	low = Math.max(0, low - pad);
	high += pad;
	// A stroke's width in from each edge, so the line is not cut in half.
	const left = 2;
	const right = width - 2;
	const top = 2;
	const bottom = height - 2;
	const span = history + aheadDays;
	const x = (day: string) => left + (daysBetween(first.day, day) / span) * (right - left);
	const y = (bytes: number) => bottom - ((bytes - low) / (high - low)) * (bottom - top);
	const points = sizes.map((s) => ({
		x: x(s.day),
		y: y(s.storage_bytes),
		day: s.day,
		bytes: s.storage_bytes,
	}));
	const line = (pts: Array<{ x: number; y: number }>) =>
		pts.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" ");
	const now = { x: x(last.day), y: y(last.storage_bytes) };
	const months = span >= 120;
	const label = (day: string, withYear: boolean) => {
		const date = new Date(`${day}T00:00:00Z`);
		return months ? (withYear ? AXIS_MONTH_YEAR : AXIS_MONTH).format(date) : AXIS_DAY.format(date);
	};
	const labels: SizeChart["labels"] = [{ x: left, text: label(first.day, true), anchor: "start" }];
	if (endBytes !== null) {
		// The newest day's label only where it clears both ends'.
		if (now.x - left >= width * 0.15 && right - now.x >= width * 0.15) {
			labels.push({ x: now.x, text: label(last.day, false), anchor: "middle" });
		}
		labels.push({ x: right, text: label(endDay, true), anchor: "end" });
	} else {
		labels.push({ x: right, text: label(last.day, true), anchor: "end" });
	}
	return {
		actual: line(points),
		ahead: endBytes === null ? "" : line([now, { x: right, y: y(endBytes) }]),
		points,
		now,
		end: endBytes === null ? null : { day: endDay, bytes: endBytes },
		labels,
	};
}

// ── The coach's cost by model ───────────────────────────────────────────

/**
 * Each model family's colour, in the order the bars stack them: fixed, so a
 * family keeps its colour whichever range or month is shown. Sonnet and
 * Haiku, the two the coach runs on, are the pair told apart best in both
 * hours (blue and coral); anything not named here is "Other", in grey.
 */
export const MODEL_FAMILIES = [
	{ family: "Sonnet", colour: "var(--data-blue)" },
	{ family: "Haiku", colour: "var(--data-coral)" },
	{ family: "Opus", colour: "var(--data-lavender)" },
	{ family: "Fable", colour: "var(--data-teal)" },
	{ family: "Other", colour: "var(--data-grey)" },
] as const;

export type ModelFamily = (typeof MODEL_FAMILIES)[number];

/** "claude-sonnet-4-6" → "Sonnet"; a model the table does not name → "Other". */
export function familyOf(model: string): ModelFamily["family"] {
	const lower = model.toLowerCase();
	return MODEL_FAMILIES.find((f) => lower.includes(f.family.toLowerCase()))?.family ?? "Other";
}

/**
 * The coach's cost a day by model family, every day of the last `count` up
 * to `today`, oldest first; `families` are those with any cost in the days,
 * in the fixed order, and each day's `parts` line up with them.
 */
export function dailyCostByFamily(
	rows: CoachCost,
	count: number,
	today: Date,
): {
	families: ModelFamily[];
	days: Array<{ day: string; total: number; parts: number[] }>;
} {
	const shown = everyDay([], count, today);
	const inRange = new Set(shown.map((d) => d.day));
	const byDay = new Map<string, Map<string, number>>();
	for (const row of rows) {
		if (!inRange.has(row.day)) continue;
		const family = familyOf(row.model);
		const day = byDay.get(row.day) ?? new Map<string, number>();
		day.set(family, (day.get(family) ?? 0) + row.cost_usd);
		byDay.set(row.day, day);
	}
	const families = MODEL_FAMILIES.filter((f) =>
		[...byDay.values()].some((day) => (day.get(f.family) ?? 0) > 0),
	);
	return {
		families,
		days: shown.map(({ day }) => {
			const parts = families.map((f) => byDay.get(day)?.get(f.family) ?? 0);
			return { day, total: parts.reduce((sum, v) => sum + v, 0), parts };
		}),
	};
}
