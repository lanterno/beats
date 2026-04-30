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
import { aggregateFlowByRepo, shortRepoPath } from "@/shared/lib/flowAggregation";

interface Props {
	projectId?: string;
	editorLanguage?: string;
	selectedRepo?: string;
	onSelectRepo?: (repo: string | undefined) => void;
}

export function FlowByRepo({ projectId, editorLanguage, selectedRepo, onSelectRepo }: Props = {}) {
	// FlowByRepo specifically does NOT filter its own data by selectedRepo —
	// it has to keep showing all repos so the user has somewhere to click
	// to switch. It DOES filter by projectId / editorLanguage because those
	// are picked elsewhere on the page and we want repo stats to honor them.
	const filter = projectId || editorLanguage ? { projectId, editorLanguage } : undefined;
	const { data: windows } = useFlowWindows(undefined, undefined, filter);
	const stats = useMemo(() => aggregateFlowByRepo(windows ?? [], 5), [windows]);

	if (stats.length === 0) return null;
	const peakAvg = Math.max(...stats.map((s) => s.avg));

	const handleClick = (repo: string) => {
		if (!onSelectRepo) return;
		onSelectRepo(selectedRepo === repo ? undefined : repo);
	};

	return (
		<div className="rounded-lg border border-border/60 bg-secondary/20 px-4 py-3 space-y-3">
			<div className="flex items-baseline justify-between">
				<p className="font-heading text-sm text-foreground">Flow by repo</p>
				<p className="text-[11px] text-muted-foreground">
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
							className={`w-full flex items-center gap-3 rounded-md px-1.5 py-1 transition-colors ${
								active ? "bg-accent/15" : "hover:bg-secondary/40"
							}`}
							aria-pressed={active}
						>
							<div
								className="text-foreground/80 truncate text-xs flex-1 min-w-0 text-left"
								title={s.repo}
							>
								{shortRepoPath(s.repo)}
							</div>
							<div className="flex-[2] h-1.5 rounded-full bg-secondary/60 relative overflow-hidden">
								<div
									className="absolute inset-y-0 left-0 bg-accent"
									style={{ width: `${(s.avg * 100).toFixed(1)}%` }}
								/>
							</div>
							<div className="text-[11px] tabular-nums text-foreground w-9 text-right">
								{Math.round(s.avg * 100)}
							</div>
							<div className="text-[10px] tabular-nums text-muted-foreground w-12 text-right">
								{s.minutes}m
							</div>
						</button>
					);
				})}
			</div>

			{stats.length >= 2 && (
				<p className="text-[10px] text-muted-foreground border-t border-border/40 pt-2">
					Best flow today on{" "}
					<span className="text-foreground">
						{shortRepoPath(stats.find((s) => s.avg === peakAvg)?.repo ?? "")}
					</span>{" "}
					at {Math.round(peakAvg * 100)}/100.
				</p>
			)}
		</div>
	);
}
