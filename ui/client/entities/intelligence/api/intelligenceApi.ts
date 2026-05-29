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
	Schemas,
	ScoreHistoryItem,
	Suggestion,
	WeeklyDigest,
} from "@/shared/api";

export type InboxResponse = Schemas["InboxResponse"];
export type InboxItem = Schemas["InboxItemResponse"];

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

/**
 * The browser's IANA timezone (e.g. "America/New_York"). Sent to tz-aware
 * intelligence endpoints so productivity/today/week bucketing follows the
 * user's local calendar rather than UTC.
 */
const browserTimeZone = (): string => Intl.DateTimeFormat().resolvedOptions().timeZone;

export async function fetchProductivityScore(): Promise<ProductivityScore> {
	const tz = encodeURIComponent(browserTimeZone());
	const data = await get<unknown>(`/api/intelligence/score?tz=${tz}`);
	return parseApiResponse(ProductivityScoreSchema, data);
}

export async function fetchScoreHistory(weeks = 8): Promise<ScoreHistoryItem[]> {
	const tz = encodeURIComponent(browserTimeZone());
	const data = await get<unknown>(`/api/intelligence/score/history?weeks=${weeks}&tz=${tz}`);
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
	const tz = encodeURIComponent(browserTimeZone());
	const url = weekOf
		? `/api/intelligence/digests/generate?week_of=${weekOf}&tz=${tz}`
		: `/api/intelligence/digests/generate?tz=${tz}`;
	const data = await post<unknown>(url, {});
	return parseApiResponse(WeeklyDigestSchema, data);
}

export async function fetchPatterns(): Promise<PatternsResponse> {
	const data = await get<unknown>("/api/intelligence/patterns");
	return parseApiResponse(PatternsResponseSchema, data);
}

export async function refreshPatterns(): Promise<PatternsResponse> {
	const tz = encodeURIComponent(browserTimeZone());
	const data = await post<unknown>(`/api/intelligence/patterns/refresh?tz=${tz}`, {});
	return parseApiResponse(PatternsResponseSchema, data);
}

export async function dismissPattern(insightId: string): Promise<void> {
	await post<void>(`/api/intelligence/patterns/${insightId}/dismiss`, {});
}

export async function fetchSuggestions(date?: string): Promise<Suggestion[]> {
	const tz = encodeURIComponent(browserTimeZone());
	const url = date
		? `/api/intelligence/suggestions?date=${date}&tz=${tz}`
		: `/api/intelligence/suggestions?tz=${tz}`;
	const data = await get<unknown>(url);
	return parseApiResponse(SuggestionListSchema, data);
}

export async function fetchFocusScores(date?: string): Promise<FocusScore[]> {
	const tz = encodeURIComponent(browserTimeZone());
	const url = date
		? `/api/intelligence/focus-scores?date=${date}&tz=${tz}`
		: `/api/intelligence/focus-scores?tz=${tz}`;
	const data = await get<unknown>(url);
	return parseApiResponse(FocusScoreListSchema, data);
}

export async function fetchMoodCorrelation(): Promise<MoodCorrelation> {
	const tz = encodeURIComponent(browserTimeZone());
	const data = await get<unknown>(`/api/intelligence/mood?tz=${tz}`);
	return parseApiResponse(MoodCorrelationSchema, data);
}

export async function fetchEstimationAccuracy(): Promise<EstimationAccuracy[]> {
	const tz = encodeURIComponent(browserTimeZone());
	const data = await get<unknown>(`/api/intelligence/estimation?tz=${tz}`);
	return parseApiResponse(EstimationAccuracyListSchema, data);
}

export async function fetchProjectHealth(): Promise<ProjectHealth[]> {
	const tz = encodeURIComponent(browserTimeZone());
	const data = await get<unknown>(`/api/intelligence/project-health?tz=${tz}`);
	return parseApiResponse(ProjectHealthListSchema, data);
}

/**
 * Fetch the aggregated intelligence Inbox (patterns + suggestions + health alerts).
 * Uses the generated OpenAPI type directly — the server owns the shape contract.
 */
export async function fetchInbox(): Promise<InboxResponse> {
	const tz = encodeURIComponent(browserTimeZone());
	return get<InboxResponse>(`/api/intelligence/inbox?tz=${tz}`);
}
