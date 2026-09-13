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
import { Button, Panel } from "@/shared/ui";

/** A section heading on the sky: the mockup's `.lbl`, in ink so it reads there. */
const SKY_HEADING =
	"px-2 mb-2.5 font-body text-[10.5px] font-bold uppercase tracking-[0.14em] text-foreground";

// The mockup's `.dlg input`: a wash, no border, the figures face.
const FIELD =
	"w-[4.5rem] text-right text-[13px] font-mono font-bold bg-secondary rounded-xl px-2.5 py-1.5 text-foreground focus:outline-hidden focus:ring-[3px] focus:ring-accent";

/** A project with no colour. */
const NO_COLOR = "var(--color-muted-foreground)";

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
			<h1 className="font-heading text-2xl font-extrabold tracking-[-0.02em] text-foreground mb-1 px-2 flex items-center gap-2">
				<CalendarDays className="w-6 h-6 text-muted-foreground" />
				Weekly Plan
			</h1>
			{/* On the bare sky the muted ink is under 3:1 and ink at 80 % is 4:1 at its top; 90 % reads. */}
			<p className="text-sm font-medium text-foreground/90 mb-8 px-2">
				Set time budgets for the week. Week of {thisMonday}.
			</p>

			<div className="grid md:grid-cols-2 gap-6">
				{/* Last week summary */}
				<div>
					<h2 className={SKY_HEADING}>
						Last week <span className="font-mono tracking-normal">({lastMonday})</span>
					</h2>
					<Panel padding="px-5 py-4" className="space-y-2">
						{lastWeekPlan?.budgets && lastWeekPlan.budgets.length > 0 ? (
							lastWeekPlan.budgets.map((b) => {
								const project = activeProjects.find((p) => p.id === b.project_id);
								return (
									<div key={b.project_id} className="flex items-center justify-between">
										<span className="text-[13.5px] font-bold text-foreground">
											{project?.name ?? "Unknown"}
										</span>
										<span className="text-[12.5px] font-mono font-bold text-muted-foreground">
											{b.planned_hours}h planned
										</span>
									</div>
								);
							})
						) : (
							<p className="text-xs font-medium text-muted-foreground">No plan set last week</p>
						)}
					</Panel>
				</div>

				{/* This week budgets */}
				<div>
					<h2 className={SKY_HEADING}>This week</h2>
					<Panel padding="px-5 py-4" className="space-y-3">
						{activeProjects.map((p) => (
							<div key={p.id} className="flex items-center gap-3">
								<div
									className="w-2 h-2 rounded-full shrink-0"
									style={{ backgroundColor: p.color ?? NO_COLOR }}
								/>
								<span className="text-[13.5px] font-bold text-foreground flex-1 truncate">
									{p.name}
								</span>
								<input
									type="number"
									min={0}
									max={80}
									step={0.5}
									value={budgets[p.id] ?? 0}
									onChange={(e) =>
										setBudgets((prev) => ({ ...prev, [p.id]: Number(e.target.value) || 0 }))
									}
									className={FIELD}
								/>
								<span className="text-xs font-medium text-muted-foreground w-3">h</span>
							</div>
						))}

						<div className="pt-3 border-t border-border flex items-center justify-between">
							<span className="text-sm font-bold text-foreground">
								Total: {formatDuration(totalHours * 60)}
							</span>
							<Button type="button" size="sm" onClick={handleSave}>
								<Save className="w-3.5 h-3.5" />
								Save Plan
							</Button>
						</div>
					</Panel>
				</div>
			</div>
		</div>
	);
}
