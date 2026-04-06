/**
 * Shared API layer - public API
 */

// API client and error handling
export { apiClient, get, post, put, patch, del, ApiError } from "./client";

// Zod schemas for validation
export {
  ApiProjectSchema,
  ApiBeatSchema,
  TimerStatusSchema,
  WeekBreakdownSchema,
  ProjectTotalSchema,
  ApiProjectListSchema,
  ApiBeatListSchema,
  HeatmapDayListSchema,
  RhythmSlotListSchema,
  IntentionSchema,
  IntentionListSchema,
  DailyNoteSchema,
  parseApiResponse,
  safeParseApiResponse,
} from "./schemas";

// Re-export types
export type {
  ApiProject,
  ApiBeat,
  TimerStatus,
  WeekBreakdown,
  ProjectTotal,
  HeatmapDay,
  RhythmSlot,
  Intention,
  DailyNote,
} from "./schemas";
