/**
 * Project API layer - public API
 */

// Low-level API functions
export {
	archiveProject,
	createProject,
	fetchProjects,
	fetchProjectTotal,
	fetchProjectWeek,
	unarchiveProject,
} from "./projectApi";

// TanStack Query hooks
export {
	projectKeys,
	useArchivedProjects,
	useArchiveProject,
	useCreateProject,
	useInvalidateProjects,
	useProject,
	useProjects,
	useProjectWeeks,
	useUnarchiveProject,
	useUpdateGoalOverrides,
	useUpdateProject,
} from "./queries";
