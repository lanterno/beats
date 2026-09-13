// Low-level API functions
export {
	archiveProject,
	createProject,
	fetchContractWeek,
	fetchHolidayRegions,
	fetchLedger,
	fetchProjectHolidays,
	fetchProjects,
	fetchProjectTotal,
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
	useProjectLedger,
	useProjects,
	useUnarchiveProject,
	useUpdateContract,
	useUpdateGoalOverrides,
	useUpdateProject,
} from "./queries";
