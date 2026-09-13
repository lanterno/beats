/**
 * Project TanStack Query Hooks
 * Data fetching with caching, deduplication, and automatic refetching.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { ApiContract, ApiGoalOverride, ApiProjectListItem } from "@/shared/api";
import type { ContractWeek, Ledger, ProjectWithDuration } from "../model";
import { toProject } from "../model";
import {
	archiveProject,
	createProject,
	fetchContractWeek,
	fetchHolidayRegions,
	fetchLedger,
	fetchProjectHolidays,
	fetchProjects,
	unarchiveProject,
	updateContract,
	updateGoalOverrides,
	updateProject,
} from "./projectApi";

export const projectKeys = {
	all: ["projects"] as const,
	list: () => [...projectKeys.all, "list"] as const,
	archivedList: () => [...projectKeys.all, "list", "archived"] as const,
	detail: (id: string) => [...projectKeys.all, "detail", id] as const,
	total: (id: string) => [...projectKeys.all, "total", id] as const,
	/** Every ledger read of one project, whatever its length — what a write invalidates. */
	ledger: (id: string) => [...projectKeys.all, "ledger", id] as const,
	holidays: (id: string, year: number) => [...projectKeys.all, "holidays", id, year] as const,
	/** Every week of one project against its contract — what an absence write invalidates. */
	contractWeeks: (id: string) => [...projectKeys.all, "contract-week", id] as const,
	contractWeek: (id: string, weekOf: string | undefined) =>
		[...projectKeys.contractWeeks(id), weekOf ?? "current"] as const,
};

/** The holiday-region list changes only with a release of the API's calendar library. */
export const holidayRegionKeys = {
	all: ["meta", "holiday-regions"] as const,
};

/** One list item, with the aggregations the list endpoint folded in. */
function toProjectWithDuration(item: ApiProjectListItem): ProjectWithDuration {
	const project = toProject(item);
	return {
		...project,
		totalMinutes: item.total_minutes ?? 0,
		// Round so downstream tabular-nums chips don't show 60.000000001h.
		weeklyMinutes: Math.round(item.weekly_minutes ?? 0),
		// Preserve null vs undefined: null = override sets "no goal" for
		// this week; undefined = field absent (e.g. older response).
		effectiveGoal: item.effective_goal === undefined ? undefined : item.effective_goal,
		effectiveGoalType: item.effective_goal_type ?? undefined,
		effectiveGoalOverridden: item.effective_goal_overridden ?? false,
		// Null on the wire means no contract governs the week; see ContractWeek.
		contractExpected: item.contract_expected ?? undefined,
		contractWorked: item.contract_worked ?? undefined,
		contractRemaining: item.contract_remaining ?? undefined,
		balance: item.balance ?? undefined,
		lastTrackedAt: item.last_tracked_at ?? undefined,
	};
}

/**
 * Hook to fetch all projects augmented with totals + this-week + last-tracked.
 *
 * P3.0 of the project-management revamp: this used to fan out 2 extra requests
 * per project (the total and the week), so a user with 30 projects paid for 61
 * round-trips on a cold load. The augmented list endpoint collapses that to one.
 */
export function useProjects() {
	return useQuery({
		queryKey: projectKeys.list(),
		queryFn: async (): Promise<ProjectWithDuration[]> => {
			const items = await fetchProjects({
				include: ["totals", "this_week", "last_tracked"],
			});

			return items.map(toProjectWithDuration);
		},
		staleTime: 30_000, // Consider fresh for 30 seconds
	});
}

/**
 * Hook to fetch archived projects with their aggregations.
 *
 * Separate cache key from useProjects so the /projects index page can
 * keep the Active tab cached while it loads the Archived tab. P3.2 of
 * the project-management revamp.
 */
export function useArchivedProjects() {
	return useQuery({
		queryKey: projectKeys.archivedList(),
		queryFn: async (): Promise<ProjectWithDuration[]> => {
			const items = await fetchProjects({
				archived: true,
				include: ["totals", "this_week", "last_tracked"],
			});
			return items.map(toProjectWithDuration);
		},
		staleTime: 30_000,
	});
}

/**
 * Hook to get a single project by ID (from cache or fetch)
 */
export function useProject(projectId: string | undefined) {
	const queryClient = useQueryClient();

	return useQuery({
		queryKey: projectKeys.detail(projectId || ""),
		queryFn: async (): Promise<ProjectWithDuration | null> => {
			// Try to get from cached list first
			const cachedProjects = queryClient.getQueryData<ProjectWithDuration[]>(projectKeys.list());
			const cached = cachedProjects?.find((p) => p.id === projectId);
			if (cached) return cached;

			// Otherwise fetch the augmented list and find — uses the same
			// single-round-trip path useProjects does (P3.0).
			const items = await fetchProjects({
				include: ["totals", "this_week", "last_tracked"],
			});
			const item = items.find((p) => p.id === projectId);
			return item ? toProjectWithDuration(item) : null;
		},
		enabled: !!projectId,
	});
}

/**
 * Hook to create a new project. Refetches the list first (so the new project
 * appears immediately) then invalidates the rest of the project tree.
 */
export function useCreateProject() {
	const queryClient = useQueryClient();
	return useMutation({
		mutationFn: createProject,
		onSuccess: async () => {
			await queryClient.refetchQueries({ queryKey: projectKeys.list() });
			queryClient.invalidateQueries({ queryKey: projectKeys.all });
		},
	});
}

/**
 * Hook to archive a project. Refetches the active list (so the row
 * disappears immediately) then invalidates the rest of the project tree
 * so any place that filters by archived state reconciles.
 */
export function useArchiveProject() {
	const queryClient = useQueryClient();
	return useMutation({
		mutationFn: archiveProject,
		onSuccess: async () => {
			await queryClient.refetchQueries({ queryKey: projectKeys.list() });
			queryClient.invalidateQueries({ queryKey: projectKeys.all });
		},
	});
}

/**
 * Hook to restore an archived project (symmetric to useArchiveProject).
 */
export function useUnarchiveProject() {
	const queryClient = useQueryClient();
	return useMutation({
		mutationFn: unarchiveProject,
		onSuccess: async () => {
			await queryClient.refetchQueries({ queryKey: projectKeys.list() });
			queryClient.invalidateQueries({ queryKey: projectKeys.all });
		},
	});
}

export function useUpdateProject() {
	const queryClient = useQueryClient();
	return useMutation({
		mutationFn: updateProject,
		onSuccess: async () => {
			// Refetch the list first: useProject derives the detail from the cached
			// list, so the list must be fresh before the detail refetches — otherwise
			// the detail re-resolves to the pre-save value.
			await queryClient.refetchQueries({ queryKey: projectKeys.list() });
			queryClient.invalidateQueries({ queryKey: projectKeys.all });
		},
	});
}

export function useUpdateGoalOverrides() {
	const queryClient = useQueryClient();
	return useMutation({
		mutationFn: ({ projectId, overrides }: { projectId: string; overrides: ApiGoalOverride[] }) =>
			updateGoalOverrides(projectId, overrides),
		onSuccess: async () => {
			// Refetch the list first: useProject derives the detail from the cached
			// list, so the list must be fresh before the detail refetches — otherwise
			// the detail re-resolves to the pre-save value.
			await queryClient.refetchQueries({ queryKey: projectKeys.list() });
			queryClient.invalidateQueries({ queryKey: projectKeys.all });
		},
	});
}

/**
 * Replace a day job's contract as one object. Refetches the list first for
 * the same reason useUpdateProject does; `projectKeys.all` then also takes
 * the holidays with it (a region may have changed).
 */
export function useUpdateContract() {
	const queryClient = useQueryClient();
	return useMutation({
		mutationFn: ({ projectId, contract }: { projectId: string; contract: ApiContract }) =>
			updateContract(projectId, contract),
		onSuccess: async () => {
			await queryClient.refetchQueries({ queryKey: projectKeys.list() });
			queryClient.invalidateQueries({ queryKey: projectKeys.all });
		},
	});
}

/**
 * One week of a day job against its contract; `weekOf` undefined is the
 * current week. Only meaningful on a day job with a contract — pass
 * `enabled: false` elsewhere rather than let the API answer 409. Invalidated
 * by every project write (`projectKeys.all`), by absence writes through
 * `projectKeys.contractWeeks`, and by timer and session writes, since
 * `worked` moves with them.
 */
export function useContractWeek(
	projectId: string | undefined,
	weekOf?: string,
	options: { enabled?: boolean; refetchInterval?: number | false } = {},
) {
	return useQuery({
		queryKey: projectKeys.contractWeek(projectId || "", weekOf),
		queryFn: (): Promise<ContractWeek> => fetchContractWeek(projectId as string, weekOf),
		enabled: !!projectId && (options.enabled ?? true),
		// A running timer moves `worked`; fresh for as long as the list is. A
		// timer start writes nothing a week read returns, so the page that shows
		// a running beat passes `refetchInterval` to keep the figures moving.
		staleTime: 30_000,
		refetchInterval: options.refetchInterval ?? false,
	});
}

/**
 * The project's last `weeks` weeks, newest first, the current week included —
 * the project page's one read for every week figure. Any kind of project.
 * Invalidated by every project write (`projectKeys.all`), by absence writes
 * through `projectKeys.ledger`, and by timer and session writes, since
 * `worked` moves with them.
 */
export function useProjectLedger(
	projectId: string | undefined,
	weeks = 8,
	options: { refetchInterval?: number | false } = {},
) {
	return useQuery({
		queryKey: [...projectKeys.ledger(projectId || ""), weeks] as const,
		queryFn: (): Promise<Ledger> => fetchLedger(projectId as string, weeks),
		enabled: !!projectId,
		// A running timer moves the current week's `worked` and today's balance;
		// the page polls with `refetchInterval` while one runs.
		staleTime: 30_000,
		refetchInterval: options.refetchInterval ?? false,
	});
}

/** The contract region's holidays for one year, for the absence calendar. */
export function useProjectHolidays(projectId: string | undefined, year: number) {
	return useQuery({
		queryKey: projectKeys.holidays(projectId || "", year),
		queryFn: () => fetchProjectHolidays(projectId as string, year),
		enabled: !!projectId,
		// Changes only with the region, and a contract write invalidates it.
		staleTime: 60 * 60_000,
	});
}

/** Every country and subdivision the calendar knows, for the region picker. */
export function useHolidayRegions() {
	return useQuery({
		queryKey: holidayRegionKeys.all,
		queryFn: fetchHolidayRegions,
		// Static for the life of the API process; the route says max-age=86400 too.
		staleTime: 24 * 60 * 60_000,
		gcTime: 24 * 60 * 60_000,
	});
}
