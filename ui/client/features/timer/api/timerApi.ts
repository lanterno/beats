/**
 * Timer API Functions
 * Low-level API calls for timer operations.
 */

import type { TimerStatus } from "@/shared/api";
import { get, parseApiResponse, TimerStatusSchema } from "@/shared/api";

export async function fetchTimerStatus(): Promise<TimerStatus> {
	const data = await get<unknown>("/api/timer/status");
	return parseApiResponse(TimerStatusSchema, data);
}
