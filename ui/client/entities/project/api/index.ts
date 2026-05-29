/**
 * Project API layer - public API
 */

// Low-level API functions
export {
	createProject,
	fetchProjects,
	fetchProjectTotal,
	fetchProjectWeek,
} from "./projectApi";

// TanStack Query hooks
export {
	projectKeys,
	useCreateProject,
	useInvalidateProjects,
	useProject,
	useProjects,
	useProjectWeeks,
	useUpdateGoalOverrides,
	useUpdateProject,
} from "./queries";
