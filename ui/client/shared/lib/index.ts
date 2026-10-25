// Bundle labels (generated table — see scripts/gen_app_labels.py)
export { shortBundleLabel } from "./bundleLabel";
// Class name utility
export { cn } from "./cn";
// Date utilities
export {
	addIsoDays,
	browserTimeZone,
	earlierIso,
	formatDate,
	formatDateOnly,
	formatDateShort,
	formatTime,
	getCurrentWeekRange,
	getDayName,
	getISOWeek,
	getMondayOfWeeksAgo,
	getWeekRange,
	laterIso,
	mondayOfIso,
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
	hoursText,
	isValidTimeRange,
} from "./format";
// Fuzzy matching (command palette)
export { fuzzyRank } from "./fuzzyMatch";
// Money: integer minor units shown, and a typed rate, budget or hours read
export {
	BILLING_BUDGET_MINOR_MAX,
	formatMoney,
	formatRate,
	minorToInput,
	type ParsedHours,
	type ParsedMoney,
	parseHours,
	parseMoney,
	RATE_MINOR_MAX,
} from "./money";
// Offline mutation queue
export type {
	HttpMethod,
	PendingMutation,
} from "./mutationQueue";
export { rememberReturnTo, takeReturnTo } from "./returnTo";
// Hooks
export { type CommandContext, useCommandActions } from "./useCommandActions";
export { useFavicon } from "./useFavicon";
export { useInstallPrompt } from "./useInstallPrompt";
export { useKeyboardShortcuts } from "./useKeyboardShortcuts";
export { useNow } from "./useNow";
export { useOAuthCallback } from "./useOAuthCallback";
export { notifySyncWork, type SyncSnapshot, useSyncEngine, useSyncStatus } from "./useSyncEngine";
export type { Density, ThemeName } from "./useTheme";
export { DENSITIES, THEMES, useTheme } from "./useTheme";
export { useTimerNotification } from "./useTimerNotification";
export { useUrlParam } from "./useUrlParam";
