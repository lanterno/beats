/**
 * Timer Feature - public API
 *
 * This feature handles timer functionality for tracking work sessions.
 * Following FSD conventions, this module exports:
 * - Model: state management hook and types
 * - API: timer API functions
 *
 * The timer's UI is the sidebar's (`widgets/sidebar/SidebarTimer.tsx`).
 */

// API layer
export { fetchTimerStatus } from "./api";
// Model layer
export type { TimerState, TimerStatus } from "./model";
export { timerStatusKey, useTimer } from "./model";
