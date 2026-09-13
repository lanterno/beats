/**
 * Project API Functions
 * Low-level API calls for projects.
 */

import type {
	ApiContract,
	ApiGoalOverride,
	ApiProject,
	ApiProjectKind,
	ApiProjectListItem,
} from "@/shared/api";
import {
	ApiProjectListSchema,
	ApiProjectSchema,
	ContractWeekSchema,
	get,
	HolidayListSchema,
	LedgerSchema,
	ProjectTotalSchema,
	parseApiResponse,
	post,
	put,
	RegionListSchema,
} from "@/shared/api";
import { browserTimeZone } from "@/shared/lib";
import type { ContractWeek, Holiday, HolidayRegion, Ledger } from "../model";
import { toContractWeek, toLedger } from "../model";

/**
 * Per-project aggregations the backend can fold into the list response when
 * requested via `?include=`. P3.0 of the project-management revamp.
 */
export type ProjectInclude = "totals" | "this_week" | "last_tracked";

/**
 * Fetch all projects from the API, optionally augmented with the aggregations
 * needed by useProjects + the upcoming /projects index page. Without
 * `include`, returns the slim shape — `total_minutes`, `weekly_minutes`,
 * `effective_goal*`, and `last_tracked_at` come back as `null`.
 */
export async function fetchProjects(
	options: { include?: ProjectInclude[]; archived?: boolean } = {},
): Promise<ApiProjectListItem[]> {
	const params = new URLSearchParams();
	if (options.include && options.include.length > 0) {
		params.set("include", options.include.join(","));
		// `this_week` buckets the contract's worked hours by local day and
		// picks the current week in this timezone.
		params.set("tz", browserTimeZone());
	}
	if (options.archived) {
		// Backend treats absent as false; only send the flag when needed so
		// the no-options call matches the historical wire (active-only).
		params.set("archived", "true");
	}
	const qs = params.toString();
	const data = await get<unknown>(qs ? `/api/projects/?${qs}` : "/api/projects/");
	return parseApiResponse(ApiProjectListSchema, data);
}

/**
 * Create a new project. Color is optional — when omitted the UI assigns a
 * stable color from the id (see toProject), so a created project always
 * renders with a color even if the user didn't pick one.
 */
export async function createProject(input: {
	name: string;
	description?: string | null;
	color?: string | null;
	weekly_goal?: number | null;
	goal_type?: "target" | "cap";
	category?: string | null;
	github_repo?: string | null;
	autostart_repos?: string[];
	kind?: ApiProjectKind;
	/** Only with kind "day_job"; a contract on any other kind is a 409. */
	contract?: ApiContract | null;
}): Promise<ApiProject> {
	const data = await post<unknown>("/api/projects/", input);
	return parseApiResponse(ApiProjectSchema, data);
}

/**
 * Archive a project. Uses the dedicated POST /api/projects/{id}/archive
 * endpoint (not a generic update) so the call can't silently wipe fields
 * the UI Project type doesn't yet manage.
 */
export async function archiveProject(projectId: string): Promise<void> {
	await post<{ status: string }>(`/api/projects/${projectId}/archive`, {});
}

/**
 * Restore an archived project. Symmetric to archiveProject — uses the
 * dedicated /unarchive endpoint for the same reason.
 */
export async function unarchiveProject(projectId: string): Promise<void> {
	await post<{ status: string }>(`/api/projects/${projectId}/unarchive`, {});
}

/**
 * Wholesale replace of a project. `kind` and `contract` are the two fields
 * the API reads by presence: leave either out and the stored value stays;
 * `contract: null` clears it. A PUT that moves a day job to another kind
 * must leave `contract` out — the API clears it with the kind, and refuses
 * a contract sent alongside any other kind (409 NOT_A_DAY_JOB).
 */
export async function updateProject(project: {
	id: string;
	name: string;
	description?: string | null;
	color?: string | null;
	archived?: boolean;
	weekly_goal?: number | null;
	goal_type?: string;
	github_repo?: string | null;
	category?: string | null;
	autostart_repos?: string[];
	kind?: ApiProjectKind;
	contract?: ApiContract | null;
}): Promise<ApiProject> {
	const data = await put<unknown>("/api/projects/", project);
	return parseApiResponse(ApiProjectSchema, data);
}

/**
 * Replace a day job's whole contract — terms, region, opening balance and
 * end date — as one object, the way goal-overrides are replaced. 409 on a
 * project that is not a day job; 400 on a region the calendar does not know.
 */
export async function updateContract(
	projectId: string,
	contract: ApiContract,
): Promise<ApiProject> {
	const data = await put<unknown>(`/api/projects/${projectId}/contract`, contract);
	return parseApiResponse(ApiProjectSchema, data);
}

/**
 * One week of a day job against its contract. `weekOf` is the week's Monday;
 * left out, the API takes the current week in the browser's timezone. 409 on
 * a project that is not a day job (NOT_A_DAY_JOB) or has no contract yet
 * (NO_CONTRACT); 422 on a `weekOf` that is not a Monday.
 */
export async function fetchContractWeek(projectId: string, weekOf?: string): Promise<ContractWeek> {
	const params = new URLSearchParams({ tz: browserTimeZone() });
	if (weekOf) params.set("week_of", weekOf);
	const data = await get<unknown>(`/api/projects/${projectId}/contract/week?${params.toString()}`);
	return toContractWeek(parseApiResponse(ContractWeekSchema, data));
}

/**
 * The last `weeks` weeks of any project, newest first and ending with the
 * current week in the browser's timezone, with the balance at each week's
 * close on a day job and the balance as of today — every week figure on the
 * project page (docs/project-page-roadmap.md, Decision 11). `weeks` is 1–104;
 * 404 on a project that is not the caller's.
 */
export async function fetchLedger(projectId: string, weeks: number): Promise<Ledger> {
	const params = new URLSearchParams({ weeks: String(weeks), tz: browserTimeZone() });
	const data = await get<unknown>(`/api/projects/${projectId}/ledger?${params.toString()}`);
	return toLedger(parseApiResponse(LedgerSchema, data));
}

/** The contract region's public holidays for a year; empty without a region. */
export async function fetchProjectHolidays(projectId: string, year: number): Promise<Holiday[]> {
	const tz = encodeURIComponent(browserTimeZone());
	const data = await get<unknown>(`/api/projects/${projectId}/holidays?year=${year}&tz=${tz}`);
	return parseApiResponse(HolidayListSchema, data);
}

/** Every country the holiday calendar knows, with its subdivisions, for the region picker. */
export async function fetchHolidayRegions(): Promise<HolidayRegion[]> {
	const data = await get<unknown>("/api/meta/holiday-regions");
	return parseApiResponse(RegionListSchema, data);
}

export async function updateGoalOverrides(
	projectId: string,
	overrides: ApiGoalOverride[],
): Promise<ApiProject> {
	const data = await put<unknown>(`/api/projects/${projectId}/goal-overrides`, overrides);
	return parseApiResponse(ApiProjectSchema, data);
}

export async function fetchProjectTotal(projectId: string): Promise<number> {
	try {
		const data = await get<unknown>(`/api/projects/${projectId}/total/`);
		const parsed = parseApiResponse(ProjectTotalSchema, data);

		if (typeof parsed.total_minutes === "number") {
			return parsed.total_minutes;
		}

		// Fallback: sum durations_per_month (legacy support)
		if (parsed.durations_per_month) {
			const totalHours = Object.values(parsed.durations_per_month).reduce<number>(
				(sum, h) => sum + (h || 0),
				0,
			);
			return Math.round(totalHours * 60);
		}

		return 0;
	} catch {
		return 0;
	}
}
