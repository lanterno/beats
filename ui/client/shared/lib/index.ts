/**
 * Shared library utilities - public API
 */

// Class name utility
export { cn } from "./cn";
// Date utilities
export {
	formatDate,
	formatDateShort,
	formatTime,
	getCurrentWeekRange,
	getDayName,
	getMondayOfWeeksAgo,
	getWeekNumberLabel,
	getWeekRange,
	parseUtcIso,
	startOfDay,
	toLocalDatetimeLocalString,
} from "./date";
// Format utilities
export {
	calculateDurationMinutes,
	formatDuration,
	formatSecondsToTime,
	parseTimedeltaToMinutes,
} from "./format";
// Fuzzy matching (command palette)
export { fuzzyRank, score as fuzzyScore } from "./fuzzyMatch";

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
export { useCountUp } from "./useCountUp";
export { useFavicon } from "./useFavicon";
export { useInstallPrompt } from "./useInstallPrompt";
export { useKeyboardShortcuts } from "./useKeyboardShortcuts";
export { useOAuthCallback } from "./useOAuthCallback";
export { notifySyncWork, type SyncSnapshot, useSyncEngine, useSyncStatus } from "./useSyncEngine";
export type { ColorMode, Density, ThemeName } from "./useTheme";
export { COLOR_MODES, DENSITIES, THEMES, useTheme } from "./useTheme";
export { useTimerNotification } from "./useTimerNotification";
