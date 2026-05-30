/**
 * ProjectHealthRail — alerts + recency + a tiny goal-trend sparkline + the
 * project's average focus score. Brings the intelligence signals that
 * Insights surfaces globally onto the project's own page (the missing-pull
 * the completeness critic flagged in the gap review).
 *
 * - When there's an active alert (stale_project / intention_completion_low),
 *   show it with a Snooze 7d button that dismisses the corresponding inbox
 *   item server-side.
 * - When there's no alert, render a friendly "All clear — last tracked X
 *   days ago" line so the rail doesn't disappear and force the user to
 *   wonder where the signal went.
 *
 * P4.3 of the project-management revamp.
 */

import { Activity, AlertTriangle, Loader2, ZapOff } from "lucide-react";
import { useMemo } from "react";
import { toast } from "sonner";
import { useDismissInboxItem, useFocusScores, useProjectHealth } from "@/entities/intelligence";
import type { Session } from "@/entities/session";
import { describeError } from "@/shared/api";
import { cn, parseUtcIso, startOfDay } from "@/shared/lib";

interface ProjectHealthRailProps {
	projectId: string;
	/** Today's sessions for this project — fed in by the parent so we don't
	 *  re-fetch what ProjectDetails already has. */
	todaysProjectSessions: Session[];
}

function describeAlert(alert: string): string {
	switch (alert) {
		case "stale_project":
			return "This project has been quiet for a while.";
		case "intention_completion_low":
			return "Recent intentions aren't getting completed.";
		default:
			return alert;
	}
}

function formatRelativeDays(days: number | null | undefined): string {
	if (days == null) return "never";
	if (days <= 0) return "today";
	if (days === 1) return "1 day ago";
	return `${days} days ago`;
}

export function ProjectHealthRail({ projectId, todaysProjectSessions }: ProjectHealthRailProps) {
	const { data: healths } = useProjectHealth();
	const { data: focusScores } = useFocusScores();
	const dismiss = useDismissInboxItem();

	const health = useMemo(
		() => (healths ?? []).find((h) => h.project_id === projectId) ?? null,
		[healths, projectId],
	);

	// Focus average across THIS project's sessions today.
	const focusAvg = useMemo(() => {
		if (!focusScores || focusScores.length === 0) return null;
		const today = startOfDay();
		const todayBeatIds = new Set(
			todaysProjectSessions.filter((s) => parseUtcIso(s.startTime) >= today).map((s) => s.id),
		);
		if (todayBeatIds.size === 0) return null;
		const matching = focusScores.filter((f) => todayBeatIds.has(f.beat_id));
		if (matching.length === 0) return null;
		return Math.round(matching.reduce((sum, f) => sum + f.score, 0) / matching.length);
	}, [focusScores, todaysProjectSessions]);

	// Don't take up space until something's loaded.
	if (!health) return null;

	const handleSnooze = () => {
		dismiss.mutate(`project_health:${projectId}`, {
			onSuccess: () => toast.success("Snoozed for 7 days"),
			onError: (err) => toast.error(describeError(err, "Failed to snooze")),
		});
	};

	const trend = health.weekly_goal_trend ?? [];
	const trendMax = Math.max(...trend, 0.1);

	return (
		<section
			aria-labelledby="project-health-title"
			className={cn(
				"mt-4 rounded-lg border bg-card px-3 py-2.5",
				health.alert ? "border-destructive/40 bg-destructive/5" : "border-border/60",
			)}
		>
			<header className="flex items-center gap-2 mb-1.5">
				<Activity className="w-3.5 h-3.5 text-accent shrink-0" aria-hidden="true" />
				<h3
					id="project-health-title"
					className="text-xs font-semibold uppercase tracking-[0.12em] text-muted-foreground"
				>
					Project health
				</h3>
			</header>

			<div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-xs">
				{health.alert ? (
					<div className="flex items-center gap-2 text-foreground">
						<AlertTriangle className="w-3.5 h-3.5 text-destructive shrink-0" aria-hidden="true" />
						<span>{describeAlert(health.alert)}</span>
						<button
							type="button"
							onClick={handleSnooze}
							disabled={dismiss.isPending}
							className="inline-flex items-center gap-1 rounded border border-border bg-background px-2 py-0.5 text-[11px] text-muted-foreground hover:text-foreground hover:border-muted-foreground/60 transition-colors disabled:opacity-50 focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-accent/40"
						>
							{dismiss.isPending ? (
								<Loader2 className="w-3 h-3 animate-spin" />
							) : (
								<ZapOff className="w-3 h-3" />
							)}
							Snooze 7d
						</button>
					</div>
				) : (
					<span className="text-muted-foreground">
						All clear — last tracked {formatRelativeDays(health.days_since_last)}.
					</span>
				)}

				<div className="flex items-center gap-2 text-muted-foreground">
					<span>Goal trend</span>
					{trend.length > 0 ? (
						<div className="flex items-end gap-px h-3">
							{trend.map((h, i) => (
								<div
									key={i}
									className="w-1.5 bg-accent/50 rounded-sm"
									style={{ height: `${Math.max(2, (h / trendMax) * 12)}px` }}
								/>
							))}
						</div>
					) : (
						<span className="text-muted-foreground/40">—</span>
					)}
				</div>

				{focusAvg !== null && (
					<div
						className="flex items-center gap-1.5 text-muted-foreground"
						title="Average focus score across today's sessions on this project"
					>
						<span>Focus today</span>
						<span className="text-foreground tabular-nums font-medium">{focusAvg}</span>
					</div>
				)}
			</div>
		</section>
	);
}
