// Low-level API functions
export {
	archiveProject,
	createProject,
	fetchContractWeek,
	fetchHolidayRegions,
	fetchProjectHolidays,
	fetchProjects,
	fetchProjectTotal,
	fetchProjectWeek,
	unarchiveProject,
	updateContract,
} from "./projectApi";

// TanStack Query hooks
export {
	holidayRegionKeys,
	projectKeys,
	useArchivedProjects,
	useArchiveProject,
	useContractWeek,
	useCreateProject,
	useHolidayRegions,
	useProject,
	useProjectHolidays,
	useProjects,
	useProjectWeeks,
	useUnarchiveProject,
	useUpdateContract,
	useUpdateGoalOverrides,
	useUpdateProject,
} from "./queries";
