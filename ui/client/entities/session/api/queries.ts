/**
 * Session TanStack Query Hooks
 * Data fetching with caching for sessions.
 */
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { fetchBeats, updateBeat } from "./sessionApi";
import { toSession, toApiBeat } from "../model";
import type { Session, DaySummary, DayProjectBreakdown } from "../model";
import type { ProjectWithDuration } from "@/entities/project";
import { parseUtcIso, getCurrentWeekRange, getWeekRange, getDayName, formatDateShort } from "@/shared/lib";
import { projectKeys } from "@/entities/project";

/**
 * Query keys for session data
 */
export const sessionKeys = {
  all: ["sessions"] as const,
  list: (projectId?: string) => [...sessionKeys.all, "list", projectId ?? "all"] as const,
  detail: (id: string) => [...sessionKeys.all, "detail", id] as const,
};

/**
 * Hook to fetch sessions for a project
 */
export function useSessions(projectId: string | undefined) {
  return useQuery({
    queryKey: sessionKeys.list(projectId),
    queryFn: async (): Promise<Session[]> => {
      const beats = await fetchBeats(projectId);
      return beats
        .filter((beat) => beat.start && beat.end)
        .map(toSession);
    },
    enabled: !!projectId,
  });
}

/**
 * Hook to update a session
 */
export function useUpdateSession() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({
      session,
      startTime,
      endTime,
      projectId,
    }: {
      session: Session;
      startTime: string;
      endTime: string;
      projectId: string;
    }) => {
      const duration = (new Date(endTime).getTime() - new Date(startTime).getTime()) / 1000 / 60;
      const updatedSession: Session = {
        ...session,
        startTime,
        endTime,
        projectId,
        duration,
      };
      await updateBeat(toApiBeat(updatedSession));
      return updatedSession;
    },
    onSuccess: (_, variables) => {
      // Invalidate related queries
      queryClient.invalidateQueries({ queryKey: sessionKeys.list(variables.session.projectId) });
      queryClient.invalidateQueries({ queryKey: sessionKeys.list(variables.projectId) });
      queryClient.invalidateQueries({ queryKey: projectKeys.all });
    },
  });
}

/**
 * Hook to fetch aggregated daily summary across all projects for the current week
 */
export function useAllCurrentWeekSessions() {
  return useQuery({
    queryKey: [...sessionKeys.all, "all-week"],
    queryFn: async (): Promise<DaySummary[]> => {
      const beats = await fetchBeats();
      const sessions = beats
        .filter((beat) => beat.start && beat.end)
        .map(toSession);
      return calculateDailySummary(sessions);
    },
    staleTime: 30_000,
  });
}

/**
 * Calculate daily summary from sessions
 */
export function calculateDailySummary(sessions: Session[]): DaySummary[] {
  const { start: weekStart, end: weekEnd } = getCurrentWeekRange();

  // Filter sessions to current week
  const weeklySessions = sessions.filter((session) => {
    const sessionDate = parseUtcIso(session.startTime);
    return sessionDate >= weekStart && sessionDate <= weekEnd;
  });

  // Create summary for each day
  return Array.from({ length: 7 }, (_, i) => {
    const dayDate = new Date(weekStart);
    dayDate.setDate(weekStart.getDate() + i);
    dayDate.setHours(0, 0, 0, 0);

    const dayEnd = new Date(dayDate);
    dayEnd.setHours(23, 59, 59, 999);

    const daySessions = weeklySessions.filter((session) => {
      const sessionDate = parseUtcIso(session.startTime);
      return sessionDate >= dayDate && sessionDate <= dayEnd;
    });

    const dayTotalMinutes = daySessions.reduce((sum, session) => sum + session.duration, 0);

    return {
      date: dayDate,
      dayName: getDayName(dayDate, "long"),
      dateShort: formatDateShort(dayDate),
      totalMinutes: dayTotalMinutes,
      sessionCount: daySessions.length,
    };
  });
}

/**
 * Hook to fetch weekly sessions grouped by project per day (for stacked bar chart)
 * @param weekOffset 0 = current week, -1 = last week, etc.
 */
export function useWeeklySessionsByProject(
  projects: ProjectWithDuration[] | undefined,
  weekOffset = 0
) {
  return useQuery({
    queryKey: [...sessionKeys.all, "weekly-by-project", weekOffset, projects?.map((p) => p.id).join(",")],
    queryFn: async (): Promise<DayProjectBreakdown[]> => {
      const beats = await fetchBeats();
      const sessions = beats
        .filter((beat) => beat.start && beat.end)
        .map(toSession);

      const { start: weekStart, end: weekEnd } = getWeekRange(weekOffset);
      const weeklySessions = sessions.filter((session) => {
        const d = parseUtcIso(session.startTime);
        return d >= weekStart && d <= weekEnd;
      });

      const projectMap = new Map(
        (projects || []).map((p) => [p.id, { name: p.name, color: p.color }])
      );

      const today = new Date();
      today.setHours(0, 0, 0, 0);

      return Array.from({ length: 7 }, (_, i) => {
        const dayDate = new Date(weekStart);
        dayDate.setDate(weekStart.getDate() + i);
        dayDate.setHours(0, 0, 0, 0);

        const dayEnd = new Date(dayDate);
        dayEnd.setHours(23, 59, 59, 999);

        const daySessions = weeklySessions.filter((s) => {
          const d = parseUtcIso(s.startTime);
          return d >= dayDate && d <= dayEnd;
        });

        // Group by project
        const byProject = new Map<string, number>();
        for (const s of daySessions) {
          byProject.set(s.projectId, (byProject.get(s.projectId) || 0) + s.duration);
        }

        const segments = Array.from(byProject.entries())
          .map(([projectId, minutes]) => {
            const info = projectMap.get(projectId);
            return {
              projectId,
              projectName: info?.name || "Unknown",
              projectColor: info?.color || "#888",
              minutes,
            };
          })
          .sort((a, b) => b.minutes - a.minutes);

        return {
          date: dayDate,
          dayName: getDayName(dayDate, "short"),
          isToday: dayDate.getTime() === today.getTime(),
          segments,
          totalMinutes: segments.reduce((sum, s) => sum + s.minutes, 0),
        };
      });
    },
    enabled: !!projects?.length,
    staleTime: 30_000,
  });
}

/**
 * Hook to fetch recent sessions across all projects
 */
export function useRecentSessions(limit = 10) {
  return useQuery({
    queryKey: [...sessionKeys.all, "recent", limit],
    queryFn: async (): Promise<Session[]> => {
      const beats = await fetchBeats();
      const sessions = beats
        .filter((beat) => beat.start && beat.end)
        .map(toSession);

      return sessions
        .sort((a, b) => new Date(b.startTime).getTime() - new Date(a.startTime).getTime())
        .slice(0, limit);
    },
    staleTime: 30_000,
  });
}

/**
 * Hook to fetch today's sessions across all projects, sorted chronologically
 */
export function useTodaySessions() {
  return useQuery({
    queryKey: [...sessionKeys.all, "today"],
    queryFn: async (): Promise<Session[]> => {
      const beats = await fetchBeats();
      const sessions = beats
        .filter((beat) => beat.start && beat.end)
        .map(toSession);
      const today = new Date();
      today.setHours(0, 0, 0, 0);
      return sessions
        .filter((s) => parseUtcIso(s.startTime) >= today)
        .sort((a, b) => new Date(a.startTime).getTime() - new Date(b.startTime).getTime());
    },
    staleTime: 15_000,
  });
}

/**
 * Hook to fetch this week's sessions across all projects, sorted desc
 */
export function useThisWeekSessions() {
  return useQuery({
    queryKey: [...sessionKeys.all, "this-week"],
    queryFn: async (): Promise<Session[]> => {
      const beats = await fetchBeats();
      const sessions = beats
        .filter((beat) => beat.start && beat.end)
        .map(toSession);
      const { start, end } = getCurrentWeekRange();
      return sessions
        .filter((s) => {
          const d = parseUtcIso(s.startTime);
          return d >= start && d <= end;
        })
        .sort((a, b) => new Date(b.startTime).getTime() - new Date(a.startTime).getTime());
    },
    staleTime: 30_000,
  });
}
