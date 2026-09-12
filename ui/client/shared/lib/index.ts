// Bundle labels (generated table — see scripts/gen_app_labels.py)
export { shortBundleLabel } from "./bundleLabel";
// Class name utility
export { cn } from "./cn";
// Date utilities
export {
	browserTimeZone,
	formatDate,
	formatDateOnly,
	formatDateShort,
	formatTime,
	getCurrentWeekRange,
	getDayName,
	getMondayOfWeeksAgo,
	getWeekNumberLabel,
	getWeekRange,
	parseIsoDate,
	parseUtcIso,
	startOfDay,
	todayIso,
	toIsoDate,
	toLocalDatetimeLocalString,
} from "./date";
// Authenticated file download
export { downloadFile } from "./downloadFile";
// Flow-window aggregation (insights)
export {
	aggregateFlowBy,
	aggregateFlowByDay,
	aggregateFlowByHour,
	aggregateFlowByRepo,
	aggregateFlowByWeekday,
	type DailyFlow,
	type FlowGroupStat,
	type FlowSummary,
	flowBaseline,
	type HourlyFlow,
	localDateKey,
	type RepoStat,
	shortRepoPath,
	summarizeFlow,
	type WeekdayFlow,
} from "./flowAggregation";
// Format utilities
export {
	calculateDurationMinutes,
	formatDuration,
	formatSecondsToTime,
	isValidTimeRange,
	parseTimedeltaToMinutes,
} from "./format";
// Fuzzy matching (command palette)
export { fuzzyRank } from "./fuzzyMatch";
// Offline mutation queue
export {
	drainPending,
	enqueueMutation,
	type HttpMethod,
	newClientId,
	type PendingMutation,
} from "./mutationQueue";
// Hooks
export { type CommandContext, useCommandActions } from "./useCommandActions";
export { useFavicon } from "./useFavicon";
export { useInstallPrompt } from "./useInstallPrompt";
export { useKeyboardShortcuts } from "./useKeyboardShortcuts";
export { useOAuthCallback } from "./useOAuthCallback";
export { notifySyncWork, type SyncSnapshot, useSyncEngine, useSyncStatus } from "./useSyncEngine";
export type { ColorMode, Density, ThemeName } from "./useTheme";
export { COLOR_MODES, DENSITIES, THEMES, useTheme } from "./useTheme";
export { useTimerNotification } from "./useTimerNotification";
export { useUrlParam } from "./useUrlParam";
