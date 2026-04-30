/**
 * FlowByRepo — groups today's flow windows by their editor_repo and shows
 * average score + tracked minutes per repo. Surfaces an answer to "where do
 * I flow best?" that wasn't possible before the editor heartbeat pipeline.
 */
import { useMemo } from "react";
import { useFlowWindows } from "@/entities/session";

interface RepoStat {
	repo: string;
	avg: number;
	minutes: number;
	count: number;
}

export function FlowByRepo() {
	const { data: windows } = useFlowWindows();

	const stats = useMemo<RepoStat[]>(() => {
		if (!windows || windows.length === 0) return [];
		const byRepo = new Map<string, { sum: number; count: number }>();
		for (const w of windows) {
			const repo = w.editor_repo;
			if (!repo) continue;
			const cur = byRepo.get(repo) ?? { sum: 0, count: 0 };
			cur.sum += w.flow_score;
			cur.count += 1;
			byRepo.set(repo, cur);
		}
		return Array.from(byRepo.entries())
			.map(([repo, { sum, count }]) => ({
				repo,
				avg: sum / count,
				// Each window is approximately 1 minute of activity. The flush
				// interval is configurable but defaults to 60s, so this maps
				// 1:1 in practice — using count as minutes is the honest
				// approximation given we don't have window-duration here.
				minutes: count,
				count,
			}))
			.sort((a, b) => b.minutes - a.minutes)
			.slice(0, 5);
	}, [windows]);

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
							{shortRepo(s.repo)}
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
						{shortRepo(stats.find((s) => s.avg === peakAvg)?.repo ?? "")}
					</span>{" "}
					at {Math.round(peakAvg * 100)}/100.
				</p>
			)}
		</div>
	);
}

function shortRepo(path: string): string {
	const parts = path.split(/[\\/]/);
	const tail = parts.filter(Boolean).slice(-2).join("/");
	return tail || path;
}
