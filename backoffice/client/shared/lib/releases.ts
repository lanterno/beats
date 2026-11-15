/**
 * The Releases page's words, apart from it so they can be tested. A web app
 * on another commit than the API is normal — they ship separately — and is
 * said as a fact, not a problem.
 */

import type { DeployStateReport, HeldBuild, ReleaseRow, ReleasesReport } from "@/shared/api/schema";
import { minuteOf } from "./format";

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

/** A build the deploy freeze held back is red in Cloud Build, and is not a bad release. */
export function buildLabel(row: ReleaseRow): string {
	return row.held ? "Held by the freeze" : statusLabel(row.status);
}

export function isBad(row: ReleaseRow): boolean {
	return !row.held && ["FAILURE", "INTERNAL_ERROR", "TIMEOUT"].includes(row.status);
}

/**
 * What to re-run once the freeze lifts. A held build does not deploy by
 * itself, and the one to re-run is the newest commit the freeze held back,
 * which the API names only while nothing has shipped it since.
 */
export function rerunAdvice(rerun: HeldBuild | null | undefined, frozen: boolean): string | null {
	if (!rerun) {
		return frozen
			? "Once it lifts, re-run the newest build it held back, if there is one: a held build does not deploy by itself."
			: null;
	}
	const what = `${short(rerun.sha)}${rerun.subject ? ` (${rerun.subject})` : ""}`;
	return frozen
		? `Once it lifts, re-run the build of ${what}: a held build does not deploy by itself.`
		: `The freeze held back ${what}, and nothing has shipped it since. Re-run its build to deploy it.`;
}

/** The page's first sentence: what each half is running. */
export function releasesHeadline(report: ReleasesReport): string {
	const api = report.api_commit
		? `The API serves ${short(report.api_commit)}`
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

/**
 * Whether the API's newest revision became ready, and what serves meanwhile
 * (docs/backoffice.md § The pages, Today). Null when the state cannot be read
 * here, where the Cloud Run console is the one to ask. Cloud Run's own words
 * for a failure are quoted whole.
 */
export function deploySentence(report: DeployStateReport): string | null {
	const d = report.deploy;
	if (!d) return null;
	const commit = (sha: string | null) => (sha ? short(sha) : "an unknown commit");
	const serving = d.serving_revision
		? `${d.serving_revision} serves ${commit(d.serving_commit)}`
		: null;
	const newest = `${d.newest_revision} with ${commit(d.newest_commit)}`;
	let sentence: string;
	if (!d.newest_revision) {
		sentence = "The API has no revision.";
	} else if (d.newest === "serving") {
		const since = d.serving_since ? `, since ${minuteOf(d.serving_since)}` : "";
		sentence = `The newest revision, ${d.serving_revision}, became ready and serves ${commit(d.serving_commit)}${since}.`;
	} else if (d.newest === "starting") {
		sentence = `${newest} is starting; ${serving ? `${serving} meanwhile` : "nothing serves yet"}.`;
	} else {
		const why = d.problem ? ` Cloud Run says: “${d.problem.trim()}”` : "";
		sentence = serving
			? `The newest revision, ${newest}, did not become ready, so ${serving} still.${why}`
			: `The newest revision, ${newest}, did not become ready, and no revision serves.${why}`;
	}
	return report.state === "stale"
		? `${sentence} That is as of ${minuteOf(report.as_of)}; Cloud Run has not answered since.`
		: sentence;
}
