/**
 * Session API Functions
 * Low-level API calls for sessions (beats) and analytics.
 */

import type { ApiBeat, FlowWindow, Gap, HeatmapDay, RhythmSlot } from "@/shared/api";
import {
	ApiBeatListSchema,
	FlowWindowListSchema,
	GapListSchema,
	get,
	HeatmapDayListSchema,
	parseApiResponse,
	put,
	RhythmSlotListSchema,
} from "@/shared/api";

/**
 * Fetch all beats, optionally filtered by project
 */
export async function fetchBeats(projectId?: string): Promise<ApiBeat[]> {
	const url = projectId ? `/api/beats/?project_id=${projectId}` : "/api/beats/";
	const data = await get<unknown>(url);
	return parseApiResponse(ApiBeatListSchema, data);
}

/**
 * Update a beat (work session)
 */
export async function updateBeat(beat: ApiBeat): Promise<void> {
	await put<void>("/api/beats/", beat);
}

/**
 * Fetch heatmap data for a given year, optionally filtered by project and/or tag
 */
export async function fetchHeatmap(
	year: number,
	projectId?: string,
	tag?: string,
): Promise<HeatmapDay[]> {
	let url = `/api/analytics/heatmap?year=${year}`;
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
	let url = `/api/analytics/rhythm?period=${period}`;
	if (projectId) url += `&project_id=${projectId}`;
	if (tag) url += `&tag=${encodeURIComponent(tag)}`;
	const data = await get<unknown>(url);
	return parseApiResponse(RhythmSlotListSchema, data);
}

/**
 * Fetch all unique tags used across sessions
 */
export async function fetchAllTags(): Promise<string[]> {
	return get<string[]>("/api/analytics/tags");
}

/**
 * Fetch untracked time gaps for a given date
 */
export async function fetchGaps(targetDate: string): Promise<Gap[]> {
	const data = await get<unknown>(`/api/analytics/gaps?target_date=${targetDate}`);
	return parseApiResponse(GapListSchema, data);
}

/**
 * Fetch flow windows in a date range. Each window is ~1 minute of
 * aggregated desktop activity emitted by the daemon's collector.
 *
 * Optional filters narrow the result server-side via the new query
 * params on /api/signals/flow-windows:
 * - projectId — windows where active_project_id matched (timer was
 *   running on this project at the time)
 * - editorRepo — windows whose VS Code heartbeat reported this
 *   absolute workspace path
 */
export async function fetchFlowWindows(
	start: string,
	end: string,
	options: { projectId?: string; editorRepo?: string } = {},
): Promise<FlowWindow[]> {
	const params = new URLSearchParams({ start, end });
	if (options.projectId) params.set("project_id", options.projectId);
	if (options.editorRepo) params.set("editor_repo", options.editorRepo);
	const data = await get<unknown>(`/api/signals/flow-windows?${params.toString()}`);
	return parseApiResponse(FlowWindowListSchema, data);
}
