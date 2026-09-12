/**
 * Absence Entity - public API
 *
 * A day, or half of one, a day-job contract does not expect work on
 * (docs/work-contracts-roadmap.md). One per (project, date); the API
 * upserts on date, so recording again on a day replaces what was there.
 */
export {
	type AbsenceInput,
	type AbsenceRange,
	absenceKeys,
	deleteAbsence,
	fetchAbsences,
	recordAbsence,
	useAbsences,
	useRecordAbsence,
	useRemoveAbsence,
} from "./api";
export { ABSENCE_TYPE_LABELS, type Absence, type AbsenceType, toAbsence } from "./model";
