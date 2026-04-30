/**
 * FlowByRepo — groups today's flow windows by their editor_repo and shows
 * average score + tracked minutes per repo. Surfaces an answer to "where do
 * I flow best?" that wasn't possible before the editor heartbeat pipeline.
 */
import { useMemo } from "react";
import { useFlowWindows } from "@/entities/session";
import { aggregateFlowByRepo, shortRepoPath } from "@/shared/lib/flowAggregation";

export function FlowByRepo({ projectId }: { projectId?: string } = {}) {
	const filter = projectId ? { projectId } : undefined;
	const { data: windows } = useFlowWindows(undefined, undefined, filter);
	const stats = useMemo(() => aggregateFlowByRepo(windows ?? [], 5), [windows]);

	if (stats.length === 0) return null;
	const peakAvg = Math.max(...stats.map((s) => s.avg));

	return (
		<div className="rounded-lg border border-border/60 bg-secondary/20 px-4 py-3 space-y-3">
			<div className="flex items-baseline justify-between">
				<p className="font-heading text-sm text-foreground">Flow by repo</p>
				<p className="text-[11px] text-muted-foreground">
					today · {stats.length} {stats.length === 1 ? "repo" : "repos"}
				</p>
			</div>

			<div className="space-y-2">
				{stats.map((s) => (
					<div key={s.repo} className="flex items-center gap-3">
						<div className="text-foreground/80 truncate text-xs flex-1 min-w-0" title={s.repo}>
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
					</div>
				))}
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
