/**
 * ProjectPulseList Component
 * Compact project rows showing sparkline, today's hours, and goal progress.
 * Designed to show data NOT already in the sidebar (which shows name + weekly hours).
 */

import { Layers } from "lucide-react";
import { useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { useProjects } from "@/entities/project";
import { useAllBeats } from "@/entities/session";
import type { ApiBeat } from "@/shared/api";
import { cn, getCurrentWeekRange, getDayName, parseUtcIso, startOfDay } from "@/shared/lib";
import { EmptyState, GoalRing } from "@/shared/ui";

interface DaySummary {
	day: string;
	hours: number;
	date: Date;
	totalMinutes: number;
}

function MiniSparkline({ data }: { data: DaySummary[] }) {
	const maxMinutes = Math.max(...data.map((d) => d.totalMinutes), 1);

	return (
		<div className="flex items-end gap-px h-3 shrink-0">
			{data.map((day, i) => {
				const h = day.totalMinutes > 0 ? Math.max((day.totalMinutes / maxMinutes) * 12, 1.5) : 0;
				const isToday = day.date.toDateString() === new Date().toDateString();
				return (
					<div
						key={i}
						className={cn(
							"w-1.5 rounded-t-sm origin-bottom",
							isToday
								? "bg-accent"
								: day.totalMinutes > 0
									? "bg-muted-foreground/35"
									: "bg-muted-foreground/10",
						)}
						style={{
							height: `${h}px`,
							animation: `sparkGrow 300ms ease-out ${i * 40}ms both`,
						}}
					/>
				);
			})}
		</div>
	);
}

function buildSummaries(beats: ApiBeat[]): Record<string, DaySummary[]> {
	const { start, end } = getCurrentWeekRange();
	const weeklyBeats = beats.filter((beat) => {
		if (!beat.start || !beat.end) return false;
		const startTime = parseUtcIso(beat.start);
		return startTime >= start && startTime <= end;
	});

	// Group by project
	const byProject = new Map<string, Map<string, number>>();
	for (const beat of weeklyBeats) {
		if (!beat.start || !beat.end || !beat.project_id) continue;
		const duration = (new Date(beat.end).getTime() - new Date(beat.start).getTime()) / 1000 / 60;
		const dayKey = parseUtcIso(beat.start).toDateString();
		if (!byProject.has(beat.project_id)) byProject.set(beat.project_id, new Map());
		const dailyTotals = byProject.get(beat.project_id)!;
		dailyTotals.set(dayKey, (dailyTotals.get(dayKey) || 0) + duration);
	}

	const { start: weekStart } = getCurrentWeekRange();
	const result: Record<string, DaySummary[]> = {};
	for (const [projectId, dailyTotals] of byProject) {
		result[projectId] = Array.from({ length: 7 }, (_, i) => {
			const dayDate = new Date(weekStart);
			dayDate.setDate(weekStart.getDate() + i);
			dayDate.setHours(0, 0, 0, 0);
			const minutes = dailyTotals.get(dayDate.toDateString()) || 0;
			return {
				day: getDayName(dayDate),
				hours: minutes / 60,
				date: dayDate,
				totalMinutes: minutes,
			};
		});
	}
	return result;
}

export function ProjectPulseList() {
	const navigate = useNavigate();
	const { data: projects } = useProjects();
	const { data: allBeats } = useAllBeats();

	const summaries = useMemo(() => (allBeats ? buildSummaries(allBeats) : undefined), [allBeats]);

	const projectsList = projects || [];

	const active = projectsList
		.filter((p) => p.weeklyMinutes > 0)
		.sort((a, b) => b.weeklyMinutes - a.weeklyMinutes);
	const inactive = projectsList
		.filter((p) => p.weeklyMinutes === 0)
		.sort((a, b) => a.name.localeCompare(b.name));
	const sorted = [...active, ...inactive];

	const today = startOfDay();

	if (sorted.length === 0) {
		return (
			<div>
				<h2 className="flex items-center gap-2 text-foreground font-medium text-sm mb-3">
					<Layers className="w-3.5 h-3.5 text-accent/75" />
					Projects
				</h2>
				<div className="rounded-lg border border-dashed border-border">
					<EmptyState variant="seedling" message="No projects yet. Create one to start tracking." />
				</div>
			</div>
		);
	}

	return (
		<div>
			<h2 className="flex items-center gap-2 text-foreground font-medium text-sm mb-3">
				<Layers className="w-3.5 h-3.5 text-accent/75" />
				Projects
			</h2>

			<div className="rounded-lg border border-border/80 bg-card shadow-soft overflow-hidden">
				<div className="py-1">
					{sorted.map((project) => {
						const summary = summaries?.[project.id];
						const todayMinutes =
							summary?.find((d) => d.date.toDateString() === today.toDateString())?.totalMinutes ??
							0;
						const todayHours = todayMinutes / 60;
						const isInactive = project.weeklyMinutes === 0;
						// Honor "no goal" overrides: when overridden=true and goal is null,
						// don't fall back to project.weeklyGoal — the user explicitly opted out.
						const dashGoal = project.effectiveGoalOverridden
							? (project.effectiveGoal ?? null)
							: (project.effectiveGoal ?? project.weeklyGoal ?? null);
						const dashGoalType = project.effectiveGoalType ?? project.goalType ?? "target";
						const goalPct = dashGoal
							? Math.min((project.weeklyMinutes / 60 / dashGoal) * 100, 100)
							: null;

						return (
							<button
								key={project.id}
								onClick={() => navigate(`/project/${project.id}`)}
								className={cn(
									"w-full flex items-center gap-2.5 px-3 py-2 hover:bg-secondary/40 transition-colors text-left",
									isInactive && "opacity-45",
								)}
							>
								<div
									className="w-2 h-2 rounded-full shrink-0"
									style={{ backgroundColor: project.color }}
								/>
								<span className="text-sm font-medium text-foreground truncate min-w-0 flex-1">
									{project.name}
								</span>

								{summary && <MiniSparkline data={summary} />}

								<span
									className={cn(
										"text-xs tabular-nums shrink-0 w-10 text-right",
										todayHours > 0 ? "text-foreground" : "text-muted-foreground/40",
									)}
								>
									{todayHours > 0 ? `${todayHours.toFixed(1)}h` : "—"}
								</span>

								{goalPct !== null && (
									<GoalRing
										percent={goalPct}
										size={22}
										strokeWidth={2.5}
										isCap={dashGoalType === "cap"}
									/>
								)}
							</button>
						);
					})}
				</div>
			</div>
		</div>
	);
}
