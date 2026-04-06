/**
 * Formatting utilities for display
 */
import { parseUtcIso } from "./date";

/**
 * Format duration in minutes to a human-readable string
 * @param minutes - Duration in minutes
 * @returns Formatted string like "2h 30m" or "45m"
 */
export function formatDuration(minutes: number): string {
  const mins = minutes || 0;
  const hours = Math.floor(mins / 60);
  const remainingMins = mins % 60;
  if (hours === 0) return `${remainingMins.toFixed(2)}m`;
  if (remainingMins === 0) return `${hours}h`;
  return `${hours}h ${remainingMins.toFixed(2)}m`;
}

/**
 * Calculate duration in minutes between two ISO datetime strings
 */
export function calculateDurationMinutes(startTime: string, endTime: string): number {
  const start = parseUtcIso(startTime);
  const end = parseUtcIso(endTime);
  return Math.max(0, (end.getTime() - start.getTime()) / 1000 / 60);
}

/**
 * Parse a Python timedelta string to minutes.
 * Handles "H:MM:SS", "M:SS", "N day(s), H:MM:SS".
 */
export function parseTimedeltaToMinutes(str: string): number {
  if (!str || typeof str !== "string") return 0;
  let totalSeconds = 0;
  let remaining = str;

  const dayMatch = remaining.match(/^(\d+)\s+days?\s*,?\s*/i);
  if (dayMatch) {
    totalSeconds += parseInt(dayMatch[1], 10) * 86400;
    remaining = remaining.slice(dayMatch[0].length).trim();
  }

  const parts = remaining.split(":");
  if (parts.length >= 3) {
    totalSeconds +=
      (parseInt(parts[0], 10) || 0) * 3600 +
      (parseInt(parts[1], 10) || 0) * 60 +
      (parseFloat(parts[2]) || 0);
  } else if (parts.length === 2) {
    totalSeconds += (parseInt(parts[0], 10) || 0) * 60 + (parseFloat(parts[1]) || 0);
  }

  return totalSeconds / 60;
}

/**
 * Format seconds to HH:MM:SS display
 */
export function formatSecondsToTime(totalSeconds: number): string {
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  return [hours, minutes, seconds].map((val) => String(val).padStart(2, "0")).join(":");
}
