/**
 * Planning API Functions
 * Low-level API calls for weekly plans (structured numeric time budgets).
 */

import { get, put } from "@/shared/api";

// Weekly Plans

export async function fetchWeeklyPlan(weekOf: string) {
	return get<{ week_of: string; budgets: Array<{ project_id: string; planned_hours: number }> }>(
		`/api/plans/weekly?week_of=${weekOf}`,
	);
}

export async function upsertWeeklyPlan(
	weekOf: string,
	budgets: Array<{ project_id: string; planned_hours: number }>,
) {
	return put<unknown>("/api/plans/weekly", { week_of: weekOf, budgets });
}
