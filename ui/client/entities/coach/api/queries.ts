/**
 * Coach TanStack Query hooks — briefs and usage.
 * Chat uses a custom SSE hook, not TanStack Query.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
	fetchBriefHistory,
	fetchMemory,
	fetchTodayBrief,
	fetchTodayReview,
	fetchUsage,
	generateBrief,
	rewriteMemory,
	startReview,
	submitReviewAnswer,
} from "./coachApi";

export const coachKeys = {
	all: ["coach"] as const,
	brief: () => [...coachKeys.all, "brief"] as const,
	briefHistory: (limit: number) => [...coachKeys.all, "brief-history", limit] as const,
	usage: (days: number) => [...coachKeys.all, "usage", days] as const,
	review: () => [...coachKeys.all, "review"] as const,
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

export function useCoachReview() {
	return useQuery({
		queryKey: coachKeys.review(),
		queryFn: fetchTodayReview,
		staleTime: 5 * 60_000,
	});
}

export function useStartReview() {
	const qc = useQueryClient();
	return useMutation({
		mutationFn: () => startReview(),
		onSuccess: () => qc.invalidateQueries({ queryKey: coachKeys.review() }),
	});
}

export function useSubmitReviewAnswer() {
	const qc = useQueryClient();
	return useMutation({
		mutationFn: (vars: { date: string; questionIndex: number; answer: string }) =>
			submitReviewAnswer(vars.date, vars.questionIndex, vars.answer),
		onSuccess: () => qc.invalidateQueries({ queryKey: coachKeys.review() }),
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
	const qc = useQueryClient();
	return useMutation({
		mutationFn: () => rewriteMemory(),
		onSuccess: () => qc.invalidateQueries({ queryKey: coachKeys.memory() }),
	});
}
