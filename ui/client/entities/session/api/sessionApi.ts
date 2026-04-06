/**
 * Session API Functions
 * Low-level API calls for sessions (beats) and analytics.
 */
import {
  get,
  put,
  ApiBeatListSchema,
  HeatmapDayListSchema,
  RhythmSlotListSchema,
  parseApiResponse,
} from "@/shared/api";
import type { ApiBeat, HeatmapDay, RhythmSlot } from "@/shared/api";

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

/**
 * Fetch heatmap data for a given year, optionally filtered by project
 */
export async function fetchHeatmap(year: number, projectId?: string): Promise<HeatmapDay[]> {
  let url = `/api/analytics/heatmap?year=${year}`;
  if (projectId) url += `&project_id=${projectId}`;
  const data = await get<unknown>(url);
  return parseApiResponse(HeatmapDayListSchema, data);
}

/**
 * Fetch daily rhythm data for a given period, optionally filtered by project
 */
export async function fetchDailyRhythm(period: string, projectId?: string): Promise<RhythmSlot[]> {
  let url = `/api/analytics/rhythm?period=${period}`;
  if (projectId) url += `&project_id=${projectId}`;
  const data = await get<unknown>(url);
  return parseApiResponse(RhythmSlotListSchema, data);
}
