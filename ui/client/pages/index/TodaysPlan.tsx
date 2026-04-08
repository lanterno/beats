/**
 * Today's Plan Component
 * Set 1-3 time-boxed daily intentions and track progress.
 */

import { Check, Plus, Target, X } from "lucide-react";
import { useState } from "react";
import {
	useCreateIntention,
	useDeleteIntention,
	useIntentions,
	useUpdateIntention,
} from "@/entities/planning";
import { useProjects } from "@/entities/project";
import type { Intention } from "@/shared/api";
import { cn, formatDuration } from "@/shared/lib";
import { GoalRing } from "@/shared/ui";

interface TodaysPlanProps {
	/** Map of project_id -> today's tracked minutes */
	trackedMinutesByProject: Record<string, number>;
}

export function TodaysPlan({ trackedMinutesByProject }: TodaysPlanProps) {
	const { data: intentions } = useIntentions();
	const { data: projects } = useProjects();
	const createMutation = useCreateIntention();
	const updateMutation = useUpdateIntention();
	const deleteMutation = useDeleteIntention();

	const [adding, setAdding] = useState(false);
	const [newProjectId, setNewProjectId] = useState("");
	const [newMinutes, setNewMinutes] = useState(60);

	const activeProjects = (projects ?? []).filter((p) => !p.archived);
	const projectMap = new Map(activeProjects.map((p) => [p.id, p]));
	const items = intentions ?? [];

	const handleAdd = () => {
		if (!newProjectId) return;
		createMutation.mutate(
			{ projectId: newProjectId, plannedMinutes: newMinutes },
			{
				onSuccess: () => {
					setAdding(false);
					setNewProjectId("");
					setNewMinutes(60);
				},
			},
		);
	};

	const toggleComplete = (intention: Intention) => {
		updateMutation.mutate({
			intentionId: intention.id,
			updates: { completed: !intention.completed },
		});
	};

	const remove = (id: string) => {
		deleteMutation.mutate(id);
	};

	// Auto-check: if tracked time exceeds planned, mark as completed
	items.forEach((intention) => {
		const tracked = trackedMinutesByProject[intention.project_id] ?? 0;
		if (tracked >= intention.planned_minutes && !intention.completed) {
			updateMutation.mutate({
				intentionId: intention.id,
				updates: { completed: true },
			});
		}
	});

	return (
		<div>
			<div className="flex items-center justify-between mb-3">
				<h2 className="flex items-center gap-2 text-foreground font-medium text-sm">
					<Target className="w-3.5 h-3.5 text-accent/75" />
					Today's Plan
				</h2>
				{items.length < 3 && !adding && (
					<button
						onClick={() => setAdding(true)}
						className="flex items-center gap-1 text-xs text-muted-foreground hover:text-accent transition-colors"
					>
						<Plus className="w-3 h-3" />
						Add
					</button>
				)}
			</div>

			{items.length === 0 && !adding ? (
				<button
					onClick={() => setAdding(true)}
					className="w-full rounded-lg border border-dashed border-border py-4 text-center text-muted-foreground/50 text-xs hover:border-accent/30 hover:text-muted-foreground transition-colors"
				>
					Set your intentions for today
				</button>
			) : (
				<div className="rounded-lg border border-border/80 bg-card shadow-soft overflow-hidden">
					<div className="py-1">
						{items.map((intention) => {
							const project = projectMap.get(intention.project_id);
							const tracked = trackedMinutesByProject[intention.project_id] ?? 0;
							const pct =
								intention.planned_minutes > 0 ? (tracked / intention.planned_minutes) * 100 : 0;

							return (
								<div
									key={intention.id}
									className="flex items-center gap-2.5 px-3 py-2 hover:bg-secondary/30 transition-colors group"
								>
									<button onClick={() => toggleComplete(intention)}>
										<GoalRing percent={pct} size={22} strokeWidth={2.5} />
									</button>
									{project && (
										<div
											className="w-2 h-2 rounded-full shrink-0"
											style={{ backgroundColor: project.color }}
										/>
									)}
									<span
										className={cn(
											"text-sm flex-1 truncate",
											intention.completed
												? "text-muted-foreground line-through"
												: "text-foreground",
										)}
									>
										{project?.name ?? "Unknown"}
									</span>
									<span className="text-xs tabular-nums text-muted-foreground">
										{formatDuration(tracked)} / {formatDuration(intention.planned_minutes)}
									</span>
									<button
										onClick={() => remove(intention.id)}
										className="p-0.5 rounded text-muted-foreground/30 opacity-0 group-hover:opacity-100 hover:text-destructive transition-all"
									>
										<X className="w-3 h-3" />
									</button>
								</div>
							);
						})}
					</div>

					{/* Add form */}
					{adding && (
						<div className="border-t border-border/40 px-3 py-2 flex items-center gap-2">
							<select
								value={newProjectId}
								onChange={(e) => setNewProjectId(e.target.value)}
								className="flex-1 text-xs bg-secondary/50 border border-border rounded px-2 py-1.5 text-foreground focus:outline-none focus:ring-1 focus:ring-accent"
							>
								<option value="">Select project...</option>
								{activeProjects.map((p) => (
									<option key={p.id} value={p.id}>
										{p.name}
									</option>
								))}
							</select>
							<input
								type="number"
								value={newMinutes}
								onChange={(e) => setNewMinutes(parseInt(e.target.value, 10) || 0)}
								className="w-16 text-xs bg-secondary/50 border border-border rounded px-2 py-1.5 text-foreground text-center tabular-nums focus:outline-none focus:ring-1 focus:ring-accent"
								placeholder="min"
								min={5}
								step={15}
							/>
							<button
								onClick={handleAdd}
								disabled={!newProjectId}
								className="p-1.5 rounded bg-accent text-accent-foreground disabled:opacity-40 hover:bg-accent/85 transition-colors"
							>
								<Check className="w-3 h-3" />
							</button>
							<button
								onClick={() => setAdding(false)}
								className="p-1.5 rounded text-muted-foreground hover:text-foreground transition-colors"
							>
								<X className="w-3 h-3" />
							</button>
						</div>
					)}
				</div>
			)}
		</div>
	);
}
