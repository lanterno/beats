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
	useProject,
	useProjects,
	useProjectWeeks,
	useUnarchiveProject,
	useUpdateGoalOverrides,
	useUpdateProject,
} from "./queries";
