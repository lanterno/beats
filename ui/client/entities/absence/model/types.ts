/**
 * Absence Domain Types
 * A day, or half of one, a day-job contract does not expect work on.
 */

/** Why a day was not worked. For the record and the calendar's colour; the arithmetic treats all three alike. */
export type AbsenceType = "vacation" | "sick" | "other";

export interface Absence {
	id: string;
	projectId: string;
	date: string; // YYYY-MM-DD
	halfDay: boolean;
	type: AbsenceType;
	note?: string;
}

export const ABSENCE_TYPE_LABELS: Record<AbsenceType, string> = {
	vacation: "Vacation",
	sick: "Sick",
	other: "Other",
};
