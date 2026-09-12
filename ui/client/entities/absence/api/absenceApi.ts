/**
 * Absence API Functions
 * Under /api/projects/{id}/absences — an absence belongs to a day job.
 */

import {
	ApiAbsenceListSchema,
	ApiAbsenceSchema,
	del,
	get,
	parseApiResponse,
	post,
} from "@/shared/api";
import { browserTimeZone } from "@/shared/lib";
import type { Absence, AbsenceType } from "../model";
import { toAbsence } from "../model";

export interface AbsenceRange {
	start: string; // YYYY-MM-DD, inclusive
	end: string; // YYYY-MM-DD, inclusive
}

export async function fetchAbsences(projectId: string, range: AbsenceRange): Promise<Absence[]> {
	const params = new URLSearchParams({ start: range.start, end: range.end, tz: browserTimeZone() });
	const data = await get<unknown>(`/api/projects/${projectId}/absences?${params.toString()}`);
	return parseApiResponse(ApiAbsenceListSchema, data).map(toAbsence);
}

export interface AbsenceInput {
	date: string; // YYYY-MM-DD
	type: AbsenceType;
	halfDay?: boolean;
	note?: string;
}

/**
 * Record an absence. One per date: posting again for a date the project
 * already has one on replaces it (a half day becoming a full one, a
 * vacation becoming sick leave) and still answers 201.
 */
export async function recordAbsence(projectId: string, input: AbsenceInput): Promise<Absence> {
	const data = await post<unknown>(`/api/projects/${projectId}/absences`, {
		date: input.date,
		type: input.type,
		half_day: input.halfDay ?? false,
		note: input.note?.trim() ? input.note.trim() : null,
	});
	return toAbsence(parseApiResponse(ApiAbsenceSchema, data));
}

export async function deleteAbsence(projectId: string, absenceId: string): Promise<void> {
	await del<void>(`/api/projects/${projectId}/absences/${absenceId}`);
}
