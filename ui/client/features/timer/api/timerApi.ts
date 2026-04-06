/**
 * Timer API Functions
 * Low-level API calls for timer operations.
 */
import { get, post, TimerStatusSchema, parseApiResponse } from "@/shared/api";
import type { TimerStatus } from "@/shared/api";

/**
 * Fetch current timer status
 */
export async function fetchTimerStatus(): Promise<TimerStatus> {
  const data = await get<unknown>("/api/timer/status");
  return parseApiResponse(TimerStatusSchema, data);
}

/**
 * Start timer for a project
 */
export async function startTimerApi(projectId: string, startTime: string): Promise<void> {
  await post<void>(`/api/projects/${projectId}/start`, { time: startTime });
}

/**
 * Stop the current timer
 */
export async function stopTimerApi(stopTime: string): Promise<void> {
  await post<void>("/api/projects/stop", { time: stopTime });
}
