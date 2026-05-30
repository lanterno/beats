/**
 * Project selectors — the single source of truth for "should this project
 * show up in a list or picker?" Pre-P0.3, every surface had its own
 * `(projects ?? []).filter((p) => !p.archived)` inline (or worse, didn't
 * filter at all). Centralizing here means P2.4's "Show archived" toggle and
 * future visibility rules (e.g. pin-to-top) land in one place.
 */

import type { Project, ProjectWithDuration } from "./types";

/**
 * True iff the project should appear in active pickers/lists. Currently just
 * "not archived", but kept as a named predicate so future rules (hidden by
 * the user, soft-deleted, etc.) plug in without touching every consumer.
 */
export function isVisibleProject(p: Pick<Project, "archived">): boolean {
	return !p.archived;
}

/**
 * Filter a project list to only those visible by default.
 */
export function visibleProjects<T extends Pick<Project, "archived">>(
	projects: T[] | undefined,
): T[] {
	return (projects ?? []).filter(isVisibleProject);
}

/**
 * Split a project list into visible vs archived buckets. Used by the
 * sidebar's "Show archived" toggle so the archived rail can render below
 * the active list with consistent ordering.
 */
export function partitionByArchived<T extends Pick<Project, "archived">>(
	projects: T[] | undefined,
): { visible: T[]; archived: T[] } {
	const visible: T[] = [];
	const archived: T[] = [];
	for (const p of projects ?? []) {
		(p.archived ? archived : visible).push(p);
	}
	return { visible, archived };
}

/**
 * Accept either bare projects or projects-with-duration — the visible filter
 * doesn't depend on weekly/total minutes, so callers don't need to widen.
 */
export type AnyProject = Project | ProjectWithDuration;

/**
 * Sorted unique list of category strings across all projects. Seeds the
 * `<datalist>` of the ProjectForm category combobox so users can pick an
 * existing value with one click but still type a new one — keeps category
 * free-form (per the roadmap open question) while reducing typo drift.
 */
export function extractCategories<T extends Pick<Project, "category">>(
	projects: T[] | undefined,
): string[] {
	const seen = new Set<string>();
	for (const p of projects ?? []) {
		const c = p.category?.trim();
		if (c) seen.add(c);
	}
	return [...seen].sort((a, b) => a.localeCompare(b));
}

export type SearchField = "name" | "description";

export interface FilterAndRankOptions {
	/** Include archived projects (default false — calls through isVisibleProject). */
	showArchived?: boolean;
	/** Which fields to substring-match against. Default: name + description. */
	searchFields?: SearchField[];
	/** Project ids in recency order (most-recent first). With no query, recents
	 *  surface at the top of the list. Items beyond the visible projects are
	 *  silently dropped. */
	recents?: string[];
}

type PickerProject = Pick<Project, "id" | "name" | "description" | "archived">;

/**
 * Filter + rank projects for the picker.
 *
 * - Always honors the archive filter (overridable via showArchived).
 * - With an empty query, recents surface first (in order), then the remaining
 *   projects in their input order.
 * - With a query, returns a substring-filtered subset; recency is ignored
 *   because the user is now driving the order with their typing.
 */
export function filterAndRankProjects<T extends PickerProject>(
	projects: T[] | undefined,
	query: string,
	options: FilterAndRankOptions = {},
): T[] {
	const { showArchived = false, searchFields = ["name", "description"], recents = [] } = options;
	const list = projects ?? [];
	const eligible = showArchived ? list : list.filter(isVisibleProject);
	const q = query.trim().toLowerCase();

	if (q === "") {
		const eligibleById = new Map(eligible.map((p) => [p.id, p]));
		const recentMatches: T[] = [];
		const seen = new Set<string>();
		for (const id of recents) {
			const match = eligibleById.get(id);
			if (match && !seen.has(id)) {
				recentMatches.push(match);
				seen.add(id);
			}
		}
		const rest = eligible.filter((p) => !seen.has(p.id));
		return [...recentMatches, ...rest];
	}

	return eligible.filter((p) =>
		searchFields.some((f) => {
			const v = p[f];
			return typeof v === "string" && v.toLowerCase().includes(q);
		}),
	);
}
