/**
 * Coach TanStack Query hooks — briefs and usage.
 * Chat uses a custom SSE hook, not TanStack Query.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchBriefHistory, fetchTodayBrief, fetchUsage, generateBrief } from "./coachApi";

export const coachKeys = {
	all: ["coach"] as const,
	brief: () => [...coachKeys.all, "brief"] as const,
	briefHistory: (limit: number) => [...coachKeys.all, "brief-history", limit] as const,
	usage: (days: number) => [...coachKeys.all, "usage", days] as const,
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
	const qc = useQueryClient();
	return useMutation({
		mutationFn: (date?: string) => generateBrief(date),
		onSuccess: () => {
			qc.invalidateQueries({ queryKey: coachKeys.brief() });
			qc.invalidateQueries({ queryKey: coachKeys.briefHistory(14) });
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
