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

// Hooks
export { useFavicon } from "./useFavicon";
export { useInstallPrompt } from "./useInstallPrompt";
export { useKeyboardShortcuts } from "./useKeyboardShortcuts";
export { useOnlineStatus } from "./useOnlineStatus";
export type { Density, ThemeName } from "./useTheme";
export { DENSITIES, THEMES, useTheme } from "./useTheme";
export { useTimerNotification } from "./useTimerNotification";
