// Color utilities
export { assignColor, PROJECT_COLORS } from "./colors";
// Last year's company days, copied into the next
export { copyCompanyDays, describeCompanyDaysCopy, hasCompanyDaysIn } from "./companyHolidays";
// Contract arithmetic + labels
export {
	type BalanceTone,
	balanceIsFinal,
	balanceTone,
	contractGovernsWeek,
	describeBalance,
	describeTerm,
	displayTermOn,
	formatSignedHours,
	isTimeBased,
	isTimeBasedOn,
	MAX_BALANCE_HOURS,
	SCHEDULE_TYPE_LABELS,
	sortTerms,
	termHoursPerDay,
	termHoursPerWeek,
	termOn,
	toPercent,
} from "./contract";
// Contract form values ↔ domain
export {
	type ContractFieldErrors,
	type ContractFrameErrors,
	type ContractFrameValues,
	contractFieldErrors,
	contractFrameDefaults,
	contractFromForm,
	type TermFieldErrors,
	type TermFormValues,
	termFormDefaults,
	termFromForm,
	validateContractFrame,
	validateTerm,
} from "./contractForm";
// The goal in force on a Monday: a permanent override, else the project's own
export { permanentOverrideOn, type StandingGoal, standingGoalOn } from "./goalOverrides";
// The ledger's rows: rule rows, adjustment rows, the quiet collapse, CSV
export {
	type AdjustmentRow,
	describeLedgerNote,
	type LedgerRow,
	type LedgerWeekRow,
	ledgerCsv,
	ledgerRows,
	type QuietRow,
	type RuleRow,
	weekDelta,
} from "./ledger";
// Mappers
export {
	toApiContract,
	toContract,
	toContractWeek,
	toLedger,
	toProject,
	toVacationYear,
} from "./mappers";
// Picker recents (user-scoped localStorage)
export { readPickerRecents, recordPickerRecent } from "./pickerRecents";
// Project pins (user-scoped localStorage + custom-event sync)
export { usePinnedProjects } from "./pins";
// A region change: the dates marked not given it would bring into force
export { notGivenYears, revivedNotGiven } from "./regionChange";
// Selectors
export {
	extractCategories,
	type FilterAndRankOptions,
	filterAndRankProjects,
	partitionByArchived,
	type SearchField,
	sortProjectsForList,
	visibleProjects,
} from "./selectors";
// The standing: the sentence, the projection, the first week, the labels
export {
	halfDays,
	isFirstWeek,
	nominalLine,
	type Projection,
	projection,
	type StandingWeek,
	type WeekSentenceInput,
	weekLabel,
	weekNumber,
	weekRange,
	weekSentence,
} from "./standing";
// The monthly timesheet: the months offered, their labels, the file's name
export {
	type TimesheetMonth,
	timesheetFilename,
	timesheetMonthLabel,
	timesheetMonths,
} from "./timesheet";
// Types
export type {
	AdjustmentKind,
	CarryOver,
	CompanyHoliday,
	Contract,
	ContractDay,
	ContractDayAbsence,
	ContractTerm,
	ContractWeek,
	GoalOverride,
	Holiday,
	HolidayRegion,
	Ledger,
	LedgerAdjustment,
	LedgerNote,
	LedgerNoteKind,
	LedgerTotals,
	LedgerWeek,
	Project,
	ProjectKind,
	ProjectOrganisation,
	ProjectWithDuration,
	RegionHoliday,
	ScheduleType,
	VacationEntitlement,
	VacationYear,
} from "./types";
// The vacation entitlement in words
export { describeEntitlement, describeVacationYear, type VacationYearWords } from "./vacation";
// This-week figures for a list row: contract or personal goal
export { type WeekGoalView, weekGoalView } from "./weekGoal";
