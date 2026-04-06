/**
 * Planning API Functions
 * Low-level API calls for intentions and daily notes.
 */
import {
  get,
  post,
  put,
  patch,
  del,
  IntentionListSchema,
  DailyNoteSchema,
  parseApiResponse,
} from "@/shared/api";
import type { Intention, DailyNote } from "@/shared/api";

// Intentions

export async function fetchIntentions(date?: string): Promise<Intention[]> {
  const params = date ? `?target_date=${date}` : "";
  const data = await get<unknown>(`/api/intentions${params}`);
  return parseApiResponse(IntentionListSchema, data);
}

export async function createIntention(
  projectId: string,
  plannedMinutes: number,
  date?: string
): Promise<Intention> {
  const body: Record<string, unknown> = {
    project_id: projectId,
    planned_minutes: plannedMinutes,
  };
  if (date) body.date = date;
  const data = await post<unknown>("/api/intentions", body);
  return parseApiResponse(DailyNoteSchema.passthrough(), data) as unknown as Intention;
}

export async function updateIntention(
  intentionId: string,
  updates: { completed?: boolean; planned_minutes?: number }
): Promise<void> {
  await patch<void>(`/api/intentions/${intentionId}`, updates);
}

export async function deleteIntention(intentionId: string): Promise<void> {
  await del<void>(`/api/intentions/${intentionId}`);
}

// Daily Notes

export async function fetchDailyNote(date?: string): Promise<DailyNote | null> {
  const params = date ? `?target_date=${date}` : "";
  const data = await get<unknown>(`/api/daily-notes${params}`);
  if (!data) return null;
  return parseApiResponse(DailyNoteSchema, data);
}

export async function upsertDailyNote(
  note: string,
  mood?: number,
  date?: string
): Promise<DailyNote> {
  const body: Record<string, unknown> = { note };
  if (mood !== undefined) body.mood = mood;
  if (date) body.date = date;
  const data = await put<unknown>("/api/daily-notes", body);
  return parseApiResponse(DailyNoteSchema, data);
}
