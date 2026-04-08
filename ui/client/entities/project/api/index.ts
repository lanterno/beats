/**
 * Project API layer - public API
 */

// Low-level API functions
export {
	fetchProjects,
	fetchProjectTotal,
	fetchProjectWeek,
} from "./projectApi";

// TanStack Query hooks
export {
	projectKeys,
	useInvalidateProjects,
	useProject,
	useProjects,
	useProjectWeeks,
	useUpdateProject,
} from "./queries";
