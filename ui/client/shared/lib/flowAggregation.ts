/**
 * Pure aggregation helpers for flow windows. Kept separate from the React
 * components so the math is unit-testable without rendering.
 */
import type { FlowWindow } from "@/shared/api";

/**
 * One bucket of aggregated flow data. The `key` field is generic — it could
 * be a repo path, language id, dominant category, branch, or anything else
 * the caller chooses to group by.
 */
export interface FlowGroupStat {
	key: string;
	avg: number;
	minutes: number;
	count: number;
}

/** Backwards-compat alias used by FlowByRepo before the helper was generalized. */
export type RepoStat = FlowGroupStat & { repo: string };

/**
 * Groups flow windows by an arbitrary string field extracted via [keyOf]
 * and returns the top [limit] buckets sorted by tracked minutes.
 *
 * Windows where [keyOf] returns null / undefined / "" are skipped — they'd
 * otherwise collapse into a meaningless "(unknown)" bucket.
 *
 * Each window represents ~1 minute of activity (the daemon's default
 * flush interval), so window count doubles as a minutes approximation.
 * Avg is the unweighted mean of flow_score across windows in the bucket.
 */
export function aggregateFlowBy(
	windows: FlowWindow[],
	keyOf: (w: FlowWindow) => string | null | undefined,
	limit = 5,
): FlowGroupStat[] {
	if (windows.length === 0) return [];

	const groups = new Map<string, { sum: number; count: number }>();
	for (const w of windows) {
		const key = keyOf(w);
		if (!key) continue;
		const cur = groups.get(key) ?? { sum: 0, count: 0 };
		cur.sum += w.flow_score;
		cur.count += 1;
		groups.set(key, cur);
	}

	return Array.from(groups.entries())
		.map(([key, { sum, count }]) => ({
			key,
			avg: sum / count,
			minutes: count,
			count,
		}))
		.sort((a, b) => {
			// Primary sort by minutes, tie-break on avg score so the
			// higher-quality bucket surfaces first when minutes match.
			// Same rule as the daemon's aggregateBy (Go) and the
			// API's _top_bucket (Python) — kept in lockstep so a user
			// toggling between web and `beatsd top` sees the same
			// row order on tied minutes.
			if (b.minutes !== a.minutes) return b.minutes - a.minutes;
			return b.avg - a.avg;
		})
		.slice(0, limit);
}

/**
 * Convenience wrapper for the most common case (group by editor_repo).
 * Preserves the original `repo` field name on the return shape so callers
 * predating the generic helper don't have to change.
 */
export function aggregateFlowByRepo(windows: FlowWindow[], limit = 5): RepoStat[] {
	return aggregateFlowBy(windows, (w) => w.editor_repo, limit).map((g) => ({
		...g,
		repo: g.key,
	}));
}

/**
 * Returns the last [segments] segments of a path so a deeply-nested
 * workspace stays readable in a single row. Falls back to the original
 * if the path has fewer segments than requested. Handles both / and \.
 */
export function shortRepoPath(path: string, segments = 2): string {
	const parts = path.split(/[\\/]/).filter(Boolean);
	if (parts.length === 0) return path;
	if (parts.length <= segments) return parts.join("/");
	return parts.slice(-segments).join("/");
}

export interface FlowSummary {
	avg: number;
	peak: number;
	count: number;
	/**
	 * Index of the peak window in the input array. -1 only when [count] is 0
	 * (which we already exclude by returning null), so callers can treat it
	 * as a non-null number when [FlowSummary] itself is non-null.
	 */
	peakIndex: number;
}

export interface DailyFlow {
	/** Local-date key in YYYY-MM-DD form. */
	date: string;
	avg: number;
	count: number;
}

/**
 * Buckets flow windows into per-day summaries keyed by local YYYY-MM-DD.
 * Used by the Flow this week card to show daily averages over a date
 * range. Days with no windows are NOT inserted — caller decides whether
 * to backfill empty days for a fixed-width chart.
 */
export function aggregateFlowByDay(windows: FlowWindow[]): DailyFlow[] {
	if (windows.length === 0) return [];
	const byDay = new Map<string, { sum: number; count: number }>();
	for (const w of windows) {
		const date = localDateKey(w.window_start);
		const cur = byDay.get(date) ?? { sum: 0, count: 0 };
		cur.sum += w.flow_score;
		cur.count += 1;
		byDay.set(date, cur);
	}
	return Array.from(byDay.entries())
		.map(([date, { sum, count }]) => ({
			date,
			avg: sum / count,
			count,
		}))
		.sort((a, b) => a.date.localeCompare(b.date));
}

/**
 * Returns the local YYYY-MM-DD for an ISO timestamp. We deliberately
 * key by *local* date (not UTC) so a session at 23:30 and another at
 * 00:30 the same evening don't end up on different days from the user's
 * perspective.
 */
export function localDateKey(iso: string): string {
	const d = new Date(iso);
	const y = d.getFullYear();
	const m = String(d.getMonth() + 1).padStart(2, "0");
	const day = String(d.getDate()).padStart(2, "0");
	return `${y}-${m}-${day}`;
}

/**
 * Returns the user's "typical day" baseline — the average flow score
 * across all windows whose local date is **strictly before** [asOfDate].
 * Today's data is excluded so the baseline answers "how does today
 * compare to my recent days?" without including itself.
 *
 * Returns null when there are fewer than [minWindows] qualifying windows
 * — too little data to draw any signal from. Callers should render a
 * neutral state in that case rather than a misleading "above typical"
 * built on three windows.
 */
export function flowBaseline(
	windows: FlowWindow[],
	asOfDate: Date,
	minWindows = 30,
): number | null {
	const todayKey = `${asOfDate.getFullYear()}-${String(asOfDate.getMonth() + 1).padStart(2, "0")}-${String(asOfDate.getDate()).padStart(2, "0")}`;
	let sum = 0;
	let count = 0;
	for (const w of windows) {
		if (localDateKey(w.window_start) >= todayKey) continue;
		sum += w.flow_score;
		count++;
	}
	if (count < minWindows) return null;
	return sum / count;
}

/**
 * Aggregate score statistics across the given windows. Returns null when
 * there's nothing to summarize, so callers can render an empty state
 * rather than "avg 0 / peak 0 / 0 windows".
 *
 * On ties (multiple windows at the exact peak score), [peakIndex] points
 * at the *first* such window — the earliest peak moment of the day. This
 * matters because callers display "peak at HH:MM"; the alternative
 * (latest peak) feels like the day got worse, the earliest framing reads
 * as "this is when you locked in".
 */
export interface HourlyFlow {
	/** Hour of day, 0–23 in the user's local time. */
	hour: number;
	avg: number;
	count: number;
}

export interface WeekdayFlow {
	/** 0 = Sunday … 6 = Saturday, matching JS Date.getDay(). */
	weekday: number;
	avg: number;
	count: number;
}

/**
 * Buckets flow windows into 24 hour-of-day slots and returns the average
 * score for each populated hour. Designed for the "Flow rhythm" card
 * that surfaces *when* during the day a user tends to flow best,
 * answering a different question than FlowThisWeek (which day) or
 * FlowToday (today's shape).
 *
 * Empty hours are omitted — caller decides whether to backfill the 24
 * slots for a fixed-width chart or just render the populated ones.
 */
export function aggregateFlowByHour(windows: FlowWindow[]): HourlyFlow[] {
	if (windows.length === 0) return [];
	const sums = new Array<number>(24).fill(0);
	const counts = new Array<number>(24).fill(0);
	for (const w of windows) {
		const h = new Date(w.window_start).getHours();
		sums[h] += w.flow_score;
		counts[h] += 1;
	}
	const out: HourlyFlow[] = [];
	for (let h = 0; h < 24; h++) {
		if (counts[h] === 0) continue;
		out.push({ hour: h, avg: sums[h] / counts[h], count: counts[h] });
	}
	return out;
}

/**
 * Buckets flow windows by local day-of-week and returns the mean score
 * for each populated weekday. Sibling to aggregateFlowByHour — answers
 * "do I flow better on certain weekdays?" rather than "when in the day".
 *
 * Uses Date.getDay() (Sunday=0..Saturday=6); callers can reorder for
 * Monday-first display by mapping the index. Empty weekdays are
 * omitted; caller decides whether to backfill the seven slots.
 */
export function aggregateFlowByWeekday(windows: FlowWindow[]): WeekdayFlow[] {
	if (windows.length === 0) return [];
	const sums = new Array<number>(7).fill(0);
	const counts = new Array<number>(7).fill(0);
	for (const w of windows) {
		const d = new Date(w.window_start).getDay();
		sums[d] += w.flow_score;
		counts[d] += 1;
	}
	const out: WeekdayFlow[] = [];
	for (let d = 0; d < 7; d++) {
		if (counts[d] === 0) continue;
		out.push({ weekday: d, avg: sums[d] / counts[d], count: counts[d] });
	}
	return out;
}

export function summarizeFlow(windows: FlowWindow[]): FlowSummary | null {
	if (windows.length === 0) return null;
	let sum = 0;
	let peak = -Infinity;
	let peakIndex = 0;
	for (let i = 0; i < windows.length; i++) {
		const score = windows[i].flow_score;
		sum += score;
		if (score > peak) {
			peak = score;
			peakIndex = i;
		}
	}
	return { avg: sum / windows.length, peak, count: windows.length, peakIndex };
}
