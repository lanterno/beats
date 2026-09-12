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
// Mappers
export { toApiContract, toContract, toContractWeek, toProject } from "./mappers";
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
// Types
export type {
	Contract,
	ContractDay,
	ContractDayAbsence,
	ContractTerm,
	ContractWeek,
	DailySummary,
	GoalOverride,
	Holiday,
	HolidayRegion,
	Project,
	ProjectKind,
	ProjectWithDuration,
	ScheduleType,
	WeekHours,
} from "./types";
// This-week figures for a list row: contract or personal goal
export { type WeekGoalView, weekGoalView } from "./weekGoal";
