/**
 * Coach TanStack Query hooks — briefs and usage.
 * Chat uses a custom SSE hook, not TanStack Query.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
	type BriefRating,
	type BriefResponse,
	deleteCoachData,
	deleteMemory,
	fetchBriefHistory,
	fetchCoachStatus,
	fetchMemory,
	fetchTodayBrief,
	fetchUsage,
	generateBrief,
	rewriteMemory,
	setBriefFeedback,
} from "./coachApi";

const coachKeys = {
	all: ["coach"] as const,
	status: () => [...coachKeys.all, "status"] as const,
	brief: () => [...coachKeys.all, "brief"] as const,
	briefHistory: (limit: number) => [...coachKeys.all, "brief-history", limit] as const,
	usage: (days: number) => [...coachKeys.all, "usage", days] as const,
	memory: () => [...coachKeys.all, "memory"] as const,
};

/**
 * Whether the coach is set up on this server. Read once a session and kept:
 * it changes only with a deploy. Until it has answered, `configured` is
 * undefined, and a caller shows nothing of the coach rather than a flash of
 * it; an older API without the route reads as configured, as it always was.
 */
export function useCoachStatus(): { configured: boolean | undefined } {
	const query = useQuery({
		queryKey: coachKeys.status(),
		queryFn: fetchCoachStatus,
		staleTime: Number.POSITIVE_INFINITY,
		gcTime: Number.POSITIVE_INFINITY,
		retry: false,
	});
	if (query.isError) return { configured: true };
	return { configured: query.data?.configured };
}

export function useCoachBrief(options: { enabled?: boolean } = {}) {
	return useQuery({
		queryKey: coachKeys.brief(),
		queryFn: fetchTodayBrief,
		staleTime: 5 * 60_000,
		enabled: options.enabled ?? true,
	});
}

export function useCoachBriefHistory(limit = 14, options: { enabled?: boolean } = {}) {
	return useQuery({
		queryKey: coachKeys.briefHistory(limit),
		queryFn: () => fetchBriefHistory(limit),
		staleTime: 10 * 60_000,
		enabled: options.enabled ?? true,
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

export function useBriefFeedback() {
	const queryClient = useQueryClient();
	return useMutation({
		mutationFn: ({ date, rating }: { date: string; rating: BriefRating | null }) =>
			setBriefFeedback(date, rating),
		onSuccess: (data) => {
			// The rated brief may be today's, a past one in history, or both.
			queryClient.setQueryData<BriefResponse | null>(coachKeys.brief(), (old) =>
				old?.date === data.date ? data : old,
			);
			queryClient.setQueryData<BriefResponse[]>(coachKeys.briefHistory(14), (old) =>
				old?.map((b) => (b.date === data.date ? data : b)),
			);
		},
	});
}

export function useCoachUsage(days = 30, options: { enabled?: boolean } = {}) {
	return useQuery({
		queryKey: coachKeys.usage(days),
		queryFn: () => fetchUsage(days),
		staleTime: 5 * 60_000,
		enabled: options.enabled ?? true,
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
