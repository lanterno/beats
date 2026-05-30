/**
 * Project model - public API
 */

// Color utilities
export { assignColor } from "./colors";
// Mappers
export { toProject } from "./mappers";
// Selectors
export {
	extractCategories,
	isVisibleProject,
	partitionByArchived,
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
