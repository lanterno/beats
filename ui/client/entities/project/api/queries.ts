/**
 * Project TanStack Query Hooks
 * Data fetching with caching, deduplication, and automatic refetching.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { ApiGoalOverride } from "@/shared/api";
import type { ProjectWithDuration, WeekHours } from "../model";
import { toProject } from "../model";
import {
	archiveProject,
	createProject,
	fetchProjects,
	fetchProjectWeek,
	unarchiveProject,
	updateGoalOverrides,
	updateProject,
} from "./projectApi";

/**
 * Query keys for project data
 */
export const projectKeys = {
	all: ["projects"] as const,
	list: () => [...projectKeys.all, "list"] as const,
	archivedList: () => [...projectKeys.all, "list", "archived"] as const,
	detail: (id: string) => [...projectKeys.all, "detail", id] as const,
	total: (id: string) => [...projectKeys.all, "total", id] as const,
	week: (id: string, weeksAgo: number) => [...projectKeys.all, "week", id, weeksAgo] as const,
	weeks: (id: string) => [...projectKeys.all, "weeks", id] as const,
};

/**
 * Hook to fetch all projects augmented with totals + this-week + last-tracked.
 *
 * P3.0 of the project-management revamp: this used to fan out 2 extra requests
 * per project (fetchProjectTotal + fetchProjectWeek), so a user with 30
 * projects paid for 61 round-trips on a cold load. The augmented list
 * endpoint collapses that to one.
 */
export function useProjects() {
	return useQuery({
		queryKey: projectKeys.list(),
		queryFn: async (): Promise<ProjectWithDuration[]> => {
			const items = await fetchProjects({
				include: ["totals", "this_week", "last_tracked"],
			});

			return items.map((item) => {
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
					lastTrackedAt: item.last_tracked_at ?? undefined,
				};
			});
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
			return items.map((item) => {
				const project = toProject(item);
				return {
					...project,
					totalMinutes: item.total_minutes ?? 0,
					weeklyMinutes: Math.round(item.weekly_minutes ?? 0),
					effectiveGoal: item.effective_goal === undefined ? undefined : item.effective_goal,
					effectiveGoalType: item.effective_goal_type ?? undefined,
					effectiveGoalOverridden: item.effective_goal_overridden ?? false,
					lastTrackedAt: item.last_tracked_at ?? undefined,
				};
			});
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
			if (!item) return null;

			const project = toProject(item);
			return {
				...project,
				totalMinutes: item.total_minutes ?? 0,
				weeklyMinutes: Math.round(item.weekly_minutes ?? 0),
				effectiveGoal: item.effective_goal === undefined ? undefined : item.effective_goal,
				effectiveGoalType: item.effective_goal_type ?? undefined,
				effectiveGoalOverridden: item.effective_goal_overridden ?? false,
				lastTrackedAt: item.last_tracked_at ?? undefined,
			};
		},
		enabled: !!projectId,
	});
}

/**
 * Hook to fetch project weekly hours for a given number of weeks
 */
export function useProjectWeeks(projectId: string | undefined, weekCount: number = 5) {
	return useQuery({
		queryKey: [...projectKeys.weeks(projectId || ""), weekCount],
		queryFn: async (): Promise<WeekHours[]> => {
			if (!projectId) return [];

			const weeks = Array.from({ length: weekCount }, (_, i) => i);
			const results = await Promise.allSettled(
				weeks.map(async (weeksAgo) => {
					const {
						totalHours,
						dailyDurations,
						weekStart,
						effectiveGoal,
						effectiveGoalType,
						effectiveGoalOverridden,
					} = await fetchProjectWeek(projectId, weeksAgo);
					return {
						weeksAgo,
						hours: totalHours,
						dailyDurations,
						weekStart,
						effectiveGoal,
						effectiveGoalType,
						effectiveGoalOverridden,
					};
				}),
			);

			const weekHours: WeekHours[] = [];
			results.forEach((result) => {
				if (result.status === "fulfilled") {
					weekHours.push(result.value);
				}
			});

			return weekHours.sort((a, b) => a.weeksAgo - b.weeksAgo);
		},
		enabled: !!projectId,
		staleTime: 60_000, // Weekly data doesn't change often
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

/**
 * Hook to update a project (e.g. color change)
 */
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

/**
 * Hook to update goal overrides for a project
 */
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
 * Hook to invalidate project queries (useful after mutations)
 */
export function useInvalidateProjects() {
	const queryClient = useQueryClient();

	return {
		invalidateAll: () => queryClient.invalidateQueries({ queryKey: projectKeys.all }),
		invalidateList: () => queryClient.invalidateQueries({ queryKey: projectKeys.list() }),
		invalidateProject: (id: string) =>
			queryClient.invalidateQueries({ queryKey: projectKeys.detail(id) }),
	};
}
