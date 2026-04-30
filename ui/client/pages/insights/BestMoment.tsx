/**
 * BestMoment — surfaces the single highest-scoring flow window from the
 * last 7 days. Different shape than the aggregation cards: it picks one
 * moment and tells its full story (day, time, score, project, editor
 * context). The card hides itself when no window in the window crosses
 * a "real flow" threshold; calling out a 0.42 peak as "your best" reads
 * as faint praise.
 */
import { useMemo } from "react";
import { useProjects } from "@/entities/project";
import { useFlowWindowsLastDays } from "@/entities/session";
import type { FlowWindow } from "@/shared/api";
import { shortRepoPath } from "@/shared/lib/flowAggregation";

const MIN_PEAK = 0.7; // below this, we don't celebrate

const DAY_NAMES = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];

export function BestMoment({ projectId }: { projectId?: string } = {}) {
	const filter = projectId ? { projectId } : undefined;
	const { data: windows } = useFlowWindowsLastDays(7, filter);
	const { data: projects } = useProjects();

	const best = useMemo<FlowWindow | null>(() => {
		if (!windows || windows.length === 0) return null;
		let peak: FlowWindow | null = null;
		for (const w of windows) {
			if (peak === null || w.flow_score > peak.flow_score) peak = w;
		}
		return peak;
	}, [windows]);

	if (!best || best.flow_score < MIN_PEAK) return null;

	const start = new Date(best.window_start);
	const dayName = DAY_NAMES[start.getDay()];
	const isToday = sameLocalDate(start, new Date());
	const timeStr = `${String(start.getHours()).padStart(2, "0")}:${String(start.getMinutes()).padStart(2, "0")}`;
	const score = Math.round(best.flow_score * 100);

	const projectName =
		best.active_project_id != null
			? (projects ?? []).find((p) => p.id === best.active_project_id)?.name
			: undefined;

	return (
		<div className="rounded-lg border border-accent/30 bg-accent/5 px-4 py-3">
			<div className="flex items-start gap-4">
				<div className="font-heading tabular-nums text-3xl text-accent leading-none pt-1">
					{score}
				</div>
				<div className="flex-1 min-w-0">
					<p className="text-[10px] uppercase tracking-[0.14em] text-muted-foreground mb-1">
						Peak this week
					</p>
					<p className="text-sm text-foreground">
						{isToday ? "Today" : dayName} at <span className="tabular-nums">{timeStr}</span>
					</p>
					<div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-muted-foreground">
						{projectName && (
							<span>
								<span className="text-foreground/70">{projectName}</span>
							</span>
						)}
						{best.dominant_category && (
							<span className="uppercase tracking-wider text-[9px]">{best.dominant_category}</span>
						)}
						{best.editor_repo && (
							<span className="text-foreground/70 truncate" title={best.editor_repo}>
								{shortRepoPath(best.editor_repo)}
								{best.editor_branch ? (
									<span className="text-muted-foreground"> · {best.editor_branch}</span>
								) : null}
							</span>
						)}
					</div>
				</div>
			</div>
		</div>
	);
}

function sameLocalDate(a: Date, b: Date): boolean {
	return (
		a.getFullYear() === b.getFullYear() &&
		a.getMonth() === b.getMonth() &&
		a.getDate() === b.getDate()
	);
}
