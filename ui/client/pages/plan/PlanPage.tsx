/**
 * Weekly Planning Page
 * Last week's summary side-by-side with this week's time budgets.
 */

import { CalendarDays, Save } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { useUpsertWeeklyPlan, useWeeklyPlan } from "@/entities/planning";
import { useProjects } from "@/entities/project";
import { formatDuration, getMondayOfWeeksAgo } from "@/shared/lib";

function getMonday(weeksAgo: number): string {
	return getMondayOfWeeksAgo(weeksAgo).toISOString().slice(0, 10);
}

export default function PlanPage() {
	const thisMonday = getMonday(0);
	const lastMonday = getMonday(1);

	const { data: projects } = useProjects();
	const { data: lastWeekPlan } = useWeeklyPlan(lastMonday);
	const { data: thisWeekPlan } = useWeeklyPlan(thisMonday);
	const upsertPlan = useUpsertWeeklyPlan();

	const activeProjects = (projects ?? []).filter((p) => !p.archived);

	const [budgets, setBudgets] = useState<Record<string, number>>({});

	// Initialize budgets from existing plan
	useEffect(() => {
		if (thisWeekPlan?.budgets) {
			const map: Record<string, number> = {};
			for (const b of thisWeekPlan.budgets) {
				map[b.project_id] = b.planned_hours;
			}
			setBudgets(map);
		}
	}, [thisWeekPlan]);

	const handleSave = useCallback(() => {
		const entries = Object.entries(budgets)
			.filter(([, hours]) => hours > 0)
			.map(([project_id, planned_hours]) => ({ project_id, planned_hours }));
		upsertPlan.mutate(
			{ weekOf: thisMonday, budgets: entries },
			{ onSuccess: () => toast.success("Weekly plan saved") },
		);
	}, [budgets, thisMonday, upsertPlan]);

	const totalHours = Object.values(budgets).reduce((sum, h) => sum + h, 0);

	return (
		<div className="max-w-4xl mx-auto px-6 py-8">
			<h1 className="font-heading text-2xl text-foreground mb-1 flex items-center gap-2">
				<CalendarDays className="w-6 h-6 text-accent" />
				Weekly Plan
			</h1>
			<p className="text-sm text-muted-foreground mb-8">
				Set time budgets for the week. Week of {thisMonday}.
			</p>

			<div className="grid md:grid-cols-2 gap-6">
				{/* Last week summary */}
				<div>
					<h2 className="text-sm font-medium text-muted-foreground mb-3">
						Last week ({lastMonday})
					</h2>
					<div className="rounded-lg border border-border/80 bg-card shadow-soft p-4 space-y-2">
						{lastWeekPlan?.budgets && lastWeekPlan.budgets.length > 0 ? (
							lastWeekPlan.budgets.map((b) => {
								const project = activeProjects.find((p) => p.id === b.project_id);
								return (
									<div key={b.project_id} className="flex items-center justify-between">
										<span className="text-sm text-foreground">{project?.name ?? "Unknown"}</span>
										<span className="text-sm tabular-nums text-muted-foreground">
											{b.planned_hours}h planned
										</span>
									</div>
								);
							})
						) : (
							<p className="text-xs text-muted-foreground/60 italic">No plan set last week</p>
						)}
					</div>
				</div>

				{/* This week budgets */}
				<div>
					<h2 className="text-sm font-medium text-foreground mb-3">This week</h2>
					<div className="rounded-lg border border-border/80 bg-card shadow-soft p-4 space-y-3">
						{activeProjects.map((p) => (
							<div key={p.id} className="flex items-center gap-3">
								<div
									className="w-2 h-2 rounded-full shrink-0"
									style={{ backgroundColor: p.color ?? "#888" }}
								/>
								<span className="text-sm text-foreground flex-1 truncate">{p.name}</span>
								<input
									type="number"
									min={0}
									max={80}
									step={0.5}
									value={budgets[p.id] ?? 0}
									onChange={(e) =>
										setBudgets((prev) => ({ ...prev, [p.id]: Number(e.target.value) || 0 }))
									}
									className="w-16 text-right text-sm tabular-nums bg-secondary/50 border border-border rounded px-2 py-1 text-foreground focus:outline-none focus:ring-1 focus:ring-accent"
								/>
								<span className="text-xs text-muted-foreground w-3">h</span>
							</div>
						))}

						<div className="pt-3 border-t border-border/40 flex items-center justify-between">
							<span className="text-sm font-medium text-foreground">
								Total: {formatDuration(totalHours * 60)}
							</span>
							<button
								onClick={handleSave}
								className="flex items-center gap-1.5 px-4 py-2 text-sm font-medium rounded-md bg-accent text-accent-foreground hover:bg-accent/85 transition-colors"
							>
								<Save className="w-3.5 h-3.5" />
								Save Plan
							</button>
						</div>
					</div>
				</div>
			</div>
		</div>
	);
}
