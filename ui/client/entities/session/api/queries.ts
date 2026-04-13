/**
 * Session TanStack Query Hooks
 * Data fetching with caching for sessions.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { ProjectWithDuration } from "@/entities/project";
import { projectKeys } from "@/entities/project";
import type { HeatmapDay, RhythmSlot } from "@/shared/api";
import {
	formatDateShort,
	getCurrentWeekRange,
	getDayName,
	getWeekRange,
	parseUtcIso,
} from "@/shared/lib";
import type { DayProjectBreakdown, DaySummary, Session } from "../model";
import { toApiBeat, toSession } from "../model";
import { fetchAllTags, fetchBeats, fetchDailyRhythm, fetchHeatmap, updateBeat } from "./sessionApi";

/**
 * Query keys for session data
 */
export const sessionKeys = {
	all: ["sessions"] as const,
	allBeats: () => [...sessionKeys.all, "all-beats"] as const,
	list: (projectId?: string) => [...sessionKeys.all, "list", projectId ?? "all"] as const,
	detail: (id: string) => [...sessionKeys.all, "detail", id] as const,
};

/**
 * Shared base query: fetches all beats once and caches them.
 * Other hooks select/derive from this to avoid duplicate HTTP requests.
 */
export function useAllBeats() {
	return useQuery({
		queryKey: sessionKeys.allBeats(),
		queryFn: () => fetchBeats(),
		staleTime: 15_000,
	});
}

/**
 * Hook to fetch sessions for a project
 */
export function useSessions(projectId: string | undefined) {
	return useQuery({
		queryKey: sessionKeys.list(projectId),
		queryFn: async (): Promise<Session[]> => {
			const beats = await fetchBeats(projectId);
			return beats.filter((beat) => beat.start && beat.end).map(toSession);
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
			queryClient.invalidateQueries({
				queryKey: sessionKeys.list(variables.session.projectId),
			});
			queryClient.invalidateQueries({
				queryKey: sessionKeys.list(variables.projectId),
			});
			queryClient.invalidateQueries({ queryKey: projectKeys.all });
		},
	});
}

/**
 * Hook to fetch aggregated daily summary across all projects for the current week
 */
export function useAllCurrentWeekSessions() {
	const { data: allBeats } = useAllBeats();
	return useQuery({
		queryKey: [...sessionKeys.all, "all-week"],
		queryFn: (): DaySummary[] => {
			const sessions = (allBeats ?? []).filter((beat) => beat.start && beat.end).map(toSession);
			return calculateDailySummary(sessions);
		},
		enabled: !!allBeats,
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
	weekOffset = 0,
) {
	const { data: allBeats } = useAllBeats();
	return useQuery({
		queryKey: [
			...sessionKeys.all,
			"weekly-by-project",
			weekOffset,
			projects?.map((p) => p.id).join(","),
		],
		queryFn: (): DayProjectBreakdown[] => {
			const sessions = (allBeats ?? []).filter((beat) => beat.start && beat.end).map(toSession);

			const { start: weekStart, end: weekEnd } = getWeekRange(weekOffset);
			const weeklySessions = sessions.filter((session) => {
				const d = parseUtcIso(session.startTime);
				return d >= weekStart && d <= weekEnd;
			});

			const projectMap = new Map(
				(projects || []).map((p) => [p.id, { name: p.name, color: p.color }]),
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
		enabled: !!projects?.length && !!allBeats,
		staleTime: 30_000,
	});
}

/**
 * Hook to fetch recent sessions across all projects
 */
export function useRecentSessions(limit = 10) {
	const { data: allBeats } = useAllBeats();
	return useQuery({
		queryKey: [...sessionKeys.all, "recent", limit],
		queryFn: (): Session[] => {
			const sessions = (allBeats ?? []).filter((beat) => beat.start && beat.end).map(toSession);
			return sessions
				.sort((a, b) => new Date(b.startTime).getTime() - new Date(a.startTime).getTime())
				.slice(0, limit);
		},
		enabled: !!allBeats,
		staleTime: 30_000,
	});
}

/**
 * Hook to fetch today's sessions across all projects, sorted chronologically
 */
export function useTodaySessions() {
	const { data: allBeats } = useAllBeats();
	return useQuery({
		queryKey: [...sessionKeys.all, "today"],
		queryFn: (): Session[] => {
			const sessions = (allBeats ?? []).filter((beat) => beat.start && beat.end).map(toSession);
			const today = new Date();
			today.setHours(0, 0, 0, 0);
			return sessions
				.filter((s) => parseUtcIso(s.startTime) >= today)
				.sort((a, b) => new Date(a.startTime).getTime() - new Date(b.startTime).getTime());
		},
		enabled: !!allBeats,
		staleTime: 15_000,
	});
}

/**
 * Hook to fetch this week's sessions across all projects, sorted desc
 */
export function useThisWeekSessions() {
	const { data: allBeats } = useAllBeats();
	return useQuery({
		queryKey: [...sessionKeys.all, "this-week"],
		queryFn: (): Session[] => {
			const sessions = (allBeats ?? []).filter((beat) => beat.start && beat.end).map(toSession);
			const { start, end } = getCurrentWeekRange();
			return sessions
				.filter((s) => {
					const d = parseUtcIso(s.startTime);
					return d >= start && d <= end;
				})
				.sort((a, b) => new Date(b.startTime).getTime() - new Date(a.startTime).getTime());
		},
		enabled: !!allBeats,
		staleTime: 30_000,
	});
}

/**
 * Hook to fetch contribution heatmap for a year, optionally filtered by project and/or tag
 */
export function useHeatmap(year: number, projectId?: string, tag?: string) {
	return useQuery({
		queryKey: [...sessionKeys.all, "heatmap", year, projectId ?? "all", tag ?? "all"],
		queryFn: (): Promise<HeatmapDay[]> => fetchHeatmap(year, projectId, tag),
		staleTime: 60_000,
	});
}

/**
 * Hook to fetch daily rhythm chart data, optionally filtered by project and/or tag
 */
export function useDailyRhythm(period: string, projectId?: string, tag?: string) {
	return useQuery({
		queryKey: [...sessionKeys.all, "rhythm", period, projectId ?? "all", tag ?? "all"],
		queryFn: (): Promise<RhythmSlot[]> => fetchDailyRhythm(period, projectId, tag),
		staleTime: 60_000,
	});
}

/**
 * Hook to compute per-project time breakdown for a period
 */
export function useProjectBreakdown(period: "week" | "month" | "year" | "all", tag?: string) {
	const { data: allBeats } = useAllBeats();
	return useQuery({
		queryKey: [...sessionKeys.all, "project-breakdown", period, tag ?? "all"],
		queryFn: () => {
			const sessions = (allBeats ?? []).filter((b) => b.start && b.end).map(toSession);

			const now = new Date();
			let filtered = sessions.filter((s) => {
				const d = parseUtcIso(s.startTime);
				if (period === "week") {
					const { start, end } = getCurrentWeekRange();
					return d >= start && d <= end;
				}
				if (period === "month") {
					return d.getMonth() === now.getMonth() && d.getFullYear() === now.getFullYear();
				}
				if (period === "year") {
					return d.getFullYear() === now.getFullYear();
				}
				return true;
			});

			if (tag) {
				filtered = filtered.filter((s) => s.tags.includes(tag));
			}

			const byProject = new Map<string, number>();
			for (const s of filtered) {
				byProject.set(s.projectId, (byProject.get(s.projectId) || 0) + s.duration);
			}

			return Array.from(byProject.entries())
				.map(([projectId, minutes]) => ({ projectId, minutes }))
				.sort((a, b) => b.minutes - a.minutes);
		},
		enabled: !!allBeats,
		staleTime: 60_000,
	});
}

/**
 * Hook to compute streak data from all beats
 */
export function useStreaks() {
	const { data: allBeats } = useAllBeats();
	return useQuery({
		queryKey: [...sessionKeys.all, "streaks"],
		queryFn: () => {
			const sessions = (allBeats ?? []).filter((b) => b.start && b.end);

			// Collect unique dates with sessions
			const datesSet = new Set<string>();
			for (const s of sessions) {
				const d = parseUtcIso(s.start);
				datesSet.add(d.toDateString());
			}

			// Sort dates ascending
			const dates = Array.from(datesSet)
				.map((d) => new Date(d))
				.sort((a, b) => a.getTime() - b.getTime());

			if (dates.length === 0) return { current: 0, longest: 0 };

			// Calculate current streak (working backwards from today)
			const today = new Date();
			today.setHours(0, 0, 0, 0);

			let current = 0;
			const cursor = new Date(today);
			while (true) {
				if (datesSet.has(cursor.toDateString())) {
					current++;
					cursor.setDate(cursor.getDate() - 1);
				} else {
					break;
				}
			}

			// Calculate longest streak
			let longest = 1;
			let run = 1;
			for (let i = 1; i < dates.length; i++) {
				const diff = (dates[i].getTime() - dates[i - 1].getTime()) / (1000 * 60 * 60 * 24);
				if (Math.round(diff) === 1) {
					run++;
					longest = Math.max(longest, run);
				} else {
					run = 1;
				}
			}

			return { current, longest };
		},
		enabled: !!allBeats,
		staleTime: 60_000,
	});
}

/**
 * Hook to fetch last week's total minutes for comparison
 */
export function useLastWeekTotal() {
	const { data: allBeats } = useAllBeats();
	return useQuery({
		queryKey: [...sessionKeys.all, "last-week-total"],
		queryFn: () => {
			const sessions = (allBeats ?? []).filter((b) => b.start && b.end).map(toSession);
			const { start, end } = getWeekRange(-1);

			const lastWeekMinutes = sessions
				.filter((s) => {
					const d = parseUtcIso(s.startTime);
					return d >= start && d <= end;
				})
				.reduce((sum, s) => sum + s.duration, 0);

			return { lastWeekMinutes };
		},
		enabled: !!allBeats,
		staleTime: 60_000,
	});
}

/**
 * Hook to fetch all unique tags used across sessions
 */
export function useAllTags() {
	return useQuery({
		queryKey: [...sessionKeys.all, "tags"],
		queryFn: fetchAllTags,
		staleTime: 60_000,
	});
}
