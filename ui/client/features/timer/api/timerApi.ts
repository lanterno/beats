/**
 * Timer API Functions
 * Low-level API calls for timer operations.
 */

import { z } from "zod";
import type { TimerStatus } from "@/shared/api";
import { get, parseApiResponse, post, TimerStatusSchema } from "@/shared/api";

const DailyAverageSchema = z.object({
	avg_minutes: z.number(),
	days_tracked: z.number(),
});

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

/**
 * Fetch average daily session time for a project (last 30 days)
 */
export async function fetchDailyAverage(
	projectId: string,
): Promise<{ avg_minutes: number; days_tracked: number }> {
	const data = await get<unknown>(`/api/projects/${projectId}/daily-average`);
	return parseApiResponse(DailyAverageSchema, data);
}
