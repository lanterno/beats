/**
 * GitHub API Functions
 */

import type { GitHubStatus } from "@/shared/api";
import { del, GitHubStatusSchema, get, parseApiResponse, post } from "@/shared/api";

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
