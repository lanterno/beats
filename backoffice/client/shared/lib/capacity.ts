/**
 * Capacity's arithmetic, apart from the page so it can be tested. The API
 * sends the coach's cost a day and model for the last 31 days (UTC), and each
 * collection's size as it stands: nothing keeps either over time, so the
 * only pace on the page is the coach's, within this month.
 */

import type { CapacityReport } from "@/shared/api/schema";
import { everyDay } from "./format";

/** A day and model's coach cost, as far as this arithmetic reads it. */
type CoachCost = ReadonlyArray<
	Pick<
		CapacityReport["coach_cost"][number],
		"day" | "model" | "cost_usd" | "input_tokens" | "cache_read_tokens"
	>
>;

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
	const cache =
		input > 0
			? `${Math.round((cached / input) * 100)}% of the input came from the cache.`
			: "No input was counted.";
	const bill =
		byModel.size === 1
			? `It all went to ${model}.`
			: `${model} is ${Math.round((share / cost) * 100)}% of the bill.`;
	return `${cache} ${bill}`;
}

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
