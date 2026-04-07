/**
 * Session Entity - public API
 *
 * This entity represents a work session (beat) in the time tracking system.
 * Following FSD conventions, this module exports:
 * - Model: types, domain logic, mappers
 * - API: data fetching hooks and functions
 * - UI: presentational components
 */

// Model layer
export type { Session, DaySummary, DayProjectBreakdown, DayProjectSegment, ProjectOption } from "./model";
export { toSession, toApiBeat, calculateDuration } from "./model";

// API layer
export {
  sessionKeys,
  useSessions,
  useUpdateSession,
  useAllCurrentWeekSessions,
  useWeeklySessionsByProject,
  useRecentSessions,
  useTodaySessions,
  useThisWeekSessions,
  useHeatmap,
  useDailyRhythm,
  useStreaks,
  useLastWeekTotal,
  useProjectBreakdown,
  useAllTags,
  calculateDailySummary,
  fetchBeats,
  updateBeat,
} from "./api";

// UI layer
export { SessionCard, SessionEditForm, DailySummaryGrid } from "./ui";
