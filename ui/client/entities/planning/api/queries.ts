/**
 * Planning TanStack Query hooks
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
	createIntention,
	deleteIntention,
	fetchDailyNote,
	fetchIntentions,
	updateIntention,
	upsertDailyNote,
} from "./planningApi";

export const planningKeys = {
	all: ["planning"] as const,
	intentions: (date?: string) => [...planningKeys.all, "intentions", date] as const,
	dailyNote: (date?: string) => [...planningKeys.all, "daily-note", date] as const,
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
