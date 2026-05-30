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
