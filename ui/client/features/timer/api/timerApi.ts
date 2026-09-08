/**
 * Timer API Functions
 * Low-level API calls for timer operations.
 */

import { z } from "zod";
import type { TimerStatus } from "@/shared/api";
import { get, parseApiResponse, TimerStatusSchema } from "@/shared/api";

const DailyAverageSchema = z.object({
	avg_minutes: z.number(),
	days_tracked: z.number(),
});

export async function fetchTimerStatus(): Promise<TimerStatus> {
	const data = await get<unknown>("/api/timer/status");
	return parseApiResponse(TimerStatusSchema, data);
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
