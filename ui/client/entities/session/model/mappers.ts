/**
 * Session Mappers
 * Convert between API types and domain types.
 */
import type { ApiBeat } from "@/shared/api";
import type { Session } from "./types";

/**
 * Convert API beat to domain Session
 */
export function toSession(beat: ApiBeat): Session {
	const startTime = new Date(beat.start);
	const endTime = beat.end ? new Date(beat.end) : new Date();
	const durationMinutes = (endTime.getTime() - startTime.getTime()) / 1000 / 60;

	return {
		id: beat.id || `beat_${Date.now()}`,
		projectId: beat.project_id || "",
		startTime: beat.start,
		endTime: beat.end || endTime.toISOString(),
		duration: durationMinutes,
		note: beat.note ?? undefined,
		tags: beat.tags ?? [],
	};
}

/**
 * Convert domain Session to API format
 */
export function toApiBeat(session: Session): ApiBeat {
	return {
		id: session.id,
		start: session.startTime,
		end: session.endTime,
		project_id: session.projectId,
		note: session.note ?? null,
		tags: session.tags ?? [],
	};
}

/**
 * Calculate duration in minutes between two times
 */
export function calculateDuration(startTime: string, endTime: string): number {
	const start = new Date(startTime);
	const end = new Date(endTime);
	return Math.max(0, (end.getTime() - start.getTime()) / 1000 / 60);
}
