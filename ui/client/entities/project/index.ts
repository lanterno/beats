/**
 * Project Entity - public API
 *
 * This entity represents a project in the time tracking system.
 * Following FSD conventions, this module exports:
 * - Model: types, domain logic, mappers
 * - API: data fetching hooks and functions
 * - UI: presentational components
 */

// API layer
export {
	fetchProjects,
	fetchProjectTotal,
	fetchProjectWeek,
	projectKeys,
	useInvalidateProjects,
	useProject,
	useProjects,
	useProjectWeeks,
	useUpdateProject,
} from "./api";
// Model layer
export type {
	DailySummary,
	Project,
	ProjectWithDuration,
	WeekHours,
} from "./model";
export { assignColor, toProject } from "./model";

// UI layer
export { LoadingSpinner } from "./ui";
