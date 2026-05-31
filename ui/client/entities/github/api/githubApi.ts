/**
 * GitHub API Functions
 */

import type { GitCommitDay, GitHubStatus } from "@/shared/api";
import {
	del,
	GitCommitActivitySchema,
	GitHubStatusSchema,
	get,
	parseApiResponse,
	post,
} from "@/shared/api";

export async function fetchGitHubAuthUrl(): Promise<string> {
	const data = await get<{ url: string }>("/api/github/auth-url");
	return data.url;
}

export async function connectGitHub(code: string): Promise<void> {
	await post<void>(`/api/github/connect?code=${encodeURIComponent(code)}`);
}

export async function disconnectGitHub(): Promise<void> {
	await del<void>("/api/github/disconnect");
}

export async function fetchGitHubStatus(): Promise<GitHubStatus> {
	const data = await get<unknown>("/api/github/status");
	return parseApiResponse(GitHubStatusSchema, data);
}

/**
 * Fetch daily commit counts for a project's linked GitHub repo, in a date
 * range. Returns [] when the project has no github_repo set OR when the user
 * isn't OAuth-connected (the server uses the same fallback for both cases),
 * so callers should treat empty as "no signal available."
 */
export async function fetchProjectGitActivity(
	projectId: string,
	start: string,
	end: string,
): Promise<GitCommitDay[]> {
	const data = await get<unknown>(
		`/api/projects/${encodeURIComponent(projectId)}/git-activity?start=${start}&end=${end}`,
	);
	return parseApiResponse(GitCommitActivitySchema, data);
}
