/**
 * Session Entity - public API
 *
 * This entity represents a work session (beat) in the time tracking system.
 * Following FSD conventions, this module exports:
 * - Model: types, domain logic, mappers
 * - API: data fetching hooks and functions
 * - UI: presentational components
 */

// API layer
export {
	calculateDailySummary,
	fetchBeats,
	sessionKeys,
	updateBeat,
	useAllBeats,
	useAllCurrentWeekSessions,
	useAllTags,
	useDailyRhythm,
	useHeatmap,
	useLastWeekTotal,
	useProjectBreakdown,
	useRecentSessions,
	useSessions,
	useStreaks,
	useThisWeekSessions,
	useTodaySessions,
	useUpdateSession,
	useWeeklySessionsByProject,
} from "./api";
// Model layer
export type {
	DayProjectBreakdown,
	DayProjectSegment,
	DaySummary,
	ProjectOption,
	Session,
} from "./model";
export { calculateDuration, toApiBeat, toSession } from "./model";

// UI layer
export { DailySummaryGrid, SessionCard, SessionEditForm } from "./ui";
