/**
 * FlowByRepo — groups today's flow windows by their editor_repo and shows
 * average score + tracked minutes per repo. Surfaces an answer to "where do
 * I flow best?" that wasn't possible before the editor heartbeat pipeline.
 *
 * Rows are clickable: tapping one toggles the Insights-page-wide
 * `selectedRepo` filter that narrows every other Flow card to that
 * workspace. Tapping the same row again clears the filter.
 */
import { useMemo } from "react";
import { useFlowWindows } from "@/entities/session";
import { aggregateFlowByRepo, cn, shortRepoPath } from "@/shared/lib";
import { Panel } from "@/shared/ui";
import { FOOTNOTE, LABEL, META, ROW } from "./styles";

interface Props {
	projectId?: string;
	editorLanguage?: string;
	bundleId?: string;
	selectedRepo?: string;
	onSelectRepo?: (repo: string | undefined) => void;
}

export function FlowByRepo({
	projectId,
	editorLanguage,
	bundleId,
	selectedRepo,
	onSelectRepo,
}: Props = {}) {
	// FlowByRepo specifically does NOT filter its own data by selectedRepo —
	// it has to keep showing all repos so the user has somewhere to click
	// to switch. It DOES filter by the other dimensions (project, language,
	// bundle) because those are picked elsewhere on the page and we want
	// repo stats to honor them.
	const filter =
		projectId || editorLanguage || bundleId ? { projectId, editorLanguage, bundleId } : undefined;
	const { data: windows } = useFlowWindows(undefined, undefined, filter);
	const stats = useMemo(() => aggregateFlowByRepo(windows ?? [], 5), [windows]);

	if (stats.length === 0) return null;
	const peakAvg = Math.max(...stats.map((s) => s.avg));

	const handleClick = (repo: string) => {
		if (!onSelectRepo) return;
		onSelectRepo(selectedRepo === repo ? undefined : repo);
	};

	return (
		<Panel padding="px-6 py-[22px]" className="space-y-3">
			<div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
				<p className={LABEL}>Flow by repo</p>
				<p className={META}>
					today · {stats.length} {stats.length === 1 ? "repo" : "repos"}
				</p>
			</div>

			<div className="space-y-1">
				{stats.map((s) => {
					const active = selectedRepo === s.repo;
					return (
						<button
							type="button"
							key={s.repo}
							onClick={() => handleClick(s.repo)}
							className={cn(
								ROW,
								"w-full flex items-center gap-3 px-2 py-1.5",
								active ? "bg-sidebar-accent" : "hover:bg-secondary",
							)}
							aria-pressed={active}
						>
							<div
								className="text-foreground font-medium truncate text-xs flex-1 min-w-0 text-left"
								title={s.repo}
							>
								{shortRepoPath(s.repo)}
							</div>
							<div className="flex-[2] h-1.5 rounded-full bg-muted relative overflow-hidden">
								<div
									className="absolute inset-y-0 left-0 rounded-full bg-success/70"
									style={{ width: `${(s.avg * 100).toFixed(1)}%` }}
								/>
							</div>
							<div className="text-xs font-bold font-mono tabular-nums text-foreground w-9 text-right">
								{Math.round(s.avg * 100)}
							</div>
							<div className="text-[11px] font-medium tabular-nums text-muted-foreground w-12 text-right">
								{s.minutes}m
							</div>
						</button>
					);
				})}
			</div>

			{stats.length >= 2 && (
				<p className={FOOTNOTE}>
					Best flow today on{" "}
					<span className="text-foreground font-bold">
						{shortRepoPath(stats.find((s) => s.avg === peakAvg)?.repo ?? "")}
					</span>{" "}
					at {Math.round(peakAvg * 100)}/100.
				</p>
			)}
		</Panel>
	);
}
