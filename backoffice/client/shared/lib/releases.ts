/**
 * The Releases page's words, apart from it so they can be tested. A web app
 * on another commit than the API is normal — they ship separately — and is
 * said as a fact, not a problem.
 */

import type { ReleaseRow, ReleasesReport } from "@/shared/api/schema";

export const short = (sha: string | null | undefined): string =>
	sha ? sha.slice(0, 7) : "unknown";

export const commitUrl = (repository: string, sha: string): string =>
	`https://github.com/${repository}/commit/${sha}`;

const STATUS: Record<string, string> = {
	SUCCESS: "Built",
	FAILURE: "Failed",
	INTERNAL_ERROR: "Failed",
	TIMEOUT: "Timed out",
	CANCELLED: "Cancelled",
	EXPIRED: "Expired",
	WORKING: "Building",
	QUEUED: "Queued",
	PENDING: "Queued",
};

export function statusLabel(status: string): string {
	return STATUS[status] ?? "Unknown";
}

export function isBad(row: ReleaseRow): boolean {
	return ["FAILURE", "INTERNAL_ERROR", "TIMEOUT"].includes(row.status);
}

/** The page's first sentence: what each half is running. */
export function releasesHeadline(report: ReleasesReport): string {
	const api = report.api_commit
		? `The API was deployed at ${short(report.api_commit)}`
		: "The API's commit is unknown";
	if (!report.web_commit) return `${api}; the web app's is unknown.`;
	if (report.web_commit === report.api_commit)
		return `${api}, and the web app is on the same commit.`;
	return `${api}; the web app is at ${short(report.web_commit)}. They ship separately, so that is normal.`;
}

const SOURCES: Record<string, string> = {
	builds: "Cloud Build",
	web: "the web app's version.json",
	subjects: "GitHub, for commit subjects",
};

/** Said when a source did not answer; the rest of the page still stands. */
export function unanswered(report: ReleasesReport): string | null {
	const names = (report.unavailable ?? []).map((s) => SOURCES[s] ?? s);
	if (names.length === 0) return null;
	return `No answer from ${names.join(", ")}. What is shown is the last answer, if there was one.`;
}
