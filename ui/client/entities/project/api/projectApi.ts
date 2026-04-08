/**
 * Project API Functions
 * Low-level API calls for projects.
 */

import type { ApiGoalOverride, ApiProject } from "@/shared/api";
import {
	ApiProjectListSchema,
	ApiProjectSchema,
	get,
	ProjectTotalSchema,
	parseApiResponse,
	put,
	WeekBreakdownSchema,
} from "@/shared/api";

/**
 * Fetch all projects from the API
 */
export async function fetchProjects(): Promise<ApiProject[]> {
	const data = await get<unknown>("/api/projects/");
	return parseApiResponse(ApiProjectListSchema, data);
}

/**
 * Fetch project week breakdown
 */
export interface WeekBreakdownResult {
	totalHours: number;
	dailyDurations: Record<string, string>;
	effectiveGoal?: number;
	effectiveGoalType?: "target" | "cap";
}

export async function fetchProjectWeek(
	projectId: string,
	weeksAgo: number,
): Promise<WeekBreakdownResult> {
	const data = await get<unknown>(`/api/projects/${projectId}/week/?weeks_ago=${weeksAgo}`);
	const parsed = parseApiResponse(WeekBreakdownSchema, data);

	const WEEKDAY_KEYS = [
		"Monday",
		"Tuesday",
		"Wednesday",
		"Thursday",
		"Friday",
		"Saturday",
		"Sunday",
	] as const;
	const dailyDurations = Object.fromEntries(
		WEEKDAY_KEYS.map((d) => [d, parsed[d] || "0:00:00"]),
	) as Record<string, string>;

	return {
		totalHours: parsed.total_hours,
		dailyDurations,
		effectiveGoal: parsed.effective_goal ?? undefined,
		effectiveGoalType: parsed.effective_goal_type ?? undefined,
	};
}

/**
 * Fetch project total minutes
 */
/**
 * Update a project
 */
export async function updateProject(project: {
	id: string;
	name: string;
	description?: string | null;
	color?: string | null;
	archived?: boolean;
	weekly_goal?: number | null;
	goal_type?: string;
}): Promise<ApiProject> {
	const data = await put<unknown>("/api/projects/", project);
	return parseApiResponse(ApiProjectSchema, data);
}

/**
 * Replace goal overrides for a project
 */
export async function updateGoalOverrides(
	projectId: string,
	overrides: ApiGoalOverride[],
): Promise<ApiProject> {
	const data = await put<unknown>(`/api/projects/${projectId}/goal-overrides`, overrides);
	return parseApiResponse(ApiProjectSchema, data);
}

export async function fetchProjectTotal(projectId: string): Promise<number> {
	try {
		const data = await get<unknown>(`/api/projects/${projectId}/total/`);
		const parsed = parseApiResponse(ProjectTotalSchema, data);

		if (typeof parsed.total_minutes === "number") {
			return parsed.total_minutes;
		}

		// Fallback: sum durations_per_month (legacy support)
		if (parsed.durations_per_month) {
			const totalHours = Object.values(parsed.durations_per_month).reduce<number>(
				(sum, h) => sum + (h || 0),
				0,
			);
			return Math.round(totalHours * 60);
		}

		return 0;
	} catch {
		return 0;
	}
}
