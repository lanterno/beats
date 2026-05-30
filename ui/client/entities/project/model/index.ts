/**
 * Project model - public API
 */

// Color utilities
export { assignColor } from "./colors";
// Mappers
export { toProject } from "./mappers";
// Picker recents (user-scoped localStorage)
export { clearPickerRecents, readPickerRecents, recordPickerRecent } from "./pickerRecents";
// Selectors
export {
	extractCategories,
	type FilterAndRankOptions,
	filterAndRankProjects,
	isVisibleProject,
	partitionByArchived,
	type SearchField,
	visibleProjects,
} from "./selectors";
// Types
export type {
	DailySummary,
	GoalOverride,
	Project,
	ProjectWithDuration,
	WeekHours,
} from "./types";
