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
} from "./queries";
// Low-level API functions
export { fetchBeats, updateBeat } from "./sessionApi";
