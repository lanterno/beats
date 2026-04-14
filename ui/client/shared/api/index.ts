/**
 * Shared API layer - public API
 */

// API client and error handling
export { ApiError, apiClient, del, get, patch, post, put } from "./client";
// Re-export types
export type {
	ApiBeat,
	ApiGoalOverride,
	ApiProject,
	DailyNote,
	EstimationAccuracy,
	FocusScore,
	Gap,
	HeatmapDay,
	InsightCard,
	Intention,
	MoodCorrelation,
	PatternsResponse,
	ProductivityScore,
	ProjectHealth,
	ProjectTotal,
	RhythmSlot,
	ScoreHistoryItem,
	Suggestion,
	TimerStatus,
	WeekBreakdown,
	WeeklyDigest,
} from "./schemas";
// Zod schemas for validation
export {
	ApiBeatListSchema,
	ApiBeatSchema,
	ApiProjectListSchema,
	ApiProjectSchema,
	DailyNoteSchema,
	EstimationAccuracyListSchema,
	FocusScoreListSchema,
	GapListSchema,
	HeatmapDayListSchema,
	IntentionListSchema,
	IntentionSchema,
	MoodCorrelationSchema,
	PatternsResponseSchema,
	ProductivityScoreSchema,
	ProjectHealthListSchema,
	ProjectTotalSchema,
	parseApiResponse,
	RhythmSlotListSchema,
	ScoreHistorySchema,
	SuggestionListSchema,
	safeParseApiResponse,
	TimerStatusSchema,
	WeekBreakdownSchema,
	WeeklyDigestListSchema,
	WeeklyDigestSchema,
} from "./schemas";
