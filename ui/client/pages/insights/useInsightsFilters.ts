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

	const clearAllFilters = () => {
		setSelectedProjectId(undefined);
		setSelectedTag(undefined);
		setSelectedRepo(undefined);
		setSelectedLanguage(undefined);
		setSelectedBundleId(undefined);
	};

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
