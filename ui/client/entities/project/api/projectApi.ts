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
	post,
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
 * Create a new project. Color is optional — when omitted the UI assigns a
 * stable color from the id (see toProject), so a created project always
 * renders with a color even if the user didn't pick one.
 */
export async function createProject(input: {
	name: string;
	description?: string | null;
	color?: string | null;
	weekly_goal?: number | null;
	category?: string | null;
	github_repo?: string | null;
	autostart_repos?: string[];
}): Promise<ApiProject> {
	const data = await post<unknown>("/api/projects/", input);
	return parseApiResponse(ApiProjectSchema, data);
}

/**
 * Archive a project. Uses the dedicated POST /api/projects/{id}/archive
 * endpoint (not a generic update) so the call can't silently wipe fields
 * the UI Project type doesn't yet manage.
 */
export async function archiveProject(projectId: string): Promise<void> {
	await post<{ status: string }>(`/api/projects/${projectId}/archive`, {});
}

/**
 * Restore an archived project. Symmetric to archiveProject — uses the
 * dedicated /unarchive endpoint for the same reason.
 */
export async function unarchiveProject(projectId: string): Promise<void> {
	await post<{ status: string }>(`/api/projects/${projectId}/unarchive`, {});
}

/**
 * Fetch project week breakdown
 */
export interface WeekBreakdownResult {
	totalHours: number;
	dailyDurations: Record<string, string>;
	/** Canonical Monday (ISO date) for this week, resolved server-side. */
	weekStart: string | undefined;
	/** number = goal applies; null = override says "no goal"; undefined = unknown */
	effectiveGoal: number | null | undefined;
	effectiveGoalType?: "target" | "cap";
	/** True iff a goal override resolves for this week (regardless of value) */
	effectiveGoalOverridden: boolean;
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
		weekStart: parsed.week_start,
		// Preserve null vs undefined: null = override sets "no goal" for this
		// week; undefined = field absent (older API). Without this, a "no goal"
		// override would silently fall back to project.weeklyGoal in the UI.
		effectiveGoal: parsed.effective_goal === undefined ? undefined : parsed.effective_goal,
		effectiveGoalType: parsed.effective_goal_type ?? undefined,
		effectiveGoalOverridden: parsed.effective_goal_overridden,
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
	github_repo?: string | null;
	category?: string | null;
	autostart_repos?: string[];
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
