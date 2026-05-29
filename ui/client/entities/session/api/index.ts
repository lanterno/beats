/**
 * Session API layer - public API
 */

// TanStack Query hooks
export {
	calculateDailySummary,
	sessionKeys,
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
	useRecentSessions,
	useSessions,
	useStreaks,
	useThisWeekSessions,
	useTodaySessions,
	useUpdateSession,
	useWeeklyFlowTrend,
	useWeeklySessionsByProject,
} from "./queries";
// Low-level API functions
export {
	type DriftEvent,
	deleteBeat,
	fetchBeats,
	fetchRecentDrift,
	updateBeat,
} from "./sessionApi";
