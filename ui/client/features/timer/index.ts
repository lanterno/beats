/**
 * Timer Feature - public API
 *
 * This feature handles timer functionality for tracking work sessions.
 * Following FSD conventions, this module exports:
 * - Model: state management hook and types
 * - API: timer API functions
 * - UI: timer-related components
 */

// API layer
export { fetchTimerStatus, startTimerApi, stopTimerApi } from "./api";
// Model layer
export type { TimerState, TimerStatus } from "./model";
export { useTimer } from "./model";

// UI layer
export { ProjectSelector, TimerDisplay, TimerManager } from "./ui";
