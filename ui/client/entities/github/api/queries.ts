/**
 * GitHub TanStack Query Hooks
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { GitHubStatus } from "@/shared/api";
import { connectGitHub, disconnectGitHub, fetchGitHubStatus } from "./githubApi";

export const githubKeys = {
	all: ["github"] as const,
	status: () => [...githubKeys.all, "status"] as const,
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

export function useDisconnectGitHub() {
	const queryClient = useQueryClient();
	return useMutation({
		mutationFn: disconnectGitHub,
		onSuccess: () => {
			queryClient.invalidateQueries({ queryKey: githubKeys.all });
		},
	});
}
