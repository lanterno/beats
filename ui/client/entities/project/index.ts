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
	archiveProject,
	createProject,
	fetchProjects,
	fetchProjectTotal,
	fetchProjectWeek,
	projectKeys,
	unarchiveProject,
	useArchiveProject,
	useCreateProject,
	useInvalidateProjects,
	useProject,
	useProjects,
	useProjectWeeks,
	useUnarchiveProject,
	useUpdateGoalOverrides,
	useUpdateProject,
} from "./api";
// Model layer
export type {
	DailySummary,
	GoalOverride,
	Project,
	ProjectWithDuration,
	WeekHours,
} from "./model";
export {
	assignColor,
	clearPickerRecents,
	extractCategories,
	type FilterAndRankOptions,
	filterAndRankProjects,
	isVisibleProject,
	partitionByArchived,
	readPickerRecents,
	recordPickerRecent,
	type SearchField,
	toProject,
	visibleProjects,
} from "./model";

// UI layer
export {
	AdvancedFields,
	type AdvancedFieldsProps,
	type AdvancedFieldsValues,
	isValidGithubRepo,
	LoadingSpinner,
	NewProjectDialog,
	ProjectForm,
	type ProjectFormProps,
	type ProjectFormValues,
	ProjectPicker,
	type ProjectPickerProps,
} from "./ui";
