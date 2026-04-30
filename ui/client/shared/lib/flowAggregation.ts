/**
 * Pure aggregation helpers for flow windows. Kept separate from the React
 * components so the math is unit-testable without rendering.
 */
import type { FlowWindow } from "@/shared/api";

export interface RepoStat {
	repo: string;
	avg: number;
	minutes: number;
	count: number;
}

/**
 * Groups flow windows by editor_repo and returns the top [limit] repos
 * sorted by tracked minutes (count of windows that hit each repo).
 *
 * Windows without an editor_repo are skipped — they represent slices
 * where no editor heartbeat was active, which would group together as
 * a meaningless "(unknown)" bucket.
 *
 * Each window represents ~1 minute of activity (the daemon's default
 * flush interval), so we use the count of windows as the minutes
 * approximation. Avg is the unweighted mean of flow_score across
 * windows in the bucket.
 */
export function aggregateFlowByRepo(windows: FlowWindow[], limit = 5): RepoStat[] {
	if (windows.length === 0) return [];

	const byRepo = new Map<string, { sum: number; count: number }>();
	for (const w of windows) {
		const repo = w.editor_repo;
		if (!repo) continue;
		const cur = byRepo.get(repo) ?? { sum: 0, count: 0 };
		cur.sum += w.flow_score;
		cur.count += 1;
		byRepo.set(repo, cur);
	}

	return Array.from(byRepo.entries())
		.map(([repo, { sum, count }]) => ({
			repo,
			avg: sum / count,
			minutes: count,
			count,
		}))
		.sort((a, b) => b.minutes - a.minutes)
		.slice(0, limit);
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
