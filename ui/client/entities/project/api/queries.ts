/**
 * Project TanStack Query Hooks
 * Data fetching with caching, deduplication, and automatic refetching.
 */
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchProjects, fetchProjectWeek, fetchProjectTotal } from "./projectApi";
import { toProject } from "../model";
import type { ProjectWithDuration, WeekHours } from "../model";

/**
 * Query keys for project data
 */
export const projectKeys = {
  all: ["projects"] as const,
  list: () => [...projectKeys.all, "list"] as const,
  detail: (id: string) => [...projectKeys.all, "detail", id] as const,
  total: (id: string) => [...projectKeys.all, "total", id] as const,
  week: (id: string, weeksAgo: number) => [...projectKeys.all, "week", id, weeksAgo] as const,
  weeks: (id: string) => [...projectKeys.all, "weeks", id] as const,
};

/**
 * Hook to fetch all projects with their total and weekly duration
 */
export function useProjects() {
  return useQuery({
    queryKey: projectKeys.list(),
    queryFn: async (): Promise<ProjectWithDuration[]> => {
      const apiProjects = await fetchProjects();

      // Fetch totals and weekly hours in parallel
      const projectsWithTotals = await Promise.all(
        apiProjects.map(async (apiProject) => {
          const project = toProject(apiProject);
          if (!project.id) {
            return { ...project, totalMinutes: 0, weeklyMinutes: 0 };
          }

          const [totalMinutes, weeklyData] = await Promise.all([
            fetchProjectTotal(project.id),
            fetchProjectWeek(project.id, 0).catch(() => ({ totalHours: 0 })),
          ]);

          const weeklyMinutes = Math.round(weeklyData.totalHours * 60);
          return { ...project, totalMinutes, weeklyMinutes };
        })
      );

      return projectsWithTotals;
    },
    staleTime: 30_000, // Consider fresh for 30 seconds
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

      // Otherwise fetch all and find
      const apiProjects = await fetchProjects();
      const apiProject = apiProjects.find((p) => p.id === projectId);
      if (!apiProject) return null;

      const project = toProject(apiProject);
      if (!project.id) {
        return { ...project, totalMinutes: 0, weeklyMinutes: 0 };
      }

      const [totalMinutes, weeklyData] = await Promise.all([
        fetchProjectTotal(project.id),
        fetchProjectWeek(project.id, 0).catch(() => ({ totalHours: 0 })),
      ]);

      const weeklyMinutes = Math.round(weeklyData.totalHours * 60);
      return { ...project, totalMinutes, weeklyMinutes };
    },
    enabled: !!projectId,
  });
}

/**
 * Hook to fetch project weekly hours for the last 5 weeks
 */
export function useProjectWeeks(projectId: string | undefined) {
  return useQuery({
    queryKey: projectKeys.weeks(projectId || ""),
    queryFn: async (): Promise<WeekHours[]> => {
      if (!projectId) return [];

      const results = await Promise.allSettled(
        [0, 1, 2, 3, 4].map(async (weeksAgo) => {
          const { totalHours, dailyDurations } = await fetchProjectWeek(projectId, weeksAgo);
          return { weeksAgo, hours: totalHours, dailyDurations };
        })
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
