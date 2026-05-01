/**
 * useInsightsFilters — bundles the five URL-persisted filter axes the
 * Insights page exposes (project, tag, repo, language, bundle) into a
 * single hook with a count + clear-all helper.
 *
 * Lives next to Insights.tsx because it's specific to that page's
 * filter set; not in shared/lib. Worth its own hook for two reasons:
 * (1) the count + clearAll logic is testable in isolation without
 * mocking the rest of Insights, and (2) the page component reads
 * cleaner with a single state hook than five.
 */
import { useCallback, useEffect } from "react";
import { useUrlParam } from "@/shared/lib/useUrlParam";

export interface InsightsFilters {
	selectedProjectId: string | undefined;
	setSelectedProjectId: (v: string | undefined) => void;
	selectedTag: string | undefined;
	setSelectedTag: (v: string | undefined) => void;
	selectedRepo: string | undefined;
	setSelectedRepo: (v: string | undefined) => void;
	selectedLanguage: string | undefined;
	setSelectedLanguage: (v: string | undefined) => void;
	selectedBundleId: string | undefined;
	setSelectedBundleId: (v: string | undefined) => void;
	/** Number of filters with a non-empty value, 0–5. */
	activeFilterCount: number;
	/** Wipe every axis. Used by the "× clear all filters" header link. */
	clearAllFilters: () => void;
}

/** Predicate for the Esc → clear-all-filters keyboard shortcut.
 * Extracted from the useEffect so the guard rules are unit-testable
 * without rendering Insights. Conservative: only fires when:
 *
 * - the key is exactly Escape (no other key produces this code)
 * - no modifier is held (Cmd/Ctrl/Alt/Shift+Esc are reserved for
 *   browser/OS shortcuts; we shouldn't shadow them)
 * - the user isn't typing in a form control (Esc on a select clears
 *   it; on a search input cancels — natural focused behavior wins)
 * - at least one filter is set (Esc on a clean page does nothing,
 *   which means we don't preventDefault unnecessarily)
 */
export function shouldHandleEscClear(e: KeyboardEvent, hasActiveFilters: boolean): boolean {
	if (e.key !== "Escape") return false;
	if (e.metaKey || e.ctrlKey || e.altKey || e.shiftKey) return false;
	if (!hasActiveFilters) return false;
	const el = e.target as HTMLElement | null;
	if (!el) return true;
	const tag = el.tagName.toLowerCase();
	if (tag === "input" || tag === "textarea" || tag === "select") return false;
	if (el.isContentEditable) return false;
	return true;
}

export function useInsightsFilters(): InsightsFilters {
	const [selectedProjectId, setSelectedProjectId] = useUrlParam("project");
	const [selectedTag, setSelectedTag] = useUrlParam("tag");
	const [selectedRepo, setSelectedRepo] = useUrlParam("repo");
	const [selectedLanguage, setSelectedLanguage] = useUrlParam("language");
	const [selectedBundleId, setSelectedBundleId] = useUrlParam("bundle");

	const activeFilterCount =
		(selectedProjectId ? 1 : 0) +
		(selectedTag ? 1 : 0) +
		(selectedRepo ? 1 : 0) +
		(selectedLanguage ? 1 : 0) +
		(selectedBundleId ? 1 : 0);

	// useCallback so the keyboard-shortcut effect below has a stable
	// dependency — without it every render would tear down and re-add
	// the global keydown listener.
	const clearAllFilters = useCallback(() => {
		setSelectedProjectId(undefined);
		setSelectedTag(undefined);
		setSelectedRepo(undefined);
		setSelectedLanguage(undefined);
		setSelectedBundleId(undefined);
	}, [
		setSelectedProjectId,
		setSelectedTag,
		setSelectedRepo,
		setSelectedLanguage,
		setSelectedBundleId,
	]);

	// Esc clears every filter — natural ergonomic for keyboard users
	// who don't want to mouse over to the header link. No-op when
	// nothing is set (Esc shouldn't preventDefault on a clean page),
	// and skipped when the user is typing in an input or modifier
	// keys are held (preserves browser/system shortcuts that use Esc).
	useEffect(() => {
		const onKeyDown = (e: KeyboardEvent) => {
			if (shouldHandleEscClear(e, activeFilterCount > 0)) {
				e.preventDefault();
				clearAllFilters();
			}
		};
		window.addEventListener("keydown", onKeyDown);
		return () => window.removeEventListener("keydown", onKeyDown);
	}, [activeFilterCount, clearAllFilters]);

	return {
		selectedProjectId,
		setSelectedProjectId,
		selectedTag,
		setSelectedTag,
		selectedRepo,
		setSelectedRepo,
		selectedLanguage,
		setSelectedLanguage,
		selectedBundleId,
		setSelectedBundleId,
		activeFilterCount,
		clearAllFilters,
	};
}
