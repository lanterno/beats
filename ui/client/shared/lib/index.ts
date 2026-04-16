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
export { useFavicon } from "./useFavicon";
export { useInstallPrompt } from "./useInstallPrompt";
export { useKeyboardShortcuts } from "./useKeyboardShortcuts";
export { notifySyncWork, type SyncSnapshot, useSyncEngine, useSyncStatus } from "./useSyncEngine";
export type { Density, ThemeName } from "./useTheme";
export { DENSITIES, THEMES, useTheme } from "./useTheme";
export { useTimerNotification } from "./useTimerNotification";
