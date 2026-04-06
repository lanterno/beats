/**
 * Session API Functions
 * Low-level API calls for sessions (beats).
 */
import { get, put, ApiBeatListSchema, parseApiResponse } from "@/shared/api";
import type { ApiBeat } from "@/shared/api";

/**
 * Fetch all beats, optionally filtered by project
 */
export async function fetchBeats(projectId?: string): Promise<ApiBeat[]> {
  const url = projectId ? `/api/beats/?project_id=${projectId}` : "/api/beats/";
  const data = await get<unknown>(url);
  return parseApiResponse(ApiBeatListSchema, data);
}

/**
 * Update a beat (work session)
 */
export async function updateBeat(beat: ApiBeat): Promise<void> {
  await put<void>("/api/beats/", beat);
}
