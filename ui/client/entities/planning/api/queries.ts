/**
 * Planning TanStack Query hooks
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
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
	const qc = useQueryClient();
	return useMutation({
		mutationFn: (args: { projectId: string; plannedMinutes: number; date?: string }) =>
			createIntention(args.projectId, args.plannedMinutes, args.date),
		onSuccess: () => qc.invalidateQueries({ queryKey: planningKeys.all }),
	});
}

export function useUpdateIntention() {
	const qc = useQueryClient();
	return useMutation({
		mutationFn: (args: {
			intentionId: string;
			updates: { completed?: boolean; planned_minutes?: number };
		}) => updateIntention(args.intentionId, args.updates),
		onSuccess: () => qc.invalidateQueries({ queryKey: planningKeys.all }),
	});
}

export function useDeleteIntention() {
	const qc = useQueryClient();
	return useMutation({
		mutationFn: (intentionId: string) => deleteIntention(intentionId),
		onSuccess: () => qc.invalidateQueries({ queryKey: planningKeys.all }),
	});
}

export function useDailyNote(date?: string) {
	return useQuery({
		queryKey: planningKeys.dailyNote(date),
		queryFn: () => fetchDailyNote(date),
	});
}

export function useUpsertDailyNote() {
	const qc = useQueryClient();
	return useMutation({
		mutationFn: (args: { note: string; mood?: number; date?: string }) =>
			upsertDailyNote(args.note, args.mood, args.date),
		onSuccess: () => qc.invalidateQueries({ queryKey: planningKeys.all }),
	});
}

// Weekly Plans

export function useWeeklyPlan(weekOf: string) {
	return useQuery({
		queryKey: planningKeys.weeklyPlan(weekOf),
		queryFn: () => fetchWeeklyPlan(weekOf),
	});
}

export function useUpsertWeeklyPlan() {
	const qc = useQueryClient();
	return useMutation({
		mutationFn: (args: {
			weekOf: string;
			budgets: Array<{ project_id: string; planned_hours: number }>;
		}) => upsertWeeklyPlan(args.weekOf, args.budgets),
		onSuccess: () => qc.invalidateQueries({ queryKey: planningKeys.all }),
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
	const qc = useQueryClient();
	return useMutation({
		mutationFn: createRecurringIntention,
		onSuccess: () => qc.invalidateQueries({ queryKey: planningKeys.all }),
	});
}

export function useDeleteRecurringIntention() {
	const qc = useQueryClient();
	return useMutation({
		mutationFn: deleteRecurringIntention,
		onSuccess: () => qc.invalidateQueries({ queryKey: planningKeys.all }),
	});
}

export function useApplyRecurring() {
	const qc = useQueryClient();
	return useMutation({
		mutationFn: applyRecurringIntentions,
		onSuccess: () => qc.invalidateQueries({ queryKey: planningKeys.all }),
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
	const qc = useQueryClient();
	return useMutation({
		mutationFn: upsertWeeklyReview,
		onSuccess: () => qc.invalidateQueries({ queryKey: planningKeys.all }),
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
