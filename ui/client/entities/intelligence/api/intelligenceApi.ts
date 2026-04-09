/**
 * Intelligence API Functions
 * Low-level API calls for productivity scoring, patterns, digests, and suggestions.
 */

import type {
	EstimationAccuracy,
	FocusScore,
	MoodCorrelation,
	PatternsResponse,
	ProductivityScore,
	ProjectHealth,
	ScoreHistoryItem,
	Suggestion,
	WeeklyDigest,
} from "@/shared/api";
import {
	EstimationAccuracyListSchema,
	FocusScoreListSchema,
	get,
	MoodCorrelationSchema,
	PatternsResponseSchema,
	ProductivityScoreSchema,
	ProjectHealthListSchema,
	parseApiResponse,
	post,
	ScoreHistorySchema,
	SuggestionListSchema,
	WeeklyDigestListSchema,
	WeeklyDigestSchema,
} from "@/shared/api";

export async function fetchProductivityScore(): Promise<ProductivityScore> {
	const data = await get<unknown>("/api/intelligence/score");
	return parseApiResponse(ProductivityScoreSchema, data);
}

export async function fetchScoreHistory(weeks = 8): Promise<ScoreHistoryItem[]> {
	const data = await get<unknown>(`/api/intelligence/score/history?weeks=${weeks}`);
	return parseApiResponse(ScoreHistorySchema, data);
}

export async function fetchDigests(limit = 12): Promise<WeeklyDigest[]> {
	const data = await get<unknown>(`/api/intelligence/digests?limit=${limit}`);
	return parseApiResponse(WeeklyDigestListSchema, data);
}

export async function fetchDigest(weekOf: string): Promise<WeeklyDigest> {
	const data = await get<unknown>(`/api/intelligence/digests/${weekOf}`);
	return parseApiResponse(WeeklyDigestSchema, data);
}

export async function generateDigest(weekOf?: string): Promise<WeeklyDigest> {
	const url = weekOf
		? `/api/intelligence/digests/generate?week_of=${weekOf}`
		: "/api/intelligence/digests/generate";
	const data = await post<unknown>(url, {});
	return parseApiResponse(WeeklyDigestSchema, data);
}

export async function fetchPatterns(): Promise<PatternsResponse> {
	const data = await get<unknown>("/api/intelligence/patterns");
	return parseApiResponse(PatternsResponseSchema, data);
}

export async function refreshPatterns(): Promise<PatternsResponse> {
	const data = await post<unknown>("/api/intelligence/patterns/refresh", {});
	return parseApiResponse(PatternsResponseSchema, data);
}

export async function dismissPattern(insightId: string): Promise<void> {
	await post<void>(`/api/intelligence/patterns/${insightId}/dismiss`, {});
}

export async function fetchSuggestions(date?: string): Promise<Suggestion[]> {
	const url = date ? `/api/intelligence/suggestions?date=${date}` : "/api/intelligence/suggestions";
	const data = await get<unknown>(url);
	return parseApiResponse(SuggestionListSchema, data);
}

export async function fetchFocusScores(date?: string): Promise<FocusScore[]> {
	const url = date
		? `/api/intelligence/focus-scores?date=${date}`
		: "/api/intelligence/focus-scores";
	const data = await get<unknown>(url);
	return parseApiResponse(FocusScoreListSchema, data);
}

export async function fetchMoodCorrelation(): Promise<MoodCorrelation> {
	const data = await get<unknown>("/api/intelligence/mood");
	return parseApiResponse(MoodCorrelationSchema, data);
}

export async function fetchEstimationAccuracy(): Promise<EstimationAccuracy[]> {
	const data = await get<unknown>("/api/intelligence/estimation");
	return parseApiResponse(EstimationAccuracyListSchema, data);
}

export async function fetchProjectHealth(): Promise<ProjectHealth[]> {
	const data = await get<unknown>("/api/intelligence/project-health");
	return parseApiResponse(ProjectHealthListSchema, data);
}
