/**
 * Planning API Functions
 * Low-level API calls for intentions and daily notes.
 */

import type { DailyNote, Intention } from "@/shared/api";
import {
	DailyNoteSchema,
	del,
	get,
	IntentionListSchema,
	parseApiResponse,
	patch,
	post,
	put,
} from "@/shared/api";

// Intentions

export async function fetchIntentions(date?: string): Promise<Intention[]> {
	const params = date ? `?target_date=${date}` : "";
	const data = await get<unknown>(`/api/intentions${params}`);
	return parseApiResponse(IntentionListSchema, data);
}

export async function createIntention(
	projectId: string,
	plannedMinutes: number,
	date?: string,
): Promise<Intention> {
	const body: Record<string, unknown> = {
		project_id: projectId,
		planned_minutes: plannedMinutes,
	};
	if (date) body.date = date;
	const data = await post<unknown>("/api/intentions", body);
	return parseApiResponse(DailyNoteSchema.passthrough(), data) as unknown as Intention;
}

export async function updateIntention(
	intentionId: string,
	updates: { completed?: boolean; planned_minutes?: number },
): Promise<void> {
	await patch<void>(`/api/intentions/${intentionId}`, updates);
}

export async function deleteIntention(intentionId: string): Promise<void> {
	await del<void>(`/api/intentions/${intentionId}`);
}

// Daily Notes

export async function fetchDailyNote(date?: string): Promise<DailyNote | null> {
	const params = date ? `?target_date=${date}` : "";
	const data = await get<unknown>(`/api/daily-notes${params}`);
	if (!data) return null;
	return parseApiResponse(DailyNoteSchema, data);
}

export async function upsertDailyNote(
	note: string,
	mood?: number,
	date?: string,
): Promise<DailyNote> {
	const body: Record<string, unknown> = { note };
	if (mood !== undefined) body.mood = mood;
	if (date) body.date = date;
	const data = await put<unknown>("/api/daily-notes", body);
	return parseApiResponse(DailyNoteSchema, data);
}

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

// Recurring Intentions

export async function fetchRecurringIntentions() {
	return get<
		Array<{
			id: string;
			project_id: string;
			planned_minutes: number;
			days_of_week: number[];
			enabled: boolean;
		}>
	>("/api/plans/recurring");
}

export async function createRecurringIntention(body: {
	project_id: string;
	planned_minutes: number;
	days_of_week: number[];
}) {
	return post<unknown>("/api/plans/recurring", body);
}

export async function deleteRecurringIntention(id: string) {
	return del<unknown>(`/api/plans/recurring/${id}`);
}

export async function applyRecurringIntentions() {
	return post<{ created: number; date: string }>("/api/plans/recurring/apply");
}

// Weekly Reviews

export async function fetchWeeklyReview(weekOf: string) {
	return get<{
		week_of: string;
		went_well: string;
		didnt_go_well: string;
		to_change: string;
	}>(`/api/plans/reviews/weekly?week_of=${weekOf}`);
}

export async function upsertWeeklyReview(body: {
	week_of: string;
	went_well: string;
	didnt_go_well: string;
	to_change: string;
}) {
	return put<unknown>("/api/plans/reviews/weekly", body);
}

// Intention Streaks

export async function fetchIntentionStreaks() {
	return get<{ current_streak: number; best_streak: number }>("/api/plans/intention-streaks");
}
