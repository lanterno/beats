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
	HeatmapDay,
	Intention,
	ProjectTotal,
	RhythmSlot,
	TimerStatus,
	WeekBreakdown,
} from "./schemas";
// Zod schemas for validation
export {
	ApiBeatListSchema,
	ApiBeatSchema,
	ApiProjectListSchema,
	ApiProjectSchema,
	DailyNoteSchema,
	HeatmapDayListSchema,
	IntentionListSchema,
	IntentionSchema,
	ProjectTotalSchema,
	parseApiResponse,
	RhythmSlotListSchema,
	safeParseApiResponse,
	TimerStatusSchema,
	WeekBreakdownSchema,
} from "./schemas";
