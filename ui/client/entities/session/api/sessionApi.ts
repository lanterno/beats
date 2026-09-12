/**
 * Session API Functions
 * Low-level API calls for sessions (beats) and analytics.
 */

import type {
	ApiBeat,
	FlowWindow,
	FlowWindowSummary,
	Gap,
	HeatmapDay,
	RhythmSlot,
} from "@/shared/api";
import {
	ApiBeatListSchema,
	del,
	FlowWindowListSchema,
	FlowWindowSummarySchema,
	GapListSchema,
	get,
	HeatmapDayListSchema,
	parseApiResponse,
	put,
	RhythmSlotListSchema,
} from "@/shared/api";
import { browserTimeZone } from "@/shared/lib";

export async function fetchBeats(projectId?: string): Promise<ApiBeat[]> {
	const url = projectId ? `/api/beats/?project_id=${projectId}` : "/api/beats/";
	const data = await get<unknown>(url);
	return parseApiResponse(ApiBeatListSchema, data);
}

export async function updateBeat(beat: ApiBeat): Promise<void> {
	await put<void>("/api/beats/", beat);
}

export async function deleteBeat(beatId: string): Promise<void> {
	await del<{ deleted: boolean }>(`/api/beats/${beatId}`);
}

/**
 * Fetch heatmap data for a given year, optionally filtered by project and/or tag
 */
export async function fetchHeatmap(
	year: number,
	projectId?: string,
	tag?: string,
): Promise<HeatmapDay[]> {
	let url = `/api/analytics/heatmap?year=${year}&tz=${encodeURIComponent(browserTimeZone())}`;
	if (projectId) url += `&project_id=${projectId}`;
	if (tag) url += `&tag=${encodeURIComponent(tag)}`;
	const data = await get<unknown>(url);
	return parseApiResponse(HeatmapDayListSchema, data);
}

/**
 * Fetch daily rhythm data for a given period, optionally filtered by project and/or tag
 */
export async function fetchDailyRhythm(
	period: string,
	projectId?: string,
	tag?: string,
): Promise<RhythmSlot[]> {
	let url = `/api/analytics/rhythm?period=${period}&tz=${encodeURIComponent(browserTimeZone())}`;
	if (projectId) url += `&project_id=${projectId}`;
	if (tag) url += `&tag=${encodeURIComponent(tag)}`;
	const data = await get<unknown>(url);
	return parseApiResponse(RhythmSlotListSchema, data);
}

export async function fetchAllTags(): Promise<string[]> {
	return get<string[]>("/api/analytics/tags");
}

export async function fetchGaps(targetDate: string): Promise<Gap[]> {
	const tz = encodeURIComponent(browserTimeZone());
	const data = await get<unknown>(`/api/analytics/gaps?target_date=${targetDate}&tz=${tz}`);
	return parseApiResponse(GapListSchema, data);
}

/**
 * Fetch flow windows in a date range. Each window is ~1 minute of
 * aggregated desktop activity emitted by the daemon's collector.
 *
 * Optional filters narrow the result server-side via the query params
 * on /api/signals/flow-windows. They AND-compose:
 * - projectId — windows where active_project_id matched (timer was
 *   running on this project at the time)
 * - editorRepo — windows whose VS Code heartbeat reported this
 *   absolute workspace path
 * - editorLanguage — windows whose VS Code heartbeat reported this
 *   language id (e.g. "go", "typescriptreact")
 * - bundleId — windows whose dominant frontmost app matched this
 *   macOS bundle id (e.g. "com.microsoft.VSCode")
 */
export async function fetchFlowWindows(
	start: string,
	end: string,
	options: {
		projectId?: string;
		editorRepo?: string;
		editorLanguage?: string;
		bundleId?: string;
	} = {},
): Promise<FlowWindow[]> {
	const params = new URLSearchParams({ start, end });
	if (options.projectId) params.set("project_id", options.projectId);
	if (options.editorRepo) params.set("editor_repo", options.editorRepo);
	if (options.editorLanguage) params.set("editor_language", options.editorLanguage);
	if (options.bundleId) params.set("bundle_id", options.bundleId);
	const data = await get<unknown>(`/api/signals/flow-windows?${params.toString()}`);
	return parseApiResponse(FlowWindowListSchema, data);
}

/**
 * A distraction "drift" event recorded by the daemon's shield package
 * (stored as a flow window with dominant_category="drift"). Served by
 * /api/signals/recent-drift.
 */
export interface DriftEvent {
	id: string;
	started_at: string;
	duration_seconds: number;
	bundle_id: string;
}

/**
 * Fetch recent drift (distraction) events. `since` defaults server-side to
 * the last 30 minutes; pass a day's start ISO to get "today's" distractions.
 */
export async function fetchRecentDrift(since?: string, limit = 100): Promise<DriftEvent[]> {
	const params = new URLSearchParams({ limit: String(limit) });
	if (since) params.set("since", since);
	const data = await get<{ events: DriftEvent[] }>(
		`/api/signals/recent-drift?${params.toString()}`,
	);
	return data.events ?? [];
}

/**
 * Fetch single round-trip aggregate stats for a flow-window slice.
 * Hits /api/signals/flow-windows/summary which returns count/avg/peak
 * plus the top bucket on each grouping axis — designed for headline
 * cards that don't need every row.
 */
export async function fetchFlowWindowsSummary(
	start: string,
	end: string,
	options: {
		projectId?: string;
		editorRepo?: string;
		editorLanguage?: string;
		bundleId?: string;
	} = {},
): Promise<FlowWindowSummary> {
	const params = new URLSearchParams({ start, end });
	if (options.projectId) params.set("project_id", options.projectId);
	if (options.editorRepo) params.set("editor_repo", options.editorRepo);
	if (options.editorLanguage) params.set("editor_language", options.editorLanguage);
	if (options.bundleId) params.set("bundle_id", options.bundleId);
	const data = await get<unknown>(`/api/signals/flow-windows/summary?${params.toString()}`);
	return parseApiResponse(FlowWindowSummarySchema, data);
}
