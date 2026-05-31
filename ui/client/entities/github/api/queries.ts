/**
 * GitHub TanStack Query Hooks
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo } from "react";
import type { GitCommitDay, GitHubStatus } from "@/shared/api";
import {
	connectGitHub,
	disconnectGitHub,
	fetchGitHubStatus,
	fetchProjectGitActivity,
} from "./githubApi";

export const githubKeys = {
	all: ["github"] as const,
	status: () => [...githubKeys.all, "status"] as const,
	gitActivity: (projectId: string, start: string, end: string) =>
		[...githubKeys.all, "git-activity", projectId, start, end] as const,
};

export function useGitHubStatus() {
	return useQuery<GitHubStatus>({
		queryKey: githubKeys.status(),
		queryFn: fetchGitHubStatus,
		staleTime: 60_000,
	});
}

export function useConnectGitHub() {
	const queryClient = useQueryClient();
	return useMutation({
		mutationFn: connectGitHub,
		onSuccess: () => {
			queryClient.invalidateQueries({ queryKey: githubKeys.all });
		},
	});
}

/**
 * Daily commit counts for a project's linked GitHub repo across a date range.
 * Returns a Map of week-Monday-ISO → commit count, summing each commit into
 * the Monday of its local week. P4.4 of the project-management revamp.
 *
 * - Returns an empty map (not undefined) when the project has no github_repo
 *   set or the user isn't OAuth-connected — the caller renders an em-dash.
 * - The range is the same Monday list the week-history table is using, so a
 *   single fetch covers all visible rows.
 */
export function useProjectGitActivityByWeek(
	projectId: string | undefined,
	mondayIsoList: string[],
) {
	const start = mondayIsoList.length > 0 ? mondayIsoList[mondayIsoList.length - 1] : "";
	const end = (() => {
		if (mondayIsoList.length === 0) return "";
		const [y, m, d] = mondayIsoList[0].split("-").map(Number);
		const sunday = new Date(y, m - 1, d, 12, 0, 0, 0);
		sunday.setDate(sunday.getDate() + 6);
		const yyyy = sunday.getFullYear();
		const mm = String(sunday.getMonth() + 1).padStart(2, "0");
		const dd = String(sunday.getDate()).padStart(2, "0");
		return `${yyyy}-${mm}-${dd}`;
	})();

	const enabled = !!projectId && mondayIsoList.length > 0;
	const query = useQuery<GitCommitDay[]>({
		queryKey: githubKeys.gitActivity(projectId ?? "", start, end),
		queryFn: () => fetchProjectGitActivity(projectId as string, start, end),
		enabled,
		staleTime: 5 * 60_000,
	});

	const byMondayIso = useMemo(() => {
		const map = new Map<string, number>();
		for (const monday of mondayIsoList) map.set(monday, 0);
		if (!query.data) return map;
		for (const { date, commit_count } of query.data) {
			const monday = mondayIsoForDate(date);
			if (!map.has(monday)) continue;
			map.set(monday, (map.get(monday) ?? 0) + commit_count);
		}
		return map;
	}, [query.data, mondayIsoList]);

	return { byMondayIso, isLoading: query.isLoading, isError: query.isError };
}

function mondayIsoForDate(iso: string): string {
	const [y, m, d] = iso.split("-").map(Number);
	const dt = new Date(y, m - 1, d, 12, 0, 0, 0);
	dt.setDate(dt.getDate() - ((dt.getDay() + 6) % 7));
	const yyyy = dt.getFullYear();
	const mm = String(dt.getMonth() + 1).padStart(2, "0");
	const dd = String(dt.getDate()).padStart(2, "0");
	return `${yyyy}-${mm}-${dd}`;
}

export function useDisconnectGitHub() {
	const queryClient = useQueryClient();
	return useMutation({
		mutationFn: disconnectGitHub,
		onSuccess: () => {
			queryClient.invalidateQueries({ queryKey: githubKeys.all });
		},
	});
}
