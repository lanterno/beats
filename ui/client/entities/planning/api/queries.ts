/**
 * Planning TanStack Query hooks
 */
import { useMutation, useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import {
	applyRecurringIntentions,
	createIntention,
	createRecurringIntention,
	deleteIntention,
	deleteRecurringIntention,
	fetchDailyNote,
	fetchIntentionStreaks,
	fetchIntentions,
	fetchRecurringIntentions,
	fetchWeeklyPlan,
	fetchWeeklyReview,
	updateIntention,
	upsertDailyNote,
	upsertWeeklyPlan,
	upsertWeeklyReview,
} from "./planningApi";

export const planningKeys = {
	all: ["planning"] as const,
	intentions: (date?: string) => [...planningKeys.all, "intentions", date] as const,
	dailyNote: (date?: string) => [...planningKeys.all, "daily-note", date] as const,
	weeklyPlan: (weekOf: string) => [...planningKeys.all, "weekly-plan", weekOf] as const,
	recurring: () => [...planningKeys.all, "recurring"] as const,
	weeklyReview: (weekOf: string) => [...planningKeys.all, "weekly-review", weekOf] as const,
	intentionStreaks: () => [...planningKeys.all, "intention-streaks"] as const,
};

export function useIntentions(date?: string) {
	return useQuery({
		queryKey: planningKeys.intentions(date),
		queryFn: () => fetchIntentions(date),
	});
}

export function useCreateIntention() {
	const queryClient = useQueryClient();
	return useMutation({
		mutationFn: (args: { projectId: string; plannedMinutes: number; date?: string }) =>
			createIntention(args.projectId, args.plannedMinutes, args.date),
		onSuccess: () => queryClient.invalidateQueries({ queryKey: planningKeys.all }),
	});
}

export function useUpdateIntention() {
	const queryClient = useQueryClient();
	return useMutation({
		mutationFn: (args: {
			intentionId: string;
			updates: { completed?: boolean; planned_minutes?: number };
		}) => updateIntention(args.intentionId, args.updates),
		onSuccess: () => queryClient.invalidateQueries({ queryKey: planningKeys.all }),
	});
}

export function useDeleteIntention() {
	const queryClient = useQueryClient();
	return useMutation({
		mutationFn: (intentionId: string) => deleteIntention(intentionId),
		onSuccess: () => queryClient.invalidateQueries({ queryKey: planningKeys.all }),
	});
}

export function useDailyNote(date?: string) {
	return useQuery({
		queryKey: planningKeys.dailyNote(date),
		queryFn: () => fetchDailyNote(date),
	});
}

export function useUpsertDailyNote() {
	const queryClient = useQueryClient();
	return useMutation({
		mutationFn: (args: { note: string; mood?: number; date?: string }) =>
			upsertDailyNote(args.note, args.mood, args.date),
		onSuccess: () => queryClient.invalidateQueries({ queryKey: planningKeys.all }),
	});
}

// Weekly Plans

export function useWeeklyPlan(weekOf: string) {
	return useQuery({
		queryKey: planningKeys.weeklyPlan(weekOf),
		queryFn: () => fetchWeeklyPlan(weekOf),
	});
}

/**
 * Hook to fetch planned hours for ONE project across MANY weeks.
 *
 * Returns a Map keyed by mondayIso → planned_hours for the project, with
 * `undefined` meaning "no plan entry for that project that week" (the
 * P4.1 spec distinguishes em-dash for absent vs '0h' for explicit-zero).
 * useQueries parallelizes the per-week fetches and reuses the
 * planningKeys.weeklyPlan cache so other consumers (PlanPage) don't
 * pay twice.
 */
export function useProjectPlannedByWeek(
	projectId: string | undefined,
	mondayIsoList: string[],
): { byMondayIso: Map<string, number>; isLoading: boolean } {
	const results = useQueries({
		queries: mondayIsoList.map((monday) => ({
			queryKey: planningKeys.weeklyPlan(monday),
			queryFn: () => fetchWeeklyPlan(monday),
			staleTime: 60_000,
			enabled: Boolean(projectId),
		})),
	});

	const byMondayIso = new Map<string, number>();
	let isLoading = false;
	results.forEach((q, i) => {
		if (q.isLoading) isLoading = true;
		const monday = mondayIsoList[i];
		const entry = q.data?.budgets.find((b) => b.project_id === projectId);
		if (entry) byMondayIso.set(monday, entry.planned_hours);
	});
	return { byMondayIso, isLoading };
}

export function useUpsertWeeklyPlan() {
	const queryClient = useQueryClient();
	return useMutation({
		mutationFn: (args: {
			weekOf: string;
			budgets: Array<{ project_id: string; planned_hours: number }>;
		}) => upsertWeeklyPlan(args.weekOf, args.budgets),
		onSuccess: () => queryClient.invalidateQueries({ queryKey: planningKeys.all }),
	});
}

// Recurring Intentions

export function useRecurringIntentions() {
	return useQuery({
		queryKey: planningKeys.recurring(),
		queryFn: fetchRecurringIntentions,
	});
}

export function useCreateRecurringIntention() {
	const queryClient = useQueryClient();
	return useMutation({
		mutationFn: createRecurringIntention,
		onSuccess: () => queryClient.invalidateQueries({ queryKey: planningKeys.all }),
	});
}

export function useDeleteRecurringIntention() {
	const queryClient = useQueryClient();
	return useMutation({
		mutationFn: deleteRecurringIntention,
		onSuccess: () => queryClient.invalidateQueries({ queryKey: planningKeys.all }),
	});
}

export function useApplyRecurring() {
	const queryClient = useQueryClient();
	return useMutation({
		mutationFn: applyRecurringIntentions,
		onSuccess: () => queryClient.invalidateQueries({ queryKey: planningKeys.all }),
	});
}

// Weekly Reviews

export function useWeeklyReview(weekOf: string) {
	return useQuery({
		queryKey: planningKeys.weeklyReview(weekOf),
		queryFn: () => fetchWeeklyReview(weekOf),
	});
}

export function useUpsertWeeklyReview() {
	const queryClient = useQueryClient();
	return useMutation({
		mutationFn: upsertWeeklyReview,
		onSuccess: () => queryClient.invalidateQueries({ queryKey: planningKeys.all }),
	});
}

// Intention Streaks

export function useIntentionStreaks() {
	return useQuery({
		queryKey: planningKeys.intentionStreaks(),
		queryFn: fetchIntentionStreaks,
		staleTime: 60_000,
	});
}
