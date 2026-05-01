/**
 * FlowFilterChips — dismissible pills for the repo / language / app
 * filters chosen by clicking a row on the matching Flow* card.
 *
 * Mirrors the project / tag dropdown affordance — explicit, dismissible,
 * sibling pills compose visually so the user sees that all active
 * filters are AND-applied.
 *
 * Includes a "↓ csv" link that downloads exactly the slice the user is
 * looking at — when chips are visible, the user has invested clicks
 * into a specific view and wanting to capture it is a natural next
 * action. (The unfiltered "all of today" case is rare enough that we
 * skip the affordance there to keep the page quiet.)
 */
import { downloadFile } from "@/shared/lib/downloadFile";

export interface FlowFilterChipsProps {
	repo?: string;
	language?: string;
	bundleId?: string;
	onClearRepo: () => void;
	onClearLanguage: () => void;
	onClearBundleId: () => void;
}

export function FlowFilterChips({
	repo,
	language,
	bundleId,
	onClearRepo,
	onClearLanguage,
	onClearBundleId,
}: FlowFilterChipsProps) {
	return (
		<div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-muted-foreground">
			{repo && (
				<FilterPill
					label="repo"
					value={shortRepoTail(repo)}
					title={repo}
					onClear={onClearRepo}
					clearLabel="Clear repo filter"
				/>
			)}
			{language && (
				<FilterPill
					label="language"
					value={language}
					title={language}
					onClear={onClearLanguage}
					clearLabel="Clear language filter"
				/>
			)}
			{bundleId && (
				<FilterPill
					label="app"
					value={shortBundleTail(bundleId)}
					title={bundleId}
					onClear={onClearBundleId}
					clearLabel="Clear app filter"
				/>
			)}
			<button
				type="button"
				onClick={() => {
					const date = new Date().toISOString().slice(0, 10).replace(/-/g, "");
					downloadFile(
						flowWindowsCsvHref({ repo, language, bundleId }),
						`beats_flow_windows_${date}.csv`,
					);
				}}
				className="text-accent hover:underline tabular-nums"
				title="Download the visible flow-window slice as CSV"
			>
				↓ csv
			</button>
		</div>
	);
}

/** Build the /flow-windows.csv URL with the same filter mapping the
 * JSON endpoint uses. Exported only for tests. */
export function flowWindowsCsvHref({
	repo,
	language,
	bundleId,
}: {
	repo?: string;
	language?: string;
	bundleId?: string;
}): string {
	const params = new URLSearchParams();
	if (repo) params.set("editor_repo", repo);
	if (language) params.set("editor_language", language);
	if (bundleId) params.set("bundle_id", bundleId);
	const q = params.toString();
	return `/api/signals/flow-windows.csv${q ? `?${q}` : ""}`;
}

function shortBundleTail(bundleId: string): string {
	// Reverse-DNS bundle ids: "com.microsoft.VSCode" → "VSCode". Same
	// fallback FlowByApp uses for unknown ids; good enough for a chip.
	const dot = bundleId.lastIndexOf(".");
	return dot >= 0 ? bundleId.slice(dot + 1) : bundleId;
}

function shortRepoTail(repo: string): string {
	const parts = repo.split(/[\\/]/).filter(Boolean);
	return parts.length > 2 ? parts.slice(-2).join("/") : parts.join("/") || repo;
}

function FilterPill({
	label,
	value,
	title,
	onClear,
	clearLabel,
}: {
	label: string;
	value: string;
	title: string;
	onClear: () => void;
	clearLabel: string;
}) {
	return (
		<span className="flex items-center gap-2">
			<span>Filtered to {label}</span>
			<span className="text-foreground/80 font-mono" title={title}>
				{value}
			</span>
			<button
				type="button"
				onClick={onClear}
				className="text-accent hover:underline tabular-nums"
				aria-label={clearLabel}
			>
				clear
			</button>
		</span>
	);
}
