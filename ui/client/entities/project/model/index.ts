/**
 * Project model - public API
 */

// Color utilities
export { assignColor } from "./colors";
// Mappers
export { toProject } from "./mappers";
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
	DailySummary,
	GoalOverride,
	Project,
	ProjectWithDuration,
	WeekHours,
} from "./types";
