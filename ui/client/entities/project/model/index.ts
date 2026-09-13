// Color utilities
export { assignColor, PROJECT_COLORS } from "./colors";
// Contract arithmetic + labels
export {
	type BalanceTone,
	balanceTone,
	contractGovernsWeek,
	describeBalance,
	describeTerm,
	displayTermOn,
	formatSignedHours,
	fromPercent,
	isTimeBased,
	isTimeBasedOn,
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
// The ledger's rows: rule rows, the quiet collapse, CSV
export {
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
export { toApiContract, toContract, toContractWeek, toLedger, toProject } from "./mappers";
// Picker recents (user-scoped localStorage)
export { clearPickerRecents, readPickerRecents, recordPickerRecent } from "./pickerRecents";
// Project pins (user-scoped localStorage + custom-event sync)
export { clearPins, isPinned, readPins, togglePin, usePinnedProjects } from "./pins";
// Selectors
export {
	extractCategories,
	type FilterAndRankOptions,
	filterAndRankProjects,
	isVisibleProject,
	partitionByArchived,
	type SearchField,
	sortProjectsForList,
	visibleProjects,
} from "./selectors";
// The standing: the sentence, the projection, the first week, the labels
export {
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
// Types
export type {
	Contract,
	ContractDay,
	ContractDayAbsence,
	ContractTerm,
	ContractWeek,
	GoalOverride,
	Holiday,
	HolidayRegion,
	Ledger,
	LedgerNote,
	LedgerNoteKind,
	LedgerTotals,
	LedgerWeek,
	Project,
	ProjectKind,
	ProjectWithDuration,
	ScheduleType,
} from "./types";
// This-week figures for a list row: contract or personal goal
export { type WeekGoalView, weekGoalView } from "./weekGoal";
