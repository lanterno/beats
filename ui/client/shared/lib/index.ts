/**
 * Shared library utilities - public API
 */

// Class name utility
export { cn } from "./cn";

// Date utilities
export {
  parseUtcIso,
  formatDate,
  formatTime,
  toLocalDatetimeLocalString,
  getCurrentWeekRange,
  getWeekRange,
  getDayName,
  formatDateShort,
  getMondayOfWeeksAgo,
  getWeekNumberLabel,
} from "./date";

// Format utilities
export {
  formatDuration,
  calculateDurationMinutes,
  parseTimedeltaToMinutes,
  formatSecondsToTime,
} from "./format";

// Hooks
export { useFavicon } from "./useFavicon";
export { useKeyboardShortcuts } from "./useKeyboardShortcuts";
export { useInstallPrompt } from "./useInstallPrompt";
export { useOnlineStatus } from "./useOnlineStatus";
export { useTimerNotification } from "./useTimerNotification";
