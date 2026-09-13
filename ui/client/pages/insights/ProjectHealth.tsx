/**
 * ProjectHealth Component
 * Shows health metrics and alerts for active projects.
 */

import { Activity, AlertTriangle } from "lucide-react";
import { Link } from "react-router";
import { useProjectHealth } from "@/entities/intelligence";
import { cn } from "@/shared/lib";
import { Panel } from "@/shared/ui";
import { LABEL } from "./styles";

export function ProjectHealth() {
	const { data: projects } = useProjectHealth();

	if (!projects || projects.length === 0) return null;

	return (
		<Panel padding="px-6 py-[22px]">
			<h3 className={cn(LABEL, "flex items-center gap-2 mb-3")}>
				<Activity className="w-3.5 h-3.5" />
				Project Health
			</h3>

			<div className="space-y-1">
				{projects.map((p) => (
					<Link
						key={p.project_id}
						to={`/project/${p.project_id}`}
						className={cn(
							"flex items-center gap-2.5 px-2 py-1.5 rounded-xl text-xs transition-colors hover:bg-secondary focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring",
							p.alert && "bg-destructive/10",
						)}
					>
						<span className="text-foreground font-bold truncate flex-1">{p.project_name}</span>
						{p.days_since_last !== null && p.days_since_last !== undefined && (
							<span className="text-muted-foreground font-medium tabular-nums">
								{p.days_since_last}d ago
							</span>
						)}
						{/* Mini sparkline for weekly goal trend */}
						{p.weekly_goal_trend.length > 0 && (
							<div className="flex items-end gap-px h-3">
								{p.weekly_goal_trend.map((h, i) => {
									const max = Math.max(...p.weekly_goal_trend, 0.1);
									return (
										<div
											key={i}
											className="w-1.5 bg-success/55 rounded-[2px]"
											style={{ height: `${Math.max(2, (h / max) * 12)}px` }}
										/>
									);
								})}
							</div>
						)}
						{p.alert && <AlertTriangle className="w-3 h-3 text-destructive shrink-0" />}
					</Link>
				))}
			</div>
		</Panel>
	);
}
