/**
 * Intelligence TanStack Query Hooks
 * Data fetching with caching for intelligence features.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
	dismissPattern,
	fetchDigests,
	fetchEstimationAccuracy,
	fetchFocusScores,
	fetchMoodCorrelation,
	fetchPatterns,
	fetchProductivityScore,
	fetchProjectHealth,
	fetchScoreHistory,
	fetchSuggestions,
	generateDigest,
	refreshPatterns,
} from "./intelligenceApi";

/**
 * Query keys for intelligence data
 */
export const intelligenceKeys = {
	all: ["intelligence"] as const,
	score: () => [...intelligenceKeys.all, "score"] as const,
	scoreHistory: (weeks: number) => [...intelligenceKeys.all, "score-history", weeks] as const,
	digests: (limit: number) => [...intelligenceKeys.all, "digests", limit] as const,
	patterns: () => [...intelligenceKeys.all, "patterns"] as const,
	suggestions: (date?: string) =>
		[...intelligenceKeys.all, "suggestions", date ?? "today"] as const,
	focusScores: (date?: string) =>
		[...intelligenceKeys.all, "focus-scores", date ?? "today"] as const,
	mood: () => [...intelligenceKeys.all, "mood"] as const,
	estimation: () => [...intelligenceKeys.all, "estimation"] as const,
	projectHealth: () => [...intelligenceKeys.all, "project-health"] as const,
};

/**
 * Fetch current productivity score
 */
export function useProductivityScore() {
	return useQuery({
		queryKey: intelligenceKeys.score(),
		queryFn: fetchProductivityScore,
		staleTime: 5 * 60_000, // 5 minutes
	});
}

/**
 * Fetch weekly productivity score history for sparkline
 */
export function useScoreHistory(weeks = 8) {
	return useQuery({
		queryKey: intelligenceKeys.scoreHistory(weeks),
		queryFn: () => fetchScoreHistory(weeks),
		staleTime: 30 * 60_000, // 30 minutes
	});
}

/**
 * Fetch recent weekly digests
 */
export function useDigests(limit = 12) {
	return useQuery({
		queryKey: intelligenceKeys.digests(limit),
		queryFn: () => fetchDigests(limit),
		staleTime: 60 * 60_000, // 1 hour
	});
}

/**
 * Generate a weekly digest
 */
export function useGenerateDigest() {
	const queryClient = useQueryClient();

	return useMutation({
		mutationFn: (weekOf?: string) => generateDigest(weekOf),
		onSuccess: () => {
			queryClient.invalidateQueries({ queryKey: intelligenceKeys.digests(12) });
		},
	});
}

/**
 * Fetch cached pattern detection results
 */
export function usePatterns() {
	return useQuery({
		queryKey: intelligenceKeys.patterns(),
		queryFn: fetchPatterns,
		staleTime: 30 * 60_000, // 30 minutes
	});
}

/**
 * Refresh pattern detection
 */
export function useRefreshPatterns() {
	const queryClient = useQueryClient();

	return useMutation({
		mutationFn: refreshPatterns,
		onSuccess: (data) => {
			queryClient.setQueryData(intelligenceKeys.patterns(), data);
		},
	});
}

/**
 * Dismiss a pattern insight card
 */
export function useDismissPattern() {
	const queryClient = useQueryClient();

	return useMutation({
		mutationFn: dismissPattern,
		onSuccess: () => {
			queryClient.invalidateQueries({ queryKey: intelligenceKeys.patterns() });
		},
	});
}

/**
 * Fetch smart daily plan suggestions
 */
export function useSuggestions(date?: string) {
	return useQuery({
		queryKey: intelligenceKeys.suggestions(date),
		queryFn: () => fetchSuggestions(date),
		staleTime: 5 * 60_000, // 5 minutes
	});
}

/**
 * Fetch focus quality scores for a date
 */
export function useFocusScores(date?: string) {
	return useQuery({
		queryKey: intelligenceKeys.focusScores(date),
		queryFn: () => fetchFocusScores(date),
		staleTime: 5 * 60_000, // 5 minutes
	});
}

/**
 * Fetch mood-productivity correlation analysis
 */
export function useMoodCorrelation() {
	return useQuery({
		queryKey: intelligenceKeys.mood(),
		queryFn: fetchMoodCorrelation,
		staleTime: 60 * 60_000, // 1 hour
	});
}

/**
 * Fetch per-project estimation accuracy
 */
export function useEstimationAccuracy() {
	return useQuery({
		queryKey: intelligenceKeys.estimation(),
		queryFn: fetchEstimationAccuracy,
		staleTime: 60 * 60_000, // 1 hour
	});
}

/**
 * Fetch project health metrics
 */
export function useProjectHealth() {
	return useQuery({
		queryKey: intelligenceKeys.projectHealth(),
		queryFn: fetchProjectHealth,
		staleTime: 30 * 60_000, // 30 minutes
	});
}
