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
		.sort((a, b) => b.minutes - a.minutes)
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
}

/**
 * Aggregate score statistics across the given windows. Returns null when
 * there's nothing to summarize, so callers can render an empty state
 * rather than "avg 0 / peak 0 / 0 windows".
 */
export function summarizeFlow(windows: FlowWindow[]): FlowSummary | null {
	if (windows.length === 0) return null;
	let sum = 0;
	let peak = 0;
	for (const w of windows) {
		sum += w.flow_score;
		if (w.flow_score > peak) peak = w.flow_score;
	}
	return { avg: sum / windows.length, peak, count: windows.length };
}
