/**
 * ProjectHealth Component
 * Shows health metrics and alerts for active projects.
 */

import { Activity, AlertTriangle } from "lucide-react";
import { useProjectHealth } from "@/entities/intelligence";
import { cn } from "@/shared/lib";

export function ProjectHealth() {
	const { data: projects } = useProjectHealth();

	if (!projects || projects.length === 0) return null;

	return (
		<div className="rounded-lg border border-border/80 bg-card shadow-soft px-4 py-3">
			<h3 className="flex items-center gap-2 text-sm font-medium text-foreground mb-3">
				<Activity className="w-3.5 h-3.5 text-accent/75" />
				Project Health
			</h3>

			<div className="space-y-2">
				{projects.map((p) => (
					<div
						key={p.project_id}
						className={cn(
							"flex items-center gap-2.5 px-2 py-1.5 rounded-md text-xs",
							p.alert && "bg-destructive/5 border border-destructive/20",
						)}
					>
						<span className="text-foreground font-medium truncate flex-1">{p.project_name}</span>
						{p.days_since_last !== null && p.days_since_last !== undefined && (
							<span className="text-muted-foreground tabular-nums">{p.days_since_last}d ago</span>
						)}
						{/* Mini sparkline for weekly goal trend */}
						{p.weekly_goal_trend.length > 0 && (
							<div className="flex items-end gap-px h-3">
								{p.weekly_goal_trend.map((h, i) => {
									const max = Math.max(...p.weekly_goal_trend, 0.1);
									return (
										<div
											key={i}
											className="w-1.5 bg-accent/40 rounded-sm"
											style={{ height: `${Math.max(2, (h / max) * 12)}px` }}
										/>
									);
								})}
							</div>
						)}
						{p.alert && <AlertTriangle className="w-3 h-3 text-destructive shrink-0" />}
					</div>
				))}
			</div>
		</div>
	);
}
