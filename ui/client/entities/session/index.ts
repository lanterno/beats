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
export type { DriftEvent } from "./api";
export {
	calculateDailySummary,
	deleteBeat,
	fetchBeats,
	fetchRecentDrift,
	sessionKeys,
	updateBeat,
	useAllBeats,
	useAllCurrentWeekSessions,
	useAllTags,
	useDailyRhythm,
	useDeleteSession,
	useFlowWindows,
	useFlowWindowsLastDays,
	useFlowWindowsSummary,
	useGaps,
	useHeatmap,
	useLastWeekTotal,
	useProjectBreakdown,
	useRecentDrift,
	useSessions,
	useStreaks,
	useThisWeekSessions,
	useTodaySessions,
	useUpdateSession,
	useWeeklyFlowTrend,
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
export { toApiBeat, toSession } from "./model";

// UI layer
export { SessionEditForm } from "./ui";
