/**
 * Session API layer - public API
 */

// Low-level API functions
export { fetchBeats, updateBeat } from "./sessionApi";

// TanStack Query hooks
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
} from "./queries";
