/**
 * Coach TanStack Query hooks — briefs and usage.
 * Chat uses a custom SSE hook, not TanStack Query.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
	deleteCoachData,
	deleteMemory,
	fetchBriefHistory,
	fetchMemory,
	fetchTodayBrief,
	fetchUsage,
	generateBrief,
	rewriteMemory,
} from "./coachApi";

export const coachKeys = {
	all: ["coach"] as const,
	brief: () => [...coachKeys.all, "brief"] as const,
	briefHistory: (limit: number) => [...coachKeys.all, "brief-history", limit] as const,
	usage: (days: number) => [...coachKeys.all, "usage", days] as const,
	memory: () => [...coachKeys.all, "memory"] as const,
};

export function useCoachBrief() {
	return useQuery({
		queryKey: coachKeys.brief(),
		queryFn: fetchTodayBrief,
		staleTime: 5 * 60_000,
	});
}

export function useCoachBriefHistory(limit = 14) {
	return useQuery({
		queryKey: coachKeys.briefHistory(limit),
		queryFn: () => fetchBriefHistory(limit),
		staleTime: 10 * 60_000,
	});
}

export function useGenerateBrief() {
	const queryClient = useQueryClient();
	return useMutation({
		mutationFn: (date?: string) => generateBrief(date),
		onSuccess: (data) => {
			// Seed today's brief from the returned doc (whose date is the exact
			// storage key) rather than refetching /brief/today — a refetch could
			// key to the next local day if the clock crosses midnight in between.
			queryClient.setQueryData(coachKeys.brief(), data);
			queryClient.invalidateQueries({ queryKey: coachKeys.briefHistory(14) });
		},
	});
}

export function useCoachUsage(days = 30) {
	return useQuery({
		queryKey: coachKeys.usage(days),
		queryFn: () => fetchUsage(days),
		staleTime: 5 * 60_000,
	});
}

export function useCoachMemory() {
	return useQuery({
		queryKey: coachKeys.memory(),
		queryFn: fetchMemory,
		staleTime: 10 * 60_000,
	});
}

export function useRewriteMemory() {
	const queryClient = useQueryClient();
	return useMutation({
		mutationFn: () => rewriteMemory(),
		onSuccess: () => queryClient.invalidateQueries({ queryKey: coachKeys.memory() }),
	});
}

export function useDeleteMemory() {
	const queryClient = useQueryClient();
	return useMutation({
		mutationFn: () => deleteMemory(),
		onSuccess: () => queryClient.invalidateQueries({ queryKey: coachKeys.memory() }),
	});
}

/**
 * Wipe all coach data. Invalidates the entire coach query tree so memory,
 * briefs, reviews, and usage all refetch as empty.
 */
export function useDeleteCoachData() {
	const queryClient = useQueryClient();
	return useMutation({
		mutationFn: () => deleteCoachData(),
		onSuccess: () => queryClient.invalidateQueries({ queryKey: coachKeys.all }),
	});
}
